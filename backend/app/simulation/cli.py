#!/usr/bin/env python3
"""
Simulation CLI - 命令行接口

提供命令行入口快速发起模拟实验，无需编写额外代码。

用法：
    python -m app.simulation.cli --mode standard --turns 10
    python -m app.simulation.cli --mode debug --turns 5 --seed 42
    python -m app.simulation.cli --config scenario.yaml --output results/
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import random
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# 确保项目路径在 sys.path 中
project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


logger = logging.getLogger(__name__)


# ============================================================================
# 运行结果数据结构
# ============================================================================

@dataclass
class SimulationResult:
    """模拟运行结果"""
    success: bool
    mode: str
    turns_completed: int
    total_duration_s: float
    random_seed: int
    
    # 物种统计
    initial_species_count: int = 0
    final_species_count: int = 0
    extinct_species_count: int = 0
    new_species_count: int = 0
    
    # 生态统计
    total_migrations: int = 0
    total_speciations: int = 0
    
    # 环境统计
    final_temperature: float = 15.0
    final_sea_level: float = 0.0
    
    # 性能统计
    avg_turn_duration_ms: float = 0.0
    slowest_stage: str = ""
    slowest_stage_time_ms: float = 0.0
    
    # 错误信息
    errors: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)
    
    def format_summary(self) -> str:
        """格式化为可读摘要"""
        lines = [
            "=" * 60,
            "模拟运行结果",
            "=" * 60,
            "",
            f"状态: {'✅ 成功' if self.success else '❌ 失败'}",
            f"模式: {self.mode}",
            f"回合: {self.turns_completed}",
            f"耗时: {self.total_duration_s:.2f}s",
            f"随机种子: {self.random_seed}",
            "",
            "物种统计:",
            f"  初始物种数: {self.initial_species_count}",
            f"  最终物种数: {self.final_species_count}",
            f"  灭绝物种数: {self.extinct_species_count}",
            f"  新增物种数: {self.new_species_count}",
            "",
            "生态事件:",
            f"  总迁徙次数: {self.total_migrations}",
            f"  总分化次数: {self.total_speciations}",
            "",
            "环境状态:",
            f"  全球温度: {self.final_temperature:.1f}°C",
            f"  海平面: {self.final_sea_level:.1f}m",
            "",
            "性能:",
            f"  平均回合耗时: {self.avg_turn_duration_ms:.1f}ms",
            f"  最慢阶段: {self.slowest_stage} ({self.slowest_stage_time_ms:.1f}ms)",
        ]
        
        if self.errors:
            lines.append("")
            lines.append("错误:")
            for error in self.errors:
                lines.append(f"  - {error}")
        
        lines.append("")
        lines.append("=" * 60)
        
        return "\n".join(lines)


# ============================================================================
# CLI 主逻辑
# ============================================================================

def setup_logging(verbosity: int = 1, log_file: str | None = None) -> None:
    """配置日志"""
    level_map = {
        0: logging.WARNING,
        1: logging.INFO,
        2: logging.DEBUG,
        3: logging.DEBUG,
    }
    level = level_map.get(verbosity, logging.INFO)
    
    handlers: List[logging.Handler] = [logging.StreamHandler()]
    
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )


async def run_simulation(
    mode: str = "standard",
    turns: int = 10,
    seed: int = 0,
    config_file: str | None = None,
    scenario_file: str | None = None,
    output_dir: str | None = None,
    param_overrides: Dict[str, Any] | None = None,
) -> SimulationResult:
    """运行模拟
    
    Args:
        mode: 模式名称
        turns: 回合数
        seed: 随机种子（0 = 随机）
        config_file: 阶段配置文件路径
        scenario_file: 场景文件路径（预留）
        output_dir: 输出目录
        param_overrides: 参数覆盖
    
    Returns:
        模拟结果
    """
    from .stage_config import (
        load_mode_with_parameters,
        get_mode_parameters,
        AVAILABLE_MODES,
    )
    
    # 验证模式
    if mode not in AVAILABLE_MODES:
        return SimulationResult(
            success=False,
            mode=mode,
            turns_completed=0,
            total_duration_s=0.0,
            random_seed=seed,
            errors=[f"未知模式: {mode}。可用模式: {', '.join(AVAILABLE_MODES)}"],
        )
    
    # 设置随机种子
    if seed == 0:
        seed = random.randint(1, 999999)
    random.seed(seed)
    
    # 加载模式配置和参数
    stages, params = load_mode_with_parameters(
        mode,
        yaml_path=config_file,
        param_overrides=param_overrides,
    )
    
    logger.info(f"开始模拟: 模式={mode}, 回合={turns}, 种子={seed}")
    
    start_time = time.perf_counter()
    errors = []
    turn_durations = []
    total_migrations = 0
    total_speciations = 0
    slowest_stage = ""
    slowest_stage_time = 0.0
    
    # 初始物种统计
    initial_species_count = 0
    final_species_count = 0
    extinct_count = 0
    new_species_count = 0
    final_temp = 15.0
    final_sea = 0.0
    
    try:
        # 尝试导入引擎
        from .engine import SimulationEngine
        from ..schemas.requests import TurnCommand
        from ..repositories.species_repository import species_repository
        from ..repositories.environment_repository import environment_repository
        
        # 创建引擎
        engine = SimulationEngine()
        
        # 获取初始物种数
        try:
            all_species = species_repository.list_species()
            initial_species_count = len([s for s in all_species if s.status == "alive"])
        except Exception:
            pass
        
        # 创建命令
        command = TurnCommand(pressures=[], rounds=turns)
        
        # 运行模拟
        for turn in range(turns):
            turn_start = time.perf_counter()
            
            try:
                # 执行一个回合
                single_cmd = TurnCommand(pressures=[], rounds=1)
                result = await engine.run_turns_async(single_cmd)
                
                # 收集统计
                if result and len(result) > 0:
                    report = result[0]
                    total_migrations += getattr(report, "migration_count", 0)
                    total_speciations += len(getattr(report, "branching_events", []))
                    
                    # 更新最慢阶段（如果有 pipeline metrics）
                    if hasattr(engine, "_last_pipeline_metrics"):
                        metrics = engine._last_pipeline_metrics
                        for stage_metrics in getattr(metrics, "stage_metrics", []):
                            if stage_metrics.duration_ms > slowest_stage_time:
                                slowest_stage_time = stage_metrics.duration_ms
                                slowest_stage = stage_metrics.stage_name
                
            except Exception as e:
                errors.append(f"回合 {turn} 失败: {str(e)}")
                logger.error(f"回合 {turn} 失败: {e}", exc_info=True)
            
            turn_duration = (time.perf_counter() - turn_start) * 1000
            turn_durations.append(turn_duration)
            
            if (turn + 1) % 10 == 0 or turn == turns - 1:
                logger.info(f"进度: {turn + 1}/{turns} 回合完成")
        
        # 获取最终统计
        try:
            all_species = species_repository.list_species()
            final_species_count = len([s for s in all_species if s.status == "alive"])
            extinct_count = len([s for s in all_species if s.status == "extinct"])
            new_species_count = max(0, final_species_count + extinct_count - initial_species_count)
            
            map_state = environment_repository.get_state()
            if map_state:
                final_temp = getattr(map_state, "global_avg_temperature", 15.0)
                final_sea = getattr(map_state, "sea_level", 0.0)
        except Exception:
            pass
        
    except ImportError as e:
        errors.append(f"导入错误: {str(e)}")
        logger.error(f"导入失败: {e}")
    except Exception as e:
        errors.append(f"运行错误: {str(e)}")
        logger.error(f"运行失败: {e}", exc_info=True)
    
    total_duration = time.perf_counter() - start_time
    avg_turn_duration = sum(turn_durations) / len(turn_durations) if turn_durations else 0.0
    
    result = SimulationResult(
        success=len(errors) == 0,
        mode=mode,
        turns_completed=len(turn_durations),
        total_duration_s=total_duration,
        random_seed=seed,
        initial_species_count=initial_species_count,
        final_species_count=final_species_count,
        extinct_species_count=extinct_count,
        new_species_count=new_species_count,
        total_migrations=total_migrations,
        total_speciations=total_speciations,
        final_temperature=final_temp,
        final_sea_level=final_sea,
        avg_turn_duration_ms=avg_turn_duration,
        slowest_stage=slowest_stage,
        slowest_stage_time_ms=slowest_stage_time,
        errors=errors,
    )
    
    # 保存结果
    if output_dir:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_file = output_path / f"result_{timestamp}_{mode}.json"
        
        with open(result_file, "w", encoding="utf-8") as f:
            f.write(result.to_json())
        
        logger.info(f"结果已保存到: {result_file}")
    
    return result


def create_parser() -> argparse.ArgumentParser:
    """创建参数解析器"""
    parser = argparse.ArgumentParser(
        prog="simulation-cli",
        description="模拟引擎命令行工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
    # 使用标准模式运行 10 回合
    python -m app.simulation.cli --mode standard --turns 10
    
    # 使用调试模式，固定随机种子
    python -m app.simulation.cli --mode debug --turns 5 --seed 42
    
    # 指定输出目录
    python -m app.simulation.cli --mode full --turns 20 --output results/
    
    # 覆盖默认参数
    python -m app.simulation.cli --mode standard --turns 10 \\
        --param pressure_scale=1.5 --param max_species_count=200

可用模式：
    minimal  - 极简模式（快速测试）
    standard - 标准模式（推荐日常使用）
    full     - 全功能模式（完整体验）
    debug    - 调试模式（开发调试）
""",
    )
    
    # 基本参数
    parser.add_argument(
        "-m", "--mode",
        choices=["minimal", "standard", "full", "debug"],
        default="standard",
        help="模拟模式 (default: standard)",
    )
    
    parser.add_argument(
        "-t", "--turns",
        type=int,
        default=10,
        help="回合数 (default: 10)",
    )
    
    parser.add_argument(
        "-s", "--seed",
        type=int,
        default=0,
        help="随机种子 (0=随机, default: 0)",
    )
    
    # 配置文件
    parser.add_argument(
        "-c", "--config",
        type=str,
        default=None,
        help="阶段配置 YAML 文件路径",
    )
    
    parser.add_argument(
        "--scenario",
        type=str,
        default=None,
        help="场景配置文件路径（预留）",
    )
    
    # 输出
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        help="结果输出目录",
    )
    
    # 日志
    parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=1,
        help="增加日志详细程度 (-v, -vv, -vvv)",
    )
    
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="静默模式（仅输出结果）",
    )
    
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="日志文件路径",
    )
    
    # 参数覆盖
    parser.add_argument(
        "-p", "--param",
        action="append",
        type=str,
        default=[],
        help="覆盖模式参数 (格式: key=value)",
    )
    
    # 其他选项
    parser.add_argument(
        "--list-modes",
        action="store_true",
        help="列出所有可用模式",
    )
    
    parser.add_argument(
        "--show-mode",
        type=str,
        default=None,
        help="显示指定模式的详细信息",
    )
    
    parser.add_argument(
        "--list-stages",
        action="store_true",
        help="列出所有已注册的阶段",
    )
    
    return parser


