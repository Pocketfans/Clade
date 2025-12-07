"""Embedding 服务 - 支持大规模向量存储与检索

【重大升级】v2.0 - 支持成千上万物种
1. 集成 Faiss 向量数据库，支持高效相似度搜索
2. 批量操作接口，减少 API 调用和 I/O 开销
3. 增量更新支持，避免每回合完全重建索引
4. 分层缓存：内存 -> 向量数据库 -> 磁盘文件

【性能指标】
- 10000 物种场景：搜索延迟 < 10ms
- 向量存储：约 2.5MB（64维）
- 批量 embedding：支持一次性处理 1000+ 文本

【使用方式】
```python
service = EmbeddingService(provider="local", dimension=64)

# 批量生成向量
vectors = service.embed(["text1", "text2", "text3"])

# 索引管理
service.index_species(species_list)
results = service.search_species("会飞的捕食者", top_k=10)

# 相似度矩阵
matrix = service.compute_similarity_matrix(["text1", "text2"])
```
"""
from __future__ import annotations

import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable, Any, Sequence, TYPE_CHECKING
import threading
import time

import httpx
import numpy as np

from ...core.config import get_settings
from .vector_store import VectorStore, MultiVectorStore, SearchResult

if TYPE_CHECKING:
    from ...models.species import Species

logger = logging.getLogger(__name__)

# 全局缓存目录
GLOBAL_CACHE_DIR = Path(get_settings().cache_dir) / "embeddings"
GLOBAL_CACHE_DIR.mkdir(parents=True, exist_ok=True)


