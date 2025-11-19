from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from ..schemas.requests import PressureConfig


@dataclass(slots=True)
class ParsedPressure:
    kind: str
    intensity: int
    affected_tiles: list[int]
    narrative: str


class EnvironmentSystem:
    """Transforms player pressures into actionable map modifiers."""

    def __init__(self, map_width: int, map_height: int) -> None:
        self.map_width = map_width
        self.map_height = map_height

    def parse_pressures(self, pressures: Sequence[PressureConfig]) -> list[ParsedPressure]:
        parsed: list[ParsedPressure] = []
        for pressure in pressures:
            affected = self._resolve_tiles(pressure)
            narrative = self._describe_pressure(pressure)
            parsed.append(
                ParsedPressure(
                    kind=pressure.kind,
                    intensity=pressure.intensity,
                    affected_tiles=affected,
                    narrative=narrative,
                )
            )
        return parsed

    def _resolve_tiles(self, pressure: PressureConfig) -> list[int]:
        if pressure.target_region is None:
            return list(range(self.map_width * self.map_height))
        x, y = pressure.target_region
        radius = pressure.radius or 1
        affected: list[int] = []
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                tx, ty = x + dx, y + dy
                if not (0 <= tx < self.map_width and 0 <= ty < self.map_height):
                    continue
                affected.append(ty * self.map_width + tx)
        return affected

    def _describe_pressure(self, pressure: PressureConfig) -> str:
        target = (
            f"局部({pressure.target_region[0]}, {pressure.target_region[1]})"
            if pressure.target_region
            else "全球"
        )
        return (
            f"{target}发生{pressure.kind}事件，强度{pressure.intensity}/10，"
            f"附注:{pressure.narrative_note or '系统解析待补充'}"
        )

    def apply_pressures(self, parsed: Iterable[ParsedPressure]) -> dict[str, float]:
        """Aggregate modifiers for downstream mortality rules."""

        summary: dict[str, float] = {}
        for item in parsed:
            summary[item.kind] = summary.get(item.kind, 0.0) + item.intensity
        return summary
