"""Trait配置和验证工具

包含：
- 地质时代配置
- 属性上限计算（时代+营养级）
- 边际递减机制
- 突破系统
- 栖息地/器官加成
"""
from __future__ import annotations

import logging
import math

logger = logging.getLogger(__name__)


# ==================== 地质时代配置 ====================
# 游戏从28亿年前开始，每回合50万年
# 时代上限会随回合数**渐进式增长**，体现生物复杂度的演化
# 
# 设计理念：
# - 早期时代（太古宙）：上限较低，生物简单
# - 随时代推进：上限不断提升，允许更复杂的生物
# - 5600回合后：继续按公式增长，无上限限制

# 基础上限（太古宙起点，所有物种从这里开始）
ERA_BASE_LIMITS = {
    "single": 5,   # 单属性基础上限
    "total": 25,   # 属性总和基础上限
}

# 每100回合的增长量（渐进式增长）
ERA_GROWTH_PER_100_TURNS = {
    "single": 0.25,  # 每100回合单属性上限+0.25
    "total": 1.5,    # 每100回合总和上限+1.5
}

# 地质时代定义（主要用于描述和里程碑）
GEOLOGICAL_ERAS = {
    # 太古宙末期（28-25亿年前）：原始单细胞时代
    "archean": {
        "start_turn": 0,
        "end_turn": 600,  # 0-600回合（3亿年）
        "name": "太古宙",
        "name_en": "Archean",
        "description": "原始生命时代，只有简单的原核生物",
        "milestone": "生命起源",
    },
    # 元古宙早期（25-18亿年前）：真核生物出现
    "proterozoic_early": {
        "start_turn": 600,
        "end_turn": 2000,  # 600-2000回合（7亿年）
        "name": "元古宙早期",
        "name_en": "Early Proterozoic", 
        "description": "真核生物和光合作用出现，大氧化事件",
        "milestone": "真核生物",
    },
    # 元古宙中期（18-10亿年前）：多细胞生物萌芽
    "proterozoic_middle": {
        "start_turn": 2000,
        "end_turn": 3600,  # 2000-3600回合（8亿年）
        "name": "元古宙中期",
        "name_en": "Middle Proterozoic",
        "description": "多细胞生物开始出现，真核藻类繁盛",
        "milestone": "多细胞生物",
    },
    # 元古宙晚期（10-5.4亿年前）：埃迪卡拉纪生物群
    "proterozoic_late": {
        "start_turn": 3600,
        "end_turn": 4720,  # 3600-4720回合（5.6亿年）
        "name": "元古宙晚期",
        "name_en": "Late Proterozoic",
        "description": "埃迪卡拉生物群，软体动物兴起",
        "milestone": "动物起源",
    },
    # 古生代早期（5.4-4亿年前）：寒武纪大爆发
    "paleozoic_early": {
        "start_turn": 4720,
        "end_turn": 5000,  # 4720-5000回合（1.4亿年）
        "name": "古生代早期",
        "name_en": "Early Paleozoic",
        "description": "寒武纪大爆发，三叶虫时代，脊椎动物出现",
        "milestone": "寒武纪大爆发",
    },
    # 古生代中期（4-3亿年前）：鱼类时代，登陆开始
    "paleozoic_middle": {
        "start_turn": 5000,
        "end_turn": 5200,  # 5000-5200回合（1亿年）
        "name": "古生代中期",
        "name_en": "Middle Paleozoic",
        "description": "鱼类时代，植物和动物开始登陆",
        "milestone": "生物登陆",
    },
    # 古生代晚期（3-2.5亿年前）：两栖类和早期爬行类
    "paleozoic_late": {
        "start_turn": 5200,
        "end_turn": 5300,  # 5200-5300回合（0.5亿年）
        "name": "古生代晚期",
        "name_en": "Late Paleozoic",
        "description": "石炭纪森林，两栖类繁盛，早期爬行类出现",
        "milestone": "羊膜卵演化",
    },
    # 中生代（2.5-0.66亿年前）：恐龙时代
    "mesozoic": {
        "start_turn": 5300,
        "end_turn": 5532,  # 5300-5532回合（1.84亿年）
        "name": "中生代",
        "name_en": "Mesozoic",
        "description": "恐龙时代，哺乳类和鸟类出现",
        "milestone": "恐龙统治",
    },
    # 新生代（0.66亿年前-现在）：哺乳类时代
    "cenozoic": {
        "start_turn": 5532,
        "end_turn": 5600,  # 5532-5600回合（0.66亿年）
        "name": "新生代",
        "name_en": "Cenozoic",
        "description": "哺乳类辐射演化，智慧生命出现",
        "milestone": "哺乳类时代",
    },
    # 超越新生代（5600回合后）：未来演化
    "future": {
        "start_turn": 5600,
        "end_turn": 99999,  # 无上限
        "name": "未来纪",
        "name_en": "Future",
        "description": "超越已知历史，生物继续演化",
        "milestone": "无限可能",
    },
}


def get_current_era(turn_index: int) -> dict:
    """根据回合数获取当前地质时代信息
    
    Args:
        turn_index: 当前回合数
        
    Returns:
        时代配置字典
    """
    for era_id, era in GEOLOGICAL_ERAS.items():
        if era["start_turn"] <= turn_index < era["end_turn"]:
            return {"id": era_id, **era}
    # 超出定义范围，返回未来纪
    return {"id": "future", **GEOLOGICAL_ERAS["future"]}


def get_era_progress(turn_index: int) -> float:
    """获取当前时代的进度（0.0-1.0）
    
    用于显示时代进度
    """
    era = get_current_era(turn_index)
    duration = era["end_turn"] - era["start_turn"]
    if duration <= 0 or duration > 10000:  # 未来纪没有固定结束
        return 0.0
    progress = (turn_index - era["start_turn"]) / duration
    return min(1.0, max(0.0, progress))


