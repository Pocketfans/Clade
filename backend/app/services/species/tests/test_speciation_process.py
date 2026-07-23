from types import SimpleNamespace

import pytest

from .. import speciation_process as speciation_process_module
from ..speciation_process import (
    build_offspring_ai_entry,
    apply_candidate_speciation_roll,
    append_offspring_plan_entries,
    calculate_candidate_speciation_chance,
    collect_candidate_entries,
    enhance_rule_fallback_descriptions,
    evaluate_candidate_eligibility,
    evaluate_environmental_pressure,
    execute_active_ai_batches,
    generate_background_results,
    materialize_active_result,
    materialize_active_results,
    materialize_background_result,
    materialize_background_results,
    normalize_candidate_state,
    plan_candidate_offspring,
    partition_speciation_entries,
    prepare_active_result,
)


def _entry(name: str, *, background: bool | None = None) -> dict:
    parent = SimpleNamespace(name=name)
    if background is not None:
        parent.is_background = background
    return {"name": name, "ctx": {"parent": parent}}


def test_entry_partition_preserves_flags_identity_order_and_inputs() -> None:
    background_one = _entry("background-one", background=True)
    active_one = _entry("active-one", background=False)
    missing_flag = _entry("missing-flag")
    background_two = _entry("background-two", background=True)
    deferred_one = _entry("deferred-one")
    deferred_two = _entry("deferred-two")
    entries = [
        background_one,
        active_one,
        missing_flag,
        background_two,
    ]
    deferred = [deferred_one, deferred_two]
    original_entries = list(entries)
    original_deferred = list(deferred)

    background, active, remaining = partition_speciation_entries(
        entries,
        deferred,
        max_deferred_requests=10,
        max_speciation_per_turn=3,
    )

    assert background == [background_one, background_two]
    assert active == [deferred_one, deferred_two, active_one]
    assert remaining == [missing_flag]
    assert background[0] is background_one
    assert active[0] is deferred_one
    assert remaining[0] is missing_flag
    assert entries == original_entries
    assert deferred == original_deferred
    assert active is not deferred
    assert remaining is not deferred


def test_entry_partition_truncates_pending_before_per_turn_slice() -> None:
    background = _entry("background", background=True)
    deferred_one = _entry("deferred-one")
    deferred_two = _entry("deferred-two")
    active_one = _entry("active-one")
    active_two = _entry("active-two")

    background_entries, active, remaining = partition_speciation_entries(
        [background, active_one, active_two],
        [deferred_one, deferred_two],
        max_deferred_requests=3,
        max_speciation_per_turn=1,
    )

    assert background_entries == [background]
    assert active == [deferred_one]
    assert remaining == [deferred_two, active_one]
    assert active_two not in active
    assert active_two not in remaining


def test_entry_partition_preserves_zero_limits_and_background_entries() -> None:
    background = _entry("background", background=True)

    assert partition_speciation_entries(
        [background, _entry("active")],
        [_entry("deferred")],
        max_deferred_requests=0,
        max_speciation_per_turn=0,
    ) == ([background], [], [])


def test_entry_partition_preserves_empty_lists() -> None:
    assert partition_speciation_entries(
        [],
        [],
        max_deferred_requests=5,
        max_speciation_per_turn=2,
    ) == ([], [], [])


def test_background_results_preserve_pressures_order_arguments_and_identity(
) -> None:
    entries = [
        {
            "ctx": {
                "parent": SimpleNamespace(common_name="Parent A"),
                "new_code": "CHILD-A",
                "population": 101,
                "speciation_type": "type-a",
            }
        },
        {
            "ctx": {
                "parent": SimpleNamespace(common_name="Parent B"),
                "new_code": "CHILD-B",
                "population": 202,
                "speciation_type": "type-b",
            }
        },
    ]
    pressures = [
        SimpleNamespace(category="temperature", intensity=0.2),
        SimpleNamespace(category="ignored-no-intensity"),
        SimpleNamespace(intensity=9.9),
        SimpleNamespace(category="temperature", intensity=0.8),
        SimpleNamespace(category="humidity", intensity=0.4),
    ]
    calls: list[dict] = []
    contents = [
        {"common_name": "Child A", "_evolution_direction": "direction-a"},
        {"common_name": "Child B"},
    ]

    def fallback(**kwargs):
        calls.append(kwargs)
        return contents[len(calls) - 1]

    results = generate_background_results(
        entries,
        pressures,
        average_pressure=3.5,
        turn_index=12,
        generate_rule_based_fallback=fallback,
    )

    assert results == [
        (entries[0], contents[0]),
        (entries[1], contents[1]),
    ]
    assert results[0][0] is entries[0]
    assert results[0][1] is contents[0]
    assert [call["new_code"] for call in calls] == ["CHILD-A", "CHILD-B"]
    assert calls[0] == {
        "parent": entries[0]["ctx"]["parent"],
        "new_code": "CHILD-A",
        "survivors": 101,
        "speciation_type": "type-a",
        "average_pressure": 3.5,
        "environment_pressure": {
            "temperature": 0.8,
            "humidity": 0.4,
        },
        "turn_index": 12,
    }
    assert calls[1]["parent"] is entries[1]["ctx"]["parent"]
    assert (
        calls[0]["environment_pressure"]
        is calls[1]["environment_pressure"]
    )


def test_background_results_preserve_empty_inputs() -> None:
    calls: list[dict] = []

    assert generate_background_results(
        [],
        None,
        average_pressure=0.0,
        turn_index=0,
        generate_rule_based_fallback=lambda **kwargs: calls.append(kwargs),
    ) == []
    assert calls == []


@pytest.mark.asyncio
async def test_active_ai_batches_preserve_empty_input_without_callbacks() -> None:
    def unexpected(*_args, **_kwargs):
        pytest.fail("empty active batches must not invoke dependencies")

    assert await execute_active_ai_batches(
        [],
        average_pressure=0.0,
        pressure_summary="",
        map_changes=[],
        major_events=[],
        turn_index=0,
        stream_callback=None,
        build_batch_payload=unexpected,
        call_batch_ai=unexpected,
        parse_batch_results=unexpected,
        staggered_gather=unexpected,
    ) == []


@pytest.mark.asyncio
async def test_active_ai_batches_preserve_stable_batches_and_arguments() -> None:
    entries = [{"name": f"entry-{idx}"} for idx in range(5)]
    callback = lambda *_args: None
    calls: list[tuple] = []
    gather_kwargs: dict = {}

    def build_payload(
        batch_entries,
        average_pressure,
        pressure_summary,
        map_changes,
        major_events,
        turn_index,
    ):
        calls.append(("build", batch_entries))
        assert average_pressure == 2.5
        assert pressure_summary == "pressure"
        assert map_changes == ["map"]
        assert major_events == ["event"]
        assert turn_index == 9
        return {"batch": batch_entries}

    async def call_batch(payload, stream_callback, batch_entries):
        calls.append(("call", batch_entries))
        assert payload == {"batch": batch_entries}
        assert stream_callback is callback
        return {"raw": batch_entries}

    def parse_batch(raw, batch_entries):
        calls.append(("parse", batch_entries))
        assert raw == {"raw": batch_entries}
        return [f"parsed-{entry['name']}" for entry in batch_entries]

    async def gather(coroutines, **kwargs):
        gather_kwargs.update(kwargs)
        return [await coroutine for coroutine in coroutines]

    results = await execute_active_ai_batches(
        entries,
        average_pressure=2.5,
        pressure_summary="pressure",
        map_changes=["map"],
        major_events=["event"],
        turn_index=9,
        stream_callback=callback,
        build_batch_payload=build_payload,
        call_batch_ai=call_batch,
        parse_batch_results=parse_batch,
        staggered_gather=gather,
    )

    batches = [
        entries[0:2],
        entries[2:4],
        entries[4:5],
    ]
    assert calls == [
        ("build", batches[0]),
        ("call", batches[0]),
        ("parse", batches[0]),
        ("build", batches[1]),
        ("call", batches[1]),
        ("parse", batches[1]),
        ("build", batches[2]),
        ("call", batches[2]),
        ("parse", batches[2]),
    ]
    assert gather_kwargs == {
        "interval": 1.5,
        "max_concurrent": 20,
        "task_name": "分化批次",
        "event_callback": callback,
    }
    assert results == [f"parsed-entry-{idx}" for idx in range(5)]


