"""营养级（Trophic Level）计算与管理服务。

标准5级食物链分类：
┌────────┬──────────────────────────────┬──────────────────────────────┐
│ 营养级 │ 典型生物                     │ 生态功能                     │
├────────┼──────────────────────────────┼──────────────────────────────┤
│ T1     │ 植物、藻类、自养微生物       │ 生产者（制造能量）           │
│ T2     │ 草食动物、浮游动物           │ 初级消费者（吃植物）         │
│ T3     │ 小型捕食者、杂食动物         │ 次级消费者（吃草食动物）     │
│ T4     │ 中大型捕食者                 │ 三级消费者（吃小捕食者）     │
│ T5+    │ 顶级捕食者                   │ 食物链顶端（终端消费者）     │
└────────┴──────────────────────────────┴──────────────────────────────┘

精细分类（支持小数，表示杂食/过渡）：
- 1.0: 纯生产者（光合/化能自养）
- 1.5: 兼性生产者、分解者、腐食者
- 2.0: 纯草食/滤食
- 2.5: 杂食（偏向植物）
- 3.0: 次级消费者（捕食草食动物）
- 3.5: 杂食（偏向肉食）
- 4.0: 三级消费者（捕食小型捕食者）
- 4.5: 高级捕食者
- 5.0+: 顶级掠食者

计算公式：T = 1 + Σ(prey_proportion × prey_T)

生态效率（能量传递）：
- T1 → T2: 约10-15%
- T2 → T3: 约10-15%
- T3 → T4: 约10-15%
- T4 → T5: 约10-15%
每上升一个营养级，生物量减少约90%
"""
from __future__ import annotations

import logging
from typing import Sequence
from ...models.species import Species

logger = logging.getLogger(__name__)


