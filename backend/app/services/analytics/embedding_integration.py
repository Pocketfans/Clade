"""Embedding 模块集成层 - 连接新模块与现有演化系统

【功能】
1. 管理所有 Embedding 扩展服务的生命周期
2. 在回合结束时自动更新分类树和索引
3. 为分化服务提供向量预测辅助
4. 为叙事服务提供事件流
5. 管理存档的保存/加载

【使用方式】
在 SimulationEngine 中注入此服务，在关键节点调用相应方法
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence

if TYPE_CHECKING:
    from ...models.species import Species
    from ...schemas.requests import PressureConfig
    from ..system.embedding import EmbeddingService
    from ...ai.model_router import ModelRouter
    from .taxonomy import TaxonomyService, TaxonomyResult
    from .evolution_predictor import EvolutionPredictor, PressureVectorLibrary
    from .narrative_engine import NarrativeEngine
    from .encyclopedia import EncyclopediaService
    from ..species.plant_reference_library import PlantReferenceLibrary
    from ..species.plant_evolution_predictor import PlantEvolutionPredictor

logger = logging.getLogger(__name__)


class EmbeddingIntegrationService:
    """Embedding 模块集成服务
    
    管理所有 Embedding 扩展服务，并提供与演化引擎的集成接口
    """
    
    # 自动更新分类树的间隔（回合数）
    TAXONOMY_UPDATE_INTERVAL = 5
    
    def __init__(
        self,
        embedding_service: 'EmbeddingService',
        router: 'ModelRouter | None' = None
    ):
        self.embeddings = embedding_service
        self.router = router
        
        # 延迟初始化服务
        self._taxonomy: 'TaxonomyService | None' = None
        self._predictor: 'EvolutionPredictor | None' = None
        self._narrative: 'NarrativeEngine | None' = None
        self._encyclopedia: 'EncyclopediaService | None' = None
        
        # 【新增】植物演化服务
        self._plant_reference: 'PlantReferenceLibrary | None' = None
        self._plant_predictor: 'PlantEvolutionPredictor | None' = None
        
        # 缓存
        self._current_taxonomy: 'TaxonomyResult | None' = None
        self._last_taxonomy_turn: int = -999
        
        # 是否启用各功能
        self.enable_taxonomy_updates = True
        self.enable_evolution_hints = True
        self.enable_narrative_events = True
        self.enable_encyclopedia_index = True
        self.enable_plant_evolution = True  # 【新增】植物演化功能

    def _ensure_services(self) -> None:
        """确保服务已初始化"""
        if self._taxonomy is None:
            from .taxonomy import TaxonomyService
            from .evolution_predictor import EvolutionPredictor, PressureVectorLibrary
            from .narrative_engine import NarrativeEngine
            from .encyclopedia import EncyclopediaService
            
            self._taxonomy = TaxonomyService(self.embeddings, self.router)
            
            pressure_lib = PressureVectorLibrary(self.embeddings)
            self._predictor = EvolutionPredictor(self.embeddings, pressure_lib, self.router)
            
            self._narrative = NarrativeEngine(self.embeddings, self.router)
            self._encyclopedia = EncyclopediaService(self.embeddings, self.router)
            
            # 【新增】初始化植物演化服务
            if self.enable_plant_evolution:
                try:
                    from ..species.plant_reference_library import PlantReferenceLibrary
                    from ..species.plant_evolution_predictor import PlantEvolutionPredictor
                    
                    self._plant_reference = PlantReferenceLibrary(self.embeddings)
                    self._plant_reference.initialize()
                    
                    self._plant_predictor = PlantEvolutionPredictor(
                        self.embeddings,
                        self._plant_reference
                    )
                    logger.info("[EmbeddingIntegration] 植物演化服务初始化完成")
                except Exception as e:
                    logger.warning(f"[EmbeddingIntegration] 植物演化服务初始化失败: {e}")
            
            logger.info("[EmbeddingIntegration] 服务初始化完成")

    @property
    def taxonomy(self) -> 'TaxonomyService':
        self._ensure_services()
        return self._taxonomy

    @property
    def predictor(self) -> 'EvolutionPredictor':
        self._ensure_services()
        return self._predictor

    @property
    def narrative(self) -> 'NarrativeEngine':
        self._ensure_services()
        return self._narrative

    @property
    def encyclopedia(self) -> 'EncyclopediaService':
        self._ensure_services()
        return self._encyclopedia

    @property
    def plant_reference(self) -> 'PlantReferenceLibrary | None':
        """获取植物参考向量库"""
        self._ensure_services()
        return self._plant_reference
    
    @property
    def plant_predictor(self) -> 'PlantEvolutionPredictor | None':
        """获取植物演化预测器"""
        self._ensure_services()
        return self._plant_predictor

    # ==================== 回合生命周期钩子 ====================

    def on_turn_start(self, turn_index: int, species_list: Sequence['Species']) -> None:
        """回合开始时调用
        
        【优化】统一更新物种索引，避免重复调用：
        1. 先更新统一的物种缓存
        2. 再调用一次底层的物种索引更新
        3. 各服务只更新自己的元数据缓存
        """
        self._ensure_services()
        
        # 【优化】更新统一的物种缓存
        from ..system.species_cache import get_species_cache
        species_cache = get_species_cache()
        species_cache.update(species_list, turn_index)
        
        # 【优化】只调用一次底层索引更新（EmbeddingService内部有增量检测）
        try:
            count = self.embeddings.index_species(species_list)
            if count > 0:
                logger.debug(f"[EmbeddingIntegration] 更新物种向量索引: {count} 个")
        except Exception as e:
            logger.warning(f"[EmbeddingIntegration] 更新物种索引失败: {e}")
        
        # 【优化】各服务只更新自己的元数据缓存，不再重复调用index_species
        if self.enable_encyclopedia_index:
            try:
                self._encyclopedia.update_species_cache(species_list)
            except Exception as e:
                logger.warning(f"[EmbeddingIntegration] 更新百科缓存失败: {e}")
        
        if self.enable_evolution_hints:
            try:
                self._predictor.update_species_cache(species_list)
            except Exception as e:
                logger.warning(f"[EmbeddingIntegration] 更新预测缓存失败: {e}")

    def on_pressure_applied(
        self, 
        turn_index: int,
        pressures: list['PressureConfig'],
        modifiers: dict[str, float]
    ) -> None:
        """压力应用后调用
        
        - 记录环境压力事件
        """
        if not self.enable_narrative_events:
            return
        
        self._ensure_services()
        
        for pressure in pressures:
            try:
                self._narrative.record_event(
                    event_type="environment_pressure",
                    turn_index=turn_index,
                    title=pressure.label or f"{pressure.kind}事件",
                    description=pressure.narrative_note or f"发生{pressure.kind}，强度{pressure.intensity}",
                    severity=pressure.intensity / 10.0,
                    payload={
                        "kind": pressure.kind,
                        "intensity": pressure.intensity,
                        "modifiers": modifiers,
                    }
                )
            except Exception as e:
                logger.warning(f"[EmbeddingIntegration] 记录压力事件失败: {e}")

    def on_speciation(
        self,
        turn_index: int,
        parent: 'Species',
        offspring: list['Species'],
        trigger_reason: str = ""
    ) -> None:
        """物种分化后调用
        
        - 记录分化事件
        - 更新分类树（如果达到更新间隔）
        """
        if not self.enable_narrative_events:
            return
        
        self._ensure_services()
        
        try:
            offspring_names = ", ".join([sp.common_name for sp in offspring])
            self._narrative.record_event(
                event_type="speciation",
                turn_index=turn_index,
                title=f"{parent.common_name}分化",
                description=f"{parent.common_name}分化产生了新物种: {offspring_names}",
                related_species=[parent.lineage_code] + [sp.lineage_code for sp in offspring],
                severity=0.7,
                payload={
                    "parent_code": parent.lineage_code,
                    "offspring_codes": [sp.lineage_code for sp in offspring],
                    "trigger": trigger_reason,
                }
            )
        except Exception as e:
            logger.warning(f"[EmbeddingIntegration] 记录分化事件失败: {e}")

    def on_extinction(
        self,
        turn_index: int,
        species: 'Species',
        cause: str = ""
    ) -> None:
        """物种灭绝后调用"""
        if not self.enable_narrative_events:
            return
        
        self._ensure_services()
        
        try:
            self._narrative.record_event(
                event_type="extinction",
                turn_index=turn_index,
                title=f"{species.common_name}灭绝",
                description=f"{species.common_name}灭绝。{cause}",
                related_species=[species.lineage_code],
                severity=0.8,
                payload={
                    "species_code": species.lineage_code,
                    "cause": cause,
                }
            )
        except Exception as e:
            logger.warning(f"[EmbeddingIntegration] 记录灭绝事件失败: {e}")

    def on_turn_end(
        self, 
        turn_index: int, 
        species_list: Sequence['Species']
    ) -> dict[str, Any]:
        """回合结束时调用
        
        - 刷新待处理的事件（批量索引）
        - 更新分类树（每N回合）
        - 返回可用于存档的数据
        
        Returns:
            包含 taxonomy 和 narrative 数据的字典
        """
        self._ensure_services()
        result = {}
        
        # 刷新待处理的事件（批量索引）
        if self.enable_narrative_events:
            try:
                count = self._narrative.flush_pending_events()
                if count > 0:
                    logger.debug(f"[EmbeddingIntegration] 批量索引 {count} 个事件")
            except Exception as e:
                logger.warning(f"[EmbeddingIntegration] 刷新事件失败: {e}")
        
        # 更新分类树
        if self.enable_taxonomy_updates:
            should_update = (turn_index - self._last_taxonomy_turn) >= self.TAXONOMY_UPDATE_INTERVAL
            if should_update and len(species_list) >= 3:
                try:
                    self._current_taxonomy = self._taxonomy.build_taxonomy(
                        species_list, 
                        current_turn=turn_index
                    )
                    self._last_taxonomy_turn = turn_index
                    logger.info(f"[EmbeddingIntegration] 分类树更新完成: {len(self._current_taxonomy.clades)} 个类群")
                    result["taxonomy"] = self._taxonomy.export_for_save(self._current_taxonomy)
                except Exception as e:
                    logger.warning(f"[EmbeddingIntegration] 更新分类树失败: {e}")
        
        # 导出叙事数据
        if self.enable_narrative_events:
            try:
                result["narrative"] = self._narrative.export_for_save()
            except Exception as e:
                logger.warning(f"[EmbeddingIntegration] 导出叙事数据失败: {e}")
        
        return result

    # ==================== 分化辅助功能 ====================

    def get_evolution_hints(
        self,
        species: 'Species',
        pressure_types: list[str],
        pressure_strengths: list[float] | None = None
    ) -> dict[str, Any]:
        """获取演化方向提示（用于辅助 LLM 分化决策）
        
        Args:
            species: 目标物种
            pressure_types: 压力类型列表（如 ["cold_adaptation", "predation_defense"]）
            pressure_strengths: 压力强度列表
        
        Returns:
            包含参考物种和预测特征变化的提示信息
        """
        if not self.enable_evolution_hints:
            return {}
        
        self._ensure_services()
        
        try:
            prediction = self._predictor.predict_evolution(
                species, 
                pressure_types,
                pressure_strengths
            )
            
            return {
                "reference_species": [
                    {
                        "code": code,
                        "name": name,
                        "similarity": round(sim, 3),
                    }
                    for code, name, sim in prediction.reference_species[:3]
                ],
                "predicted_trait_changes": prediction.predicted_trait_changes,
                "confidence": round(prediction.confidence, 3),
            }
        except Exception as e:
            logger.warning(f"[EmbeddingIntegration] 获取演化提示失败: {e}")
            return {}

    def get_plant_evolution_hints(
        self,
        species: 'Species',
        pressure_types: list[str],
        pressure_strengths: list[float] | None = None
    ) -> dict[str, Any]:
        """获取植物演化提示（供分化服务使用）
        
        【新增】专门为植物设计的演化预测
        
        Args:
            species: 目标物种
            pressure_types: 压力类型列表
            pressure_strengths: 压力强度列表
            
        Returns:
            包含预测特质变化、阶段升级、参考物种的提示信息
        """
        # 非植物使用动物预测
        if species.trophic_level >= 2.0:
            return self.get_evolution_hints(species, pressure_types, pressure_strengths)
        
        if not self.enable_plant_evolution or self._plant_predictor is None:
            return {}
        
        self._ensure_services()
        
        try:
            prediction = self._plant_predictor.predict_evolution(
                species,
                pressure_types,
                pressure_strengths
            )
            
            return {
                "trait_changes": prediction.get("trait_changes", {}),
                "stage_progression": prediction.get("stage_progression", {}),
                "organ_suggestions": prediction.get("organ_suggestions", []),
                "reference_species": prediction.get("reference_species", []),
                "confidence": prediction.get("confidence", 0.5),
                "prompt_context": prediction.get("prompt_context", ""),
            }
        except Exception as e:
            logger.warning(f"[EmbeddingIntegration] 获取植物演化提示失败: {e}")
            return {}

    def on_plant_speciation(
        self,
        turn_index: int,
        parent: 'Species',
        offspring: list['Species'],
        trait_changes: dict,
        milestone: str | None = None
    ) -> None:
        """植物分化后调用（记录演化事件）
        
        Args:
            turn_index: 回合索引
            parent: 父代物种
            offspring: 子代物种列表
            trait_changes: 特质变化
            milestone: 触发的里程碑ID
        """
        self._ensure_services()
        
        # 记录到植物预测器的历史
        if self._plant_predictor:
            self._plant_predictor.record_evolution_event(
                parent.lineage_code,
                turn_index,
                trait_changes,
                milestone=milestone
            )
        
        # 调用通用的分化记录
        trigger_reason = f"植物分化"
        if milestone:
            from ..species.plant_evolution import PLANT_MILESTONES
            m = PLANT_MILESTONES.get(milestone)
            if m:
                trigger_reason = f"植物里程碑: {m.name}"
        
        self.on_speciation(turn_index, parent, offspring, trigger_reason)

    def map_pressures_to_vectors(
        self,
        modifiers: dict[str, float]
    ) -> list[str]:
        """将环境修改器映射到压力向量类型
        
        Args:
            modifiers: 环境修改器字典，如 {"temperature": -5.0, "drought": 3.0}
        
        Returns:
            对应的压力向量类型列表
        """
        pressure_types = []
        
        # 温度映射
        temp = modifiers.get("temperature", 0)
        if temp < -3:
            pressure_types.append("cold_adaptation")
        elif temp > 3:
            pressure_types.append("heat_adaptation")
        
        # 干旱映射
        drought = modifiers.get("drought", 0)
        if drought > 3:
            pressure_types.append("drought_adaptation")
        
        # 洪水/水环境映射
        flood = modifiers.get("flood", 0)
        if flood > 3:
            pressure_types.append("aquatic_adaptation")
        
        # 捕食压力（需要从营养级互动获取）
        predation = modifiers.get("predation", 0)
        if predation > 3:
            pressure_types.append("predation_defense")
        
        return pressure_types

    # ==================== 存档功能 ====================

    def export_for_save(self) -> dict[str, Any]:
        """导出所有数据用于存档"""
        self._ensure_services()
        
        data = {
            "version": "1.0",
            "last_taxonomy_turn": self._last_taxonomy_turn,
        }
        
        if self._current_taxonomy:
            data["taxonomy"] = self._taxonomy.export_for_save(self._current_taxonomy)
        
        data["narrative"] = self._narrative.export_for_save()
        data["evolution_predictor"] = self._predictor.export_for_save()
        
        return data

    def import_from_save(self, data: dict[str, Any]) -> None:
        """从存档导入数据"""
        if not data:
            return
        
        self._ensure_services()
        
        self._last_taxonomy_turn = data.get("last_taxonomy_turn", -999)
        
        if "taxonomy" in data:
            self._current_taxonomy = self._taxonomy.import_from_save(data["taxonomy"])
        
        if "narrative" in data:
            self._narrative.import_from_save(data["narrative"])
        
        if "evolution_predictor" in data:
            self._predictor.import_from_save(data["evolution_predictor"])
        
        logger.info("[EmbeddingIntegration] 从存档恢复数据完成")

    # ==================== 查询功能 ====================

    def get_species_taxonomy(self, species_code: str) -> list[str]:
        """获取物种的分类路径"""
        if not self._current_taxonomy:
            return []
        return self._taxonomy.get_species_classification(species_code, self._current_taxonomy)

    def get_related_species(self, species_code: str, rank: str = "family") -> list[str]:
        """获取同类群的物种"""
        if not self._current_taxonomy:
            return []
        return self._taxonomy.find_related_species(species_code, self._current_taxonomy, rank)

    async def get_turn_narrative(self, turn_index: int) -> str:
        """获取回合叙事"""
        self._ensure_services()
        result = await self._narrative.generate_turn_narrative(turn_index)
        return result.narrative

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息"""
        self._ensure_services()
        
        return {
            "taxonomy": {
                "last_update_turn": self._last_taxonomy_turn,
                "clade_count": len(self._current_taxonomy.clades) if self._current_taxonomy else 0,
            },
            "narrative": self._narrative.get_event_stats(),
            "encyclopedia": self._encyclopedia.get_index_stats(),
            "embedding_cache": self.embeddings.get_cache_stats(),
        }
    
    def clear_all_caches(self) -> dict[str, Any]:
        """清空所有缓存（切换存档时调用）
        
        【重要】加载或创建新存档时必须调用此方法，
        确保所有子服务的缓存被清空，避免数据污染。
        
        清理内容：
        1. SpeciesCacheManager - 物种对象缓存
        2. EmbeddingService - 内存缓存、物种哈希、向量索引
        3. NarrativeEngine - 事件历史
        4. Encyclopedia - 物种索引元数据
        5. TaxonomyService - 分类树缓存
        6. EvolutionPredictor - 预测缓存
        
        Returns:
            清理统计信息
        """
        stats = {
            "species_cache_cleared": False,
            "embedding_indexes_cleared": {},
            "narrative_events_cleared": 0,
            "taxonomy_cleared": False,
        }
        
        # 1. 清空物种缓存管理器
        from ..system.species_cache import get_species_cache
        species_cache = get_species_cache()
        species_cache.clear()
        stats["species_cache_cleared"] = True
        
        # 2. 清空 EmbeddingService 的缓存和索引
        stats["embedding_indexes_cleared"] = self.embeddings.clear_all_indexes()
        
        # 3. 清空各子服务的缓存
        self._ensure_services()
        
        # NarrativeEngine - 清空事件历史
        if self._narrative:
            event_count = len(self._narrative._events)
            self._narrative._events.clear()
            self._narrative._pending_events.clear()
            stats["narrative_events_cleared"] = event_count
        
        # TaxonomyService - 清空分类树
        self._current_taxonomy = None
        self._last_taxonomy_turn = -999
        stats["taxonomy_cleared"] = True
        
        # EvolutionPredictor - 物种数据现在由全局 SpeciesCacheManager 管理
        # 已在上面通过 species_cache.clear() 清空，无需额外操作
        
        logger.info(f"[EmbeddingIntegration] 所有缓存已清空: {stats}")
        return stats
    
    def switch_to_save_context(self, save_dir: 'Path | str | None') -> dict[str, Any]:
        """切换到存档专属的上下文
        
        【重要】创建或加载存档时调用，实现：
        1. 清空所有缓存
        2. 切换向量索引目录到存档专属目录
        
        Args:
            save_dir: 存档目录路径（如 data/saves/my_save/）
                     如果为 None，使用全局缓存目录
        
        Returns:
            切换信息
        """
        # 1. 清空所有缓存
        cache_stats = self.clear_all_caches()
        
        # 2. 切换向量索引目录
        index_stats = self.embeddings.switch_to_save_context(save_dir)
        
        result = {
            "cache_cleared": cache_stats,
            "index_switched": index_stats,
            "save_dir": str(save_dir) if save_dir else "global",
        }
        
        logger.info(f"[EmbeddingIntegration] 已切换到存档上下文: {save_dir}")
        return result