def calculate_era_limits(turn_index: int) -> dict:
    """根据回合数计算当前的属性上限（渐进式增长）
    
    核心公式：
    - 单属性上限 = 基础值 + (回合数 / 100) × 每100回合增长量
    - 总和上限 = 基础值 + (回合数 / 100) × 每100回合增长量
    
    Args:
        turn_index: 当前回合数
        
    Returns:
        {"single": 单属性上限, "total": 总和上限}
    """
    # 计算增长量
    growth_factor = turn_index / 100.0
    
    single_limit = ERA_BASE_LIMITS["single"] + growth_factor * ERA_GROWTH_PER_100_TURNS["single"]
    total_limit = ERA_BASE_LIMITS["total"] + growth_factor * ERA_GROWTH_PER_100_TURNS["total"]
    
    # 取整（向下取整，确保不会超标）
    return {
        "single": int(single_limit),
        "total": int(total_limit),
    }


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
    
    # 基础营养级上限（不考虑时代修正）
    TROPHIC_LIMITS_BASE = {
        1.0: {"base": 5, "specialized": 8, "total": 30},
        2.0: {"base": 7, "specialized": 10, "total": 50},
        3.0: {"base": 9, "specialized": 12, "total": 80},
        4.0: {"base": 12, "specialized": 14, "total": 105},
        5.0: {"base": 14, "specialized": 15, "total": 135},
    }
    
    # 兼容旧代码
    TROPHIC_LIMITS = TROPHIC_LIMITS_BASE
    
    # 特质到压力类型的映射
    # 格式: { 特质名: (压力类型, 触发方向) }
    # 触发方向: "cold"=负值触发, "hot"=正值触发, "high"=高值触发, "low"=低值触发
    # 
    # 【生物学依据】
    # 物种在特定环境压力下，会通过自然选择发展出相应的适应性特质
    # 
    TRAIT_PRESSURE_MAPPING = {
        # ========== 温度相关 ==========
        "耐寒性": ("temperature", "cold"),    # 低温环境选择耐寒个体
        "耐热性": ("temperature", "hot"),     # 高温环境选择耐热个体
        "耐极寒": ("temperature", "cold"),    # 极端低温适应
        "温度适应范围": ("temperature", "high"),  # 温度波动大时扩展适应范围
        
        # ========== 水分相关 ==========
        "耐旱性": ("drought", "high"),        # 干旱环境选择节水个体
        "耐湿性": ("humidity", "high"),       # 潮湿环境适应
        "耐涝性": ("flood", "high"),          # 洪水环境适应
        "保水能力": ("drought", "high"),      # 干旱压力下增强保水
        
        # ========== 盐度相关 ==========
        "耐盐性": ("salinity_change", "high"), # 盐度变化时的渗透调节
        "渗透调节": ("salinity_change", "high"),  # 渗透压调节能力
        "广盐性": ("salinity_change", "high"),    # 盐度适应范围广
        
        # ========== 压力/深度相关 ==========
        "耐高压": ("pressure", "high"),       # 深海高压适应
        "耐低压": ("altitude_change", "high"), # 高海拔低压适应
        
        # ========== 光照相关 ==========
        "光照需求": ("light_reduction", "high"),  # 光照减少时降低依赖
        "弱光适应": ("light_reduction", "high"),  # 弱光环境下的视觉/光合适应
        "暗视觉": ("light_reduction", "high"),    # 黑暗环境适应
        
        # ========== 酸碱相关 ==========
        "耐酸性": ("acidity", "high"),        # 酸性环境适应
        "耐碱性": ("alkalinity", "high"),     # 碱性环境适应
        "耐酸碱性": ("acidity", "high"),      # pH耐受范围广
        "钙化能力": ("carbonate_stress", "high"),  # 酸化条件下维持壳体
        
        # ========== 氧气相关 ==========
        "氧气需求": ("oxygen", "low"),        # 低氧时降低代谢需求
        "耐缺氧": ("oxygen", "low"),          # 缺氧环境适应
        "高效呼吸": ("oxygen", "low"),        # 低氧时提高氧气利用效率
        "厌氧代谢": ("oxygen", "low"),        # 无氧呼吸能力
        
        # ========== 毒素/化学相关 ==========
        "耐毒性": ("toxin_level", "high"),    # 毒素耐受
        "解毒能力": ("sulfide", "high"),      # 硫化物等毒素解毒
        "抗紫外线": ("uv_radiation", "high"), # UV辐射防护
        "黑色素沉着": ("uv_radiation", "high"),  # 紫外防护适应
        
        # ========== 资源/食物相关 ==========
        "资源利用效率": ("resource_decline", "high"),  # 资源匮乏时提高效率
        "杂食性": ("resource_decline", "high"),  # 食物短缺时扩展食谱
        "储能能力": ("resource_decline", "high"),  # 储存脂肪应对饥荒
        "饥饿耐受": ("starvation_risk", "high"),  # 长期饥饿耐受
        
        # ========== 竞争/社会相关 ==========
        "竞争能力": ("competition", "high"),  # 竞争压力下增强竞争力
        "领地性": ("niche_displacement", "high"),  # 入侵压力下保卫领地
        "社会性": ("competition", "high"),    # 竞争压力下可能增强合作
        
        # ========== 捕食/防御相关 ==========
        "攻击性": ("predator", "high"),       # 捕食压力下增加攻击性
        "防御性": ("predator", "high"),       # 捕食压力下增强防御
        "警觉性": ("predator", "high"),       # 捕食压力下提高警觉
        "伪装能力": ("predator", "high"),     # 躲避捕食者
        "毒腺": ("predator", "high"),         # 化学防御
        
        # ========== 运动/迁徙相关 ==========
        "运动能力": ("predator", "high"),     # 逃避捕食者
        "迁徙能力": ("habitat_fragmentation", "high"),  # 栖息地破碎时迁徙
        "挖掘能力": ("wildfire", "high"),     # 火灾时躲避地下
        
        # ========== 疾病/免疫相关 ==========
        "免疫力": ("disease", "high"),        # 疾病压力下增强免疫
        "抗病性": ("disease", "high"),        # 特定病原体抗性
        "自我隔离": ("disease", "high"),      # 避免传染的行为
        
        # ========== 繁殖相关 ==========
        "繁殖速度": ("mortality_spike", "high"),  # 高死亡率时加速繁殖（r-策略）
        "后代存活率": ("resource_decline", "high"),  # 资源匮乏时提高育幼投资
        "繁殖季节灵活性": ("seasonality", "high"),  # 季节变化时调整繁殖期
        
        # ========== 火灾适应 ==========
        "耐火性": ("wildfire", "high"),       # 火灾环境适应
        "火后萌发": ("wildfire", "high"),     # 火灾后的恢复能力
    }
    
    # 新增：按栖息地类型分组的特质优先级
    # 不同栖息地类型的物种面对同一压力时，优先发展不同特质
    HABITAT_TRAIT_PRIORITY = {
        "marine": ["耐盐性", "渗透调节", "耐高压", "钙化能力", "耐缺氧"],
        "deep_sea": ["耐高压", "暗视觉", "耐缺氧", "耐寒性", "储能能力"],
        "coastal": ["耐盐性", "耐涝性", "广盐性", "迁徙能力", "耐热性"],
        "terrestrial": ["耐旱性", "耐热性", "耐寒性", "运动能力", "竞争能力"],
        "freshwater": ["渗透调节", "耐缺氧", "耐涝性", "温度适应范围", "保水能力"],
        "aerial": ["运动能力", "迁徙能力", "耐寒性", "高效呼吸", "温度适应范围"],
        "amphibious": ["耐旱性", "耐湿性", "温度适应范围", "渗透调节", "防御性"],
    }
    
    # 压力类型描述（用于生成叙事）
    # 【优化】扩展以支持更多压力场景
    PRESSURE_DESCRIPTIONS = {
        # 气候相关
        "temperature": {"hot": "高温环境", "cold": "寒冷环境"},
        "drought": {"high": "干旱环境"},
        "humidity": {"high": "潮湿环境"},
        "flood": {"high": "洪水/涝害"},
        "storm_damage": {"high": "风暴破坏"},
        "seasonality": {"high": "季节性剧变"},
        
        # 地质相关
        "volcanic": {"high": "火山活动"},
        "tectonic": {"high": "地壳运动"},
        "sea_level": {"high": "海平面上升", "low": "海平面下降"},
        "altitude_change": {"high": "海拔剧变"},
        "habitat_fragmentation": {"high": "栖息地破碎化"},
        "erosion": {"high": "严重侵蚀"},
        
        # 海洋相关
        "salinity_change": {"high": "盐度变化"},
        "upwelling_change": {"high": "上升流变化"},
        "carbonate_stress": {"high": "碳酸盐胁迫"},
        
        # 化学/大气相关
        "acidity": {"high": "酸性环境"},
        "oxygen": {"low": "低氧环境", "high": "富氧环境"},
        "sulfide": {"high": "硫化物毒害"},
        "uv_radiation": {"high": "紫外辐射增强"},
        "toxin_level": {"high": "毒素污染"},
        
        # 生态相关
        "predator": {"high": "捕食压力"},
        "competition": {"high": "种间竞争"},
        "niche_displacement": {"high": "生态位被侵占"},
        "disease": {"high": "疾病流行"},
        "resource_decline": {"high": "资源匮乏"},
        "resource_boost": {"high": "资源丰富期"},
        "starvation_risk": {"high": "饥荒威胁"},
        
        # 火灾相关
        "wildfire": {"high": "野火肆虐"},
        "wildfire_risk": {"high": "火灾风险"},
        
        # 其他
        "light_reduction": {"high": "光照不足"},
        "mortality_spike": {"high": "死亡率骤增"},
        "habitat_loss": {"high": "栖息地丧失"},
    }
    
    TRAIT_DESCRIPTIONS = {
        # 温度相关
        "耐寒性": "抵抗低温能力，如抗冻蛋白、厚毛皮",
        "耐热性": "抵抗高温能力，如高效散热、热休克蛋白",
        "耐极寒": "极端低温环境适应，如南极鱼类的抗冻血液",
        "温度适应范围": "对温度变化的耐受范围",
        
        # 水分相关
        "耐旱性": "抵抗干旱能力，如骆驼的储水机制",
        "耐湿性": "潮湿环境适应能力",
        "耐涝性": "洪水/淹没环境的耐受力",
        "保水能力": "减少水分流失的能力",
        
        # 盐度相关
        "耐盐性": "抵抗盐度变化能力，如渗透压调节",
        "渗透调节": "体液渗透压的调节能力",
        "广盐性": "适应多种盐度环境的能力",
        
        # 压力/深度相关
        "耐高压": "深海高压环境适应",
        "耐低压": "高海拔低压环境适应",
        
        # 光照相关
        "光照需求": "对光照的依赖程度",
        "弱光适应": "在弱光条件下生存的能力",
        "暗视觉": "黑暗环境中的视觉能力",
        
        # 酸碱相关
        "耐酸性": "酸性环境耐受能力",
        "耐碱性": "碱性环境耐受能力",
        "耐酸碱性": "酸碱环境综合耐受能力",
        "钙化能力": "在酸化条件下维持钙质壳体的能力",
        
        # 氧气相关
        "氧气需求": "对氧气的依赖程度",
        "耐缺氧": "低氧环境的耐受能力",
        "高效呼吸": "氧气利用效率",
        "厌氧代谢": "无氧呼吸的能力",
        
        # 毒素/化学相关
        "耐毒性": "对环境毒素的耐受能力",
        "解毒能力": "代谢分解毒素的能力",
        "抗紫外线": "抵抗紫外辐射的能力",
        "黑色素沉着": "通过色素保护免受UV伤害",
        
        # 资源相关
        "资源利用效率": "对食物资源的利用效率",
        "杂食性": "食物来源的多样性",
        "储能能力": "储存能量（如脂肪）的能力",
        "饥饿耐受": "长期饥饿状态的耐受力",
        
        # 运动相关
        "运动能力": "移动和游动能力",
        "迁徙能力": "长距离迁移的能力",
        "挖掘能力": "挖洞穴居的能力",
        
        # 社会/竞争相关
        "社会性": "群居和社会互动倾向",
        "攻击性": "主动攻击倾向",
        "防御性": "防御和逃避能力",
        "警觉性": "对威胁的警觉程度",
        "竞争能力": "资源竞争的综合能力",
        "领地性": "保卫领地的倾向和能力",
        "伪装能力": "隐蔽自身的能力",
        "毒腺": "化学防御能力",
        
        # 繁殖相关
        "繁殖速度": "繁殖效率和速度",
        "后代存活率": "后代的生存概率",
        "繁殖季节灵活性": "繁殖时间的可调节性",
        
        # 疾病/免疫相关
        "免疫力": "抵抗病原体的能力",
        "抗病性": "对特定疾病的抵抗力",
        
        # 火灾适应
        "耐火性": "对火灾的耐受能力",
        "火后萌发": "火灾后恢复的能力",
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
    def get_trophic_limits(cls, trophic_level: float, turn_index: int = None) -> dict:
        """获取属性上限（营养级 + 时代双重增长）
        
        计算逻辑：
        1. 时代上限 = 基础值 + 回合数带来的增长（所有物种共享）
        2. 营养级加成 = 高营养级获得额外加成（捕食者更强）
        3. 最终上限 = 时代上限 + 营养级加成
        
        Args:
            trophic_level: 营养级（1.0-5.0+）
            turn_index: 当前回合数（如果提供，会应用时代增长）
            
        Returns:
            {"base": 基础上限, "specialized": 特化上限, "total": 总和上限, 
             "era_name": 时代名称, "era_progress": 时代进度}
        """
        # 1. 计算时代基础上限
        if turn_index is None:
            turn_index = 0
        
        era_limits = calculate_era_limits(turn_index)
        era = get_current_era(turn_index)
        era_progress = get_era_progress(turn_index)
        
        # 2. 计算营养级加成
        # 高营养级的捕食者可以比同时代的低营养级生物更强
        # 每提升1个营养级，单属性+1，总和+8
        trophic_bonus_single = int((trophic_level - 1.0) * 1.5)
        trophic_bonus_total = int((trophic_level - 1.0) * 10)
        
        # 3. 计算最终上限
        final_single = era_limits["single"] + trophic_bonus_single
        final_total = era_limits["total"] + trophic_bonus_total
        
        # base 是普通属性的建议上限（specialized 的 60%）
        final_base = int(final_single * 0.6)
        
        adjusted_limits = {
            "base": max(3, final_base),
            "specialized": max(5, final_single),
            "total": max(20, final_total),
            "era_name": era["name"],
            "era_id": era["id"],
            "era_progress": era_progress,
            "era_description": era["description"],
            # 额外信息
            "era_single_base": era_limits["single"],
            "era_total_base": era_limits["total"],
            "trophic_bonus_single": trophic_bonus_single,
            "trophic_bonus_total": trophic_bonus_total,
        }
        
        return adjusted_limits
    
    @classmethod
    def validate_traits_with_trophic(
        cls,
        traits: dict[str, float],
        trophic_level: float,
        turn_index: int = None
    ) -> tuple[bool, str]:
        """验证traits是否符合营养级和时代限制
        
        Args:
            traits: 待验证的traits字典
            trophic_level: 营养级
            turn_index: 当前回合数（可选，用于时代修正）
            
        Returns:
            (是否通过, 错误信息)
        """
        limits = cls.get_trophic_limits(trophic_level, turn_index)
        
        total = sum(traits.values())
        if total > limits["total"]:
            era_info = f"（{limits.get('era_name', '未知')}时代）" if turn_index else ""
            return False, f"属性总和{total:.1f}超过{era_info}上限{limits['total']}"
        
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
        trophic_level: float,
        turn_index: int = None
    ) -> dict[str, float]:
        """将traits限制到营养级和时代允许的范围内
        
        Args:
            traits: 原始traits
            trophic_level: 营养级
            turn_index: 当前回合数（可选，用于时代修正）
            
        Returns:
            调整后的traits
        """
        limits = cls.get_trophic_limits(trophic_level, turn_index)
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
    
    @classmethod
    def get_era_limits_summary(cls, turn_index: int, trophic_level: float = 2.0) -> str:
        """获取时代上限的文字摘要（用于prompt）
        
        Args:
            turn_index: 当前回合数
            trophic_level: 营养级（默认2.0作为参考）
            
        Returns:
            格式化的时代上限说明
        """
        limits = cls.get_trophic_limits(trophic_level, turn_index)
        era = get_current_era(turn_index)
        progress = get_era_progress(turn_index)
        
        # 计算游戏内时间
        years_passed = turn_index * 500_000
        years_ago = 2_800_000_000 - years_passed
        
        if years_ago >= 1_000_000_000:
            time_str = f"{years_ago / 1_000_000_000:.1f}亿年前"
        elif years_ago >= 10_000_000:
            time_str = f"{years_ago / 100_000_000:.1f}亿年前"
        elif years_ago >= 1_000_000:
            time_str = f"{years_ago / 10_000:.0f}万年前"
        elif years_ago > 0:
            time_str = f"{years_ago:.0f}年前"
        else:
            time_str = "现代"
        
        # 显示增长信息
        era_base = limits.get('era_single_base', limits['specialized'])
        trophic_bonus = limits.get('trophic_bonus_single', 0)
        
        return (
            f"【当前时代】{era['name']}（{time_str}，回合{turn_index}）\n"
            f"里程碑：{era.get('milestone', '未知')}\n"
            f"时代特征：{era['description']}\n"
            f"时代基础上限：单属性≤{era_base}，总和≤{limits.get('era_total_base', limits['total'])}\n"
            f"营养级T{trophic_level:.1f}加成：单属性+{trophic_bonus}，总和+{limits.get('trophic_bonus_total', 0)}\n"
            f"【最终上限】单属性≤{limits['specialized']}，总和≤{limits['total']}"
        )


