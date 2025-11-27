from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Iterable, Any
from dataclasses import dataclass, field

import numpy as np

from ...core.config import get_settings

# 全局缓存目录
GLOBAL_CACHE_DIR = Path(get_settings().cache_dir) / "embeddings"
GLOBAL_CACHE_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class EmbeddingMetadata:
    """Embedding 元数据，用于存档"""
    provider: str
    model: str | None
    dimension: int
    text_hash: str
    text_preview: str  # 文本前50字符，用于调试


class EmbeddingService:
    """Embedding 服务 - 支持缓存、模型隔离和存档集成
    
    【重要改进】
    1. 缓存 key 包含模型信息，避免不同模型的向量混淆
    2. 支持按存档隔离的缓存目录
    3. 支持批量导出/导入 embedding 数据到存档
    4. 维护 embedding 索引，支持快速检索
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
    ) -> None:
        self.provider = provider
        self.dimension = dimension
        self.api_base_url = base_url
        self.api_key = api_key
        self.model = model
        self.enabled = enabled
        
        # 缓存目录：可指定存档专用目录，否则使用全局缓存
        self._cache_dir = cache_dir or GLOBAL_CACHE_DIR
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        
        # 内存缓存：text_hash -> vector（加速重复查询）
        self._memory_cache: dict[str, list[float]] = {}
        
        # Embedding 索引：用于快速相似度搜索
        self._index: dict[str, list[float]] = {}
        self._index_texts: dict[str, str] = {}  # hash -> original text

    @property
    def model_identifier(self) -> str:
        """生成模型标识符，用于缓存隔离"""
        if self.enabled and self.model:
            return f"{self.provider}_{self.model}"
        return f"fake_{self.dimension}d"

    def embed(self, texts: Iterable[str], require_real: bool = False) -> list[list[float]]:
        """
        生成文本的向量表示
        
        Args:
            texts: 文本列表
            require_real: 是否要求使用真实embedding（不允许使用假向量）
        
        Returns:
            向量列表，保证所有向量维度一致
        """
        vectors: list[list[float]] = []
        target_dimension = None
        
        for idx, text in enumerate(texts):
            try:
                # 生成包含模型信息的缓存 key
                cache_key = self._make_cache_key(text)
                
                # 1. 先检查内存缓存
                if cache_key in self._memory_cache:
                    cached = self._memory_cache[cache_key]
                    if target_dimension is None:
                        target_dimension = len(cached)
                    elif len(cached) != target_dimension:
                        cached = None
                    if cached is not None:
                        vectors.append(cached)
                        continue
                
                # 2. 检查磁盘缓存
                cached = self._load_from_cache(cache_key)
                if cached is not None:
                    if target_dimension is None:
                        target_dimension = len(cached)
                    elif len(cached) != target_dimension:
                        print(f"[Embedding] 缓存向量维度不一致：期望{target_dimension}，得到{len(cached)}，重新生成")
                        cached = None
                
                if cached is not None:
                    self._memory_cache[cache_key] = cached
                    vectors.append(cached)
                    continue
                
                # 3. 生成新向量
                if self.enabled and self.api_base_url and self.api_key and self.model:
                    vec = self._remote_embed(text, require_real=require_real)
                else:
                    if require_real:
                        raise RuntimeError(
                            "生态位对比需要 embedding 向量，但 embedding 服务未配置。"
                            "请在设置中配置 Embedding Provider、Model、Base URL 和 API Key。"
                        )
                    vec = self._fake_embed(text)
                
                # 验证维度一致性
                if target_dimension is None:
                    target_dimension = len(vec)
                elif len(vec) != target_dimension:
                    print(f"[Embedding警告] 向量维度不一致，调整为{target_dimension}维")
                    vec = self._adjust_dimension(vec, target_dimension)
                
                # 存入缓存
                self._store_in_cache(cache_key, vec, text)
                self._memory_cache[cache_key] = vec
                vectors.append(vec)
                
            except Exception as e:
                print(f"[Embedding错误] 处理第{idx}个文本时失败: {str(e)}")
                if target_dimension is None:
                    target_dimension = self.dimension
                fallback_vec = self._fake_embed(text)
                fallback_vec = self._adjust_dimension(fallback_vec, target_dimension)
                vectors.append(fallback_vec)
        
        return vectors

    def embed_single(self, text: str, require_real: bool = False) -> list[float]:
        """生成单个文本的向量（便捷方法）"""
        return self.embed([text], require_real=require_real)[0]

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

    def _remote_embed(self, text: str, require_real: bool = False) -> list[float]:
        """调用远程 Embedding API"""
        import httpx
        url = f"{self.api_base_url.rstrip('/')}/embeddings"
        body = {"model": self.model, "input": text}
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            response = httpx.post(url, json=body, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            return data["data"][0]["embedding"]
        except Exception as exc:
            if require_real:
                raise RuntimeError(
                    f"Embedding API 调用失败: {exc}。"
                    "生态位对比错误，无法生成向量，请检查 API 配置是否正确。"
                ) from exc
            print(f"远程向量 API 调用失败，使用假向量: {exc}")
            return self._fake_embed(text)

    def _fake_embed(self, text: str) -> list[float]:
        """生成基于文本哈希的伪向量（确定性）"""
        rng = np.random.default_rng(int(hashlib.sha256(text.encode()).hexdigest(), 16) % (2**32))
        vector = rng.normal(size=self.dimension)
        normalized = vector / np.linalg.norm(vector)
        return normalized.tolist()

    def _cache_path(self, cache_key: str) -> Path:
        """获取缓存文件路径"""
        return self._cache_dir / f"{cache_key}.json"

    def _load_from_cache(self, cache_key: str) -> list[float] | None:
        """从磁盘缓存加载"""
        path = self._cache_path(cache_key)
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                # 兼容旧格式（纯向量数组）和新格式（包含元数据）
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict) and "vector" in data:
                    return data["vector"]
            except Exception as e:
                print(f"[Embedding] 加载缓存失败 {cache_key}: {e}")
        return None

    def _store_in_cache(self, cache_key: str, vector: list[float], text: str) -> None:
        """存储到磁盘缓存（包含元数据）"""
        path = self._cache_path(cache_key)
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

    # ========== 存档集成功能 ==========
    
    def export_embeddings(self, texts: list[str]) -> dict[str, Any]:
        """导出指定文本的 embedding 数据（用于存档）
        
        Args:
            texts: 需要导出的文本列表
        
        Returns:
            可序列化的 embedding 数据字典
        """
        export_data = {
            "version": "1.0",
            "model_identifier": self.model_identifier,
            "provider": self.provider,
            "model": self.model,
            "dimension": self.dimension,
            "embeddings": {}
        }
        
        for text in texts:
            cache_key = self._make_cache_key(text)
            vector = self._load_from_cache(cache_key)
            if vector is None:
                # 如果没有缓存，生成新向量
                vector = self.embed_single(text)
            
            # 使用文本哈希作为 key（不含模型信息，便于跨模型恢复）
            text_hash = hashlib.sha256(text.encode()).hexdigest()
            export_data["embeddings"][text_hash] = {
                "vector": vector,
                "text_preview": text[:100],
            }
        
        return export_data

    def import_embeddings(self, import_data: dict[str, Any], texts: list[str]) -> int:
        """从存档导入 embedding 数据
        
        Args:
            import_data: 存档中的 embedding 数据
            texts: 需要匹配的文本列表（用于重建索引）
        
        Returns:
            成功导入的数量
        """
        if not import_data or "embeddings" not in import_data:
            return 0
        
        imported_count = 0
        stored_model = import_data.get("model_identifier", "")
        
        # 如果模型不匹配，记录警告但仍然导入
        if stored_model != self.model_identifier:
            print(f"[Embedding] 存档模型 ({stored_model}) 与当前模型 ({self.model_identifier}) 不匹配")
            print(f"[Embedding] 将使用存档中的向量，但可能影响分析准确性")
        
        for text in texts:
            text_hash = hashlib.sha256(text.encode()).hexdigest()
            if text_hash in import_data["embeddings"]:
                embedding_entry = import_data["embeddings"][text_hash]
                vector = embedding_entry.get("vector", [])
                
                if vector:
                    # 使用当前模型标识存储（覆盖旧缓存）
                    cache_key = self._make_cache_key(text)
                    self._store_in_cache(cache_key, vector, text)
                    self._memory_cache[cache_key] = vector
                    imported_count += 1
        
        print(f"[Embedding] 已导入 {imported_count}/{len(texts)} 个向量")
        return imported_count

    def clear_cache(self) -> int:
        """清除所有缓存"""
        count = 0
        for cache_file in self._cache_dir.glob("*.json"):
            try:
                cache_file.unlink()
                count += 1
            except Exception:
                pass
        self._memory_cache.clear()
        print(f"[Embedding] 已清除 {count} 个缓存文件")
        return count

    def get_cache_stats(self) -> dict[str, Any]:
        """获取缓存统计信息"""
        cache_files = list(self._cache_dir.glob("*.json"))
        total_size = sum(f.stat().st_size for f in cache_files)
        
        return {
            "cache_dir": str(self._cache_dir),
            "file_count": len(cache_files),
            "memory_cache_count": len(self._memory_cache),
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / 1024 / 1024, 2),
            "model_identifier": self.model_identifier,
        }

    # ========== 向量相似度搜索 ==========
    
    def build_index(self, texts: list[str], labels: list[str] | None = None) -> None:
        """构建向量索引（用于相似度搜索）
        
        Args:
            texts: 文本列表
            labels: 可选的标签列表（如物种代码）
        """
        vectors = self.embed(texts)
        labels = labels or [str(i) for i in range(len(texts))]
        
        for text, label, vec in zip(texts, labels, vectors):
            text_hash = hashlib.sha256(text.encode()).hexdigest()
            self._index[label] = vec
            self._index_texts[label] = text
        
        print(f"[Embedding] 索引构建完成: {len(self._index)} 个向量")

    def search_similar(
        self, 
        query: str, 
        top_k: int = 5,
        threshold: float = 0.0
    ) -> list[tuple[str, float, str]]:
        """搜索相似向量
        
        Args:
            query: 查询文本
            top_k: 返回数量
            threshold: 相似度阈值
        
        Returns:
            [(label, similarity, text), ...]
        """
        if not self._index:
            return []
        
        query_vec = np.array(self.embed_single(query))
        query_norm = np.linalg.norm(query_vec)
        if query_norm == 0:
            return []
        query_vec = query_vec / query_norm
        
        results = []
        for label, vec in self._index.items():
            vec_arr = np.array(vec)
            vec_norm = np.linalg.norm(vec_arr)
            if vec_norm == 0:
                continue
            vec_arr = vec_arr / vec_norm
            
            similarity = float(np.dot(query_vec, vec_arr))
            if similarity >= threshold:
                results.append((label, similarity, self._index_texts.get(label, "")))
        
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def compute_similarity_matrix(self, texts: list[str]) -> np.ndarray:
        """计算文本列表的相似度矩阵
        
        Args:
            texts: 文本列表
        
        Returns:
            N x N 相似度矩阵
        """
        vectors = self.embed(texts)
        matrix = np.array(vectors)
        
        # 归一化
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        normalized = matrix / norms
        
        # 计算余弦相似度
        similarity = normalized @ normalized.T
        return np.clip(similarity, -1.0, 1.0)

    def compute_distance_matrix(self, texts: list[str]) -> np.ndarray:
        """计算文本列表的距离矩阵（1 - 相似度）"""
        similarity = self.compute_similarity_matrix(texts)
        return 1.0 - similarity
