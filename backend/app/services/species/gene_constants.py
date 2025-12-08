"""基因系统常量与类型定义

定义基因库系统的核心常量：
- 压力类型与基因响应映射
- 基因连锁组
- 器官发育阶段
- 显隐性类型
- 有害突变类型
"""
from __future__ import annotations

from enum import Enum
from typing import TypedDict, Literal


# ============================================================
# 1. 压力类型系统 - 细化的环境选择压力
# ============================================================

class PressureCategory(str, Enum):
    """压力大类"""
    TEMPERATURE = "temperature"
    WATER = "water"
    CHEMICAL = "chemical"
    BIOTIC = "biotic"
    RESOURCE = "resource"
    RADIATION = "radiation"
    MECHANICAL = "mechanical"


# 具体压力类型 -> 对应的基因响应
PRESSURE_GENE_MAPPING: dict[str, dict] = {
    # === 温度压力 ===
    "cold": {
        "category": PressureCategory.TEMPERATURE,
        "responsive_traits": ["耐寒性", "代谢调节", "细胞膜稳定"],
        "responsive_organs": ["脂肪层", "毛发", "血管收缩系统"],
        "description": "低温环境压力",
    },
    "heat": {
        "category": PressureCategory.TEMPERATURE,
        "responsive_traits": ["耐热性", "散热能力", "热休克蛋白"],
        "responsive_organs": ["汗腺", "散热鳍", "体表血管"],
        "description": "高温环境压力",
    },
    "temperature_fluctuation": {
        "category": PressureCategory.TEMPERATURE,
        "responsive_traits": ["温度适应性", "昼夜节律"],
        "responsive_organs": ["体温调节中枢"],
        "description": "温度剧烈波动",
    },
    
    # === 水分压力 ===
    "drought": {
        "category": PressureCategory.WATER,
        "responsive_traits": ["耐旱性", "保水能力", "代谢效率"],
        "responsive_organs": ["角质层", "储水组织", "肾脏浓缩"],
        "description": "干旱环境压力",
    },
    "flooding": {
        "category": PressureCategory.WATER,
        "responsive_traits": ["耐淹性", "厌氧代谢"],
        "responsive_organs": ["通气组织", "气孔调节"],
        "description": "水涝环境压力",
    },
    "humidity_high": {
        "category": PressureCategory.WATER,
        "responsive_traits": ["真菌抗性", "表皮透气"],
        "responsive_organs": ["防水层"],
        "description": "高湿环境压力",
    },
    
    # === 化学压力 ===
    "salinity": {
        "category": PressureCategory.CHEMICAL,
        "responsive_traits": ["耐盐性", "渗透调节"],
        "responsive_organs": ["盐腺", "渗透调节器"],
        "description": "高盐环境压力",
    },
    "acidic": {
        "category": PressureCategory.CHEMICAL,
        "responsive_traits": ["耐酸性", "pH缓冲"],
        "responsive_organs": ["酸中和腺"],
        "description": "酸性环境压力",
    },
    "alkaline": {
        "category": PressureCategory.CHEMICAL,
        "responsive_traits": ["耐碱性"],
        "responsive_organs": [],
        "description": "碱性环境压力",
    },
    "toxin": {
        "category": PressureCategory.CHEMICAL,
        "responsive_traits": ["解毒能力", "毒素耐受"],
        "responsive_organs": ["解毒腺", "肝脏强化"],
        "description": "毒素环境压力",
    },
    "heavy_metal": {
        "category": PressureCategory.CHEMICAL,
        "responsive_traits": ["重金属耐受", "金属螯合"],
        "responsive_organs": ["金属储存体"],
        "description": "重金属污染压力",
    },
    
    # === 生物压力 ===
    "predation": {
        "category": PressureCategory.BIOTIC,
        "responsive_traits": ["逃避能力", "警觉性", "伪装"],
        "responsive_organs": ["逃逸肌肉", "警戒感官", "保护色素"],
        "description": "捕食压力",
    },
    "hunting": {
        "category": PressureCategory.BIOTIC,
        "responsive_traits": ["捕猎本能", "追踪能力", "埋伏技巧"],
        "responsive_organs": ["捕食附肢", "毒腺", "锐利齿"],
        "description": "捕猎效率压力",
    },
    "competition": {
        "category": PressureCategory.BIOTIC,
        "responsive_traits": ["竞争力", "领地意识", "资源利用效率"],
        "responsive_organs": ["展示器官", "战斗器官"],
        "description": "种间/种内竞争",
    },
    "disease": {
        "category": PressureCategory.BIOTIC,
        "responsive_traits": ["免疫力", "病原抗性"],
        "responsive_organs": ["免疫系统", "抗菌腺"],
        "description": "疾病压力",
    },
    "parasitism": {
        "category": PressureCategory.BIOTIC,
        "responsive_traits": ["寄生虫抗性", "清洁行为"],
        "responsive_organs": ["粘液层", "免疫细胞"],
        "description": "寄生虫压力",
    },
    
    # === 资源压力 ===
    "starvation": {
        "category": PressureCategory.RESOURCE,
        "responsive_traits": ["代谢效率", "能量储存", "休眠能力"],
        "responsive_organs": ["储能组织", "消化效率器官"],
        "description": "食物匮乏压力",
    },
    "light_limitation": {
        "category": PressureCategory.RESOURCE,
        "responsive_traits": ["光合效率", "弱光适应"],
        "responsive_organs": ["增强叶绿体", "光捕获天线"],
        "description": "光照不足压力（生产者）",
    },
    "nutrient_poor": {
        "category": PressureCategory.RESOURCE,
        "responsive_traits": ["营养吸收", "固氮能力"],
        "responsive_organs": ["根毛强化", "共生结构"],
        "description": "营养贫瘠压力",
    },
    "oxygen_low": {
        "category": PressureCategory.RESOURCE,
        "responsive_traits": ["厌氧能力", "血红蛋白效率"],
        "responsive_organs": ["辅助呼吸器", "气囊"],
        "description": "低氧环境压力",
    },
    
    # === 辐射压力 ===
    "uv_radiation": {
        "category": PressureCategory.RADIATION,
        "responsive_traits": ["UV抗性", "DNA修复"],
        "responsive_organs": ["色素层", "UV防护膜"],
        "description": "紫外线辐射压力",
    },
    
    # === 机械压力 ===
    "pressure_deep": {
        "category": PressureCategory.MECHANICAL,
        "responsive_traits": ["耐压能力", "骨骼强化"],
        "responsive_organs": ["耐压细胞壁", "压力平衡器"],
        "description": "深海高压环境",
    },
    "abrasion": {
        "category": PressureCategory.MECHANICAL,
        "responsive_traits": ["表皮强度", "再生能力"],
        "responsive_organs": ["硬化表皮", "再生组织"],
        "description": "物理磨损压力",
    },
}

