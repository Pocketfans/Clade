"""Energy route contracts for the split API router."""

import pytest
from fastapi.testclient import TestClient

from ...main import app
from ...services.system import divine_energy as energy_module
from ...services.system.divine_energy import DivineEnergyService


@pytest.fixture
def energy_service(monkeypatch: pytest.MonkeyPatch) -> DivineEnergyService:
    """Use an isolated real service so route and service contracts stay aligned."""
    service = DivineEnergyService()
    monkeypatch.setattr(energy_module, "energy_service", service)
    return service


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


def test_get_energy_returns_the_real_service_status(
    client: TestClient,
    energy_service: DivineEnergyService,
) -> None:
    response = client.get("/api/energy")

    assert response.status_code == 200
    assert response.json() == energy_service.get_status()


def test_get_energy_costs_preserves_the_service_response(
    client: TestClient,
    energy_service: DivineEnergyService,
) -> None:
    response = client.get("/api/energy/costs")

    assert response.status_code == 200
    assert response.json() == {"costs": energy_service.get_all_costs()}


def test_get_energy_history_honors_the_limit(
    client: TestClient,
    energy_service: DivineEnergyService,
) -> None:
    energy_service.spend("protect", turn=3, details="first")
    energy_service.spend("suppress", turn=4, details="second")

    response = client.get("/api/energy/history?limit=1")

    assert response.status_code == 200
    assert response.json() == {"history": energy_service.get_history(1)}


def test_calculate_energy_cost_does_not_forward_action_twice(
    client: TestClient,
    energy_service: DivineEnergyService,
) -> None:
    energy_service.set_energy(current=40)

    response = client.post(
        "/api/energy/calculate",
        json={"action": "create_species"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "action": "create_species",
        "cost": 50,
        "can_afford": False,
        "current_energy": 40,
    }


def test_calculate_pressure_uses_the_combined_cost_for_affordability(
    client: TestClient,
    energy_service: DivineEnergyService,
) -> None:
    energy_service.set_energy(current=10)
    pressures = [{"kind": "glacial_period", "intensity": 1}]

    response = client.post(
        "/api/energy/calculate",
        json={"action": "pressure", "pressures": pressures},
    )

    assert response.status_code == 200
    assert response.json() == {
        "action": "pressure",
        "cost": 20,
        "can_afford": False,
        "current_energy": 10,
    }


def test_toggle_energy_updates_the_service(
    client: TestClient,
    energy_service: DivineEnergyService,
) -> None:
    response = client.post("/api/energy/toggle", json={"enabled": False})

    assert response.status_code == 200
    assert response.json() == {"success": True, "enabled": False}
    assert energy_service.enabled is False


def test_set_energy_updates_and_returns_the_complete_status(
    client: TestClient,
    energy_service: DivineEnergyService,
) -> None:
    response = client.post(
        "/api/energy/set",
        json={"current": 120, "maximum": 500, "regen": 25},
    )

    assert response.status_code == 200
    assert response.json() == energy_service.get_status()
    assert response.json() == {
        "enabled": True,
        "current": 120,
        "maximum": 500,
        "regen_per_turn": 25,
        "total_spent": 0,
        "total_regenerated": 0,
        "percentage": 24.0,
    }
