import sys
from types import ModuleType, SimpleNamespace

from app.api import embedding_routes
from app.api.dependencies import get_container
from app.services import embedding_plugins


class RecordingPluginManager:
    instances: list["RecordingPluginManager"] = []

    def __init__(self, embedding_service, mode: str, config_path) -> None:
        self.embedding_service = embedding_service
        self.mode = mode
        self.config_path = config_path
        self.load_count = 0
        self.__class__.instances.append(self)

    def load_plugins(self) -> int:
        self.load_count += 1
        return 1


PLUGIN_ENDPOINT_NAMES = {
    "get_plugins_status",
    "get_behavior_profile",
    "get_similar_behaviors",
    "check_behavior_conflicts",
    "get_behavior_summary",
    "get_keystone_species",
    "get_ecosystem_stability",
    "find_replacement_candidates",
    "get_food_web_summary",
    "get_ecological_hotspots",
    "match_species_to_tiles",
    "get_tile_summary",
    "get_evolution_trends",
    "detect_convergent_evolution",
    "predict_species_trajectory",
    "get_evolution_summary",
    "get_ancestry_info",
    "get_genetic_inertia",
    "should_species_speciate",
    "calculate_divergence",
    "get_ancestry_summary",
}


def test_plugin_manager_uses_the_explicit_container_without_legacy_routes(
    monkeypatch,
) -> None:
    embedding_service = object()
    container = SimpleNamespace(
        embedding_service=embedding_service,
        simulation_engine=SimpleNamespace(_pipeline_mode="minimal"),
    )
    forbidden_routes = ModuleType("app.api.routes")

    def reject_legacy_attribute(name: str):
        raise AssertionError(f"legacy routes attribute accessed: {name}")

    forbidden_routes.__getattr__ = reject_legacy_attribute
    monkeypatch.setitem(sys.modules, "app.api.routes", forbidden_routes)
    monkeypatch.setattr(
        embedding_plugins,
        "EmbeddingPluginManager",
        RecordingPluginManager,
    )
    monkeypatch.setattr(embedding_plugins, "load_all_plugins", lambda: [])
    monkeypatch.setattr(embedding_routes, "_plugin_managers", {})
    RecordingPluginManager.instances.clear()

    manager = embedding_routes._get_plugin_manager(container)

    assert manager is RecordingPluginManager.instances[0]
    assert manager.embedding_service is embedding_service
    assert manager.mode == "minimal"
    assert manager.config_path.name == "stage_config.yaml"
    assert manager.load_count == 1


def test_plugin_manager_cache_is_isolated_per_container(monkeypatch) -> None:
    first_container = SimpleNamespace(
        embedding_service=object(),
        simulation_engine=SimpleNamespace(_pipeline_mode="minimal"),
    )
    second_container = SimpleNamespace(
        embedding_service=object(),
        simulation_engine=SimpleNamespace(_pipeline_mode="full"),
    )
    monkeypatch.setattr(
        embedding_plugins,
        "EmbeddingPluginManager",
        RecordingPluginManager,
    )
    monkeypatch.setattr(embedding_plugins, "load_all_plugins", lambda: [])
    monkeypatch.setattr(embedding_routes, "_plugin_managers", {})
    monkeypatch.setattr(embedding_routes, "id", lambda _container: 1, raising=False)
    RecordingPluginManager.instances.clear()

    first_manager = embedding_routes._get_plugin_manager(first_container)
    repeated_first_manager = embedding_routes._get_plugin_manager(first_container)
    second_manager = embedding_routes._get_plugin_manager(second_container)

    assert repeated_first_manager is first_manager
    assert second_manager is not first_manager
    assert [manager.embedding_service for manager in RecordingPluginManager.instances] == [
        first_container.embedding_service,
        second_container.embedding_service,
    ]


def test_all_plugin_endpoints_depend_on_the_current_container() -> None:
    routes_by_name = {
        route.endpoint.__name__: route
        for route in embedding_routes.router.routes
        if route.endpoint.__name__ in PLUGIN_ENDPOINT_NAMES
    }

    assert set(routes_by_name) == PLUGIN_ENDPOINT_NAMES
    missing_dependencies = [
        name
        for name, route in routes_by_name.items()
        if not any(
            dependency.call is get_container
            for dependency in route.dependant.dependencies
        )
    ]
    assert missing_dependencies == []
