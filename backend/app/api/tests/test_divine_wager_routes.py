"""Wager route contracts for the split divine API router."""

from types import SimpleNamespace
from unittest.mock import create_autospec

import pytest
from fastapi.testclient import TestClient

from ...main import app
from ...services.system import divine_energy as energy_module
from ...services.system import divine_progression as progression_module
from ...services.system.divine_energy import DivineEnergyService
from ...services.system.divine_progression import (
    WAGER_TYPES,
    DivineProgressionService,
    WagerType,
)


@pytest.fixture
def wager_services(monkeypatch: pytest.MonkeyPatch):
    progression = create_autospec(DivineProgressionService, instance=True)
    energy = DivineEnergyService()
    energy.set_energy(current=100, maximum=200)
    monkeypatch.setattr(progression_module, "divine_progression_service", progression)
    monkeypatch.setattr(energy_module, "energy_service", energy)
    return progression, energy


@pytest.fixture
def client(mock_container, mock_session):
    app.state.container = mock_container
    app.state.session = mock_session
    test_client = TestClient(app, raise_server_exceptions=False)
    try:
        yield test_client
    finally:
        if hasattr(app.state, "container"):
            del app.state.container
        if hasattr(app.state, "session"):
            del app.state.session


def _wager_summary() -> dict:
    return {
        "active_wagers": [],
        "total_bet": 20,
        "total_won": 0,
        "total_lost": 0,
        "net_profit": 0,
        "consecutive_wins": 0,
        "consecutive_losses": 0,
        "faith_shaken_turns": 0,
        "wager_types": [],
    }


def _species(code: str, name: str) -> SimpleNamespace:
    return SimpleNamespace(
        lineage_code=code,
        common_name=name,
        status="alive",
        trophic_level=2,
        morphology_stats={"population": 1_000},
        abstract_traits={"适应性": 8},
        regions=["temperate_forest"],
        parent_code=None,
        born_turn=0,
    )


def test_place_wager_accepts_the_active_frontend_contract(
    client: TestClient,
    mock_container,
    wager_services,
) -> None:
    progression, energy = wager_services
    target = _species("sp-alpha", "Alpha")
    opponent = _species("sp-beta", "Beta")
    mock_container.species_repository.get_by_lineage.side_effect = {
        "sp-alpha": target,
        "sp-beta": opponent,
    }.get
    mock_container.simulation_engine.turn_counter = 12
    progression.place_wager.return_value = (
        True,
        "已下注「物种对决」，押注 20 能量",
        "wager_12_0",
    )
    progression.get_wager_summary.return_value = _wager_summary()

    response = client.post(
        "/api/divine/wager/place",
        json={
            "wager_type": "duel",
            "target_species": "sp-alpha",
            "bet_amount": 20,
            "secondary_species": "sp-beta",
            "predicted_outcome": "sp-alpha",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "已下注「物种对决」，押注 20 能量",
        "wager_id": "wager_12_0",
        "wager_type": WAGER_TYPES[WagerType.DUEL].name,
        "potential_return": int(20 * WAGER_TYPES[WagerType.DUEL].multiplier),
        "energy_bet": 20,
        "energy_remaining": 80,
    }
    call = progression.place_wager.call_args
    assert call.kwargs["wager_type"] is WagerType.DUEL
    assert call.kwargs["target_species"] == "sp-alpha"
    assert call.kwargs["bet_amount"] == 20
    assert call.kwargs["current_turn"] == 12
    assert call.kwargs["secondary_species"] == "sp-beta"
    assert call.kwargs["predicted_outcome"] == "sp-alpha"
    assert call.kwargs["initial_state"]["population"] == 1_000
    assert energy.get_state().current == 80


def test_check_wager_returns_the_resolved_frontend_contract(
    client: TestClient,
    mock_container,
    wager_services,
) -> None:
    progression, energy = wager_services
    wager = SimpleNamespace(
        id="wager_5_0",
        wager_type=WagerType.EXTINCTION,
        target_species="sp-alpha",
        secondary_species=None,
        predicted_outcome="",
        bet_amount=20,
        start_turn=5,
        end_turn=8,
        initial_state={"population": 1_000},
    )
    progression.get_state.return_value = SimpleNamespace(
        wager_state=SimpleNamespace(active_wagers={"wager_5_0": wager}),
    )
    progression.resolve_wager.return_value = 40
    progression.get_wager_summary.return_value = _wager_summary()
    mock_container.simulation_engine.turn_counter = 8
    mock_container.species_repository.get_by_lineage.return_value = None

    response = client.post(
        "/api/divine/wager/check",
        json={"wager_id": "wager_5_0"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "resolved",
        "success": True,
        "reason": "物种已灭绝",
        "reward": 40,
        "current_energy": 140,
        "wager_summary": _wager_summary(),
    }
    progression.resolve_wager.assert_called_once_with("wager_5_0", True)
    assert energy.get_state().current == 140