class PlantTraitConfig:
    """植物特质配置（仅用于营养级 < 2.0 的生产者）
    
    【设计原则】
    - 植物不需要动物特质（运动能力、攻击性等）
    - 植物有专属特质（光合效率、根系发达度等）
    - 当检测到植物时，部分动物特质会被映射/替换
    """
    
    # 植物专属特质（默认值）
    PLANT_TRAITS = {
        # 光合与代谢
        "光合效率": 5.0,       # 光能转化效率
        "固碳能力": 5.0,       # CO2固定效率
        
        # 水分与养分
        "根系发达度": 0.0,     # 0=无根(水生), 10=发达根系(陆生)
        "保水能力": 3.0,       # 水分保持能力（登陆必需）
        "养分吸收": 5.0,       # 土壤养分利用效率
        
        # 结构与繁殖
        "多细胞程度": 1.0,     # 1=单细胞, 10=复杂组织分化
        "木质化程度": 0.0,     # 0=无, 10=完全木质化（成为树木必需>=7）
        "种子化程度": 0.0,     # 0=孢子繁殖, 10=完全种子繁殖
        "散布能力": 3.0,       # 孢子/种子传播范围
        
        # 防御与适应
        "化学防御": 3.0,       # 毒素、单宁等
        "物理防御": 3.0,       # 刺、硬壳等
    }
    
    # 动物特质到植物特质的映射
    # 当处理植物时，这些动物特质会被替换为对应的植物特质
    ANIMAL_TO_PLANT_MAPPING = {
        "运动能力": "光合效率",
        "攻击性": "化学防御",
        "社会性": "散布能力",
        "防御性": "物理防御",
    }
    
    # 植物到动物的反向映射
    PLANT_TO_ANIMAL_MAPPING = {v: k for k, v in ANIMAL_TO_PLANT_MAPPING.items()}
    
    # 共享特质（动植物通用）
    SHARED_TRAITS = [
        "耐寒性", "耐热性", "耐旱性", "耐盐性",
        "光照需求", "繁殖速度",
    ]
    
    # 植物演化阶段名称
    LIFE_FORM_STAGE_NAMES = {
        0: "原核光合生物",
        1: "单细胞真核藻类",
        2: "群体/丝状藻类",
        3: "苔藓类植物",
        4: "蕨类植物",
        5: "裸子植物",
        6: "被子植物",
    }
    
    # 生长形式
    GROWTH_FORMS = ["aquatic", "moss", "herb", "shrub", "tree"]
    
    # 生长形式与阶段的约束
    GROWTH_FORM_STAGE_CONSTRAINTS = {
        "aquatic": [0, 1, 2],           # 水生：阶段0-2
        "moss": [3],                     # 苔藓：阶段3
        "herb": [4, 5, 6],               # 草本：阶段4-6
        "shrub": [5, 6],                 # 灌木：阶段5-6
        "tree": [5, 6],                  # 乔木：阶段5-6（需木质化>=7）
    }
    
    # 【新增】植物特质到压力类型的映射
    # 格式: { 特质名: (压力类型, 触发方向) }
    # 用于渐进演化中植物特质的自动调整
    PLANT_TRAIT_PRESSURE_MAPPING = {
        # ========== 光合与代谢 ==========
        "光合效率": ("light_reduction", "high"),     # 弱光环境提升光合效率
        "固碳能力": ("co2_level", "high"),           # 高CO2环境提升固碳
        
        # ========== 水分与养分 ==========
        "根系发达度": ("drought", "high"),           # 干旱促进根系发展
        "保水能力": ("drought", "high"),             # 干旱提升保水能力
        "养分吸收": ("nutrient_poor", "high"),       # 贫瘠环境提升养分吸收
        
        # ========== 结构发育 ==========
        "多细胞程度": ("competition", "high"),       # 竞争促进复杂化
        "木质化程度": ("drought", "high"),           # 干旱促进木质化（更好的水分运输）
        "种子化程度": ("drought", "high"),           # 干旱促进种子化（脱水繁殖）
        "散布能力": ("habitat_fragmentation", "high"),  # 栖息地破碎促进散布
        
        # ========== 防御机制 ==========
        "化学防御": ("herbivory", "high"),           # 食草压力促进化学防御
        "物理防御": ("herbivory", "high"),           # 食草压力促进物理防御
    }
    
    # 【新增】植物特质的权衡关系（增加某特质时，哪些特质可能降低）
    PLANT_TRAIT_TRADEOFFS = {
        "光合效率": ["耐旱性", "繁殖速度"],         # 高效光合需要更多水分
        "根系发达度": ["散布能力", "繁殖速度"],     # 发达根系限制移动
        "木质化程度": ["繁殖速度", "光合效率"],     # 木质化消耗大量能量
        "化学防御": ["繁殖速度", "光合效率"],       # 毒素合成消耗能量
        "物理防御": ["繁殖速度", "散布能力"],       # 刺等结构消耗资源
        "种子化程度": ["繁殖速度"],                 # 种子发育周期长
        "保水能力": ["光合效率"],                   # 厚角质层阻碍气体交换
    }
    
    @classmethod
    def get_plant_pressure_mapping(cls, trait_name: str) -> tuple[str, str] | None:
        """获取植物特质对应的压力类型
        
        Args:
            trait_name: 特质名称
            
        Returns:
            (压力类型, 触发方向) 或 None
        """
        return cls.PLANT_TRAIT_PRESSURE_MAPPING.get(trait_name)
    
    @classmethod
    def get_trait_tradeoffs(cls, trait_name: str) -> list[str]:
        """获取特质的权衡关系（增加时哪些可能降低）
        
        Args:
            trait_name: 特质名称
            
        Returns:
            可能降低的特质列表
        """
        return cls.PLANT_TRAIT_TRADEOFFS.get(trait_name, [])
    
    @classmethod
    def get_default_plant_traits(cls) -> dict[str, float]:
        """获取默认植物特质集合"""
        # 合并共享特质和植物专属特质
        traits = {}
        for trait in cls.SHARED_TRAITS:
            traits[trait] = TraitConfig.STANDARD_TRAITS.get(trait, 5.0)
        traits.update(cls.PLANT_TRAITS)
        return traits
    
    @classmethod
    def convert_animal_to_plant_traits(cls, animal_traits: dict[str, float]) -> dict[str, float]:
        """将动物特质转换为植物特质
        
        Args:
            animal_traits: 动物特质字典
            
        Returns:
            转换后的植物特质字典
        """
        plant_traits = {}
        
        for trait_name, value in animal_traits.items():
            # 检查是否需要映射
            if trait_name in cls.ANIMAL_TO_PLANT_MAPPING:
                mapped_name = cls.ANIMAL_TO_PLANT_MAPPING[trait_name]
                plant_traits[mapped_name] = value
            elif trait_name in cls.SHARED_TRAITS:
                plant_traits[trait_name] = value
            # 忽略其他动物专属特质
        
        # 确保所有植物特质都有值
        for trait_name, default_value in cls.PLANT_TRAITS.items():
            if trait_name not in plant_traits:
                plant_traits[trait_name] = default_value
        
        return plant_traits
    
    @classmethod
    def convert_plant_to_animal_traits(cls, plant_traits: dict[str, float]) -> dict[str, float]:
        """将植物特质转换回动物特质格式（用于兼容性）
        
        Args:
            plant_traits: 植物特质字典
            
        Returns:
            兼容动物特质格式的字典
        """
        animal_traits = {}
        
        for trait_name, value in plant_traits.items():
            if trait_name in cls.PLANT_TO_ANIMAL_MAPPING:
                mapped_name = cls.PLANT_TO_ANIMAL_MAPPING[trait_name]
                animal_traits[mapped_name] = value
            elif trait_name in cls.SHARED_TRAITS:
                animal_traits[trait_name] = value
            else:
                # 保留植物专属特质
                animal_traits[trait_name] = value
        
        return animal_traits
    
    @classmethod
    def is_plant(cls, species) -> bool:
        """判断物种是否为植物（生产者）
        
        Args:
            species: 物种对象
            
        Returns:
            是否为植物
        """
        # 营养级 < 2.0 是生产者
        if hasattr(species, 'trophic_level') and species.trophic_level < 2.0:
            return True
        
        # 有光合作用能力
        caps = getattr(species, 'capabilities', []) or []
        if '光合作用' in caps or 'photosynthesis' in caps:
            return True
        
        # 食性为自养
        diet = getattr(species, 'diet_type', '')
        if diet == 'autotroph':
            return True
        
        return False
    
    @classmethod
    def validate_growth_form(cls, growth_form: str, life_form_stage: int) -> bool:
        """验证生长形式与演化阶段是否匹配
        
        Args:
            growth_form: 生长形式
            life_form_stage: 演化阶段
            
        Returns:
            是否匹配
        """
        if growth_form not in cls.GROWTH_FORM_STAGE_CONSTRAINTS:
            return False
        
        allowed_stages = cls.GROWTH_FORM_STAGE_CONSTRAINTS[growth_form]
        return life_form_stage in allowed_stages
    
    @classmethod
    def get_valid_growth_forms(cls, life_form_stage: int) -> list[str]:
        """获取指定阶段允许的生长形式
        
        Args:
            life_form_stage: 演化阶段
            
        Returns:
            允许的生长形式列表
        """
        valid_forms = []
        for form, stages in cls.GROWTH_FORM_STAGE_CONSTRAINTS.items():
            if life_form_stage in stages:
                valid_forms.append(form)
        return valid_forms
    
    @classmethod
    def get_stage_name(cls, life_form_stage: int) -> str:
        """获取阶段名称"""
        return cls.LIFE_FORM_STAGE_NAMES.get(life_form_stage, "未知阶段")