def parse_param_overrides(param_list: List[str]) -> Dict[str, Any]:
    """解析参数覆盖列表"""
    overrides = {}
    for param_str in param_list:
        if "=" not in param_str:
            continue
        key, value = param_str.split("=", 1)
        key = key.strip()
        value = value.strip()
        
        # 尝试解析为数字
        try:
            if "." in value:
                overrides[key] = float(value)
            else:
                overrides[key] = int(value)
        except ValueError:
            # 布尔值
            if value.lower() in ("true", "yes", "1"):
                overrides[key] = True
            elif value.lower() in ("false", "no", "0"):
                overrides[key] = False
            else:
                overrides[key] = value
    
    return overrides


def main():
    """主入口"""
    parser = create_parser()
    args = parser.parse_args()
    
    # 配置日志
    verbosity = 0 if args.quiet else args.verbose
    setup_logging(verbosity, args.log_file)
    
    # 处理信息查询命令
    if args.list_modes:
        from .stage_config import AVAILABLE_MODES, format_mode_info
        print("\n可用模式:")
        print("-" * 40)
        for mode in AVAILABLE_MODES:
            print(f"\n{format_mode_info(mode)}")
        return 0
    
    if args.show_mode:
        from .stage_config import format_mode_info, AVAILABLE_MODES
        if args.show_mode not in AVAILABLE_MODES:
            print(f"未知模式: {args.show_mode}")
            print(f"可用模式: {', '.join(AVAILABLE_MODES)}")
            return 1
        print(format_mode_info(args.show_mode))
        return 0
    
    if args.list_stages:
        from .stage_config import stage_registry
        print("\n已注册阶段:")
        print("-" * 40)
        for name in sorted(stage_registry.list_stages()):
            print(f"  - {name}")
        return 0
    
    # 解析参数覆盖
    param_overrides = parse_param_overrides(args.param)
    
    # 运行模拟
    result = asyncio.run(run_simulation(
        mode=args.mode,
        turns=args.turns,
        seed=args.seed,
        config_file=args.config,
        scenario_file=args.scenario,
        output_dir=args.output,
        param_overrides=param_overrides,
    ))
    
    # 输出结果
    print(result.format_summary())
    
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())



