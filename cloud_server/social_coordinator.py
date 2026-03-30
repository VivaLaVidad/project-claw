from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple

import numpy as np

from shared.claw_protocol import GeoCoord, MatchFoundEvent, SocialIntent


def haversine_m(a: GeoCoord, b: GeoCoord) -> float:
    r = 6371000.0
    lat1, lng1 = np.radians(a.lat), np.radians(a.lng)
    lat2, lng2 = np.radians(b.lat), np.radians(b.lng)
    dlat, dlng = lat2 - lat1, lng2 - lng1
    h = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlng / 2.0) ** 2
    return float(r * 2.0 * np.arctan2(np.sqrt(h), np.sqrt(1.0 - h)))


def cosine_similarity_1024(v1: List[float], v2: List[float]) -> float:
    a = np.asarray(v1, dtype=np.float32)
    b = np.asarray(v2, dtype=np.float32)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom <= 1e-12:
        return 0.0
    return float(np.dot(a, b) / denom)


@dataclass
class ActiveClientIntent:
    intent: SocialIntent
    updated_at: float


class SocialCoordinator:
    def __init__(
        self,
        similarity_threshold: float = 0.85,
        max_distance_m: float = 5000.0,
        ttl_sec: float = 300.0,
        match_cooldown_sec: float = 600.0,
    ):
        self.similarity_threshold = similarity_threshold
        self.max_distance_m = max_distance_m
        self.ttl_sec = ttl_sec
        self.match_cooldown_sec = match_cooldown_sec

        self._active: Dict[str, ActiveClientIntent] = {}
        self._sse_queues: Dict[str, asyncio.Queue[MatchFoundEvent]] = {}
        self._active_stream_clients: Set[str] = set()
        self._pair_last_match_ts: Dict[Tuple[str, str], float] = {}
        self._metrics = {
            "intent_received": 0,
            "match_pairs": 0,
            "events_queued": 0,
            "queue_drops": 0,
        }
        self._lock = asyncio.Lock()

    async def register_sse(self, client_id: str) -> asyncio.Queue[MatchFoundEvent]:
        q: asyncio.Queue[MatchFoundEvent] = asyncio.Queue(maxsize=128)
        async with self._lock:
            self._sse_queues[client_id] = q
            self._active_stream_clients.add(client_id)
        return q

    async def unregister_sse(self, client_id: str):
        async with self._lock:
            self._sse_queues.pop(client_id, None)
            self._active_stream_clients.discard(client_id)

    async def upsert_intent(self, intent: SocialIntent) -> List[MatchFoundEvent]:
        now = time.time()
        events: List[MatchFoundEvent] = []

        async with self._lock:
            self._metrics["intent_received"] += 1
            self._active[intent.client_id] = ActiveClientIntent(intent=intent, updated_at=now)

            expired = [cid for cid, row in self._active.items() if now - row.updated_at > self.ttl_sec]
            for cid in expired:
                self._active.pop(cid, None)

            stale_pairs = [k for k, ts in self._pair_last_match_ts.items() if now - ts > self.match_cooldown_sec]
            for k in stale_pairs:
                self._pair_last_match_ts.pop(k, None)

            if intent.client_id not in self._active_stream_clients:
                return []

            for peer_id, peer_row in self._active.items():
                if peer_id == intent.client_id:
                    continue
                if peer_id not in self._active_stream_clients:
                    continue

                pair_key = tuple(sorted((intent.client_id, peer_id)))
                last_match_at = self._pair_last_match_ts.get(pair_key, 0.0)
                if now - last_match_at < self.match_cooldown_sec:
                    continue

                distance = haversine_m(intent.location, peer_row.intent.location)
                if distance > self.max_distance_m:
                    continue

                sim = cosine_similarity_1024(intent.persona_vector, peer_row.intent.persona_vector)
                if sim < self.similarity_threshold:
                    continue

                tip_a = self._build_ice_breaker(intent.topic_hint, peer_row.intent.topic_hint)
                tip_b = self._build_ice_breaker(peer_row.intent.topic_hint, intent.topic_hint)

                evt_a = MatchFoundEvent(
                    match_id=f"m-{uuid.uuid4().hex[:10]}",
                    client_id=intent.client_id,
                    peer_client_id=peer_id,
                    similarity=sim,
                    distance_m=distance,
                    ice_breaker_tip=tip_a,
                )
                evt_b = MatchFoundEvent(
                    match_id=f"m-{uuid.uuid4().hex[:10]}",
                    client_id=peer_id,
                    peer_client_id=intent.client_id,
                    similarity=sim,
                    distance_m=distance,
                    ice_breaker_tip=tip_b,
                )
                events.extend([evt_a, evt_b])
                self._pair_last_match_ts[pair_key] = now
                self._metrics["match_pairs"] += 1

            for event in events:
                q = self._sse_queues.get(event.client_id)
                if q is None:
                    continue
                if q.full():
                    try:
                        _ = q.get_nowait()
                        self._metrics["queue_drops"] += 1
                    except asyncio.QueueEmpty:
                        pass
                await q.put(event)
                self._metrics["events_queued"] += 1

        return events

    async def metrics_snapshot(self) -> dict:
        async with self._lock:
            return {
                "active_intents": len(self._active),
                "active_stream_clients": len(self._active_stream_clients),
                **self._metrics,
            }

    @staticmethod
    def _build_ice_breaker(topic_a: str, topic_b: str) -> str:
        a = (topic_a or "美食").strip() or "美食"
        b = (topic_b or "旅行").strip() or "旅行"
        return f"你们都对{a}/{b}有兴趣，先聊聊最近最喜欢的一家店吧。"