# ==================== 边际递减机制 ====================

# 边际递减阈值配置
DIMINISHING_RETURNS_CONFIG = {
    "t1_ratio": 0.50,   # 第一递减阈值：50%上限
    "t2_ratio": 0.70,   # 第二递减阈值：70%上限
    "t3_ratio": 0.85,   # 第三递减阈值：85%上限
    "t4_ratio": 0.95,   # 第四递减阈值：95%上限
    "f1": 0.60,         # 第一区间效率：60%
    "f2": 0.30,         # 第二区间效率：30%
    "f3": 0.10,         # 第三区间效率：10%
    "f4": 0.02,         # 第四区间效率：2%
}


def get_single_trait_cap(turn_index: int, trophic_level: float = 2.0) -> float:
    """获取单属性上限
    
    Args:
        turn_index: 当前回合数
        trophic_level: 营养级（默认2.0）
        
    Returns:
        单属性上限值
    """
    limits = TraitConfig.get_trophic_limits(trophic_level, turn_index)
    return float(limits["specialized"])


def get_diminishing_factor(current_value: float, turn_index: int, trophic_level: float = 2.0) -> float:
    """计算边际递减因子
    
    属性越高，新增益的效率越低。
    
    Args:
        current_value: 当前属性值
        turn_index: 当前回合数
        trophic_level: 营养级
        
    Returns:
        增益效率（0.02-1.0）
    """
    cap = get_single_trait_cap(turn_index, trophic_level)
    if cap <= 0:
        return 1.0
    
    config = DIMINISHING_RETURNS_CONFIG
    
    # 相对阈值（基于上限的比例）
    t1 = cap * config["t1_ratio"]
    t2 = cap * config["t2_ratio"]
    t3 = cap * config["t3_ratio"]
    t4 = cap * config["t4_ratio"]
    
    if current_value < t1:
        return 1.0
    elif current_value < t2:
        return config["f1"]
    elif current_value < t3:
        return config["f2"]
    elif current_value < t4:
        return config["f3"]
    else:
        return config["f4"]


