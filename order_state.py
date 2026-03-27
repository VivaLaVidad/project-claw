from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class OrderStatus(str, Enum):
    CREATED = "created"
    BROADCASTED = "broadcasted"
    OFFERED = "offered"
    EXECUTING = "executing"
    EXECUTED = "executed"
    FAILED = "failed"


@dataclass
class OrderRecord:
    intent_id: str
    client_id: str
    demand_text: str
    max_price: float
    location: str
    status: OrderStatus = OrderStatus.CREATED
    offers: list[dict[str, Any]] = field(default_factory=list)
    selected_offer: dict[str, Any] | None = None
    executed_result: dict[str, Any] | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class OrderStore:
    def __init__(self, file_path: str = "logs/order_store.jsonl"):
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._orders: dict[str, OrderRecord] = {}

    def create_intent(self, intent_id: str, client_id: str, demand_text: str, max_price: float, location: str) -> OrderRecord:
        with self._lock:
            record = OrderRecord(intent_id=intent_id, client_id=client_id, demand_text=demand_text, max_price=max_price, location=location)
            self._orders[intent_id] = record
            self._append_event(intent_id, "created", asdict(record))
            return record

    def mark_broadcasted(self, intent_id: str, total_merchants: int) -> None:
        with self._lock:
            record = self._orders.get(intent_id)
            if not record:
                return
            record.status = OrderStatus.BROADCASTED
            record.updated_at = time.time()
            self._append_event(intent_id, "broadcasted", {"total_merchants": total_merchants})

    def add_offer(self, intent_id: str, offer: dict[str, Any]) -> None:
        with self._lock:
            record = self._orders.get(intent_id)
            if not record:
                return
            record.offers = [x for x in record.offers if x.get("merchant_id") != offer.get("merchant_id")]
            record.offers.append(offer)
            record.status = OrderStatus.OFFERED
            record.updated_at = time.time()
            self._append_event(intent_id, "offer_received", offer)

    def mark_executing(self, intent_id: str, selected_offer: dict[str, Any]) -> None:
        with self._lock:
            record = self._orders.get(intent_id)
            if not record:
                return
            record.status = OrderStatus.EXECUTING
            record.selected_offer = selected_offer
            record.updated_at = time.time()
            self._append_event(intent_id, "executing", selected_offer)

    def mark_executed(self, intent_id: str, result: dict[str, Any]) -> None:
        with self._lock:
            record = self._orders.get(intent_id)
            if not record:
                return
            record.status = OrderStatus.EXECUTED
            record.executed_result = result
            record.updated_at = time.time()
            self._append_event(intent_id, "executed", result)

    def mark_failed(self, intent_id: str, reason: str) -> None:
        with self._lock:
            record = self._orders.get(intent_id)
            if not record:
                return
            record.status = OrderStatus.FAILED
            record.updated_at = time.time()
            self._append_event(intent_id, "failed", {"reason": reason})

    def get(self, intent_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._orders.get(intent_id)
            return asdict(record) if record else None

    def list_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            values = sorted(self._orders.values(), key=lambda x: x.updated_at, reverse=True)
            return [asdict(x) for x in values[:limit]]

    def _append_event(self, intent_id: str, event_type: str, payload: dict[str, Any]) -> None:
        row = {
            "ts": time.time(),
            "intent_id": intent_id,
            "event": event_type,
            "payload": payload,
        }
        with self.file_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
