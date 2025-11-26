from __future__ import annotations

import math


class PopulationCalculator:
    """根据生物体型计算合理的种群数量范围。
    
    采用生物量单位（kg）而非个体数
    - 1个规模单位 = 1kg 生物量
    - 地块约8万平方公里
    - 基于体型的幂律关系：体型越大，总生物量越小
    
    基于生态学原理：
    - 体型越大，代谢需求越高，环境承载力越小
    - 遵循幂律关系：种群密度 ∝ 体重^(-0.75)
    """
    
    @staticmethod
    def calculate_reasonable_population(
        body_length_cm: float,
        body_weight_g: float | None = None,
        habitat_quality: float = 1.0,
    ) -> tuple[int, int]:
        """计算合理的种群生物量范围（单位：kg）。
        
        Args:
            body_length_cm: 体长（厘米）
            body_weight_g: 单个个体体重（克），如果为None则根据体长估算
            habitat_quality: 栖息地质量系数（0.5-2.0，默认1.0）
            
        Returns:
            (最小合理生物量kg, 最大合理生物量kg)
        """
        # 如果没有体重，根据体长估算（假设大致球形或圆柱形）
        if body_weight_g is None or body_weight_g <= 0:
            # 粗略估算：体重 ≈ 体长^3（立方关系）
            body_weight_g = max(0.000001, (body_length_cm ** 3) * 0.1)
        
        # 【简化方案】直接基于体重估算全球生物量范围
        # 不区分具体的生态系统类型，而是使用体型-生物量的幂律关系
        # 参考地球数据：
        # - 全球植物生物量：~450 Gt (4.5×10^14 kg)
        # - 全球细菌生物量：~70 Gt
        # - 全球动物生物量：~2 Gt
        # 
        # 一个地块约占全球陆地+海洋的 80,000 / 510,000,000 ≈ 1/6,375
        # 因此单个物种在单个地块的合理生物量应该在 10^6 - 10^9 kg 数量级
        
        body_weight_kg = body_weight_g / 1000
        
        # 使用幂律关系估算：生物量 ∝ (体重)^(-0.75)
        # 基准：1kg个体，全球生物量约 10^8 kg
        base_global_biomass = 1e8  # kg
        
        # 根据体重调整（越小越多）
        scale_factor = (body_weight_kg / 1.0) ** (-0.75)
        
        # 单个地块的生物量（全球的1/5000左右）
        block_fraction = 1 / 5000
        
        # 计算基准生物量
        base_biomass = base_global_biomass * scale_factor * block_fraction
        
        # 设置合理范围（最小10%，最大200%）
        min_biomass_kg = int(base_biomass * 0.1)
        max_biomass_kg = int(base_biomass * 2.0)
        
        # 应用栖息地质量系数
        habitat_quality = max(0.5, min(2.0, habitat_quality))
        min_biomass_kg = int(min_biomass_kg * habitat_quality)
        max_biomass_kg = int(max_biomass_kg * habitat_quality)
        
        # 确保在合理范围内
        # 最小：100 kg（即使是大型动物也需要一定生物量）
        # 最大：10^11 kg（避免单个物种占据过多）
        min_biomass_kg = max(100, min(min_biomass_kg, int(1e11)))
        max_biomass_kg = max(1000, min(max_biomass_kg, int(1e11)))
        
        return (min_biomass_kg, max_biomass_kg)
    
    @staticmethod
    def get_initial_population(
        body_length_cm: float,
        body_weight_g: float | None = None,
        habitat_quality: float = 1.0,
    ) -> int:
        """获取推荐的初始种群数量（范围中位数）。"""
        min_pop, max_pop = PopulationCalculator.calculate_reasonable_population(
            body_length_cm, body_weight_g, habitat_quality
        )
        # 返回对数中位数（更合理的分布）
        import math
        log_mid = (math.log10(min_pop) + math.log10(max_pop)) / 2
        return int(10 ** log_mid)
    
    @staticmethod
    def validate_population(
        population: int,
        body_length_cm: float,
        body_weight_g: float | None = None,
    ) -> tuple[bool, str]:
        """验证种群数量是否合理。
        
        Returns:
            (是否合理, 提示信息)
        """
        min_pop, max_pop = PopulationCalculator.calculate_reasonable_population(
            body_length_cm, body_weight_g
        )
        
        if population < min_pop * 0.1:
            return (False, f"种群数量过低（建议范围：{min_pop}-{max_pop}）")
        elif population > max_pop * 10:
            return (False, f"种群数量过高（建议范围：{min_pop}-{max_pop}）")
        elif population < min_pop:
            return (True, f"种群数量偏低但可接受（建议范围：{min_pop}-{max_pop}）")
        elif population > max_pop:
            return (True, f"种群数量偏高但可接受（建议范围：{min_pop}-{max_pop}）")
        else:
            return (True, "种群数量合理")