@pytest.mark.asyncio
async def test_active_ai_batches_repeat_batch_exception_per_entry() -> None:
    entries = [{"name": f"entry-{idx}"} for idx in range(5)]
    batch_error = RuntimeError("first batch failed")

    def build_payload(batch_entries, *_args):
        return {"batch": batch_entries}

    async def call_batch(payload, _stream_callback, _batch_entries):
        if payload["batch"][0] is entries[0]:
            raise batch_error
        return payload

    def parse_batch(payload, batch_entries):
        return [entry["name"] for entry in batch_entries]

    async def gather(coroutines, **_kwargs):
        gathered = []
        for coroutine in coroutines:
            try:
                gathered.append(await coroutine)
            except Exception as exc:
                gathered.append(exc)
        return gathered

    results = await execute_active_ai_batches(
        entries,
        average_pressure=1.0,
        pressure_summary="pressure",
        map_changes=[],
        major_events=[],
        turn_index=3,
        stream_callback=None,
        build_batch_payload=build_payload,
        call_batch_ai=call_batch,
        parse_batch_results=parse_batch,
        staggered_gather=gather,
    )

    assert results == [
        batch_error,
        batch_error,
        "entry-2",
        "entry-3",
        "entry-4",
    ]
    assert results[0] is batch_error
    assert results[1] is batch_error


@pytest.mark.asyncio
async def test_fallback_description_enhancement_preserves_empty_noop() -> None:
    class UnexpectedEnhancer:
        def queue_for_enhancement(self, **_kwargs):
            pytest.fail("empty fallback list must not queue work")

        async def process_queue_async(self, **_kwargs):
            pytest.fail("empty fallback list must not process work")

    pending: list[tuple] = []

    await enhance_rule_fallback_descriptions(
        pending,
        description_enhancer=UnexpectedEnhancer(),
        upsert_species=lambda _species: pytest.fail(
            "empty fallback list must not persist work"
        ),
    )

    assert pending == []


@pytest.mark.asyncio
async def test_fallback_description_enhancement_preserves_order_and_args(
) -> None:
    species_one = object()
    species_two = object()
    parent_one = object()
    parent_two = object()
    enhanced_one = object()
    enhanced_two = object()
    pending = [
        (species_one, parent_one, "type-one"),
        (species_two, parent_two, "type-two"),
    ]
    queued: list[dict] = []
    process_kwargs: dict = {}
    persisted: list[object] = []

    class Enhancer:
        def queue_for_enhancement(self, **kwargs):
            queued.append(kwargs)

        async def process_queue_async(self, **kwargs):
            process_kwargs.update(kwargs)
            return [enhanced_one, enhanced_two]

    await enhance_rule_fallback_descriptions(
        pending,
        description_enhancer=Enhancer(),
        upsert_species=persisted.append,
    )

    assert queued == [
        {
            "species": species_one,
            "parent": parent_one,
            "speciation_type": "type-one",
            "is_hybrid": False,
        },
        {
            "species": species_two,
            "parent": parent_two,
            "speciation_type": "type-two",
            "is_hybrid": False,
        },
    ]
    assert process_kwargs == {
        "max_items": 20,
        "timeout_per_item": 25.0,
    }
    assert persisted == [enhanced_one, enhanced_two]
    assert pending == []


@pytest.mark.asyncio
async def test_fallback_description_enhancement_swallows_failure_and_clears(
) -> None:
    pending = [(object(), object(), "type-one")]
    processing_error = RuntimeError("enhancement failed")

    class FailingEnhancer:
        def queue_for_enhancement(self, **_kwargs):
            return None

        async def process_queue_async(self, **_kwargs):
            raise processing_error

    await enhance_rule_fallback_descriptions(
        pending,
        description_enhancer=FailingEnhancer(),
        upsert_species=lambda _species: pytest.fail(
            "failed enhancement must not persist"
        ),
    )

    assert pending == []


def test_background_result_materialization_preserves_callbacks_and_state(
) -> None:
    parent = SimpleNamespace(common_name="Parent", lineage_code="PARENT")
    created = SimpleNamespace(
        common_name="Created",
        created_turn=8,
        genus_code="GENUS",
    )
    stored = SimpleNamespace(
        common_name="Stored",
        created_turn=8,
        genus_code="GENUS",
    )
    entry = {
        "ctx": {
            "parent": parent,
            "new_code": "CHILD",
            "population": 123,
            "speciation_type": "adaptive",
            "assigned_tiles": {4, 5},
        }
    }
    raw_content = {"common_name": "Raw"}
    validated_content = {"common_name": "Validated"}
    calls: list[tuple] = []
    queued: list[tuple] = []
    persisted: list[object] = []
    timestamp = object()
    lineage_event = object()
    branching_event = object()

    class GeneLibrary:
        def inherit_dormant_genes(self, parent_arg, child_arg, genus_arg):
            calls.append(("inherit_genes", parent_arg, child_arg, genus_arg))

    gene_library = GeneLibrary()

    class GeneOwner:
        @property
        def gene_library_service(self):
            calls.append(("get_gene_library",))
            return gene_library

    class GenusRepository:
        def get_by_code(self, code):
            calls.append(("get_genus", code))
            return "GENUS-OBJECT"

    def validate_and_fix(content, parent_arg, preprocess_result):
        calls.append(
            ("validate", content, parent_arg, preprocess_result)
        )
        return validated_content

    def create_species(**kwargs):
        calls.append(("create", kwargs))
        return created

    def upsert_species(species):
        calls.append(
            ("upsert", species, getattr(species, "is_background", None))
        )
        persisted.append(species)
        return stored

    def inherit_habitat_distribution(**kwargs):
        calls.append(("inherit_habitat", kwargs))

    def try_speciation_breakthrough(species, turn):
        calls.append(("breakthrough", species, turn))
        return "activated-gene"

    def lineage_event_factory(**kwargs):
        calls.append(("lineage_factory", kwargs))
        return lineage_event

    def log_lineage_event(event):
        calls.append(("log_event", event))

    def utcnow():
        calls.append(("utcnow",))
        return timestamp

    def branching_event_factory(**kwargs):
        calls.append(("branching_factory", kwargs))
        return branching_event

    result = materialize_background_result(
        entry,
        raw_content,
        turn_index=8,
        average_pressure=3.25,
        validate_and_fix=validate_and_fix,
        create_species=create_species,
        rule_fallback_species=queued,
        random_uniform=lambda low, high: (
            calls.append(("random", low, high)) or 0.4
        ),
        inherit_habitat_distribution=inherit_habitat_distribution,
        gene_library_service_owner=GeneOwner(),
        genus_repository=GenusRepository(),
        try_speciation_breakthrough=try_speciation_breakthrough,
        upsert_species=upsert_species,
        log_lineage_event=log_lineage_event,
        lineage_event_factory=lineage_event_factory,
        branching_event_factory=branching_event_factory,
        utcnow=utcnow,
    )

    assert result is branching_event
    assert created.is_background is True
    assert queued == [(stored, parent, "adaptive")]
    assert persisted == [created, stored, stored]
    assert [call[0] for call in calls] == [
        "validate",
        "create",
        "upsert",
        "random",
        "inherit_habitat",
        "get_gene_library",
        "get_gene_library",
        "get_genus",
        "get_gene_library",
        "inherit_genes",
        "upsert",
        "breakthrough",
        "upsert",
        "lineage_factory",
        "log_event",
        "utcnow",
        "branching_factory",
    ]
    assert calls[1][1] == {
        "parent": parent,
        "new_code": "CHILD",
        "survivors": 123,
        "turn_index": 8,
        "ai_payload": validated_content,
        "average_pressure": 3.25,
        "speciation_type": "adaptive",
    }
    assert calls[4][1] == {
        "parent": parent,
        "child": stored,
        "turn_index": 8,
        "assigned_tiles": {4, 5},
        "reproduction_bonus": 0.4,
    }
    assert calls[13][1] == {
        "lineage_code": "CHILD",
        "event_type": "speciation",
        "payload": {"parent": "PARENT", "turn": 8},
    }
    assert calls[16][1] == {
        "parent_lineage": "PARENT",
        "new_lineage": "CHILD",
        "description": "Parent在压力3.2条件下分化出CHILD（背景物种）",
        "timestamp": timestamp,
        "reason": "Parent种群在演化压力下发生生态位分化",
    }


def test_background_result_materialization_preserves_optional_noop_branches(
) -> None:
    parent = SimpleNamespace(common_name="Parent", lineage_code="PARENT")
    child = SimpleNamespace(
        common_name="Child",
        created_turn=1,
        genus_code=None,
    )
    upserts: list[object] = []
    genus_lookups: list[str] = []
    entry = {
        "ctx": {
            "parent": parent,
            "new_code": "CHILD",
            "population": 5,
            "speciation_type": "type",
        }
    }

    result = materialize_background_result(
        entry,
        {},
        turn_index=1,
        average_pressure=0.0,
        validate_and_fix=lambda content, *_args, **_kwargs: content,
        create_species=lambda **_kwargs: child,
        rule_fallback_species=[],
        random_uniform=lambda _low, _high: 0.3,
        inherit_habitat_distribution=lambda **kwargs: (
            pytest.fail("assigned_tiles must default to an empty set")
            if kwargs["assigned_tiles"] != set()
            else None
        ),
        gene_library_service_owner=SimpleNamespace(),
        genus_repository=SimpleNamespace(
            get_by_code=lambda code: genus_lookups.append(code)
        ),
        try_speciation_breakthrough=lambda _species, _turn: None,
        upsert_species=lambda species: (
            upserts.append(species) or species
        ),
        log_lineage_event=lambda _event: None,
        lineage_event_factory=lambda **kwargs: kwargs,
        branching_event_factory=lambda **kwargs: kwargs,
        utcnow=lambda: "now",
    )

    assert upserts == [child]
    assert genus_lookups == []
    assert result["timestamp"] == "now"


