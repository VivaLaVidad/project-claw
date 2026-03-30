"""
Project Claw v14.0 - edge_box/main.py
【B端】工业级运行入口

能力：
1) Producer/Consumer 消息队列，避免 LLM 慢导致漏消息
2) LLM 超时控制 + 熔断降级（Circuit Breaker）
3) Watchdog 自动拉起 worker / ws / 设备重连
4) 进程级自愈重启（异常退避重启）
5) 结构化事件日志 + 运行指标日志
"""
from __future__ import annotations

import json
import logging
import os
import queue
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("edge_box.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("claw.edge.main")


def log_event(event: str, **fields):
    payload = {"event": event, **fields}
    logger.info(json.dumps(payload, ensure_ascii=False))


@dataclass
class RuntimeMetrics:
    produced: int = 0
    dropped: int = 0
    consumed: int = 0
    sent: int = 0
    llm_timeout: int = 0
    llm_error: int = 0
    degraded: int = 0


class CircuitBreaker:
    """简单稳定的熔断器：失败阈值后打开，冷却后半开。"""

    def __init__(self, failure_threshold: int, open_seconds: float):
        self.failure_threshold = failure_threshold
        self.open_seconds = open_seconds
        self.failures = 0
        self.open_until = 0.0
        self._lock = threading.Lock()

    def allow(self) -> bool:
        with self._lock:
            now = time.time()
            if now < self.open_until:
                return False
            return True

    def mark_success(self):
        with self._lock:
            self.failures = 0
            self.open_until = 0.0

    def mark_failure(self):
        with self._lock:
            self.failures += 1
            if self.failures >= self.failure_threshold:
                self.open_until = time.time() + self.open_seconds


def load_config() -> dict:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    return {
        "MERCHANT_ID": os.getenv("MERCHANT_ID", "box-001"),
        "SIGNALING_URL": os.getenv("SIGNALING_URL", ""),
        "DEEPSEEK_API_KEY": os.getenv("DEEPSEEK_API_KEY", ""),
        "MENU_CSV": os.getenv("MENU_CSV", "menu.csv"),
        "PAYMENT_QR": os.getenv("PAYMENT_QR", "payment_qr.png"),
        "INPUT_X": float(os.getenv("INPUT_X", "540")),
        "INPUT_Y": float(os.getenv("INPUT_Y", "1800")),
        "POLL_INTERVAL": float(os.getenv("POLL_INTERVAL", "0.3")),
        "DEVICE_SERIAL": os.getenv("DEVICE_SERIAL", None),
        # 工业级参数
        "MESSAGE_QUEUE_MAX": int(os.getenv("MESSAGE_QUEUE_MAX", "200")),
        "WATCHDOG_INTERVAL": float(os.getenv("WATCHDOG_INTERVAL", "5")),
        "METRICS_LOG_INTERVAL": float(os.getenv("METRICS_LOG_INTERVAL", "15")),
        "LLM_TIMEOUT_SEC": float(os.getenv("LLM_TIMEOUT_SEC", "18")),
        "CB_FAILURE_THRESHOLD": int(os.getenv("CB_FAILURE_THRESHOLD", "3")),
        "CB_OPEN_SECONDS": float(os.getenv("CB_OPEN_SECONDS", "60")),
        "HUB_MERCHANT_KEY": os.getenv("HUB_MERCHANT_KEY", "merchant-shared-key"),
        "MERCHANT_LAT": os.getenv("MERCHANT_LAT", ""),
        "MERCHANT_LNG": os.getenv("MERCHANT_LNG", ""),
    }


def build_components(cfg: dict):
    from edge_box.agent_workflow import build_workflow
    from edge_box.local_memory import LocalMenuRAG
    from edge_box.physical_tool import PhysicalTool
    from edge_box.lobster_tool import PhysicalActionTool

    rag = LocalMenuRAG(cfg["MENU_CSV"])
    logger.info("✅ LocalMenuRAG 就绪")

    physical = PhysicalTool(
        device_serial=cfg["DEVICE_SERIAL"],
        qr_path=cfg["PAYMENT_QR"],
    )
    if not physical.init_device():
        logger.warning("⚠️ 设备未连接，物理操控不可用")
    if not physical.init_ocr():
        logger.warning("⚠️ OCR 未就绪")

    action_tool = PhysicalActionTool(
        physical=physical,
        input_x=cfg["INPUT_X"],
        input_y=cfg["INPUT_Y"],
        max_retries=3,
    )

    workflow = build_workflow(
        api_key=cfg["DEEPSEEK_API_KEY"],
        rag=rag,
        merchant_id=cfg["MERCHANT_ID"],
    )
    logger.info("✅ AgentWorkflow 就绪")
    return physical, workflow, rag, action_tool


def start_ws_listener(cfg: dict, workflow, physical, action_tool, runtime_state: dict) -> Optional[threading.Thread]:
    url = cfg["SIGNALING_URL"]
    if not url:
        logger.info("[WSListener] SIGNALING_URL 未配置，跳过")
        return None

    from edge_box.ws_listener import WSListener

    mid = cfg["MERCHANT_ID"]
    token = ""
    http_url = url.replace("wss://", "https://").replace("ws://", "http://")
    try:
        import requests
        auth_res = requests.post(
            f"{http_url}/api/v1/auth/merchant",
            json={"merchant_id": mid, "key": cfg["HUB_MERCHANT_KEY"]},
            timeout=8,
        )
        if 200 <= auth_res.status_code < 300:
            token = (auth_res.json() or {}).get("token", "")
        else:
            logger.warning(f"[WSListener] 商家鉴权失败 status={auth_res.status_code}")
    except Exception as e:
        logger.warning(f"[WSListener] 商家鉴权异常: {e}")

    ws_url = f"{url}/ws/merchant/{mid}"
    if token:
        ws_url = f"{ws_url}?token={token}"
    # 附加商家坐标（用于 Hub 地理筛选）
    lat = cfg.get("MERCHANT_LAT", "").strip()
    lng = cfg.get("MERCHANT_LNG", "").strip()
    if lat and lng:
        sep = "&" if "?" in ws_url else "?"
        ws_url = f"{ws_url}{sep}lat={lat}&lng={lng}"
    listener = WSListener(
        merchant_id=mid,
        server_url=ws_url,
        workflow=workflow,
        physical=physical,
        input_xy=(cfg["INPUT_X"], cfg["INPUT_Y"]),
        hub_http_url=url,
        merchant_key=cfg["HUB_MERCHANT_KEY"],
        on_billing_update=lambda balance, payload: handle_billing_update(action_tool, runtime_state, balance, payload),
    )
    t = listener.start()
    logger.info(f"✅ WSListener -> {ws_url}")
    return t


def enqueue_latest(q: "queue.Queue[dict]", item: dict, metrics: RuntimeMetrics):
    """队列满时丢弃最旧消息，保证新消息可入队。"""
    try:
        q.put_nowait(item)
        metrics.produced += 1
        return
    except queue.Full:
        metrics.dropped += 1
        try:
            _ = q.get_nowait()  # 丢弃最旧
        except queue.Empty:
            pass
        try:
            q.put_nowait(item)
            metrics.produced += 1
        except queue.Full:
            metrics.dropped += 1
            logger.warning("[MsgQueue] 队列仍满，放弃本条消息")


def ocr_polling_loop(cfg: dict, physical, msg_queue: "queue.Queue[dict]", metrics: RuntimeMetrics):
    """
    Producer：只负责检测新消息并入队。
    不做 LLM 推理，避免阻塞导致漏读新消息。
    """
    interval = cfg["POLL_INTERVAL"]
    logger.info("[OCRLoop] 启动 (producer, v4 节点计数法 + queue)")

    while True:
        try:
            msg = physical.detect_new_customer_message()
            if msg:
                item = {
                    "message_id": uuid.uuid4().hex[:12],
                    "text": msg,
                    "ts": time.time(),
                }
                enqueue_latest(msg_queue, item, metrics)
                log_event(
                    "message_enqueued",
                    message_id=item["message_id"],
                    text=item["text"][:60],
                    qsize=msg_queue.qsize(),
                )
        except Exception as e:
            logger.error(f"[OCRLoop] 异常: {e}")
        time.sleep(interval)


def build_fallback_reply(msg: str) -> str:
    if "在吗" in msg or "老板" in msg:
        return "兄弟在呢，想吃点啥？"
    if "价格" in msg or "多少钱" in msg:
        return "兄弟，牛肉面18、麻辣烫15、水饺8，想吃哪个我给你安排！"
    return "兄弟收到，正在给你安排，稍等片刻！"


def _set_led(status: str):
    cmd = os.getenv("CLAW_LED_COMMAND", "").strip()
    if not cmd:
        return
    try:
        subprocess.run(f"{cmd} {status}", shell=True, check=False, timeout=3)
    except Exception:
        pass


def handle_billing_update(action_tool, runtime_state: dict, balance: float, payload: dict):
    runtime_state["current_balance"] = balance
    runtime_state["last_billing_payload"] = payload
    log_event("billing_update", balance=balance, currency_unit=payload.get("currency_unit", "Token"), frozen=payload.get("is_frozen", False))
    if balance <= 0 and action_tool is not None and hasattr(action_tool, "show_fee_reminder"):
        try:
            import asyncio
            asyncio.run(action_tool.show_fee_reminder("欠费提醒：余额不足，已停止接单"))
        except Exception as e:
            logger.warning(f"[BillingUI] fee reminder failed: {e}")


def message_worker_loop(
    cfg: dict,
    workflow,
    physical,
    action_tool,
    msg_queue: "queue.Queue[dict]",
    metrics: RuntimeMetrics,
    runtime_state: dict,
):
    """
    Consumer：串行消费消息，调用 LLM + 发送回复。
    含超时控制 + 熔断降级。
    """
    from edge_box.agent_workflow import run_chat_state

    input_x = cfg["INPUT_X"]
    input_y = cfg["INPUT_Y"]
    timeout_sec = cfg["LLM_TIMEOUT_SEC"]

    breaker = CircuitBreaker(
        failure_threshold=cfg["CB_FAILURE_THRESHOLD"],
        open_seconds=cfg["CB_OPEN_SECONDS"],
    )

    logger.info("[MsgWorker] 启动 (consumer, 串行 + 超时 + 熔断)")

    # 单 worker 内部独占线程池，用于对 run_chat 加 timeout
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="llm-call") as pool:
        while True:
            item = msg_queue.get()
            message_id = item.get("message_id", "unknown")
            msg = item.get("text", "")
            metrics.consumed += 1

            try:
                log_event("message_consuming", message_id=message_id, text=msg[:60], qsize=msg_queue.qsize())
                _set_led("yellow_blink")
                sent = False

                if not breaker.allow():
                    reply = build_fallback_reply(msg)
                    sent = physical.send_message(input_x, input_y, reply)
                    metrics.degraded += 1
                    log_event("circuit_open_degrade", message_id=message_id)
                else:
                    future = pool.submit(run_chat_state,
                        workflow,
                        msg,
                        cfg["MERCHANT_ID"],
                        None,
                        physical,
                        action_tool,
                        float(runtime_state.get("current_balance", 1.0)))
                    try:
                        result_state = future.result(timeout=timeout_sec)
                        reply = result_state.get("final_reply", "")
                        sent = bool(result_state.get("physical_sent", False))
                        breaker.mark_success()
                    except FuturesTimeoutError:
                        metrics.llm_timeout += 1
                        breaker.mark_failure()
                        reply = build_fallback_reply(msg)
                        sent = physical.send_message(input_x, input_y, reply)
                        log_event("llm_timeout", message_id=message_id, timeout_sec=timeout_sec)
                    except Exception as e:
                        metrics.llm_error += 1
                        breaker.mark_failure()
                        reply = build_fallback_reply(msg)
                        sent = physical.send_message(input_x, input_y, reply)
                        log_event("llm_error", message_id=message_id, error=str(e))

                if sent:
                    metrics.sent += 1
                    log_event("message_replied", message_id=message_id, sent=sent, reply=reply[:60])

            except Exception as e:
                logger.error(f"[MsgWorker] 处理失败 message_id={message_id}: {e}")
            finally:
                _set_led("green_solid")
                msg_queue.task_done()


