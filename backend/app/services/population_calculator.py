from __future__ import annotations

import math


class PopulationCalculator:
    """根据生物体型计算合理的种群数量范围。
    
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
        """计算合理的种群数量范围。
        
        Args:
            body_length_cm: 体长（厘米）
            body_weight_g: 体重（克），如果为None则根据体长估算
            habitat_quality: 栖息地质量系数（0.5-2.0，默认1.0）
            
        Returns:
            (最小合理数量, 最大合理数量)
        """
        # 如果没有体重，根据体长估算（假设大致球形或圆柱形）
        if body_weight_g is None or body_weight_g <= 0:
            # 粗略估算：体重 ≈ 体长^3（立方关系）
            body_weight_g = max(0.000001, (body_length_cm ** 3) * 0.1)
        
        # 根据体重分类
        if body_weight_g < 0.00001:  # < 0.01 毫克（病毒、超微型细菌）
            base_min = 10_000_000
            base_max = 100_000_000
        elif body_weight_g < 0.0001:  # < 0.1 毫克（细菌、古菌）
            base_min = 1_000_000
            base_max = 10_000_000
        elif body_weight_g < 0.001:  # < 1 毫克（大型细菌、小型原生生物）
            base_min = 500_000
            base_max = 5_000_000
        elif body_weight_g < 0.01:  # < 10 毫克（原生生物）
            base_min = 100_000
            base_max = 1_000_000
        elif body_weight_g < 0.1:  # < 100 毫克（大型单细胞、小型多细胞）
            base_min = 50_000
            base_max = 500_000
        elif body_weight_g < 1:  # < 1 克（小型无脊椎动物）
            base_min = 10_000
            base_max = 100_000
        elif body_weight_g < 10:  # < 10 克（昆虫、小鱼等）
            base_min = 5_000
            base_max = 50_000
        elif body_weight_g < 100:  # < 100 克（老鼠大小）
            base_min = 1_000
            base_max = 10_000
        elif body_weight_g < 1000:  # < 1 千克（兔子大小）
            base_min = 500
            base_max = 5_000
        elif body_weight_g < 10000:  # < 10 千克（狗大小）
            base_min = 200
            base_max = 2_000
        elif body_weight_g < 100000:  # < 100 千克（人类大小）
            base_min = 100
            base_max = 1_000
        elif body_weight_g < 1000000:  # < 1 吨（牛、马大小）
            base_min = 50
            base_max = 500
        else:  # > 1 吨（大型动物）
            # 对于巨型动物，继续缩小
            base_min = max(10, int(50 * math.pow(1000000 / body_weight_g, 0.5)))
            base_max = max(100, int(500 * math.pow(1000000 / body_weight_g, 0.5)))
        
        # 应用栖息地质量系数
        habitat_quality = max(0.5, min(2.0, habitat_quality))
        min_pop = int(base_min * habitat_quality)
        max_pop = int(base_max * habitat_quality)
        
        return (min_pop, max_pop)
    
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

