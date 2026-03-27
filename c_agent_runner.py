from __future__ import annotations

import argparse
import asyncio
import json

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config import settings


def pick_top_offer(offers: list[dict]) -> dict | None:
    if not offers:
        return None
    return sorted(offers, key=lambda x: float(x.get("match_score", 0)), reverse=True)[0]


@retry(
    retry=retry_if_exception_type(requests.RequestException),
    wait=wait_exponential(multiplier=0.2, min=0.2, max=2),
    stop=stop_after_attempt(3),
    reraise=True,
)
def _post_json(url: str, payload: dict, headers: dict, timeout: float) -> dict:
    resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


async def run_quote_and_execute(
    client_id: str,
    demand_text: str,
    max_price: float,
    location: str = "agent-client",
    timeout: float = 3.0,
    preferred_tags: list[str] | None = None,
    avoid_tags: list[str] | None = None,
    eta_sensitivity: float = 0.5,
    budget_sensitivity: float = 0.5,
):
    base = settings.signaling_http_base_url
    preferred_tags = preferred_tags or []
    avoid_tags = avoid_tags or []

    def _intent_call() -> dict:
        headers = {}
        if settings.INTERNAL_API_TOKEN:
            headers["X-Internal-Token"] = settings.INTERNAL_API_TOKEN
        headers["Idempotency-Key"] = f"intent:{client_id}:{location}:{demand_text}:{max_price}"
        payload = {
            "client_id": client_id,
            "location": location,
            "demand_text": demand_text,
            "max_price": max_price,
            "timeout": timeout,
            "client_profile": {
                "preferred_tags": preferred_tags,
                "avoid_tags": avoid_tags,
                "eta_sensitivity": eta_sensitivity,
                "budget_sensitivity": budget_sensitivity,
            },
        }
        return _post_json(f"{base}/intent", payload=payload, headers=headers, timeout=max(6.0, timeout + 3))

    result = await asyncio.to_thread(_intent_call)
    offers = result.get("offers", [])
    best = pick_top_offer(offers)
    if not best:
        return {"ok": False, "stage": "intent", "reason": "no_offer", "payload": result}

    intent_id = result.get("intent_id", "")
    merchant_id = str(best.get("merchant_id", ""))
    final_price = float(best.get("final_price", 0))
    reply_text = str(best.get("reply_text", ""))

    def _execute_call() -> dict:
        headers = {
            "Idempotency-Key": f"execute:{intent_id}:{client_id}:{merchant_id}:{final_price}",
        }
        if settings.INTERNAL_API_TOKEN:
            headers["X-Internal-Token"] = settings.INTERNAL_API_TOKEN
        payload = {
            "intent_id": intent_id,
            "client_id": client_id,
            "merchant_id": merchant_id,
            "reply_text": reply_text,
            "final_price": final_price,
            "eta_minutes": int(best.get("eta_minutes", 0) or 0),
        }
        return _post_json(f"{base}/execute_trade", payload=payload, headers=headers, timeout=8)

    execute = await asyncio.to_thread(_execute_call)
    return {
        "ok": True,
        "intent": result,
        "best_offer": best,
        "execute": execute,
    }


def main():
    parser = argparse.ArgumentParser(description="C-Agent quote + execute runner")
    parser.add_argument("--client-id", default="c-agent-001")
    parser.add_argument("--demand", default="想吃牛肉面")
    parser.add_argument("--max-price", type=float, default=20.0)
    parser.add_argument("--location", default="agent-client")
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--preferred-tags", default="", help="逗号分隔，如 spicy,fast")
    parser.add_argument("--avoid-tags", default="", help="逗号分隔，如 oily,sweet")
    parser.add_argument("--eta-sensitivity", type=float, default=0.5)
    parser.add_argument("--budget-sensitivity", type=float, default=0.5)
    args = parser.parse_args()

    result = asyncio.run(
        run_quote_and_execute(
            client_id=args.client_id,
            demand_text=args.demand,
            max_price=args.max_price,
            location=args.location,
            timeout=args.timeout,
            preferred_tags=[x.strip() for x in args.preferred_tags.split(",") if x.strip()],
            avoid_tags=[x.strip() for x in args.avoid_tags.split(",") if x.strip()],
            eta_sensitivity=float(args.eta_sensitivity),
            budget_sensitivity=float(args.budget_sensitivity),
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
