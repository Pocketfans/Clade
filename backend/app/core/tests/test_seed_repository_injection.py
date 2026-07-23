"""Repository isolation coverage for genus seed data."""

from __future__ import annotations

import importlib

from app.core import seed
from app.models.genus import Genus


class _InMemoryGenusRepository:
    def __init__(self) -> None:
        self.genera: dict[str, Genus] = {}
        self.upserted_codes: list[str] = []

    def get_by_code(self, code: str) -> Genus | None:
        return self.genera.get(code)

    def upsert(self, genus: Genus) -> Genus:
        self.genera[genus.code] = genus
        self.upserted_codes.append(genus.code)
        return genus


def test_genus_repository_module_does_not_publish_singleton() -> None:
    module = importlib.import_module("app.repositories.genus_repository")

    assert not hasattr(module, "genus_repository")


def test_seed_genera_uses_injected_repository() -> None:
    repository = _InMemoryGenusRepository()

    seed._seed_genera(repository)
    seed._seed_genera(repository)

    assert set(repository.genera) == {"A", "B", "C"}
    assert repository.upserted_codes == ["A", "B", "C"]
