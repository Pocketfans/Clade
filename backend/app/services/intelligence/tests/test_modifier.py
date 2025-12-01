"""
Test Modifier Applicator - ModifierApplicator 测试

测试统一数值修正入口的各种场景。
"""

import pytest
from ..modifier_applicator import ModifierApplicator, AdjustmentType
from ..schemas import BiologicalAssessment, AssessmentTier
from ..config import IntelligenceConfig


class TestModifierApplicator:
    """ModifierApplicator 测试"""
    
    def setup_method(self):
        self.config = IntelligenceConfig()
        self.modifier = ModifierApplicator(config=self.config)
    
    def test_apply_without_assessment_returns_default(self):
        """无评估时应返回默认值"""
        # 不设置任何 assessment
        
        result = self.modifier.apply("UNKNOWN", 0.5, "mortality")
        
        # 应该返回基于 fallback_mortality_modifier 的值
        assert result == 0.5 * self.config.fallback_mortality_modifier
    
    def test_apply_mortality_modifier(self):
        """死亡率修正应用"""
        assessment = BiologicalAssessment(
            species_id=1,
            lineage_code="TEST-001",
            mortality_modifier=0.8,  # 降低 20%
        )
        self.modifier.set_assessments({"TEST-001": assessment})
        
        base_mortality = 0.5
        result = self.modifier.apply("TEST-001", base_mortality, "mortality")
        
        assert result == pytest.approx(0.4, rel=0.01)  # 0.5 * 0.8
    
    def test_apply_reproduction_r(self):
        """繁殖率修正应用"""
        assessment = BiologicalAssessment(
            species_id=1,
            lineage_code="TEST-001",
            r_adjust=0.1,  # 增加 0.1
        )
        self.modifier.set_assessments({"TEST-001": assessment})
        
        base_r = 1.0
        result = self.modifier.apply("TEST-001", base_r, "reproduction_r")
        
        assert result == pytest.approx(1.1, rel=0.01)
    
    def test_apply_carrying_capacity(self):
        """承载力修正应用"""
        assessment = BiologicalAssessment(
            species_id=1,
            lineage_code="TEST-001",
            k_adjust=0.2,  # 增加 20%
        )
        self.modifier.set_assessments({"TEST-001": assessment})
        
        base_k = 10000
        result = self.modifier.apply("TEST-001", base_k, "carrying_capacity")
        
        assert result == pytest.approx(12000, rel=0.01)  # 10000 * 1.2
    
    def test_apply_migration_bias(self):
        """迁徙偏向修正应用"""
        assessment = BiologicalAssessment(
            species_id=1,
            lineage_code="TEST-001",
            migration_bias=0.5,  # 增加迁徙倾向
        )
        self.modifier.set_assessments({"TEST-001": assessment})
        
        base_probability = 0.3
        result = self.modifier.apply("TEST-001", base_probability, "migration")
        
        # migration_bias = 0.5 -> probability * (1 + 0.5 * 0.5) = 0.3 * 1.25 = 0.375
        assert result > base_probability
        assert result <= 1.0
    
    def test_apply_speciation_signal(self):
        """分化信号修正应用"""
        assessment = BiologicalAssessment(
            species_id=1,
            lineage_code="TEST-001",
            speciation_signal=0.8,  # 强分化信号
        )
        self.modifier.set_assessments({"TEST-001": assessment})
        
        base_probability = 0.1
        result = self.modifier.apply("TEST-001", base_probability, "speciation")
        
        # 应该增加分化概率
        assert result > base_probability
    
    def test_apply_with_species_id(self):
        """使用 species_id 查找评估"""
        assessment = BiologicalAssessment(
            species_id=42,
            lineage_code="TEST-001",
            mortality_modifier=0.7,
        )
        self.modifier.set_assessments({"TEST-001": assessment})
        
        # 使用 species_id 查找
        result = self.modifier.apply(42, 0.5, "mortality")
        
        assert result == pytest.approx(0.35, rel=0.01)
    
    def test_apply_enum_adjustment_type(self):
        """支持枚举类型的调整类型"""
        assessment = BiologicalAssessment(
            species_id=1,
            lineage_code="TEST-001",
            mortality_modifier=0.9,
        )
        self.modifier.set_assessments({"TEST-001": assessment})
        
        result = self.modifier.apply("TEST-001", 0.5, AdjustmentType.MORTALITY)
        
        assert result == pytest.approx(0.45, rel=0.01)
    
    def test_get_ecological_fate(self):
        """获取生态命运"""
        assessment = BiologicalAssessment(
            species_id=1,
            lineage_code="TEST-001",
            ecological_fate="endangered",
        )
        self.modifier.set_assessments({"TEST-001": assessment})
        
        fate = self.modifier.get_ecological_fate("TEST-001")
        
        assert fate == "endangered"
    
    def test_get_evolution_direction(self):
        """获取演化方向"""
        assessment = BiologicalAssessment(
            species_id=1,
            lineage_code="TEST-001",
            evolution_direction=["larger_body", "cold_adaptation"],
        )
        self.modifier.set_assessments({"TEST-001": assessment})
        
        directions = self.modifier.get_evolution_direction("TEST-001")
        
        assert "larger_body" in directions
        assert "cold_adaptation" in directions
    
    def test_should_speciate(self):
        """判断是否应该分化"""
        assessment = BiologicalAssessment(
            species_id=1,
            lineage_code="TEST-001",
            speciation_signal=0.8,
        )
        self.modifier.set_assessments({"TEST-001": assessment})
        
        # 默认阈值 0.7
        assert self.modifier.should_speciate("TEST-001") is True
        assert self.modifier.should_speciate("TEST-001", threshold=0.9) is False
    
    def test_batch_apply(self):
        """批量应用修正"""
        assessments = {
            "SP-001": BiologicalAssessment(1, "SP-001", mortality_modifier=0.8),
            "SP-002": BiologicalAssessment(2, "SP-002", mortality_modifier=1.2),
        }
        self.modifier.set_assessments(assessments)
        
        base_values = {"SP-001": 0.5, "SP-002": 0.3}
        results = self.modifier.apply_batch(base_values, "mortality")
        
        assert results["SP-001"] == pytest.approx(0.4, rel=0.01)
        assert results["SP-002"] == pytest.approx(0.36, rel=0.01)
    
    def test_get_stats(self):
        """获取统计信息"""
        assessments = {
            "SP-001": BiologicalAssessment(1, "SP-001", ecological_fate="thriving", speciation_signal=0.8),
            "SP-002": BiologicalAssessment(2, "SP-002", ecological_fate="declining", speciation_signal=0.2),
            "SP-003": BiologicalAssessment(3, "SP-003", ecological_fate="thriving", speciation_signal=0.6),
        }
        self.modifier.set_assessments(assessments)
        
        stats = self.modifier.get_stats()
        
        assert stats["count"] == 3
        assert stats["fates"]["thriving"] == 2
        assert stats["fates"]["declining"] == 1
        assert stats["speciation_candidates"] == 2  # signal > 0.5
    
    def test_clear(self):
        """清除评估"""
        assessment = BiologicalAssessment(1, "TEST-001", mortality_modifier=0.8)
        self.modifier.set_assessments({"TEST-001": assessment})
        
        self.modifier.clear()
        
        assert self.modifier.get_assessment("TEST-001") is None


