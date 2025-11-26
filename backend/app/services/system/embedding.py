from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable

import numpy as np

from ...core.config import get_settings

CACHE_DIR = Path(get_settings().cache_dir) / "embeddings"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


class EmbeddingService:
    """Caches embeddings for species descriptions to control cost."""

    def __init__(
        self,
        provider: str = "local",
        dimension: int = 64,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        enabled: bool = False,
    ) -> None:
        self.provider = provider
        self.dimension = dimension
        self.api_base_url = base_url
        self.api_key = api_key
        self.model = model
        self.enabled = enabled

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
        target_dimension = None  # 记录第一个向量的维度，确保后续一致
        
        for idx, text in enumerate(texts):
            try:
                cached = self._load_from_cache(text)
                if cached is not None:
                    # 验证缓存向量的维度
                    if target_dimension is None:
                        target_dimension = len(cached)
                    elif len(cached) != target_dimension:
                        print(f"[Embedding] 缓存向量维度不一致：期望{target_dimension}，得到{len(cached)}，重新生成")
                        cached = None
                
                if cached is not None:
                    vectors.append(cached)
                    continue
                
                # 判断是否启用远程向量
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
                    if len(vec) > target_dimension:
                        vec = vec[:target_dimension]
                    else:
                        vec = vec + [0.0] * (target_dimension - len(vec))
                
                self._store_in_cache(text, vec)
                vectors.append(vec)
            except Exception as e:
                print(f"[Embedding错误] 处理第{idx}个文本时失败: {str(e)}")
                # 生成降级向量
                if target_dimension is None:
                    target_dimension = self.dimension
                fallback_vec = self._fake_embed(text)
                if len(fallback_vec) != target_dimension:
                    if len(fallback_vec) > target_dimension:
                        fallback_vec = fallback_vec[:target_dimension]
                    else:
                        fallback_vec = fallback_vec + [0.0] * (target_dimension - len(fallback_vec))
                vectors.append(fallback_vec)
        
        return vectors

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
            # Fallback to fake embed on error (仅用于非关键功能)
            print(f"远程向量 API 调用失败，使用假向量: {exc}")
            return self._fake_embed(text)

    def _fake_embed(self, text: str) -> list[float]:
        rng = np.random.default_rng(int(hashlib.sha256(text.encode()).hexdigest(), 16) % (2**32))
        vector = rng.normal(size=self.dimension)
        normalized = vector / np.linalg.norm(vector)
        return normalized.tolist()

    def _cache_path(self, text: str) -> Path:
        key = hashlib.sha256(text.encode()).hexdigest()
        return CACHE_DIR / f"{key}.json"

    def _load_from_cache(self, text: str) -> list[float] | None:
        path = self._cache_path(text)
        if path.exists():
            return json.loads(path.read_text())
        return None

    def _store_in_cache(self, text: str, vector: list[float]) -> None:
        path = self._cache_path(text)
        path.write_text(json.dumps(vector))
