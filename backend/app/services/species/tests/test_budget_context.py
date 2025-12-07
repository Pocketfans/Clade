"""测试属性预算系统的增强上下文生成"""

import pytest
from ..trait_config import (
    get_single_trait_cap,
    get_diminishing_factor,
    get_diminishing_summary,
    get_near_breakthroughs,
    get_breakthrough_summary,
    get_habitat_trait_bonus,
    get_organ_trait_bonus,
    get_effective_trait_cap,
    get_bonus_summary,
    TraitConfig,
    DIMINISHING_RETURNS_CONFIG,
    TRAIT_BREAKTHROUGH_TIERS,
    HABITAT_TRAIT_BONUS,
)


class TestDiminishingReturns:
    """边际递减机制测试"""
    
    def test_get_single_trait_cap(self):
        """测试单属性上限获取"""
        # 早期时代（回合0）
        cap_early = get_single_trait_cap(0, trophic_level=2.0)
        assert cap_early > 0
        
        # 后期时代（回合1000）
        cap_late = get_single_trait_cap(1000, trophic_level=2.0)
        assert cap_late > cap_early, "后期时代上限应更高"
        
        # 高营养级加成
        cap_high_trophic = get_single_trait_cap(500, trophic_level=4.0)
        cap_low_trophic = get_single_trait_cap(500, trophic_level=2.0)
        assert cap_high_trophic > cap_low_trophic, "高营养级上限应更高"
    
    def test_get_diminishing_factor(self):
        """测试边际递减因子计算"""
        turn = 500
        cap = get_single_trait_cap(turn)
        
        # 低属性值：无递减
        factor_low = get_diminishing_factor(cap * 0.3, turn)
        assert factor_low == 1.0, "低于50%上限应无递减"
        
        # 50-70%区间
        factor_mid1 = get_diminishing_factor(cap * 0.6, turn)
        assert factor_mid1 == DIMINISHING_RETURNS_CONFIG["f1"], "50-70%区间效率应为f1"
        
        # 70-85%区间
        factor_mid2 = get_diminishing_factor(cap * 0.75, turn)
        assert factor_mid2 == DIMINISHING_RETURNS_CONFIG["f2"], "70-85%区间效率应为f2"
        
        # 85-95%区间
        factor_high = get_diminishing_factor(cap * 0.9, turn)
        assert factor_high == DIMINISHING_RETURNS_CONFIG["f3"], "85-95%区间效率应为f3"
        
        # 95%以上
        factor_extreme = get_diminishing_factor(cap * 0.98, turn)
        assert factor_extreme == DIMINISHING_RETURNS_CONFIG["f4"], "95%以上效率应为f4"
    
    def test_get_diminishing_summary(self):
        """测试边际递减摘要生成"""
        turn = 500
        cap = get_single_trait_cap(turn)
        
        traits = {
            "耐寒性": cap * 0.8,   # 高属性
            "耐热性": cap * 0.55,  # 中等属性
            "运动能力": cap * 0.3,  # 低属性
        }
        
        summary = get_diminishing_summary(traits, turn)
        
        # 应该有2个高属性（>50%）
        assert len(summary["high_traits"]) == 2
        assert summary["warning_text"] != ""
        
        # 检查排序（按比例降序）
        if summary["high_traits"]:
            ratios = [t[2] for t in summary["high_traits"]]
            assert ratios == sorted(ratios, reverse=True)


class TestBreakthroughSystem:
    """突破系统测试"""
    
    def test_get_near_breakthroughs(self):
        """测试接近突破检测"""
        turn = 500
        cap = get_single_trait_cap(turn)
        
        traits = {
            "耐寒性": cap * 0.48,   # 接近50%突破
            "耐热性": cap * 0.78,   # 接近80%突破
            "运动能力": cap * 0.3,   # 不接近任何突破
        }
        
        near = get_near_breakthroughs(traits, turn)
        
        # 应该检测到耐寒性和耐热性接近突破
        trait_names = [n["trait"] for n in near]
        assert "耐寒性" in trait_names or "耐热性" in trait_names
        
        # 检查结构
        for n in near:
            assert "trait" in n
            assert "gap" in n
            assert "tier_name" in n
            assert n["gap"] > 0
    
    def test_get_breakthrough_summary(self):
        """测试突破摘要生成"""
        turn = 500
        cap = get_single_trait_cap(turn)
        
        traits = {
            "耐寒性": cap * 0.55,   # 已达专精
            "耐热性": cap * 0.78,   # 接近卓越
        }
        
        summary = get_breakthrough_summary(traits, turn)
        
        # 应该有已达成的突破
        assert len(summary["achieved"]) >= 1
        
        # 摘要文本不为空
        assert summary["summary_text"] != ""