def get_diminishing_summary(traits: dict[str, float], turn_index: int, trophic_level: float = 2.0) -> dict:
    """获取属性的边际递减摘要
    
    Args:
        traits: 属性字典
        turn_index: 当前回合数
        trophic_level: 营养级
        
    Returns:
        {
            "high_traits": [(trait_name, value, ratio, efficiency), ...],
            "warning_text": 警告文本,
            "strategy_hint": 策略建议
        }
    """
    cap = get_single_trait_cap(turn_index, trophic_level)
    high_traits = []
    
    for trait_name, value in traits.items():
        if cap > 0:
            ratio = value / cap
            if ratio >= 0.5:
                efficiency = get_diminishing_factor(value, turn_index, trophic_level)
                high_traits.append((trait_name, value, ratio, efficiency))
    
    # 按比例降序排序
    high_traits.sort(key=lambda x: x[2], reverse=True)
    
    warning_lines = []
    for trait_name, value, ratio, efficiency in high_traits:
        warning_lines.append(f"- {trait_name}: {value:.1f} ({ratio:.0%}上限，增益效率{efficiency:.0%})")
    
    warning_text = ""
    if warning_lines:
        warning_text = "以下属性已进入递减区域：\n" + "\n".join(warning_lines)
    
    strategy_hint = ""
    if len(high_traits) >= 3:
        strategy_hint = "💡 建议：多个属性已接近上限，考虑分散投资到其他属性"
    elif len(high_traits) >= 1 and high_traits[0][2] >= 0.85:
        strategy_hint = f"💡 建议：{high_traits[0][0]} 效率很低，可尝试突破或转向其他属性"
    
    return {
        "high_traits": high_traits,
        "warning_text": warning_text,
        "strategy_hint": strategy_hint,
    }


# ==================== 突破系统 ====================

# 单属性突破阈值
TRAIT_BREAKTHROUGH_TIERS = {
    0.50: {
        "name": "专精",
        "effect": "该属性生态效果+30%",
        "bonus": {"eco_effect": 0.30}
    },
    0.65: {
        "name": "大师",
        "effect": "边际递减减缓50%",
        "bonus": {"diminishing_reduction": 0.50}
    },
    0.80: {
        "name": "卓越",
        "effect": "该属性上限+15%",
        "bonus": {"cap_bonus_percent": 0.15}
    },
    0.90: {
        "name": "传奇",
        "effect": "免疫边际递减",
        "bonus": {"no_diminishing": True}
    },
    0.98: {
        "name": "神话",
        "effect": "该属性可协同增强相关属性",
        "bonus": {"synergy_unlock": True}
    },
}

# 总和突破阈值
TOTAL_BREAKTHROUGH_TIERS = {
    0.30: {
        "name": "简单生物",
        "effect": "器官槽位+1",
        "bonus": {"organ_slots": 1}
    },
    0.50: {
        "name": "复杂生物",
        "effect": "基因激活概率+20%",
        "bonus": {"activation_bonus": 0.20}
    },
    0.70: {
        "name": "高等生物",
        "effect": "新基因发现概率+30%",
        "bonus": {"discovery_bonus": 0.30}
    },
    0.85: {
        "name": "顶级生物",
        "effect": "竞争压力-15%",
        "bonus": {"competition_reduce": 0.15}
    },
    0.95: {
        "name": "顶点生物",
        "effect": "繁殖效率+20%",
        "bonus": {"reproduction_bonus": 0.20}
    },
}


def get_trait_breakthrough_status(value: float, cap: float) -> dict | None:
    """获取单属性的突破状态
    
    Args:
        value: 当前属性值
        cap: 属性上限
        
    Returns:
        当前已达到的最高突破等级信息，或 None
    """
    if cap <= 0:
        return None
    
    ratio = value / cap
    achieved = None
    
    for threshold in sorted(TRAIT_BREAKTHROUGH_TIERS.keys()):
        if ratio >= threshold:
            achieved = {
                "threshold": threshold,
                "ratio": ratio,
                **TRAIT_BREAKTHROUGH_TIERS[threshold]
            }
    
    return achieved