# 通用/兼容压力（向后兼容旧数据）
LEGACY_PRESSURE_MAPPING = {
    "adaptive": ["competition", "starvation"],
    "environment": ["temperature_fluctuation", "drought"],
    "temperature": ["cold", "heat"],
    "humidity": ["drought", "humidity_high"],
    "osmotic": ["salinity"],
    "foraging": ["starvation", "competition"],
    "locomotion": ["predation", "hunting"],
    "defense": ["predation"],
    "depth": ["pressure_deep", "oxygen_low"],
    "navigation": ["predation", "hunting"],
    "damage": ["abrasion", "disease"],
    "stress": ["starvation", "competition", "disease"],
    "chemosynthesis": ["oxygen_low", "toxin"],
    "amphibious": ["drought", "flooding"],
    "respiration": ["oxygen_low"],
    "oxygen": ["oxygen_low"],
    "protection": ["predation", "abrasion"],
    "resource": ["starvation", "nutrient_poor"],
    "light": ["light_limitation", "uv_radiation"],
}


# ============================================================
# 2. 基因连锁组 - 相关基因一起激活/代价
# ============================================================

class GeneLinkageGroup(TypedDict):
    """基因连锁组定义"""
    primary: str  # 主基因
    linked: list[str]  # 连锁基因（一起激活）
    tradeoff: list[tuple[str, float]]  # 代价（特质名, 扣减值）


