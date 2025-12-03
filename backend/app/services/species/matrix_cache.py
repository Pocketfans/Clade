"""矩阵运算缓存服务 (Matrix Computation Cache)

缓存大型矩阵运算结果，减少重复计算。

核心功能：
1. Embedding 相似度矩阵缓存
2. Tile 重叠矩阵缓存
3. TTL 过期管理
4. 增量更新支持

设计原则：
- 回合内复用缓存，减少向量计算
- 物种增减时局部更新
- 内存占用可控
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from ...models.species import Species

logger = logging.getLogger(__name__)


@dataclass
class CachedMatrix:
    """缓存的矩阵数据"""
    matrix: np.ndarray
    species_codes: list[str]  # 行/列对应的物种代码
    code_to_idx: dict[str, int]  # 物种代码 → 索引映射
    timestamp: float
    turn_index: int
    
    @property
    def size(self) -> int:
        """矩阵大小"""
        return len(self.species_codes)
    
    @property
    def memory_bytes(self) -> int:
        """估算内存占用（字节）"""
        return self.matrix.nbytes


@dataclass
class TileOverlapCache:
    """地块重叠缓存"""
    # species_code → set(tile_ids) 映射
    species_tiles: dict[str, set[int]]
    # tile_id → set(species_codes) 映射
    tile_species: dict[int, set[str]]
    # 重叠矩阵（可选，大型生态系统可能不缓存）
    overlap_matrix: np.ndarray | None
    species_codes: list[str]
    code_to_idx: dict[str, int]
    timestamp: float
    turn_index: int


class MatrixCacheService:
    """矩阵运算缓存服务
    
    提供 embedding 相似度和 tile 重叠计算的缓存。
    """
    
    # 默认 TTL（秒）
    DEFAULT_TTL = 600  # 10分钟
    
    # 最大缓存矩阵大小（物种数）
    MAX_MATRIX_SIZE = 500
    
    def __init__(self, ttl_seconds: float = DEFAULT_TTL):
        self._ttl = ttl_seconds
        self._logger = logging.getLogger(__name__)
        
        # Embedding 相似度缓存
        self._embedding_cache: CachedMatrix | None = None
        
        # Tile 重叠缓存
        self._tile_overlap_cache: TileOverlapCache | None = None
        
        # 统计
        self._cache_hits = 0
        self._cache_misses = 0
    
    @property
    def stats(self) -> dict:
        """获取缓存统计"""
        total = self._cache_hits + self._cache_misses
        hit_rate = self._cache_hits / total if total > 0 else 0
        
        embedding_info = None
        if self._embedding_cache:
            embedding_info = {
                "size": self._embedding_cache.size,
                "memory_mb": round(self._embedding_cache.memory_bytes / 1024 / 1024, 2),
                "age_seconds": round(time.time() - self._embedding_cache.timestamp, 1),
            }
        
        tile_info = None
        if self._tile_overlap_cache:
            tile_info = {
                "species_count": len(self._tile_overlap_cache.species_codes),
                "tile_count": len(self._tile_overlap_cache.tile_species),
                "age_seconds": round(time.time() - self._tile_overlap_cache.timestamp, 1),
            }
        
        return {
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_rate": round(hit_rate, 3),
            "embedding_cache": embedding_info,
            "tile_overlap_cache": tile_info,
        }
    
    def invalidate_all(self):
        """清除所有缓存"""
        self._embedding_cache = None
        self._tile_overlap_cache = None
        self._logger.debug("[矩阵缓存] 所有缓存已清除")
    
    # ========== Embedding 相似度缓存 ==========
    
    def get_embedding_similarity(
        self,
        species_a: str,
        species_b: str,
    ) -> float | None:
        """获取两个物种的 embedding 相似度（从缓存）
        
        Returns:
            相似度值，如果未缓存返回 None
        """
        if self._embedding_cache is None:
            self._cache_misses += 1
            return None
        
        if time.time() - self._embedding_cache.timestamp > self._ttl:
            self._cache_misses += 1
            return None
        
        idx_a = self._embedding_cache.code_to_idx.get(species_a)
        idx_b = self._embedding_cache.code_to_idx.get(species_b)
        
        if idx_a is None or idx_b is None:
            self._cache_misses += 1
            return None
        
        self._cache_hits += 1
        return float(self._embedding_cache.matrix[idx_a, idx_b])
    
    def get_embedding_similarity_row(
        self,
        species_code: str,
    ) -> tuple[np.ndarray, list[str]] | None:
        """获取物种与所有其他物种的相似度向量
        
        Returns:
            (相似度向量, 对应物种代码列表)，如果未缓存返回 None
        """
        if self._embedding_cache is None:
            return None
        
        if time.time() - self._embedding_cache.timestamp > self._ttl:
            return None
        
        idx = self._embedding_cache.code_to_idx.get(species_code)
        if idx is None:
            return None
        
        self._cache_hits += 1
        return (
            self._embedding_cache.matrix[idx, :].copy(),
            self._embedding_cache.species_codes.copy(),
        )
    
    def cache_embedding_matrix(
        self,
        matrix: np.ndarray,
        species_codes: list[str],
        turn_index: int,
    ):
        """缓存 embedding 相似度矩阵
        
        Args:
            matrix: N×N 相似度矩阵
            species_codes: 物种代码列表（长度 N）
            turn_index: 当前回合
        """
        if len(species_codes) > self.MAX_MATRIX_SIZE:
            self._logger.warning(
                f"[矩阵缓存] 物种数 {len(species_codes)} 超过限制 {self.MAX_MATRIX_SIZE}，"
                f"只缓存前 {self.MAX_MATRIX_SIZE} 个"
            )
            species_codes = species_codes[:self.MAX_MATRIX_SIZE]
            matrix = matrix[:self.MAX_MATRIX_SIZE, :self.MAX_MATRIX_SIZE]
        
        self._embedding_cache = CachedMatrix(
            matrix=matrix.astype(np.float32),  # 使用 float32 节省内存
            species_codes=species_codes,
            code_to_idx={code: i for i, code in enumerate(species_codes)},
            timestamp=time.time(),
            turn_index=turn_index,
        )
        
        self._logger.debug(
            f"[矩阵缓存] Embedding 矩阵已缓存: "
            f"{len(species_codes)}×{len(species_codes)}, "
            f"{self._embedding_cache.memory_bytes / 1024:.1f} KB"
        )
    
    # ========== Tile 重叠缓存 ==========
    
    def get_tile_overlap(
        self,
        species_a: str,
        species_b: str,
    ) -> float | None:
        """获取两个物种的地块重叠度（从缓存）
        
        Returns:
            重叠度 (0-1)，如果未缓存返回 None
        """
        if self._tile_overlap_cache is None:
            self._cache_misses += 1
            return None
        
        if time.time() - self._tile_overlap_cache.timestamp > self._ttl:
            self._cache_misses += 1
            return None
        
        tiles_a = self._tile_overlap_cache.species_tiles.get(species_a)
        tiles_b = self._tile_overlap_cache.species_tiles.get(species_b)
        
        if tiles_a is None or tiles_b is None:
            self._cache_misses += 1
            return None
        
        self._cache_hits += 1
        
        if not tiles_a and not tiles_b:
            return 0.0
        
        intersection = len(tiles_a & tiles_b)
        union = len(tiles_a | tiles_b)
        
        return intersection / union if union > 0 else 0.0
    
    def get_species_tiles(self, species_code: str) -> set[int] | None:
        """获取物种占据的地块集合"""
        if self._tile_overlap_cache is None:
            return None
        
        if time.time() - self._tile_overlap_cache.timestamp > self._ttl:
            return None
        
        return self._tile_overlap_cache.species_tiles.get(species_code)
    
    def get_tile_species(self, tile_id: int) -> set[str] | None:
        """获取地块上的物种集合"""
        if self._tile_overlap_cache is None:
            return None
        
        if time.time() - self._tile_overlap_cache.timestamp > self._ttl:
            return None
        
        return self._tile_overlap_cache.tile_species.get(tile_id)
    
    def get_tile_maps(self) -> tuple[dict[str, set[int]], dict[int, set[str]]] | None:
        """获取完整的地块映射（用于批量查询）
        
        Returns:
            (species_tiles, tile_species) 或 None
        """
        if self._tile_overlap_cache is None:
            return None
        
        if time.time() - self._tile_overlap_cache.timestamp > self._ttl:
            return None
        
        self._cache_hits += 1
        return (
            self._tile_overlap_cache.species_tiles,
            self._tile_overlap_cache.tile_species,
        )
    
    def cache_tile_overlap(
        self,
        species_list: list["Species"],
        turn_index: int,
        build_overlap_matrix: bool = False,
    ):
        """缓存地块重叠数据
        
        Args:
            species_list: 物种列表
            turn_index: 当前回合
            build_overlap_matrix: 是否构建完整的重叠矩阵（内存消耗大）
        """
        species_tiles: dict[str, set[int]] = {}
        tile_species: dict[int, set[str]] = {}
        species_codes = []
        
        for sp in species_list:
            if sp.status != "alive":
                continue
            
            tiles = set(sp.morphology_stats.get("tile_ids", []))
            code = sp.lineage_code
            
            species_tiles[code] = tiles
            species_codes.append(code)
            
            for tid in tiles:
                if tid not in tile_species:
                    tile_species[tid] = set()
                tile_species[tid].add(code)
        
        overlap_matrix = None
        if build_overlap_matrix and len(species_codes) <= self.MAX_MATRIX_SIZE:
            n = len(species_codes)
            overlap_matrix = np.zeros((n, n), dtype=np.float32)
            
            for i, code_i in enumerate(species_codes):
                tiles_i = species_tiles[code_i]
                for j, code_j in enumerate(species_codes):
                    if i == j:
                        overlap_matrix[i, j] = 1.0
                        continue
                    if j < i:
                        overlap_matrix[i, j] = overlap_matrix[j, i]
                        continue
                    
                    tiles_j = species_tiles[code_j]
                    if tiles_i and tiles_j:
                        intersection = len(tiles_i & tiles_j)
                        union = len(tiles_i | tiles_j)
                        overlap_matrix[i, j] = intersection / union if union > 0 else 0.0
        
        self._tile_overlap_cache = TileOverlapCache(
            species_tiles=species_tiles,
            tile_species=tile_species,
            overlap_matrix=overlap_matrix,
            species_codes=species_codes,
            code_to_idx={code: i for i, code in enumerate(species_codes)},
            timestamp=time.time(),
            turn_index=turn_index,
        )
        
        self._logger.debug(
            f"[矩阵缓存] Tile 重叠已缓存: "
            f"{len(species_codes)} 物种, {len(tile_species)} 地块"
        )
    
    def update_on_speciation(
        self,
        new_species: list["Species"],
    ):
        """分化后增量更新缓存"""
        if self._tile_overlap_cache is None:
            return
        
        for sp in new_species:
            code = sp.lineage_code
            tiles = set(sp.morphology_stats.get("tile_ids", []))
            
            self._tile_overlap_cache.species_tiles[code] = tiles
            self._tile_overlap_cache.species_codes.append(code)
            self._tile_overlap_cache.code_to_idx[code] = len(self._tile_overlap_cache.species_codes) - 1
            
            for tid in tiles:
                if tid not in self._tile_overlap_cache.tile_species:
                    self._tile_overlap_cache.tile_species[tid] = set()
                self._tile_overlap_cache.tile_species[tid].add(code)
        
        # 重叠矩阵需要重建（太复杂，直接失效）
        if self._tile_overlap_cache.overlap_matrix is not None:
            self._tile_overlap_cache.overlap_matrix = None
        
        self._logger.debug(f"[矩阵缓存] 增量更新: +{len(new_species)} 物种")
    
    def update_on_extinction(self, extinct_codes: list[str]):
        """灭绝后增量更新缓存"""
        if self._tile_overlap_cache is None:
            return
        
        for code in extinct_codes:
            tiles = self._tile_overlap_cache.species_tiles.pop(code, set())
            
            for tid in tiles:
                if tid in self._tile_overlap_cache.tile_species:
                    self._tile_overlap_cache.tile_species[tid].discard(code)
        
        # 重叠矩阵需要重建
        if self._tile_overlap_cache.overlap_matrix is not None:
            self._tile_overlap_cache.overlap_matrix = None
        
        self._logger.debug(f"[矩阵缓存] 移除 {len(extinct_codes)} 个灭绝物种")


# 全局单例
_matrix_cache_service: MatrixCacheService | None = None


def get_matrix_cache() -> MatrixCacheService:
    """获取矩阵缓存服务单例"""
    global _matrix_cache_service
    if _matrix_cache_service is None:
        _matrix_cache_service = MatrixCacheService()
    return _matrix_cache_service




