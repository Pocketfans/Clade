"""Container wiring coverage for the save manager."""

from __future__ import annotations

from types import SimpleNamespace

from app.core.container import ServiceContainer
from app.repositories.genus_repository import GenusRepository


def test_save_manager_uses_container_genus_repository(tmp_path) -> None:
    container = ServiceContainer()
    genus_repository = GenusRepository()
    container.settings = SimpleNamespace(saves_dir=tmp_path / "saves")
    container.override("embedding_service", object())
    container.override("genus_repository", genus_repository)

    manager = container.save_manager

    assert manager._genus_repository is genus_repository
