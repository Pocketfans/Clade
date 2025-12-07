"""
张量系统回合级集成测试

测试张量系统各组件在模拟完整回合中的协同工作：
- TensorState 构建与传递
- SpeciationMonitor 分化检测
- TradeoffCalculator 代价计算
- TensorMetricsCollector 指标收集
"""

import numpy as np
import pytest

from ..config import TensorConfig
from ..metrics import TensorMetricsCollector
from ..speciation_monitor import SpeciationMonitor
from ..state import TensorState
from ..tradeoff import TradeoffCalculator


class TestTensorSystemIntegration:
    """张量系统集成测试套件"""
    
    @pytest.fixture
    def config(self) -> TensorConfig:
        """默认张量配置"""
        return TensorConfig.default()
    
    @pytest.fixture
    def metrics_collector(self) -> TensorMetricsCollector:
        """指标收集器"""
        return TensorMetricsCollector()
    
    @pytest.fixture
    def simple_world(self) -> TensorState:
        """简单的模拟世界
        
        10x10 地图，3个物种：
        - SP001: 分布在左侧 (x < 5)
        - SP002: 分布在右侧 (x >= 5)
        - SP003: 分布在中间带 (3 <= x <= 6)
        """
        # 环境张量: 5通道 (海拔、温度、湿度、辐射、植被)
        env = np.zeros((5, 10, 10), dtype=np.float32)
        # 海拔：东高西低
        for x in range(10):
            env[0, :, x] = x * 100  # 0-900米
        # 温度：西热东冷
        for x in range(10):
            env[1, :, x] = 30 - x * 2  # 30-12°C
        # 湿度：均匀
        env[2, :, :] = 0.5
        # 辐射：均匀
        env[3, :, :] = 0.3
        # 植被：中间高
        for x in range(10):
            env[4, :, x] = 0.3 + 0.4 * (1 - abs(x - 5) / 5)
        
        # 种群张量: 3物种
        pop = np.zeros((3, 10, 10), dtype=np.float32)
        # SP001: 西部
        pop[0, :, :5] = 100.0
        # SP002: 东部
        pop[1, :, 5:] = 80.0
        # SP003: 中间
        pop[2, :, 3:7] = 60.0
        
        # 物种参数: 简化为 5 个特质
        species_params = np.array([
            [6.0, 4.0, 7.0, 5.0, 5.0],  # SP001: 耐热
            [4.0, 6.0, 5.0, 5.0, 5.0],  # SP002: 耐寒
            [5.0, 5.0, 6.0, 5.0, 5.0],  # SP003: 平衡
        ], dtype=np.float32)
        
        return TensorState(
            env=env,
            pop=pop,
            species_params=species_params,
            masks={"land": np.ones((10, 10), dtype=bool)},
            species_map={"SP001": 0, "SP002": 1, "SP003": 2},
        )
    
    @pytest.fixture
    def isolated_world(self) -> TensorState:
        """有地理隔离的世界
        
        物种分布被山脉分隔
        """
        env = np.zeros((5, 10, 10), dtype=np.float32)
        env[0, :, :] = 100  # 基础海拔
        env[0, :, 4:6] = 2000  # 中间山脉
        env[1, :, :] = 20  # 温度
        
        pop = np.zeros((2, 10, 10), dtype=np.float32)
        # SP001: 被山脉分成两部分
        pop[0, :, :4] = 100.0  # 西侧
        pop[0, :, 6:] = 100.0  # 东侧
        # 注意：中间 4:6 列没有种群（山脉阻隔）
        
        species_params = np.array([
            [5.0, 5.0, 5.0, 5.0, 5.0],
            [5.0, 5.0, 5.0, 5.0, 5.0],
        ], dtype=np.float32)
        
        return TensorState(
            env=env,
            pop=pop,
            species_params=species_params,
            masks={},
            species_map={"SP001": 0, "SP002": 1},
        )
    
    def test_full_turn_simulation(
        self,
        config: TensorConfig,
        simple_world: TensorState,
        metrics_collector: TensorMetricsCollector,
    ):
        """测试完整回合的张量计算流程"""
        # 1. 验证 TensorState
        simple_world.ensure_shapes()
        assert simple_world.pop.shape == (3, 10, 10)
        assert simple_world.env.shape == (5, 10, 10)
        
        # 2. 分化检测
        monitor = SpeciationMonitor(simple_world.species_map)
        
        with metrics_collector.track_speciation_detection():
            triggers = monitor.get_speciation_triggers(
                simple_world, threshold=config.divergence_threshold
            )
        
        # SP003 跨越温度梯度，可能有分歧触发
        # 由于覆盖中间区域环境差异较小，可能没有触发
        metrics_collector.record_tensor_trigger(len(triggers))
        
        # 3. 代价计算（模拟一次分化）
        calculator = TradeoffCalculator(tradeoff_ratio=config.tradeoff_ratio)
        
        gains = {"耐寒性": 1.5, "运动能力": 0.5}
        parent_traits = {"耐寒性": 5.0, "繁殖速度": 7.0, "运动能力": 5.0, "耐热性": 5.0}
        
        with metrics_collector.track_tradeoff():
            penalties = calculator.calculate_penalties(gains, parent_traits)
        
        # 验证代价计算结果
        assert len(penalties) > 0
        assert all(v < 0 for v in penalties.values())
        
        # 4. 结束回合，检查指标
        turn_metrics = metrics_collector.end_turn(turn=1)
        
        assert turn_metrics.speciation_detection_time_ms > 0
        assert turn_metrics.tradeoff_time_ms > 0
    
    def test_isolation_detection_flow(
        self,
        isolated_world: TensorState,
        metrics_collector: TensorMetricsCollector,
    ):
        """测试地理隔离检测流程"""
        monitor = SpeciationMonitor(isolated_world.species_map)
        
        with metrics_collector.track_speciation_detection():
            isolation = monitor.detect_isolation(isolated_world.pop)
        
        # SP001 应该被检测到隔离
        assert "SP001" in isolation
        assert len(isolation["SP001"]) == 2  # 两个分离区域
        
        metrics_collector.record_isolation_detection(len(isolation))
        metrics_collector.record_tensor_trigger(len(isolation))
        
        turn_metrics = metrics_collector.end_turn()
        assert turn_metrics.isolation_detections == 1
        assert turn_metrics.tensor_triggers == 1
    
    def test_divergence_detection_flow(
        self,
        simple_world: TensorState,
        metrics_collector: TensorMetricsCollector,
    ):
        """测试环境分歧检测流程"""
        monitor = SpeciationMonitor(simple_world.species_map)
        
        with metrics_collector.track_speciation_detection():
            divergence = monitor.detect_divergence(
                simple_world.pop, simple_world.env
            )
        
        # 所有物种都应该有分歧得分
        assert "SP001" in divergence
        assert "SP002" in divergence
        assert "SP003" in divergence
        
        # 检查分歧得分范围
        for score in divergence.values():
            assert 0 <= score <= 1.0
        
        # 记录高分歧物种
        high_divergence = sum(1 for s in divergence.values() if s >= 0.3)
        metrics_collector.record_divergence_detection(high_divergence)
        
        turn_metrics = metrics_collector.end_turn()
        assert turn_metrics.divergence_detections >= 0
    
    def test_tradeoff_integration(
        self,
        config: TensorConfig,
    ):
        """测试代价计算集成"""
        calculator = TradeoffCalculator(tradeoff_ratio=config.tradeoff_ratio)
        
        # 场景1：单一增益
        gains1 = {"耐寒性": 2.0}
        parent1 = {"耐寒性": 5.0, "耐热性": 5.0, "繁殖速度": 6.0}
        penalties1 = calculator.calculate_penalties(gains1, parent1)
        
        # 耐热性应该是主要代价目标
        assert "耐热性" in penalties1 or "繁殖速度" in penalties1
        
        # 场景2：多重增益
        gains2 = {"运动能力": 1.0, "智力": 0.5}
        parent2 = {"运动能力": 5.0, "智力": 4.0, "繁殖速度": 6.0, "物理防御": 5.0}
        penalties2 = calculator.calculate_penalties(gains2, parent2)
        
        # 应该有更多代价（因为运动能力和智力成本高）
        total_penalty2 = sum(abs(v) for v in penalties2.values())
        total_gain2 = sum(gains2.values())
        
        # 代价应该与增益成比例
        assert total_penalty2 <= total_gain2 * 2  # 宽松检查
    
    def test_metrics_accumulation(
        self,
        simple_world: TensorState,
        config: TensorConfig,
    ):
        """测试多回合指标累积"""
        collector = TensorMetricsCollector()
        monitor = SpeciationMonitor(simple_world.species_map)
        calculator = TradeoffCalculator(tradeoff_ratio=config.tradeoff_ratio)
        
        # 模拟5个回合
        for turn in range(5):
            with collector.track_speciation_detection():
                triggers = monitor.get_speciation_triggers(simple_world)
            
            collector.record_tensor_trigger(len(triggers))
            
            # 每回合一次代价计算
            with collector.track_tradeoff():
                calculator.calculate_penalties(
                    {"耐寒性": 1.0},
                    {"耐寒性": 5.0, "繁殖速度": 6.0},
                )
            
            collector.end_turn(turn=turn + 1)
        
        # 验证累积统计
        stats = collector.get_statistics()
        assert stats["total_turns"] == 5
        assert stats["avg_time_ms"] > 0
        
        # 验证历史记录
        assert len(collector.history) == 5
    
    def test_config_disabled_mode(self):
        """测试禁用模式"""
        config = TensorConfig.disabled()
        
        assert config.use_tensor_mortality is False
        assert config.use_tensor_speciation is False
        assert config.use_auto_tradeoff is False
        assert config.is_any_enabled() is False
    
    def test_population_slice_access(self, simple_world: TensorState):
        """测试种群切片访问"""
        # 获取 SP001 的分布
        sp001_pop = simple_world.population_slice("SP001")
        assert sp001_pop is not None
        assert sp001_pop.shape == (10, 10)
        
        # 验证分布：左侧有种群，右侧没有
        assert sp001_pop[:, 0].sum() > 0  # 最左列有种群
        assert sp001_pop[:, 9].sum() == 0  # 最右列无种群
        
        # 不存在的物种返回 None
        assert simple_world.population_slice("INVALID") is None


