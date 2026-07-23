from types import SimpleNamespace

from ..speciation import SpeciationService
from ..speciation_traits import (
    add_differentiation_noise,
    apply_tradeoff_penalties,
    clamp_traits_to_limit,
    enforce_trait_tradeoffs,
    validate_trait_changes,
)


def _limits(
    *,
    total: float = 100.0,
    specialized: float = 20.0,
    base: float = 10.0,
) -> dict:
    return {
        "total": total,
        "specialized": specialized,
        "base": base,
    }


def _validate(
    old_traits: dict,
    new_traits: dict,
    *,
    limits: dict | None = None,
) -> tuple[bool, str]:
    return validate_trait_changes(
        old_traits,
        new_traits,
        2.5,
        lambda trophic_level: limits or _limits(),
    )


def test_trait_validation_rejects_net_gain_above_six_first() -> None:
    assert _validate({"speed": 1.0}, {"speed": 7.1}) == (
        False,
        "属性总和净增加6.1，超过上限6.0（建议≤3.0）",
    )


def test_trait_validation_rejects_total_above_trophic_limit() -> None:
    assert _validate(
        {"speed": 6.0, "armor": 5.0},
        {"speed": 6.0, "armor": 5.0},
        limits=_limits(total=10.0),
    ) == (
        False,
        "属性总和11.0超过营养级T2.5的上限10.0",
    )


def test_trait_validation_reports_first_specialized_trait_in_input_order() -> None:
    assert _validate(
        {"speed": 9.0, "armor": 10.0},
        {"speed": 9.0, "armor": 10.0},
        limits=_limits(specialized=8.0),
    ) == (
        False,
        "属性speed=9.0超过特化上限8.0",
    )


def test_trait_validation_rejects_more_than_two_traits_above_base_limit() -> None:
    traits = {"speed": 6.0, "armor": 6.0, "reproduction": 6.0}

    assert _validate(
        traits,
        traits,
        limits=_limits(base=5.0),
    ) == (
        False,
        "3个属性超过基础上限5.0，最多允许2个",
    )


def test_trait_validation_rejects_large_gain_without_a_decrease() -> None:
    assert _validate(
        {"speed": 1.0, "armor": 1.0},
        {"speed": 6.0, "armor": 1.0},
    ) == (
        False,
        "净增益5.0但无权衡代价（需要至少一项属性降低）",
    )


def test_trait_validation_preserves_exact_boundaries_and_compensating_decrease() -> None:
    assert _validate(
        {"speed": 1.0, "armor": 1.0},
        {"speed": 5.0, "armor": 1.0},
    ) == (True, "验证通过")
    assert _validate(
        {"speed": 1.0, "armor": 5.0},
        {"speed": 10.0, "armor": 1.0},
        limits=_limits(total=11.0, specialized=10.0, base=9.0),
    ) == (True, "验证通过")


def test_service_trait_validation_delegate_uses_bound_limit_calculator() -> None:
    calls = []
    service = object.__new__(SpeciationService)
    service.trophic_calculator = SimpleNamespace(
        get_attribute_limits=lambda trophic_level: (
            calls.append(trophic_level) or _limits()
        )
    )

    assert service._validate_trait_changes(
        {"speed": 2.0},
        {"speed": 3.0},
        3.5,
    ) == (True, "验证通过")
    assert calls == [3.5]


class _TradeoffCalculator:
    def __init__(self, penalties=None, *, error=None) -> None:
        self.penalties = penalties
        self.error = error
        self.calls = []

    def calculate_penalties(self, gains, current_traits):
        self.calls.append((gains, current_traits))
        if self.error is not None:
            raise self.error
        return self.penalties


def test_tradeoff_penalties_preserve_fast_return_identity() -> None:
    empty = {}
    changes = {"speed": 1.0}
    non_gains = {"speed": 0.0, "armor": -1.0}
    calculator = _TradeoffCalculator({"armor": -0.5})

    assert apply_tradeoff_penalties(empty, {}, calculator) is empty
    assert apply_tradeoff_penalties(changes, {}, None) is changes
    assert apply_tradeoff_penalties(non_gains, {}, calculator) is non_gains
    assert calculator.calls == []


def test_tradeoff_penalties_pass_only_positive_gains_and_current_traits() -> None:
    calculator = _TradeoffCalculator({})
    changes = {"speed": 2.0, "armor": -1.0, "social": 0.0}
    current = {"speed": 5.0}

    assert apply_tradeoff_penalties(changes, current, calculator) is changes
    assert calculator.calls == [({"speed": 2.0}, current)]


def test_tradeoff_penalties_use_empty_traits_and_fall_back_on_error() -> None:
    error = RuntimeError("calculator failed")
    calculator = _TradeoffCalculator(error=error)
    changes = {"speed": 2.0}

    assert apply_tradeoff_penalties(changes, None, calculator) is changes
    assert calculator.calls == [({"speed": 2.0}, {})]


def test_tradeoff_penalties_merge_existing_and_new_trait_deltas() -> None:
    calculator = _TradeoffCalculator({"speed": -0.5, "armor": -1.25})
    changes = {"speed": 2.0, "social": -0.2}

    result = apply_tradeoff_penalties(
        changes,
        {"speed": 5.0},
        calculator,
    )

    assert result == {"speed": 1.5, "social": -0.2, "armor": -1.25}
    assert result is not changes
    assert changes == {"speed": 2.0, "social": -0.2}