class EmbeddingService:
    """Embedding 服务 - 大规模向量存储与检索
    
    【架构设计】
    1. 文本 -> 向量生成（API 或伪向量）
    2. 向量 -> 缓存存储（内存 + 磁盘）
    3. 向量 -> 索引管理（Faiss 向量数据库）
    4. 向量 -> 相似度搜索（批量高效）
    
    【索引类型】
    - species: 物种描述向量索引
    - events: 事件描述向量索引
    - concepts: 概念定义向量索引
    - pressures: 压力向量索引
    """

    def __init__(
        self,
        provider: str = "local",
        dimension: int = 64,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        enabled: bool = False,
        cache_dir: Path | None = None,
        timeout: int = 60,
        allow_fake_embeddings: bool = True,
        max_parallel_requests: int = 1,
        enable_concurrency: bool = False,
    ) -> None:
        self.provider = provider
        self.dimension = dimension
        self.api_base_url = base_url
        self.api_key = api_key
        self.model = model
        self.enabled = enabled
        self.timeout = timeout
        self.allow_fake_embeddings = allow_fake_embeddings
        self.enable_concurrency = enable_concurrency and max_parallel_requests > 1
        self.max_parallel_requests = max(1, max_parallel_requests)
        if not self.enable_concurrency:
            self.max_parallel_requests = 1
        
        # 缓存目录
        self._cache_dir = cache_dir or GLOBAL_CACHE_DIR
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        
        # 内存缓存：text_hash -> vector（加速重复查询）
        self._memory_cache: dict[str, list[float]] = {}
        self._memory_cache_max_size = 10000  # 限制内存缓存大小
        
        # 多索引向量存储
        self._vector_stores = MultiVectorStore(
            base_dir=self._cache_dir / "indexes",
            dimension=dimension
        )
        
        # 物种代码到描述的映射（用于增量更新检测）
        self._species_text_hashes: dict[str, str] = {}
        
        # 性能统计信息（增强版）
        self._stats = {
            "embed_calls": 0,
            "cache_hits": 0,
            "memory_cache_hits": 0,
            "disk_cache_hits": 0,
            "api_calls": 0,
            "fake_embeds": 0,
            "total_texts_processed": 0,
            "index_updates": 0,
            "species_indexed": 0,
            "events_indexed": 0,
        }
        self._stats_lock = threading.Lock()

    @property
    def model_identifier(self) -> str:
        """生成模型标识符，用于缓存隔离"""
        if self.enabled and self.model:
            return f"{self.provider}_{self.model}"
        return f"fake_{self.dimension}d"

    # ==================== 核心 Embedding 接口 ====================

    def embed(
        self, 
        texts: Iterable[str], 
        require_real: bool = False,
        batch_size: int = 20  # 默认批量大小减小到 20，提高稳定性
    ) -> list[list[float]]:
        """批量生成文本的向量表示
        
        Args:
            texts: 文本列表
            require_real: 是否要求使用真实 embedding（不允许使用假向量）
            batch_size: API 批量请求大小
        
        Returns:
            向量列表，保证所有向量维度一致
        """
        texts = list(texts)
        if not texts:
            return []
        
        self._stats["embed_calls"] += 1
        
        vectors: list[list[float]] = [None] * len(texts)
        uncached_indices: list[int] = []
        uncached_texts: list[str] = []
        target_dimension = None
        
        # 第一遍：检查缓存
        for idx, text in enumerate(texts):
            cache_key = self._make_cache_key(text)
            
            # 检查内存缓存
            if cache_key in self._memory_cache:
                cached = self._memory_cache[cache_key]
                if target_dimension is None:
                    target_dimension = len(cached)
                vectors[idx] = cached
                self._stats["cache_hits"] += 1
                self._stats["memory_cache_hits"] += 1
                continue
            
            # 检查磁盘缓存
            cached = self._load_from_disk_cache(cache_key)
            if cached is not None:
                if target_dimension is None:
                    target_dimension = len(cached)
                vectors[idx] = cached
                self._update_memory_cache(cache_key, cached)
                self._stats["cache_hits"] += 1
                self._stats["disk_cache_hits"] += 1
                continue
            
            # 需要生成
            uncached_indices.append(idx)
            uncached_texts.append(text)
        
        # 第二遍：批量生成未缓存的向量
        if uncached_texts:
            if target_dimension is None:
                target_dimension = self.dimension
            
            new_vectors = self._generate_vectors_batch(
                uncached_texts, 
                require_real=require_real,
                batch_size=batch_size
            )
            
            for i, (idx, text, vec) in enumerate(zip(uncached_indices, uncached_texts, new_vectors)):
                # 确保维度一致
                vec = self._adjust_dimension(vec, target_dimension)
                vectors[idx] = vec
                
                # 存入缓存
                cache_key = self._make_cache_key(text)
                self._store_in_disk_cache(cache_key, vec, text)
                self._update_memory_cache(cache_key, vec)
        
        return vectors

    def embed_single(self, text: str, require_real: bool = False) -> list[float]:
        """生成单个文本的向量（便捷方法）"""
        return self.embed([text], require_real=require_real)[0]

    def _generate_vectors_batch(
        self, 
        texts: list[str], 
        require_real: bool = False,
        batch_size: int = 100
    ) -> list[list[float]]:
        """批量生成向量（内部方法）"""
        if self.enabled and self.api_base_url and self.api_key and self.model:
            # 使用远程 API
            return self._remote_embed_batch(texts, require_real, batch_size)
        else:
            if require_real:
                raise RuntimeError(
                    "需要真实 embedding，但服务未配置。"
                    "请在设置中配置 Embedding Provider、Model、Base URL 和 API Key。"
                )
            # 使用伪向量
            with self._stats_lock:
                self._stats["fake_embeds"] += len(texts)
            return [self._fake_embed(text) for text in texts]

    def _remote_embed_batch(
        self, 
        texts: list[str], 
        require_real: bool = False,
        batch_size: int = 10  # 【优化】减小默认批量大小，提高稳定性
    ) -> list[list[float]]:
        """批量调用远程 Embedding API（支持并发分片）
        
        【优化策略】
        - 默认批量大小从 100 减小到 10，避免单次请求超时
        - 支持自适应批量：如果超时频繁，可进一步减小
        """
        # 【优化】根据文本总长度自适应调整批量大小
        total_chars = sum(len(t) for t in texts)
        avg_chars = total_chars / len(texts) if texts else 0
        
        # 如果平均文本较长，减小批量
        if avg_chars > 500:
            batch_size = min(batch_size, 5)
        elif avg_chars > 1000:
            batch_size = min(batch_size, 3)
        
        chunks: list[list[str]] = [
            texts[i:i + batch_size] for i in range(0, len(texts), batch_size)
        ]
        if not chunks:
            return []
        
        results: list[list[list[float]] | None] = [None] * len(chunks)
        
        def run_chunk(idx: int, chunk: list[str]) -> None:
            vectors = self._request_embedding_chunk(chunk, require_real)
            results[idx] = vectors
        
        max_workers = self.max_parallel_requests if self.enable_concurrency else 1
        if max_workers <= 1 or len(chunks) == 1:
            for idx, chunk in enumerate(chunks):
                run_chunk(idx, chunk)
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_map = {
                    executor.submit(self._request_embedding_chunk, chunk, require_real): idx
                    for idx, chunk in enumerate(chunks)
                }
                for future in as_completed(future_map):
                    idx = future_map[future]
                    results[idx] = future.result()
        
        all_vectors: list[list[float]] = []
        for chunk_vectors in results:
            if chunk_vectors is None:
                continue
            all_vectors.extend(chunk_vectors)
        return all_vectors

    def _request_embedding_chunk(
        self,
        batch_texts: list[str],
        require_real: bool,
        max_retries: int = 3,
    ) -> list[list[float]]:
        """向远程服务请求一个批次的向量
        
        【优化策略】
        - 文本长度限制：单个文本超过 2000 字符时截断
        - 批次大小自适应：超时后减小批次重试
        - 指数退避重试：每次重试间隔翻倍
        """
        url = f"{self.api_base_url.rstrip('/')}/embeddings"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        
        # 【优化】限制单个文本长度，避免上下文过长
        MAX_TEXT_LENGTH = 2000
        truncated_texts = []
        for text in batch_texts:
            if len(text) > MAX_TEXT_LENGTH:
                truncated_texts.append(text[:MAX_TEXT_LENGTH] + "...")
            else:
                truncated_texts.append(text)
        
        body = {"model": self.model, "input": truncated_texts}
        
        for attempt in range(max_retries):
            try:
                # 【优化】使用更细粒度的超时控制
                timeout_config = httpx.Timeout(
                    connect=10.0,  # 连接超时 10 秒
                    read=self.timeout,  # 读取超时使用配置值
                    write=30.0,  # 写入超时 30 秒
                    pool=10.0  # 连接池超时 10 秒
                )
                response = httpx.post(url, json=body, headers=headers, timeout=timeout_config)
                response.raise_for_status()
                data = response.json()
                
                embeddings = sorted(data["data"], key=lambda x: x["index"])
                batch_vectors = [e["embedding"] for e in embeddings]
                
                with self._stats_lock:
                    self._stats["api_calls"] += 1
                
                return batch_vectors
            except httpx.ReadTimeout as exc:
                # 【优化】读取超时时，记录更详细的信息
                logger.warning(
                    f"[Embedding] 读取超时 (批次大小: {len(batch_texts)}, "
                    f"总字符数: {sum(len(t) for t in truncated_texts)}, "
                    f"重试 {attempt+1}/{max_retries}): {exc}"
                )
                if attempt == max_retries - 1:
                    if require_real or not self.allow_fake_embeddings:
                        raise RuntimeError(f"Embedding API 读取超时 (重试耗尽): {exc}") from exc
                    
                    logger.warning(f"[Embedding] 超时后使用假向量")
                    vectors = [self._fake_embed(t) for t in batch_texts]
                    with self._stats_lock:
                        self._stats["fake_embeds"] += len(batch_texts)
                    return vectors
                
                # 指数退避
                time.sleep(2 ** attempt)
                
            except Exception as exc:
                if attempt == max_retries - 1:
                    if require_real or not self.allow_fake_embeddings:
                        raise RuntimeError(f"Embedding API 调用失败 (重试耗尽): {exc}") from exc
                    
                    logger.warning(f"[Embedding] API 调用失败，使用假向量: {exc}")
                    vectors = [self._fake_embed(t) for t in batch_texts]
                    with self._stats_lock:
                        self._stats["fake_embeds"] += len(batch_texts)
                    return vectors
                
                logger.warning(f"[Embedding] API 调用失败，正在重试 ({attempt+1}/{max_retries}): {exc}")
                time.sleep(2 ** attempt)  # 指数退避
        
        # 理论上不会到此
        return [self._fake_embed(t) for t in batch_texts]

    def _fake_embed(self, text: str) -> list[float]:
        """生成基于文本哈希的伪向量（确定性）"""
        rng = np.random.default_rng(int(hashlib.sha256(text.encode()).hexdigest(), 16) % (2**32))
        vector = rng.normal(size=self.dimension)
        normalized = vector / np.linalg.norm(vector)
        return normalized.tolist()

    def _adjust_dimension(self, vec: list[float], target_dim: int) -> list[float]:
        """调整向量维度"""
        if len(vec) > target_dim:
            return vec[:target_dim]
        elif len(vec) < target_dim:
            return vec + [0.0] * (target_dim - len(vec))
        return vec

    def _make_cache_key(self, text: str) -> str:
        """生成缓存 key（包含模型标识）"""
        content = f"{self.model_identifier}:{text}"
        return hashlib.sha256(content.encode()).hexdigest()

    # ==================== 内存缓存管理 ====================

    def _update_memory_cache(self, key: str, vector: list[float]) -> None:
        """更新内存缓存（带 LRU 淘汰）"""
        if len(self._memory_cache) >= self._memory_cache_max_size:
            # 简单淘汰：删除最早添加的 10%
            keys_to_remove = list(self._memory_cache.keys())[:self._memory_cache_max_size // 10]
            for k in keys_to_remove:
                del self._memory_cache[k]
        
        self._memory_cache[key] = vector

    # ==================== 磁盘缓存管理 ====================

    def _disk_cache_path(self, cache_key: str) -> Path:
        """获取磁盘缓存文件路径"""
        # 使用两级目录避免单目录文件过多
        subdir = cache_key[:2]
        return self._cache_dir / "vectors" / subdir / f"{cache_key}.json"

    def _load_from_disk_cache(self, cache_key: str) -> list[float] | None:
        """从磁盘缓存加载"""
        path = self._disk_cache_path(cache_key)
        if not path.exists():
            return None
        
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "vector" in data:
                return data["vector"]
        except Exception as e:
            logger.warning(f"[Embedding] 加载缓存失败 {cache_key}: {e}")
        
        return None

    def _store_in_disk_cache(self, cache_key: str, vector: list[float], text: str) -> None:
        """存储到磁盘缓存"""
        path = self._disk_cache_path(cache_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "vector": vector,
            "metadata": {
                "provider": self.provider,
                "model": self.model,
                "dimension": len(vector),
                "model_identifier": self.model_identifier,
                "text_preview": text[:100] if text else "",
            }
        }
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    # ==================== 向量索引管理 ====================

    def index_species(
        self, 
        species_list: Sequence['Species'],
        force_rebuild: bool = False
    ) -> int:
        """索引物种向量（支持增量更新）
        
        【扩展】同时索引植物和动物，植物使用专门的索引
        
        Args:
            species_list: 物种列表
            force_rebuild: 是否强制完全重建
            
        Returns:
            更新的物种数量
        """
        store = self._vector_stores.get_store("species")
        plant_store = self._vector_stores.get_store("plants")
        
        if force_rebuild:
            # 完全重建
            store.rebuild()
            plant_store.rebuild()
            self._species_text_hashes.clear()
        
        # 检测需要更新的物种
        texts_to_embed = []
        species_to_update = []
        plant_texts_to_embed = []
        plants_to_update = []
        
        for sp in species_list:
            search_text = self._build_species_search_text(sp)
            text_hash = hashlib.md5(search_text.encode()).hexdigest()
            
            # 检查是否需要更新
            old_hash = self._species_text_hashes.get(sp.lineage_code)
            if old_hash == text_hash and store.contains(sp.lineage_code):
                continue
            
            texts_to_embed.append(search_text)
            species_to_update.append(sp)
            self._species_text_hashes[sp.lineage_code] = text_hash
            
            # 【扩展】如果是植物，同时加入植物索引
            if sp.trophic_level < 2.0:
                plant_text = self._build_plant_search_text(sp)
                plant_texts_to_embed.append(plant_text)
                plants_to_update.append(sp)
        
        if not texts_to_embed:
            return 0
        
        # 批量生成向量
        vectors = self.embed(texts_to_embed)
        
        # 批量添加到索引
        ids = [sp.lineage_code for sp in species_to_update]
        metadata_list = [
            {
                "common_name": sp.common_name,
                "latin_name": sp.latin_name,
                "trophic_level": sp.trophic_level,
                "status": sp.status,
            }
            for sp in species_to_update
        ]
        
        store.add_batch(ids, vectors, metadata_list)
        
        # 【扩展】批量添加植物到植物索引
        if plant_texts_to_embed:
            plant_vectors = self.embed(plant_texts_to_embed)
            plant_ids = [sp.lineage_code for sp in plants_to_update]
            plant_metadata = [
                {
                    "common_name": sp.common_name,
                    "latin_name": sp.latin_name,
                    "trophic_level": sp.trophic_level,
                    "life_form_stage": getattr(sp, 'life_form_stage', 0),
                    "growth_form": getattr(sp, 'growth_form', 'aquatic'),
                    "status": sp.status,
                }
                for sp in plants_to_update
            ]
            plant_store.add_batch(plant_ids, plant_vectors, plant_metadata)
            logger.debug(f"[Embedding] 植物索引更新: {len(plant_ids)} 个")
        
        # 更新统计
        self._stats["index_updates"] += 1
        self._stats["species_indexed"] = store.size
        
        logger.info(f"[Embedding] 物种索引更新: {len(ids)} 个")
        return len(ids)
    
    def _build_plant_search_text(self, species: 'Species') -> str:
        """构建植物专用搜索文本
        
        Args:
            species: 物种对象
            
        Returns:
            植物搜索文本
        """
        parts = [
            species.common_name,
            species.latin_name,
            species.description,
        ]
        
        # 添加植物特有特征
        life_form = getattr(species, 'life_form_stage', 0)
        growth = getattr(species, 'growth_form', 'aquatic')
        
        stage_names = {
            0: "原核光合生物",
            1: "单细胞真核藻类",
            2: "群体藻类",
            3: "苔藓类植物",
            4: "蕨类植物",
            5: "裸子植物",
            6: "被子植物",
        }
        parts.append(f"生命形式: {stage_names.get(life_form, '未知')}")
        parts.append(f"生长形式: {growth}")
        
        # 添加植物特有特质
        traits = species.abstract_traits or {}
        for trait_name in ["光合效率", "根系发达度", "木质化程度", "种子化程度", "保水能力", "多细胞程度"]:
            value = traits.get(trait_name, 0)
            if value > 7:
                parts.append(f"高{trait_name}")
            elif value < 3 and trait_name not in ["木质化程度", "种子化程度", "根系发达度"]:
                parts.append(f"低{trait_name}")
        
        return " ".join(parts)
    
    def get_species_vectors(
        self, 
        lineage_codes: Sequence[str]
    ) -> tuple[np.ndarray, list[str]]:
        """批量获取物种向量（从已有索引中获取）
        
        优先从索引获取向量，避免重复embed调用。
        用于 NicheAnalyzer、GeneticDistanceCalculator 等需要批量向量的场景。
        
        Args:
            lineage_codes: 物种代码列表
            
        Returns:
            (向量矩阵, 有效的物种代码列表)
            
        Note:
            如果物种未在索引中，会返回空向量（不会自动embed）
        """
        store = self._vector_stores.get_store("species", create=False)
        
        vectors = []
        valid_codes = []
        
        for code in lineage_codes:
            vec = store.get(code) if store else None
            if vec is not None:
                vectors.append(vec)
                valid_codes.append(code)
        
        if not vectors:
            return np.array([]), []
        
        return np.array(vectors, dtype=np.float32), valid_codes
    
    def get_species_vector(self, lineage_code: str) -> np.ndarray | None:
        """获取单个物种的向量（从索引获取）"""
        store = self._vector_stores.get_store("species", create=False)
        if store is None:
            return None
        return store.get(lineage_code)

    def remove_species_from_index(self, lineage_codes: Sequence[str]) -> int:
        """从索引中移除物种（灭绝时调用）"""
        store = self._vector_stores.get_store("species", create=False)
        if store is None:
            return 0
        
        count = store.remove_batch(lineage_codes)
        for code in lineage_codes:
            self._species_text_hashes.pop(code, None)
        
        return count

    def search_species(
        self, 
        query: str, 
        top_k: int = 10,
        threshold: float = 0.3,
        exclude_codes: set[str] | None = None
    ) -> list[SearchResult]:
        """搜索相似物种
        
        Args:
            query: 查询文本
            top_k: 返回数量
            threshold: 最低相似度阈值
            exclude_codes: 排除的物种代码
            
        Returns:
            搜索结果列表
        """
        store = self._vector_stores.get_store("species", create=False)
        if store is None or store.size == 0:
            return []
        
        query_vec = self.embed_single(query)
        return store.search(query_vec, top_k, threshold, exclude_codes)

    def get_species_similarity(self, code_a: str, code_b: str) -> float:
        """计算两个物种的相似度"""
        store = self._vector_stores.get_store("species", create=False)
        if store is None:
            return 0.0
        
        vec_a = store.get(code_a)
        vec_b = store.get(code_b)
        
        if vec_a is None or vec_b is None:
            return 0.0
        
        # 计算余弦相似度
        vec_a = vec_a / (np.linalg.norm(vec_a) + 1e-8)
        vec_b = vec_b / (np.linalg.norm(vec_b) + 1e-8)
        return float(np.dot(vec_a, vec_b))

    @staticmethod
    def build_species_text(
        species: 'Species', 
        include_traits: bool = True,
        include_names: bool = True
    ) -> str:
        """统一的物种描述文本构建方法
        
        所有需要为物种生成embedding的地方都应该使用这个方法，
        以确保向量的一致性。
        
        Args:
            species: 物种对象
            include_traits: 是否包含抽象特征（高/低特征标记）
            include_names: 是否包含物种名称（common_name, latin_name）
            
        Returns:
            构建的描述文本
        """
        parts = []
        
        if include_names:
            parts.extend([species.common_name, species.latin_name])
        
        parts.append(species.description)
        
        # 添加特征信息
        if include_traits:
            traits = []
            for trait, value in species.abstract_traits.items():
                if value > 7:
                    traits.append(f"高{trait}")
                elif value < 3:
                    traits.append(f"低{trait}")
            if traits:
                parts.append(f"特征: {', '.join(traits)}")
        
        return " ".join(parts)
    
    def _build_species_search_text(self, species: 'Species') -> str:
        """构建物种搜索文本（内部方法，调用统一的build_species_text）"""
        return self.build_species_text(species, include_traits=True, include_names=True)

    # ==================== 事件索引管理 ====================

    def index_event(
        self,
        event_id: int | str,
        title: str,
        description: str,
        metadata: dict | None = None
    ) -> None:
        """索引单个事件"""
        store = self._vector_stores.get_store("events")
        text = f"{title}. {description}"
        vector = self.embed_single(text)
        store.add(str(event_id), vector, metadata or {})

    def index_events_batch(
        self,
        events: list[dict]
    ) -> int:
        """批量索引事件
        
        Args:
            events: [{"id": ..., "title": ..., "description": ..., "metadata": ...}, ...]
        """
        if not events:
            return 0
        
        store = self._vector_stores.get_store("events")
        
        texts = [f"{e['title']}. {e['description']}" for e in events]
        vectors = self.embed(texts)
        
        ids = [str(e["id"]) for e in events]
        metadata_list = [e.get("metadata", {}) for e in events]
        
        count = store.add_batch(ids, vectors, metadata_list)
        
        # 更新统计
        self._stats["events_indexed"] = store.size
        
        return count

    def search_events(
        self, 
        query: str, 
        top_k: int = 10,
        threshold: float = 0.3
    ) -> list[SearchResult]:
        """搜索相似事件"""
        store = self._vector_stores.get_store("events", create=False)
        if store is None or store.size == 0:
            return []
        
        query_vec = self.embed_single(query)
        return store.search(query_vec, top_k, threshold)

    # ==================== 概念索引管理 ====================

    def index_concepts(self, concepts: dict[str, dict]) -> int:
        """索引概念定义
        
        Args:
            concepts: {"概念名": {"description": "...", "keywords": [...]}, ...}
        """
        if not concepts:
            return 0
        
        store = self._vector_stores.get_store("concepts")
        
        texts = []
        ids = []
        metadata_list = []
        
        for name, info in concepts.items():
            text = f"{name}. {info.get('description', '')}"
            texts.append(text)
            ids.append(name)
            metadata_list.append(info)
        
        vectors = self.embed(texts)
        return store.add_batch(ids, vectors, metadata_list)

    def search_concepts(
        self, 
        query: str, 
        top_k: int = 5,
        threshold: float = 0.3
    ) -> list[SearchResult]:
        """搜索相关概念"""
        store = self._vector_stores.get_store("concepts", create=False)
        if store is None or store.size == 0:
            return []
        
        query_vec = self.embed_single(query)
        return store.search(query_vec, top_k, threshold)

    # ==================== 相似度矩阵计算 ====================

    def compute_similarity_matrix(self, texts: list[str]) -> np.ndarray:
        """计算文本列表的相似度矩阵
        
        Args:
            texts: 文本列表
        
        Returns:
            N x N 相似度矩阵
        """
        if not texts:
            return np.array([])
        
        vectors = self.embed(texts)
        matrix = np.array(vectors)
        
        # 归一化
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        normalized = matrix / norms
        
        # 计算余弦相似度
        similarity = normalized @ normalized.T
        return np.clip(similarity, -1.0, 1.0)

    def compute_species_similarity_matrix(
        self, 
        lineage_codes: Sequence[str] | None = None
    ) -> tuple[np.ndarray, list[str]]:
        """计算物种间的相似度矩阵
        
        Args:
            lineage_codes: 物种代码列表，None 表示所有已索引物种
            
        Returns:
            (相似度矩阵, 物种代码列表)
        """
        store = self._vector_stores.get_store("species", create=False)
        if store is None:
            return np.array([]), []
        
        return store.compute_similarity_matrix(lineage_codes)

    def compute_distance_matrix(self, texts: list[str]) -> np.ndarray:
        """计算文本列表的距离矩阵（1 - 相似度）"""
        similarity = self.compute_similarity_matrix(texts)
        return 1.0 - similarity

    # ==================== 压力向量管理 ====================

    def store_pressure_vector(
        self, 
        pressure_name: str, 
        source_desc: str, 
        target_desc: str
    ) -> np.ndarray:
        """计算并存储压力向量
        
        压力向量 = target_embedding - source_embedding
        
        Args:
            pressure_name: 压力名称
            source_desc: 源状态描述（低压力）
            target_desc: 目标状态描述（高压力）
            
        Returns:
            归一化的压力向量
        """
        store = self._vector_stores.get_store("pressures")
        
        source_vec = np.array(self.embed_single(source_desc))
        target_vec = np.array(self.embed_single(target_desc))
        
        pressure_vec = target_vec - source_vec
        norm = np.linalg.norm(pressure_vec)
        if norm > 0:
            pressure_vec = pressure_vec / norm
        
        store.add(pressure_name, pressure_vec.tolist(), {
            "source_desc": source_desc[:100],
            "target_desc": target_desc[:100],
        })
        
        return pressure_vec

    def get_pressure_vector(self, pressure_name: str) -> np.ndarray | None:
        """获取压力向量"""
        store = self._vector_stores.get_store("pressures", create=False)
        if store is None:
            return None
        return store.get(pressure_name)

    # ==================== 存档集成 ====================

    def export_for_save(self) -> dict[str, Any]:
        """导出数据用于存档"""
        # 保存向量存储
        self._vector_stores.save_all()
        
        return {
            "version": "2.0",
            "model_identifier": self.model_identifier,
            "provider": self.provider,
            "model": self.model,
            "dimension": self.dimension,
            "species_hashes": self._species_text_hashes,
            "stats": self._stats.copy(),
        }

    def import_from_save(self, data: dict[str, Any]) -> None:
        """从存档导入数据"""
        if not data:
            return
        
        # 恢复物种哈希（用于增量更新检测）
        self._species_text_hashes = data.get("species_hashes", {})
        
        # 向量存储会在 get_store 时自动从磁盘加载
        logger.info("[Embedding] 从存档恢复数据完成")
    
    def export_embeddings(self, descriptions: list[str]) -> dict[str, Any]:
        """导出 embedding 数据用于存档（供 SaveManager 调用）
        
        Args:
            descriptions: 物种描述列表
            
        Returns:
            包含 embedding 数据的字典
        """
        embeddings = {}
        
        for desc in descriptions:
            cache_key = self._make_cache_key(desc)
            
            # 优先从内存缓存获取
            if cache_key in self._memory_cache:
                embeddings[cache_key] = self._memory_cache[cache_key]
            else:
                # 尝试从磁盘缓存加载
                cached = self._load_from_disk_cache(cache_key)
                if cached:
                    embeddings[cache_key] = cached
        
        return {
            "version": "2.0",
            "model_identifier": self.model_identifier,
            "dimension": self.dimension,
            "embeddings": embeddings,
        }
    
    def import_embeddings(self, data: dict[str, Any], descriptions: list[str]) -> int:
        """从存档导入 embedding 数据（供 SaveManager 调用）
        
        Args:
            data: 导出的 embedding 数据
            descriptions: 对应的物种描述列表
            
        Returns:
            成功导入的 embedding 数量
        """
        if not data or "embeddings" not in data:
            return 0
        
        # 检查模型标识符是否匹配
        saved_identifier = data.get("model_identifier", "")
        if saved_identifier and saved_identifier != self.model_identifier:
            logger.warning(
                f"[Embedding] 模型标识符不匹配: 存档={saved_identifier}, 当前={self.model_identifier}"
            )
            # 仍然尝试导入，但可能不准确
        
        imported = 0
        saved_embeddings = data.get("embeddings", {})
        
        for desc in descriptions:
            cache_key = self._make_cache_key(desc)
            
            if cache_key in saved_embeddings:
                vector = saved_embeddings[cache_key]
                # 存入内存缓存
                self._update_memory_cache(cache_key, vector)
                imported += 1
        
        logger.info(f"[Embedding] 从存档导入 {imported} 个向量")
        return imported

    # ==================== 缓存管理 ====================

    def clear_memory_cache(self) -> int:
        """清除内存缓存"""
        count = len(self._memory_cache)
        self._memory_cache.clear()
        return count
    
    def clear_all_indexes(self) -> dict[str, int]:
        """清空所有向量索引（切换存档时调用）
        
        【重要】加载或创建新存档时必须调用此方法，
        否则向量索引会混入旧存档的数据。
        
        Returns:
            各索引清除前的大小 {"species": 100, "events": 50, ...}
        """
        stats = {}
        
        for name in ["species", "events", "concepts", "pressures"]:
            store = self._vector_stores.get_store(name, create=False)
            if store:
                stats[name] = store.size
                # 重建空索引
                store.rebuild()
        
        # 清空物种哈希（用于增量更新检测）
        self._species_text_hashes.clear()
        
        # 清空内存缓存
        self._memory_cache.clear()
        
        # 重置统计信息中的索引计数
        self._stats["species_indexed"] = 0
        self._stats["events_indexed"] = 0
        
        logger.info(f"[Embedding] 已清空所有向量索引: {stats}")
        return stats
    
    def switch_to_save_context(self, save_dir: Path | str | None) -> dict[str, Any]:
        """切换到存档专属的向量索引目录
        
        【重要】实现存档间的向量索引完全隔离。
        每个存档使用自己的 indexes 目录，避免不同存档数据混淆。
        
        Args:
            save_dir: 存档目录路径（如 data/saves/my_save/）
                     如果为 None，使用全局缓存目录
        
        Returns:
            切换信息 {"old_dir": ..., "new_dir": ..., "indexes_cleared": ...}
        """
        old_dir = self._cache_dir / "indexes"
        
        if save_dir is None:
            # 切回全局缓存目录
            new_cache_dir = GLOBAL_CACHE_DIR
        else:
            # 使用存档专属目录
            save_path = Path(save_dir)
            new_cache_dir = save_path / "vectors"
        
        new_cache_dir.mkdir(parents=True, exist_ok=True)
        new_index_dir = new_cache_dir / "indexes"
        
        # 清空当前索引（内存中的）
        cleared = self.clear_all_indexes()
        
        # 更新缓存目录（磁盘缓存保持全局共享，只有向量索引隔离）
        # 注意：这里只改变向量索引目录，embedding缓存仍然共享
        self._vector_stores = MultiVectorStore(
            base_dir=new_index_dir,
            dimension=self.dimension
        )
        
        result = {
            "old_index_dir": str(old_dir),
            "new_index_dir": str(new_index_dir),
            "indexes_cleared": cleared,
        }
        
        logger.info(f"[Embedding] 切换向量索引目录: {old_dir} -> {new_index_dir}")
        return result

    def rebuild_species_index(self, species_list: Sequence['Species']) -> int:
        """强制重建物种索引"""
        return self.index_species(species_list, force_rebuild=True)

    def optimize_indexes(self) -> dict[str, int]:
        """优化所有索引（清理已删除向量）"""
        results = {}
        for name in ["species", "events", "concepts", "pressures"]:
            store = self._vector_stores.get_store(name, create=False)
            if store and store.total_size > store.size:
                old_size = store.total_size
                store.rebuild()
                results[name] = old_size - store.size
        return results

    # ==================== 统计信息 ====================

    def get_cache_stats(self) -> dict[str, Any]:
        """获取缓存统计信息（增强版）"""
        # 统计磁盘缓存
        vectors_dir = self._cache_dir / "vectors"
        disk_files = 0
        disk_size = 0
        if vectors_dir.exists():
            for f in vectors_dir.rglob("*.json"):
                disk_files += 1
                disk_size += f.stat().st_size
        
        # 计算缓存命中率
        total_requests = (
            self._stats["cache_hits"] + 
            self._stats["api_calls"] + 
            self._stats["fake_embeds"]
        )
        cache_hit_rate = (
            self._stats["cache_hits"] / max(total_requests, 1)
        )
        
        return {
            "cache_dir": str(self._cache_dir),
            "memory_cache_count": len(self._memory_cache),
            "memory_cache_max": self._memory_cache_max_size,
            "disk_cache_files": disk_files,
            "disk_cache_size_mb": round(disk_size / 1024 / 1024, 2),
            "model_identifier": self.model_identifier,
            "cache_hit_rate": round(cache_hit_rate, 4),
            "stats": self._stats.copy(),
        }

    def get_index_stats(self) -> dict[str, Any]:
        """获取索引统计信息"""
        return self._vector_stores.get_stats()

    def get_full_stats(self) -> dict[str, Any]:
        """获取完整统计信息"""
        return {
            "cache": self.get_cache_stats(),
            "indexes": self.get_index_stats(),
        }
    
    def log_performance_summary(self) -> None:
        """输出性能统计摘要到日志"""
        stats = self.get_cache_stats()
        index_stats = self.get_index_stats()
        
        logger.info(
            f"[Embedding Stats] "
            f"缓存命中率: {stats['cache_hit_rate']:.1%}, "
            f"API调用: {self._stats['api_calls']}, "
            f"假向量: {self._stats['fake_embeds']}, "
            f"物种索引: {index_stats.get('species', {}).get('size', 0)}, "
            f"事件索引: {index_stats.get('events', {}).get('size', 0)}"
        )
