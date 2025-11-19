#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
EvoSandbox 世界重置工具

功能：
1. 将数据库重置为初始状态（仅保留种子物种）。
2. 清除所有存档文件。
3. 清除所有生成的报告和日志。
4. 重置地图状态（可选）。

用法：
    python scripts/reset_world.py [--force] [--keep-saves]
"""

import sys
import os
import shutil
import argparse
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from app.core.database import session_scope, init_db, engine
from app.core.seed import A_SCENARIO
from app.models.species import Species
from app.models.environment import MapTile, MapState, TerrainEvolutionHistory
from app.models.history import HistoryRecord
from app.repositories.species_repository import species_repository
from sqlmodel import delete

def clear_directory(dir_path: Path, pattern: str = "*"):
    """清空目录下的文件"""
    if not dir_path.exists():
        return
    
    print(f"正在清理目录: {dir_path} ({pattern})...")
    for item in dir_path.glob(pattern):
        if item.is_file():
            try:
                item.unlink()
            except Exception as e:
                print(f"  [WARN] 无法删除 {item.name}: {e}")
        elif item.is_dir():
            try:
                shutil.rmtree(item)
            except Exception as e:
                print(f"  [WARN] 无法删除目录 {item.name}: {e}")

def reset_database(keep_map: bool = False):
    """重置数据库内容"""
    print("\n[1/3] 重置数据库...")
    
    with session_scope() as session:
        # 1. 删除历史记录
        session.exec(delete(HistoryRecord))
        print("  - 已清除历史记录")
        
        # 2. 删除非初始物种
        initial_codes = {s['lineage_code'] for s in A_SCENARIO}
        all_species = session.query(Species).all()
        deleted_count = 0
        for sp in all_species:
            if sp.lineage_code not in initial_codes:
                session.delete(sp)
                deleted_count += 1
            else:
                # 重置初始物种状态
                scenario = next(s for s in A_SCENARIO if s['lineage_code'] == sp.lineage_code)
                sp.population = 1000  # 重置种群数量
                sp.status = 'alive'
                sp.created_turn = 0
                sp.parent_code = None
                # 恢复原始属性
                sp.morphology_stats = scenario['morphology_stats']
                sp.abstract_traits = scenario['abstract_traits']
                sp.description = scenario['description']
                session.add(sp)
                
        print(f"  - 已删除 {deleted_count} 个演化物种，重置 {len(initial_codes)} 个初始物种")
        
        # 3. 重置地图（如果需要）
        if not keep_map:
            session.exec(delete(TerrainEvolutionHistory))
            session.exec(delete(MapState))
            # 注意：通常我们不删除 MapTile，因为生成地图很耗时。
            # 如果确实要重置地图生成，需要取消下面注释
            # session.exec(delete(MapTile)) 
            print("  - 已重置地图状态（保留地形数据）")
            
            # 重置初始地图状态
            initial_state = MapState(
                turn_index=0,
                stage_name="稳定期",
                stage_progress=0,
                stage_duration=50,
                sea_level=0.0,
                global_avg_temperature=15.0
            )
            session.add(initial_state)
            print("  - 已创建初始地图状态")

def main():
    parser = argparse.ArgumentParser(description="重置 EvoSandbox 世界状态")
    parser.add_argument("--force", action="store_true", help="跳过确认提示")
    parser.add_argument("--keep-saves", action="store_true", help="保留存档文件")
    parser.add_argument("--keep-map", action="store_true", help="保留地图演化状态")
    
    args = parser.parse_args()
    
    if not args.force:
        print("警告：此操作将永久删除所有游戏进度、演化物种和日志！")
        response = input("确定要继续吗？[y/N]: ")
        if response.lower() != 'y':
            print("操作已取消。")
            sys.exit(0)
            
    # 路径定义
    root_dir = Path(__file__).parent.parent
    data_dir = root_dir / "data"
    
    # 1. 重置数据库
    try:
        reset_database(keep_map=args.keep_map)
    except Exception as e:
        print(f"[ERROR] 数据库重置失败: {e}")
        sys.exit(1)
        
    # 2. 清理文件
    print("\n[2/3] 清理文件...")
    if not args.keep_saves:
        clear_directory(data_dir / "saves")
        clear_directory(data_dir / "exports")
    
    clear_directory(data_dir / "reports")
    clear_directory(data_dir / "logs")
    
    # 3. 验证
    print("\n[3/3] 验证状态...")
    species_count = len(species_repository.list_species())
    print(f"  当前物种数: {species_count} (应为 3)")
    
    print("\n" + "="*40)
    print("世界已重置完成！")
    print("="*40)

if __name__ == "__main__":
    main()