def start_message_worker(cfg: dict, workflow, physical, action_tool, msg_queue: "queue.Queue[dict]", metrics: RuntimeMetrics, runtime_state: dict) -> threading.Thread:
    t = threading.Thread(
        target=message_worker_loop,
        args=(cfg, workflow, physical, action_tool, msg_queue, metrics, runtime_state),
        daemon=True,
        name="MsgWorker",
    )
    t.start()
    return t


def start_menu_reload_server(rag, port: int = 18765):
    """
    商业级菜单热更新：轻量 HTTP 服务，POST /menu/reload 无需重启即可更新菜单
    鉴权：Bearer token = HUB_MERCHANT_KEY
    """
    from http.server import BaseHTTPRequestHandler, HTTPServer

    merchant_key = os.getenv("HUB_MERCHANT_KEY", "merchant-shared-key")

    class ReloadHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # 静默访问日志
            pass

        def _auth_ok(self) -> bool:
            auth = self.headers.get("Authorization", "")
            return auth == f"Bearer {merchant_key}"

        def do_POST(self):
            if self.path != "/menu/reload":
                self.send_response(404); self.end_headers(); return
            if not self._auth_ok():
                self.send_response(403)
                self.end_headers()
                self.wfile.write(b'{"error":"forbidden"}')
                return
            try:
                rag._items.clear()
                rag._load()
                rag._init_semantic()
                msg = f'{{"ok":true,"items":{len(rag._items)}}}'
                log_event("menu_reloaded", items=len(rag._items))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(msg.encode())
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f'{{"error":"{e}"}}'.encode())

        def do_GET(self):
            if self.path == "/menu/status":
                msg = f'{{"items":{len(rag._items)},"semantic":{str(rag._semantic_ready).lower()}}}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(msg.encode())
            else:
                self.send_response(404); self.end_headers()

    def _serve():
        try:
            srv = HTTPServer(("127.0.0.1", port), ReloadHandler)
            logger.info(f"[MenuReload] 热更新服务已启动 http://127.0.0.1:{port}/menu/reload")
            srv.serve_forever()
        except Exception as e:
            logger.error(f"[MenuReload] 启动失败: {e}")




    t = threading.Thread(target=_serve, daemon=True, name="MenuReloadServer")
    t.start()
    return t