class TestEdgeCases:
    """边界情况测试"""
    
    def test_empty_world(self):
        """测试空世界"""
        state = TensorState(
            env=np.zeros((5, 10, 10), dtype=np.float32),
            pop=np.zeros((0, 10, 10), dtype=np.float32),  # 无物种
            species_params=np.zeros((0, 5), dtype=np.float32),
            species_map={},
        )
        
        monitor = SpeciationMonitor(state.species_map)
        triggers = monitor.get_speciation_triggers(state)
        
        assert len(triggers) == 0
    
    def test_single_cell_population(self):
        """测试单格种群"""
        pop = np.zeros((1, 10, 10), dtype=np.float32)
        pop[0, 5, 5] = 100.0  # 只在一个格子
        
        env = np.ones((3, 10, 10), dtype=np.float32)
        
        state = TensorState(
            env=env,
            pop=pop,
            species_params=np.zeros((1, 5), dtype=np.float32),
            species_map={"SP001": 0},
        )
        
        monitor = SpeciationMonitor(state.species_map)
        
        # 单格不会有隔离
        isolation = monitor.detect_isolation(state.pop)
        assert "SP001" not in isolation
        
        # 单格分歧应该很小
        divergence = monitor.detect_divergence(state.pop, state.env)
        assert divergence.get("SP001", 0) < 0.1
    
    def test_extreme_tradeoff_ratios(self):
        """测试极端代价比例"""
        gains = {"耐寒性": 2.0}
        parent = {"耐寒性": 5.0, "耐热性": 5.0, "繁殖速度": 6.0}
        
        # 低比例
        calc_low = TradeoffCalculator(tradeoff_ratio=0.1)
        penalties_low = calc_low.calculate_penalties(gains, parent)
        
        # 高比例
        calc_high = TradeoffCalculator(tradeoff_ratio=1.0)
        penalties_high = calc_high.calculate_penalties(gains, parent)
        
        # 高比例应该产生更大代价
        total_low = sum(abs(v) for v in penalties_low.values())
        total_high = sum(abs(v) for v in penalties_high.values())
        
        assert total_high >= total_low