def get_near_breakthroughs(traits: dict[str, float], turn_index: int, trophic_level: float = 2.0) -> list[dict]:
    """获取接近突破的属性
    
    Args:
        traits: 属性字典
        turn_index: 当前回合数
        trophic_level: 营养级
        
    Returns:
        [{"trait": 属性名, "current": 当前值, "target": 目标值, "gap": 差距, "tier": 突破等级名}, ...]
    """
    cap = get_single_trait_cap(turn_index, trophic_level)
    if cap <= 0:
        return []
    
    near_list = []
    
    for trait_name, value in traits.items():
        ratio = value / cap
        
        # 找到下一个未达到的突破阈值
        for threshold in sorted(TRAIT_BREAKTHROUGH_TIERS.keys()):
            if ratio < threshold:
                gap = (threshold * cap) - value
                # 只显示差距在合理范围内的（比如差距 < 5.0）
                if gap <= 5.0:
                    tier_info = TRAIT_BREAKTHROUGH_TIERS[threshold]
                    near_list.append({
                        "trait": trait_name,
                        "current": value,
                        "target": threshold * cap,
                        "gap": gap,
                        "tier_name": tier_info["name"],
                        "tier_effect": tier_info["effect"],
                        "threshold": threshold,
                    })
                break
    
    # 按差距排序
    near_list.sort(key=lambda x: x["gap"])
    return near_list


def get_breakthrough_summary(traits: dict[str, float], turn_index: int, trophic_level: float = 2.0) -> dict:
    """获取突破系统摘要
    
    Args:
        traits: 属性字典
        turn_index: 当前回合数
        trophic_level: 营养级
        
    Returns:
        {
            "achieved": 已达成的突破,
            "near": 接近突破的属性,
            "summary_text": 摘要文本
        }
    """
    cap = get_single_trait_cap(turn_index, trophic_level)
    
    achieved = []
    for trait_name, value in traits.items():
        status = get_trait_breakthrough_status(value, cap)
        if status:
            achieved.append({
                "trait": trait_name,
                "tier": status["name"],
                "effect": status["effect"],
            })
    
    near = get_near_breakthroughs(traits, turn_index, trophic_level)
    
    # 生成摘要文本
    summary_lines = []
    
    if achieved:
        summary_lines.append("【已达成突破】")
        for a in achieved:
            summary_lines.append(f"  - {a['trait']}: 「{a['tier']}」{a['effect']}")
    
    if near:
        summary_lines.append("【接近突破】")
        for n in near[:3]:  # 只显示前3个
            summary_lines.append(f"  - {n['trait']}: 再+{n['gap']:.1f}可达「{n['tier_name']}」")
    
    summary_text = "\n".join(summary_lines) if summary_lines else "暂无突破进度"
    
    return {
        "achieved": achieved,
        "near": near,
        "summary_text": summary_text,
    }


# ==================== 栖息地/器官加成 ====================

# 栖息地特化加成：特定栖息地允许相关属性超过普通上限
HABITAT_TRAIT_BONUS = {
    "deep_sea": {
        "耐高压": 5.0,
        "暗视觉": 3.0,
        "耐寒性": 2.0,
        "耐缺氧": 2.0,
    },
    "terrestrial": {
        "运动能力": 3.0,
        "耐旱性": 3.0,
        "耐热性": 2.0,
    },
    "aerial": {
        "运动能力": 5.0,
        "感知能力": 3.0,
        "迁徙能力": 3.0,
    },
    "marine": {
        "耐盐性": 4.0,
        "渗透调节": 3.0,
        "耐高压": 2.0,
    },
    "freshwater": {
        "渗透调节": 3.0,
        "耐缺氧": 2.0,
        "耐涝性": 2.0,
    },
    "coastal": {
        "耐盐性": 3.0,
        "耐旱性": 2.0,
        "温度适应范围": 2.0,
    },
    "amphibious": {
        "耐旱性": 3.0,
        "耐湿性": 3.0,
        "温度适应范围": 2.0,
    },
}

# 器官加成：成熟器官解锁相关属性额外上限
ORGAN_TRAIT_BONUS = {
    "sensory": {
        "警觉性": 4.0,
        "感知能力": 4.0,
        "暗视觉": 2.0,
    },
    "locomotion": {
        "运动能力": 5.0,
        "迁徙能力": 3.0,
    },
    "defense": {
        "防御性": 4.0,
        "物理防御": 4.0,
    },
    "metabolic": {
        "耐寒性": 2.0,
        "耐热性": 2.0,
        "饥饿耐受": 3.0,
    },
    "respiratory": {
        "耐缺氧": 4.0,
        "高效呼吸": 3.0,
    },
    "nervous": {
        "智力": 5.0,
        "社会性": 3.0,
        "警觉性": 2.0,
    },
    "digestive": {
        "杂食性": 3.0,
        "资源利用效率": 3.0,
    },
}

# 器官阶段对加成的缩放
ORGAN_STAGE_SCALE = {
    0: 0.0,    # 原基：0%
    1: 0.25,   # 初级：25%
    2: 0.60,   # 功能：60%
    3: 1.00,   # 成熟：100%
    4: 1.20,   # 完善：120%
}


def get_habitat_trait_bonus(habitat_type: str) -> dict[str, float]:
    """获取栖息地特化加成
    
    Args:
        habitat_type: 栖息地类型
        
    Returns:
        {属性名: 加成值}
    """
    return HABITAT_TRAIT_BONUS.get(habitat_type, {})


def get_organ_trait_bonus(organs: dict, trait_name: str) -> float:
    """获取器官对特定属性的加成
    
    Args:
        organs: 器官字典 {category: {stage: int, ...}}
        trait_name: 属性名
        
    Returns:
        总加成值
    """
    total_bonus = 0.0
    
    for category, organ_info in organs.items():
        if category not in ORGAN_TRAIT_BONUS:
            continue
        
        trait_bonuses = ORGAN_TRAIT_BONUS[category]
        if trait_name not in trait_bonuses:
            continue
        
        stage = organ_info.get("stage", 0)
        scale = ORGAN_STAGE_SCALE.get(stage, 0.0)
        base_bonus = trait_bonuses[trait_name]
        
        total_bonus += base_bonus * scale
    
    return total_bonus


def get_effective_trait_cap(
    trait_name: str,
    turn_index: int,
    trophic_level: float,
    habitat_type: str = None,
    organs: dict = None
) -> float:
    """获取属性的有效上限（考虑所有加成）
    
    Args:
        trait_name: 属性名
        turn_index: 当前回合数
        trophic_level: 营养级
        habitat_type: 栖息地类型（可选）
        organs: 器官字典（可选）
        
    Returns:
        有效上限值
    """
    base_cap = get_single_trait_cap(turn_index, trophic_level)
    
    # 栖息地加成
    habitat_bonus = 0.0
    if habitat_type:
        habitat_bonuses = get_habitat_trait_bonus(habitat_type)
        habitat_bonus = habitat_bonuses.get(trait_name, 0.0)
    
    # 器官加成
    organ_bonus = 0.0
    if organs:
        organ_bonus = get_organ_trait_bonus(organs, trait_name)
    
    return base_cap + habitat_bonus + organ_bonus


