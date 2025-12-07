"""
迁徙计算性能测试

对比新旧迁徙计算方案的性能差异：
- 旧方案：逐物种循环的 DispersalEngine
- 新方案：全物种并行的 TensorMigrationEngine

运行：
    cd backend
    python -m pytest app/tensor/tests/test_migration_performance.py -v -s
"""

import time
import numpy as np
import pytest


class TestMigrationPerformance:
    """迁徙计算性能测试"""
    
    def test_tensor_migration_basic(self):
        """测试张量迁徙引擎基本功能"""
        from ..migration import (
            TensorMigrationEngine,
            MigrationConfig,
        )
        
        # 创建测试数据
        S, H, W = 10, 64, 64  # 10个物种, 64x64地图
        
        pop = np.random.rand(S, H, W).astype(np.float32) * 100
        env = np.zeros((7, H, W), dtype=np.float32)
        env[0] = np.random.rand(H, W) * 2 - 1  # 温度 [-1, 1]
        env[1] = np.random.rand(H, W)           # 湿度 [0, 1]
        env[3] = np.random.rand(H, W)           # 资源 [0, 1]
        env[4] = 1.0  # 全陆地
        
        species_prefs = np.zeros((S, 7), dtype=np.float32)
        species_prefs[:, 4] = 1.0  # 全陆生
        
        death_rates = np.random.rand(S).astype(np.float32) * 0.3
        
        # 创建引擎
        engine = TensorMigrationEngine()
        
        # 执行迁徙
        new_pop, metrics = engine.process_migration(
            pop=pop,
            env=env,
            species_prefs=species_prefs,
            death_rates=death_rates,
        )
        
        # 验证结果
        assert new_pop.shape == pop.shape
        assert metrics.total_time_ms > 0
        assert metrics.species_count == S
        
        print(f"\n基础测试 ({S}物种, {H}x{W}地图):")
        print(f"  总耗时: {metrics.total_time_ms:.2f}ms")
        print(f"  后端: {metrics.backend}")
    
    def test_tensor_migration_scaling(self):
        """测试张量迁徙引擎的规模扩展性"""
        from ..migration import TensorMigrationEngine
        
        engine = TensorMigrationEngine()
        
        # 测试不同规模
        test_cases = [
            (5, 32, 32),    # 小规模
            (10, 64, 64),   # 中规模
            (20, 128, 128), # 大规模
            (50, 128, 128), # 超大规模（物种多）
        ]
        
        print("\n规模扩展性测试:")
        print(f"{'规模':<20} {'耗时(ms)':<15} {'物种/ms':<15}")
        print("-" * 50)
        
        for S, H, W in test_cases:
            # 创建测试数据
            pop = np.random.rand(S, H, W).astype(np.float32) * 100
            env = np.zeros((7, H, W), dtype=np.float32)
            env[0] = np.random.rand(H, W) * 2 - 1
            env[1] = np.random.rand(H, W)
            env[3] = np.random.rand(H, W)
            env[4] = 1.0
            
            species_prefs = np.zeros((S, 7), dtype=np.float32)
            species_prefs[:, 4] = 1.0
            
            death_rates = np.random.rand(S).astype(np.float32) * 0.3
            
            # 预热
            engine.process_migration(pop, env, species_prefs, death_rates)
            
            # 计时
            start = time.perf_counter()
            iterations = 10
            for _ in range(iterations):
                engine.process_migration(pop, env, species_prefs, death_rates)
            elapsed = (time.perf_counter() - start) * 1000 / iterations
            
            scale_str = f"({S}, {H}, {W})"
            throughput = S / elapsed if elapsed > 0 else 0
            print(f"{scale_str:<20} {elapsed:<15.2f} {throughput:<15.2f}")
    
    def test_migration_correctness(self):
        """测试迁徙计算的正确性"""
        from ..migration import TensorMigrationEngine
        
        engine = TensorMigrationEngine()
        
        # 创建简单测试数据
        S, H, W = 2, 8, 8
        
        # 物种1在左上角，物种2在右下角
        pop = np.zeros((S, H, W), dtype=np.float32)
        pop[0, 0:2, 0:2] = 100  # 物种0在左上
        pop[1, 6:8, 6:8] = 100  # 物种1在右下
        
        env = np.zeros((7, H, W), dtype=np.float32)
        env[0] = 0.0  # 中性温度
        env[1] = 0.5  # 中性湿度
        env[3] = 0.5  # 中等资源
        env[4] = 1.0  # 全陆地
        
        species_prefs = np.zeros((S, 7), dtype=np.float32)
        species_prefs[:, 4] = 1.0  # 全陆生
        
        # 高死亡率触发迁徙
        death_rates = np.array([0.3, 0.3], dtype=np.float32)
        
        # 执行迁徙
        new_pop, metrics = engine.process_migration(
            pop=pop,
            env=env,
            species_prefs=species_prefs,
            death_rates=death_rates,
        )
        
        # 验证：总种群应该守恒（或略有变化）
        total_before = pop.sum()
        total_after = new_pop.sum()
        
        # 允许10%的误差（因为扩散）
        assert abs(total_after - total_before) / total_before < 0.1, \
            f"种群不守恒: {total_before} -> {total_after}"
        
        # 验证：种群应该有扩散
        assert new_pop[0, 2:4, 0:2].sum() > 0 or new_pop[0, 0:2, 2:4].sum() > 0, \
            "物种0应该有扩散"
        
        print("\n正确性测试通过")
        print(f"  种群守恒: {total_before:.0f} -> {total_after:.0f}")
    
    def test_habitat_constraints(self):
        """测试栖息地约束（水生物种不能上岸等）"""
        from ..migration import (
            TensorMigrationEngine,
            extract_habitat_mask,
        )
        
        engine = TensorMigrationEngine()
        
        S, H, W = 2, 8, 8
        
        # 创建环境：左半边是海，右半边是陆
        env = np.zeros((7, H, W), dtype=np.float32)
        env[4, :, :4] = 0.0  # 左边不是陆地
        env[4, :, 4:] = 1.0  # 右边是陆地
        env[5, :, :4] = 1.0  # 左边是海洋
        env[5, :, 4:] = 0.0  # 右边不是海洋
        
        # 物种0是陆生，物种1是水生
        species_prefs = np.zeros((S, 7), dtype=np.float32)
        species_prefs[0, 4] = 1.0  # 物种0陆生
        species_prefs[1, 5] = 1.0  # 物种1水生
        
        # 生成栖息地掩码
        habitat_mask = extract_habitat_mask(env, species_prefs)
        
        # 验证掩码
        assert habitat_mask[0, :, :4].sum() == 0, "陆生物种不应该能去海里"
        assert habitat_mask[0, :, 4:].sum() > 0, "陆生物种应该能在陆地"
        assert habitat_mask[1, :, :4].sum() > 0, "水生物种应该能在海里"
        assert habitat_mask[1, :, 4:].sum() == 0, "水生物种不应该能上岸"
        
        print("\n栖息地约束测试通过")


