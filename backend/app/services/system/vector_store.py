"""向量存储服务 - 基于 Faiss 的高性能向量数据库

【设计目标】
支持成千上万物种的高效向量存储和检索：
1. 使用 Faiss 进行高效的相似度搜索（支持百万级向量）
2. 支持增量更新（添加/删除向量）
3. 持久化到磁盘，支持快速加载
4. 批量操作接口，减少 I/O 开销

【性能特点】
- 添加向量：O(1) 摊销
- 搜索 top-k：O(n) 暴力搜索 / O(log n) IVF 索引
- 内存占用：约 4 bytes * dimension * n_vectors
- 对于 10000 个 64 维向量约 2.5 MB

【使用方式】
```python
store = VectorStore(dimension=64, index_type="flat")
store.add("species_A1", vector_a1)
store.add_batch(["A2", "A3"], [vec_a2, vec_a3])
results = store.search(query_vec, top_k=10)
store.save("vectors.index")
```
"""
from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import numpy as np

logger = logging.getLogger(__name__)

# 尝试导入 faiss，如果失败则使用纯 numpy 后备实现
try:
    import faiss
    FAISS_AVAILABLE = True
    logger.info("[VectorStore] Faiss 已加载")
except ImportError:
    FAISS_AVAILABLE = False
    logger.warning("[VectorStore] Faiss 未安装，使用 NumPy 后备实现（性能较低）")


@dataclass
class SearchResult:
    """搜索结果"""
    id: str
    score: float  # 相似度分数 (0-1，越高越相似)
    metadata: dict = field(default_factory=dict)


