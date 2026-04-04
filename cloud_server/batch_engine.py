from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger("claw.cloud.batch_engine")


@dataclass
class BatchRequest:
    request_id: str
    messages: list[dict[str, str]]
    future: asyncio.Future
    created_at: float


class GPUClusterBatcher:
    """毫秒窗口批处理，确保请求 ID 与返回严格对应。"""

    def __init__(
        self,
        endpoint: str = "http://5090-cluster-gateway:8080/v1/chat/completions/batch",
        max_batch_size: int = 32,
        wait_ms: float = 1.0,
    ):
        self.endpoint = endpoint
        self.max_batch_size = max_batch_size
        self.wait_ms = wait_ms / 1000.0
        self.queue: list[BatchRequest] = []
        self._lock = asyncio.Lock()
        self._client = httpx.AsyncClient(timeout=30.0)
        self._running = False

    async def chat(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        req = BatchRequest(
            request_id=str(uuid.uuid4()),
            messages=messages,
            future=future,
            created_at=time.time(),
        )

        async with self._lock:
            self.queue.append(req)
            if not self._running:
                self._running = True
                asyncio.create_task(self._batch_loop())

        return await future

    async def _batch_loop(self) -> None:
        while True:
            await asyncio.sleep(self.wait_ms)
            async with self._lock:
                if not self.queue:
                    self._running = False
                    return
                batch = self.queue[: self.max_batch_size]
                self.queue = self.queue[self.max_batch_size :]
            asyncio.create_task(self._process_batch(batch))

    async def _process_batch(self, batch: list[BatchRequest]) -> None:
        start = time.perf_counter()
        payload = {
            "requests": [{"id": r.request_id, "messages": r.messages} for r in batch],
            "parallel_config": {"device": "RTX-5090-Cluster"},
        }

        try:
            resp = await self._client.post(self.endpoint, json=payload)
            if resp.status_code != 200:
                raise RuntimeError(f"cluster_http_{resp.status_code}:{resp.text}")

            results = (resp.json() or {}).get("results", {})
            for req in batch:
                if req.request_id not in results:
                    req.future.set_exception(ValueError(f"missing_result_for:{req.request_id}"))
                    continue
                req.future.set_result(results[req.request_id])

        except Exception as e:
            for req in batch:
                if not req.future.done():
                    req.future.set_exception(e)
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.info("[BatchEngine] batch_size=%d elapsed=%.2fms", len(batch), elapsed_ms)
