#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
地形演化模拟工具

功能：
1. 生成随机的初始地形（基于 Perlin 噪声）。
2. 模拟 N 个回合的地质演化（板块运动、气候变化）。
3. 模拟环境压力事件（火山、冰期）。
4. 生成详细的演化报告。

用法：
    python scripts/simulate_terrain.py [--turns 10] [--width 80] [--height 40]
"""

import json
import logging
import sys
import argparse
import math
import random
from datetime import datetime
from pathlib import Path
from collections import Counter

# 设置UTF-8编码
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.ai.model_router import ModelConfig, ModelRouter
from app.core.database import init_db, engine
from app.core.config import get_settings
from app.models.environment import MapState, MapTile, TerrainEvolutionHistory
from app.repositories.environment_repository import environment_repository
from app.services.terrain_evolution import TerrainEvolutionService
from app.services.map_evolution import MapEvolutionService
from app.simulation.environment import ParsedPressure
from sqlmodel import Session, delete

# 配置logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

def create_test_map(width: int, height: int) -> list[MapTile]:
    """创建测试地图 - 使用Perlin噪声生成自然地形"""
    
    # 简化的Perlin噪声实现
    def interpolate(a, b, x):
        ft = x * math.pi
        f = (1 - math.cos(ft)) * 0.5
        return a * (1 - f) + b * f
    
    def noise2d(x, y, seed=0):
        n = int(x) + int(y) * 57 + seed * 131
        n = (n << 13) ^ n
        return (1.0 - ((n * (n * n * 15731 + 789221) + 1376312589) & 0x7fffffff) / 1073741824.0)
    
    def perlin_noise(x, y, seed=0):
        xi = int(math.floor(x))
        yi = int(math.floor(y))
        xf = x - xi
        yf = y - yi
        n00 = noise2d(xi, yi, seed)
        n10 = noise2d(xi + 1, yi, seed)
        n01 = noise2d(xi, yi + 1, seed)
        n11 = noise2d(xi + 1, yi + 1, seed)
        nx0 = interpolate(n00, n10, xf)
        nx1 = interpolate(n01, n11, xf)
        return interpolate(nx0, nx1, yf)
    
    def octave_perlin(x, y, octaves=4, persistence=0.5, seed=0):
        total = 0
        frequency = 1
        amplitude = 1
        max_value = 0
        for _ in range(octaves):
            total += perlin_noise(x * frequency, y * frequency, seed) * amplitude
            max_value += amplitude
            amplitude *= persistence
            frequency *= 2
        return total / max_value
    
    tiles = []
    seed = random.randint(0, 10000)
    
    # 生成高度图
    height_map = []
    for y in range(height):
        row = []
        for x in range(width):
            continent = octave_perlin(x / 30.0, y / 30.0, octaves=3, seed=seed)
            mountains = octave_perlin(x / 10.0, y / 10.0, octaves=4, seed=seed + 1) * 0.5
            detail = octave_perlin(x / 3.0, y / 3.0, octaves=2, seed=seed + 2) * 0.2
            combined = continent + mountains + detail
            normalized = (combined + 1.0) / 2.0
            row.append(normalized)
        height_map.append(row)
    
    # 生成地块
    for y in range(height):
        latitude = 1 - (y / (height - 1)) if height > 1 else 0.5
        for x in range(width):
            longitude = x / (width - 1) if width > 1 else 0.5
            normalized = height_map[y][x]
            
            # 海陆分布：60%海洋，40%陆地
            if normalized < 0.6:
                ocean_val = normalized / 0.6
                if ocean_val < 0.15: elevation = -11000 + ocean_val/0.15 * 5000
                elif ocean_val < 0.65: elevation = -6000 + (ocean_val-0.15)/0.5 * 3000
                elif ocean_val < 0.85: elevation = -3000 + (ocean_val-0.65)/0.2 * 2800
                else: elevation = -200 + (ocean_val-0.85)/0.15 * 200
            else:
                land_height = (normalized - 0.6) / 0.4
                if land_height < 0.6: elevation = land_height * 333
                elif land_height < 0.85: elevation = 200 + (land_height-0.6) * 5200
                elif land_height < 0.96: elevation = 1500 + ((land_height-0.85)/0.11)**1.5 * 2500
                else: elevation = 4000 + ((land_height-0.96)/0.04)**2.2 * 4848
            
            temperature = 35 - abs(latitude - 0.5) * 70 - (elevation / 100 if elevation > 0 else 0)
            humidity = max(0.0, min(1.0, 0.5 + 0.3 * math.sin(2 * math.pi * longitude) - 0.2 * abs(latitude - 0.5)))
            
            # 简化的生物群系推断
            if elevation < 0: biome, cover = "海洋", "水域"
            elif temperature < 0: biome, cover = "冻原", "苔原"
            elif humidity < 0.2: biome, cover = "荒漠", "沙漠"
            elif temperature > 25 and humidity > 0.6: biome, cover = "雨林", "森林"
            else: biome, cover = "温带森林", "森林"
            
            tile = MapTile(
                id=y * width + x + 1,
                x=x, y=y,
                q=x - (y - (y & 1)) // 2, r=y,
                biome=biome, elevation=elevation, cover=cover,
                temperature=temperature, humidity=humidity,
                resources=random.uniform(0.3, 0.9),
                has_river=False, pressures={},
            )
            tiles.append(tile)
    
    return tiles

def create_test_pressures(turn: int) -> list[ParsedPressure]:
    """创建测试压力"""
    pressures = []
    if turn % 5 == 0:
        pressures.append(ParsedPressure(
            kind="volcanic",
            intensity=7,
            affected_tiles=list(range(1000, 1100)),
            narrative="赤道带发生火山活动"
        ))
    elif turn % 7 == 0:
        pressures.append(ParsedPressure(
            kind="temperature",
            intensity=5,
            affected_tiles=[],
            narrative="全球温度上升"
        ))
    return pressures

def print_terrain_summary(tiles: list[MapTile], turn: int, log_func):
    """打印地形摘要"""
    log_func(f"\n{'='*60}")
    log_func(f"  回合 {turn} 地形统计")
    log_func(f"{'='*60}")
    
    elevations = [t.elevation for t in tiles]
    biomes = Counter(t.biome for t in tiles)
    
    log_func(f"  平均海拔: {sum(elevations)/len(elevations):.1f}m")
    log_func(f"  最高/最低: {max(elevations):.1f}m / {min(elevations):.1f}m")
    log_func(f"  生物群系: {dict(biomes.most_common(5))}")
    log_func(f"{'='*60}\n")

def main():
    parser = argparse.ArgumentParser(description="地形演化模拟")
    parser.add_argument("--turns", type=int, default=10, help="模拟回合数")
    parser.add_argument("--width", type=int, default=126, help="地图宽度")
    parser.add_argument("--height", type=int, default=40, help="地图高度")
    args = parser.parse_args()

    # 报告文件
    reports_dir = Path(__file__).parent.parent / "data/reports"
    reports_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = reports_dir / f"terrain_sim_{timestamp}.txt"
    
    def log(msg):
        print(msg)
        with open(report_file, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    
    log(f"开始地形演化模拟 (Turns={args.turns}, Size={args.width}x{args.height})")
    
    # 1. 初始化
    settings = get_settings()
    init_db()
    
    # 清理旧数据
    with Session(engine) as session:
        session.exec(delete(TerrainEvolutionHistory))
        session.exec(delete(MapTile))
        session.exec(delete(MapState))
        session.commit()
    
    # 2. AI Router
    router = ModelRouter(
        {"terrain_evolution": ModelConfig(provider="openai", model=settings.report_model)},
        base_url=settings.ai_base_url,
        api_key=settings.ai_api_key,
        timeout=settings.ai_request_timeout,
    )
    
    # 3. 服务
    terrain_service = TerrainEvolutionService(router)
    map_evolution_service = MapEvolutionService(width=args.width, height=args.height)
    
    # 4. 生成地图
    log("生成初始地形...")
    tiles = create_test_map(args.width, args.height)
    environment_repository.upsert_tiles(tiles)
    
    initial_state = MapState(
        turn_index=0,
        stage_name="稳定期",
        stage_progress=0,
        stage_duration=map_evolution_service.stage_duration,
        sea_level=0.0,
        global_avg_temperature=15.0,
    )
    environment_repository.save_state(initial_state)
    print_terrain_summary(tiles, 0, log)
    
    # 5. 循环
    for turn in range(1, args.turns + 1):
        log(f"--- Turn {turn} ---")
        
        current_state = environment_repository.get_state()
        prev_state = current_state
        
        # 推进阶段
        map_evolution_service.advance([], turn, {}, current_state)
        environment_repository.save_state(current_state)
        log(f"阶段: {current_state.stage_name} ({current_state.stage_progress}/{current_state.stage_duration})")
        
        # 压力
        pressures = create_test_pressures(turn)
        if pressures:
            log(f"压力事件: {[p.narrative for p in pressures]}")
            
        # 演化
        try:
            updated_tiles, events = terrain_service.evolve_terrain(
                tiles=tiles,
                pressures=pressures,
                map_state=current_state,
                prev_state=prev_state,
                turn_index=turn,
            )
            
            if updated_tiles:
                environment_repository.upsert_tiles(updated_tiles)
                tiles = environment_repository.list_tiles()
                log(f"地形更新: {len(updated_tiles)} 地块受影响")
            
            for evt in events:
                log(f"AI事件: {evt.description}")
                
            print_terrain_summary(tiles, turn, log)
            
        except Exception as e:
            log(f"[ERROR] {e}")
            import traceback
            traceback.print_exc()

    log(f"模拟完成。报告: {report_file}")

if __name__ == "__main__":
    main()

