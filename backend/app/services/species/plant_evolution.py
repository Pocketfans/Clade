"""植物演化核心逻辑

【设计原则】
- 与动物演化路径分离
- 阶段递进式演化
- 里程碑驱动的重大突破
- 与Embedding系统集成
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Sequence

import numpy as np

if TYPE_CHECKING:
    from ...models.species import Species
    from ...ai.model_router import ModelRouter
    from ..system.embedding import EmbeddingService

logger = logging.getLogger(__name__)


# ==================== 植物演化里程碑定义 ====================

@dataclass
class PlantMilestone:
    """植物演化里程碑"""
    id: str
    name: str
    from_stage: int | None = None  # 起始阶段（None表示形态里程碑）
    to_stage: int | None = None    # 目标阶段
    requirements: dict[str, float] = field(default_factory=dict)
    unlock_organs: list[str] = field(default_factory=list)
    unlock_traits: list[str] = field(default_factory=list)
    achievement: str | None = None  # 解锁的成就ID
    narrative: str = ""


# 里程碑配置
PLANT_MILESTONES: dict[str, PlantMilestone] = {
    # ========== 阶段升级里程碑 ==========
    "first_eukaryote": PlantMilestone(
        id="first_eukaryote",
        name="真核化",
        from_stage=0,
        to_stage=1,
        requirements={"多细胞程度": 1.5},
        unlock_organs=["叶绿体"],
        narrative="生命史上的重大飞跃：真核细胞的诞生，细胞核和叶绿体的形成开启了复杂生命的新纪元"
    ),
    "first_multicellular": PlantMilestone(
        id="first_multicellular",
        name="多细胞化",
        from_stage=1,
        to_stage=2,
        requirements={"多细胞程度": 3.0},
        unlock_organs=["类囊体膜"],
        narrative="细胞开始协作，形成原始组织，生命的复杂性迈上新台阶"
    ),
    # 【新增】沿岸过渡里程碑 - 登陆的前置准备
    "coastal_pioneer": PlantMilestone(
        id="coastal_pioneer",
        name="沿岸先驱",
        from_stage=2,
        to_stage=2,  # 不升阶段，但获得过渡能力
        requirements={"保水能力": 3.0, "耐旱性": 2.5},
        unlock_organs=["气囊组织"],  # 潮间带浮力/缓冲结构
        narrative="开始适应潮间带的干湿交替环境，发展出原始保水结构，为真正登陆做准备"
    ),
    "first_land_plant": PlantMilestone(
        id="first_land_plant",
        name="植物登陆",
        from_stage=2,
        to_stage=3,
        requirements={"保水能力": 5.0, "耐旱性": 4.0},
        unlock_organs=["假根", "角质层"],
        achievement="开荒先锋",
        narrative="生命征服陆地的第一步，角质层和假根的演化使植物能够抵抗干燥和紫外线"
    ),
    "first_true_root": PlantMilestone(
        id="first_true_root",
        name="真根演化",
        from_stage=3,
        to_stage=4,
        requirements={"根系发达度": 5.0},
        unlock_organs=["原始根", "维管束"],
        narrative="真正的根系深入土壤，维管束的形成实现了高效的水分和养分运输"
    ),
    "first_seed": PlantMilestone(
        id="first_seed",
        name="种子革命",
        from_stage=4,
        to_stage=5,
        requirements={"种子化程度": 5.0},
        unlock_organs=["球果", "胚珠"],
        narrative="种子的诞生让植物摆脱了对水的繁殖依赖，可以征服更干燥的陆地"
    ),
    "first_flower": PlantMilestone(
        id="first_flower",
        name="开花时代",
        from_stage=5,
        to_stage=6,
        requirements={"种子化程度": 8.0, "散布能力": 7.0},
        unlock_organs=["花", "果实"],
        achievement="繁花似锦",
        narrative="被子植物登场，花与昆虫的共同演化开启了生命最绚烂的篇章"
    ),
    
    # ========== 形态里程碑（无阶段变化）==========
    "first_tree": PlantMilestone(
        id="first_tree",
        name="首棵树木",
        from_stage=None,
        to_stage=None,
        requirements={"木质化程度": 7.0},
        unlock_organs=["乔木干"],
        achievement="参天巨木",
        narrative="第一棵真正的树木诞生，森林生态系统的奠基者，改变了陆地的面貌"
    ),
}


# ==================== 植物器官定义（混合模式）====================
#
# 【设计理念】
# 采用"框架内自由发挥"模式：
# 1. 里程碑器官（MILESTONE_REQUIRED_ORGANS）是必须获得的，由系统自动解锁
# 2. 参考器官（PLANT_ORGANS）提供模板和数值参考
# 3. 自定义器官：LLM可以在类别框架内创造新结构名称
#
# 【规则】
# - 器官类别是固定的（6个）
# - 每个类别有最低阶段限制
# - 里程碑解锁的器官必须获得
# - 其他器官可以自由命名，参数在合理范围内

# 里程碑必须解锁的核心器官（不可替代）
MILESTONE_REQUIRED_ORGANS = {
    "first_eukaryote": ["叶绿体"],
    "first_multicellular": ["类囊体膜"],
    "coastal_pioneer": ["气囊组织"],  # 【新增】沿岸过渡
    "first_land_plant": ["假根", "角质层"],
    "first_true_root": ["原始根", "维管束"],
    "first_seed": ["胚珠"],
    "first_flower": ["花", "果实"],
    "first_tree": ["乔木干"],
}

# 器官类别配置（允许自定义的框架）
PLANT_ORGAN_CATEGORIES = {
    "photosynthetic": {
        "name": "光合器官",
        "min_stage": 0,
        "required_params": ["efficiency"],
        "param_ranges": {"efficiency": [0.1, 5.0]},
        "examples": ["原始色素体", "叶绿体", "类囊体膜", "真叶", "阔叶", "复叶", "羽状叶"],
        "allow_custom": True,
        "description": "负责光合作用的器官，从简单色素到复杂叶片",
    },
    "root_system": {
        "name": "根系",
        "min_stage": 3,  # 登陆后才有
        "required_params": ["depth_cm", "absorption"],
        "param_ranges": {"depth_cm": [0.1, 500], "absorption": [0.1, 2.0]},
        "examples": ["假根", "原始根", "须根系", "直根系", "气生根", "支柱根", "呼吸根"],
        "allow_custom": True,
        "description": "吸收水分和养分的器官，水生植物无此结构",
    },
    "stem": {
        "name": "茎/支撑",
        "min_stage": 3,
        "required_params": ["height_cm", "support"],
        "param_ranges": {"height_cm": [0.1, 10000], "support": [0.1, 3.0]},
        "examples": ["匍匐茎", "草本茎", "木质茎", "乔木干", "藤本茎", "肉质茎", "块茎"],
        "allow_custom": True,
        "description": "支撑和运输的器官，决定植物高度",
    },
    "reproductive": {
        "name": "繁殖器官",
        "min_stage": 3,
        "required_params": ["dispersal_km"],
        "param_ranges": {"dispersal_km": [0.01, 100]},
        "examples": ["孢子囊", "胚珠", "球果", "花", "果实", "种荚", "浆果", "翅果"],
        "allow_custom": True,
        "description": "繁殖相关器官，从孢子到种子到果实",
    },
    "protection": {
        "name": "保护结构",
        "min_stage": 0,
        "required_params": ["uv_resist"],
        "optional_params": ["drought_resist", "cold_resist", "herbivore_resist"],
        "param_ranges": {
            "uv_resist": [0.0, 3.0],
            "drought_resist": [0.0, 3.0],
            "cold_resist": [0.0, 3.0],
            "herbivore_resist": [0.0, 3.0],
        },
        "examples": ["粘液层", "角质层", "蜡质表皮", "树皮", "刺毛", "硅化表皮", "荧光色素层"],
        "allow_custom": True,
        "description": "保护植物免受环境和捕食压力",
    },
    "vascular": {
        "name": "维管系统",
        "min_stage": 4,
        "required_params": ["transport"],
        "param_ranges": {"transport": [0.1, 3.0]},
        "examples": ["原始维管束", "维管束", "次生木质部", "筛管", "导管"],
        "allow_custom": True,
        "description": "水分和养分的长距离运输系统",
    },
    "storage": {
        "name": "储存器官",
        "min_stage": 3,
        "required_params": ["capacity"],
        "param_ranges": {"capacity": [0.1, 5.0]},
        "examples": ["块根", "块茎", "鳞茎", "球茎", "储水组织"],
        "allow_custom": True,
        "description": "储存水分、养分或能量的器官（LLM自由发挥）",
    },
    "defense": {
        "name": "防御结构",
        "min_stage": 3,
        "required_params": ["defense_power"],
        "param_ranges": {"defense_power": [0.1, 3.0]},
        "examples": ["毒腺", "刺", "毛刺", "单宁囊", "乳汁管", "树脂道"],
        "allow_custom": True,
        "description": "主动防御食草动物的结构（LLM自由发挥）",
    },
}

# 参考器官（提供数值模板，LLM可以参考或自创）
PLANT_ORGANS = {
    # 光合器官
    "photosynthetic": {
        "原始色素体": {"efficiency": 0.5, "min_stage": 0},
        "叶绿体": {"efficiency": 1.0, "min_stage": 1},
        "类囊体膜": {"efficiency": 1.5, "min_stage": 2},
        "原始叶片": {"efficiency": 2.0, "min_stage": 3},
        "真叶": {"efficiency": 3.0, "min_stage": 4},
        "针叶": {"efficiency": 2.5, "min_stage": 5},
        "阔叶": {"efficiency": 3.5, "min_stage": 6},
    },
    
    # 根系
    "root_system": {
        "假根": {"depth_cm": 0.5, "absorption": 0.3, "min_stage": 3},
        "原始根": {"depth_cm": 5, "absorption": 0.5, "min_stage": 4},
        "须根系": {"depth_cm": 30, "absorption": 0.8, "min_stage": 5},
        "直根系": {"depth_cm": 100, "absorption": 1.0, "min_stage": 5},
    },
    
    # 茎/支撑
    "stem": {
        "匍匐茎": {"height_cm": 1, "support": 0.2, "min_stage": 3},
        "草本茎": {"height_cm": 50, "support": 0.5, "min_stage": 4},
        "木质茎": {"height_cm": 500, "support": 1.0, "min_stage": 5},
        "乔木干": {"height_cm": 3000, "support": 2.0, "min_stage": 5},
    },
    
    # 繁殖器官
    "reproductive": {
        "孢子囊": {"dispersal_km": 0.1, "min_stage": 3},
        "胚珠": {"dispersal_km": 0.2, "min_stage": 5},
        "球果": {"dispersal_km": 0.5, "min_stage": 5},
        "花": {"dispersal_km": 2.0, "min_stage": 6},
        "果实": {"dispersal_km": 5.0, "min_stage": 6},
    },
    
    # 保护结构
    "protection": {
        "粘液层": {"uv_resist": 0.5, "drought_resist": 0.3, "min_stage": 0},
        "细胞壁加厚": {"uv_resist": 0.8, "drought_resist": 0.5, "min_stage": 2},
        "角质层": {"uv_resist": 1.0, "drought_resist": 0.8, "min_stage": 3},
        "蜡质表皮": {"uv_resist": 1.5, "drought_resist": 1.0, "min_stage": 4},
        "树皮": {"uv_resist": 2.0, "drought_resist": 1.5, "min_stage": 5},
    },
    
    # 维管系统
    "vascular": {
        "原始维管束": {"transport": 0.5, "min_stage": 4},
        "维管束": {"transport": 1.0, "min_stage": 4},
        "次生木质部": {"transport": 1.5, "min_stage": 5},
    },
    
    # 储存器官（新增，供LLM参考）
    "storage": {
        "块根": {"capacity": 1.0, "min_stage": 4},
        "块茎": {"capacity": 1.2, "min_stage": 4},
        "鳞茎": {"capacity": 1.5, "min_stage": 5},
    },
    
    # 防御结构（新增，供LLM参考）
    "defense": {
        "刺": {"defense_power": 0.5, "min_stage": 3},
        "毒腺": {"defense_power": 1.0, "min_stage": 4},
        "乳汁管": {"defense_power": 0.8, "min_stage": 4},
    },
}


class PlantEvolutionService:
    """植物演化服务
    
    核心功能：
    1. 判定物种是否为植物
    2. 检查里程碑触发条件
    3. 处理阶段升级
    4. 管理植物器官演化
    5. 【新增】Embedding辅助演化预测
    """
    
    def __init__(
        self, 
        router: 'ModelRouter | None' = None,
        embedding_service: 'EmbeddingService | None' = None
    ):
        self.router = router
        self._embeddings = embedding_service
        self._milestone_cache: dict[str, bool] = {}
        
        # 阶段原型向量缓存
        self._stage_vectors: dict[int, 'np.ndarray'] = {}
    
    def set_embedding_service(self, embedding_service: 'EmbeddingService') -> None:
        """设置Embedding服务"""
        self._embeddings = embedding_service
    
    def is_plant(self, species: 'Species') -> bool:
        """判定物种是否为植物"""
        from .trait_config import PlantTraitConfig
        return PlantTraitConfig.is_plant(species)
    
    def get_current_stage(self, species: 'Species') -> int:
        """获取物种当前的演化阶段"""
        return getattr(species, 'life_form_stage', 0)
    
    def get_growth_form(self, species: 'Species') -> str:
        """获取物种的生长形式"""
        return getattr(species, 'growth_form', 'aquatic')
    
    # ==================== 自定义器官验证（混合模式核心）====================
    
    def validate_custom_organ(
        self,
        category: str,
        organ_name: str,
        parameters: dict[str, float],
        current_stage: int
    ) -> tuple[bool, str, dict[str, float]]:
        """验证LLM提出的自定义器官是否合法
        
        【混合模式核心逻辑】
        - 类别必须是预定义的
        - 参数范围必须在合理区间内
        - 阶段限制必须满足
        - 名称可以是自定义的（创意空间）
        
        Args:
            category: 器官类别（如photosynthetic, root_system等）
            organ_name: 器官名称（可以是自定义的）
            parameters: 器官参数（如{"efficiency": 2.5}）
            current_stage: 物种当前演化阶段
            
        Returns:
            (是否合法, 原因说明, 修正后的参数)
        """
        # 检查类别是否存在
        if category not in PLANT_ORGAN_CATEGORIES:
            return False, f"未知器官类别: {category}", {}
        
        cat_config = PLANT_ORGAN_CATEGORIES[category]
        
        # 检查阶段限制
        min_stage = cat_config.get("min_stage", 0)
        if current_stage < min_stage:
            stage_name = self._get_stage_name_safe(min_stage)
            return False, f"需要达到{stage_name}阶段(stage {min_stage})才能拥有{cat_config['name']}", {}
        
        # 检查必需参数
        required_params = cat_config.get("required_params", [])
        for param in required_params:
            if param not in parameters:
                # 尝试从参考器官获取默认值
                default_val = self._get_default_param(category, param)
                parameters[param] = default_val
        
        # 验证并修正参数范围
        corrected = {}
        param_ranges = cat_config.get("param_ranges", {})
        for param, value in parameters.items():
            if param in param_ranges:
                min_val, max_val = param_ranges[param]
                corrected[param] = max(min_val, min(max_val, value))
            else:
                corrected[param] = value
        
        # 添加min_stage
        corrected["min_stage"] = min_stage
        
        return True, "合法的自定义器官", corrected
    
    def is_milestone_required_organ(self, organ_name: str) -> tuple[bool, str | None]:
        """检查器官是否是里程碑必需器官
        
        Args:
            organ_name: 器官名称
            
        Returns:
            (是否是必需器官, 关联的里程碑ID)
        """
        for milestone_id, organs in MILESTONE_REQUIRED_ORGANS.items():
            if organ_name in organs:
                return True, milestone_id
        return False, None
    
    def get_organ_category_info_for_prompt(self, current_stage: int) -> str:
        """生成器官类别信息供Prompt使用
        
        Args:
            current_stage: 当前阶段，用于过滤可用类别
            
        Returns:
            格式化的器官类别说明文本
        """
        lines = ["=== 可用器官类别（可以自由命名，参数需在范围内）==="]
        
        for cat_id, cat_config in PLANT_ORGAN_CATEGORIES.items():
            min_stage = cat_config.get("min_stage", 0)
            if min_stage > current_stage:
                continue  # 当前阶段不可用
            
            name = cat_config["name"]
            examples = ", ".join(cat_config.get("examples", [])[:4])
            param_ranges = cat_config.get("param_ranges", {})
            
            param_str = ", ".join([f"{k}: {v[0]}-{v[1]}" for k, v in param_ranges.items()])
            
            lines.append(f"\n【{name}】(category: {cat_id})")
            lines.append(f"  参考结构: {examples}...")
            lines.append(f"  参数范围: {param_str}")
            lines.append(f"  说明: {cat_config.get('description', '')}")
            lines.append(f"  💡 可自定义名称，如发展出独特的适应性结构")
        
        return "\n".join(lines)
    
    def merge_organ_into_species(
        self,
        species: 'Species',
        category: str,
        organ_name: str,
        parameters: dict[str, float]
    ) -> bool:
        """将验证通过的器官合并到物种
        
        Args:
            species: 物种对象
            category: 器官类别
            organ_name: 器官名称
            parameters: 器官参数
            
        Returns:
            是否成功合并
        """
        current_stage = self.get_current_stage(species)
        
        # 先验证
        valid, reason, corrected_params = self.validate_custom_organ(
            category, organ_name, parameters, current_stage
        )
        
        if not valid:
            logger.warning(f"[PlantEvolution] 器官验证失败: {reason}")
            return False
        
        # 获取或初始化植物器官
        plant_organs = getattr(species, 'plant_organs', None)
        if plant_organs is None:
            plant_organs = {}
        elif not isinstance(plant_organs, dict):
            plant_organs = {}
        
        # 合并器官
        if category not in plant_organs:
            plant_organs[category] = {}
        
        plant_organs[category][organ_name] = corrected_params
        species.plant_organs = plant_organs
        
        logger.debug(f"[PlantEvolution] 合并器官: {organ_name} -> {category}")
        return True
    
    def _get_default_param(self, category: str, param: str) -> float:
        """获取参数的默认值"""
        # 尝试从参考器官获取
        if category in PLANT_ORGANS:
            for organ_data in PLANT_ORGANS[category].values():
                if param in organ_data:
                    return organ_data[param]
        
        # 返回类别的最小值
        if category in PLANT_ORGAN_CATEGORIES:
            ranges = PLANT_ORGAN_CATEGORIES[category].get("param_ranges", {})
            if param in ranges:
                return ranges[param][0]  # 返回最小值
        
        return 1.0  # 默认
    
    def _get_stage_name_safe(self, stage: int) -> str:
        """安全获取阶段名称"""
        names = {
            0: "原核生物",
            1: "真核生物", 
            2: "群体藻类",
            3: "苔藓植物",
            4: "蕨类植物",
            5: "裸子植物",
            6: "被子植物",
        }
        return names.get(stage, f"阶段{stage}")
    
    def check_milestone_requirements(
        self,
        species: 'Species',
        milestone_id: str
    ) -> tuple[bool, float, list[str]]:
        """检查物种是否满足里程碑条件
        
        Args:
            species: 物种对象
            milestone_id: 里程碑ID
            
        Returns:
            (是否满足, 满足度0-1, 未满足的条件列表)
        """
        if milestone_id not in PLANT_MILESTONES:
            return False, 0.0, [f"未知里程碑: {milestone_id}"]
        
        milestone = PLANT_MILESTONES[milestone_id]
        current_stage = self.get_current_stage(species)
        
        # 检查阶段前置条件
        if milestone.from_stage is not None:
            if current_stage != milestone.from_stage:
                return False, 0.0, [f"需要在阶段{milestone.from_stage}，当前阶段{current_stage}"]
        
        # 检查特质条件
        traits = species.abstract_traits or {}
        unmet = []
        met_count = 0
        total_count = len(milestone.requirements)
        
        for trait_name, required_value in milestone.requirements.items():
            actual_value = traits.get(trait_name, 0.0)
            if actual_value >= required_value:
                met_count += 1
            else:
                unmet.append(f"{trait_name}: {actual_value:.1f}/{required_value:.1f}")
        
        # 对于树木里程碑，额外检查阶段
        if milestone_id == "first_tree":
            if current_stage < 5:
                unmet.append(f"需要阶段>=5，当前阶段{current_stage}")
                total_count += 1
            else:
                met_count += 1
                total_count += 1
        
        readiness = met_count / total_count if total_count > 0 else 0.0
        is_met = len(unmet) == 0
        
        return is_met, readiness, unmet
    
    def get_milestone_readiness_with_embedding(
        self,
        species: 'Species',
        milestone_id: str
    ) -> dict[str, float]:
        """【新增】使用Embedding增强的里程碑准备度评估
        
        综合考虑：
        1. 特质条件满足度（60%权重）
        2. 与目标阶段原型的向量相似度（40%权重）
        
        Returns:
            {
                "trait_readiness": 特质满足度,
                "embedding_similarity": 向量相似度,
                "overall_readiness": 综合准备度,
            }
        """
        # 特质准备度
        _, trait_readiness, _ = self.check_milestone_requirements(species, milestone_id)
        
        # 向量相似度
        embedding_similarity = 0.5  # 默认值
        
        if self._embeddings is not None:
            try:
                milestone = PLANT_MILESTONES.get(milestone_id)
                if milestone and milestone.to_stage is not None:
                    target_stage = milestone.to_stage
                    
                    # 获取目标阶段原型向量
                    if target_stage not in self._stage_vectors:
                        self._initialize_stage_vectors()
                    
                    if target_stage in self._stage_vectors:
                        stage_vec = self._stage_vectors[target_stage]
                        
                        # 获取物种向量
                        species_text = self._build_species_text(species)
                        species_vec = np.array(self._embeddings.embed_single(species_text))
                        
                        # 余弦相似度
                        norm_stage = np.linalg.norm(stage_vec)
                        norm_species = np.linalg.norm(species_vec)
                        if norm_stage > 0 and norm_species > 0:
                            similarity = np.dot(stage_vec, species_vec) / (norm_stage * norm_species)
                            embedding_similarity = float(max(0.0, similarity))
            except Exception as e:
                logger.debug(f"[PlantEvolution] Embedding计算失败: {e}")
        
        # 综合准备度
        overall = trait_readiness * 0.6 + embedding_similarity * 0.4
        
        return {
            "trait_readiness": trait_readiness,
            "embedding_similarity": embedding_similarity,
            "overall_readiness": overall,
        }
    
    def _initialize_stage_vectors(self) -> None:
        """初始化阶段原型向量"""
        if self._embeddings is None:
            return
        
        stage_descriptions = {
            0: "原核光合细菌，蓝藻，单细胞，无核，光合作用，水生，浮游，产氧",
            1: "真核藻类，单细胞，叶绿体，细胞核，有丝分裂，光合自养，浮游藻",
            2: "群体藻类，多细胞初期，细胞分化，丝状体，团藻，简单组织",
            3: "苔藓植物，登陆先锋，假根，孢子繁殖，角质层，保水，陆生适应",
            4: "蕨类植物，维管束，真根，孢子囊，叶片分化，荫蔽环境",
            5: "裸子植物，种子繁殖，球果，针叶，木质化，乔木，针叶林",
            6: "被子植物，开花植物，果实，昆虫授粉，草本乔木，阔叶，快速演化",
        }
        
        try:
            for stage, desc in stage_descriptions.items():
                vec = self._embeddings.embed_single(desc)
                self._stage_vectors[stage] = np.array(vec, dtype=np.float32)
            logger.debug(f"[PlantEvolution] 初始化了 {len(self._stage_vectors)} 个阶段原型向量")
        except Exception as e:
            logger.warning(f"[PlantEvolution] 阶段向量初始化失败: {e}")
    
    def _build_species_text(self, species: 'Species') -> str:
        """构建物种搜索文本"""
        from .trait_config import PlantTraitConfig
        
        parts = [
            species.common_name,
            species.latin_name,
            species.description,
        ]
        
        life_form = getattr(species, 'life_form_stage', 0)
        growth = getattr(species, 'growth_form', 'aquatic')
        
        parts.append(f"生命形式: {PlantTraitConfig.get_stage_name(life_form)}")
        parts.append(f"生长形式: {growth}")
        
        traits = species.abstract_traits or {}
        for trait_name in ["光合效率", "根系发达度", "木质化程度", "多细胞程度"]:
            value = traits.get(trait_name, 0)
            if value > 7:
                parts.append(f"高{trait_name}")
        
        return " ".join(parts)
    
    def predict_evolution_direction(
        self,
        species: 'Species',
        pressure_types: list[str]
    ) -> dict[str, any]:
        """【新增】预测植物演化方向
        
        Args:
            species: 物种对象
            pressure_types: 环境压力类型列表
            
        Returns:
            预测结果
        """
        result = {
            "next_milestone": None,
            "milestone_readiness": 0.0,
            "suggested_traits": {},
            "suggested_organs": [],
        }
        
        # 获取下一个里程碑
        next_milestone = self.get_next_milestone(species)
        if next_milestone:
            result["next_milestone"] = next_milestone.name
            
            # 使用Embedding增强的准备度
            readiness = self.get_milestone_readiness_with_embedding(
                species, next_milestone.id
            )
            result["milestone_readiness"] = readiness["overall_readiness"]
            
            # 建议需要提升的特质
            _, _, unmet = self.check_milestone_requirements(species, next_milestone.id)
            for condition in unmet:
                if ":" in condition:
                    trait_name = condition.split(":")[0].strip()
                    result["suggested_traits"][trait_name] = "+1.0"
            
            # 建议的器官
            result["suggested_organs"] = next_milestone.unlock_organs[:2]
        
        return result
    
    def get_next_milestone(self, species: 'Species') -> PlantMilestone | None:
        """获取物种的下一个可能的里程碑
        
        Args:
            species: 物种对象
            
        Returns:
            下一个里程碑，如果没有则返回None
        """
        current_stage = self.get_current_stage(species)
        achieved = set(getattr(species, 'achieved_milestones', []) or [])
        
        # 优先检查阶段升级里程碑
        for milestone_id, milestone in PLANT_MILESTONES.items():
            if milestone_id in achieved:
                continue
            
            if milestone.from_stage == current_stage:
                return milestone
        
        # 检查形态里程碑
        for milestone_id, milestone in PLANT_MILESTONES.items():
            if milestone_id in achieved:
                continue
            
            if milestone.from_stage is None:
                # 形态里程碑，检查条件
                is_met, _, _ = self.check_milestone_requirements(species, milestone_id)
                if is_met:
                    return milestone
        
        return None
    
    def get_milestone_hints(self, species: 'Species') -> str:
        """生成里程碑提示文本（供Prompt使用）
        
        Args:
            species: 物种对象
            
        Returns:
            里程碑提示文本
        """
        next_milestone = self.get_next_milestone(species)
        if not next_milestone:
            return "当前没有接近的演化里程碑。"
        
        is_met, readiness, unmet = self.check_milestone_requirements(species, next_milestone.id)
        
        # 进度条可视化
        progress_filled = int(readiness * 10)
        progress_bar = "█" * progress_filled + "░" * (10 - progress_filled)
        
        lines = [f"🎯 接近里程碑: 【{next_milestone.name}】"]
        lines.append(f"进度: [{progress_bar}] {readiness:.0%}")
        
        if is_met:
            lines.append("✅ 所有条件已满足，可以触发里程碑！")
            lines.append(f"💡 建议：在分化时设置 milestone_triggered: \"{next_milestone.id}\"")
        else:
            lines.append("⚠️ 未满足条件（需要提升这些特质）:")
            for condition in unmet:
                # 解析条件并给出建议
                if ":" in condition:
                    trait_name = condition.split(":")[0].strip()
                    lines.append(f"  - {condition} → 建议增加 {trait_name}")
                else:
                    lines.append(f"  - {condition}")
        
        if next_milestone.unlock_organs:
            lines.append(f"🔓 解锁器官: {', '.join(next_milestone.unlock_organs)}")
        
        if next_milestone.achievement:
            lines.append(f"🏆 获得成就: {next_milestone.achievement}")
        
        # 检查是否有前置里程碑未完成
        current_stage = self.get_current_stage(species)
        if next_milestone.from_stage is not None and current_stage < next_milestone.from_stage:
            lines.append(f"⚠️ 注意：需先达到阶段{next_milestone.from_stage}（当前阶段{current_stage}）")
        
        return "\n".join(lines)
    
    def get_milestone_progress_for_prompt(self, species: 'Species') -> str:
        """【新增】生成详细的里程碑进度信息（供压力响应Prompt使用）
        
        Args:
            species: 物种对象
            
        Returns:
            格式化的里程碑进度信息
        """
        current_stage = self.get_current_stage(species)
        achieved = set(getattr(species, 'achieved_milestones', []) or [])
        traits = species.abstract_traits or {}
        
        lines = [f"当前阶段: {current_stage} ({self._get_stage_name_safe(current_stage)})"]
        lines.append(f"已达成里程碑: {', '.join(achieved) if achieved else '无'}")
        
        # 检查所有可能的里程碑进度
        milestone_progress = []
        for milestone_id, milestone in PLANT_MILESTONES.items():
            if milestone_id in achieved:
                continue
            
            # 检查阶段前置
            if milestone.from_stage is not None and current_stage != milestone.from_stage:
                continue
            
            # 计算准备度
            _, readiness, unmet = self.check_milestone_requirements(species, milestone_id)
            
            if readiness > 0.3:  # 只显示有一定进度的里程碑
                progress_filled = int(readiness * 10)
                bar = "█" * progress_filled + "░" * (10 - progress_filled)
                status = "✅可触发" if readiness >= 1.0 else f"[{bar}] {readiness:.0%}"
                
                milestone_progress.append({
                    "id": milestone_id,
                    "name": milestone.name,
                    "readiness": readiness,
                    "status": status,
                    "unmet": unmet[:2] if unmet else [],  # 只显示前2个未满足条件
                })
        
        if milestone_progress:
            lines.append("\n可接近的里程碑:")
            for mp in sorted(milestone_progress, key=lambda x: -x["readiness"]):
                lines.append(f"  {mp['name']}: {mp['status']}")
                if mp["unmet"]:
                    for cond in mp["unmet"]:
                        lines.append(f"    → 需要: {cond}")
        else:
            lines.append("暂无接近的里程碑")
        
        return "\n".join(lines)
    
    def trigger_milestone(
        self,
        species: 'Species',
        milestone_id: str,
        turn_index: int
    ) -> dict[str, Any]:
        """触发里程碑
        
        Args:
            species: 物种对象
            milestone_id: 里程碑ID
            turn_index: 当前回合
            
        Returns:
            触发结果，包含阶段变化、新器官、成就等
        """
        if milestone_id not in PLANT_MILESTONES:
            return {"success": False, "error": f"未知里程碑: {milestone_id}"}
        
        milestone = PLANT_MILESTONES[milestone_id]
        
        # 检查条件
        is_met, readiness, unmet = self.check_milestone_requirements(species, milestone_id)
        if not is_met:
            return {
                "success": False,
                "error": f"里程碑条件未满足",
                "unmet_conditions": unmet,
                "readiness": readiness
            }
        
        # 检查是否已达成
        achieved = getattr(species, 'achieved_milestones', []) or []
        if milestone_id in achieved:
            return {"success": False, "error": "里程碑已达成"}
        
        result = {
            "success": True,
            "milestone_id": milestone_id,
            "milestone_name": milestone.name,
            "narrative": milestone.narrative,
            "turn_index": turn_index,
        }
        
        # 阶段升级
        if milestone.to_stage is not None:
            old_stage = self.get_current_stage(species)
            species.life_form_stage = milestone.to_stage
            result["stage_change"] = {"from": old_stage, "to": milestone.to_stage}
            
            # 更新生长形式
            from .trait_config import PlantTraitConfig
            valid_forms = PlantTraitConfig.get_valid_growth_forms(milestone.to_stage)
            current_form = self.get_growth_form(species)
            if current_form not in valid_forms and valid_forms:
                species.growth_form = valid_forms[0]
                result["growth_form_change"] = {"from": current_form, "to": valid_forms[0]}
        
        # 解锁器官
        if milestone.unlock_organs:
            new_organs = self._add_milestone_organs(species, milestone, turn_index)
            result["new_organs"] = new_organs
        
        # 记录成就
        if milestone.achievement:
            result["achievement"] = milestone.achievement
        
        # 更新已达成里程碑列表
        if not hasattr(species, 'achieved_milestones') or species.achieved_milestones is None:
            species.achieved_milestones = []
        species.achieved_milestones.append(milestone_id)
        
        logger.info(f"[植物演化] 触发里程碑 '{milestone.name}' for {species.common_name}")
        
        return result
    
    def _add_milestone_organs(
        self,
        species: 'Species',
        milestone: PlantMilestone,
        turn_index: int
    ) -> list[dict]:
        """添加里程碑解锁的器官
        
        Args:
            species: 物种对象
            milestone: 里程碑对象
            turn_index: 当前回合
            
        Returns:
            新添加的器官列表
        """
        if species.organs is None:
            species.organs = {}
        
        new_organs = []
        
        for organ_name in milestone.unlock_organs:
            # 查找器官属于哪个类别
            for category, organs in PLANT_ORGANS.items():
                if organ_name in organs:
                    organ_params = dict(organs[organ_name])
                    organ_params.pop("min_stage", None)  # 移除最小阶段限制
                    
                    species.organs[category] = {
                        "type": organ_name,
                        "parameters": organ_params,
                        "acquired_turn": turn_index,
                        "is_active": True,
                    }
                    
                    new_organs.append({
                        "category": category,
                        "type": organ_name,
                        "parameters": organ_params,
                    })
                    break
        
        return new_organs
    
    def get_available_organs(self, species: 'Species') -> dict[str, list[str]]:
        """获取物种当前阶段可用的器官列表
        
        Args:
            species: 物种对象
            
        Returns:
            按类别分组的可用器官名称
        """
        current_stage = self.get_current_stage(species)
        available = {}
        
        for category, organs in PLANT_ORGANS.items():
            available[category] = []
            for organ_name, params in organs.items():
                min_stage = params.get("min_stage", 0)
                if current_stage >= min_stage:
                    available[category].append(organ_name)
        
        return available
    
    def validate_organ_upgrade(
        self,
        species: 'Species',
        category: str,
        new_organ: str
    ) -> tuple[bool, str]:
        """验证器官升级是否合法
        
        Args:
            species: 物种对象
            category: 器官类别
            new_organ: 新器官名称
            
        Returns:
            (是否合法, 错误信息)
        """
        if category not in PLANT_ORGANS:
            return False, f"未知器官类别: {category}"
        
        if new_organ not in PLANT_ORGANS[category]:
            return False, f"类别 {category} 中没有器官 {new_organ}"
        
        current_stage = self.get_current_stage(species)
        min_stage = PLANT_ORGANS[category][new_organ].get("min_stage", 0)
        
        if current_stage < min_stage:
            return False, f"器官 {new_organ} 需要阶段 >= {min_stage}，当前阶段 {current_stage}"
        
        return True, ""
    
    def calculate_stage_readiness(self, species: 'Species') -> dict[int, float]:
        """计算物种对各阶段的准备度
        
        Args:
            species: 物种对象
            
        Returns:
            {阶段: 准备度} 字典
        """
        current_stage = self.get_current_stage(species)
        readiness = {}
        
        # 对于每个可能的下一阶段
        for target_stage in range(current_stage + 1, 7):
            # 找到对应的里程碑
            for milestone_id, milestone in PLANT_MILESTONES.items():
                if milestone.from_stage == current_stage and milestone.to_stage == target_stage:
                    _, stage_readiness, _ = self.check_milestone_requirements(species, milestone_id)
                    readiness[target_stage] = stage_readiness
                    break
            
            if target_stage not in readiness:
                readiness[target_stage] = 0.0
        
        return readiness
    
    def get_evolution_path(self, species: 'Species') -> list[dict]:
        """获取物种的演化路径（已达成的里程碑）
        
        Args:
            species: 物种对象
            
        Returns:
            已达成里程碑列表
        """
        achieved = getattr(species, 'achieved_milestones', []) or []
        path = []
        
        for milestone_id in achieved:
            if milestone_id in PLANT_MILESTONES:
                milestone = PLANT_MILESTONES[milestone_id]
                path.append({
                    "id": milestone_id,
                    "name": milestone.name,
                    "from_stage": milestone.from_stage,
                    "to_stage": milestone.to_stage,
                })
        
        return path


# 全局服务实例
plant_evolution_service = PlantEvolutionService()