class TrophicLevelCalculator:
    """营养级计算器（回退方案）
    
    【重要】营养级的主要来源应该是：
    1. AI 生成时直接判定（推荐）
    2. 继承父代营养级
    
    本计算器只用于：
    - 初始物种没有设置营养级
    - 导入的物种缺少营养级
    - AI 生成失败时的应急回退
    
    关键词估算不够可靠，请尽量避免依赖它。
    """
    
    def calculate_trophic_level(self, species: Species, all_species: Sequence[Species]) -> float:
        """估算物种的营养级（回退方案）
        
        【注意】这是基于描述文本的启发式估算，不如 AI 判定准确。
        
        Args:
            species: 目标物种
            all_species: 所有物种列表（用于分析食性）
            
        Returns:
            营养级（1.0-6.0+）
        """
        # 如果物种已有有效的营养级，直接返回
        if species.trophic_level and species.trophic_level >= 1.0:
            return species.trophic_level
        
        desc = species.description.lower()
        
        # 1. 明确的生产者特征（营养级 1.0）
        if self._is_producer(desc):
            logger.info(f"[营养级回退] {species.common_name}: 检测到生产者特征 → T1.0")
            return 1.0
        
        # 2. 明确的分解者特征（营养级 1.5）
        if self._is_decomposer(desc):
            logger.info(f"[营养级回退] {species.common_name}: 检测到分解者特征 → T1.5")
            return 1.5
        
        # 3. 尝试从描述中解析食性
        diet_info = self._parse_diet(desc)
        
        if diet_info["prey_items"]:
            # 有明确的食物描述，计算营养级
            trophic = 1.0
            for prey_desc, proportion in diet_info["prey_items"]:
                prey_trophic = self._find_prey_trophic(prey_desc, all_species)
                trophic += proportion * prey_trophic
            
            result = round(trophic, 2)
            logger.info(f"[营养级回退] {species.common_name}: 基于食性计算 → T{result}")
            return result
        
        # 4. 最后的回退：关键词估算
        estimated = self._estimate_from_keywords(desc)
        logger.warning(
            f"[营养级回退] {species.common_name}: 无明确食性，关键词估算 → T{estimated} "
            f"(建议让AI在生成时明确指定)"
        )
        return estimated
    
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
        
        # 未找到匹配物种，基于关键词估算（按营养级从低到高）
        # T1: 生产者
        if any(kw in prey_desc_lower for kw in ["藻", "草", "植物", "叶", "浮游植物"]):
            return 1.0
        # T1.5: 分解者/微生物
        elif any(kw in prey_desc_lower for kw in ["细菌", "真菌", "碎屑", "有机物"]):
            return 1.5
        # T2: 初级消费者
        elif any(kw in prey_desc_lower for kw in ["浮游动物", "虫", "小型", "幼体", "草食"]):
            return 2.0
        # T2.5: 小型杂食/低级消费者
        elif any(kw in prey_desc_lower for kw in ["小鱼", "虾", "贝", "软体动物"]):
            return 2.5
        # T3: 次级消费者
        elif any(kw in prey_desc_lower for kw in ["鱼", "蛙", "蜥蜴", "小型捕食"]):
            return 3.0
        # T3.5: 中型捕食者
        elif any(kw in prey_desc_lower for kw in ["鸟", "蛇", "中型"]):
            return 3.5
        # T4: 三级消费者
        elif any(kw in prey_desc_lower for kw in ["大型", "兽", "哺乳", "肉食"]):
            return 4.0
        else:
            return 2.0  # 默认为初级消费者
    
    def _estimate_from_keywords(self, desc: str) -> float:
        """基于关键词估算营养级（最后的回退方案）
        
        【警告】这个方法不够可靠！
        - 关键词可能不在预设列表中
        - 描述可能模糊或不规范
        
        建议：让 AI 在生成物种时直接指定 trophic_level
        """
        # 只处理最明确、最可靠的关键词
        
        # T1: 明确的生产者
        if any(kw in desc for kw in ["光合作用", "自养", "化能合成", "固定二氧化碳"]):
            return 1.0
        
        # T5: 明确的顶级捕食者
        if any(kw in desc for kw in ["顶级捕食", "apex predator", "食物链顶端"]):
            return 5.0
        
        # T4: 明确的大型捕食者
        if any(kw in desc for kw in ["捕食其他捕食者", "捕食肉食动物"]):
            return 4.0
        
        # T3: 明确的次级消费者
        if any(kw in desc for kw in ["捕食草食", "食虫", "捕食浮游动物"]):
            return 3.0
        
        # T2: 明确的初级消费者
        if any(kw in desc for kw in ["草食", "滤食", "食藻", "以藻类为食", "以植物为食"]):
            return 2.0
        
        # 默认值：初级消费者 (T2.0)
        # 这是最保守的选择：
        # - 大多数早期生物都是初级消费者
        # - 比随意猜测更安全
        return 2.0
    
    def get_trophic_category(self, trophic_level: float) -> str:
        """获取营养级分类名称
        
        标准5级分类：
        - T1 (1.0-1.9): 生产者/分解者 - 能量制造
        - T2 (2.0-2.9): 初级消费者 - 吃植物
        - T3 (3.0-3.9): 次级消费者 - 吃草食动物
        - T4 (4.0-4.9): 三级消费者 - 吃小型捕食者
        - T5 (5.0+): 顶级捕食者 - 食物链终端
        """
        if trophic_level < 2.0:
            return "生产者/分解者"
        elif trophic_level < 3.0:
            return "初级消费者"
        elif trophic_level < 4.0:
            return "次级消费者"
        elif trophic_level < 5.0:
            return "三级消费者"
        else:
            return "顶级捕食者"
    
    def get_attribute_limits(self, trophic_level: float) -> dict:
        """根据营养级获取属性上限
        
        高营养级生物通常更复杂，允许更高的属性总和
        
        Returns:
            {"base": 基础上限, "specialized": 特化上限, "total": 总和上限}
        """
        if trophic_level < 2.0:
            # T1: 生产者/分解者 - 结构简单
            return {"base": 5, "specialized": 8, "total": 30}
        elif trophic_level < 3.0:
            # T2: 初级消费者 - 基本动物机能
            return {"base": 7, "specialized": 10, "total": 50}
        elif trophic_level < 4.0:
            # T3: 次级消费者 - 需要捕猎能力
            return {"base": 9, "specialized": 12, "total": 70}
        elif trophic_level < 5.0:
            # T4: 三级消费者 - 更高级的捕猎技能
            return {"base": 11, "specialized": 13, "total": 90}
        else:
            # T5: 顶级捕食者 - 食物链顶端，最复杂
            return {"base": 13, "specialized": 15, "total": 110}
    
    def calculate_population_capacity_factor(self, trophic_level: float) -> float:
        """计算营养级对承载力的影响因子
        
        生态金字塔原理：每上升一个营养级，可支撑的生物量减少约90%
        高营养级物种需要更多资源，承载力更低
        
        Returns:
            承载力因子（0.01-1.0）
        """
        if trophic_level < 2.0:
            return 1.0   # T1 生产者：最高承载力（100%）
        elif trophic_level < 3.0:
            return 0.15  # T2 初级消费者：约15%
        elif trophic_level < 4.0:
            return 0.02  # T3 次级消费者：约2%
        elif trophic_level < 5.0:
            return 0.003  # T4 三级消费者：约0.3%
        else:
            return 0.0005  # T5 顶级捕食者：约0.05%（种群极小）
    
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