def test_background_results_materialization_preserves_loop_order(
    monkeypatch,
) -> None:
    first = ({"name": "entry-one"}, {"name": "content-one"})
    second = ({"name": "entry-two"}, {"name": "content-two"})
    calls: list[tuple] = []

    def materialize_one(entry, content, **kwargs):
        calls.append((entry, content, kwargs))
        return f"event-{entry['name']}"

    monkeypatch.setattr(
        speciation_process_module,
        "materialize_background_result",
        materialize_one,
    )

    marker = object()
    existing_events = ["existing-active-event"]
    result = materialize_background_results(
        [first, second],
        result_events=existing_events,
        marker=marker,
    )

    assert result is None
    assert existing_events == [
        "existing-active-event",
        "event-entry-one",
        "event-entry-two",
    ]
    assert calls == [
        (first[0], first[1], {"marker": marker}),
        (second[0], second[1], {"marker": marker}),
    ]


def test_background_results_materialization_preserves_partial_append_on_error(
    monkeypatch,
) -> None:
    first = ({"name": "entry-one"}, {"name": "content-one"})
    second = ({"name": "entry-two"}, {"name": "content-two"})
    processing_error = RuntimeError("second entry failed")

    def materialize_one(entry, _content, **_kwargs):
        if entry is second[0]:
            raise processing_error
        return "event-entry-one"

    monkeypatch.setattr(
        speciation_process_module,
        "materialize_background_result",
        materialize_one,
    )
    existing_events = ["existing-active-event"]

    with pytest.raises(RuntimeError) as exc_info:
        materialize_background_results(
            [first, second],
            result_events=existing_events,
        )

    assert exc_info.value is processing_error
    assert existing_events == [
        "existing-active-event",
        "event-entry-one",
    ]


def test_active_result_preparation_skips_stale_without_dependencies() -> None:
    entry = {"request_turn": 3, "ctx": {"new_code": "STALE"}}

    def unexpected(*_args, **_kwargs):
        pytest.fail("stale results must not invoke preparation dependencies")

    assert prepare_active_result(
        {"unused": True},
        entry,
        turn_index=4,
        average_pressure=1.0,
        environment_pressure={"heat": 2.0},
        queue_deferred_request=unexpected,
        normalize_ai_content=unexpected,
        generate_rule_based_fallback=unexpected,
    ) is None


@pytest.mark.parametrize(
    ("result", "retry_count"),
    [
        (RuntimeError("AI failed"), 0),
        ("not-a-dict", 1),
        ({"latin_name": "", "common_name": "Name"}, 0),
    ],
)
def test_active_result_preparation_defers_retryable_invalid_results(
    result,
    retry_count,
) -> None:
    entry = {
        "request_turn": 5,
        "_retry_count": retry_count,
        "ctx": {"new_code": "CHILD"},
    }
    queued: list[dict] = []

    assert prepare_active_result(
        result,
        entry,
        turn_index=5,
        average_pressure=1.0,
        environment_pressure={},
        queue_deferred_request=queued.append,
        normalize_ai_content=lambda content: content,
        generate_rule_based_fallback=lambda **_kwargs: pytest.fail(
            "retryable invalid results must not use fallback"
        ),
    ) is None
    assert queued == [entry]


def test_active_result_preparation_preserves_fallback_arguments() -> None:
    parent = object()
    entry = {
        "request_turn": 7,
        "_retry_count": 2,
        "ctx": {
            "parent": parent,
            "new_code": "CHILD",
            "population": 77,
            "speciation_type": "adaptive",
        },
    }
    fallback_content = {"fallback": True}
    normalized_content = {
        "latin_name": "Species fallback",
        "common_name": "Fallback",
        "description": "Description",
    }
    calls: list[tuple] = []

    def fallback(**kwargs):
        calls.append(("fallback", kwargs))
        return fallback_content

    def normalize(content):
        calls.append(("normalize", content))
        return normalized_content

    prepared = prepare_active_result(
        RuntimeError("AI failed"),
        entry,
        turn_index=7,
        average_pressure=2.5,
        environment_pressure={"heat": 0.8},
        queue_deferred_request=lambda _entry: pytest.fail(
            "exhausted retries must not defer"
        ),
        normalize_ai_content=normalize,
        generate_rule_based_fallback=fallback,
    )

    assert prepared == (entry["ctx"], normalized_content)
    assert calls == [
        (
            "fallback",
            {
                "parent": parent,
                "new_code": "CHILD",
                "survivors": 77,
                "speciation_type": "adaptive",
                "average_pressure": 2.5,
                "environment_pressure": {"heat": 0.8},
                "turn_index": 7,
            },
        ),
        ("normalize", fallback_content),
    ]


def test_active_result_preparation_normalizes_before_required_fields() -> None:
    entry = {
        "request_turn": 9,
        "ctx": {"new_code": "CHILD"},
    }
    normalized = {
        "latin_name": "Species normalized",
        "common_name": "Normalized",
        "description": "Description",
    }

    assert prepare_active_result(
        {"raw": True},
        entry,
        turn_index=9,
        average_pressure=0.0,
        environment_pressure={},
        queue_deferred_request=lambda _entry: pytest.fail(
            "valid normalized content must not defer"
        ),
        normalize_ai_content=lambda content: (
            normalized if content == {"raw": True} else None
        ),
        generate_rule_based_fallback=lambda **_kwargs: pytest.fail(
            "valid content must not use fallback"
        ),
    ) == (entry["ctx"], normalized)


def test_active_result_materialization_preserves_core_mutations() -> None:
    parent = SimpleNamespace(common_name="Parent", lineage_code="PARENT")
    child = SimpleNamespace(
        common_name="Child",
        created_turn=10,
        genus_code=None,
        lineage_code="CHILD",
        morphology_stats={},
    )
    ctx = {
        "parent": parent,
        "new_code": "CHILD",
        "population": 50,
        "speciation_type": "adaptive",
        "assigned_tiles": {2},
    }
    ai_content = {
        "latin_name": "Species child",
        "common_name": "Child",
        "description": "Description",
        "event_description": "AI event",
        "reason": "AI reason",
        "_is_rule_fallback": True,
    }
    counts = {"PARENT": 0}
    queued: list[tuple] = []
    upserts: list[object] = []
    calls: list[tuple] = []
    lineage_event = object()
    timestamp = object()

    class GeneLibrary:
        def inherit_dormant_genes(self, parent_arg, child_arg, genus_arg):
            calls.append(("inherit_genes", parent_arg, child_arg, genus_arg))

    class Owner:
        _tensor_state = None

        @property
        def gene_library_service(self):
            calls.append(("gene_library",))
            return GeneLibrary()

    result = materialize_active_result(
        ctx,
        ai_content,
        turn_index=10,
        average_pressure=4.0,
        validate_and_fix=lambda content, *_args, **_kwargs: content,
        create_species=lambda **kwargs: (
            calls.append(("create", kwargs)) or child
        ),
        turn_offspring_counts=counts,
        rule_fallback_species=queued,
        random_uniform=lambda low, high: (
            calls.append(("random", low, high)) or 0.35
        ),
        inherit_habitat_distribution=lambda **kwargs: calls.append(
            ("inherit_habitat", kwargs)
        ),
        update_genetic_distances=lambda *args: calls.append(
            ("genetic_distance", args)
        ),
        gene_library_service_owner=Owner(),
        genus_repository=SimpleNamespace(
            get_by_code=lambda code: pytest.fail(
                f"genus lookup not expected: {code}"
            )
        ),
        process_ai_activated_genes=lambda *_args: 0,
        process_ai_new_dormant_genes=lambda *_args: 0,
        try_speciation_breakthrough=lambda *_args: None,
        check_and_trigger_plant_milestones=lambda *_args: None,
        evaluate_new_species_viability=lambda *_args: pytest.fail(
            "tensor viability must not run without tensor state"
        ),
        upsert_species=lambda species: (
            upserts.append(species) or species
        ),
        log_lineage_event=lambda event: calls.append(("log_event", event)),
        lineage_event_factory=lambda **_kwargs: lineage_event,
        branching_event_factory=lambda **kwargs: kwargs,
        utcnow=lambda: timestamp,
    )

    assert counts == {"PARENT": 2}
    assert queued == [(child, parent, "adaptive")]
    assert upserts == [child, child]
    assert result == {
        "parent_lineage": "PARENT",
        "new_lineage": "CHILD",
        "description": "AI event",
        "timestamp": timestamp,
        "reason": "AI reason",
    }
    assert [call[0] for call in calls] == [
        "create",
        "random",
        "inherit_habitat",
        "genetic_distance",
        "gene_library",
        "inherit_genes",
        "log_event",
    ]


