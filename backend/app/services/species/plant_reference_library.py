"""植物参考向量库 - 预定义的植物演化模式

【核心功能】
1. 存储各演化阶段的原型向量
2. 存储里程碑事件的语义向量
3. 提供压力-适应映射向量
4. 支持跨物种的演化模式匹配
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from ..system.embedding import EmbeddingService
    from ...models.species import Species

logger = logging.getLogger(__name__)


class PlantReferenceLibrary:
    """植物参考向量库"""
    
    # 预定义的阶段原型描述
    STAGE_PROTOTYPES = {
        0: "原核光合细菌，蓝藻，叶绿素，光合作用，单细胞，无核，细胞壁，水生，浮游，产氧",
        1: "真核藻类，单细胞，叶绿体，细胞核，有丝分裂，光合自养，浮游藻，绿藻",
        2: "群体藻类，多细胞初期，细胞分化，丝状体，团藻，水绵，简单组织，细胞协作",
        3: "苔藓植物，登陆先锋，假根，孢子繁殖，角质层，保水，陆生适应，无维管束，潮湿环境",
        4: "蕨类植物，维管束，真根，孢子囊，叶片分化，茎叶根分化，森林底层，荫蔽环境",
        5: "裸子植物，种子繁殖，球果，针叶，木质化，乔木，针叶林，花粉传播，抗旱",
        6: "被子植物，开花植物，果实，花粉传播，昆虫授粉，草本乔木，阔叶，森林冠层，快速演化",
    }
    
    # 预定义的里程碑描述
    MILESTONE_DESCRIPTIONS = {
        "first_eukaryote": "从原核到真核的飞跃，细胞核形成，线粒体和叶绿体内共生，有丝分裂，遗传物质隔离",
        "first_multicellular": "从单细胞到多细胞的转变，细胞分化开始，细胞间通讯，原始组织形成，协作分工",
        "first_land_plant": "从水生到陆生的伟大迁徙，角质层形成，假根锚定，抵抗干燥和紫外线，气孔调节",
        "first_true_root": "真根演化，维管束形成，高效水分和养分运输，植物真正站稳陆地，深层土壤获取",
        "first_seed": "种子革命，摆脱对水的繁殖依赖，胚珠保护，长距离传播，干燥环境繁殖",
        "first_flower": "开花植物诞生，昆虫授粉共演化，果实传播，快速多样化辐射，被子植物崛起",
        "first_tree": "第一棵树木诞生，高大木质茎，森林生态系统奠基者，竞争阳光优势，复杂生态位",
    }
    
    # 压力-适应映射（植物专用）
    PRESSURE_ADAPTATIONS = {
        "cold": {
            "description": "寒冷环境适应，抗冻蛋白，厚细胞壁，休眠机制，落叶策略，低温光合优化",
            "trait_effects": {"耐寒性": 2.0, "繁殖速度": -0.5, "光合效率": -0.3},
        },
        "drought": {
            "description": "干旱环境适应，角质层加厚，气孔调节，肉质储水，深根系，CAM代谢",
            "trait_effects": {"保水能力": 2.0, "根系发达度": 1.0, "光合效率": -0.5},
        },
        "high_uv": {
            "description": "高紫外辐射适应，花青素积累，厚角质层，矮化生长，色素保护",
            "trait_effects": {"化学防御": 1.5, "木质化程度": 0.5},
        },
        "low_light": {
            "description": "弱光环境适应，大叶面积，薄叶片，高叶绿素含量，林下生长，高光敏感",
            "trait_effects": {"光合效率": 1.5, "耐热性": -0.5},
        },
        "nutrient_poor": {
            "description": "贫瘠土壤适应，与真菌共生，固氮能力，高效养分循环，根系扩展",
            "trait_effects": {"养分吸收": 2.0, "根系发达度": 1.0, "繁殖速度": -0.5},
        },
        "salinity": {
            "description": "盐碱环境适应，盐腺分泌，渗透调节，耐盐性增强，离子隔离",
            "trait_effects": {"耐盐性": 2.5, "保水能力": 0.5},
        },
        "waterlogged": {
            "description": "水涝环境适应，通气组织，支柱根，厌氧代谢，气生根",
            "trait_effects": {"耐旱性": -1.0, "根系发达度": 0.5},
        },
        "herbivory": {
            "description": "食草压力适应，毒素积累，刺毛，快速再生，化学防御，物理屏障",
            "trait_effects": {"化学防御": 2.0, "物理防御": 1.0, "繁殖速度": 0.5},
        },
        "fire": {
            "description": "火灾环境适应，厚树皮，萌蘖能力，火后萌发，地下芽保护",
            "trait_effects": {"物理防御": 2.0, "木质化程度": 1.0},
        },
        "competition": {
            "description": "种间竞争适应，快速生长，高大化，遮阴策略，资源竞争",
            "trait_effects": {"光合效率": 1.0, "木质化程度": 1.5, "繁殖速度": -0.5},
        },
    }
    
    def __init__(self, embedding_service: 'EmbeddingService'):
        self.embeddings = embedding_service
        self._stage_vectors: dict[int, np.ndarray] = {}
        self._milestone_vectors: dict[str, np.ndarray] = {}
        self._pressure_vectors: dict[str, np.ndarray] = {}
        self._initialized = False
        self._init_failed = False  # 【新增】区分失败和未初始化
        self._init_retry_count = 0  # 【新增】重试计数
        self._max_retries = 3  # 【新增】最大重试次数
    
    def initialize(self) -> None:
        """初始化所有参考向量
        
        【改进】
        - 区分初始化成功、失败、未初始化三种状态
        - 失败后允许重试，但有最大重试次数限制
        - 部分失败时保留已成功的向量
        """
        if self._initialized:
            return
        
        # 检查是否超过最大重试次数
        if self._init_failed and self._init_retry_count >= self._max_retries:
            logger.debug(f"[PlantReferenceLibrary] 已达到最大重试次数({self._max_retries})，跳过初始化")
            return
        
        logger.info("[PlantReferenceLibrary] 初始化植物参考向量库...")
        self._init_retry_count += 1
        
        success_count = 0
        total_count = len(self.STAGE_PROTOTYPES) + len(self.MILESTONE_DESCRIPTIONS) + len(self.PRESSURE_ADAPTATIONS)
        
        try:
            # 1. 生成阶段原型向量
            for stage, desc in self.STAGE_PROTOTYPES.items():
                try:
                    vector = self.embeddings.embed_single(desc)
                    self._stage_vectors[stage] = np.array(vector, dtype=np.float32)
                    success_count += 1
                except Exception as e:
                    logger.debug(f"[PlantReferenceLibrary] 阶段{stage}向量生成失败: {e}")
            
            # 2. 生成里程碑向量
            for milestone_id, desc in self.MILESTONE_DESCRIPTIONS.items():
                try:
                    vector = self.embeddings.embed_single(desc)
                    self._milestone_vectors[milestone_id] = np.array(vector, dtype=np.float32)
                    success_count += 1
                except Exception as e:
                    logger.debug(f"[PlantReferenceLibrary] 里程碑{milestone_id}向量生成失败: {e}")
            
            # 3. 生成压力适应向量
            for pressure_type, info in self.PRESSURE_ADAPTATIONS.items():
                try:
                    vector = self.embeddings.embed_single(info["description"])
                    self._pressure_vectors[pressure_type] = np.array(vector, dtype=np.float32)
                    success_count += 1
                except Exception as e:
                    logger.debug(f"[PlantReferenceLibrary] 压力{pressure_type}向量生成失败: {e}")
            
            # 4. 存入向量索引（便于搜索）
            self._store_in_indexes()
            
            # 判断初始化结果
            if success_count == total_count:
                self._initialized = True
                self._init_failed = False
                logger.info(
                    f"[PlantReferenceLibrary] 初始化完成: "
                    f"{len(self._stage_vectors)} 阶段, "
                    f"{len(self._milestone_vectors)} 里程碑, "
                    f"{len(self._pressure_vectors)} 压力类型"
                )
            elif success_count > 0:
                # 部分成功
                self._initialized = True
                self._init_failed = False
                logger.warning(
                    f"[PlantReferenceLibrary] 部分初始化完成({success_count}/{total_count}): "
                    f"{len(self._stage_vectors)} 阶段, "
                    f"{len(self._milestone_vectors)} 里程碑, "
                    f"{len(self._pressure_vectors)} 压力类型"
                )
            else:
                # 完全失败
                self._init_failed = True
                logger.warning(f"[PlantReferenceLibrary] 初始化失败，将在下次调用时重试")
                
        except Exception as e:
            self._init_failed = True
            logger.warning(f"[PlantReferenceLibrary] 初始化异常: {e}")
    
    def is_ready(self) -> bool:
        """【新增】检查库是否可用
        
        Returns:
            是否至少有部分向量可用
        """
        return self._initialized and (
            len(self._stage_vectors) > 0 or 
            len(self._milestone_vectors) > 0 or 
            len(self._pressure_vectors) > 0
        )
    
    def _store_in_indexes(self) -> None:
        """将向量存入索引"""
        try:
            # 存入阶段向量
            store = self.embeddings._vector_stores.get_store("plant_stages")
            for stage, vec in self._stage_vectors.items():
                store.add(f"stage_{stage}", vec.tolist(), {"stage": stage})
            
            # 存入里程碑向量
            milestone_store = self.embeddings._vector_stores.get_store("plant_milestones")
            for mid, vec in self._milestone_vectors.items():
                milestone_store.add(mid, vec.tolist(), {"milestone": mid})
        except Exception as e:
            logger.warning(f"[PlantReferenceLibrary] 存入索引失败: {e}")
    
    def get_stage_similarity(self, species: 'Species', target_stage: int) -> float:
        """计算物种与目标阶段的相似度
        
        用于判断物种是否接近下一个演化阶段
        
        Args:
            species: 物种对象
            target_stage: 目标阶段
            
        Returns:
            相似度 (0-1)
        """
        if not self._initialized:
            self.initialize()
        
        if target_stage not in self._stage_vectors:
            return 0.0
        
        try:
            # 获取物种向量
            plant_text = self._build_plant_search_text(species)
            species_vec = np.array(self.embeddings.embed_single(plant_text), dtype=np.float32)
            
            # 计算余弦相似度
            stage_vec = self._stage_vectors[target_stage]
            similarity = np.dot(species_vec, stage_vec) / (
                np.linalg.norm(species_vec) * np.linalg.norm(stage_vec) + 1e-8
            )
            
            return float(max(0.0, similarity))
        except Exception as e:
            logger.warning(f"[PlantReferenceLibrary] 计算阶段相似度失败: {e}")
            return 0.0
    
    def get_milestone_readiness(self, species: 'Species', milestone_id: str) -> dict[str, float]:
        """评估物种对某个里程碑的准备程度
        
        Args:
            species: 物种对象
            milestone_id: 里程碑ID
            
        Returns:
            {
                "similarity": 0.75,  # 向量相似度
                "trait_readiness": 0.8,  # 特质条件满足度
                "overall_readiness": 0.77,  # 综合准备度
            }
        """
        if not self._initialized:
            self.initialize()
        
        if milestone_id not in self._milestone_vectors:
            return {"similarity": 0.0, "trait_readiness": 0.0, "overall_readiness": 0.0}
        
        try:
            # 向量相似度
            plant_text = self._build_plant_search_text(species)
            species_vec = np.array(self.embeddings.embed_single(plant_text), dtype=np.float32)
            milestone_vec = self._milestone_vectors[milestone_id]
            
            similarity = np.dot(species_vec, milestone_vec) / (
                np.linalg.norm(species_vec) * np.linalg.norm(milestone_vec) + 1e-8
            )
            similarity = max(0.0, float(similarity))
            
            # 特质条件检查
            from .plant_evolution import PLANT_MILESTONES
            milestone = PLANT_MILESTONES.get(milestone_id)
            if not milestone:
                return {"similarity": similarity, "trait_readiness": 0.0, "overall_readiness": similarity * 0.5}
            
            requirements = milestone.requirements
            traits = species.abstract_traits or {}
            
            trait_scores = []
            for trait, required in requirements.items():
                actual = traits.get(trait, 0.0)
                score = min(1.0, actual / required) if required > 0 else 1.0
                trait_scores.append(score)
            
            trait_readiness = sum(trait_scores) / len(trait_scores) if trait_scores else 1.0
            
            # 综合评分
            overall = 0.4 * similarity + 0.6 * trait_readiness
            
            return {
                "similarity": similarity,
                "trait_readiness": trait_readiness,
                "overall_readiness": overall,
            }
        except Exception as e:
            logger.warning(f"[PlantReferenceLibrary] 评估里程碑准备度失败: {e}")
            return {"similarity": 0.0, "trait_readiness": 0.0, "overall_readiness": 0.0}
    
    def find_similar_plants(
        self,
        species: 'Species',
        top_k: int = 5,
        same_stage_only: bool = False
    ) -> list[dict]:
        """找到与当前物种最相似的植物
        
        用于参考其演化历史
        
        Args:
            species: 物种对象
            top_k: 返回数量
            same_stage_only: 是否只返回同阶段物种
            
        Returns:
            相似植物列表
        """
        if not self._initialized:
            self.initialize()
        
        try:
            plant_text = self._build_plant_search_text(species)
            
            # 搜索植物索引
            results = self.embeddings.search_species(
                plant_text,
                top_k=top_k + 1,  # +1 因为可能包含自己
                threshold=0.3
            )
            
            # 过滤和格式化
            similar_plants = []
            current_stage = getattr(species, 'life_form_stage', 0)
            
            for result in results:
                if result.id == species.lineage_code:
                    continue  # 跳过自己
                
                if same_stage_only:
                    result_stage = result.metadata.get("life_form_stage", 0)
                    if result_stage != current_stage:
                        continue
                
                similar_plants.append({
                    "lineage_code": result.id,
                    "common_name": result.metadata.get("common_name", "未知"),
                    "similarity": round(result.score, 3),
                    "life_form_stage": result.metadata.get("life_form_stage", 0),
                    "growth_form": result.metadata.get("growth_form", "unknown"),
                })
                
                if len(similar_plants) >= top_k:
                    break
            
            return similar_plants
        except Exception as e:
            logger.warning(f"[PlantReferenceLibrary] 搜索相似植物失败: {e}")
            return []
    
    def predict_adaptation(
        self,
        species: 'Species',
        pressure_types: list[str]
    ) -> dict[str, Any]:
        """预测在给定压力下最可能的适应方向
        
        Args:
            species: 物种对象
            pressure_types: 压力类型列表
            
        Returns:
            {
                "predicted_trait_changes": {"耐寒性": +1.5, ...},
                "confidence": 0.75,
                "suggested_organs": ["角质层加厚", ...],
                "reference_species": [...],
            }
        """
        if not self._initialized:
            self.initialize()
        
        # 收集压力向量
        pressure_vecs = []
        for p_type in pressure_types:
            if p_type in self._pressure_vectors:
                pressure_vecs.append(self._pressure_vectors[p_type])
        
        if not pressure_vecs:
            return {
                "predicted_trait_changes": {},
                "confidence": 0.0,
                "suggested_organs": [],
                "reference_species": [],
            }
        
        try:
            # 平均压力向量
            avg_pressure = np.mean(pressure_vecs, axis=0)
            
            # 获取物种向量
            plant_text = self._build_plant_search_text(species)
            species_vec = np.array(self.embeddings.embed_single(plant_text))
            
            # 预测向量 = 物种向量 + 压力适应向量
            predicted_vec = species_vec + avg_pressure * 0.3  # 适度调整
            norm = np.linalg.norm(predicted_vec)
            if norm > 0:
                predicted_vec = predicted_vec / norm
            
            # 搜索相似物种作为参考
            reference_species = self.find_similar_plants(species, top_k=3)
            
            # 汇总特质变化预测
            predicted_changes = {}
            for p_type in pressure_types:
                if p_type in self.PRESSURE_ADAPTATIONS:
                    effects = self.PRESSURE_ADAPTATIONS[p_type]["trait_effects"]
                    for trait, delta in effects.items():
                        if trait in predicted_changes:
                            predicted_changes[trait] += delta * 0.5  # 多重压力时减半
                        else:
                            predicted_changes[trait] = delta
            
            # 计算置信度
            confidence = 0.5
            if reference_species:
                confidence = max(r["similarity"] for r in reference_species)
            
            return {
                "predicted_trait_changes": predicted_changes,
                "confidence": float(confidence),
                "suggested_organs": self._suggest_organs(pressure_types, species),
                "reference_species": reference_species,
            }
        except Exception as e:
            logger.warning(f"[PlantReferenceLibrary] 预测适应方向失败: {e}")
            return {
                "predicted_trait_changes": {},
                "confidence": 0.0,
                "suggested_organs": [],
                "reference_species": [],
            }
    
    def _build_plant_search_text(self, species: 'Species') -> str:
        """构建植物专用搜索文本"""
        from .trait_config import PlantTraitConfig
        
        parts = [
            species.common_name,
            species.latin_name,
            species.description,
        ]
        
        # 添加植物特有特征
        life_form = getattr(species, 'life_form_stage', 0)
        growth = getattr(species, 'growth_form', 'aquatic')
        
        parts.append(f"生命形式: {PlantTraitConfig.get_stage_name(life_form)}")
        parts.append(f"生长形式: {growth}")
        
        # 添加植物特有特质
        traits = species.abstract_traits or {}
        for trait_name in ["光合效率", "根系发达度", "木质化程度", "种子化程度", "保水能力"]:
            value = traits.get(trait_name, 0)
            if value > 7:
                parts.append(f"高{trait_name}")
            elif value < 3:
                parts.append(f"低{trait_name}")
        
        return " ".join(parts)
    
    def _suggest_organs(self, pressure_types: list[str], species: 'Species') -> list[str]:
        """根据压力类型建议新器官"""
        current_stage = getattr(species, 'life_form_stage', 0)
        suggestions = []
        
        organ_suggestions = {
            "drought": ["角质层", "蜡质表皮", "须根系", "直根系"],
            "cold": ["细胞壁加厚", "木质化"],
            "low_light": ["真叶", "阔叶"],
            "herbivory": ["树皮", "化学防御"],
            "fire": ["树皮", "木质茎"],
            "competition": ["乔木干", "真叶"],
        }
        
        # 阶段限制
        stage_limits = {
            "须根系": 5,
            "直根系": 5,
            "乔木干": 5,
            "真叶": 4,
            "阔叶": 6,
            "树皮": 5,
            "木质茎": 5,
        }
        
        for p_type in pressure_types:
            if p_type in organ_suggestions:
                for organ in organ_suggestions[p_type]:
                    min_stage = stage_limits.get(organ, 0)
                    if current_stage >= min_stage and organ not in suggestions:
                        suggestions.append(organ)
        
        return suggestions[:3]  # 最多3个建议
    
    def export_for_save(self) -> dict:
        """导出用于存档"""
        return {"initialized": self._initialized}
    
    def import_from_save(self, data: dict) -> None:
        """从存档导入"""
        if data.get("initialized"):
            self.initialize()