def metrics_logger_loop(cfg: dict, msg_queue: "queue.Queue[dict]", metrics: RuntimeMetrics):
    interval = cfg["METRICS_LOG_INTERVAL"]
    while True:
        time.sleep(interval)
        log_event(
            "runtime_metrics",
            qsize=msg_queue.qsize(),
            produced=metrics.produced,
            dropped=metrics.dropped,
            consumed=metrics.consumed,
            sent=metrics.sent,
            llm_timeout=metrics.llm_timeout,
            llm_error=metrics.llm_error,
            degraded=metrics.degraded,
        )


def watchdog_loop(
    cfg: dict,
    workflow,
    physical,
    action_tool,
    msg_queue: "queue.Queue[dict]",
    metrics: RuntimeMetrics,
    state: dict,
):
    """Watchdog：周期检查关键线程存活，自动拉起。"""
    interval = cfg["WATCHDOG_INTERVAL"]
    logger.info("[Watchdog] 启动")

    while True:
        time.sleep(interval)
        try:
            wt = state.get("worker_thread")
            if wt is None or not wt.is_alive():
                logger.warning("[Watchdog] MsgWorker 异常退出，正在重拉...")
                state["worker_thread"] = start_message_worker(cfg, workflow, physical, action_tool, msg_queue, metrics, state)

            if cfg["SIGNALING_URL"]:
                ws_t = state.get("ws_thread")
                if ws_t is None or not ws_t.is_alive():
                    logger.warning("[Watchdog] WSListener 异常退出，正在重拉...")
                    state["ws_thread"] = start_ws_listener(cfg, workflow, physical, action_tool, state)

            # 设备掉线重连（限速：每 30s 最多尝试一次，避免日志刷屏）
            now = time.time()
            if not getattr(physical, "_d", None):
                last_reconnect = state.get("_last_device_reconnect", 0)
                if now - last_reconnect >= 30:
                    state["_last_device_reconnect"] = now
                    if physical.reconnect():
                        physical.init_ocr()
                        logger.info("[Watchdog] 设备重连成功")
                    else:
                        logger.debug("[Watchdog] 设备未就绪，等待下次重试")
        except Exception as e:
            logger.error(f"[Watchdog] 异常: {e}")


