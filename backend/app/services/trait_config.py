"""Trait配置和验证工具"""
from __future__ import annotations


class TraitConfig:
    """统一的trait配置管理"""
    
    STANDARD_TRAITS = {
        "耐寒性": 5.0,
        "耐热性": 5.0,
        "耐旱性": 5.0,
        "耐盐性": 5.0,
        "光照需求": 5.0,
        "运动能力": 5.0,
        "繁殖速度": 5.0,
        "社会性": 3.0,
        "攻击性": 3.0,
        "防御性": 3.0,
    }
    
    TROPHIC_LIMITS = {
        1.0: {"base": 5, "specialized": 8, "total": 30},
        2.0: {"base": 7, "specialized": 10, "total": 50},
        3.0: {"base": 9, "specialized": 12, "total": 80},
        4.0: {"base": 12, "specialized": 14, "total": 105},
        5.0: {"base": 14, "specialized": 15, "total": 135},
    }
    
    TRAIT_PRESSURE_MAPPING = {
        "耐寒性": ("temperature", "cold"),
        "耐热性": ("temperature", "hot"),
        "耐极寒": ("temperature", "cold"),
        "耐旱性": ("drought", "high"),
        "耐盐性": ("salinity", "high"),
        "耐高压": ("pressure", "high"),
        "光照需求": ("light", "low"),
        "耐酸性": ("acidity", "high"),
        "耐碱性": ("alkalinity", "high"),
        "耐酸碱性": ("acidity", "high"),
        "氧气需求": ("oxygen", "low"),
    }
    
    TRAIT_DESCRIPTIONS = {
        "耐寒性": "抵抗低温能力",
        "耐热性": "抵抗高温能力",
        "耐极寒": "极端低温环境适应",
        "耐旱性": "抵抗干旱能力",
        "耐盐性": "抵抗盐度变化能力",
        "耐高压": "深海高压环境适应",
        "光照需求": "对光照的依赖程度",
        "运动能力": "移动和游动能力",
        "繁殖速度": "繁殖效率和速度",
        "社会性": "群居和社会互动倾向",
        "攻击性": "主动攻击倾向",
        "防御性": "防御和逃避能力",
        "耐酸性": "酸性环境耐受",
        "耐碱性": "碱性环境耐受",
        "耐酸碱性": "酸碱环境综合耐受",
        "氧气需求": "对氧气的依赖程度",
    }
    
    @classmethod
    def get_default_traits(cls) -> dict[str, float]:
        """获取默认trait集合"""
        return dict(cls.STANDARD_TRAITS)
    
    @classmethod
    def validate_trait(cls, trait_name: str, value: float) -> bool:
        """验证trait值是否合法"""
        if not isinstance(value, (int, float)):
            return False
        if value < 0.0 or value > 15.0:
            return False
        return True
    
    @classmethod
    def clamp_trait(cls, value: float) -> float:
        """限制trait值到有效范围"""
        return max(0.0, min(15.0, float(value)))
    
    @classmethod
    def get_pressure_mapping(cls, trait_name: str) -> tuple[str, str] | None:
        """获取trait对应的压力类型"""
        return cls.TRAIT_PRESSURE_MAPPING.get(trait_name)
    
    @classmethod
    def get_trait_description(cls, trait_name: str) -> str:
        """获取trait描述"""
        return cls.TRAIT_DESCRIPTIONS.get(trait_name, "未知特质")
    
    @classmethod
    def merge_traits(cls, base_traits: dict[str, float], new_traits: dict[str, float]) -> dict[str, float]:
        """合并trait字典，确保基础trait存在"""
        merged = cls.get_default_traits()
        merged.update(base_traits)
        merged.update(new_traits)
        
        for trait_name in merged:
            merged[trait_name] = cls.clamp_trait(merged[trait_name])
        
        return merged
    
    @classmethod
    def inherit_traits(cls, parent_traits: dict[str, float], variation: float = 0.1) -> dict[str, float]:
        """从父代继承trait，带小幅度变异
        
        Args:
            parent_traits: 父代traits
            variation: 变异幅度 (0.1 = ±10%)
        """
        import random
        
        inherited = {}
        for trait_name, value in parent_traits.items():
            delta = random.uniform(-variation, variation) * value
            inherited[trait_name] = cls.clamp_trait(value + delta)
        
        return inherited
    
    @classmethod
    def get_trophic_limits(cls, trophic_level: float) -> dict:
        """获取营养级对应的属性上限
        
        Args:
            trophic_level: 营养级（1.0-5.0+）
            
        Returns:
            {"base": 基础上限, "specialized": 特化上限, "total": 总和上限}
        """
        if trophic_level < 2.0:
            return cls.TROPHIC_LIMITS[1.0]
        elif trophic_level < 3.0:
            return cls.TROPHIC_LIMITS[2.0]
        elif trophic_level < 4.0:
            return cls.TROPHIC_LIMITS[3.0]
        elif trophic_level < 5.0:
            return cls.TROPHIC_LIMITS[4.0]
        else:
            return cls.TROPHIC_LIMITS[5.0]
    
    @classmethod
    def validate_traits_with_trophic(
        cls,
        traits: dict[str, float],
        trophic_level: float
    ) -> tuple[bool, str]:
        """验证traits是否符合营养级限制
        
        Args:
            traits: 待验证的traits字典
            trophic_level: 营养级
            
        Returns:
            (是否通过, 错误信息)
        """
        limits = cls.get_trophic_limits(trophic_level)
        
        total = sum(traits.values())
        if total > limits["total"]:
            return False, f"属性总和{total:.1f}超过营养级{trophic_level:.1f}的上限{limits['total']}"
        
        above_specialized = [(k, v) for k, v in traits.items() if v > limits["specialized"]]
        if above_specialized:
            return False, f"属性{above_specialized[0][0]}={above_specialized[0][1]:.1f}超过特化上限{limits['specialized']}"
        
        above_base_count = sum(1 for v in traits.values() if v > limits["base"])
        if above_base_count > 2:
            return False, f"{above_base_count}个属性超过基础上限{limits['base']}，最多允许2个特化"
        
        return True, ""
    
    @classmethod
    def clamp_traits_to_trophic(
        cls,
        traits: dict[str, float],
        trophic_level: float
    ) -> dict[str, float]:
        """将traits限制到营养级允许的范围内
        
        Args:
            traits: 原始traits
            trophic_level: 营养级
            
        Returns:
            调整后的traits
        """
        limits = cls.get_trophic_limits(trophic_level)
        adjusted = {}
        
        for trait_name, value in traits.items():
            clamped = min(value, limits["specialized"])
            adjusted[trait_name] = max(0.0, clamped)
        
        total = sum(adjusted.values())
        if total > limits["total"]:
            scale_factor = limits["total"] / total
            for trait_name in adjusted:
                adjusted[trait_name] = round(adjusted[trait_name] * scale_factor, 2)
        
        return adjusted

