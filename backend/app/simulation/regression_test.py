"""
Regression Test Framework - 回归测试框架

用于验证插件化引擎与原版引擎的行为一致性。
在相同输入条件下，对比两个版本的输出是否一致。
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import copy
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SpeciesSnapshot:
    """物种快照（用于对比）"""
    lineage_code: str
    common_name: str
    population: int
    status: str
    trophic_level: float
    death_rate: float = 0.0


@dataclass
class TurnSnapshot:
    """回合快照（用于对比）"""
    turn_index: int
    species_data: dict[str, SpeciesSnapshot] = field(default_factory=dict)
    extinctions: list[str] = field(default_factory=list)
    speciations: list[str] = field(default_factory=list)
    total_population: int = 0
    total_biomass: float = 0.0
    marine_biomass: float = 0.0
    terrestrial_biomass: float = 0.0
    avg_trophic_level: float = 0.0
    sea_level: float = 0.0
    global_temperature: float = 0.0


@dataclass
class RegressionResult:
    """回归测试结果"""
    test_name: str
    rounds: int
    passed: bool
    max_population_diff: float = 0.0
    max_diff_species: str = ""
    max_diff_turn: int = 0
    extinction_match: bool = True
    speciation_match: bool = True
    biomass_diff: float = 0.0
    details: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "test_name": self.test_name,
            "rounds": self.rounds,
            "passed": self.passed,
            "max_population_diff": self.max_population_diff,
            "max_diff_species": self.max_diff_species,
            "max_diff_turn": self.max_diff_turn,
            "extinction_match": self.extinction_match,
            "speciation_match": self.speciation_match,
            "biomass_diff": self.biomass_diff,
            "details": self.details,
        }


class RegressionTestRunner:
    """回归测试运行器"""
    
    # 允许的差异阈值
    POPULATION_DIFF_THRESHOLD = 0.05  # 5% 的种群差异
    BIOMASS_DIFF_THRESHOLD = 0.05  # 5% 的生物量差异
    
    def __init__(self, seed: int = 42):
        self.seed = seed
        self.old_snapshots: list[TurnSnapshot] = []
        self.new_snapshots: list[TurnSnapshot] = []
    
    def _reset_random_state(self) -> None:
        """重置随机状态"""
        random.seed(self.seed)
        # 如果使用 numpy，也需要重置
        try:
            import numpy as np
            np.random.seed(self.seed)
        except ImportError:
            pass
    
    def _capture_turn_snapshot(
        self,
        turn_index: int,
        species_list: list,
        report: Any,
    ) -> TurnSnapshot:
        """捕获回合快照"""
        snapshot = TurnSnapshot(turn_index=turn_index)
        
        # 物种数据
        for sp in species_list:
            code = sp.lineage_code
            population = int(sp.morphology_stats.get("population", 0) or 0)
            snapshot.species_data[code] = SpeciesSnapshot(
                lineage_code=code,
                common_name=sp.common_name,
                population=population,
                status=sp.status,
                trophic_level=sp.trophic_level,
            )
            
            # 计算生物量
            weight = sp.morphology_stats.get("body_weight_g", 1.0) or 1.0
            biomass = population * weight
            snapshot.total_biomass += biomass
            snapshot.total_population += population
            
            habitat = (getattr(sp, "habitat_type", "") or "").lower()
            if habitat in {"marine", "deep_sea", "coastal"}:
                snapshot.marine_biomass += biomass
            else:
                snapshot.terrestrial_biomass += biomass
            
            snapshot.avg_trophic_level += sp.trophic_level
        
        if species_list:
            snapshot.avg_trophic_level /= len(species_list)
        
        # 从报告中提取信息
        if report:
            # 灭绝和分化
            for sp_snap in getattr(report, 'species', []):
                if sp_snap.status == "extinct":
                    snapshot.extinctions.append(sp_snap.lineage_code)
            
            for branch in getattr(report, 'branching_events', []) or []:
                snapshot.speciations.append(branch.new_lineage)
            
            # 环境数据
            snapshot.sea_level = getattr(report, 'sea_level', 0.0) or 0.0
            snapshot.global_temperature = getattr(report, 'global_temperature', 15.0) or 15.0
        
        return snapshot
    
    def compare_snapshots(
        self,
        old_snapshots: list[TurnSnapshot],
        new_snapshots: list[TurnSnapshot],
    ) -> RegressionResult:
        """对比两组快照"""
        result = RegressionResult(
            test_name="Regression Test",
            rounds=len(old_snapshots),
            passed=True,
        )
        
        if len(old_snapshots) != len(new_snapshots):
            result.passed = False
            result.details.append(
                f"回合数不匹配: 旧版 {len(old_snapshots)} vs 新版 {len(new_snapshots)}"
            )
            return result
        
        max_pop_diff = 0.0
        max_diff_species = ""
        max_diff_turn = 0
        
        for old_snap, new_snap in zip(old_snapshots, new_snapshots):
            turn = old_snap.turn_index
            
            # 对比灭绝事件
            old_extinctions = set(old_snap.extinctions)
            new_extinctions = set(new_snap.extinctions)
            if old_extinctions != new_extinctions:
                result.extinction_match = False
                diff = old_extinctions.symmetric_difference(new_extinctions)
                result.details.append(f"回合 {turn} 灭绝差异: {diff}")
            
            # 对比分化事件
            old_speciations = set(old_snap.speciations)
            new_speciations = set(new_snap.speciations)
            if old_speciations != new_speciations:
                result.speciation_match = False
                diff = old_speciations.symmetric_difference(new_speciations)
                result.details.append(f"回合 {turn} 分化差异: {diff}")
            
            # 对比每个物种的种群
            all_codes = set(old_snap.species_data.keys()) | set(new_snap.species_data.keys())
            for code in all_codes:
                old_sp = old_snap.species_data.get(code)
                new_sp = new_snap.species_data.get(code)
                
                if old_sp is None or new_sp is None:
                    result.details.append(
                        f"回合 {turn} 物种 {code} 存在性差异"
                    )
                    continue
                
                if old_sp.population > 0:
                    pop_diff = abs(old_sp.population - new_sp.population) / old_sp.population
                else:
                    pop_diff = 0 if new_sp.population == 0 else 1.0
                
                if pop_diff > max_pop_diff:
                    max_pop_diff = pop_diff
                    max_diff_species = code
                    max_diff_turn = turn
            
            # 对比生物量
            if old_snap.total_biomass > 0:
                biomass_diff = abs(old_snap.total_biomass - new_snap.total_biomass) / old_snap.total_biomass
                if biomass_diff > result.biomass_diff:
                    result.biomass_diff = biomass_diff
        
        result.max_population_diff = max_pop_diff
        result.max_diff_species = max_diff_species
        result.max_diff_turn = max_diff_turn
        
        # 判断是否通过
        if max_pop_diff > self.POPULATION_DIFF_THRESHOLD:
            result.passed = False
            result.details.append(
                f"种群差异过大: {max_pop_diff:.2%} (物种: {max_diff_species}, 回合: {max_diff_turn})"
            )
        
        if result.biomass_diff > self.BIOMASS_DIFF_THRESHOLD:
            result.passed = False
            result.details.append(
                f"生物量差异过大: {result.biomass_diff:.2%}"
            )
        
        if not result.extinction_match:
            result.passed = False
        
        if not result.speciation_match:
            result.passed = False
        
        return result
    
    async def run_engine_with_snapshots(
        self,
        engine,
        command,
        capture_callback,
    ) -> list[TurnSnapshot]:
        """运行引擎并捕获快照"""
        from ..repositories.species_repository import species_repository
        
        snapshots = []
        original_callback = engine._event_callback
        
        # 设置回调来捕获每回合结束时的状态
        def on_event(event_type, message, category, **extra):
            if original_callback:
                original_callback(event_type, message, category, **extra)
        
        engine._event_callback = on_event
        
        try:
            reports = await engine.run_turns_async(command)
            
            # 从报告中构建快照
            for report in reports:
                species_list = species_repository.list_species()
                snapshot = self._capture_turn_snapshot(
                    report.turn_index,
                    species_list,
                    report,
                )
                snapshots.append(snapshot)
        finally:
            engine._event_callback = original_callback
        
        return snapshots


def generate_regression_report(
    results: list[RegressionResult],
    output_path: str | Path | None = None,
) -> str:
    """生成回归测试报告"""
    lines = [
        "=" * 60,
        "回归测试报告",
        f"生成时间: {datetime.now().isoformat()}",
        "=" * 60,
        "",
    ]
    
    passed_count = sum(1 for r in results if r.passed)
    total_count = len(results)
    
    lines.append(f"总测试数: {total_count}")
    lines.append(f"通过: {passed_count}")
    lines.append(f"失败: {total_count - passed_count}")
    lines.append("")
    
    for result in results:
        status = "✅ PASSED" if result.passed else "❌ FAILED"
        lines.append(f"测试: {result.test_name} ({result.rounds} 回合)")
        lines.append(f"  状态: {status}")
        lines.append(f"  最大种群差异: {result.max_population_diff:.2%}")
        if result.max_diff_species:
            lines.append(f"    差异最大物种: {result.max_diff_species} (回合 {result.max_diff_turn})")
        lines.append(f"  灭绝事件匹配: {'是' if result.extinction_match else '否'}")
        lines.append(f"  分化事件匹配: {'是' if result.speciation_match else '否'}")
        lines.append(f"  生物量差异: {result.biomass_diff:.2%}")
        
        if result.details:
            lines.append("  详细信息:")
            for detail in result.details[:10]:  # 最多显示10条
                lines.append(f"    - {detail}")
            if len(result.details) > 10:
                lines.append(f"    ... 还有 {len(result.details) - 10} 条")
        lines.append("")
    
    lines.append("=" * 60)
    overall = "✅ 所有测试通过" if passed_count == total_count else "❌ 存在失败的测试"
    lines.append(f"总结: {overall}")
    lines.append("=" * 60)
    
    report_text = "\n".join(lines)
    
    if output_path:
        Path(output_path).write_text(report_text, encoding="utf-8")
        
        # 同时输出 JSON 格式
        json_path = Path(output_path).with_suffix(".json")
        json_data = {
            "generated_at": datetime.now().isoformat(),
            "total": total_count,
            "passed": passed_count,
            "failed": total_count - passed_count,
            "results": [r.to_dict() for r in results],
        }
        json_path.write_text(json.dumps(json_data, indent=2, ensure_ascii=False), encoding="utf-8")
    
    return report_text


# ============================================================================
# 快速一致性检查（不需要完整的双引擎对比）
# ============================================================================

class QuickConsistencyChecker:
    """快速一致性检查器
    
    由于新旧引擎使用相同的代码路径（只是重构了变量位置），
    我们可以通过检查关键不变量来验证一致性。
    """
    
    def __init__(self):
        self.checks: list[tuple[str, bool, str]] = []
    
    def check_context_fields(self, ctx) -> None:
        """检查 SimulationContext 字段完整性"""
        from .context import SimulationContext
        
        required_fields = [
            "turn_index", "command", "pressures", "modifiers", "major_events",
            "current_map_state", "map_changes", "all_species", "species_batch",
            "extinct_codes", "tiered", "all_habitats", "all_tiles",
            "niche_metrics", "trophic_interactions", "preliminary_mortality",
            "critical_results", "focus_results", "background_results",
            "combined_results", "migration_events", "migration_count",
            "new_populations", "ai_status_evals", "branching_events",
            "background_summary", "reemergence_events", "report",
        ]
        
        for field in required_fields:
            has_field = hasattr(ctx, field)
            self.checks.append((
                f"Context has '{field}'",
                has_field,
                "" if has_field else f"Missing field: {field}"
            ))
    
    def check_report_integrity(self, report) -> None:
        """检查报告完整性"""
        if report is None:
            self.checks.append(("Report exists", False, "Report is None"))
            return
        
        self.checks.append(("Report exists", True, ""))
        
        # 检查必要字段
        required = ["turn_index", "species", "narrative", "pressures_summary"]
        for field in required:
            has_field = hasattr(report, field) and getattr(report, field) is not None
            self.checks.append((
                f"Report has '{field}'",
                has_field,
                "" if has_field else f"Missing or None: {field}"
            ))
        
        # 检查物种快照
        species = getattr(report, 'species', [])
        if species:
            self.checks.append(("Report has species", True, f"Count: {len(species)}"))
            
            # 检查物种快照字段
            for sp in species[:3]:  # 只检查前3个
                has_population = hasattr(sp, 'population')
                has_death_rate = hasattr(sp, 'death_rate')
                self.checks.append((
                    f"Species {sp.lineage_code} has required fields",
                    has_population and has_death_rate,
                    ""
                ))
        else:
            self.checks.append(("Report has species", False, "Empty species list"))
    
    def check_population_conservation(self, ctx) -> None:
        """检查种群守恒（初始 - 死亡 + 出生 = 最终）"""
        if not ctx.combined_results:
            return
        
        for item in ctx.combined_results[:5]:  # 只检查前5个
            initial = item.initial_population
            deaths = item.deaths
            births = getattr(item, 'births', 0)
            final = getattr(item, 'final_population', 0)
            survivors = item.survivors
            
            # 验证: final = survivors + births
            expected = survivors + births
            is_valid = abs(final - expected) <= 1  # 允许1的舍入误差
            
            self.checks.append((
                f"Population conservation for {item.species.lineage_code}",
                is_valid,
                f"Expected {expected}, got {final}" if not is_valid else ""
            ))
    
    def get_report(self) -> str:
        """生成检查报告"""
        lines = ["一致性检查报告", "=" * 40]
        
        passed = sum(1 for _, ok, _ in self.checks if ok)
        total = len(self.checks)
        
        for name, ok, msg in self.checks:
            status = "✅" if ok else "❌"
            line = f"{status} {name}"
            if msg:
                line += f" ({msg})"
            lines.append(line)
        
        lines.append("=" * 40)
        lines.append(f"通过: {passed}/{total}")
        
        return "\n".join(lines)


async def run_quick_consistency_check(engine, command) -> str:
    """运行快速一致性检查"""
    from .context import SimulationContext
    
    checker = QuickConsistencyChecker()
    
    # 运行一个回合
    original_rounds = command.rounds
    command.rounds = 1
    
    try:
        reports = await engine.run_turns_async(command)
        
        if reports:
            report = reports[0]
            checker.check_report_integrity(report)
    finally:
        command.rounds = original_rounds
    
    return checker.get_report()