GENE_LINKAGE_GROUPS: list[GeneLinkageGroup] = [
    # 温度适应连锁
    {
        "primary": "耐寒性",
        "linked": ["代谢调节"],
        "tradeoff": [("耐热性", -1.5)],  # 耐寒与耐热互斥
    },
    {
        "primary": "耐热性",
        "linked": ["散热能力"],
        "tradeoff": [("耐寒性", -1.5)],
    },
    
    # 运动-能量连锁
    {
        "primary": "运动能力",
        "linked": ["肌肉发达"],
        "tradeoff": [("代谢效率", -1.0)],  # 高运动=高能耗
    },
    {
        "primary": "捕猎本能",
        "linked": ["追踪能力", "攻击性"],
        "tradeoff": [("繁殖速度", -0.5)],  # 顶级捕食者繁殖慢
    },
    
    # 防御-速度连锁
    {
        "primary": "防护外壳",
        "linked": ["表皮强度"],
        "tradeoff": [("运动能力", -1.5), ("灵活性", -1.0)],  # 重甲=慢
    },
    
    # 光合-水分连锁（植物）
    {
        "primary": "光合效率",
        "linked": ["叶绿体密度"],
        "tradeoff": [("耐旱性", -0.5)],  # 高光合需要更多水分
    },
    
    # 感知-能量连锁
    {
        "primary": "感知敏锐",
        "linked": ["神经发达"],
        "tradeoff": [("代谢效率", -0.3)],  # 复杂神经系统消耗能量
    },
    
    # 繁殖-寿命连锁
    {
        "primary": "繁殖速度",
        "linked": [],
        "tradeoff": [("寿命", -1.0)],  # r策略 vs K策略
    },
    
    # 体型连锁
    {
        "primary": "体型增大",
        "linked": ["力量"],
        "tradeoff": [("繁殖速度", -1.0), ("隐蔽性", -1.5)],
    },
]

# 按主基因名建立索引
LINKAGE_INDEX = {g["primary"]: g for g in GENE_LINKAGE_GROUPS}


# ============================================================
# 3. 器官发育阶段
# ============================================================

class OrganStage(int, Enum):
    """器官发育阶段"""
    PRIMORDIUM = 0      # 原基 - 细胞分化开始
    PRIMITIVE = 1       # 初级结构 - 基础形态形成
    FUNCTIONAL = 2      # 功能原型 - 开始发挥部分功能
    MATURE = 3          # 成熟器官 - 完整功能


# 器官发育参数（快速进化版本：总计2-5回合成熟）
ORGAN_DEVELOPMENT_CONFIG = {
    # 每阶段的功能效率（0-1）
    "efficiency_by_stage": {
        OrganStage.PRIMORDIUM: 0.0,     # 原基无功能
        OrganStage.PRIMITIVE: 0.30,     # 30% 效率（提升）
        OrganStage.FUNCTIONAL: 0.70,    # 70% 效率（提升）
        OrganStage.MATURE: 1.0,         # 100% 效率
    },
    # 每阶段发育所需回合数（快速发育：总计2-5回合）
    # 实际使用时会随机化：random.randint(min, max)
    "turns_per_stage": {
        OrganStage.PRIMORDIUM: 1,       # 原基 -> 初级: 1回合
        OrganStage.PRIMITIVE: 1,        # 初级 -> 功能: 1回合
        OrganStage.FUNCTIONAL: 1,       # 功能 -> 成熟: 1回合（高压力下可跳过）
    },
    # 发育所需回合数范围（用于随机化）
    "turns_per_stage_range": {
        OrganStage.PRIMORDIUM: (0, 1),  # 0-1回合（可能直接跳过原基期）
        OrganStage.PRIMITIVE: (1, 2),   # 1-2回合
        OrganStage.FUNCTIONAL: (1, 2),  # 1-2回合
    },
    # 发育失败概率（每阶段）- 降低失败率
    "failure_chance": {
        OrganStage.PRIMORDIUM: 0.08,    # 8% 概率发育失败（降低）
        OrganStage.PRIMITIVE: 0.05,     # 5%（降低）
        OrganStage.FUNCTIONAL: 0.02,    # 2%（降低）
    },
}


# ============================================================
# 4. 显隐性遗传类型
# ============================================================

