from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

from ...models.species import Species
from ...schemas.responses import TurnReport


class ExportService:
    """Write per-turn Markdown + JSON exports for long-term archiving."""

    def __init__(self, reports_dir: str | Path, exports_dir: str | Path) -> None:
        self.reports_dir = Path(reports_dir)
        self.exports_dir = Path(exports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir.mkdir(parents=True, exist_ok=True)

    def export_turn(self, report: TurnReport, species: Sequence[Species]) -> tuple[Path, Path]:
        markdown_path = self._write_markdown(report)
        json_path = self._write_json(report, species)
        return markdown_path, json_path

    def list_records(self) -> list[dict[str, str | int]]:
        records: list[dict[str, str | int]] = []
        for md_path in sorted(self.reports_dir.glob("turn_*.md")):
            stem = md_path.stem.split("_")[-1]
            if not stem.isdigit():
                continue
            turn_index = int(stem)
            json_path = self.exports_dir / f"state_{turn_index:04}.json"
            records.append(
                {
                    "turn_index": turn_index,
                    "markdown_path": str(md_path.resolve()),
                    "json_path": str(json_path.resolve()),
                }
            )
        records.sort(key=lambda item: item["turn_index"], reverse=True)
        return records

    def _write_markdown(self, report: TurnReport) -> Path:
        path = self.reports_dir / f"turn_{report.turn_index:04}.md"
        lines: list[str] = [
            f"# 回合 {report.turn_index}",
            "",
            "## 环境压力",
            report.pressures_summary or "无",
            "",
            "## 叙事",
            report.narrative,
            "",
            "## 物种列表",
        ]
        for snap in report.species:
            # 生成描述预览
            desc_lines = []
            if snap.ecological_role:
                desc_preview = snap.ecological_role[:80] + "..." if len(snap.ecological_role) > 80 else snap.ecological_role
                desc_lines.append(f"  - 描述: {desc_preview}\n")
            
            lines.append(
                (
                    f"- **{snap.latin_name} / {snap.common_name} ({snap.lineage_code})**\n"
                    f"  - 数量: {snap.population} (占比 {(snap.population_share * 100):.1f}%)\n"
                    f"  - 死亡: {snap.deaths} (死亡率 {(snap.death_rate * 100):.1f}%)\n"
                    f"  - 状态: {snap.status}，类别: {snap.tier or '未知'}\n"
                    + "".join(desc_lines) +
                    f"  - 生态位重叠: {(snap.niche_overlap or 0):.2f}, 资源饱和: {(snap.resource_pressure or 0):.2f}\n"
                    f"  - 备注: {'; '.join(snap.notes) if snap.notes else '无'}"
                )
            )
        if report.branching_events:
            lines.append("\n## 分化事件")
            for event in report.branching_events:
                lines.append(
                    (
                        f"- {event.timestamp.isoformat()}"
                        f"：{event.parent_lineage} → {event.new_lineage}: {event.description}"
                    )
                )
        if report.background_summary:
            lines.append("\n## 背景物种概览")
            for summary in report.background_summary:
                lines.append(
                    (
                        f"- {summary.role}："
                        f"{len(summary.species_codes)} 种，合计 {summary.total_population} → {summary.survivor_population}"
                    )
                )
        if report.reemergence_events:
            lines.append("\n## 背景物种回归")
            for event in report.reemergence_events:
                lines.append(f"- {event.lineage_code}: {event.reason}")
        if report.major_events:
            lines.append("\n## 高级压力事件")
            for event in report.major_events:
                lines.append(f"- {event.severity}: {event.description} (格子:{len(event.affected_tiles)})")
        if report.map_changes:
            lines.append("\n## 地图演化")
            for change in report.map_changes:
                lines.append(f"- {change.stage}: {change.description} @ {change.affected_region}")
        if report.migration_events:
            lines.append("\n## 迁徙与避难")
            for event in report.migration_events:
                lines.append(
                    f"- {event.lineage_code}: {event.origin} → {event.destination} ({event.rationale})"
                )
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def _write_json(self, report: TurnReport, species: Sequence[Species]) -> Path:
        path = self.exports_dir / f"state_{report.turn_index:04}.json"
        payload = {
            "report": report.model_dump(),
            "species": [sp.model_dump() for sp in species],
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        return path
