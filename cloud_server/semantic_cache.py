from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Optional

import numpy as np
import redis.asyncio as redis
from sentence_transformers import SentenceTransformer

logger = logging.getLogger("claw.cloud.semantic_cache")


class SemanticCache:
    """Redis + sentence-transformers 语义缓存。"""

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/1",
        model_name: str = "all-MiniLM-L6-v2",
        ttl_seconds: int = 300,
        similarity_threshold: float = 0.96,
    ):
        self.redis = redis.from_url(redis_url, decode_responses=True)
        self.model = SentenceTransformer(model_name)
        self.ttl_seconds = ttl_seconds
        self.similarity_threshold = similarity_threshold

    @staticmethod
    def _cosine_similarity(v1: np.ndarray, v2: np.ndarray) -> float:
        denom = float(np.linalg.norm(v1) * np.linalg.norm(v2))
        if denom <= 0:
            return 0.0
        return float(np.dot(v1, v2) / denom)

    @staticmethod
    def _item_key(demand_text: str) -> str:
        digest = hashlib.sha256(demand_text.encode("utf-8")).hexdigest()[:24]
        return f"semantic_cache:item:{digest}"

    async def get(self, demand_text: str) -> Optional[dict[str, Any]]:
        start = time.perf_counter()
        query_vector = np.array(self.model.encode(demand_text), dtype=np.float32)

        keys = await self.redis.keys("semantic_cache:item:*")
        if not keys:
            return None

        best_payload: Optional[dict[str, Any]] = None
        best_score = -1.0

        for key in keys:
            raw = await self.redis.get(key)
            if not raw:
                continue
            item = json.loads(raw)
            vec = np.array(item.get("vector", []), dtype=np.float32)
            if vec.size == 0:
                continue
            score = self._cosine_similarity(query_vector, vec)
            if score > best_score:
                best_score = score
                best_payload = item.get("payload")

        elapsed_ms = (time.perf_counter() - start) * 1000
        if best_payload is not None and best_score > self.similarity_threshold:
            logger.info("[SemanticCache] hit score=%.4f elapsed=%.2fms", best_score, elapsed_ms)
            return best_payload

        logger.info("[SemanticCache] miss max_score=%.4f elapsed=%.2fms", best_score, elapsed_ms)
        return None

    async def set(self, demand_text: str, payload: dict[str, Any]) -> None:
        vector = np.array(self.model.encode(demand_text), dtype=np.float32).tolist()
        item = {
            "demand_text": demand_text,
            "vector": vector,
            "payload": payload,
            "created_at": time.time(),
        }
        await self.redis.set(self._item_key(demand_text), json.dumps(item, ensure_ascii=False), ex=self.ttl_seconds)
