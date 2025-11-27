"""向量演化预测服务 - 基于 Embedding 向量运算预测物种演化方向

【核心思想】
用向量运算代替规则编写：
1. 每个物种有一个 embedding 向量
2. 环境压力也用向量表示
3. 未来物种 = 当前向量 + Σ(压力向量 × 强度) + 噪声

【压力向量】
通过参考物种对计算：
- 热适应向量 = 热带物种embedding - 极地物种embedding
- 防御压力向量 = 高防御物种embedding - 低防御物种embedding

【用途】
1. 预测物种未来可能的演化方向
2. 为 LLM 生成提供参考特征
3. 分析演化趋势
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Sequence

import numpy as np

from ...ai.prompts.embedding import EMBEDDING_PROMPTS

if TYPE_CHECKING:
    from ...models.species import Species
    from ..system.embedding import EmbeddingService
    from ...ai.model_router import ModelRouter

logger = logging.getLogger(__name__)


@dataclass
class PressureVector:
    """压力向量定义"""
    name: str  # 压力名称
    name_cn: str  # 中文名称
    vector: np.ndarray  # 向量
    description: str  # 描述
    source_desc: str  # 源描述（低压力状态）
    target_desc: str  # 目标描述（高压力状态）


@dataclass
class EvolutionPredictionResult:
    """演化预测结果"""
    species_code: str
    species_name: str
    
    # 预测向量
    current_vector: np.ndarray
    predicted_vector: np.ndarray
    
    # 应用的压力
    applied_pressures: list[str]
    pressure_strengths: list[float]
    
    # 参考物种（向量空间中的近邻）
    reference_species: list[tuple[str, str, float]]  # (code, name, similarity)
    
    # 预测的特征变化
    predicted_trait_changes: dict[str, float]
    
    # 置信度
    confidence: float
    
    # LLM 生成的描述（可选）
    predicted_description: str = ""


class PressureVectorLibrary:
    """压力向量库 - 存储和管理演化压力向量
    
    压力向量通过对比不同适应状态的物种 embedding 差值计算得到
    """
    
    # 压力参考描述对（源状态 → 目标状态）
    PRESSURE_REFERENCES = {
        # ===== 温度适应 =====
        "cold_adaptation": {
            "name_cn": "寒冷适应",
            "source": "一种生活在温暖热带环境的生物，适应高温，没有保温层",
            "target": "一种生活在极寒环境的生物，有厚厚的脂肪层和绒毛，体液含有防冻蛋白",
            "description": "向寒冷环境适应的演化压力"
        },
        "heat_adaptation": {
            "name_cn": "高温适应",
            "source": "一种生活在寒冷环境的生物，有厚重的保温层",
            "target": "一种生活在炎热沙漠的生物，有高效散热系统，夜行性，节水能力强",
            "description": "向高温环境适应的演化压力"
        },
        
        # ===== 水分适应 =====
        "drought_adaptation": {
            "name_cn": "干旱适应",
            "source": "一种水生生物，依赖充足水源生存",
            "target": "一种沙漠生物，能长期不喝水，通过代谢产水，有储水器官",
            "description": "向干旱环境适应的演化压力"
        },
        "aquatic_adaptation": {
            "name_cn": "水生适应",
            "source": "一种完全陆生的生物，没有游泳能力",
            "target": "一种水生生物，有鳃或皮肤呼吸，流线型身体，鳍状附肢",
            "description": "向水生环境适应的演化压力"
        },
        
        # ===== 捕食相关 =====
        "predation_defense": {
            "name_cn": "防御压力",
            "source": "一种没有防御能力的软弱生物，容易被捕食",
            "target": "一种高度防御的生物，有坚硬外壳、毒刺、保护色或拟态",
            "description": "被捕食压力导致的防御能力演化"
        },
        "predator_enhancement": {
            "name_cn": "捕食强化",
            "source": "一种杂食性生物，捕食能力一般",
            "target": "一种顶级掠食者，有锋利牙齿、强壮肌肉、敏锐感官",
            "description": "向更高效捕食者演化的压力"
        },
        
        # ===== 运动能力 =====
        "speed_enhancement": {
            "name_cn": "速度强化",
            "source": "一种缓慢移动的生物",
            "target": "一种极速奔跑的生物，有修长四肢、发达肌肉、高效心肺系统",
            "description": "向高速运动能力演化的压力"
        },
        "flight_adaptation": {
            "name_cn": "飞行适应",
            "source": "一种完全陆生、无法飞行的生物",
            "target": "一种飞行生物，有翅膀、轻量化骨骼、高效呼吸系统",
            "description": "向飞行能力演化的压力"
        },
        
        # ===== 社会性 =====
        "social_enhancement": {
            "name_cn": "社会性强化",
            "source": "一种独居生物，没有社会行为",
            "target": "一种高度社会化的生物，有复杂的群体结构、分工合作、通讯系统",
            "description": "向社会性群居演化的压力"
        },
        
        # ===== 感官 =====
        "sensory_enhancement": {
            "name_cn": "感官强化",
            "source": "一种感官简单的生物，只有基本的光感和触觉",
            "target": "一种感官高度发达的生物，有复眼/大眼睛、回声定位、电感受器",
            "description": "向更强感官能力演化的压力"
        },
        
        # ===== 繁殖策略 =====
        "r_strategy": {
            "name_cn": "r策略（多产）",
            "source": "一种低繁殖率、高亲代投资的生物",
            "target": "一种高繁殖率的生物，产大量后代，发育快速，寿命短",
            "description": "向r选择策略（多产少育）演化的压力"
        },
        "k_strategy": {
            "name_cn": "K策略（精育）",
            "source": "一种高繁殖率、低亲代投资的生物",
            "target": "一种低繁殖率的生物，产少量后代，高亲代照顾，寿命长",
            "description": "向K选择策略（少产精育）演化的压力"
        },
        
        # ===== 体型 =====
        "size_increase": {
            "name_cn": "体型增大",
            "source": "一种微小的生物",
            "target": "一种巨型生物，身体庞大，代谢率低，寿命长",
            "description": "向更大体型演化的压力"
        },
        "size_decrease": {
            "name_cn": "体型缩小",
            "source": "一种大型生物",
            "target": "一种微型生物，体型微小，代谢率高，世代快",
            "description": "向更小体型演化的压力"
        },
    }

    def __init__(self, embedding_service: 'EmbeddingService'):
        self.embeddings = embedding_service
        self._vectors: dict[str, PressureVector] = {}
        self._initialized = False

    def initialize(self) -> None:
        """初始化所有压力向量（懒加载）"""
        if self._initialized:
            return
        
        logger.info("初始化压力向量库...")
        
        for pressure_name, config in self.PRESSURE_REFERENCES.items():
            try:
                # 获取源和目标描述的 embedding
                source_vec = np.array(self.embeddings.embed_single(config["source"]))
                target_vec = np.array(self.embeddings.embed_single(config["target"]))
                
                # 计算压力向量（目标 - 源）
                pressure_vec = target_vec - source_vec
                
                # 归一化
                norm = np.linalg.norm(pressure_vec)
                if norm > 0:
                    pressure_vec = pressure_vec / norm
                
                self._vectors[pressure_name] = PressureVector(
                    name=pressure_name,
                    name_cn=config["name_cn"],
                    vector=pressure_vec,
                    description=config["description"],
                    source_desc=config["source"],
                    target_desc=config["target"]
                )
                
            except Exception as e:
                logger.error(f"计算压力向量 {pressure_name} 失败: {e}")
        
        self._initialized = True
        logger.info(f"压力向量库初始化完成: {len(self._vectors)} 个向量")

    def get_pressure(self, name: str) -> PressureVector | None:
        """获取压力向量"""
        self.initialize()
        return self._vectors.get(name)

    def list_pressures(self) -> list[dict[str, str]]:
        """列出所有可用压力"""
        self.initialize()
        return [
            {
                "name": p.name,
                "name_cn": p.name_cn,
                "description": p.description
            }
            for p in self._vectors.values()
        ]

    def get_vector(self, name: str) -> np.ndarray | None:
        """获取压力向量数组"""
        pressure = self.get_pressure(name)
        return pressure.vector if pressure else None


class EvolutionPredictor:
    """向量演化预测器
    
    使用向量运算预测物种的演化方向
    """

    def __init__(
        self,
        embedding_service: 'EmbeddingService',
        pressure_library: PressureVectorLibrary | None = None,
        router: 'ModelRouter | None' = None
    ):
        self.embeddings = embedding_service
        self.pressures = pressure_library or PressureVectorLibrary(embedding_service)
        self.router = router
        
        # 物种向量缓存
        self._species_vectors: dict[str, np.ndarray] = {}
        self._species_data: dict[str, 'Species'] = {}

    def build_species_index(self, species_list: Sequence['Species']) -> None:
        """构建物种向量索引"""
        descriptions = [sp.description for sp in species_list]
        vectors = self.embeddings.embed(descriptions)
        
        for sp, vec in zip(species_list, vectors):
            self._species_vectors[sp.lineage_code] = np.array(vec)
            self._species_data[sp.lineage_code] = sp
        
        logger.info(f"物种向量索引构建完成: {len(self._species_vectors)} 个物种")

    def predict_evolution(
        self,
        species: 'Species',
        pressure_types: list[str],
        pressure_strengths: list[float] | None = None,
        noise_scale: float = 0.05
    ) -> EvolutionPredictionResult:
        """预测物种的演化方向
        
        Args:
            species: 目标物种
            pressure_types: 压力类型列表
            pressure_strengths: 压力强度列表（默认每个压力强度为1.0）
            noise_scale: 噪声强度（模拟突变随机性）
        
        Returns:
            演化预测结果
        """
        self.pressures.initialize()
        
        # 获取当前物种向量
        current_vec = self._get_species_vector(species)
        
        # 默认压力强度
        if pressure_strengths is None:
            pressure_strengths = [1.0] * len(pressure_types)
        
        # 累加压力向量
        pressure_sum = np.zeros_like(current_vec)
        valid_pressures = []
        valid_strengths = []
        
        for p_type, strength in zip(pressure_types, pressure_strengths):
            p_vec = self.pressures.get_vector(p_type)
            if p_vec is not None:
                # 确保维度匹配
                if len(p_vec) == len(current_vec):
                    pressure_sum += strength * p_vec
                    valid_pressures.append(p_type)
                    valid_strengths.append(strength)
        
        # 添加随机扰动（模拟突变）
        noise = np.random.normal(0, noise_scale, current_vec.shape)
        
        # 计算预测向量
        predicted_vec = current_vec + pressure_sum * 0.3 + noise  # 0.3 是压力影响系数
        
        # 归一化
        norm = np.linalg.norm(predicted_vec)
        if norm > 0:
            predicted_vec = predicted_vec / norm
        
        # 在物种库中找最近邻
        reference_species = self._find_nearest_species(predicted_vec, exclude=species.lineage_code)
        
        # 预测特征变化
        trait_changes = self._predict_trait_changes(
            current_vec, 
            predicted_vec, 
            valid_pressures
        )
        
        # 计算置信度
        confidence = self._calculate_confidence(
            current_vec, 
            predicted_vec, 
            reference_species
        )
        
        return EvolutionPredictionResult(
            species_code=species.lineage_code,
            species_name=species.common_name,
            current_vector=current_vec,
            predicted_vector=predicted_vec,
            applied_pressures=valid_pressures,
            pressure_strengths=valid_strengths,
            reference_species=reference_species,
            predicted_trait_changes=trait_changes,
            confidence=confidence
        )

    def _get_species_vector(self, species: 'Species') -> np.ndarray:
        """获取物种的 embedding 向量"""
        if species.lineage_code in self._species_vectors:
            return self._species_vectors[species.lineage_code]
        
        vec = np.array(self.embeddings.embed_single(species.description))
        self._species_vectors[species.lineage_code] = vec
        self._species_data[species.lineage_code] = species
        return vec

    def _find_nearest_species(
        self, 
        target_vec: np.ndarray, 
        exclude: str = "",
        top_k: int = 5
    ) -> list[tuple[str, str, float]]:
        """在物种库中找到最接近目标向量的物种"""
        if not self._species_vectors:
            return []
        
        # 归一化目标向量
        target_norm = target_vec / (np.linalg.norm(target_vec) + 1e-8)
        
        results = []
        for code, vec in self._species_vectors.items():
            if code == exclude:
                continue
            
            vec_norm = vec / (np.linalg.norm(vec) + 1e-8)
            similarity = float(np.dot(target_norm, vec_norm))
            
            species = self._species_data.get(code)
            name = species.common_name if species else code
            
            results.append((code, name, similarity))
        
        results.sort(key=lambda x: x[2], reverse=True)
        return results[:top_k]

    def _predict_trait_changes(
        self,
        current_vec: np.ndarray,
        predicted_vec: np.ndarray,
        pressure_types: list[str]
    ) -> dict[str, float]:
        """预测特征变化"""
        changes = {}
        
        # 基于压力类型推断特征变化
        pressure_to_traits = {
            "cold_adaptation": {"耐寒性": +2.0, "耐热性": -1.0},
            "heat_adaptation": {"耐热性": +2.0, "耐寒性": -1.0},
            "drought_adaptation": {"耐旱性": +2.0},
            "predation_defense": {"防御性": +2.0, "运动能力": -0.5},
            "predator_enhancement": {"攻击性": +2.0, "运动能力": +1.0},
            "speed_enhancement": {"运动能力": +2.0},
            "flight_adaptation": {"运动能力": +2.0},
            "social_enhancement": {"社会性": +2.0},
            "sensory_enhancement": {"感知能力": +2.0},
            "r_strategy": {"繁殖速度": +2.0},
            "k_strategy": {"繁殖速度": -1.0, "社会性": +1.0},
            "size_increase": {"体型": +2.0},
            "size_decrease": {"体型": -2.0, "繁殖速度": +1.0},
        }
        
        for p_type in pressure_types:
            if p_type in pressure_to_traits:
                for trait, change in pressure_to_traits[p_type].items():
                    if trait in changes:
                        changes[trait] += change
                    else:
                        changes[trait] = change
        
        return changes

    def _calculate_confidence(
        self,
        current_vec: np.ndarray,
        predicted_vec: np.ndarray,
        reference_species: list[tuple[str, str, float]]
    ) -> float:
        """计算预测置信度"""
        # 基于向量变化幅度和参考物种相似度
        
        # 1. 向量变化不宜过大（过大说明预测不稳定）
        change_magnitude = np.linalg.norm(predicted_vec - current_vec)
        magnitude_score = max(0, 1 - change_magnitude / 2)
        
        # 2. 应该有相似的参考物种
        if reference_species:
            max_similarity = reference_species[0][2]
            reference_score = max(0, max_similarity)
        else:
            reference_score = 0.5
        
        # 综合置信度
        confidence = (magnitude_score * 0.4 + reference_score * 0.6)
        
        return min(1.0, max(0.0, confidence))

    async def generate_prediction_description(
        self,
        prediction: EvolutionPredictionResult,
        species: 'Species'
    ) -> str:
        """使用 LLM 生成预测描述"""
        if not self.router:
            return ""
        
        # 获取参考物种信息
        ref_info = []
        for code, name, sim in prediction.reference_species[:3]:
            ref_sp = self._species_data.get(code)
            if ref_sp:
                ref_info.append(f"- {name} (相似度{sim:.2f}): {ref_sp.description[:100]}...")
        
        # 压力描述
        pressure_desc = []
        for p_type in prediction.applied_pressures:
            p = self.pressures.get_pressure(p_type)
            if p:
                pressure_desc.append(f"- {p.name_cn}: {p.description}")
        
        # 格式化特征变化
        traits_text = ", ".join([
            f"{k}: {v:+.1f}" for k, v in prediction.predicted_trait_changes.items()
        ]) if prediction.predicted_trait_changes else "无明显变化"
        
        # 使用模板化 prompt
        prompt = EMBEDDING_PROMPTS["embedding_prediction"].format(
            species_name=species.common_name,
            description=species.description,
            pressure_descriptions="\n".join(pressure_desc) if pressure_desc else "无特定压力",
            reference_species="\n".join(ref_info) if ref_info else "无参考物种",
            predicted_traits=traits_text
        )

        try:
            description = await self.router.chat(prompt, capability="speciation")
            return description
        except Exception as e:
            logger.error(f"生成预测描述失败: {e}")
            return ""

    def export_for_save(self) -> dict[str, Any]:
        """导出压力向量数据用于存档"""
        self.pressures.initialize()
        
        return {
            "version": "1.0",
            "pressure_vectors": {
                name: {
                    "name_cn": p.name_cn,
                    "vector": p.vector.tolist(),
                    "description": p.description
                }
                for name, p in self.pressures._vectors.items()
            },
            "species_vectors": {
                code: vec.tolist()
                for code, vec in self._species_vectors.items()
            }
        }

    def import_from_save(self, data: dict[str, Any]) -> None:
        """从存档导入数据"""
        if not data:
            return
        
        # 导入物种向量
        if "species_vectors" in data:
            for code, vec_list in data["species_vectors"].items():
                self._species_vectors[code] = np.array(vec_list)
        
        logger.info(f"从存档导入 {len(self._species_vectors)} 个物种向量")

