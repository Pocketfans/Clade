"""
Modifier Applicator - 数值修正应用器

统一的数值修正入口，所有业务模块通过此入口获取修正后的数值。
业务 Stage 不再直接读取 BiologicalAssessment。
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Dict, Optional

from .config import IntelligenceConfig, DEFAULT_CONFIG
from .schemas import BiologicalAssessment

logger = logging.getLogger(__name__)


class AdjustmentType(Enum):
    """修正类型枚举"""
    MORTALITY = "mortality"
    REPRODUCTION_R = "reproduction_r"
    CARRYING_CAPACITY = "carrying_capacity"
    MIGRATION = "migration"
    CLIMATE_TOLERANCE = "climate_tolerance"
    PREDATION = "predation"
    SPECIATION = "speciation"


class ModifierApplicator:
    """数值修正应用器
    
    核心职责：
    1. 存储和管理 BiologicalAssessment 结果
    2. 提供统一的 apply() 接口获取修正后的数值
    3. 处理降级策略（无评估时返回默认值）
    
    使用方式：
    ```python
    # 在业务 Stage 中
    final_mortality = modifier.apply(species_id, base_mortality, "mortality")
    final_r = modifier.apply(species_id, base_r, "reproduction_r")
    ```
    
    扩展方式：
    新增修正类型时，只需在 apply() 方法中添加对应的处理逻辑。
    """
    
    def __init__(
        self,
        config: IntelligenceConfig | None = None,
    ):
        self.config = config or DEFAULT_CONFIG
        self._assessments: Dict[str, BiologicalAssessment] = {}
        self._lineage_to_id: Dict[str, int] = {}
        
    def set_assessments(
        self,
        assessments: Dict[str, BiologicalAssessment],
    ) -> None:
        """设置评估结果
        
        Args:
            assessments: lineage_code -> BiologicalAssessment 映射
        """
        self._assessments = assessments
        self._lineage_to_id = {
            code: a.species_id
            for code, a in assessments.items()
        }
        logger.info(f"[ModifierApplicator] 加载了 {len(assessments)} 个评估结果")
    
    def get_assessment(
        self,
        species_id: int | str,
    ) -> Optional[BiologicalAssessment]:
        """获取物种的评估结果
        
        Args:
            species_id: 物种 ID 或 lineage_code
            
        Returns:
            BiologicalAssessment 或 None
        """
        # 支持两种查找方式
        if isinstance(species_id, str):
            return self._assessments.get(species_id)
        
        # 通过 species_id 查找
        for code, assessment in self._assessments.items():
            if assessment.species_id == species_id:
                return assessment
        return None
    
    def apply(
        self,
        species_id: int | str,
        base_value: float,
        adjustment_type: str | AdjustmentType,
    ) -> float:
        """应用修正并返回最终值
        
        这是业务模块的统一入口。
        
        Args:
            species_id: 物种 ID 或 lineage_code
            base_value: 基础值
            adjustment_type: 修正类型
            
        Returns:
            修正后的值
        """
        # 获取评估结果
        assessment = self.get_assessment(species_id)
        
        if assessment is None:
            # 无评估，返回默认值
            return self._apply_default(base_value, adjustment_type)
        
        # 标准化 adjustment_type
        if isinstance(adjustment_type, str):
            try:
                adjustment_type = AdjustmentType(adjustment_type)
            except ValueError:
                logger.warning(f"未知的修正类型: {adjustment_type}")
                return base_value
        
        # 根据类型应用修正
        if adjustment_type == AdjustmentType.MORTALITY:
            return self._apply_mortality(base_value, assessment)
        elif adjustment_type == AdjustmentType.REPRODUCTION_R:
            return self._apply_reproduction_r(base_value, assessment)
        elif adjustment_type == AdjustmentType.CARRYING_CAPACITY:
            return self._apply_carrying_capacity(base_value, assessment)
        elif adjustment_type == AdjustmentType.MIGRATION:
            return self._apply_migration(base_value, assessment)
        elif adjustment_type == AdjustmentType.CLIMATE_TOLERANCE:
            return self._apply_climate_tolerance(base_value, assessment)
        elif adjustment_type == AdjustmentType.PREDATION:
            return self._apply_predation(base_value, assessment)
        elif adjustment_type == AdjustmentType.SPECIATION:
            return self._apply_speciation(base_value, assessment)
        else:
            return base_value
    
    def _apply_default(
        self,
        base_value: float,
        adjustment_type: str | AdjustmentType,
    ) -> float:
        """应用默认修正（无评估时使用）"""
        if isinstance(adjustment_type, str):
            try:
                adjustment_type = AdjustmentType(adjustment_type)
            except ValueError:
                return base_value
        
        if adjustment_type == AdjustmentType.MORTALITY:
            return base_value * self.config.fallback_mortality_modifier
        elif adjustment_type == AdjustmentType.REPRODUCTION_R:
            return base_value + self.config.fallback_r_adjust
        elif adjustment_type == AdjustmentType.CARRYING_CAPACITY:
            return base_value * (1 + self.config.fallback_k_adjust)
        else:
            return base_value
    
    # =========================================================================
    # 具体修正逻辑
    # =========================================================================
    
    def _apply_mortality(
        self,
        base_value: float,
        assessment: BiologicalAssessment,
    ) -> float:
        """应用死亡率修正
        
        base_value * mortality_modifier
        """
        result = base_value * assessment.mortality_modifier
        
        # 限制范围
        min_mod, max_mod = self.config.mortality_mod_range
        effective_modifier = max(min_mod, min(max_mod, assessment.mortality_modifier))
        
        return base_value * effective_modifier
    
    def _apply_reproduction_r(
        self,
        base_value: float,
        assessment: BiologicalAssessment,
    ) -> float:
        """应用繁殖率修正
        
        base_value + r_adjust
        """
        min_adj, max_adj = self.config.r_adjust_range
        effective_adjust = max(min_adj, min(max_adj, assessment.r_adjust))
        
        result = base_value + effective_adjust
        
        # 确保繁殖率不为负
        return max(0.0, result)
    
    def _apply_carrying_capacity(
        self,
        base_value: float,
        assessment: BiologicalAssessment,
    ) -> float:
        """应用承载力修正
        
        base_value * (1 + k_adjust)
        """
        min_adj, max_adj = self.config.k_adjust_range
        effective_adjust = max(min_adj, min(max_adj, assessment.k_adjust))
        
        result = base_value * (1 + effective_adjust)
        
        # 确保承载力不为负
        return max(0.0, result)
    
    def _apply_migration(
        self,
        base_value: float,
        assessment: BiologicalAssessment,
    ) -> float:
        """应用迁徙倾向修正
        
        迁徙概率 = base_value * (1 + migration_bias * 0.5)
        migration_bias > 0: 增加迁徙概率
        migration_bias < 0: 减少迁徙概率
        """
        min_bias, max_bias = self.config.migration_bias_range
        effective_bias = max(min_bias, min(max_bias, assessment.migration_bias))
        
        # 迁徙偏向影响迁徙概率
        result = base_value * (1 + effective_bias * 0.5)
        
        # 限制在 [0, 1] 范围
        return max(0.0, min(1.0, result))
    
    def _apply_climate_tolerance(
        self,
        base_value: float,
        assessment: BiologicalAssessment,
    ) -> float:
        """应用气候耐受性修正
        
        base_value + climate_bandwidth
        """
        return base_value + assessment.climate_bandwidth
    
    def _apply_predation(
        self,
        base_value: float,
        assessment: BiologicalAssessment,
    ) -> float:
        """应用捕食脆弱性修正
        
        predation_vulnerability > 0: 更容易被捕食
        predation_vulnerability < 0: 更难被捕食
        """
        vulnerability = assessment.predation_vulnerability
        
        # 调整被捕食概率
        result = base_value * (1 + vulnerability * 0.3)
        
        return max(0.0, min(1.0, result))
    
    def _apply_speciation(
        self,
        base_value: float,
        assessment: BiologicalAssessment,
    ) -> float:
        """应用分化信号修正
        
        speciation_signal 作为分化概率的加成
        """
        # 分化概率 = 基础概率 + 信号强度 * 权重
        result = base_value + assessment.speciation_signal * 0.1
        
        return max(0.0, min(1.0, result))
    
    # =========================================================================
    # 批量应用
    # =========================================================================
    
    def apply_batch(
        self,
        species_values: Dict[str, float],
        adjustment_type: str | AdjustmentType,
    ) -> Dict[str, float]:
        """批量应用修正
        
        Args:
            species_values: lineage_code -> base_value 映射
            adjustment_type: 修正类型
            
        Returns:
            lineage_code -> adjusted_value 映射
        """
        results = {}
        for code, base_value in species_values.items():
            results[code] = self.apply(code, base_value, adjustment_type)
        return results
    
    # =========================================================================
    # 查询接口
    # =========================================================================
    
    def get_ecological_fate(
        self,
        species_id: int | str,
    ) -> str:
        """获取物种的生态命运预测"""
        assessment = self.get_assessment(species_id)
        if assessment:
            return assessment.ecological_fate
        return "unknown"
    
    def get_evolution_direction(
        self,
        species_id: int | str,
    ) -> list[str]:
        """获取物种的演化方向提示"""
        assessment = self.get_assessment(species_id)
        if assessment:
            return assessment.evolution_direction
        return []
    
    def get_narrative(
        self,
        species_id: int | str,
    ) -> str:
        """获取物种的叙事描述"""
        assessment = self.get_assessment(species_id)
        if assessment:
            return assessment.narrative
        return ""
    
    def get_speciation_signal(
        self,
        species_id: int | str,
    ) -> float:
        """获取物种的分化信号"""
        assessment = self.get_assessment(species_id)
        if assessment:
            return assessment.speciation_signal
        return 0.0
    
    def should_speciate(
        self,
        species_id: int | str,
        threshold: float = 0.7,
    ) -> bool:
        """判断物种是否应该分化"""
        return self.get_speciation_signal(species_id) >= threshold
    
    # =========================================================================
    # 统计
    # =========================================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        if not self._assessments:
            return {"count": 0}
        
        fates = {}
        for assessment in self._assessments.values():
            fate = assessment.ecological_fate
            fates[fate] = fates.get(fate, 0) + 1
        
        avg_mortality_mod = sum(
            a.mortality_modifier for a in self._assessments.values()
        ) / len(self._assessments)
        
        speciation_candidates = sum(
            1 for a in self._assessments.values()
            if a.speciation_signal > 0.5
        )
        
        return {
            "count": len(self._assessments),
            "fates": fates,
            "avg_mortality_modifier": avg_mortality_mod,
            "speciation_candidates": speciation_candidates,
        }
    
    def clear(self) -> None:
        """清除所有评估结果"""
        self._assessments.clear()
        self._lineage_to_id.clear()


