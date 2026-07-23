from __future__ import annotations

import json
from typing import Any

import pytest

from app.services.species.speciation import SpeciationService


class InterruptedSpeciationRouter:
    def __init__(self, partial: str) -> None:
        self.partial = partial

    async def astream(self, capability: str, payload: dict[str, Any]):
        yield {"type": "status", "state": "receiving"}
        yield self.partial
        yield {
            "type": "status",
            "state": "interrupted",
            "reason": "outbound_timeout",
            "partial": True,
        }


@pytest.mark.asyncio
async def test_batch_speciation_does_not_parse_partial_json(monkeypatch) -> None:
    partial = '{"species": [{"name": "unfinished"}]'
    service = object.__new__(SpeciationService)
    service.router = InterruptedSpeciationRouter(partial)
    original_loads = json.loads

    def reject_partial(value: str, *args: Any, **kwargs: Any) -> Any:
        if value == partial:
            pytest.fail("partial streamed JSON must not be parsed")
        return original_loads(value, *args, **kwargs)

    monkeypatch.setattr(json, "loads", reject_partial)

    result = await service._call_batch_ai({}, None, entries=[])

    assert result == {"_timeout": True, "_use_fallback": True}
