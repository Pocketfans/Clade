"""
HybridCompute 混合计算测试

测试 NumPy + Taichi 分工协作的正确性和性能。
"""

import numpy as np
import pytest

from ..hybrid import HybridCompute, get_compute, reset_compute


class TestHybridCompute:
    """混合计算测试套件"""
    
    @pytest.fixture
    def compute(self) -> HybridCompute:
        """创建计算实例"""
        return HybridCompute(arch="cpu")  # 测试用 CPU
    
    @pytest.fixture
    def test_data(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """测试数据"""
        S, H, W = 5, 20, 20
        
        pop = np.random.rand(S, H, W).astype(np.float32) * 100
        pop[pop < 20] = 0  # 一些空格
        
        env = np.zeros((5, H, W), dtype=np.float32)
        env[0] = np.random.rand(H, W) * 1000  # 海拔
        env[1] = np.random.rand(H, W) * 40 - 10  # 温度 -10~30
        env[2] = np.random.rand(H, W)  # 湿度
        
        params = np.random.rand(S, 5).astype(np.float32) * 10
        
        return pop, env, params
    
    def test_backend_detection(self, compute: HybridCompute):
        """测试后端检测"""
        assert compute.backend in ("taichi", "numpy")
        print(f"\n当前后端: {compute.backend}")
    
    # ======== Taichi 加速操作测试 ========
    
    def test_mortality_shape(
        self, compute: HybridCompute, test_data: tuple
    ):
        """测试死亡率输出形状"""
        pop, env, params = test_data
        
        mortality = compute.mortality(pop, env, params)
        
        assert mortality.shape == pop.shape
        assert mortality.dtype == np.float32
    
    def test_mortality_range(
        self, compute: HybridCompute, test_data: tuple
    ):
        """测试死亡率值范围"""
        pop, env, params = test_data
        
        mortality = compute.mortality(pop, env, params)
        
        mask = pop > 0
        assert np.all(mortality[mask] >= 0.01)
        assert np.all(mortality[mask] <= 0.99)
        assert np.all(mortality[~mask] == 0)
    
    def test_diffusion_conservation(
        self, compute: HybridCompute, test_data: tuple
    ):
        """测试扩散质量守恒"""
        pop, _, _ = test_data
        
        new_pop = compute.diffusion(pop, rate=0.1)
        
        # 内部区域应该守恒（边界有损失）
        original_total = pop.sum()
        new_total = new_pop.sum()
        
        # 允许 5% 误差
        assert abs(new_total - original_total) / original_total < 0.05
    
    def test_apply_mortality(
        self, compute: HybridCompute, test_data: tuple
    ):
        """测试应用死亡率"""
        pop, _, _ = test_data
        mortality = np.ones_like(pop) * 0.3
        
        new_pop = compute.apply_mortality(pop, mortality)
        
        np.testing.assert_allclose(new_pop, pop * 0.7, rtol=1e-5)
    
    def test_reproduction(
        self, compute: HybridCompute, test_data: tuple
    ):
        """测试繁殖"""
        pop, _, _ = test_data
        fitness = np.ones_like(pop) * 0.8
        capacity = np.ones((pop.shape[1], pop.shape[2])) * 500
        
        new_pop = compute.reproduction(pop, fitness, capacity, birth_rate=0.1)
        
        # 种群应该增长（在承载力内）
        assert new_pop.sum() >= pop.sum()
    
    def test_competition(
        self, compute: HybridCompute, test_data: tuple
    ):
        """测试竞争"""
        pop, _, _ = test_data
        fitness = np.ones_like(pop) * 0.5
        
        new_pop = compute.competition(pop, fitness, strength=0.01)
        
        # 竞争应该导致种群减少
        assert new_pop.sum() <= pop.sum()
    
    # ======== NumPy 简单操作测试 ========
    
    def test_sum_population(
        self, compute: HybridCompute, test_data: tuple
    ):
        """测试种群求和"""
        pop, _, _ = test_data
        
        totals = compute.sum_population(pop)
        
        assert totals.shape == (pop.shape[0],)
        expected = pop.sum(axis=(1, 2))
        np.testing.assert_allclose(totals, expected)
    
    def test_filter_alive(
        self, compute: HybridCompute, test_data: tuple
    ):
        """测试筛选存活物种"""
        pop, _, _ = test_data
        
        alive = compute.filter_alive(pop, threshold=100)
        
        assert isinstance(alive, list)
        for idx in alive:
            assert pop[idx].sum() >= 100
    
    def test_get_presence_mask(
        self, compute: HybridCompute, test_data: tuple
    ):
        """测试存在掩码"""
        pop, _, _ = test_data
        
        mask = compute.get_presence_mask(pop)
        
        assert mask.shape == pop.shape
        assert mask.dtype == bool
        assert np.array_equal(mask, pop > 0)
    
    def test_normalize_population(
        self, compute: HybridCompute, test_data: tuple
    ):
        """测试归一化"""
        pop, _, _ = test_data
        
        normalized = compute.normalize_population(pop)
        
        # 每个物种最大值应该是 1
        for s in range(pop.shape[0]):
            if pop[s].max() > 0:
                assert np.isclose(normalized[s].max(), 1.0)


class TestGlobalCompute:
    """全局计算实例测试"""
    
    def test_singleton(self):
        """测试单例模式"""
        reset_compute()
        
        c1 = get_compute()
        c2 = get_compute()
        
        assert c1 is c2
    
    def test_reset(self):
        """测试重置"""
        c1 = get_compute()
        reset_compute()
        c2 = get_compute()
        
        assert c1 is not c2


class TestPerformance:
    """性能测试"""
    
    def test_large_scale(self):
        """大规模计算测试"""
        import time
        
        compute = HybridCompute(arch="cpu")
        
        # 大规模数据
        S, H, W = 50, 256, 256
        pop = np.random.rand(S, H, W).astype(np.float32) * 100
        env = np.zeros((5, H, W), dtype=np.float32)
        env[1] = np.random.rand(H, W) * 40
        params = np.random.rand(S, 5).astype(np.float32) * 10
        
        # 预热
        compute.mortality(pop, env, params)
        compute.diffusion(pop)
        
        # 计时
        iterations = 10
        
        start = time.perf_counter()
        for _ in range(iterations):
            compute.mortality(pop, env, params)
        mortality_time = (time.perf_counter() - start) * 1000 / iterations
        
        start = time.perf_counter()
        for _ in range(iterations):
            compute.diffusion(pop)
        diffusion_time = (time.perf_counter() - start) * 1000 / iterations
        
        print(f"\n后端: {compute.backend}")
        print(f"规模: ({S}, {H}, {W})")
        print(f"死亡率: {mortality_time:.2f} ms")
        print(f"扩散: {diffusion_time:.2f} ms")





