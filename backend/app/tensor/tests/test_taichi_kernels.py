"""
Taichi 内核单元测试

测试 Taichi 加速内核的正确性和性能。
"""

import numpy as np
import pytest

from ..taichi_kernels import TaichiKernels, _taichi_available, benchmark_kernels


class TestTaichiKernels:
    """Taichi 内核测试套件"""
    
    @pytest.fixture
    def kernels(self) -> TaichiKernels:
        """创建内核实例"""
        return TaichiKernels(arch="auto")
    
    @pytest.fixture
    def simple_data(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """简单测试数据"""
        S, H, W = 3, 10, 10
        
        pop = np.zeros((S, H, W), dtype=np.float32)
        pop[0, 2:8, 2:8] = 100.0  # 物种0
        pop[1, 3:7, 3:7] = 50.0   # 物种1
        
        env = np.zeros((5, H, W), dtype=np.float32)
        env[0] = 100  # 海拔
        env[1] = 20   # 温度 (最适温度)
        env[2] = 0.5  # 湿度
        
        params = np.array([
            [5.0, 20.0, 0.5, 5.0, 5.0],  # 物种0
            [5.0, 25.0, 0.5, 5.0, 5.0],  # 物种1
            [5.0, 15.0, 0.5, 5.0, 5.0],  # 物种2
        ], dtype=np.float32)
        
        return pop, env, params
    
    def test_compute_mortality_shape(
        self, kernels: TaichiKernels, simple_data: tuple
    ):
        """测试死亡率输出形状"""
        pop, env, params = simple_data
        
        mortality = kernels.compute_mortality(pop, env, params)
        
        assert mortality.shape == pop.shape
        assert mortality.dtype == np.float32
    
    def test_compute_mortality_range(
        self, kernels: TaichiKernels, simple_data: tuple
    ):
        """测试死亡率值范围"""
        pop, env, params = simple_data
        
        mortality = kernels.compute_mortality(pop, env, params)
        
        # 有种群的地方死亡率应该在 [0.01, 0.99]
        mask = pop > 0
        assert np.all(mortality[mask] >= 0.01)
        assert np.all(mortality[mask] <= 0.99)
        
        # 无种群的地方死亡率应该是 0
        assert np.all(mortality[~mask] == 0)
    
    def test_compute_mortality_temperature_effect(
        self, kernels: TaichiKernels
    ):
        """测试温度对死亡率的影响"""
        S, H, W = 1, 10, 10
        
        pop = np.ones((S, H, W), dtype=np.float32) * 100
        params = np.array([[5.0, 20.0, 0.5, 5.0, 5.0]], dtype=np.float32)
        
        # 最适温度 (20°C)
        env_optimal = np.zeros((5, H, W), dtype=np.float32)
        env_optimal[1] = 20.0
        
        # 极端温度 (40°C)
        env_extreme = np.zeros((5, H, W), dtype=np.float32)
        env_extreme[1] = 40.0
        
        mortality_optimal = kernels.compute_mortality(pop, env_optimal, params, temp_opt=20.0)
        mortality_extreme = kernels.compute_mortality(pop, env_extreme, params, temp_opt=20.0)
        
        # 极端温度应该有更高的死亡率
        assert np.mean(mortality_extreme) > np.mean(mortality_optimal)
    
    def test_diffusion_step_shape(
        self, kernels: TaichiKernels, simple_data: tuple
    ):
        """测试扩散输出形状"""
        pop, _, _ = simple_data
        
        new_pop = kernels.diffusion_step(pop)
        
        assert new_pop.shape == pop.shape
        assert new_pop.dtype == np.float32
    
    def test_diffusion_step_conservation(
        self, kernels: TaichiKernels, simple_data: tuple
    ):
        """测试扩散过程的质量守恒（边界除外）"""
        pop, _, _ = simple_data
        
        # 使用较小的扩散率
        new_pop = kernels.diffusion_step(pop, diffusion_rate=0.1)
        
        # 总种群应该大致守恒（边界会有少量损失）
        original_total = pop.sum()
        new_total = new_pop.sum()
        
        # 允许 5% 的误差（边界损失）
        assert abs(new_total - original_total) / original_total < 0.05
    
    def test_diffusion_step_spreading(
        self, kernels: TaichiKernels
    ):
        """测试扩散导致种群扩散"""
        S, H, W = 1, 20, 20
        
        # 中心点种群
        pop = np.zeros((S, H, W), dtype=np.float32)
        pop[0, 10, 10] = 1000.0
        
        # 执行多步扩散
        current = pop.copy()
        for _ in range(10):
            current = kernels.diffusion_step(current, diffusion_rate=0.2)
        
        # 扩散后，中心应该减少，周围应该增加
        assert current[0, 10, 10] < pop[0, 10, 10]
        assert current[0, 9, 10] > 0  # 邻居有种群
        assert current[0, 10, 9] > 0
    
    def test_apply_mortality(
        self, kernels: TaichiKernels, simple_data: tuple
    ):
        """测试应用死亡率"""
        pop, _, _ = simple_data
        
        # 50% 死亡率
        mortality = np.ones_like(pop) * 0.5
        
        new_pop = kernels.apply_mortality(pop, mortality)
        
        # 种群应该减半
        np.testing.assert_allclose(new_pop, pop * 0.5, rtol=1e-5)
    
    def test_compute_fitness_shape(
        self, kernels: TaichiKernels, simple_data: tuple
    ):
        """测试适应度输出形状"""
        pop, env, params = simple_data
        
        fitness = kernels.compute_fitness(pop, env, params)
        
        assert fitness.shape == pop.shape
        assert fitness.dtype == np.float32
    
    def test_compute_fitness_range(
        self, kernels: TaichiKernels, simple_data: tuple
    ):
        """测试适应度值范围"""
        pop, env, params = simple_data
        
        fitness = kernels.compute_fitness(pop, env, params)
        
        # 适应度应该在 [0, 1]
        assert np.all(fitness >= 0)
        assert np.all(fitness <= 1)
    
    def test_sum_population(
        self, kernels: TaichiKernels, simple_data: tuple
    ):
        """测试种群求和"""
        pop, _, _ = simple_data
        
        totals = kernels.sum_population(pop)
        
        assert totals.shape == (pop.shape[0],)
        
        # 验证正确性
        expected = pop.sum(axis=(1, 2))
        np.testing.assert_allclose(totals, expected, rtol=1e-5)
    
    def test_taichi_numpy_consistency(
        self, simple_data: tuple
    ):
        """测试 Taichi 和 NumPy 结果一致性"""
        pop, env, params = simple_data
        
        # NumPy 版本
        kernels_np = TaichiKernels.__new__(TaichiKernels)
        kernels_np._use_taichi = False
        
        mortality_np = kernels_np.compute_mortality(pop, env, params)
        diffusion_np = kernels_np.diffusion_step(pop)
        fitness_np = kernels_np.compute_fitness(pop, env, params)
        
        # Taichi 版本（如果可用）
        if _taichi_available:
            kernels_ti = TaichiKernels(arch="auto")
            
            if kernels_ti.is_taichi_enabled:
                mortality_ti = kernels_ti.compute_mortality(pop, env, params)
                diffusion_ti = kernels_ti.diffusion_step(pop)
                fitness_ti = kernels_ti.compute_fitness(pop, env, params)
                
                # 结果应该一致（允许浮点误差）
                np.testing.assert_allclose(mortality_ti, mortality_np, rtol=1e-4, atol=1e-6)
                np.testing.assert_allclose(diffusion_ti, diffusion_np, rtol=1e-4, atol=1e-6)
                np.testing.assert_allclose(fitness_ti, fitness_np, rtol=1e-4, atol=1e-6)


class TestBenchmark:
    """性能基准测试"""
    
    def test_benchmark_runs(self):
        """测试基准测试可以运行"""
        results = benchmark_kernels(shape=(5, 32, 32), iterations=10)
        
        assert "numpy" in results
        assert "mortality_ms" in results["numpy"]
        assert results["numpy"]["mortality_ms"] > 0
    
    @pytest.mark.skipif(not _taichi_available, reason="Taichi not available")
    def test_benchmark_taichi(self):
        """测试 Taichi 基准"""
        results = benchmark_kernels(shape=(5, 64, 64), iterations=20)
        
        if "taichi" in results and results["taichi"]:
            assert "mortality_ms" in results["taichi"]
            
            # 检查加速比
            if "speedup" in results:
                print(f"\n加速比 - 死亡率: {results['speedup']['mortality']:.2f}x")
                print(f"加速比 - 扩散: {results['speedup']['diffusion']:.2f}x")








