"""植物演化预测器 - 使用Embedding预测演化方向

【核心功能】
1. 基于压力向量预测特质变化
2. 评估阶段升级准备度
3. 生成演化提示供AI使用
4. 追踪演化历史模式
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..system.embedding import EmbeddingService
    from ...models.species import Species
    from .plant_reference_library import PlantReferenceLibrary

logger = logging.getLogger(__name__)


class PlantEvolutionPredictor:
    """植物演化预测器"""
    
    def __init__(
        self,
        embedding_service: 'EmbeddingService',
        reference_library: 'PlantReferenceLibrary'
    ):
        self.embeddings = embedding_service
        self.reference_lib = reference_library
        
        # 演化历史缓存（用于模式学习）
        self._evolution_history: dict[str, list[dict]] = {}
    
    def predict_evolution(
        self,
        species: 'Species',
        pressure_types: list[str],
        pressure_strengths: list[float] | None = None,
        species_list: list['Species'] | None = None,  # 【新增】用于竞争压力计算
    ) -> dict[str, Any]:
        """预测物种的演化方向
        
        综合考虑：
        1. 当前特质状态
        2. 环境压力向量
        3. 相似物种的历史演化
        4. 阶段升级可能性
        5. 【新增】植物竞争压力
        6. 【新增】食草动物压力
        
        Args:
            species: 物种对象
            pressure_types: 压力类型列表
            pressure_strengths: 压力强度列表（可选）
            species_list: 所有物种列表（可选，用于竞争分析）
            
        Returns:
            {
                "trait_changes": {"特质": 变化值, ...},
                "stage_progression": {...},
                "organ_suggestions": ["器官1", ...],
                "reference_species": [...],
                "confidence": 0.8,
                "prompt_context": "可直接用于AI的上下文文本",
                "competition_pressure": {...},  # 新增
                "herbivory_pressure": {...},    # 新增
            }
        """
        from .plant_evolution import plant_evolution_service
        from .plant_competition import plant_competition_calculator
        
        current_stage = getattr(species, 'life_form_stage', 0)
        
        # 1. 获取压力适应预测
        adaptation = self.reference_lib.predict_adaptation(species, pressure_types)
        
        # 2. 评估阶段升级可能性
        next_stage = current_stage + 1
        stage_progression = self._evaluate_stage_progression(species, next_stage)
        
        # 3. 查找相似物种的演化历史
        similar_plants = self.reference_lib.find_similar_plants(species, top_k=3)
        history_insights = self._analyze_evolution_history(similar_plants)
        
        # 4. 【新增】获取竞争压力和食草压力
        competition_pressure = {}
        herbivory_pressure = {}
        if species_list:
            competition_pressure = plant_competition_calculator.get_species_competition_summary(
                species, species_list
            )
            herbivory_pressure = plant_competition_calculator.get_herbivory_pressure(
                species, species_list
            )
        
        # 5. 综合预测（整合竞争和捕食压力）
        trait_changes = self._merge_predictions(
            adaptation["predicted_trait_changes"],
            history_insights.get("common_changes", {}),
            stage_progression,
            competition_pressure,  # 新增
            herbivory_pressure,    # 新增
        )
        
        # 6. 生成Prompt上下文
        prompt_context = self._build_prompt_context(
            species,
            trait_changes,
            stage_progression,
            similar_plants,
            pressure_types,
            competition_pressure,  # 新增
            herbivory_pressure,    # 新增
        )
        
        return {
            "trait_changes": trait_changes,
            "stage_progression": stage_progression,
            "organ_suggestions": adaptation["suggested_organs"],
            "reference_species": similar_plants,
            "confidence": adaptation["confidence"],
            "prompt_context": prompt_context,
            "competition_pressure": competition_pressure,
            "herbivory_pressure": herbivory_pressure,
        }
    
    def _evaluate_stage_progression(
        self,
        species: 'Species',
        target_stage: int
    ) -> dict[str, Any]:
        """评估阶段升级可能性"""
        from .plant_evolution import PLANT_MILESTONES, plant_evolution_service
        
        current_stage = getattr(species, 'life_form_stage', 0)
        
        # 找到对应的里程碑
        milestone_id = None
        for mid, milestone in PLANT_MILESTONES.items():
            if milestone.from_stage == current_stage and milestone.to_stage == target_stage:
                milestone_id = mid
                break
        
        if not milestone_id:
            return {
                "possible": False,
                "target_stage": target_stage,
                "readiness": 0.0,
                "milestone_id": None,
            }
        
        # 获取准备度
        readiness = self.reference_lib.get_milestone_readiness(species, milestone_id)
        
        # 获取详细条件
        is_met, _, unmet = plant_evolution_service.check_milestone_requirements(species, milestone_id)
        
        return {
            "possible": is_met or readiness["overall_readiness"] > 0.8,
            "target_stage": target_stage,
            "readiness": readiness["overall_readiness"],
            "milestone_id": milestone_id,
            "similarity": readiness["similarity"],
            "trait_readiness": readiness["trait_readiness"],
            "unmet_conditions": unmet if not is_met else [],
        }
    
    def _analyze_evolution_history(self, similar_plants: list[dict]) -> dict[str, Any]:
        """分析相似物种的演化历史，找出共同模式"""
        common_changes = {}
        
        for plant in similar_plants:
            code = plant["lineage_code"]
            if code in self._evolution_history:
                for event in self._evolution_history[code]:
                    for trait, delta in event.get("trait_changes", {}).items():
                        if trait not in common_changes:
                            common_changes[trait] = []
                        common_changes[trait].append(delta)
        
        # 计算平均变化
        avg_changes = {}
        for trait, deltas in common_changes.items():
            if deltas:
                avg_changes[trait] = sum(deltas) / len(deltas)
        
        return {"common_changes": avg_changes}
    
    def _merge_predictions(
        self,
        pressure_changes: dict[str, float],
        history_changes: dict[str, float],
        stage_info: dict[str, Any],
        competition_pressure: dict | None = None,  # 【新增】
        herbivory_pressure: dict | None = None,    # 【新增】
    ) -> dict[str, float]:
        """合并多个预测来源
        
        权重分配：
        - 环境压力适应: 40%
        - 历史模式: 20%
        - 阶段升级: 15%
        - 竞争压力: 15%（新增）
        - 食草压力: 10%（新增）
        """
        merged = {}
        
        # 环境压力适应预测权重 0.4
        for trait, delta in pressure_changes.items():
            merged[trait] = delta * 0.4
        
        # 历史模式权重 0.2
        for trait, delta in history_changes.items():
            if trait in merged:
                merged[trait] += delta * 0.2
            else:
                merged[trait] = delta * 0.2
        
        # 阶段升级预测权重 0.15
        if stage_info.get("possible") or stage_info.get("readiness", 0) > 0.6:
            # 阶段升级时加强相关特质
            stage_boosts = self._get_stage_boost_traits(stage_info.get("target_stage", 0))
            for trait, boost in stage_boosts.items():
                if trait in merged:
                    merged[trait] += boost * 0.15
                else:
                    merged[trait] = boost * 0.15
        
        # 【新增】竞争压力预测权重 0.15
        if competition_pressure and competition_pressure.get("total_pressure", 0) > 0.1:
            competition_boosts = self._get_competition_boost_traits(competition_pressure)
            for trait, boost in competition_boosts.items():
                if trait in merged:
                    merged[trait] += boost * 0.15
                else:
                    merged[trait] = boost * 0.15
        
        # 【新增】食草压力预测权重 0.1
        if herbivory_pressure and herbivory_pressure.get("pressure", 0) > 0.1:
            herbivory_boosts = self._get_herbivory_boost_traits(herbivory_pressure)
            for trait, boost in herbivory_boosts.items():
                if trait in merged:
                    merged[trait] += boost * 0.1
                else:
                    merged[trait] = boost * 0.1
        
        return merged
    
    def _get_stage_boost_traits(self, target_stage: int) -> dict[str, float]:
        """获取阶段升级需要加强的特质"""
        stage_boosts = {
            1: {"多细胞程度": 1.5},
            2: {"多细胞程度": 2.0},
            3: {"保水能力": 2.0, "耐旱性": 1.5},  # 登陆
            4: {"根系发达度": 2.0},  # 真根
            5: {"种子化程度": 2.0, "木质化程度": 1.0},  # 种子
            6: {"散布能力": 1.5, "种子化程度": 1.0},  # 开花
        }
        return stage_boosts.get(target_stage, {})
    
    def _get_competition_boost_traits(self, competition: dict) -> dict[str, float]:
        """【新增】根据竞争压力获取建议的特质变化
        
        Args:
            competition: 竞争压力信息
            
        Returns:
            特质变化建议
        """
        boosts = {}
        strategy = competition.get("competition_strategy", "generalist")
        light_pressure = competition.get("light_pressure", 0)
        nutrient_pressure = competition.get("nutrient_pressure", 0)
        
        # 根据策略推荐特质
        if strategy == "shade_tolerance":
            boosts["光合效率"] = 1.5  # 提高弱光下的光合效率
            boosts["繁殖速度"] = -0.5  # 代价：繁殖放缓
        elif strategy == "height_growth":
            boosts["木质化程度"] = 2.0  # 发展木质化
            boosts["繁殖速度"] = -0.8  # 代价
        elif strategy == "deep_rooting":
            boosts["根系发达度"] = 2.0  # 发展根系
            boosts["散布能力"] = -0.5  # 代价：更固着
        elif strategy == "nutrient_efficiency":
            boosts["养分吸收"] = 1.5  # 提高吸收效率
        elif strategy == "niche_specialization":
            # 差异化演化，根据具体压力决定
            if light_pressure > nutrient_pressure:
                boosts["光合效率"] = 1.0
            else:
                boosts["养分吸收"] = 1.0
        elif strategy == "pioneer":
            boosts["繁殖速度"] = 1.0  # 快速扩张
            boosts["散布能力"] = 0.5
        
        return boosts
    
    def _get_herbivory_boost_traits(self, herbivory: dict) -> dict[str, float]:
        """【新增】根据食草压力获取建议的特质变化
        
        Args:
            herbivory: 食草压力信息
            
        Returns:
            特质变化建议
        """
        boosts = {}
        pressure = herbivory.get("pressure", 0)
        suggested_defense = herbivory.get("suggested_defense", "")
        
        if pressure < 0.1:
            return boosts  # 无需防御
        
        # 根据建议策略推荐特质
        if "化学防御" in suggested_defense or "chemical" in suggested_defense.lower():
            boosts["化学防御"] = 1.5 + pressure  # 压力越大变化越大
            boosts["繁殖速度"] = -0.3  # 代价
        elif "物理防御" in suggested_defense or "physical" in suggested_defense.lower():
            boosts["物理防御"] = 1.5 + pressure
            boosts["光合效率"] = -0.2  # 代价：资源投入防御
        elif "快速繁殖" in suggested_defense or "r-策略" in suggested_defense:
            boosts["繁殖速度"] = 2.0  # r-策略应对高捕食压力
            boosts["化学防御"] = -0.3  # 减少防御投入
        else:
            # 均衡防御
            boosts["化学防御"] = 0.8
            boosts["物理防御"] = 0.7
        
        return boosts
    
    def _build_prompt_context(
        self,
        species: 'Species',
        trait_changes: dict[str, float],
        stage_info: dict[str, Any],
        similar_plants: list[dict],
        pressure_types: list[str],
        competition_pressure: dict | None = None,  # 【新增】
        herbivory_pressure: dict | None = None,    # 【新增】
    ) -> str:
        """构建供AI使用的Prompt上下文"""
        from .trait_config import PlantTraitConfig
        
        lines = ["【Embedding预测参考】"]
        
        # 1. 压力环境
        if pressure_types:
            lines.append(f"当前环境压力：{', '.join(pressure_types)}")
        
        # 2. 预测的特质变化
        if trait_changes:
            changes_str = ", ".join([
                f"{t}{'+' if d > 0 else ''}{d:.1f}"
                for t, d in sorted(trait_changes.items(), key=lambda x: abs(x[1]), reverse=True)[:5]
            ])
            lines.append(f"预测特质变化方向：{changes_str}")
        
        # 3. 阶段升级提示
        readiness = stage_info.get("readiness", 0)
        if readiness > 0.5:
            target_stage = stage_info.get("target_stage", 0)
            stage_name = PlantTraitConfig.get_stage_name(target_stage)
            milestone_id = stage_info.get("milestone_id", "")
            
            from .plant_evolution import PLANT_MILESTONES
            milestone = PLANT_MILESTONES.get(milestone_id)
            milestone_name = milestone.name if milestone else stage_name
            
            if stage_info.get("possible"):
                lines.append(f"✅ 里程碑准备就绪：{milestone_name}（准备度：{readiness:.0%}）")
            else:
                lines.append(f"接近里程碑：{milestone_name}（准备度：{readiness:.0%}）")
                
                # 显示未满足条件
                unmet = stage_info.get("unmet_conditions", [])
                if unmet:
                    lines.append(f"  未满足条件：{', '.join(unmet[:2])}")
        
        # 4. 【新增】竞争压力信息
        if competition_pressure and competition_pressure.get("total_pressure", 0) > 0.1:
            lines.append(f"\n【竞争压力】")
            lines.append(f"  光照竞争: {competition_pressure.get('light_pressure', 0):.0%}")
            lines.append(f"  养分竞争: {competition_pressure.get('nutrient_pressure', 0):.0%}")
            strategy = competition_pressure.get("competition_strategy", "unknown")
            strategy_names = {
                "pioneer": "先锋扩张",
                "shade_tolerance": "耐阴适应",
                "height_growth": "增高竞争",
                "deep_rooting": "深根策略",
                "niche_specialization": "生态位特化",
            }
            lines.append(f"  建议策略: {strategy_names.get(strategy, strategy)}")
        
        # 5. 【新增】食草压力信息
        if herbivory_pressure and herbivory_pressure.get("pressure", 0) > 0.1:
            lines.append(f"\n【食草压力】")
            lines.append(f"  被捕食压力: {herbivory_pressure.get('pressure', 0):.0%}")
            predators = herbivory_pressure.get("predators", [])
            if predators:
                lines.append(f"  主要食草者: {', '.join(predators[:2])}")
            lines.append(f"  建议防御: {herbivory_pressure.get('suggested_defense', '无')}")
        
        # 6. 参考物种
        if similar_plants:
            refs = ", ".join([
                f"{p['common_name']}(相似度{p['similarity']:.0%})"
                for p in similar_plants[:2]
            ])
            lines.append(f"\n参考物种：{refs}")
        
        return "\n".join(lines)
    
    def record_evolution_event(
        self,
        species_code: str,
        turn_index: int,
        trait_changes: dict[str, float],
        stage_change: int | None = None,
        milestone: str | None = None
    ) -> None:
        """记录演化事件（用于历史模式学习）
        
        Args:
            species_code: 物种代码
            turn_index: 回合索引
            trait_changes: 特质变化
            stage_change: 阶段变化（新阶段）
            milestone: 触发的里程碑ID
        """
        if species_code not in self._evolution_history:
            self._evolution_history[species_code] = []
        
        event = {
            "turn": turn_index,
            "trait_changes": trait_changes,
        }
        
        if stage_change is not None:
            event["stage_change"] = stage_change
        
        if milestone:
            event["milestone"] = milestone
        
        self._evolution_history[species_code].append(event)
        
        # 限制历史长度
        if len(self._evolution_history[species_code]) > 20:
            self._evolution_history[species_code] = self._evolution_history[species_code][-20:]
    
    def get_evolution_summary(self, species_code: str) -> dict[str, Any]:
        """获取物种的演化历史摘要"""
        history = self._evolution_history.get(species_code, [])
        
        if not history:
            return {
                "event_count": 0,
                "milestones": [],
                "stage_changes": [],
                "dominant_trait_trends": {},
            }
        
        milestones = [e["milestone"] for e in history if e.get("milestone")]
        stage_changes = [e["stage_change"] for e in history if e.get("stage_change") is not None]
        
        # 计算特质变化趋势
        trait_totals = {}
        for event in history:
            for trait, delta in event.get("trait_changes", {}).items():
                if trait not in trait_totals:
                    trait_totals[trait] = 0
                trait_totals[trait] += delta
        
        # 排序得到主导趋势
        dominant = dict(sorted(trait_totals.items(), key=lambda x: abs(x[1]), reverse=True)[:5])
        
        return {
            "event_count": len(history),
            "milestones": milestones,
            "stage_changes": stage_changes,
            "dominant_trait_trends": dominant,
        }
    
    def update_species_cache(self, species_list) -> None:
        """更新物种缓存（与动物预测器接口兼容）"""
        # 植物预测器不需要额外缓存，使用 reference_library
        pass
    
    def export_for_save(self) -> dict:
        """导出用于存档"""
        return {"evolution_history": self._evolution_history}
    
    def import_from_save(self, data: dict) -> None:
        """从存档导入"""
        self._evolution_history = data.get("evolution_history", {})

