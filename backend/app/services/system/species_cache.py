"""物种缓存管理器 - 统一的物种数据缓存

【设计目标】
1. 单例模式，全局共享物种缓存
2. 避免各服务（Encyclopedia、EvolutionPredictor等）各自维护缓存
3. 支持批量更新和增量更新
4. 提供线程安全的访问

【使用方式】
```python
cache = SpeciesCacheManager.get_instance()
cache.update(species_list)
species = cache.get("A1")
```
"""
from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Sequence, Iterator

if TYPE_CHECKING:
    from ...models.species import Species

logger = logging.getLogger(__name__)


class SpeciesCacheManager:
    """统一的物种缓存管理器（单例）
    
    所有需要缓存物种数据的服务都应该使用这个管理器，
    而不是各自维护缓存，避免内存浪费和数据不一致。
    """
    
    _instance: 'SpeciesCacheManager | None' = None
    _lock = threading.Lock()
    
    def __new__(cls) -> 'SpeciesCacheManager':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self) -> None:
        if self._initialized:
            return
        
        self._cache: dict[str, 'Species'] = {}
        self._id_to_code: dict[int, str] = {}  # species.id -> lineage_code 映射
        self._last_update_turn: int = -1
        self._update_count: int = 0
        self._initialized = True
        
        logger.info("[SpeciesCache] 初始化完成")
    
    @classmethod
    def get_instance(cls) -> 'SpeciesCacheManager':
        """获取单例实例"""
        return cls()
    
    def update(self, species_list: Sequence['Species'], turn_index: int = -1) -> int:
        """更新物种缓存
        
        Args:
            species_list: 物种列表
            turn_index: 当前回合数（用于检测是否需要更新）
            
        Returns:
            更新的物种数量
        """
        updated = 0
        
        for sp in species_list:
            code = sp.lineage_code
            
            # 检查是否需要更新（新物种或状态变化）
            existing = self._cache.get(code)
            if existing is None or existing.status != sp.status:
                updated += 1
            
            self._cache[code] = sp
            
            # 维护 id -> code 映射
            if sp.id:
                self._id_to_code[sp.id] = code
        
        self._last_update_turn = turn_index
        self._update_count += 1
        
        if updated > 0:
            logger.debug(f"[SpeciesCache] 更新 {updated} 个物种，总计 {len(self._cache)} 个")
        
        return updated
    
    def get(self, lineage_code: str) -> 'Species | None':
        """根据谱系代码获取物种"""
        return self._cache.get(lineage_code)
    
    def get_by_id(self, species_id: int) -> 'Species | None':
        """根据物种ID获取物种"""
        code = self._id_to_code.get(species_id)
        if code:
            return self._cache.get(code)
        return None
    
    def get_many(self, codes: Sequence[str]) -> list['Species']:
        """批量获取物种"""
        result = []
        for code in codes:
            sp = self._cache.get(code)
            if sp:
                result.append(sp)
        return result
    
    def get_all(self) -> list['Species']:
        """获取所有缓存的物种"""
        return list(self._cache.values())
    
    def get_alive(self) -> list['Species']:
        """获取所有存活的物种"""
        return [sp for sp in self._cache.values() if sp.status == "alive"]
    
    def contains(self, lineage_code: str) -> bool:
        """检查物种是否在缓存中"""
        return lineage_code in self._cache
    
    def remove(self, lineage_code: str) -> bool:
        """从缓存中移除物种"""
        if lineage_code in self._cache:
            sp = self._cache.pop(lineage_code)
            if sp.id and sp.id in self._id_to_code:
                del self._id_to_code[sp.id]
            return True
        return False
    
    def clear(self) -> None:
        """清空缓存"""
        self._cache.clear()
        self._id_to_code.clear()
        self._last_update_turn = -1
        logger.info("[SpeciesCache] 缓存已清空")
    
    def __len__(self) -> int:
        return len(self._cache)
    
    def __iter__(self) -> Iterator['Species']:
        return iter(self._cache.values())
    
    def __contains__(self, lineage_code: str) -> bool:
        return lineage_code in self._cache
    
    @property
    def size(self) -> int:
        """缓存大小"""
        return len(self._cache)
    
    @property
    def last_update_turn(self) -> int:
        """最后更新的回合数"""
        return self._last_update_turn
    
    def get_stats(self) -> dict:
        """获取缓存统计信息"""
        alive_count = sum(1 for sp in self._cache.values() if sp.status == "alive")
        extinct_count = len(self._cache) - alive_count
        
        return {
            "total_cached": len(self._cache),
            "alive_count": alive_count,
            "extinct_count": extinct_count,
            "last_update_turn": self._last_update_turn,
            "update_count": self._update_count,
        }


# 便捷访问函数
def get_species_cache() -> SpeciesCacheManager:
    """获取物种缓存管理器实例"""
    return SpeciesCacheManager.get_instance()