class TestHabitatOrganBonus:
    """栖息地和器官加成测试"""
    
    def test_get_habitat_trait_bonus(self):
        """测试栖息地特化加成"""
        # 深海栖息地
        deep_sea_bonus = get_habitat_trait_bonus("deep_sea")
        assert "耐高压" in deep_sea_bonus
        assert deep_sea_bonus["耐高压"] > 0
        
        # 空中栖息地
        aerial_bonus = get_habitat_trait_bonus("aerial")
        assert "运动能力" in aerial_bonus
        
        # 不存在的栖息地
        unknown_bonus = get_habitat_trait_bonus("unknown")
        assert unknown_bonus == {}
    
    def test_get_organ_trait_bonus(self):
        """测试器官加成"""
        organs = {
            "sensory": {"stage": 3},  # 成熟阶段
            "locomotion": {"stage": 2},  # 功能阶段
        }
        
        # 感知能力应该有加成（来自sensory器官）
        bonus = get_organ_trait_bonus(organs, "感知能力")
        assert bonus > 0
        
        # 运动能力应该有加成（来自locomotion器官）
        bonus_move = get_organ_trait_bonus(organs, "运动能力")
        assert bonus_move > 0
        
        # 不相关的属性无加成
        bonus_none = get_organ_trait_bonus(organs, "耐寒性")
        assert bonus_none == 0
    
    def test_get_effective_trait_cap(self):
        """测试有效上限计算"""
        turn = 500
        base_cap = get_single_trait_cap(turn)
        
        # 无加成
        cap_none = get_effective_trait_cap("耐寒性", turn, 2.0)
        assert cap_none == base_cap
        
        # 有栖息地加成
        cap_habitat = get_effective_trait_cap(
            "耐高压", turn, 2.0, 
            habitat_type="deep_sea"
        )
        assert cap_habitat > base_cap
        
        # 有器官加成
        organs = {"sensory": {"stage": 3}}
        cap_organ = get_effective_trait_cap(
            "感知能力", turn, 2.0,
            organs=organs
        )
        assert cap_organ > base_cap
    
    def test_get_bonus_summary(self):
        """测试加成摘要生成"""
        organs = {"sensory": {"stage": 3}}
        
        summary = get_bonus_summary("deep_sea", organs)
        
        assert summary["habitat_bonus"]
        assert "耐高压" in summary["habitat_bonus"]
        assert summary["summary_text"] != ""


class TestIntegration:
    """集成测试"""
    
    def test_full_budget_context(self):
        """测试完整的预算上下文生成"""
        turn = 500
        trophic = 2.5
        habitat = "marine"
        
        traits = {
            "耐寒性": 8.0,
            "耐热性": 5.0,
            "耐盐性": 10.0,
            "运动能力": 6.0,
        }
        
        organs = {
            "sensory": {"stage": 2},
            "locomotion": {"stage": 1},
        }
        
        # 获取各种上下文
        cap = get_single_trait_cap(turn, trophic)
        diminishing = get_diminishing_summary(traits, turn, trophic)
        breakthrough = get_breakthrough_summary(traits, turn, trophic)
        bonus = get_bonus_summary(habitat, organs)
        
        # 验证输出结构
        assert cap > 0
        assert "high_traits" in diminishing
        assert "achieved" in breakthrough
        assert "habitat_bonus" in bonus
        
        print("\n=== 预算上下文测试结果 ===")
        print(f"单属性上限: {cap}")
        print(f"边际递减警告: {diminishing['warning_text'][:100]}..." if diminishing['warning_text'] else "无")
        print(f"已达成突破数: {len(breakthrough['achieved'])}")
        print(f"接近突破数: {len(breakthrough['near'])}")
        print(f"栖息地加成: {list(bonus['habitat_bonus'].keys())}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