class VectorStore:
    """高性能向量存储
    
    支持两种后端：
    1. Faiss（推荐）：高性能，支持大规模向量
    2. NumPy（后备）：当 Faiss 不可用时使用
    
    索引类型：
    - "flat": 暴力搜索，精确但慢（适合 <10000 向量）
    - "ivf": IVF 索引，近似但快（适合 >10000 向量）
    - "hnsw": HNSW 图索引，快速近似搜索（适合 >50000 向量）
    """
    
    def __init__(
        self,
        dimension: int = 64,
        index_type: str = "flat",
        metric: str = "cosine",
        nlist: int = 100,  # IVF 聚类数
        nprobe: int = 10,  # IVF 搜索时检查的聚类数
    ):
        """初始化向量存储
        
        Args:
            dimension: 向量维度
            index_type: 索引类型 ("flat", "ivf", "hnsw")
            metric: 距离度量 ("cosine", "l2", "ip")
            nlist: IVF 索引的聚类数（仅 ivf 类型）
            nprobe: IVF 搜索时探测的聚类数（仅 ivf 类型）
        """
        self.dimension = dimension
        self.index_type = index_type
        self.metric = metric
        self.nlist = nlist
        self.nprobe = nprobe
        
        # ID 映射：内部索引 <-> 外部 ID
        self._id_to_idx: dict[str, int] = {}
        self._idx_to_id: dict[int, str] = {}
        self._next_idx: int = 0
        
        # 元数据存储
        self._metadata: dict[str, dict] = {}
        
        # 删除标记（软删除，定期重建索引）
        self._deleted: set[int] = set()
        
        # 初始化索引
        self._index = None
        self._vectors: np.ndarray | None = None  # NumPy 后备存储
        self._is_trained = False
        
        self._init_index()
    
    def _init_index(self) -> None:
        """初始化 Faiss 索引"""
        if not FAISS_AVAILABLE:
            # NumPy 后备：使用简单的矩阵存储
            self._vectors = np.zeros((0, self.dimension), dtype=np.float32)
            return
        
        # 根据度量类型选择基础索引
        if self.metric == "cosine":
            # 余弦相似度 = 归一化后的内积
            base_index = faiss.IndexFlatIP(self.dimension)
        elif self.metric == "l2":
            base_index = faiss.IndexFlatL2(self.dimension)
        else:  # "ip" 内积
            base_index = faiss.IndexFlatIP(self.dimension)
        
        # 根据索引类型包装
        if self.index_type == "flat":
            self._index = base_index
            self._is_trained = True
        elif self.index_type == "ivf":
            # IVF 索引需要训练
            quantizer = base_index
            self._index = faiss.IndexIVFFlat(quantizer, self.dimension, self.nlist)
            self._index.nprobe = self.nprobe
            # 【重要】设置 DirectMap 以支持 reconstruct() 方法
            # 使用 Hashtable 类型，在添加向量时会自动维护映射
            self._index.set_direct_map_type(faiss.DirectMap.Hashtable)
        elif self.index_type == "hnsw":
            # HNSW 图索引
            self._index = faiss.IndexHNSWFlat(self.dimension, 32)  # M=32
            self._is_trained = True
        else:
            raise ValueError(f"不支持的索引类型: {self.index_type}")
    
    def _normalize(self, vectors: np.ndarray) -> np.ndarray:
        """归一化向量（用于余弦相似度）"""
        if self.metric != "cosine":
            return vectors
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return vectors / norms
    
    def add(
        self, 
        id: str, 
        vector: np.ndarray | list[float],
        metadata: dict | None = None,
        overwrite: bool = True
    ) -> bool:
        """添加单个向量
        
        Args:
            id: 向量的唯一标识符
            vector: 向量数据
            metadata: 可选的元数据
            overwrite: 如果 ID 已存在，是否覆盖
            
        Returns:
            是否成功添加
        """
        return self.add_batch([id], [vector], [metadata] if metadata else None, overwrite)
    
    def add_batch(
        self,
        ids: Sequence[str],
        vectors: Sequence[np.ndarray | list[float]],
        metadata_list: Sequence[dict] | None = None,
        overwrite: bool = True
    ) -> int:
        """批量添加向量
        
        Args:
            ids: ID 列表
            vectors: 向量列表
            metadata_list: 元数据列表（可选）
            overwrite: 如果 ID 已存在，是否覆盖
            
        Returns:
            成功添加的数量
        """
        if len(ids) != len(vectors):
            raise ValueError("IDs 和 vectors 长度必须一致")
        
        if len(ids) == 0:
            return 0
        
        # 转换为 numpy 数组
        vectors_array = np.array(vectors, dtype=np.float32)
        if vectors_array.ndim == 1:
            vectors_array = vectors_array.reshape(1, -1)
        
        # 检查维度
        if vectors_array.shape[1] != self.dimension:
            # 尝试调整维度
            if vectors_array.shape[1] > self.dimension:
                vectors_array = vectors_array[:, :self.dimension]
            else:
                padding = np.zeros((vectors_array.shape[0], self.dimension - vectors_array.shape[1]))
                vectors_array = np.hstack([vectors_array, padding])
        
        # 归一化
        vectors_array = self._normalize(vectors_array)
        
        # 处理已存在的 ID
        new_ids = []
        new_vectors = []
        new_metadata = []
        
        for i, id in enumerate(ids):
            if id in self._id_to_idx:
                if overwrite:
                    # 标记旧向量为删除
                    old_idx = self._id_to_idx[id]
                    self._deleted.add(old_idx)
                else:
                    continue
            
            new_ids.append(id)
            new_vectors.append(vectors_array[i])
            if metadata_list and i < len(metadata_list):
                new_metadata.append(metadata_list[i])
            else:
                new_metadata.append({})
        
        if not new_ids:
            return 0
        
        new_vectors_array = np.array(new_vectors, dtype=np.float32)
        
        # 添加到索引
        if FAISS_AVAILABLE:
            # 如果是 IVF 索引且未训练，需要先训练
            if self.index_type == "ivf" and not self._is_trained:
                if len(new_vectors_array) >= self.nlist:
                    self._index.train(new_vectors_array)
                    self._is_trained = True
                else:
                    # 向量不足以训练，暂存
                    if self._vectors is None:
                        self._vectors = new_vectors_array
                    else:
                        self._vectors = np.vstack([self._vectors, new_vectors_array])
                    # 更新映射
                    for j, id in enumerate(new_ids):
                        idx = self._next_idx
                        self._id_to_idx[id] = idx
                        self._idx_to_id[idx] = id
                        self._metadata[id] = new_metadata[j]
                        self._next_idx += 1
                    return len(new_ids)
            
            self._index.add(new_vectors_array)
        else:
            # NumPy 后备
            if self._vectors is None or len(self._vectors) == 0:
                self._vectors = new_vectors_array
            else:
                self._vectors = np.vstack([self._vectors, new_vectors_array])
        
        # 更新映射
        for j, id in enumerate(new_ids):
            idx = self._next_idx
            self._id_to_idx[id] = idx
            self._idx_to_id[idx] = id
            self._metadata[id] = new_metadata[j]
            self._next_idx += 1
        
        return len(new_ids)
    
    def remove(self, id: str) -> bool:
        """删除向量（软删除）
        
        Note: 实际删除在 rebuild() 时执行
        """
        if id not in self._id_to_idx:
            return False
        
        idx = self._id_to_idx[id]
        self._deleted.add(idx)
        return True
    
    def remove_batch(self, ids: Sequence[str]) -> int:
        """批量删除向量"""
        count = 0
        for id in ids:
            if self.remove(id):
                count += 1
        return count
    
    def get(self, id: str) -> np.ndarray | None:
        """获取向量"""
        if id not in self._id_to_idx:
            return None
        
        idx = self._id_to_idx[id]
        if idx in self._deleted:
            return None
        
        if FAISS_AVAILABLE and self._index is not None:
            try:
                # Faiss 重构向量
                return self._index.reconstruct(idx)
            except RuntimeError as e:
                # DirectMap 未初始化的情况
                if "direct map not initialized" in str(e):
                    logger.warning(f"[VectorStore] DirectMap 未初始化，尝试重建...")
                    try:
                        # 尝试重建 DirectMap
                        if hasattr(self._index, 'make_direct_map'):
                            self._index.make_direct_map()
                            return self._index.reconstruct(idx)
                    except Exception as rebuild_err:
                        logger.error(f"[VectorStore] DirectMap 重建失败: {rebuild_err}")
                
                # 如果有 NumPy 后备存储，使用它
                if self._vectors is not None and idx < len(self._vectors):
                    return self._vectors[idx].copy()
                
                logger.error(f"[VectorStore] 无法获取向量 {id}: {e}")
                return None
        elif self._vectors is not None:
            return self._vectors[idx].copy()
        
        return None
    
    def search(
        self,
        query: np.ndarray | list[float],
        top_k: int = 10,
        threshold: float = 0.0,
        exclude_ids: set[str] | None = None
    ) -> list[SearchResult]:
        """搜索最相似的向量
        
        Args:
            query: 查询向量
            top_k: 返回数量
            threshold: 最低相似度阈值
            exclude_ids: 排除的 ID 集合
            
        Returns:
            搜索结果列表，按相似度降序排列
        """
        if self.size == 0:
            return []
        
        # 准备查询向量
        query_array = np.array(query, dtype=np.float32).reshape(1, -1)
        if query_array.shape[1] != self.dimension:
            if query_array.shape[1] > self.dimension:
                query_array = query_array[:, :self.dimension]
            else:
                padding = np.zeros((1, self.dimension - query_array.shape[1]))
                query_array = np.hstack([query_array, padding])
        
        query_array = self._normalize(query_array)
        
        # 扩大搜索范围以处理删除和排除
        search_k = min(top_k * 3 + len(self._deleted) + (len(exclude_ids) if exclude_ids else 0), self.size)
        
        if FAISS_AVAILABLE and self._index is not None and self._index.ntotal > 0:
            distances, indices = self._index.search(query_array, search_k)
            distances = distances[0]
            indices = indices[0]
        elif self._vectors is not None and len(self._vectors) > 0:
            # NumPy 后备：暴力搜索
            similarities = self._vectors @ query_array.T
            similarities = similarities.flatten()
            indices = np.argsort(-similarities)[:search_k]
            distances = similarities[indices]
        else:
            return []
        
        # 过滤结果
        results = []
        for i, idx in enumerate(indices):
            if idx < 0 or idx >= self._next_idx:
                continue
            if idx in self._deleted:
                continue
            
            id = self._idx_to_id.get(int(idx))
            if id is None:
                continue
            if exclude_ids and id in exclude_ids:
                continue
            
            # 计算相似度分数
            if self.metric == "l2":
                # L2 距离转相似度
                score = 1.0 / (1.0 + float(distances[i]))
            else:
                # 内积/余弦已经是相似度
                score = float(distances[i])
            
            if score < threshold:
                continue
            
            results.append(SearchResult(
                id=id,
                score=score,
                metadata=self._metadata.get(id, {})
            ))
            
            if len(results) >= top_k:
                break
        
        return results
    
    def search_batch(
        self,
        queries: Sequence[np.ndarray | list[float]],
        top_k: int = 10,
        threshold: float = 0.0
    ) -> list[list[SearchResult]]:
        """批量搜索
        
        Args:
            queries: 查询向量列表
            top_k: 每个查询返回的数量
            threshold: 最低相似度阈值
            
        Returns:
            每个查询的搜索结果列表
        """
        return [self.search(q, top_k, threshold) for q in queries]
    
    def compute_similarity_matrix(self, ids: Sequence[str] | None = None) -> tuple[np.ndarray, list[str]]:
        """计算指定向量间的相似度矩阵
        
        Args:
            ids: 要计算的 ID 列表，None 表示所有
            
        Returns:
            (相似度矩阵, ID列表)
        """
        if ids is None:
            ids = [id for id in self._id_to_idx.keys() if self._id_to_idx[id] not in self._deleted]
        
        n = len(ids)
        if n == 0:
            return np.array([]), []
        
        # 收集向量
        vectors = []
        valid_ids = []
        for id in ids:
            vec = self.get(id)
            if vec is not None:
                vectors.append(vec)
                valid_ids.append(id)
        
        if not vectors:
            return np.array([]), []
        
        vectors_array = np.array(vectors, dtype=np.float32)
        vectors_array = self._normalize(vectors_array)
        
        # 计算相似度矩阵
        similarity = vectors_array @ vectors_array.T
        similarity = np.clip(similarity, -1.0, 1.0)
        
        return similarity, valid_ids
    
    @property
    def size(self) -> int:
        """有效向量数量（不含已删除）"""
        return len(self._id_to_idx) - len(self._deleted)
    
    @property
    def total_size(self) -> int:
        """总向量数量（含已删除）"""
        return len(self._id_to_idx)
    
    def contains(self, id: str) -> bool:
        """检查 ID 是否存在"""
        return id in self._id_to_idx and self._id_to_idx[id] not in self._deleted
    
    def list_ids(self) -> list[str]:
        """列出所有有效 ID"""
        return [id for id, idx in self._id_to_idx.items() if idx not in self._deleted]
    
    def rebuild(self) -> None:
        """重建索引（清理已删除向量，优化空间）
        
        当删除比例超过 30% 时建议调用
        """
        if len(self._deleted) == 0:
            return
        
        logger.info(f"[VectorStore] 开始重建索引，清理 {len(self._deleted)} 个已删除向量")
        
        # 收集有效向量
        valid_ids = []
        valid_vectors = []
        valid_metadata = []
        
        for id, idx in list(self._id_to_idx.items()):
            if idx in self._deleted:
                continue
            
            vec = self.get(id)
            if vec is not None:
                valid_ids.append(id)
                valid_vectors.append(vec)
                valid_metadata.append(self._metadata.get(id, {}))
        
        # 重置状态
        self._id_to_idx.clear()
        self._idx_to_id.clear()
        self._deleted.clear()
        self._next_idx = 0
        self._is_trained = False
        
        # 重新初始化索引
        self._init_index()
        
        # 重新添加向量
        if valid_ids:
            self.add_batch(valid_ids, valid_vectors, valid_metadata)
        
        logger.info(f"[VectorStore] 索引重建完成，当前 {self.size} 个向量")
    
    def save(self, path: str | Path) -> None:
        """保存到磁盘
        
        Args:
            path: 保存路径（不含扩展名）
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # 保存索引
        if FAISS_AVAILABLE and self._index is not None:
            faiss.write_index(self._index, str(path.with_suffix(".faiss")))
        
        # 保存元数据
        meta = {
            "dimension": self.dimension,
            "index_type": self.index_type,
            "metric": self.metric,
            "nlist": self.nlist,
            "nprobe": self.nprobe,
            "id_to_idx": self._id_to_idx,
            "idx_to_id": self._idx_to_id,
            "next_idx": self._next_idx,
            "metadata": self._metadata,
            "deleted": list(self._deleted),
            "is_trained": self._is_trained,
        }
        
        # 如果使用 NumPy 后备，也保存向量
        if not FAISS_AVAILABLE and self._vectors is not None:
            np.save(str(path.with_suffix(".npy")), self._vectors)
        
        with open(path.with_suffix(".meta"), "wb") as f:
            pickle.dump(meta, f)
        
        logger.info(f"[VectorStore] 已保存到 {path}，共 {self.size} 个向量")
    
    @classmethod
    def load(cls, path: str | Path) -> 'VectorStore':
        """从磁盘加载
        
        Args:
            path: 保存路径（不含扩展名）
            
        Returns:
            加载的 VectorStore 实例
        """
        path = Path(path)
        
        # 加载元数据
        with open(path.with_suffix(".meta"), "rb") as f:
            meta = pickle.load(f)
        
        # 创建实例
        store = cls(
            dimension=meta["dimension"],
            index_type=meta["index_type"],
            metric=meta["metric"],
            nlist=meta.get("nlist", 100),
            nprobe=meta.get("nprobe", 10),
        )
        
        # 恢复状态
        store._id_to_idx = meta["id_to_idx"]
        store._idx_to_id = {int(k): v for k, v in meta["idx_to_id"].items()}
        store._next_idx = meta["next_idx"]
        store._metadata = meta["metadata"]
        store._deleted = set(meta["deleted"])
        store._is_trained = meta.get("is_trained", True)
        
        # 加载索引
        faiss_path = path.with_suffix(".faiss")
        if FAISS_AVAILABLE and faiss_path.exists():
            store._index = faiss.read_index(str(faiss_path))
            
            # 【重要】对于 IVF 类型索引，确保 DirectMap 已初始化
            # 这样才能使用 reconstruct() 方法获取向量
            if store.index_type == "ivf" and hasattr(store._index, 'make_direct_map'):
                try:
                    # 检查 DirectMap 是否已初始化
                    # 如果没有，调用 make_direct_map() 重建
                    if store._index.direct_map.type == faiss.DirectMap.NoMap:
                        store._index.make_direct_map()
                        logger.info(f"[VectorStore] 已为 IVF 索引重建 DirectMap")
                except Exception as e:
                    logger.warning(f"[VectorStore] DirectMap 检查/重建失败: {e}")
        
        # 加载 NumPy 后备
        npy_path = path.with_suffix(".npy")
        if npy_path.exists():
            store._vectors = np.load(str(npy_path))
        
        logger.info(f"[VectorStore] 从 {path} 加载，共 {store.size} 个向量")
        return store
    
    def get_stats(self) -> dict[str, Any]:
        """获取统计信息"""
        memory_usage = 0
        if FAISS_AVAILABLE and self._index is not None:
            # 估算 Faiss 内存使用
            memory_usage = self._index.ntotal * self.dimension * 4  # float32
        elif self._vectors is not None:
            memory_usage = self._vectors.nbytes
        
        return {
            "size": self.size,
            "total_size": self.total_size,
            "deleted_count": len(self._deleted),
            "dimension": self.dimension,
            "index_type": self.index_type,
            "metric": self.metric,
            "is_trained": self._is_trained,
            "memory_bytes": memory_usage,
            "memory_mb": round(memory_usage / 1024 / 1024, 2),
            "backend": "faiss" if FAISS_AVAILABLE else "numpy",
        }


class MultiVectorStore:
    """多索引向量存储管理器
    
    管理多个独立的向量索引，用于不同用途：
    - species: 物种描述向量
    - events: 事件描述向量
    - pressures: 压力向量
    - concepts: 概念向量
    """
    
    def __init__(self, base_dir: Path, dimension: int = 64):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.dimension = dimension
        
        self._stores: dict[str, VectorStore] = {}
    
    def get_store(self, name: str, create: bool = True) -> VectorStore | None:
        """获取指定名称的向量存储"""
        if name not in self._stores:
            store_path = self.base_dir / name
            meta_path = store_path.with_suffix(".meta")
            
            if meta_path.exists():
                # 从磁盘加载
                self._stores[name] = VectorStore.load(store_path)
            elif create:
                # 创建新存储
                # 根据用途选择索引类型
                if name == "species":
                    # 物种可能很多，使用 IVF
                    index_type = "ivf" if FAISS_AVAILABLE else "flat"
                else:
                    index_type = "flat"
                
                self._stores[name] = VectorStore(
                    dimension=self.dimension,
                    index_type=index_type
                )
            else:
                return None
        
        return self._stores.get(name)
    
    def save_all(self) -> None:
        """保存所有存储"""
        for name, store in self._stores.items():
            store.save(self.base_dir / name)
    
    def get_stats(self) -> dict[str, dict]:
        """获取所有存储的统计"""
        return {name: store.get_stats() for name, store in self._stores.items()}

