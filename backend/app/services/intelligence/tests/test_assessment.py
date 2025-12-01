"""
Test Assessment - BiologicalAssessment 解析测试

测试 BiologicalAssessment 的解析和 clamp 逻辑。
"""

import pytest
from ..schemas import BiologicalAssessment, AssessmentTier


class TestBiologicalAssessmentParsing:
    """BiologicalAssessment 解析测试"""
    
    def test_parse_valid_output(self):
        """解析有效的 LLM 输出"""
        raw_output = {
            "mortality_modifier": 0.8,
            "r_adjust": 0.1,
            "k_adjust": -0.2,
            "migration_bias": 0.5,
            "speciation_signal": 0.7,
            "ecological_fate": "thriving",
            "narrative": "This species is doing well.",
            "headline": "Success Story",
            "mood": "positive",
            "confidence": 0.9,
        }
        
        assessment = BiologicalAssessment.from_llm_output(
            species_id=1,
            lineage_code="TEST-001",
            raw_output=raw_output,
            tier=AssessmentTier.A,
        )
        
        assert assessment.mortality_modifier == 0.8
        assert assessment.r_adjust == 0.1
        assert assessment.k_adjust == -0.2
        assert assessment.migration_bias == 0.5
        assert assessment.speciation_signal == 0.7
        assert assessment.ecological_fate == "thriving"
        assert assessment.narrative == "This species is doing well."
        assert assessment.tier == AssessmentTier.A
    
    def test_clamp_mortality_modifier(self):
        """死亡率修正应该被 clamp 到安全范围"""
        # 超出上限
        raw_output = {"mortality_modifier": 3.0}
        assessment = BiologicalAssessment.from_llm_output(1, "TEST", raw_output)
        assert assessment.mortality_modifier == 1.8  # 上限
        
        # 超出下限
        raw_output = {"mortality_modifier": 0.1}
        assessment = BiologicalAssessment.from_llm_output(1, "TEST", raw_output)
        assert assessment.mortality_modifier == 0.3  # 下限
        
        # 正常范围
        raw_output = {"mortality_modifier": 1.0}
        assessment = BiologicalAssessment.from_llm_output(1, "TEST", raw_output)
        assert assessment.mortality_modifier == 1.0
    
    def test_clamp_r_adjust(self):
        """繁殖率调整应该被 clamp 到安全范围"""
        # 超出上限
        raw_output = {"r_adjust": 0.5}
        assessment = BiologicalAssessment.from_llm_output(1, "TEST", raw_output)
        assert assessment.r_adjust == 0.3  # 上限
        
        # 超出下限
        raw_output = {"r_adjust": -0.5}
        assessment = BiologicalAssessment.from_llm_output(1, "TEST", raw_output)
        assert assessment.r_adjust == -0.3  # 下限
    
    def test_clamp_speciation_signal(self):
        """分化信号应该被 clamp 到 [0, 1]"""
        raw_output = {"speciation_signal": 1.5}
        assessment = BiologicalAssessment.from_llm_output(1, "TEST", raw_output)
        assert assessment.speciation_signal == 1.0
        
        raw_output = {"speciation_signal": -0.5}
        assessment = BiologicalAssessment.from_llm_output(1, "TEST", raw_output)
        assert assessment.speciation_signal == 0.0
    
    def test_handle_missing_fields(self):
        """处理缺失字段"""
        raw_output = {}  # 空输出
        
        assessment = BiologicalAssessment.from_llm_output(1, "TEST", raw_output)
        
        # 应该使用默认值
        assert assessment.mortality_modifier == 1.0
        assert assessment.r_adjust == 0.0
        assert assessment.k_adjust == 0.0
        assert assessment.migration_bias == 0.0
        assert assessment.speciation_signal == 0.0
        assert assessment.ecological_fate == "stable"
    
    def test_handle_invalid_types(self):
        """处理无效类型"""
        raw_output = {
            "mortality_modifier": "invalid",
            "r_adjust": None,
            "speciation_signal": "0.5",  # 字符串数字
        }
        
        assessment = BiologicalAssessment.from_llm_output(1, "TEST", raw_output)
        
        # 应该使用中间值或转换成功
        assert 0.3 <= assessment.mortality_modifier <= 1.8
        assert -0.3 <= assessment.r_adjust <= 0.3
    
    def test_k_adjust_alias(self):
        """K_adjust 应该被识别为 k_adjust"""
        raw_output = {"K_adjust": 0.2}  # 大写 K
        
        assessment = BiologicalAssessment.from_llm_output(1, "TEST", raw_output)
        
        assert assessment.k_adjust == 0.2
    
    def test_create_default(self):
        """创建默认评估"""
        assessment = BiologicalAssessment.create_default(
            species_id=1,
            lineage_code="TEST-001",
            tier=AssessmentTier.C,
        )
        
        assert assessment.mortality_modifier == 1.0
        assert assessment.r_adjust == 0.0
        assert assessment.ecological_fate == "default_fallback"
        assert "默认" in assessment.reasoning or "fallback" in assessment.reasoning


class TestAssessmentDefaults:
    """测试评估默认值"""
    
    def test_defaults_are_neutral(self):
        """默认值应该是中性的（不影响数值）"""
        assessment = BiologicalAssessment.create_default(1, "TEST")
        
        # 死亡率乘数为 1（不改变）
        assert assessment.mortality_modifier == 1.0
        
        # 加法调整为 0
        assert assessment.r_adjust == 0.0
        assert assessment.k_adjust == 0.0
        assert assessment.migration_bias == 0.0
        
        # 分化信号为 0
        assert assessment.speciation_signal == 0.0
    
    def test_default_tier_is_c(self):
        """默认层级应该是 C"""
        assessment = BiologicalAssessment.create_default(1, "TEST")
        assert assessment.tier == AssessmentTier.C


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


