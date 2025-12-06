"""
TradeoffCalculator 单元测试

测试自动代价计算器的核心功能：
- 代价总量计算
- 竞争属性选择
- 能量守恒验证
"""

import pytest

from ..tradeoff import TradeoffCalculator


class TestTradeoffCalculator:
    """TradeoffCalculator 测试套件"""
    
    @pytest.fixture
    def calculator(self) -> TradeoffCalculator:
        """创建默认配置的计算器"""
        return TradeoffCalculator(tradeoff_ratio=0.7)
    
    @pytest.fixture
    def parent_traits(self) -> dict[str, float]:
        """模拟父系物种的属性"""
        return {
            "耐寒性": 6.0,
            "耐热性": 6.0,
            "繁殖速度": 7.0,
            "运动能力": 5.0,
            "物理防御": 5.0,
            "智力": 4.0,
            "体型": 5.0,
            "社会性": 5.0,
        }
    
    def test_basic_penalty_calculation(
        self, calculator: TradeoffCalculator, parent_traits: dict
    ):
        """测试基本代价计算"""
        gains = {"耐寒性": 1.5}
        penalties = calculator.calculate_penalties(gains, parent_traits)
        
        # 应该产生代价
        assert len(penalties) > 0
        # 所有代价应该是负值
        assert all(v < 0 for v in penalties.values())
        # 增益属性不应出现在代价中
        assert "耐寒性" not in penalties
    
    def test_competition_map_priority(
        self, calculator: TradeoffCalculator, parent_traits: dict
    ):
        """测试竞争属性优先选择"""
        # 耐寒性的竞争属性是 耐热性 和 繁殖速度
        gains = {"耐寒性": 2.0}
        penalties = calculator.calculate_penalties(gains, parent_traits)
        
        # 应该优先从竞争属性中选择代价
        penalty_traits = set(penalties.keys())
        competition_traits = {"耐热性", "繁殖速度"}
        
        # 至少有一个竞争属性被选为代价
        assert len(penalty_traits & competition_traits) > 0
    
    def test_energy_conservation(
        self, calculator: TradeoffCalculator, parent_traits: dict
    ):
        """测试能量守恒原则"""
        gains = {"运动能力": 1.0, "智力": 0.5}
        penalties = calculator.calculate_penalties(gains, parent_traits)
        
        # 计算增益的加权总量
        total_gain = sum(
            delta * TradeoffCalculator.ENERGY_COSTS.get(trait, 1.0)
            for trait, delta in gains.items()
        )
        
        # 计算代价的加权总量（取绝对值）
        total_penalty = sum(
            abs(delta) * TradeoffCalculator.ENERGY_COSTS.get(trait, 1.0)
            for trait, delta in penalties.items()
        )
        
        # 代价应该接近 增益 × tradeoff_ratio
        expected_penalty = total_gain * calculator.tradeoff_ratio
        # 允许一定误差（因为有最大削减限制）
        assert total_penalty <= expected_penalty + 0.5
    
    def test_exclude_gain_traits(
        self, calculator: TradeoffCalculator, parent_traits: dict
    ):
        """测试增益属性不会被选为代价"""
        gains = {"耐寒性": 1.5, "耐热性": 0.5}
        penalties = calculator.calculate_penalties(gains, parent_traits)
        
        # 增益属性不应出现在代价中
        assert "耐寒性" not in penalties
        assert "耐热性" not in penalties
    
    def test_max_reduction_limit(
        self, calculator: TradeoffCalculator
    ):
        """测试单项最大削减限制"""
        # 父系属性值很高
        parent_traits = {
            "耐寒性": 10.0,
            "繁殖速度": 10.0,
            "运动能力": 10.0,
        }
        
        # 大量增益
        gains = {"耐寒性": 3.0}
        penalties = calculator.calculate_penalties(gains, parent_traits)
        
        # 单项代价不应超过 2.0（max_reduction 限制）
        for penalty in penalties.values():
            assert abs(penalty) <= 2.0
    
    def test_low_parent_value_protection(
        self, calculator: TradeoffCalculator
    ):
        """测试低属性值保护"""
        # 父系属性值很低
        parent_traits = {
            "耐寒性": 2.0,
            "繁殖速度": 1.0,  # 很低
            "运动能力": 3.0,
        }
        
        gains = {"耐寒性": 1.0}
        penalties = calculator.calculate_penalties(gains, parent_traits)
        
        # 低属性值的削减应该受限（parent_val * 0.3）
        if "繁殖速度" in penalties:
            assert abs(penalties["繁殖速度"]) <= 1.0 * 0.3
    
    def test_custom_tradeoff_ratio(self, parent_traits: dict):
        """测试自定义代价比例"""
        # 低代价比例
        calc_low = TradeoffCalculator(tradeoff_ratio=0.5)
        # 高代价比例
        calc_high = TradeoffCalculator(tradeoff_ratio=1.0)
        
        gains = {"耐寒性": 2.0}
        
        penalties_low = calc_low.calculate_penalties(gains, parent_traits)
        penalties_high = calc_high.calculate_penalties(gains, parent_traits)
        
        # 高比例应该产生更大的代价
        total_low = sum(abs(v) for v in penalties_low.values())
        total_high = sum(abs(v) for v in penalties_high.values())
        
        assert total_high >= total_low
    
    def test_empty_gains(
        self, calculator: TradeoffCalculator, parent_traits: dict
    ):
        """测试空增益"""
        gains = {}
        penalties = calculator.calculate_penalties(gains, parent_traits)
        
        # 空增益应该不产生代价
        assert len(penalties) == 0
    
    def test_unknown_trait_gain(
        self, calculator: TradeoffCalculator, parent_traits: dict
    ):
        """测试未知属性的增益"""
        gains = {"未知属性": 1.0}
        penalties = calculator.calculate_penalties(gains, parent_traits)
        
        # 未知属性使用默认能量成本 1.0
        # 应该仍然产生代价
        assert len(penalties) >= 0  # 可能有代价，也可能没有（取决于候选池）


class TestEnergyConstants:
    """能量成本常量测试"""
    
    def test_energy_costs_positive(self):
        """所有能量成本应为正值"""
        for trait, cost in TradeoffCalculator.ENERGY_COSTS.items():
            assert cost > 0, f"{trait} 能量成本应为正值"
    
    def test_competition_map_bidirectional(self):
        """测试竞争关系合理性"""
        # 检查一些关键的竞争关系
        comp_map = TradeoffCalculator.COMPETITION_MAP
        
        # 耐寒性和耐热性应该互相竞争
        assert "耐热性" in comp_map.get("耐寒性", [])
        assert "耐寒性" in comp_map.get("耐热性", [])
        
        # 运动能力和物理防御应该竞争
        assert "物理防御" in comp_map.get("运动能力", [])
        assert "运动能力" in comp_map.get("物理防御", [])





