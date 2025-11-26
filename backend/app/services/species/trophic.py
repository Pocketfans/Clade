"""营养级（Trophic Level）计算与管理服务。

营养级定义：
- 1.0-1.9: 生产者/分解者
- 2.0-2.9: 主要草食
- 3.0-3.9: 中层捕食者
- 4.0-4.9: 高层捕食者
- 5.0+: 顶级掠食者/超级掠食者

计算公式：T = 1 + Σ(prey_proportion × prey_T)
"""
from __future__ import annotations

import logging
from typing import Sequence
from ...models.species import Species

logger = logging.getLogger(__name__)


class TrophicLevelCalculator:
    """营养级计算器"""
    
    def calculate_trophic_level(self, species: Species, all_species: Sequence[Species]) -> float:
        """计算物种的营养级
        
        Args:
            species: 目标物种
            all_species: 所有物种列表（用于分析食性）
            
        Returns:
            营养级（1.0-6.0+）
        """
        desc = species.description.lower()
        
        # 1. 生产者检测（营养级 1.0）
        if self._is_producer(desc):
            return 1.0
        
        # 2. 分解者检测（营养级 1.5）
        if self._is_decomposer(desc):
            return 1.5
        
        # 3. 基于食性描述推断营养级
        diet_info = self._parse_diet(desc)
        
        if not diet_info["prey_items"]:
            # 无明确食性信息，基于关键词估算
            estimated = self._estimate_from_keywords(desc)
            logger.debug(f"[营养级] {species.common_name} 无食性信息，关键词估算为 {estimated}")
            return estimated
        
        # 4. 根据食物组成计算
        trophic = 1.0
        for prey_desc, proportion in diet_info["prey_items"]:
            # 查找被捕食物种的营养级
            prey_trophic = self._find_prey_trophic(prey_desc, all_species)
            trophic += proportion * prey_trophic
        
        result = round(trophic, 2)
        logger.debug(f"[营养级] {species.common_name} 计算结果: {result} (基于 {len(diet_info['prey_items'])} 种食物)")
        return result
    
    def _is_producer(self, desc: str) -> bool:
        """判断是否为生产者"""
        producer_keywords = [
            "光合", "photosyn", "藻", "algae", "植物", "plant",
            "自养", "autotroph", "叶绿", "chlorophyll", "固定二氧化碳",
            "初级生产者", "primary producer"
        ]
        return any(kw in desc for kw in producer_keywords)
    
    def _is_decomposer(self, desc: str) -> bool:
        """判断是否为分解者"""
        decomposer_keywords = [
            "分解", "decompos", "腐食", "腐生", "sapro",
            "清道夫", "scavenger", "腐肉", "carrion"
        ]
        return any(kw in desc for kw in decomposer_keywords)
    
    def _parse_diet(self, desc: str) -> dict:
        """解析食性描述
        
        Returns:
            {"prey_items": [(prey_description, proportion)]}
        """
        prey_items = []
        
        # 检测食物比例描述（如"70%藻类，30%碎屑"）
        import re
        percentage_pattern = r'(\d+)%\s*([^，。,\s]+)'
        matches = re.findall(percentage_pattern, desc)
        
        if matches:
            total_percent = sum(int(m[0]) for m in matches)
            for percent_str, prey_name in matches:
                proportion = int(percent_str) / total_percent if total_percent > 0 else 0
                prey_items.append((prey_name, proportion))
        else:
            # 无明确比例，查找食物关键词
            if "捕食" in desc or "以" in desc and "为食" in desc:
                # 提取"捕食XX"或"以XX为食"的内容
                food_pattern = r'(?:捕食|以)([^，。,\s]{1,8})(?:为食|和|、)'
                food_matches = re.findall(food_pattern, desc)
                if food_matches:
                    # 平均分配比例
                    proportion = 1.0 / len(food_matches)
                    prey_items = [(food, proportion) for food in food_matches]
        
        return {"prey_items": prey_items}
    
    def _find_prey_trophic(self, prey_desc: str, all_species: Sequence[Species]) -> float:
        """根据猎物描述查找对应物种的营养级
        
        Args:
            prey_desc: 猎物描述（如"微藻"、"小鱼"等）
            all_species: 所有物种列表
            
        Returns:
            猎物的估计营养级
        """
        prey_desc_lower = prey_desc.lower()
        
        # 尝试匹配物种描述中的关键词
        for species in all_species:
            if species.trophic_level and species.trophic_level > 0:
                # 检查物种名称或描述是否包含猎物关键词
                if (prey_desc in species.common_name or 
                    prey_desc in species.description or
                    any(kw in species.description.lower() for kw in prey_desc_lower.split())):
                    return species.trophic_level
        
        # 未找到匹配物种，基于关键词估算
        if any(kw in prey_desc_lower for kw in ["藻", "草", "植物", "叶"]):
            return 1.0  # 植物性食物
        elif any(kw in prey_desc_lower for kw in ["浮游", "微生物", "细菌"]):
            return 1.5  # 微生物
        elif any(kw in prey_desc_lower for kw in ["虫", "小型", "幼体"]):
            return 2.0  # 小型草食动物
        elif any(kw in prey_desc_lower for kw in ["鱼", "虾", "贝"]):
            return 2.5  # 水生动物
        elif any(kw in prey_desc_lower for kw in ["鸟", "兽", "大型"]):
            return 3.0  # 中型动物
        else:
            return 2.0  # 默认为初级消费者
    
    def _estimate_from_keywords(self, desc: str) -> float:
        """基于关键词估算营养级（回退方法）"""
        # 顶级捕食者（5.0+）
        if any(kw in desc for kw in ["顶级", "apex", "霸主", "食物链顶端"]):
            return 5.0
        
        # 大型捕食者（4.0-4.9）
        if any(kw in desc for kw in ["大型捕食", "猛禽", "猛兽", "掠食者"]):
            return 4.5
        
        # 中层捕食者（3.0-3.9）
        if any(kw in desc for kw in ["捕食", "肉食", "carnivore", "猎食"]):
            return 3.5
        
        # 杂食（2.5-3.0）
        if any(kw in desc for kw in ["杂食", "omnivore"]):
            return 2.7
        
        # 草食/滤食（2.0-2.9）
        if any(kw in desc for kw in ["草食", "herbivore", "滤食", "植食"]):
            return 2.0
        
        # 默认为生产者
        return 1.0
    
    def get_trophic_category(self, trophic_level: float) -> str:
        """获取营养级分类名称"""
        if trophic_level < 2.0:
            return "生产者/分解者"
        elif trophic_level < 3.0:
            return "主要草食"
        elif trophic_level < 4.0:
            return "中层捕食者"
        elif trophic_level < 5.0:
            return "高层捕食者"
        else:
            return "顶级掠食者"
    
    def get_attribute_limits(self, trophic_level: float) -> dict:
        """根据营养级获取属性上限
        
        Returns:
            {"base": 基础上限, "specialized": 特化上限, "total": 总和上限}
        """
        if trophic_level < 2.0:
            # 生产者/分解者
            return {"base": 5, "specialized": 8, "total": 30}
        elif trophic_level < 3.0:
            # 主要草食
            return {"base": 7, "specialized": 10, "total": 50}
        elif trophic_level < 4.0:
            # 中层捕食者
            return {"base": 9, "specialized": 12, "total": 80}
        elif trophic_level < 5.0:
            # 高层捕食者
            return {"base": 12, "specialized": 14, "total": 105}
        else:
            # 顶级掠食者
            return {"base": 14, "specialized": 15, "total": 135}
    
    def calculate_population_capacity_factor(self, trophic_level: float) -> float:
        """计算营养级对承载力的影响因子
        
        高营养级物种需要更多资源，承载力更低
        
        Returns:
            承载力因子（0.1-1.0）
        """
        if trophic_level < 2.0:
            return 1.0  # 生产者：最高承载力
        elif trophic_level < 3.0:
            return 0.6  # 草食：60%
        elif trophic_level < 4.0:
            return 0.3  # 中层捕食：30%
        elif trophic_level < 5.0:
            return 0.15  # 高层捕食：15%
        else:
            return 0.05  # 顶级掠食：5%（种群极小）
    
    def calculate_metabolic_rate_factor(self, trophic_level: float) -> float:
        """计算营养级对基础代谢的影响因子 (Legacy)"""
        return 1.0 + (trophic_level - 1.0) * 0.375

    def estimate_kleiber_metabolic_rate(self, body_weight_g: float, trophic_level: float) -> float:
        """基于克莱伯定律(Kleiber's Law)估算单位体重的代谢率

        SMR (Specific Metabolic Rate) ∝ Mass^(-0.25)
        同时受营养级影响（捕食者通常更活跃）

        Args:
            body_weight_g: 体重(g)
            trophic_level: 营养级

        Returns:
            代谢率因子 (0.1-10.0)
        """
        # 1. 基础SMR计算 (Mass^-0.25)
        # 归一化基准：假设1kg(1000g)生物的SMR因子为1.0
        # 1g -> 1000^0.25 ≈ 5.6
        # 1000kg -> (10^6)^-0.25 ≈ 0.17
        if body_weight_g <= 0:
            body_weight_g = 1.0
            
        mass_factor = (body_weight_g / 1000.0) ** -0.25
        
        # 2. 营养级修正 (活跃度)
        # T1(植物)代谢极低, T5(猎豹)代谢高
        if trophic_level < 2.0:
            activity_factor = 0.5  # 植物/分解者
        else:
            # 动物随营养级线性增加
            activity_factor = 1.0 + (trophic_level - 2.0) * 0.3
            
        # 3. 综合计算
        metabolic_rate = mass_factor * activity_factor
        
        # 4. 钳制到合理游戏数值范围 (0.1 - 15.0)
        return max(0.1, min(15.0, metabolic_rate))