def test_service_tradeoff_penalty_delegate_uses_current_calculator() -> None:
    calculator = _TradeoffCalculator({"armor": -0.5})
    service = object.__new__(SpeciationService)
    service.tradeoff_calculator = calculator

    assert service._apply_tradeoff_penalties(
        {"speed": 1.0},
        {"speed": 4.0},
    ) == {"speed": 1.0, "armor": -0.5}


def test_trait_clamp_caps_specialized_values_and_rounds() -> None:
    result = clamp_traits_to_limit(
        {"speed": 12.345, "armor": 1.236},
        {"speed": 10.0, "armor": 1.0},
        2.0,
        lambda level: _limits(specialized=10.0, base=20.0),
    )

    assert result == {"speed": 10.0, "armor": 1.24}


def test_trait_clamp_reduces_increases_proportionally_to_parent_plus_five() -> None:
    result = clamp_traits_to_limit(
        {"speed": 10.0, "armor": 10.0},
        {"speed": 5.0, "armor": 5.0},
        2.0,
        lambda level: _limits(),
    )

    assert result == {"speed": 7.5, "armor": 7.5}


def test_trait_clamp_globally_scales_when_no_increase_can_absorb_excess() -> None:
    result = clamp_traits_to_limit(
        {"speed": 10.0, "armor": 10.0},
        {"speed": 10.0, "armor": 10.0},
        2.0,
        lambda level: _limits(total=10.0),
    )

    assert result == {"speed": 5.0, "armor": 5.0}


def test_trait_clamp_keeps_first_two_specializations_on_stable_tie() -> None:
    traits = {"speed": 8.0, "armor": 8.0, "social": 8.0}

    assert clamp_traits_to_limit(
        traits,
        traits,
        2.0,
        lambda level: _limits(base=5.0),
    ) == {"speed": 8.0, "armor": 8.0, "social": 5.0}


def test_service_trait_clamp_delegate_uses_bound_limit_calculator() -> None:
    calls = []
    service = object.__new__(SpeciationService)
    service.trophic_calculator = SimpleNamespace(
        get_attribute_limits=lambda level: calls.append(level) or _limits()
    )

    assert service._clamp_traits_to_limit(
        {"speed": 3.0},
        {"speed": 2.0},
        4.0,
    ) == {"speed": 3.0}
    assert calls == [4.0]


def test_enforced_tradeoffs_preserve_empty_and_sufficient_decrease_identity() -> None:
    empty = {}
    sufficient = {"speed": 10.0, "social": -3.0}

    assert enforce_trait_tradeoffs({}, empty, "A1a") is empty
    assert enforce_trait_tradeoffs(
        {"armor": 10.0},
        sufficient,
        "A1a",
    ) is sufficient


def test_enforced_tradeoffs_reduce_gains_when_no_candidate_exists() -> None:
    assert enforce_trait_tradeoffs(
        {"speed": 5.0},
        {"speed": 4.0},
        "A1a",
    ) == {"speed": 2.4}


def test_enforced_tradeoffs_are_exactly_deterministic_by_lineage() -> None:
    current = {"armor": 10.0, "social": 8.0, "speed": 5.0}
    proposed = {"speed": 4.0}

    assert enforce_trait_tradeoffs(current, proposed, "A1a") == {
        "speed": 4.0,
        "social": -1.42,
        "armor": -0.11,
    }
    assert enforce_trait_tradeoffs(current, proposed, "A1b") == {
        "speed": 4.0,
        "armor": -1.2,
        "social": -0.23,
    }
    assert proposed == {"speed": 4.0}


def test_service_enforced_tradeoffs_delegate_matches_direct_function() -> None:
    service = object.__new__(SpeciationService)
    current = {"armor": 10.0, "social": 8.0, "speed": 5.0}
    proposed = {"speed": 4.0}

    assert service._enforce_trait_tradeoffs(
        current,
        proposed,
        "A1a",
    ) == enforce_trait_tradeoffs(current, proposed, "A1a")


def test_differentiation_noise_preserves_empty_input_identity() -> None:
    changes = {}

    assert add_differentiation_noise(changes, "A1a") is changes


def test_differentiation_noise_is_exactly_deterministic_by_lineage() -> None:
    changes = {"speed": 1.0, "armor": 2.0}

    assert add_differentiation_noise(changes, "A1a") == {
        "speed": 1.16,
        "armor": 2.12,
        "耐寒性": 0.43,
        "耐热性": 0.9,
        "运动能力": 0.0,
        "繁殖速度": -0.32,
    }
    assert add_differentiation_noise(changes, "A1b") == {
        "speed": 1.08,
        "armor": 1.77,
        "运动能力": 0.79,
        "攻击性": 0.43,
        "耐寒性": -0.41,
        "社会性": -0.43,
    }
    assert changes == {"speed": 1.0, "armor": 2.0}


def test_differentiation_noise_uses_a_pattern_for_empty_lineage() -> None:
    assert add_differentiation_noise(
        {"speed": 1.0, "armor": 2.0},
        "",
    ) == {
        "speed": 0.71,
        "armor": 2.25,
        "耐寒性": 0.28,
        "耐热性": 0.75,
        "运动能力": -0.57,
        "繁殖速度": -0.25,
    }


def test_service_differentiation_noise_delegate_matches_direct_function() -> None:
    service = object.__new__(SpeciationService)
    changes = {"speed": 1.0, "armor": 2.0}

    assert service._add_differentiation_noise(
        changes,
        "A1a",
    ) == add_differentiation_noise(changes, "A1a")