def get_bonus_summary(habitat_type: str, organs: dict = None) -> dict:
    """获取所有加成的摘要
    
    Args:
        habitat_type: 栖息地类型
        organs: 器官字典
        
    Returns:
        {
            "habitat_bonus": 栖息地加成字典,
            "organ_bonus": 器官加成字典,
            "summary_text": 摘要文本
        }
    """
    habitat_bonus = get_habitat_trait_bonus(habitat_type)
    
    organ_bonus = {}
    if organs:
        # 收集所有器官的加成
        for category, organ_info in organs.items():
            if category not in ORGAN_TRAIT_BONUS:
                continue
            
            stage = organ_info.get("stage", 0)
            scale = ORGAN_STAGE_SCALE.get(stage, 0.0)
            
            if scale > 0:
                for trait, base_bonus in ORGAN_TRAIT_BONUS[category].items():
                    if trait not in organ_bonus:
                        organ_bonus[trait] = 0.0
                    organ_bonus[trait] += base_bonus * scale
    
    # 生成摘要文本
    lines = []
    
    if habitat_bonus:
        lines.append(f"【{habitat_type} 栖息地特化】")
        for trait, bonus in habitat_bonus.items():
            lines.append(f"  - {trait}: 上限+{bonus:.0f}")
    
    if organ_bonus:
        lines.append("【器官加成】")
        for trait, bonus in sorted(organ_bonus.items(), key=lambda x: -x[1]):
            if bonus >= 0.5:
                lines.append(f"  - {trait}: 上限+{bonus:.1f}")
    
    summary_text = "\n".join(lines) if lines else "无特殊加成"
    
    return {
        "habitat_bonus": habitat_bonus,
        "organ_bonus": organ_bonus,
        "summary_text": summary_text,
    }


# ==================== 核心预算计算系统 ====================
# 基于设计文档第三章的公式：
# 预算上限 = 基础值 × 时代因子 × 营养级因子 × 体型因子 × 器官因子

# 基础预算值
BASE_BUDGET = 15.0


def get_era_factor(turn_index: int) -> float:
    """计算时代因子，体现演化复杂度的累积
    
    设计理念（基于设计文档2.1的时间线）：
    - 太古宙（0-15）: 缓慢起步，1.0→1.5
    - 元古宙（15-54）: 稳定增长，1.5→4.0
    - 古生代（54-343）: 寒武纪爆发后加速！4.0→25.0
    - 中生代（343-715）: 持续增长，25.0→50.0
    - 新生代（715-979）: 精细演化，50.0→70.0
    - 未来（979+）: 无限可能
    
    Args:
        turn_index: 当前回合数
        
    Returns:
        时代因子（1.0-100+）
    """
    if turn_index <= 15:
        # 太古宙：线性起步
        return 1.0 + (turn_index / 15) * 0.5
    
    elif turn_index <= 54:
        # 元古宙：加速准备
        base = 1.5
        progress = (turn_index - 15) / (54 - 15)
        return base + progress * 2.5  # 1.5 → 4.0
    
    elif turn_index <= 343:
        # 古生代：寒武纪大爆发！指数增长
        base = 4.0
        progress = (turn_index - 54) / (343 - 54)
        # 使用幂函数加速：progress^1.3
        return base + (progress ** 1.3) * 21.0  # 4.0 → 25.0
    
    elif turn_index <= 715:
        # 中生代：稳定增长
        base = 25.0
        progress = (turn_index - 343) / (715 - 343)
        return base + progress * 25.0  # 25.0 → 50.0
    
    elif turn_index <= 979:
        # 新生代：精细演化
        base = 50.0
        progress = (turn_index - 715) / (979 - 715)
        return base + progress * 20.0  # 50.0 → 70.0
    
    else:
        # 未来：持续增长（对数减速）
        base = 70.0
        extra_turns = turn_index - 979
        return base + 15.0 * math.log(1 + extra_turns / 200)


def get_trophic_factor(trophic_level: float) -> float:
    """计算营养级因子
    
    高营养级生物需要更多能力（感知、运动、捕食等）
    
    Args:
        trophic_level: 营养级（1.0-5.5）
        
    Returns:
        营养级因子（0.84-1.92）
        - T1.0 (生产者): 0.84
        - T2.0 (草食): 1.08
        - T3.0 (小肉食): 1.32
        - T4.0 (大肉食): 1.56
        - T5.0 (顶级): 1.80
    """
    return 0.6 + trophic_level * 0.24


def get_size_factor(body_weight_g: float) -> float:
    """计算体型因子（基于克莱伯定律）
    
    大型生物可维持更高属性总和（代谢率 ∝ 体重^0.75）
    
    Args:
        body_weight_g: 体重（克）
        
    Returns:
        体型因子（0.5-1.8）
        - 细菌 (10^-12g): 0.6
        - 单细胞 (10^-6g): 0.75
        - 1g 生物: 1.0
        - 1kg 生物: 1.24
        - 100kg 生物: 1.4
        - 10000kg 生物: 1.56
    """
    if body_weight_g <= 0:
        return 0.6
    
    log_weight = math.log10(body_weight_g)
    # 参考点：1g = 1.0
    factor = 1.0 + 0.08 * max(-5, min(5, log_weight))
    return max(0.5, min(1.8, factor))


def get_organ_factor(organ_count: int, mature_count: int = 0) -> float:
    """计算器官因子
    
    复杂器官系统允许更高属性
    
    Args:
        organ_count: 器官总数
        mature_count: 成熟器官数量（阶段>=3）
        
    Returns:
        器官因子（1.0-1.5）
        - 0器官: 1.0
        - 5器官: 1.1
        - 10器官: 1.2
        - 成熟器官额外 +0.02 每个
    """
    base = 1.0 + min(organ_count, 15) * 0.02
    mature_bonus = min(mature_count, 10) * 0.02
    return min(1.5, base + mature_bonus)


def calculate_budget(
    turn_index: int,
    trophic_level: float = 2.0,
    body_weight_g: float = 1.0,
    organ_count: int = 0,
    mature_organ_count: int = 0,
) -> float:
    """计算属性预算上限
    
    核心公式：预算 = 基础值 × 时代因子 × 营养级因子 × 体型因子 × 器官因子
    
    Args:
        turn_index: 当前回合数
        trophic_level: 营养级
        body_weight_g: 体重（克）
        organ_count: 器官总数
        mature_organ_count: 成熟器官数量
        
    Returns:
        属性预算上限
    """
    era = get_era_factor(turn_index)
    trophic = get_trophic_factor(trophic_level)
    size = get_size_factor(body_weight_g)
    organ = get_organ_factor(organ_count, mature_organ_count)
    
    return BASE_BUDGET * era * trophic * size * organ


def calculate_budget_from_species(species, turn_index: int) -> float:
    """从物种对象计算预算
    
    Args:
        species: 物种对象
        turn_index: 当前回合数
        
    Returns:
        属性预算上限
    """
    trophic_level = getattr(species, 'trophic_level', 2.0) or 2.0
    
    # 获取体重
    morphology = getattr(species, 'morphology_stats', {}) or {}
    body_weight = morphology.get('body_weight_g', 1.0) or 1.0
    
    # 获取器官信息
    organs = getattr(species, 'organs', {}) or {}
    organ_count = len(organs)
    mature_count = sum(1 for o in organs.values() if o.get('stage', 0) >= 3)
    
    return calculate_budget(
        turn_index=turn_index,
        trophic_level=trophic_level,
        body_weight_g=body_weight,
        organ_count=organ_count,
        mature_organ_count=mature_count,
    )


# ==================== 超预算处理 ====================

def find_lowest_priority_trait(traits: dict[str, float]) -> str:
    """找到优先级最低的属性（用于权衡削减）
    
    优先级规则：
    - 社会性、繁殖速度优先削减
    - 核心生存属性（耐寒/耐热/耐旱）尽量保留
    
    Args:
        traits: 属性字典
        
    Returns:
        最低优先级的属性名
    """
    # 属性优先级（数字越小优先级越低，越容易被削减）
    priority_map = {
        "社会性": 1,
        "繁殖速度": 2,
        "运动能力": 3,
        "光照需求": 4,
        "氧气需求": 4,
        "攻击性": 5,
        "防御性": 5,
        "耐酸碱性": 6,
        "耐盐性": 7,
        "耐旱性": 8,
        "耐热性": 9,
        "耐寒性": 10,
    }
    
    # 找到优先级最低且值最高的属性
    candidates = []
    for trait_name, value in traits.items():
        priority = priority_map.get(trait_name, 5)
        candidates.append((priority, -value, trait_name))
    
    if not candidates:
        return list(traits.keys())[0] if traits else "社会性"
    
    # 按优先级升序，值降序排序
    candidates.sort()
    return candidates[0][2]


