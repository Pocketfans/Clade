#!/usr/bin/env python
"""运行板块构造系统测试

使用方式:
    cd backend
    python -m app.services.tectonic.tests.run_tests
"""

import sys
import os

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def run_quick_test():
    """快速验证测试（不使用pytest）"""
    print("=" * 60)
    print("板块构造系统 - 快速验证测试")
    print("=" * 60)
    
    try:
        # 导入模块
        print("\n[1/7] 导入模块...")
        from app.services.tectonic import TectonicSystem
        from app.services.tectonic.plate_generator import PlateGenerator
        from app.services.tectonic.motion_engine import PlateMotionEngine
        from app.services.tectonic.geological_features import GeologicalFeatureDistributor
        from app.services.tectonic.matrix_engine import TectonicMatrixEngine
        from app.services.tectonic.species_tracker import PlateSpeciesTracker, SimpleSpecies, SimpleHabitat
        from app.services.tectonic.models import Plate, PlateType, BoundaryType
        print("   ✓ 模块导入成功")
        
        # 测试板块生成
        print("\n[2/7] 测试板块生成...")
        generator = PlateGenerator(64, 20)
        plates, plate_map, tiles = generator.generate(seed=42)
        assert len(plates) > 0, "应该生成板块"
        assert plate_map.shape == (20, 64), "板块地图尺寸错误"
        assert len(tiles) == 64 * 20, "地块数量错误"
        print(f"   ✓ 生成了 {len(plates)} 个板块，{len(tiles)} 个地块")
        
        # 测试边界检测
        print("\n[3/7] 测试边界检测...")
        engine = PlateMotionEngine(64, 20)
        boundary_info = engine._detect_boundaries(plates, plate_map, tiles)
        boundary_tiles = [t for t in tiles if t.boundary_type != BoundaryType.INTERNAL]
        assert len(boundary_tiles) > 0, "应该检测到边界"
        print(f"   ✓ 检测到 {len(boundary_tiles)} 个边界地块")
        
        # 测试地质特征
        print("\n[4/7] 测试地质特征分布...")
        distributor = GeologicalFeatureDistributor(64, 20)
        features = distributor.initialize(plates, plate_map, tiles, seed=42)
        print(f"   ✓ 生成了 {len(features['volcanoes'])} 个火山，{len(features['hotspots'])} 个热点")
        
        # 测试矩阵引擎
        print("\n[5/7] 测试矩阵计算引擎...")
        matrix_engine = TectonicMatrixEngine(64, 20)
        matrix_engine.build(tiles, plates, plate_map)
        assert matrix_engine.plate_assignment is not None, "板块分配矩阵应该存在"
        print("   ✓ 矩阵构建成功")
        
        # 测试完整系统
        print("\n[6/7] 测试完整系统...")
        system = TectonicSystem(width=64, height=20, seed=42)
        result = system.step()
        assert result.turn_index == 1, "回合数应该增加"
        print(f"   ✓ 执行了 1 回合，地形变化 {len(result.terrain_changes)} 处，事件 {len(result.events)} 个")
        
        # 测试多回合
        print("\n[7/7] 测试多回合执行...")
        for i in range(5):
            result = system.step(pressure_modifiers={"volcanic_eruption": 3})
        stats = system.get_statistics()
        print(f"   ✓ 执行了 {stats['turn_index']} 回合")
        print(f"   ✓ 陆地比例: {stats['land_ratio']:.1%}")
        print(f"   ✓ 海拔范围: {stats['elevation']['min']:.0f}m ~ {stats['elevation']['max']:.0f}m")
        
        print("\n" + "=" * 60)
        print("✓ 所有快速验证测试通过！")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_pytest():
    """使用pytest运行完整测试"""
    import pytest
    
    # 获取测试目录
    test_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 运行测试
    exit_code = pytest.main([
        test_dir,
        "-v",
        "--tb=short",
        "-x",  # 遇到第一个失败就停止
    ])
    
    return exit_code == 0


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="运行板块构造系统测试")
    parser.add_argument("--quick", action="store_true", help="只运行快速验证测试")
    parser.add_argument("--full", action="store_true", help="运行完整pytest测试")
    
    args = parser.parse_args()
    
    # 切换到backend目录
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
    os.chdir(backend_dir)
    
    if args.quick or not args.full:
        success = run_quick_test()
    else:
        success = run_pytest()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()