class DominanceType(str, Enum):
    """显隐性类型"""
    RECESSIVE = "recessive"           # 隐性 - 需要纯合才表达
    CODOMINANT = "codominant"         # 共显性 - 中间表型
    DOMINANT = "dominant"             # 显性 - 杂合即表达
    OVERDOMINANT = "overdominant"     # 超显性 - 杂合优势


# 显隐性对表达值的影响系数
DOMINANCE_EXPRESSION_FACTOR = {
    DominanceType.RECESSIVE: 0.25,      # 隐性：25% 表达（模拟低频表达）
    DominanceType.CODOMINANT: 0.60,     # 共显性：60% 表达
    DominanceType.DOMINANT: 1.0,        # 显性：100% 表达
    DominanceType.OVERDOMINANT: 1.15,   # 超显性：115% 表达（杂合优势）
}

# 各类型基因的显隐性分布概率
DOMINANCE_DISTRIBUTION = {
    "trait": {
        DominanceType.RECESSIVE: 0.30,
        DominanceType.CODOMINANT: 0.40,
        DominanceType.DOMINANT: 0.25,
        DominanceType.OVERDOMINANT: 0.05,
    },
    "organ": {
        DominanceType.RECESSIVE: 0.20,
        DominanceType.CODOMINANT: 0.50,
        DominanceType.DOMINANT: 0.25,
        DominanceType.OVERDOMINANT: 0.05,
    },
}


# ============================================================
# 5. 有害突变类型
# ============================================================

class MutationEffect(str, Enum):
    """突变效果类型"""
    BENEFICIAL = "beneficial"         # 有益
    NEUTRAL = "neutral"               # 中性
    MILDLY_HARMFUL = "mildly_harmful" # 轻微有害
    HARMFUL = "harmful"               # 有害
    LETHAL = "lethal"                 # 致死（纯合致死）


# 突变效果分布（符合真实生物学：大多数突变是中性或有害的）
MUTATION_EFFECT_DISTRIBUTION = {
    MutationEffect.BENEFICIAL: 0.05,      # 5% 有益
    MutationEffect.NEUTRAL: 0.45,         # 45% 中性
    MutationEffect.MILDLY_HARMFUL: 0.30,  # 30% 轻微有害
    MutationEffect.HARMFUL: 0.15,         # 15% 有害
    MutationEffect.LETHAL: 0.05,          # 5% 致死
}

# 有害突变类型及其效果
HARMFUL_MUTATIONS: list[dict] = [
    # 代谢缺陷
    {
        "name": "代谢缺陷",
        "effect": MutationEffect.HARMFUL,
        "target_trait": "代谢效率",
        "value_modifier": -2.0,
        "description": "代谢途径异常，能量转化效率下降",
    },
    {
        "name": "线粒体功能障碍",
        "effect": MutationEffect.MILDLY_HARMFUL,
        "target_trait": "代谢效率",
        "value_modifier": -1.0,
        "description": "线粒体功能轻微受损",
    },
    
    # 免疫缺陷
    {
        "name": "免疫缺陷",
        "effect": MutationEffect.HARMFUL,
        "target_trait": "免疫力",
        "value_modifier": -3.0,
        "description": "免疫系统发育不全",
    },
    
    # 感知缺陷
    {
        "name": "感知迟钝",
        "effect": MutationEffect.MILDLY_HARMFUL,
        "target_trait": "感知敏锐",
        "value_modifier": -1.5,
        "description": "感觉器官功能减退",
    },
    {
        "name": "色盲",
        "effect": MutationEffect.NEUTRAL,  # 很多情况下影响不大
        "target_trait": "视觉",
        "value_modifier": -0.5,
        "description": "色觉异常",
    },
    
    # 繁殖缺陷
    {
        "name": "繁殖障碍",
        "effect": MutationEffect.HARMFUL,
        "target_trait": "繁殖速度",
        "value_modifier": -2.5,
        "description": "生殖系统发育异常",
    },
    {
        "name": "孵化率下降",
        "effect": MutationEffect.MILDLY_HARMFUL,
        "target_trait": "繁殖速度",
        "value_modifier": -1.0,
        "description": "胚胎发育成功率降低",
    },
    
    # 运动缺陷
    {
        "name": "运动协调障碍",
        "effect": MutationEffect.HARMFUL,
        "target_trait": "运动能力",
        "value_modifier": -2.0,
        "description": "神经肌肉协调异常",
    },
    
    # 环境适应缺陷
    {
        "name": "温度敏感",
        "effect": MutationEffect.MILDLY_HARMFUL,
        "target_trait": "耐热性",
        "value_modifier": -1.5,
        "description": "热应激蛋白表达异常",
    },
    {
        "name": "渗透失调",
        "effect": MutationEffect.MILDLY_HARMFUL,
        "target_trait": "耐盐性",
        "value_modifier": -1.5,
        "description": "渗透压调节功能异常",
    },
    
    # 致死突变（纯合时致死）
    {
        "name": "发育停滞",
        "effect": MutationEffect.LETHAL,
        "target_trait": None,  # 不影响具体特质，直接影响存活
        "value_modifier": 0,
        "lethal_when_homozygous": True,
        "description": "纯合时胚胎发育停滞",
    },
]


