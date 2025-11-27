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
        
        # 缓存
        self._current_taxonomy: 'TaxonomyResult | None' = None
        self._last_taxonomy_turn: int = -999
        
        # 是否启用各功能
        self.enable_taxonomy_updates = True
        self.enable_evolution_hints = True
        self.enable_narrative_events = True
        self.enable_encyclopedia_index = True

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

    # ==================== 回合生命周期钩子 ====================

    def on_turn_start(self, turn_index: int, species_list: Sequence['Species']) -> None:
        """回合开始时调用
        
        - 更新物种索引
        - 构建向量缓存
        """
        self._ensure_services()
        
        if self.enable_encyclopedia_index:
            try:
                self._encyclopedia.build_species_index(species_list)
                logger.debug(f"[EmbeddingIntegration] 更新物种搜索索引: {len(species_list)} 个")
            except Exception as e:
                logger.warning(f"[EmbeddingIntegration] 更新搜索索引失败: {e}")
        
        if self.enable_evolution_hints:
            try:
                self._predictor.build_species_index(species_list)
                logger.debug(f"[EmbeddingIntegration] 更新演化预测索引")
            except Exception as e:
                logger.warning(f"[EmbeddingIntegration] 更新预测索引失败: {e}")

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
        
        - 更新分类树（每N回合）
        - 返回可用于存档的数据
        
        Returns:
            包含 taxonomy 和 narrative 数据的字典
        """
        self._ensure_services()
        result = {}
        
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

