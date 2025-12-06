"""物种描述增强服务

为规则生成的物种（背景物种分化、杂交等）提供描述增强。

设计理念：
- 零成本：使用模板生成描述 + 向量遗传，完全移除 LLM 调用
- 批量处理：保持原有的队列和批处理接口兼容
- 异步执行：不阻塞主要推演流程

使用场景：
1. 背景物种规则分化后
2. 同步杂交物种创建后
3. 任何使用模板描述的物种
"""
from __future__ import annotations

import asyncio
import logging
import random
from typing import TYPE_CHECKING, Sequence

from ...models.species import Species

if TYPE_CHECKING:
    from ...ai.model_router import ModelRouter

logger = logging.getLogger(__name__)


class DescriptionEnhancerService:
    """物种描述增强服务 (规则版)
    
    不再调用 LLM，而是通过模板拼接和向量遗传算法为物种生成描述和 Embedding。
    这种方式成本为零，且能满足 Embedding 引擎的识别需求。
    
    使用方式：
    1. 在规则生成物种后，调用 queue_for_enhancement() 将物种加入队列
    2. 在回合结束前，调用 process_queue_async() 批量处理
    3. 或者使用 enhance_single_async() 立即处理单个物种
    """
    
    def __init__(self, router: 'ModelRouter' = None, batch_size: int = 10):
        # router 参数保留用于兼容性，但不再使用
        self.batch_size = batch_size
        self._pending_queue: list[dict] = []
        self._enhancement_count = 0
    
    def queue_for_enhancement(
        self,
        species: Species,
        parent: Species | None = None,
        speciation_type: str = "自然分化",
        is_hybrid: bool = False,
        parent2: Species | None = None,
        fertility: float = 1.0,
    ) -> None:
        """将物种加入增强队列
        
        Args:
            species: 需要增强描述的物种
            parent: 父系物种（分化时）
            speciation_type: 分化类型
            is_hybrid: 是否为杂交物种
            parent2: 第二亲本（杂交时）
            fertility: 杂交可育性
        """
        entry = {
            "species": species,
            "parent": parent,
            "speciation_type": speciation_type,
            "is_hybrid": is_hybrid,
            "parent2": parent2,
            "fertility": fertility,
        }
        self._pending_queue.append(entry)
        logger.debug(
            f"[描述增强] 加入队列: {species.common_name} "
            f"({'杂交' if is_hybrid else speciation_type}), 队列大小: {len(self._pending_queue)}"
        )
    
    def get_queue_size(self) -> int:
        """获取当前队列大小"""
        return len(self._pending_queue)
    
    def clear_queue(self) -> None:
        """清空队列"""
        self._pending_queue.clear()
    
    async def process_queue_async(
        self,
        max_items: int | None = None,
        timeout_per_item: float = 30.0,
    ) -> list[Species]:
        """批量处理队列中的物种
        
        Args:
            max_items: 最大处理数量（None 表示全部）
            timeout_per_item: 每个物种的超时时间（秒）
            
        Returns:
            成功增强的物种列表
        """
        if not self._pending_queue:
            return []
        
        # 取出要处理的条目
        items_to_process = self._pending_queue[:max_items] if max_items else self._pending_queue[:]
        self._pending_queue = self._pending_queue[len(items_to_process):]
        
        logger.info(f"[描述增强] 开始批量处理 {len(items_to_process)} 个物种 (规则模式)")
        
        enhanced_species = []
        tasks = []
        
        for entry in items_to_process:
            # 规则处理非常快，其实不需要 async，但为了保持接口一致，wrap 一下
            task = self._enhance_entry_async(entry, timeout_per_item)
            tasks.append(task)
        
        # 并发执行
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for entry, result in zip(items_to_process, results):
            if isinstance(result, Exception):
                logger.warning(
                    f"[描述增强] 失败: {entry['species'].common_name} - {result}"
                )
            elif result:
                enhanced_species.append(result)
                self._enhancement_count += 1
        
        logger.info(
            f"[描述增强] 批量处理完成: {len(enhanced_species)}/{len(items_to_process)} 成功"
        )
        return enhanced_species
    
    async def enhance_single_async(
        self,
        species: Species,
        parent: Species | None = None,
        speciation_type: str = "自然分化",
        is_hybrid: bool = False,
        parent2: Species | None = None,
        fertility: float = 1.0,
        timeout: float = 30.0,
    ) -> Species | None:
        """立即增强单个物种的描述"""
        entry = {
            "species": species,
            "parent": parent,
            "speciation_type": speciation_type,
            "is_hybrid": is_hybrid,
            "parent2": parent2,
            "fertility": fertility,
        }
        return await self._enhance_entry_async(entry, timeout)
    
    async def _enhance_entry_async(
        self,
        entry: dict,
        timeout: float,
    ) -> Species | None:
        """处理单个队列条目 (纯规则逻辑)"""
        species = entry["species"]
        
        try:
            # 方案1：模板生成描述
            description = self._generate_template_description(entry)
            old_desc = species.description
            species.description = description
            
            # 方案2：向量遗传
            self._apply_vector_inheritance(entry)
            
            vector_status = '成功' if species.ecological_vector else '跳过'
            logger.debug(
                f"[描述增强] {species.common_name} 生成完成: "
                f"描述={len(description)}字, 向量={vector_status}"
            )
            return species
                
        except Exception as e:
            logger.error(f"[描述增强] 异常: {species.common_name} - {e}")
            return None

    def _generate_template_description(self, entry: dict) -> str:
        """方案1：基于规则模板生成描述"""
        species = entry["species"]
        parent = entry["parent"]
        speciation_type = entry["speciation_type"]
        is_hybrid = entry["is_hybrid"]
        
        # 基础信息
        desc_parts = []
        
        # 1. 开头：定义
        habitat_map = {
            "marine": "海洋", "freshwater": "淡水", "terrestrial": "陆生",
            "amphibious": "两栖", "aerial": "飞行", "deep_sea": "深海", "coastal": "沿岸"
        }
        diet_map = {
            "herbivore": "植食性", "carnivore": "肉食性", "omnivore": "杂食性",
            "detritivore": "腐食性", "autotroph": "自养"
        }
        
        h_str = habitat_map.get(species.habitat_type, species.habitat_type)
        d_str = diet_map.get(species.diet_type, species.diet_type)
        
        desc_parts.append(f"{species.common_name}是一种生活在{h_str}环境中的{d_str}生物。")
        
        # 2. 演化/来源
        if is_hybrid:
            p1 = entry.get("parent")
            p2 = entry.get("parent2")
            p1_name = p1.common_name if p1 else "未知物种"
            p2_name = p2.common_name if p2 else "未知物种"
            desc_parts.append(f"作为{p1_name}与{p2_name}的杂交后代，它继承了双亲的特征。")
        elif parent:
            desc_parts.append(f"它由{parent.common_name}通过{speciation_type}分化而来。")
        
        # 3. 特质描述
        traits = species.abstract_traits or {}
        if traits:
            # 找显著特质
            high_traits = [k for k, v in traits.items() if v > 7.0]
            if high_traits:
                desc_parts.append(f"该物种具有显著的{'、'.join(high_traits[:3])}。")
        
        # 4. 结尾
        desc_parts.append("其生理结构已适应当前的生态位。")
        
        return "".join(desc_parts)

    def _apply_vector_inheritance(self, entry: dict) -> None:
        """方案2：向量遗传算法"""
        species = entry["species"]
        parent = entry["parent"]
        is_hybrid = entry["is_hybrid"]
        
        new_vector = None
        
        if is_hybrid:
            parent2 = entry.get("parent2")
            if parent and parent2 and parent.ecological_vector and parent2.ecological_vector:
                # 杂交：加权平均
                v1 = parent.ecological_vector
                v2 = parent2.ecological_vector
                if len(v1) == len(v2):
                    # 加上一点随机扰动体现变异
                    new_vector = [
                        (a + b) / 2.0 + random.gauss(0, 0.01) 
                        for a, b in zip(v1, v2)
                    ]
        elif parent and parent.ecological_vector:
            # 分化：父系向量 + 噪声
            noise_scale = 0.05
            new_vector = [
                v + random.gauss(0, noise_scale) 
                for v in parent.ecological_vector
            ]
            
        if new_vector:
            species.ecological_vector = new_vector
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            "total_enhanced": self._enhancement_count,
            "queue_size": len(self._pending_queue),
        }


def create_description_enhancer(router: 'ModelRouter') -> DescriptionEnhancerService:
    """创建描述增强服务实例"""
    # router 仅用于兼容接口，不再传递
    return DescriptionEnhancerService(router=None)