def test_active_result_materialization_preserves_optional_upserts() -> None:
    parent = SimpleNamespace(common_name="Parent", lineage_code="PARENT")
    child = SimpleNamespace(
        common_name="Child",
        created_turn=11,
        genus_code="GENUS",
        lineage_code="CHILD",
        morphology_stats={},
    )
    ai_content = {
        "latin_name": "Species child",
        "common_name": "Child",
        "description": "Description",
        "genetic_discoveries": ["gene-a"],
        "activated_genes": ["active-a"],
        "new_dormant_genes": ["dormant-a"],
    }
    calls: list[str] = []
    upserts: list[object] = []
    tensor_state = SimpleNamespace(species_map={"CHILD": 1})

    class GeneLibrary:
        def record_discovery(self, **_kwargs):
            calls.append("record_discovery")

        def inherit_dormant_genes(self, *_args):
            calls.append("inherit_genes")

    class Owner:
        _tensor_state = tensor_state

        @property
        def gene_library_service(self):
            return GeneLibrary()

    materialize_active_result(
        {
            "parent": parent,
            "new_code": "CHILD",
            "population": 50,
            "speciation_type": "adaptive",
        },
        ai_content,
        turn_index=11,
        average_pressure=1.0,
        validate_and_fix=lambda content, *_args, **_kwargs: content,
        create_species=lambda **_kwargs: child,
        turn_offspring_counts={"PARENT": 0},
        rule_fallback_species=[],
        random_uniform=lambda _low, _high: 0.4,
        inherit_habitat_distribution=lambda **_kwargs: None,
        update_genetic_distances=lambda *_args: None,
        gene_library_service_owner=Owner(),
        genus_repository=SimpleNamespace(
            get_by_code=lambda code: f"genus:{code}"
        ),
        process_ai_activated_genes=lambda *_args: 1,
        process_ai_new_dormant_genes=lambda *_args: 1,
        try_speciation_breakthrough=lambda *_args: "breakthrough",
        check_and_trigger_plant_milestones=lambda *_args: {
            "milestone_name": "milestone"
        },
        evaluate_new_species_viability=lambda *args: {
            "recommendation": "extinct",
            "avg_suitability": 0.1,
            "tile_count": 1,
        },
        upsert_species=lambda species: (
            upserts.append(species) or species
        ),
        log_lineage_event=lambda _event: None,
        lineage_event_factory=lambda **kwargs: kwargs,
        branching_event_factory=lambda **kwargs: kwargs,
        utcnow=lambda: "now",
    )

    assert calls == ["record_discovery", "inherit_genes"]
    assert len(upserts) == 7
    assert child.morphology_stats["viability_risk"] == "critical"


def test_active_results_materialization_preserves_partial_append(
    monkeypatch,
) -> None:
    first = object()
    second = object()
    processing_error = RuntimeError("second materialization failed")

    monkeypatch.setattr(
        speciation_process_module,
        "prepare_active_result",
        lambda result, entry, **_kwargs: (entry, result),
    )

    def materialize_one(ctx, _content, **_kwargs):
        if ctx is second:
            raise processing_error
        return "first-event"

    monkeypatch.setattr(
        speciation_process_module,
        "materialize_active_result",
        materialize_one,
    )
    events = ["existing-event"]

    with pytest.raises(RuntimeError) as exc_info:
        materialize_active_results(
            ["first-content", "second-content", "zip-truncated"],
            [first, second],
            result_events=events,
            preparation_kwargs={"prepare": object()},
            materialization_kwargs={"materialize": object()},
        )

    assert exc_info.value is processing_error
    assert events == ["existing-event", "first-event"]


def _offspring_species() -> SimpleNamespace:
    return SimpleNamespace(
        lineage_code="PARENT",
        latin_name="Species parent",
        common_name="Parent",
        habitat_type="forest",
        description="parent traits",
        history_highlights=[
            "old event",
            "x" * 81,
            "recent event",
        ],
        trophic_level=2.5,
        diet_type=None,
        gene_diversity_radius=0.0,
        gene_stability=None,
        explored_directions=["one", "two"],
    )


def _rule_constraints() -> dict:
    return {
        "trait_budget_summary": "budget",
        "organ_constraints_summary": "organs",
        "evolution_direction": "direction",
        "direction_description": "direction-description",
        "suggested_increases": ["speed", "vision"],
        "suggested_decreases": ["size"],
        "habitat_options": ["forest", "coast"],
        "trophic_range": "2-3",
        "niche_exploration_strategy": "explore",
        "niche_exploration_description": "explore-description",
        "niche_exploration_full": "explore-full",
        "target_diet_focus": "plants",
        "target_body_size_trend": "smaller",
        "target_ecological_role": "browser",
        "competition_with_parent": "reduced",
        "era_summary": "era",
        "era_single_cap": 12,
        "era_total_cap": 80,
        "diminishing_returns_context": "diminishing",
        "breakthrough_opportunities": "breakthrough",
        "habitat_specialization_bonus": "habitat-bonus",
        "strategy_recommendation": "strategy",
        "budget_usage_percent": 0.25,
        "remaining_budget": 75,
    }


def test_offspring_ai_entry_preserves_cluster_payload_and_call_order() -> None:
    species = _offspring_species()
    assigned_tiles = {7, 8}
    cluster_environment = {"temperature": "cold"}
    candidate_data = {
        "tile_environment": {7: {"temperature": 1}},
        "cluster_environments": [cluster_environment],
    }
    pressure = SimpleNamespace(modifiers={"temperature": 3, "wind": 2})
    calls: list[tuple] = []
    naming = SimpleNamespace(
        set_seed=lambda seed: calls.append(("set_seed", seed)),
        generate_compact_hint=lambda: (
            calls.append(("generate_name",)) or "name-hint"
        ),
    )
    rules = SimpleNamespace(
        preprocess=lambda **kwargs: (
            calls.append(("preprocess", kwargs)) or _rule_constraints()
        )
    )
    organ_service = SimpleNamespace(
        build_mature_organs_context=lambda species_arg: (
            calls.append(("mature_organs", species_arg)) or "mature"
        )
    )
    organ_catalog = [
        {
            "organ_key": "vision",
            "category": "sensory",
            "default_name": "Eye",
        }
    ]

    entry = build_offspring_ai_entry(
        species=species,
        new_code="CHILD",
        population=123,
        offspring_index=0,
        num_offspring=2,
        offspring_tiles=[assigned_tiles],
        cluster_pressure_data=[
            {
                "avg_mortality": 0.6,
                "pressure_level": "高压",
                "population": 321,
            }
        ],
        clusters=[{7, 8}, {9}],
        tile_populations={7: 100},
        tile_mortality={7: 0.7},
        mortality_gradient=0.4,
        is_isolated=True,
        death_rate=0.2,
        candidate_data=candidate_data,
        average_pressure=3.5,
        pressure_summary="pressure",
        generations=4.9,
        speciation_type="地理隔离",
        map_changes=["map"],
        major_events=["event"],
        food_chain_summary="food-chain",
        current_pressures=[pressure],
        current_pressure_types=["heat"],
        organ_catalog=organ_catalog,
        turn_index=12,
        infer_biological_domain=lambda value: (
            calls.append(("domain", value)) or "animal"
        ),
        generate_tile_context=lambda *args, **kwargs: (
            calls.append(("tile_context", args, kwargs)) or "tile-context"
        ),
        rules=rules,
        naming_hint_generator=naming,
        summarize_organs=lambda value: (
            calls.append(("organs", value)) or "organ-summary"
        ),
        summarize_map_changes=lambda value: "map-summary",
        summarize_major_events=lambda value: "event-summary",
        summarize_prey_species=lambda value: "prey-summary",
        summarize_dormant_genes=lambda *args, **kwargs: (
            calls.append(("dormant", args, kwargs)) or "dormant-summary"
        ),
        organ_evolution_service=organ_service,
    )

    payload = entry["payload"]
    assert entry["ctx"] == {
        "parent": species,
        "new_code": "CHILD",
        "population": 123,
        "ai_payload_input": payload,
        "speciation_type": "地理隔离",
        "assigned_tiles": assigned_tiles,
        "average_pressure": 3.5,
    }
    assert entry["request_turn"] == 12
    assert payload == {
        "parent_lineage": "PARENT",
        "latin_name": "Species parent",
        "common_name": "Parent",
        "habitat_type": "forest",
        "biological_domain": "animal",
        "current_organs_summary": "organ-summary",
        "environment_pressure": 3.5,
        "pressure_summary": "pressure",
        "evolutionary_generations": 4,
        "traits": "parent traits",
        "history_highlights": ("x" * 80) + "...; recent event",
        "survivors": 123,
        "speciation_type": "地理隔离",
        "map_changes_summary": "map-summary",
        "major_events_summary": "event-summary",
        "parent_trophic_level": 2.5,
        "offspring_index": 1,
        "total_offspring": 2,
        "food_chain_status": "food-chain",
        "tile_context": "tile-context",
        "region_mortality": 0.6,
        "region_pressure_level": "高压",
        "mortality_gradient": 0.4,
        "num_isolation_regions": 2,
        "is_geographic_isolation": True,
        "trait_budget_summary": "budget",
        "organ_constraints_summary": "organs",
        "evolution_direction": "direction",
        "direction_description": "direction-description",
        "suggested_increases": "speed, vision",
        "suggested_decreases": "size",
        "habitat_options": "forest, coast",
        "trophic_range": "2-3",
        "niche_exploration_strategy": "explore",
        "niche_exploration_description": "explore-description",
        "niche_exploration_full": "explore-full",
        "target_diet_focus": "plants",
        "target_body_size_trend": "smaller",
        "target_ecological_role": "browser",
        "competition_with_parent": "reduced",
        "era_summary": "era",
        "era_single_cap": 12,
        "era_total_cap": 80,
        "diminishing_returns_context": "diminishing",
        "breakthrough_opportunities": "breakthrough",
        "habitat_specialization_bonus": "habitat-bonus",
        "strategy_recommendation": "strategy",
        "budget_usage_percent": 0.25,
        "remaining_budget": 75,
        "diet_type": "omnivore",
        "prey_species_summary": "prey-summary",
        "gene_diversity_radius": 0.35,
        "gene_stability": 0.5,
        "explored_directions": 2,
        "dormant_genes_summary": "dormant-summary",
        "organ_key_catalog": "- vision (sensory)：Eye",
        "mature_organs_context": "mature",
        "naming_hints": "name-hint",
    }
    expected_seed = (
        abs(hash("CHILD-PARENT-0")) % 1_000_000_007
    )
    assert [call[0] for call in calls] == [
        "domain",
        "tile_context",
        "preprocess",
        "set_seed",
        "generate_name",
        "organs",
        "dormant",
        "mature_organs",
    ]
    assert calls[2][1]["environment_pressure"] == {
        "temperature": 3,
        "humidity": 0,
        "salinity": 0,
        "wind": 2,
    }
    assert calls[3] == ("set_seed", expected_seed)
    assert calls[6][2] == {
        "pressure_types": ["heat"],
        "pressure_strength": 3.5,
    }


