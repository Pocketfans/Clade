"""
Intervention Service - 干预服务

处理对物种的外部干预操作。
"""

from __future__ import annotations

import logging
from typing import Any, Callable, List, TYPE_CHECKING

if TYPE_CHECKING:
    from ...repositories.species_repository import SpeciesRepository
    from ...models.species import Species

logger = logging.getLogger(__name__)


class InterventionService:
    """干预服务
    
    处理对物种的外部干预，如保护、引入等。
    """
    
    def __init__(
        self,
        species_repository: "SpeciesRepository",
        event_callback: Callable[[str, str, str], None] | None = None,
    ):
        self.species_repository = species_repository
        self.event_callback = event_callback
    
    def _emit_event(self, event_type: str, message: str, category: str = "干预"):
        """发送事件"""
        if self.event_callback:
            try:
                self.event_callback(event_type, message, category)
            except Exception:
                pass
    
    def update_intervention_status(
        self,
        species_list: List["Species"],
    ) -> None:
        """更新物种的干预状态
        
        检查并更新物种是否处于保护状态等。
        
        Args:
            species_list: 物种列表
        """
        for species in species_list:
            if species.status != "alive":
                continue
            
            # 检查是否处于保护状态
            protected = getattr(species, 'protected', False)
            if protected:
                # 保护状态的物种有额外的生存加成
                pass
            
            # 检查是否是引入物种
            introduced = getattr(species, 'introduced', False)
            if introduced:
                # 引入物种可能有适应期
                pass
    
    def apply_protection(
        self,
        species: "Species",
        duration: int = 10,
    ) -> None:
        """对物种应用保护状态
        
        Args:
            species: 要保护的物种
            duration: 保护持续回合数
        """
        species.protected = True
        species.protection_duration = duration
        self.species_repository.upsert(species)
        
        logger.info(f"[干预] 保护: {species.common_name} (持续 {duration} 回合)")
        self._emit_event("info", f"🛡️ 保护: {species.common_name}", "干预")
    
    def apply_introduction(
        self,
        species: "Species",
        target_tiles: List[int],
    ) -> None:
        """引入物种到新区域
        
        Args:
            species: 要引入的物种
            target_tiles: 目标地块 ID 列表
        """
        species.introduced = True
        self.species_repository.upsert(species)
        
        logger.info(f"[干预] 引入: {species.common_name} 到 {len(target_tiles)} 个地块")
        self._emit_event("info", f"🌍 引入: {species.common_name}", "干预")