def handle_budget_overflow(
    traits: dict[str, float],
    budget: float,
    turn_index: int = 0,
) -> tuple[dict[str, float], str, str]:
    """处理属性总和超出预算的情况
    
    处理策略（基于设计文档第八章）：
    - 超出≤15%: 警告但允许（物种特化）
    - 超出15-40%: 自动权衡（削减低优先级属性）
    - 超出>40%: 等比缩放
    
    Args:
        traits: 属性字典
        budget: 预算上限
        turn_index: 当前回合数
        
    Returns:
        (调整后的属性字典, 处理类型, 处理说明)
        处理类型: "normal" | "warning" | "tradeoff" | "scaled"
    """
    current_total = sum(traits.values())
    
    if budget <= 0:
        return traits, "normal", ""
    
    overflow_ratio = current_total / budget - 1.0
    
    if overflow_ratio <= 0:
        return traits, "normal", ""
    
    elif overflow_ratio <= 0.15:
        # 超出≤15%：警告但允许（物种特化）
        return traits, "warning", f"属性略超预算 ({overflow_ratio:.0%})"
    
    elif overflow_ratio <= 0.40:
        # 超出15-40%：自动权衡
        adjusted = dict(traits)
        sacrifice_amount = (current_total - budget) * 0.7
        sacrifice_trait = find_lowest_priority_trait(adjusted)
        
        adjusted[sacrifice_trait] = max(
            1.0,
            adjusted[sacrifice_trait] - sacrifice_amount
        )
        return adjusted, "tradeoff", f"权衡: {sacrifice_trait} 削减 {sacrifice_amount:.1f}"
    
    else:
        # 超出>40%：等比缩放
        adjusted = {}
        scale = (budget * 1.4) / current_total
        for trait_name, value in traits.items():
            adjusted[trait_name] = round(value * scale, 2)
        return adjusted, "scaled", f"属性缩放至 {scale:.0%}"


# ==================== 基因激活检查 ====================

def can_activate_gene(
    species,
    trait_name: str,
    gain_value: float,
    turn_index: int,
) -> tuple[bool, float, str | None]:
    """检查是否可以激活基因
    
    考虑因素：
    1. 边际递减：高属性增益会被削减
    2. 单属性上限：考虑栖息地和器官加成
    3. 总预算：超出过多需要权衡
    
    Args:
        species: 物种对象
        trait_name: 要增强的属性名
        gain_value: 基因潜力值
        turn_index: 当前回合数
        
    Returns:
        (是否可激活, 实际增益, 警告信息)
    """
    traits = getattr(species, 'abstract_traits', {}) or {}
    trophic_level = getattr(species, 'trophic_level', 2.0) or 2.0
    habitat_type = getattr(species, 'habitat_type', 'terrestrial')
    organs = getattr(species, 'organs', {}) or {}
    
    # 计算预算
    budget = calculate_budget_from_species(species, turn_index)
    current_total = sum(traits.values())
    
    # 应用边际递减
    current_value = traits.get(trait_name, 0)
    diminishing = get_diminishing_factor(current_value, turn_index, trophic_level)
    effective_gain = gain_value * diminishing
    
    # 检查单属性上限（考虑加成）
    single_cap = get_effective_trait_cap(
        trait_name, turn_index, trophic_level,
        habitat_type=habitat_type,
        organs=organs
    )
    
    if current_value + effective_gain > single_cap:
        effective_gain = max(0, single_cap - current_value)
    
    # 检查总预算
    new_total = current_total + effective_gain
    overflow = new_total / budget - 1.0 if budget > 0 else 0
    
    warning = None
    if overflow > 0.4:
        warning = "需要权衡"
    elif overflow > 0.15:
        warning = "接近预算上限"
    elif diminishing < 0.5:
        warning = f"边际递减严重 ({diminishing:.0%}效率)"
    
    return True, effective_gain, warning


def get_budget_prompt_context(species, turn_index: int) -> str:
    """为 LLM 生成预算上下文
    
    Args:
        species: 物种对象
        turn_index: 当前回合数
        
    Returns:
        格式化的预算上下文文本
    """
    traits = getattr(species, 'abstract_traits', {}) or {}
    trophic_level = getattr(species, 'trophic_level', 2.0) or 2.0
    
    budget = calculate_budget_from_species(species, turn_index)
    current_total = sum(traits.values())
    single_cap = get_single_trait_cap(turn_index, trophic_level)
    
    remaining = max(0, budget - current_total)
    usage_percent = current_total / budget if budget > 0 else 0
    
    return f"""
【属性预算信息】
- 当前属性总和: {current_total:.0f}
- 预算上限: {budget:.0f}
- 使用率: {usage_percent:.0%}
- 剩余空间: {remaining:.0f}
- 单属性上限: {single_cap:.0f}

【生成基因建议】
- 新基因潜力值范围: 4.0 - {min(10.0, single_cap * 0.4):.1f}
- 建议生成 3-5 个休眠基因（为演化预埋丰富种子）
- 约 80% 有益/中性，20% 轻微有害（提供自然选择原料）
"""


# ==================== 预算系统综合上下文 ====================

def get_full_budget_context(species, turn_index: int) -> dict:
    """获取完整的预算系统上下文（供 prompt 使用）
    
    整合：预算计算、边际递减、突破机会、加成信息
    
    Args:
        species: 物种对象
        turn_index: 当前回合数
        
    Returns:
        完整的预算上下文字典
    """
    traits = getattr(species, 'abstract_traits', {}) or {}
    trophic_level = getattr(species, 'trophic_level', 2.0) or 2.0
    habitat_type = getattr(species, 'habitat_type', 'terrestrial')
    organs = getattr(species, 'organs', {}) or {}
    
    # 1. 基础预算信息
    budget = calculate_budget_from_species(species, turn_index)
    current_total = sum(traits.values())
    single_cap = get_single_trait_cap(turn_index, trophic_level)
    remaining = max(0, budget - current_total)
    usage_percent = current_total / budget if budget > 0 else 0
    
    # 2. 时代因子分解
    era_factor = get_era_factor(turn_index)
    trophic_factor = get_trophic_factor(trophic_level)
    
    # 3. 边际递减摘要
    diminishing = get_diminishing_summary(traits, turn_index, trophic_level)
    
    # 4. 突破摘要
    breakthrough = get_breakthrough_summary(traits, turn_index, trophic_level)
    
    # 5. 加成摘要
    bonus = get_bonus_summary(habitat_type, organs)
    
    # 6. 生成综合文本
    budget_text = f"""【属性预算总览】
- 当前属性总和: {current_total:.0f} / {budget:.0f} ({usage_percent:.0%})
- 剩余空间: {remaining:.0f}
- 单属性上限: {single_cap:.0f}
- 时代因子: {era_factor:.1f} | 营养级因子: {trophic_factor:.2f}"""
    
    return {
        # 数值
        "budget": budget,
        "current_total": current_total,
        "remaining": remaining,
        "usage_percent": usage_percent,
        "single_cap": single_cap,
        "era_factor": era_factor,
        "trophic_factor": trophic_factor,
        # 文本
        "budget_text": budget_text,
        "diminishing_text": diminishing["warning_text"],
        "breakthrough_text": breakthrough["summary_text"],
        "bonus_text": bonus["summary_text"],
        "strategy_hint": diminishing["strategy_hint"],
        # 原始数据
        "_diminishing": diminishing,
        "_breakthrough": breakthrough,
        "_bonus": bonus,
    }