def test_offspring_ai_entry_preserves_fallback_region_defaults() -> None:
    species = _offspring_species()
    constraints = _rule_constraints()

    entry = build_offspring_ai_entry(
        species=species,
        new_code="CHILD",
        population=10,
        offspring_index=0,
        num_offspring=1,
        offspring_tiles=[{1, 2}],
        cluster_pressure_data=[],
        clusters=[],
        tile_populations={},
        tile_mortality={1: 0.2, 2: 0.6},
        mortality_gradient=0.0,
        is_isolated=True,
        death_rate=0.9,
        candidate_data=None,
        average_pressure=0.0,
        pressure_summary="",
        generations=1,
        speciation_type="adaptive",
        map_changes=[],
        major_events=[],
        food_chain_summary="",
        current_pressures=[],
        current_pressure_types=[],
        organ_catalog=[],
        turn_index=1,
        infer_biological_domain=lambda _species: "animal",
        generate_tile_context=lambda *_args, **_kwargs: "tiles",
        rules=SimpleNamespace(preprocess=lambda **_kwargs: constraints),
        naming_hint_generator=SimpleNamespace(
            set_seed=lambda _seed: None,
            generate_compact_hint=lambda: "hint",
        ),
        summarize_organs=lambda _species: "",
        summarize_map_changes=lambda _changes: pytest.fail(
            "empty map changes must not be summarized"
        ),
        summarize_major_events=lambda _events: pytest.fail(
            "empty events must not be summarized"
        ),
        summarize_prey_species=lambda _species: "",
        summarize_dormant_genes=lambda *_args, **_kwargs: "",
        organ_evolution_service=SimpleNamespace(
            build_mature_organs_context=lambda _species: ""
        ),
    )

    assert entry["ctx"]["assigned_tiles"] == {1, 2}
    assert entry["payload"]["region_mortality"] == pytest.approx(0.4)
    assert entry["payload"]["region_pressure_level"] == "中压"
    assert entry["payload"]["num_isolation_regions"] == 1
    assert entry["payload"]["is_geographic_isolation"] is False
    assert entry["payload"]["map_changes_summary"] == ""
    assert entry["payload"]["major_events_summary"] == ""


def test_candidate_state_normalization_preserves_prescreened_state() -> None:
    species = SimpleNamespace(
        common_name="Parent",
        morphology_stats={"population": 100},
    )
    candidate_tiles = {1, 2, 3}
    tile_populations = {1: 80, 2: 70, 3: 10}
    tile_mortality = {1: 0.2, 2: 0.6, 3: 0.9}
    original_clusters = [{1}, {2}, {3}]
    candidate_data = {
        "candidate_tiles": candidate_tiles,
        "tile_populations": tile_populations,
        "tile_mortality": tile_mortality,
        "is_isolated": True,
        "mortality_gradient": 0.7,
        "clusters": original_clusters,
        "total_candidate_population": 200,
    }
    threshold_calls: list[tuple] = []

    work = normalize_candidate_state(
        species=species,
        lineage_code="PARENT",
        global_population=100,
        result_death_rate=0.5,
        turn_index=4,
        spec_config=SimpleNamespace(
            candidate_tile_min_pop=1,
            candidate_tile_death_rate_min=0.0,
            candidate_tile_death_rate_max=1.0,
        ),
        speciation_candidates={"PARENT": candidate_data},
        tile_population_cache={},
        tile_mortality_cache={},
        calculate_speciation_threshold=lambda species_arg, turn: (
            threshold_calls.append((species_arg, turn)) or 100
        ),
    )

    assert work.candidate_data is candidate_data
    assert work.candidate_tiles is candidate_tiles
    assert work.tile_populations is tile_populations
    assert work.tile_mortality is tile_mortality
    assert work.global_population == 160
    assert species.morphology_stats["population"] == 160
    assert work.candidate_population == 160
    assert work.death_rate == pytest.approx(
        (0.2 * 80 + 0.6 * 70 + 0.9 * 10) / 160
    )
    assert work.is_isolated is True
    assert work.mortality_gradient == 0.7
    assert work.clusters == [{1}, {2}]
    assert work.clusters is not original_clusters
    assert threshold_calls == [(species, 4)]


def test_candidate_state_normalization_downgrades_empty_valid_clusters(
) -> None:
    species = SimpleNamespace(
        common_name="Parent",
        morphology_stats={"population": 80},
    )
    clusters = [{1}, {2}]
    candidate_data = {
        "candidate_tiles": {1, 2},
        "tile_populations": {1: 40, 2: 40},
        "tile_mortality": {1: 0.2, 2: 0.3},
        "is_isolated": True,
        "mortality_gradient": 0.1,
        "clusters": clusters,
        "total_candidate_population": 80,
    }

    work = normalize_candidate_state(
        species=species,
        lineage_code="PARENT",
        global_population=80,
        result_death_rate=0.5,
        turn_index=2,
        spec_config=SimpleNamespace(
            candidate_tile_min_pop=1,
            candidate_tile_death_rate_min=0.0,
            candidate_tile_death_rate_max=1.0,
        ),
        speciation_candidates={"PARENT": candidate_data},
        tile_population_cache={},
        tile_mortality_cache={},
        calculate_speciation_threshold=lambda _species, _turn: 100,
    )

    assert work.is_isolated is False
    assert work.clusters is clusters


def test_candidate_state_normalization_preserves_cache_fallback_filters(
) -> None:
    species = SimpleNamespace(
        common_name="Parent",
        morphology_stats={"population": 100},
    )
    tile_populations = {1: 50, 2: 30, 3: 5}
    tile_mortality = {1: 0.2, 2: 0.8, 3: 0.4}

    work = normalize_candidate_state(
        species=species,
        lineage_code="PARENT",
        global_population=100,
        result_death_rate=0.33,
        turn_index=3,
        spec_config=SimpleNamespace(
            candidate_tile_min_pop=10,
            candidate_tile_death_rate_min=0.1,
            candidate_tile_death_rate_max=0.7,
        ),
        speciation_candidates={},
        tile_population_cache={"PARENT": tile_populations},
        tile_mortality_cache={"PARENT": tile_mortality},
        calculate_speciation_threshold=lambda *_args: pytest.fail(
            "fallback path must not calculate cluster threshold"
        ),
    )

    assert work.candidate_data is None
    assert work.candidate_tiles == {1}
    assert work.tile_populations is tile_populations
    assert work.tile_mortality is tile_mortality
    assert work.global_population == 85
    assert species.morphology_stats["population"] == 85
    assert work.candidate_population == 50
    assert work.death_rate == 0.33
    assert work.is_isolated is False
    assert work.mortality_gradient == 0.0
    assert work.clusters == []


