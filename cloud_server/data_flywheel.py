from __future__ import annotations

import json
import os
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import desc, select

from cloud_server.data_models import TradeLedgerORM, TradeStatusEnum
from cloud_server.db import session_scope


def _clean_text(v: str) -> str:
    txt = (v or "").strip()
    txt = re.sub(r"\s+", " ", txt)
    return txt[:2000]


def _to_prompt(row: TradeLedgerORM) -> str:
    return (
        f"用户需求: {_clean_text(row.demand_text)}\n"
        f"商品: {_clean_text(row.item_name)}\n"
        f"预算上限: {row.max_price:.2f}\n"
        "请给出商家谈判回复与报价。"
    )


def _to_answer(row: TradeLedgerORM) -> str:
    status = row.status.value if hasattr(row.status, "value") else str(row.status)
    return (
        f"商家回复: 可安排 {_clean_text(row.item_name)}，报价 {row.final_price:.2f} 元。\n"
        f"成交状态: {status}"
    )


class DataFlywheelService:
    def __init__(self):
        self.enabled = os.getenv("DPO_FLYWHEEL_ENABLED", "1") == "1"
        self.interval_sec = int(os.getenv("DPO_SCAN_INTERVAL_SEC", "300"))
        self.dataset_dir = Path(os.getenv("DPO_DATASET_DIR", "./cloud_server/data"))
        self.dataset_path = self.dataset_dir / "dpo_dataset_latest.jsonl"
        self.scheduler = AsyncIOScheduler(timezone="UTC")

    async def build_dataset(self) -> dict[str, Any]:
        self.dataset_dir.mkdir(parents=True, exist_ok=True)

        async with session_scope() as s:
            rows = (
                await s.scalars(select(TradeLedgerORM).order_by(desc(TradeLedgerORM.updated_at)).limit(10000))
            ).all()

        chosen_by_item: dict[str, list[TradeLedgerORM]] = defaultdict(list)
        rejected_by_item: dict[str, list[TradeLedgerORM]] = defaultdict(list)

        for r in rows:
            status = r.status if isinstance(r.status, TradeStatusEnum) else TradeStatusEnum(str(r.status))
            item_key = (r.item_name or "unknown").strip().lower()

            if status == TradeStatusEnum.executed:
                chosen_by_item[item_key].append(r)
                continue

            if status in {TradeStatusEnum.failed, TradeStatusEnum.expired}:
                rejected_by_item[item_key].append(r)
                continue

            reason = (r.error_reason or "").lower()
            if "circuit" in reason or "breaker" in reason or "熔断" in reason:
                rejected_by_item[item_key].append(r)

        lines: list[str] = []
        for item, chosen_rows in chosen_by_item.items():
            negatives = rejected_by_item.get(item) or []
            if not negatives:
                continue

            neg_idx = 0
            for pos in chosen_rows:
                neg = negatives[neg_idx % len(negatives)]
                neg_idx += 1

                prompt = _to_prompt(pos)
                chosen = _to_answer(pos)
                rejected = _to_answer(neg)

                sample = {
                    "prompt": prompt,
                    "chosen": chosen,
                    "rejected": rejected,
                    "meta": {
                        "request_id": pos.request_id,
                        "trade_id": pos.trade_id,
                        "merchant_id": pos.merchant_id,
                        "item_name": pos.item_name,
                        "chosen_status": (pos.status.value if hasattr(pos.status, "value") else str(pos.status)),
                        "rejected_status": (neg.status.value if hasattr(neg.status, "value") else str(neg.status)),
                        "generated_at": time.time(),
                    },
                }
                lines.append(json.dumps(sample, ensure_ascii=False))

        self.dataset_path.write_text("\n".join(lines), encoding="utf-8")

        return {
            "ok": True,
            "dataset_path": str(self.dataset_path),
            "samples": len(lines),
            "timestamp": time.time(),
        }

    async def _scheduled_job(self):
        try:
            await self.build_dataset()
        except Exception:
            # scheduler job should not crash server
            pass

    def start(self):
        if not self.enabled:
            return
        if self.scheduler.running:
            return
        self.scheduler.add_job(self._scheduled_job, IntervalTrigger(seconds=self.interval_sec), id="dpo_flywheel_job", replace_existing=True)
        self.scheduler.start()

    def stop(self):
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
