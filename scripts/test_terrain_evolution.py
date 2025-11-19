#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
地形演化AI推演测试脚本

测试AI驱动的地形演化系统，进行10轮模拟，输出地质演化过程
"""
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# 设置UTF-8编码
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 配置logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.ai.model_router import ModelConfig, ModelRouter
from app.core.database import init_db
from app.models.environment import MapState, MapTile
from app.repositories.environment_repository import environment_repository
from app.services.terrain_evolution import TerrainEvolutionService
from app.services.map_evolution import MapEvolutionService
from app.simulation.environment import ParsedPressure


def load_settings():
    """加载settings.json配置"""
    settings_path = Path(__file__).parent.parent / "data/settings.json"
    if not settings_path.exists():
        raise FileNotFoundError(f"找不到settings.json: {settings_path}")
    
    with open(settings_path, "r", encoding="utf-8") as f:
        return json.load(f)


def create_test_map(width: int = 80, height: int = 40) -> list[MapTile]:
    """创建测试地图 - 使用Perlin噪声生成自然地形"""
    import math
    import random
    
    # 简化的Perlin噪声实现
    def interpolate(a, b, x):
        """平滑插值"""
        ft = x * math.pi
        f = (1 - math.cos(ft)) * 0.5
        return a * (1 - f) + b * f
    
    def noise2d(x, y, seed=0):
        """2D噪声生成器"""
        n = int(x) + int(y) * 57 + seed * 131
        n = (n << 13) ^ n
        return (1.0 - ((n * (n * n * 15731 + 789221) + 1376312589) & 0x7fffffff) / 1073741824.0)
    
    def perlin_noise(x, y, seed=0):
        """Perlin噪声"""
        xi = int(math.floor(x))
        yi = int(math.floor(y))
        xf = x - xi
        yf = y - yi
        
        # 四个角的噪声值
        n00 = noise2d(xi, yi, seed)
        n10 = noise2d(xi + 1, yi, seed)
        n01 = noise2d(xi, yi + 1, seed)
        n11 = noise2d(xi + 1, yi + 1, seed)
        
        # 双线性插值
        nx0 = interpolate(n00, n10, xf)
        nx1 = interpolate(n01, n11, xf)
        return interpolate(nx0, nx1, yf)
    
    def octave_perlin(x, y, octaves=4, persistence=0.5, seed=0):
        """多层Perlin噪声"""
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
    
    # 第一步：生成Perlin噪声高度图
    height_map = []
    for y in range(height):
        row = []
        for x in range(width):
            # 多尺度Perlin噪声叠加
            # 大尺度：大陆形状（频率低）
            continent = octave_perlin(x / 30.0, y / 30.0, octaves=3, seed=seed)
            # 中尺度：山脉盆地
            mountains = octave_perlin(x / 10.0, y / 10.0, octaves=4, seed=seed + 1) * 0.5
            # 小尺度：细节
            detail = octave_perlin(x / 3.0, y / 3.0, octaves=2, seed=seed + 2) * 0.2
            
            combined = continent + mountains + detail
            # 归一化到[0,1]
            normalized = (combined + 1.0) / 2.0
            row.append(normalized)
        height_map.append(row)
    
    # 第二步：生成地块（符合地球实际海洋深度分布）
    for y in range(height):
        latitude = 1 - (y / (height - 1)) if height > 1 else 0.5
        for x in range(width):
            longitude = x / (width - 1) if width > 1 else 0.5
            normalized = height_map[y][x]
            
            # 海陆分布：60%海洋，40%陆地
            if normalized < 0.6:
                # 海洋深度分布（模拟地球实际分布）
                ocean_val = normalized / 0.6  # 归一化到[0,1]
                
                if ocean_val < 0.15:
                    # 极深海沟（6000-11000m）：约10%的海洋
                    depth_in_range = ocean_val / 0.15
                    elevation = -11000 + depth_in_range * 5000  # -11000到-6000m
                elif ocean_val < 0.65:
                    # 深海平原（3000-6000m）：约50%的海洋
                    depth_in_range = (ocean_val - 0.15) / 0.5
                    elevation = -6000 + depth_in_range * 3000  # -6000到-3000m
                elif ocean_val < 0.85:
                    # 大陆坡（200-3000m）：约20%的海洋
                    depth_in_range = (ocean_val - 0.65) / 0.2
                    elevation = -3000 + depth_in_range * 2800  # -3000到-200m
                else:
                    # 浅海大陆架（0-200m）：约15%的海洋
                    depth_in_range = (ocean_val - 0.85) / 0.15
                    elevation = -200 + depth_in_range * 200  # -200到0m
            else:
                # 陆地（40%）
                land_height = (normalized - 0.6) / 0.4
                
                if land_height < 0.6:
                    # 平原（0-200m）：约60%的陆地
                    elevation = land_height * 333  # 0-200m
                elif land_height < 0.85:
                    # 丘陵和低山（200-1500m）：约25%的陆地
                    elevation = 200 + (land_height - 0.6) * 5200  # 200-1500m
                elif land_height < 0.96:
                    # 山地（1500-4000m）：约11%的陆地
                    elevation = 1500 + ((land_height - 0.85) / 0.11) ** 1.5 * 2500  # 1500-4000m
                else:
                    # 高山（4000-8848m）：约4%的陆地
                    elevation = 4000 + ((land_height - 0.96) / 0.04) ** 2.2 * 4848  # 4000-8848m
            
            # 生成温度和湿度
            temperature = 35 - abs(latitude - 0.5) * 70 - (elevation / 100 if elevation > 0 else 0)
            humidity = max(0.0, min(1.0, 0.5 + 0.3 * math.sin(2 * math.pi * longitude) - 0.2 * abs(latitude - 0.5)))
            
            # 推断生物群系（使用相对海拔）
            current_sea_level = 0.0  # 初始海平面为0
            relative_elev = elevation - current_sea_level
            if relative_elev < -3000:
                biome = "深海"
                cover = "水域"
            elif relative_elev < -200:
                biome = "浅海"
                cover = "水域"
            elif relative_elev < 0:
                biome = "海岸"
                cover = "水域"
            elif relative_elev > 5000:
                biome = "极高山"
                cover = "冰川"
            elif relative_elev > 3000:
                biome = "高山"
                cover = "冰川"
            elif relative_elev > 1000:
                biome = "山地"
                cover = "裸地"
            elif relative_elev > 200:
                biome = "丘陵"
                cover = "草甸"
            else:
                if temperature > 25 and humidity > 0.6:
                    biome = "雨林"
                    cover = "森林"
                elif temperature > 20 and humidity <= 0.6:
                    biome = "草原"
                    cover = "草甸"
                elif temperature < 0:
                    biome = "冻原"
                    cover = "苔原"
                elif humidity < 0.2:
                    biome = "荒漠"
                    cover = "沙漠"
                else:
                    biome = "温带森林"
                    cover = "森林"
            
            tile = MapTile(
                id=y * width + x + 1,
                x=x,
                y=y,
                q=x - (y - (y & 1)) // 2,
                r=y,
                biome=biome,
                elevation=elevation,
                cover=cover,
                temperature=temperature,
                humidity=humidity,
                resources=random.uniform(0.3, 0.9),
                has_river=False,
                pressures={},
            )
            tiles.append(tile)
    
    return tiles


def create_test_pressures(turn: int) -> list[ParsedPressure]:
    """创建测试压力"""
    pressures = []
    
    # 每3回合施加一次压力
    if turn % 3 == 1:
        # 火山活动
        pressures.append(ParsedPressure(
            kind="volcanic",
            intensity=7,
            affected_tiles=list(range(1000, 1100)),  # 模拟火山区
            narrative="赤道带发生火山活动"
        ))
    elif turn % 3 == 2:
        # 温度变化
        pressures.append(ParsedPressure(
            kind="temperature",
            intensity=5,
            affected_tiles=[],  # 全球影响
            narrative="全球温度上升"
        ))
    
    return pressures


def print_terrain_summary(tiles: list[MapTile], turn: int, log_func=print):
    """打印地形摘要"""
    from collections import Counter
    
    log_func(f"\n{'='*80}")
    log_func(f"  回合 {turn} 地形统计")
    log_func(f"{'='*80}")
    
    elevations = [t.elevation for t in tiles]
    biomes = Counter(t.biome for t in tiles)
    
    log_func(f"  总地块数: {len(tiles)}")
    log_func(f"  平均海拔: {sum(elevations)/len(elevations):.1f}m")
    log_func(f"  最高海拔: {max(elevations):.1f}m")
    log_func(f"  最低海拔: {min(elevations):.1f}m")
    log_func(f"\n  生物群系分布:")
    for biome, count in biomes.most_common():
        log_func(f"    {biome}: {count}块 ({count/len(tiles)*100:.1f}%)")
    log_func(f"{'='*80}\n")


def main():
    """主测试函数"""
    # 创建报告文件
    reports_dir = Path(__file__).parent.parent / "data/reports"
    reports_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = reports_dir / f"terrain_evolution_test_{timestamp}.txt"
    
    def log(msg):
        """同时打印到控制台和文件"""
        print(msg)
        with open(report_file, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    
    log("="*80)
    log("  地形演化AI推演测试")
    log("="*80)
    
    # 1. 加载配置
    log("\n[1] 加载配置...")
    settings = load_settings()
    log(f"  AI Provider: {settings.get('ai_provider')}")
    log(f"  AI Model: {settings.get('ai_model')}")
    log(f"  Base URL: {settings.get('ai_base_url')}")
    
    # 2. 初始化数据库
    log("\n[2] 初始化数据库...")
    init_db()
    log("  数据库初始化完成")
    
    # 清理旧数据，确保测试从干净状态开始
    log("\n[2.1] 清理旧测试数据...")
    from app.core.database import engine
    from sqlmodel import Session, delete
    from app.models.environment import MapTile, MapState, TerrainEvolutionHistory
    
    with Session(engine) as session:
        session.exec(delete(TerrainEvolutionHistory))
        session.exec(delete(MapTile))
        session.exec(delete(MapState))
        session.commit()
    log("  旧数据清理完成")
    
    # 3. 创建ModelRouter
    log("\n[3] 初始化AI Router...")
    router = ModelRouter(
        {"terrain_evolution": ModelConfig(provider="openai", model=settings.get("ai_model"))},
        base_url=settings.get("ai_base_url"),
        api_key=settings.get("ai_api_key"),
        timeout=settings.get("ai_timeout", 60),
    )
    log("  AI Router初始化完成")
    
    # 4. 创建地形演化服务和地图演化服务
    log("\n[4] 创建演化服务...")
    terrain_service = TerrainEvolutionService(router)
    map_evolution_service = MapEvolutionService(width=80, height=40)
    log("  演化服务创建完成")
    
    # 5. 创建测试地图
    log("\n[5] 生成测试地图...")
    tiles = create_test_map(width=80, height=40)
    log(f"  生成了 {len(tiles)} 个地块")
    
    # 保存到数据库
    environment_repository.upsert_tiles(tiles)
    log("  地图已保存到数据库")
    
    # 6. 创建初始地图状态（与MapEvolutionService保持一致）
    log("\n[6] 创建初始地图状态...")
    initial_state = MapState(
        turn_index=0,
        stage_name="稳定期",
        stage_progress=0,
        stage_duration=map_evolution_service.stage_duration,  # 使用MapEvolutionService的初始持续时间
        sea_level=0.0,
        global_avg_temperature=15.0,
    )
    environment_repository.save_state(initial_state)
    log(f"  地图状态已保存（初始阶段: {initial_state.stage_name}, 持续: {initial_state.stage_duration}回合）")
    
    # 打印初始地形
    print_terrain_summary(tiles, 0, log)
    
    # 7. 进行10轮推演
    log("\n" + "="*80)
    log("  开始10轮地形演化推演")
    log("="*80 + "\n")
    
    for turn in range(1, 11):
        log(f"\n{'#'*80}")
        log(f"  第 {turn} 回合开始")
        log(f"{'#'*80}")
        
        # 获取当前状态
        current_state = environment_repository.get_state()
        prev_state = current_state  # 简化处理
        
        # 推进板块阶段
        log(f"\n  推进板块阶段...")
        map_evolution_service.advance([], turn, {}, current_state)
        current_stage = map_evolution_service.current_stage()
        
        # MapState已在advance中更新，只需保存
        environment_repository.save_state(current_state)
        
        log(f"  当前阶段: {current_state.stage_name} ({current_state.stage_progress}/{current_state.stage_duration})")
        log(f"  阶段描述: {current_stage.description}")
        
        # 创建压力
        pressures = create_test_pressures(turn)
        if pressures:
            log(f"\n  本回合压力:")
            for p in pressures:
                log(f"    - {p.kind} (强度{p.intensity}): {p.narrative}")
        else:
            log(f"\n  本回合无压力事件")
        
        # 执行演化
        try:
            log(f"\n  调用AI进行地形演化...")
            updated_tiles, terrain_events = terrain_service.evolve_terrain(
                tiles=tiles,
                pressures=pressures,
                map_state=current_state,
                prev_state=prev_state,
                turn_index=turn,
            )
            
            # 更新地块
            if updated_tiles:
                environment_repository.upsert_tiles(updated_tiles)
                # 重新加载所有地块以反映变化
                tiles = environment_repository.list_tiles()
                log(f"\n  [OK] 演化完成，更新了 {len(updated_tiles)} 个地块")
            else:
                log(f"\n  [OK] 演化完成，无地形变化")

            if terrain_events:
                log("\n  [AI地形事件]")
                for event in terrain_events:
                    log(f"    - {event.stage}: {event.description}（{event.affected_region}）")
            
            # 更新地图状态
            current_state.turn_index = turn
            environment_repository.save_state(current_state)
            
            # 打印地形摘要
            print_terrain_summary(tiles, turn, log)
            
        except Exception as e:
            log(f"\n  [ERROR] 第 {turn} 回合失败: {e}")
            import traceback
            traceback.print_exc()
            log(f"\n  继续下一回合...")
    
    # 8. 测试总结
    log("\n" + "="*80)
    log("  测试完成！")
    log("="*80)
    log(f"\n  已完成10轮地形演化推演")
    log(f"  报告已保存到: {report_file}")
    log(f"  请检查输出，判断地质演化是否符合常理")
    log(f"\n  关注点:")
    log(f"    1. 板块阶段是否驱动相应的地形变化")
    log(f"    2. 火山活动是否导致局部海拔上升")
    log(f"    3. 持续过程是否合理延续")
    log(f"    4. 地形变化的幅度是否符合50万年时间尺度")
    log(f"    5. AI分析是否符合地质学逻辑")
    log(f"\n{'='*80}\n")


if __name__ == "__main__":
    main()