def _candidate_work(
    *,
    candidate_data: dict | None = None,
    candidate_population: int = 500,
    death_rate: float = 0.2,
    is_isolated: bool = False,
) -> speciation_process_module._CandidateWork:
    return speciation_process_module._CandidateWork(
        candidate_data=candidate_data,
        candidate_tiles=set(),
        tile_populations={},
        tile_mortality={},
        global_population=candidate_population,
        candidate_population=candidate_population,
        death_rate=death_rate,
        is_isolated=is_isolated,
        mortality_gradient=0.0,
        clusters=[],
    )


def _candidate_config(**overrides) -> SimpleNamespace:
    values = {
        "cooldown_turns": 10,
        "early_skip_cooldown_turns": 10,
        "pressure_threshold_early": 0.5,
        "resource_threshold_early": 0.5,
        "evo_potential_threshold_early": 0.8,
        "pressure_threshold_late": 0.7,
        "resource_threshold_late": 0.7,
        "evo_potential_threshold_late": 0.9,
        "radiation_base_chance": 0.15,
        "radiation_pop_ratio_early": 0.8,
        "radiation_pop_ratio_late": 1.2,
        "radiation_early_bonus": 0.25,
        "radiation_max_chance_early": 0.6,
        "radiation_max_chance_late": 0.4,
        "no_isolation_penalty_early": 0.95,
        "no_isolation_penalty_late": 0.8,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _candidate_species(
    *,
    evolution_potential: float = 0.5,
    speciation_pressure: float = 0.0,
    last_speciation_turn: int = -999,
) -> SimpleNamespace:
    return SimpleNamespace(
        common_name="Parent",
        hidden_traits={"evolution_potential": evolution_potential},
        morphology_stats={
            "speciation_pressure": speciation_pressure,
            "last_speciation_turn": last_speciation_turn,
            "milestone_progress": 0.25,
        },
    )


def _eligibility_result(
    *,
    resource_pressure: float = 0.2,
    niche_overlap: float = 0.3,
    niche_saturation: float = 0.4,
) -> SimpleNamespace:
    return SimpleNamespace(
        resource_pressure=resource_pressure,
        niche_overlap=niche_overlap,
        niche_saturation=niche_saturation,
    )


def test_candidate_eligibility_preserves_threshold_values_and_early_bypass(
) -> None:
    species = _candidate_species(last_speciation_turn=4)
    work = evaluate_candidate_eligibility(
        _candidate_work(
            candidate_population=500,
            is_isolated=True,
        ),
        species=species,
        result=_eligibility_result(
            resource_pressure=0.6,
            niche_overlap=0.8,
            niche_saturation=0.9,
        ),
        turn_index=5,
        average_pressure=0.7,
        spec_config=_candidate_config(),
        calculate_speciation_threshold=lambda species_arg, turn: (
            100
            if (species_arg, turn) == (species, 5)
            else pytest.fail("threshold inputs changed")
        ),
    )

    assert work is not None
    assert work.survivors == 500
    assert work.resource_pressure == 0.6
    assert work.niche_overlap == 0.8
    assert work.niche_saturation == 0.9
    assert work.base_threshold == 100
    assert work.min_population == int(100 * 0.7 * 0.8 * 1.1)
    assert work.evo_potential == 0.5
    assert work.speciation_pressure == 0.0


@pytest.mark.parametrize(
    ("work", "species", "turn_index"),
    [
        (
            _candidate_work(candidate_population=100),
            _candidate_species(),
            20,
        ),
        (
            _candidate_work(candidate_population=500),
            _candidate_species(last_speciation_turn=15),
            20,
        ),
        (
            _candidate_work(candidate_population=500),
            _candidate_species(evolution_potential=0.14),
            20,
        ),
    ],
    ids=["population", "cooldown", "potential"],
)
def test_candidate_eligibility_preserves_each_early_return(
    work,
    species,
    turn_index: int,
) -> None:
    assert evaluate_candidate_eligibility(
        work,
        species=species,
        result=_eligibility_result(),
        turn_index=turn_index,
        average_pressure=0.0,
        spec_config=_candidate_config(),
        calculate_speciation_threshold=lambda *_args: 100,
    ) is None


def _eligible_work(
    *,
    candidate_data: dict | None = None,
    candidate_population: int = 100,
    death_rate: float = 0.2,
    is_isolated: bool = False,
    speciation_pressure: float = 0.0,
) -> speciation_process_module._CandidateWork:
    return speciation_process_module._CandidateWork(
        candidate_data=candidate_data,
        candidate_tiles=set(),
        tile_populations={},
        tile_mortality={},
        global_population=candidate_population,
        candidate_population=candidate_population,
        death_rate=death_rate,
        is_isolated=is_isolated,
        mortality_gradient=0.0,
        clusters=[],
        survivors=candidate_population,
        resource_pressure=0.0,
        niche_overlap=0.2,
        niche_saturation=0.2,
        base_threshold=100,
        min_population=100,
        evo_potential=0.2,
        speciation_pressure=speciation_pressure,
    )


def test_environmental_pressure_isolation_skips_plant_and_random_checks(
) -> None:
    work = evaluate_environmental_pressure(
        _eligible_work(candidate_data={}, is_isolated=True),
        species=_candidate_species(),
        is_early_game=False,
        average_pressure=0.0,
        spec_config=_candidate_config(),
        is_plant=lambda _species: False,
        plant_evolution_service=SimpleNamespace(),
        random_random=lambda: pytest.fail(
            "isolated candidate must not draw radiation randomness"
        ),
    )

    assert work is not None
    assert work.speciation_pressure == 0.0


def test_environmental_pressure_preserves_plant_milestone_short_circuit(
) -> None:
    species = _candidate_species()
    milestone = SimpleNamespace(id="root", name="Root")
    calls: list[tuple] = []
    service = SimpleNamespace(
        get_next_milestone=lambda species_arg: (
            calls.append(("get", species_arg)) or milestone
        ),
        check_milestone_requirements=lambda species_arg, milestone_id: (
            calls.append(("check", species_arg, milestone_id))
            or (True, 1.0, None)
        ),
    )

    work = evaluate_environmental_pressure(
        _eligible_work(candidate_data={}),
        species=species,
        is_early_game=False,
        average_pressure=0.0,
        spec_config=_candidate_config(),
        is_plant=lambda species_arg: (
            calls.append(("is_plant", species_arg)) or True
        ),
        plant_evolution_service=service,
        random_random=lambda: pytest.fail(
            "met milestone must suppress radiation randomness"
        ),
    )

    assert work is not None
    assert work.speciation_pressure == 0.0
    assert calls == [
        ("is_plant", species),
        ("get", species),
        ("check", species, "root"),
    ]


def test_environmental_pressure_updates_readiness_before_radiation_draw(
) -> None:
    species = _candidate_species()
    milestone = SimpleNamespace(id="leaf", name="Leaf")
    calls: list[str] = []
    service = SimpleNamespace(
        get_next_milestone=lambda _species: (
            calls.append("get") or milestone
        ),
        check_milestone_requirements=lambda *_args: (
            calls.append("check") or (False, 0.9, None)
        ),
    )

    work = evaluate_environmental_pressure(
        _eligible_work(candidate_data={}, candidate_population=200),
        species=species,
        is_early_game=False,
        average_pressure=0.0,
        spec_config=_candidate_config(),
        is_plant=lambda _species: calls.append("is_plant") or True,
        plant_evolution_service=service,
        random_random=lambda: calls.append("random") or 1.0,
    )

    assert work is not None
    assert work.speciation_pressure == pytest.approx(0.09)
    assert calls == ["is_plant", "get", "check", "random"]


def test_environmental_pressure_preserves_population_random_short_circuit(
) -> None:
    work = evaluate_environmental_pressure(
        _eligible_work(candidate_data={}, candidate_population=100),
        species=_candidate_species(),
        is_early_game=False,
        average_pressure=0.0,
        spec_config=_candidate_config(),
        is_plant=lambda _species: False,
        plant_evolution_service=SimpleNamespace(),
        random_random=lambda: pytest.fail(
            "population guard must short-circuit before random draw"
        ),
    )

    assert work is not None


def test_environmental_pressure_preserves_legacy_death_rate_return_order(
) -> None:
    calls: list[str] = []
    work = evaluate_environmental_pressure(
        _eligible_work(
            candidate_data=None,
            candidate_population=200,
            death_rate=0.9,
        ),
        species=_candidate_species(),
        is_early_game=False,
        average_pressure=0.0,
        spec_config=_candidate_config(),
        is_plant=lambda _species: False,
        plant_evolution_service=SimpleNamespace(),
        random_random=lambda: calls.append("random") or 1.0,
    )

    assert work is None
    assert calls == ["random"]


def _trigger_work(
    *,
    candidate_data: dict | None = None,
    candidate_population: int = 200,
    death_rate: float = 0.2,
    is_isolated: bool = False,
    mortality_gradient: float = 0.0,
    clusters: list | None = None,
    niche_overlap: float = 0.2,
    niche_saturation: float = 0.2,
    speciation_pressure: float = 0.0,
) -> speciation_process_module._CandidateWork:
    return speciation_process_module._CandidateWork(
        candidate_data=candidate_data,
        candidate_tiles={1, 2},
        tile_populations={1: 100, 2: 100},
        tile_mortality={1: 0.2, 2: 0.2},
        global_population=candidate_population,
        candidate_population=candidate_population,
        death_rate=death_rate,
        is_isolated=is_isolated,
        mortality_gradient=mortality_gradient,
        clusters=[] if clusters is None else clusters,
        survivors=candidate_population,
        resource_pressure=0.2,
        niche_overlap=niche_overlap,
        niche_saturation=niche_saturation,
        base_threshold=100,
        min_population=100,
        evo_potential=0.2,
        speciation_pressure=speciation_pressure,
    )


def _trigger_species(
    *,
    recent_migrations: list[int] | None = None,
    is_background: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        common_name="Parent",
        lineage_code="PARENT",
        is_background=is_background,
        morphology_stats={
            "generation_time_days": 365,
            "recent_migration_turns": (
                [] if recent_migrations is None else recent_migrations
            ),
            "speciation_pressure": 0.0,
        },
    )


def test_final_chance_rejects_high_death_rate_before_channel_callbacks(
) -> None:
    assert calculate_candidate_speciation_chance(
        _trigger_work(death_rate=0.61),
        species=_trigger_species(),
        lineage_code="PARENT",
        mortality_results=[],
        turn_index=20,
        density_damping=1.0,
        average_pressure=0.0,
        map_changes=[],
        major_events=[],
        spec_config=_candidate_config(
            early_game_turns=10,
            background_speciation_penalty=0.1,
        ),
        base_speciation_rate=0.1,
        ai_speciation_candidates=set(),
        detect_geographic_isolation=lambda _code: pytest.fail(
            "high death rate must return before channel detection"
        ),
        detect_coevolution=lambda *_args: pytest.fail(
            "high death rate must return before coevolution"
        ),
    ) is None


def test_final_chance_preserves_prescreened_geographic_channel() -> None:
    clusters = [{1}, {2}]
    work = calculate_candidate_speciation_chance(
        _trigger_work(
            candidate_data={"candidate_tiles": {1, 2}},
            is_isolated=True,
            mortality_gradient=0.3,
            clusters=clusters,
        ),
        species=_trigger_species(),
        lineage_code="PARENT",
        mortality_results=[],
        turn_index=20,
        density_damping=1.0,
        average_pressure=0.0,
        map_changes=[],
        major_events=[],
        spec_config=_candidate_config(
            early_game_turns=10,
            background_speciation_penalty=0.1,
        ),
        base_speciation_rate=0.1,
        ai_speciation_candidates=set(),
        detect_geographic_isolation=lambda _code: pytest.fail(
            "prescreened candidate must not run legacy detection"
        ),
        detect_coevolution=lambda *_args: {
            "has_coevolution": False,
        },
    )

    assert work is not None
    expected_base = (
        (0.1 + 0.2 * 0.25) * 0.8
        + __import__("math").log10(500_000) * 0.02
    )
    assert work.generations == 500_000
    assert work.speciation_type == "地理隔离"
    assert work.speciation_chance == pytest.approx(
        expected_base + 0.50 + 0.10
    )
    assert work.clusters is clusters


def test_final_chance_preserves_ecological_population_rejection() -> None:
    assert calculate_candidate_speciation_chance(
        _trigger_work(
            candidate_data={"candidate_tiles": {1}},
            candidate_population=100,
            niche_overlap=0.7,
        ),
        species=_trigger_species(),
        lineage_code="PARENT",
        mortality_results=[],
        turn_index=20,
        density_damping=1.0,
        average_pressure=0.7,
        map_changes=[],
        major_events=[],
        spec_config=_candidate_config(
            early_game_turns=10,
            background_speciation_penalty=0.1,
        ),
        base_speciation_rate=0.1,
        ai_speciation_candidates=set(),
        detect_geographic_isolation=lambda _code: pytest.fail(
            "prescreened candidate must not run legacy detection"
        ),
        detect_coevolution=lambda *_args: {
            "has_coevolution": False,
        },
    ) is None


def test_final_chance_preserves_migration_ai_and_background_order() -> None:
    species = _trigger_species(
        recent_migrations=[10, 17, 18],
        is_background=True,
    )
    work = calculate_candidate_speciation_chance(
        _trigger_work(),
        species=species,
        lineage_code="PARENT",
        mortality_results=[],
        turn_index=20,
        density_damping=1.0,
        average_pressure=0.0,
        map_changes=[],
        major_events=[],
        spec_config=_candidate_config(
            early_game_turns=10,
            background_speciation_penalty=0.2,
        ),
        base_speciation_rate=0.1,
        ai_speciation_candidates={"PARENT"},
        detect_geographic_isolation=lambda _code: {
            "is_isolated": False,
        },
        detect_coevolution=lambda *_args: {
            "has_coevolution": False,
        },
    )

    assert work is not None
    base_chance = (
        (0.1 + 0.2 * 0.25) * 0.8
        + __import__("math").log10(500_000) * 0.02
    )
    assert species.morphology_stats["recent_migration_turns"] == [18]
    assert work.speciation_type == "AI辅助生态隔离"
    assert work.speciation_chance == pytest.approx(
        (base_chance * 0.5 + 0.15) * 0.2
    )


def test_final_roll_failure_accumulates_pressure_before_upsert() -> None:
    species = _trigger_species()
    work = _trigger_work(speciation_pressure=0.10)
    work = speciation_process_module.replace(
        work,
        speciation_chance=0.20,
    )
    calls: list[tuple] = []

    result = apply_candidate_speciation_roll(
        work,
        species=species,
        turn_index=20,
        random_random=lambda: calls.append(("random",)) or 0.30,
        upsert_species=lambda species_arg: calls.append(
            (
                "upsert",
                species_arg.morphology_stats["speciation_pressure"],
            )
        ),
    )

    assert result is None
    assert species.morphology_stats["speciation_pressure"] == 0.18
    assert calls == [("random",), ("upsert", 0.18)]


def test_final_roll_success_resets_pressure_and_sets_cooldown() -> None:
    species = _trigger_species()
    work = speciation_process_module.replace(
        _trigger_work(speciation_pressure=0.10),
        speciation_chance=0.20,
    )

    result = apply_candidate_speciation_roll(
        work,
        species=species,
        turn_index=20,
        random_random=lambda: 0.20,
        upsert_species=lambda _species: pytest.fail(
            "successful roll must not upsert at this boundary"
        ),
    )

    assert result is work
    assert species.morphology_stats["speciation_pressure"] == 0.0
    assert species.morphology_stats["last_speciation_turn"] == 20


def test_offspring_planner_preserves_dynamic_population_and_callback_order(
) -> None:
    species = _trigger_species()
    species.morphology_stats["population"] = 150
    work = speciation_process_module.replace(
        _trigger_work(
            candidate_data={"candidate_tiles": {1, 2}},
            candidate_population=200,
            is_isolated=True,
            mortality_gradient=0.4,
            clusters=[{1}, {2}],
        ),
        generations=500_000,
    )
    existing_codes = {"PARENT"}
    calls: list[tuple] = []

    plan = plan_candidate_offspring(
        work,
        species=species,
        mortality_results=[],
        current_species_count=5,
        existing_codes=existing_codes,
        enable_dynamic_speciation=True,
        calculate_dynamic_offspring_count=lambda *args, **kwargs: (
            calls.append(("count", args, kwargs)) or 2
        ),
        random_choice=lambda _values: pytest.fail(
            "dynamic mode must not use legacy random choice"
        ),
        random_uniform=lambda low, high: (
            calls.append(("uniform", low, high)) or 0.5
        ),
        allocate_offspring_population=lambda pool, count: (
            calls.append(("population", pool, count)) or [37, 38]
        ),
        generate_multiple_lineage_codes=lambda parent, codes, count: (
            calls.append(("codes", parent, set(codes), count))
            or ["CHILD-A", "CHILD-B"]
        ),
        allocate_tiles_from_clusters=lambda clusters, tiles, count: (
            calls.append(("cluster_tiles", clusters, tiles, count))
            or [{1}, {2}]
        ),
        allocate_tiles_to_offspring=lambda *_args: pytest.fail(
            "prescreened clusters must use cluster allocation"
        ),
        upsert_species=lambda species_arg: calls.append(
            ("upsert", species_arg.morphology_stats["population"])
        ),
    )

    assert plan is not None
    assert plan.num_offspring == 2
    assert plan.pop_splits == [37, 38]
    assert plan.new_codes == ["CHILD-A", "CHILD-B"]
    assert plan.offspring_tiles == [{1}, {2}]
    assert plan.cluster_pressure_data == [
        {
            "cluster_idx": 0,
            "tiles": {1},
            "population": 100,
            "avg_mortality": 0.2,
            "pressure_level": "低压",
        },
        {
            "cluster_idx": 1,
            "tiles": {2},
            "population": 100,
            "avg_mortality": 0.2,
            "pressure_level": "低压",
        },
    ]
    assert existing_codes == {"PARENT", "CHILD-A", "CHILD-B"}
    assert species.morphology_stats["population"] == 75
    assert [call[0] for call in calls] == [
        "count",
        "uniform",
        "population",
        "codes",
        "upsert",
        "cluster_tiles",
    ]
    assert calls[0][1] == (500_000, 150, 0.2)
    assert calls[0][2] == {
        "current_species_count": 5,
        "sibling_count": 0,
    }


def test_offspring_planner_preserves_legacy_random_order_and_early_return(
) -> None:
    species = _trigger_species()
    species.morphology_stats["population"] = 1
    calls: list[tuple] = []

    plan = plan_candidate_offspring(
        _trigger_work(candidate_population=1),
        species=species,
        mortality_results=[],
        current_species_count=1,
        existing_codes={"PARENT"},
        enable_dynamic_speciation=False,
        calculate_dynamic_offspring_count=lambda *_args, **_kwargs: (
            pytest.fail("legacy mode must not calculate dynamic count")
        ),
        random_choice=lambda values: (
            calls.append(("choice", values)) or 2
        ),
        random_uniform=lambda low, high: (
            calls.append(("uniform", low, high)) or 0.5
        ),
        allocate_offspring_population=lambda *_args: pytest.fail(
            "insufficient population must return before allocation"
        ),
        generate_multiple_lineage_codes=lambda *_args: pytest.fail(
            "insufficient population must return before code generation"
        ),
        allocate_tiles_from_clusters=lambda *_args: pytest.fail(
            "insufficient population must return before tile allocation"
        ),
        allocate_tiles_to_offspring=lambda *_args: pytest.fail(
            "insufficient population must return before tile allocation"
        ),
        upsert_species=lambda *_args: pytest.fail(
            "insufficient population must return before persistence"
        ),
    )

    assert plan is None
    assert calls == [("choice", [2, 2, 3]), ("uniform", 0.40, 0.55)]


def test_offspring_entry_append_preserves_order_and_partial_progress() -> None:
    plan = speciation_process_module._OffspringPlan(
        cluster_pressure_data=[{"cluster_idx": 0}],
        num_offspring=2,
        pop_splits=[10, 20],
        new_codes=["A", "B"],
        offspring_tiles=[{1}, {2}],
    )
    entries = [{"existing": True}]
    calls: list[dict] = []

    def build_entry(**kwargs):
        calls.append(kwargs)
        if kwargs["new_code"] == "B":
            raise RuntimeError("second entry failed")
        return {"code": kwargs["new_code"]}

    with pytest.raises(RuntimeError, match="second entry failed"):
        append_offspring_plan_entries(
            entries,
            plan,
            build_entry=build_entry,
            common_kwargs_factory=lambda: {
                "species": "parent",
                "marker": object(),
            },
        )

    assert entries == [{"existing": True}, {"code": "A"}]
    assert [call["new_code"] for call in calls] == ["A", "B"]
    assert [call["population"] for call in calls] == [10, 20]
    assert [call["offspring_index"] for call in calls] == [0, 1]
    assert all(call["num_offspring"] == 2 for call in calls)
    assert all(
        call["offspring_tiles"] is plan.offspring_tiles
        for call in calls
    )
    assert all(
        call["cluster_pressure_data"] is plan.cluster_pressure_data
        for call in calls
    )


def test_candidate_coordinator_preserves_phase_and_random_callback_order(
    monkeypatch,
) -> None:
    species = _trigger_species()
    species.morphology_stats["population"] = 500
    result = SimpleNamespace(species=species, death_rate=0.2)
    work = _trigger_work(candidate_population=500)
    plan = speciation_process_module._OffspringPlan(
        cluster_pressure_data=[],
        num_offspring=1,
        pop_splits=[100],
        new_codes=["CHILD"],
        offspring_tiles=[set()],
    )
    calls: list[tuple] = []

    def phase(name, returned):
        def run(*args, **kwargs):
            calls.append((name, args, kwargs))
            return returned

        return run

    monkeypatch.setattr(
        speciation_process_module,
        "normalize_candidate_state",
        phase("normalize", work),
    )
    monkeypatch.setattr(
        speciation_process_module,
        "evaluate_candidate_eligibility",
        phase("eligibility", work),
    )
    monkeypatch.setattr(
        speciation_process_module,
        "evaluate_environmental_pressure",
        phase("environment", work),
    )
    monkeypatch.setattr(
        speciation_process_module,
        "calculate_candidate_speciation_chance",
        phase("chance", work),
    )
    monkeypatch.setattr(
        speciation_process_module,
        "apply_candidate_speciation_roll",
        phase("roll", work),
    )
    monkeypatch.setattr(
        speciation_process_module,
        "plan_candidate_offspring",
        phase("plan", plan),
    )

    def append(entries, received_plan, **kwargs):
        calls.append(("append", (entries, received_plan), kwargs))
        entries.append({"lineage_code": "CHILD"})

    monkeypatch.setattr(
        speciation_process_module,
        "append_offspring_plan_entries",
        append,
    )

    threshold = object()
    service = SimpleNamespace(
        _speciation_candidates={},
        _tile_population_cache={},
        _tile_mortality_cache={},
        _calculate_speciation_threshold=threshold,
        _ai_speciation_candidates=set(),
        _detect_geographic_isolation=object(),
        _detect_coevolution=object(),
        _calculate_dynamic_offspring_count=object(),
        _allocate_offspring_population=object(),
        _generate_multiple_lineage_codes=object(),
        _allocate_tiles_from_clusters=object(),
        _allocate_tiles_to_offspring=object(),
    )
    random_source = SimpleNamespace(
        random=object(),
        choice=object(),
        uniform=object(),
    )
    config = SimpleNamespace(
        max_direct_offspring=3,
        count_only_alive_offspring=True,
        max_hybrids_per_parent_per_turn=2,
        min_population_for_speciation=100,
        early_game_turns=10,
    )
    settings = SimpleNamespace(
        base_speciation_rate=0.01,
        enable_dynamic_speciation=True,
    )
    repository = SimpleNamespace(upsert=object())
    is_plant = object()

    entries = collect_candidate_entries(
        service,
        [result],
        {"PARENT"},
        direct_offspring_map={},
        turn_offspring_counts={},
        spec_config=config,
        current_species_count=1,
        turn_index=5,
        is_early_game=True,
        average_pressure=2.0,
        pressure_summary="pressure",
        density_damping=1.0,
        map_changes=[],
        major_events=[],
        settings=settings,
        species_repository=repository,
        plant_evolution_service=object(),
        random_source=random_source,
        is_plant=is_plant,
    )

    assert entries == [{"lineage_code": "CHILD"}]
    assert [call[0] for call in calls] == [
        "normalize",
        "eligibility",
        "environment",
        "chance",
        "roll",
        "plan",
        "append",
    ]
    assert calls[0][2]["calculate_speciation_threshold"] is threshold
    assert calls[2][2]["is_early_game"] is True
    assert calls[2][2]["random_random"] is random_source.random
    assert calls[4][2]["random_random"] is random_source.random
    assert calls[5][2]["random_choice"] is random_source.choice
    assert calls[5][2]["random_uniform"] is random_source.uniform
    assert calls[5][2]["upsert_species"] is repository.upsert


def test_candidate_coordinator_skips_before_phases_at_direct_child_limit(
    monkeypatch,
) -> None:
    species = _trigger_species()
    child = SimpleNamespace(status="alive")
    service = SimpleNamespace()

    monkeypatch.setattr(
        speciation_process_module,
        "normalize_candidate_state",
        lambda **_kwargs: pytest.fail(
            "direct-child limit must skip before candidate phases"
        ),
    )

    entries = collect_candidate_entries(
        service,
        [SimpleNamespace(species=species, death_rate=0.2)],
        {"PARENT"},
        direct_offspring_map={"PARENT": [child]},
        turn_offspring_counts={},
        spec_config=SimpleNamespace(
            max_direct_offspring=1,
            count_only_alive_offspring=True,
            max_hybrids_per_parent_per_turn=2,
            min_population_for_speciation=100,
            early_game_turns=10,
        ),
        current_species_count=1,
        turn_index=5,
        is_early_game=True,
        average_pressure=2.0,
        pressure_summary="pressure",
        density_damping=1.0,
        map_changes=[],
        major_events=[],
        settings=SimpleNamespace(),
        species_repository=SimpleNamespace(),
        plant_evolution_service=object(),
        random_source=SimpleNamespace(),
        is_plant=object(),
    )

    assert entries == []