# ============================================================
# 6. 水平基因转移 (HGT) 配置
# ============================================================

HGT_CONFIG = {
    # HGT 仅发生在营养级 < 1.5 的物种（原核生物/简单真核）
    "max_trophic_level": 1.5,
    
    # 每回合 HGT 发生概率
    "base_chance_per_turn": 0.12,
    
    # 同域物种 HGT 概率加成
    "sympatric_bonus": 0.08,
    
    # 可通过 HGT 转移的基因类型
    "transferable_traits": [
        "耐热性", "耐盐性", "毒素耐受", "抗生素抗性",
        "代谢效率", "化能利用", "固氮能力", "光合效率",
    ],
    
    # HGT 转移效率（获得原基因值的比例）
    "transfer_efficiency": (0.5, 0.8),  # 50-80%
    
    # 转移后的稳定概率（基因是否能稳定整合）
    "integration_stability": 0.70,
}


# ============================================================
# 7. 辅助函数
# ============================================================

def get_pressure_response(pressure_type: str) -> dict | None:
    """获取压力类型对应的基因响应"""
    # 首先查找直接映射
    if pressure_type in PRESSURE_GENE_MAPPING:
        return PRESSURE_GENE_MAPPING[pressure_type]
    
    # 查找兼容映射
    if pressure_type in LEGACY_PRESSURE_MAPPING:
        mapped = LEGACY_PRESSURE_MAPPING[pressure_type]
        if mapped:
            return PRESSURE_GENE_MAPPING.get(mapped[0])
    
    return None


def get_linkage_group(trait_name: str) -> GeneLinkageGroup | None:
    """获取特质的连锁组"""
    return LINKAGE_INDEX.get(trait_name)


def roll_dominance(gene_type: Literal["trait", "organ"]) -> DominanceType:
    """随机决定基因的显隐性"""
    import random
    distribution = DOMINANCE_DISTRIBUTION.get(gene_type, DOMINANCE_DISTRIBUTION["trait"])
    roll = random.random()
    cumulative = 0.0
    for dom_type, prob in distribution.items():
        cumulative += prob
        if roll < cumulative:
            return dom_type
    return DominanceType.CODOMINANT


def roll_mutation_effect() -> MutationEffect:
    """随机决定突变效果类型"""
    import random
    roll = random.random()
    cumulative = 0.0
    for effect_type, prob in MUTATION_EFFECT_DISTRIBUTION.items():
        cumulative += prob
        if roll < cumulative:
            return effect_type
    return MutationEffect.NEUTRAL


def get_random_harmful_mutation() -> dict | None:
    """随机获取一个有害突变"""
    import random
    harmful_list = [m for m in HARMFUL_MUTATIONS if m["effect"] in 
                    (MutationEffect.MILDLY_HARMFUL, MutationEffect.HARMFUL, MutationEffect.LETHAL)]
    if harmful_list:
        return random.choice(harmful_list)
    return None


def is_hgt_eligible(species) -> bool:
    """判断物种是否符合 HGT 条件"""
    trophic = getattr(species, "trophic_level", 2.0) or 2.0
    return trophic <= HGT_CONFIG["max_trophic_level"]
