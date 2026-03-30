"""
Project Claw - A2A smoke test
验证链路：A 发起 TradeRequest -> 多个 B 返回 Offer -> Hub 输出推荐
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
import uuid


def _post_json(url: str, body: dict, headers: dict | None = None, timeout: float = 8.0) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_json(url: str, headers: dict | None = None, timeout: float = 8.0) -> dict:
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    p = argparse.ArgumentParser(description="Project Claw A2A smoke test")
    p.add_argument("--url", default="http://127.0.0.1:8765", help="Hub HTTP URL")
    p.add_argument("--source", default="box-001", help="A 盒子 merchant_id")
    p.add_argument("--targets", default="box-002,box-003,box-004", help="B 盒子列表，逗号分隔")
    p.add_argument("--item", default="牛肉面")
    p.add_argument("--max", type=float, default=20.0)
    p.add_argument("--merchant-key", default="merchant-shared-key")
    p.add_argument("--timeout", type=float, default=20.0)
    args = p.parse_args()

    base = args.url.rstrip("/")
    targets = [x.strip() for x in args.targets.split(",") if x.strip()]
    if len(targets) < 3:
        raise SystemExit("targets 至少提供 3 个商家，才能触发推荐逻辑")

    print("[A2A] 1) source merchant auth ...")
    auth = _post_json(
        f"{base}/api/v1/auth/merchant",
        {"merchant_id": args.source, "key": args.merchant_key},
    )
    token = auth.get("token", "")
    if not token:
        raise SystemExit("source merchant token 获取失败")
    headers = {"Authorization": f"Bearer {token}"}

    print("[A2A] 2) dispatch trade_request to targets ...")
    request_id = str(uuid.uuid4())[:8]
    trade_request = {
        "request_id": request_id,
        "client_id": f"a2a-{args.source}",
        "item_name": args.item,
        "demand_text": f"我想要{args.item}，预算{args.max}元以内",
        "max_price": args.max,
        "quantity": 1,
        "timeout_sec": 8.0,
    }

    for t in targets:
        body = {
            "source_id": args.source,
            "target_id": t,
            "trade_request": trade_request,
        }
        try:
            r = _post_json(f"{base}/api/v1/a2a/request", body, headers=headers)
            print(f"  -> {t}: ok packet_id={r.get('packet_id')}")
        except Exception as e:
            print(f"  -> {t}: failed {e}")

    print("[A2A] 3) poll recommendation ...")
    deadline = time.time() + args.timeout
    last_err = ""
    while time.time() < deadline:
        try:
            rec = _get_json(f"{base}/api/v1/a2a/recommend/{request_id}")
            print("\n✅ A2A 推荐已生成")
            print(json.dumps(rec, ensure_ascii=False, indent=2))
            return
        except urllib.error.HTTPError as e:
            last_err = f"http_{e.code}"
        except Exception as e:
            last_err = str(e)
        time.sleep(0.8)

    raise SystemExit(f"❌ timeout: recommendation_not_ready ({last_err})")


if __name__ == "__main__":
    main()