def run_once():
    logger.info("=" * 60)
    logger.info("Project Claw v14.0 - Edge Box 启动")
    logger.info("=" * 60)

    cfg = load_config()
    logger.info(f"merchant_id={cfg['MERCHANT_ID']} signaling={cfg['SIGNALING_URL'] or '(未配置)'}")

    physical, workflow, rag, action_tool = build_components(cfg)

    # 菜单热更新服务（POST /menu/reload，无需重启）
    menu_reload_port = int(os.getenv("MENU_RELOAD_PORT", "18765"))
    start_menu_reload_server(rag, menu_reload_port)

    metrics = RuntimeMetrics()
    msg_queue: "queue.Queue[dict]" = queue.Queue(maxsize=cfg["MESSAGE_QUEUE_MAX"])

    state = {
        "current_balance": 1.0,
        "last_billing_payload": {},
        "ws_thread": None,
        "worker_thread": None,
    }
    state["ws_thread"] = start_ws_listener(cfg, workflow, physical, action_tool, state)
    state["worker_thread"] = start_message_worker(cfg, workflow, physical, action_tool, msg_queue, metrics, state)

    threading.Thread(
        target=metrics_logger_loop,
        args=(cfg, msg_queue, metrics),
        daemon=True,
        name="MetricsLogger",
    ).start()

    threading.Thread(
        target=watchdog_loop,
        args=(cfg, workflow, physical, action_tool, msg_queue, metrics, state),
        daemon=True,
        name="RuntimeWatchdog",
    ).start()

    # 主线程只做 producer（微信新消息检测）
    if physical.ready:
        ocr_polling_loop(cfg, physical, msg_queue, metrics)
    else:
        _last_dev_rc = 0
        while True:
            time.sleep(2)
            _now = time.time()
            if _now - _last_dev_rc >= 30:
                _last_dev_rc = _now
                if physical.reconnect():
                    physical.init_ocr()
                    logger.info("设备重连成功，启动 OCR producer")
                    ocr_polling_loop(cfg, physical, msg_queue, metrics)

def main():
    """进程级守护：run_once 若异常退出，自动重启。"""
    backoff = [2, 5, 10, 20, 30]
    attempt = 0
    while True:
        try:
            run_once()
            attempt = 0
        except KeyboardInterrupt:
            logger.info("收到 KeyboardInterrupt，进程退出")
            break
        except Exception as e:
            delay = backoff[min(attempt, len(backoff) - 1)]
            logger.exception(f"[ProcessGuard] 主流程崩溃: {e}，{delay}s 后重启")
            time.sleep(delay)
            attempt += 1


if __name__ == "__main__":
    main()