class TestModifierRangeClamping:
    """测试修正范围限制"""
    
    def setup_method(self):
        self.config = IntelligenceConfig(
            mortality_mod_range=(0.5, 1.5),
            r_adjust_range=(-0.2, 0.2),
            k_adjust_range=(-0.3, 0.3),
        )
        self.modifier = ModifierApplicator(config=self.config)
    
    def test_mortality_clamped_to_config_range(self):
        """死亡率修正应该被限制在配置范围内"""
        # 创建超出范围的评估
        assessment = BiologicalAssessment(
            species_id=1,
            lineage_code="TEST-001",
            mortality_modifier=2.0,  # 超出上限 1.5
        )
        self.modifier.set_assessments({"TEST-001": assessment})
        
        result = self.modifier.apply("TEST-001", 0.4, "mortality")
        
        # 应该被 clamp 到 1.5
        assert result == pytest.approx(0.4 * 1.5, rel=0.01)
    
    def test_r_adjust_clamped(self):
        """繁殖率调整应该被限制"""
        assessment = BiologicalAssessment(
            species_id=1,
            lineage_code="TEST-001",
            r_adjust=0.5,  # 超出上限 0.2
        )
        self.modifier.set_assessments({"TEST-001": assessment})
        
        result = self.modifier.apply("TEST-001", 1.0, "reproduction_r")
        
        # 应该被 clamp 到 0.2
        assert result == pytest.approx(1.2, rel=0.01)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