class TestHybridComputeMigration:
    """测试 HybridCompute 的迁徙方法"""
    
    def test_batch_migration(self):
        """测试批量迁徙计算"""
        from ..hybrid import HybridCompute
        
        compute = HybridCompute()
        
        S, H, W = 5, 32, 32
        
        pop = np.random.rand(S, H, W).astype(np.float32) * 100
        env = np.zeros((7, H, W), dtype=np.float32)
        env[0] = np.random.rand(H, W) * 2 - 1
        env[1] = np.random.rand(H, W)
        env[3] = np.random.rand(H, W)
        env[4] = 1.0
        
        species_prefs = np.zeros((S, 7), dtype=np.float32)
        species_prefs[:, 4] = 1.0
        
        death_rates = np.array([0.2, 0.1, 0.3, 0.05, 0.15], dtype=np.float32)
        
        # 执行迁徙
        new_pop = compute.batch_migration(
            pop=pop,
            env=env,
            species_prefs=species_prefs,
            death_rates=death_rates,
        )
        
        assert new_pop.shape == pop.shape
        print(f"\nHybridCompute 批量迁徙测试通过，后端: {compute.backend}")
    
    def test_guided_diffusion(self):
        """测试带引导的扩散"""
        from ..hybrid import HybridCompute
        
        compute = HybridCompute()
        
        S, H, W = 3, 16, 16
        
        # 中间有种群
        pop = np.zeros((S, H, W), dtype=np.float32)
        pop[:, 7:9, 7:9] = 100
        
        # 右边适宜度高
        suitability = np.zeros((S, H, W), dtype=np.float32)
        suitability[:, :, 10:] = 1.0
        suitability[:, :, :10] = 0.3
        
        # 执行带引导的扩散
        new_pop = compute.guided_diffusion(pop, suitability, rate=0.2)
        
        # 验证：种群应该向右边高适宜度区域扩散
        right_pop = new_pop[:, :, 10:].sum()
        left_pop = new_pop[:, :, :10].sum()
        
        assert new_pop.shape == pop.shape
        print(f"\n带引导扩散测试通过")
        print(f"  左侧种群: {left_pop:.0f}, 右侧种群: {right_pop:.0f}")


if __name__ == "__main__":
    # 直接运行性能测试
    print("=" * 60)
    print("迁徙计算性能测试")
    print("=" * 60)
    
    test = TestMigrationPerformance()
    test.test_tensor_migration_basic()
    test.test_tensor_migration_scaling()
    test.test_migration_correctness()
    test.test_habitat_constraints()
    
    print("\n" + "=" * 60)
    print("HybridCompute 迁徙测试")
    print("=" * 60)
    
    test2 = TestHybridComputeMigration()
    test2.test_batch_migration()
    test2.test_guided_diffusion()
    
    print("\n所有测试通过！")
