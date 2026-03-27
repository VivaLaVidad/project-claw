

"""
Project Claw v12.0 - 工业级生产主程序

完整集成：
  - LocalMemory   : ChromaDB 本地向量记忆
  - AgentWorkflow : async LangGraph 商业状态机
  - BusinessBrain : sync LangGraph 商业大脑（备用）
  - VirtualMatch  : C 端虚拟匹配房间
  - UIVerifier    : 发送后界面状态校验
  - FeishuSync    : 飞书群 + 多维表格异步同步
"""
import warnings
warnings.filterwarnings("ignore", message=".*pin_memory.*")
warnings.filterwarnings("ignore", category=UserWarning, module="torch")

import os
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import cv2
import logging
import logging.handlers
import threading
import time
from pathlib import Path
from typing import List, Optional

from config import settings
from logger_setup import setup_logger
from llm_client import LLMClient
from local_memory import StoreManager
from agent_workflow import build_workflow as build_agent_workflow_impl
from business_brain import build_business_brain
from brain_rag import RAGEngine
from virtual_match_room import VirtualMatchRoom
from session_manager import SessionManager
from edge_driver import U2Driver
from edge_pipeline import BubbleDetector, MessageDedup, MessageExtractor
from edge_runtime import EdgeRuntimeContext
from edge_services import FeishuSync, ReplyEngine
from health_monitor import HealthMonitor
from a2a_box_client import A2ABoxClient, make_execute_trade_handler


logger = setup_logger("lobster")
reader: Optional[object] = None


def build_llm_client() -> LLMClient:
    return LLMClient(
        api_key=settings.DEEPSEEK_API_KEY,
        api_url=settings.DEEPSEEK_API_URL,
        model=settings.DEEPSEEK_MODEL,
        temperature=settings.DEEPSEEK_TEMPERATURE,
        max_tokens=settings.DEEPSEEK_MAX_TOKENS,
        timeout=settings.DEEPSEEK_TIMEOUT,
        max_retries=settings.DEEPSEEK_MAX_RETRIES,
    )


def build_store_manager() -> Optional[StoreManager]:
    store: Optional[StoreManager] = None
    ready = threading.Event()

    def _init_store():
        nonlocal store
        if not settings.LOCAL_MEMORY_ENABLED:
            ready.set()
            return
        try:
            logger.info("⏳ LocalMemory 初始化中（后台）...")
            s = StoreManager(
                db_dir=settings.LOCAL_MEMORY_DB_DIR,
                embed_model=settings.LOCAL_MEMORY_EMBED_MODEL,
                top_k=settings.LOCAL_MEMORY_TOP_K,
            )
            n = s.load_csv(settings.LOCAL_MEMORY_CSV)
            store = s
            logger.info(f"✅ LocalMemory 就绪 | {n} 条业务数据")
        except Exception as e:
            logger.error(f"❌ LocalMemory 初始化失败（将跳过）: {e}")
        finally:
            ready.set()

    threading.Thread(target=_init_store, daemon=True, name="StoreInit").start()
    ready.wait(timeout=30)
    if store is None:
        logger.warning("⚠️ LocalMemory 未就绪，以无记忆模式运行")
    return store


def build_agent_workflow() -> Optional[object]:
    if not settings.AGENT_WORKFLOW_ENABLED:
        return None
    try:
        workflow = build_agent_workflow_impl(api_key=settings.DEEPSEEK_API_KEY)
        logger.info("✅ AgentWorkflow 就绪 (IntentRouter+RAG+Negotiator)")
        return workflow
    except Exception as e:
        logger.error(f"❌ AgentWorkflow 初始化失败: {e}")
        return None


def build_brain_workflow(llm: LLMClient) -> Optional[object]:
    if not settings.BRAIN_ENABLED:
        return None
    try:
        rag = RAGEngine(
            persist_dir=settings.RAG_PERSIST_DIR,
            collection_name=settings.RAG_COLLECTION,
            top_k=settings.RAG_TOP_K,
        )
        if settings.MENU_EXCEL_PATH:
            rag.load_from_excel(settings.MENU_EXCEL_PATH)
        else:
            rag.load_menu()
        workflow = build_business_brain(llm=llm, rag=rag)
        logger.info("✅ BusinessBrain 就绪 (备用)")
        return workflow
    except Exception as e:
        logger.error(f"❌ BusinessBrain 初始化失败: {e}")
        return None


def build_match_room(llm: LLMClient) -> Optional[VirtualMatchRoom]:
    if not settings.MATCH_ENABLED:
        return None
    try:
        room = VirtualMatchRoom(
            llm=llm,
            max_rounds=settings.MATCH_ROUNDS,
            match_threshold=settings.MATCH_THRESHOLD,
        )
        logger.info("✅ C端虚拟匹配房间就绪")
        return room
    except Exception as e:
        logger.error(f"❌ C端匹配房间初始化失败: {e}")
        return None


def build_message_pipeline() -> tuple[MessageDedup, BubbleDetector, MessageExtractor]:
    return (
        MessageDedup(
            window=settings.MESSAGE_DEDUP_WINDOW,
            time_window=settings.MESSAGE_DEDUP_TIME_WINDOW,
        ),
        BubbleDetector(),
        MessageExtractor(),
    )


def build_runtime(driver) -> EdgeRuntimeContext:
    runtime = EdgeRuntimeContext(
        driver=driver,
        payment_qr_path=settings.__dict__.get("PAYMENT_QR_PATH", "./payment_qr.png"),
    )
    from agent_workflow import set_payment_callback
    set_payment_callback(runtime.payment_sender.send_payment_code)
    logger.info("✅ PaymentSender 就绪（收款码: ./payment_qr.png）")
    return runtime


def build_monitor() -> HealthMonitor:
    monitor = HealthMonitor(
        reconnect_fn=lambda: U2Driver.connect(),
        restart_ocr_fn=init_ocr,
        check_interval=15.0,
        work_dir=".",
    )
    monitor.mark_device_ok(True)
    monitor.mark_ocr_ok(True)
    monitor.start()
    logger.info("✅ HealthMonitor 就绪")
    return monitor


def build_a2a_client(brain_wf, runtime: EdgeRuntimeContext):
    a2a_url = getattr(settings, "A2A_SIGNALING_URL", "")
    if not a2a_url or not brain_wf:
        logger.info("[A2A] A2A_SIGNALING_URL 未配置，跳过 A2ABoxClient")
        return None
    try:
        execute_handler = make_execute_trade_handler(
            verifier=runtime.verifier,
            payment_sender=runtime.payment_sender,
            input_x=runtime.geometry.input_x,
            input_y=runtime.geometry.input_y,
        )
        client = A2ABoxClient(
            merchant_id=getattr(settings, "A2A_MERCHANT_ID", "box-001"),
            server_url=a2a_url,
            brain_workflow=brain_wf,
            on_execute_trade=execute_handler,
        )
        client.start()
        logger.info(f"✅ A2ABoxClient 就绪 -> {a2a_url}")
        return client
    except Exception as e:
        logger.warning(f"⚠️ A2ABoxClient 启动失败: {e}")
        return None


def build_session_manager() -> SessionManager:
    session_mgr = SessionManager(max_sessions=200, max_turns=8, ttl_sec=1800)
    logger.info("✅ SessionManager 就绪")
    return session_mgr


def startup_smoke_check() -> bool:
    try:
        llm = build_llm_client()
        _ = build_agent_workflow()
        _ = build_brain_workflow(llm)
        _ = build_match_room(llm)
        _ = build_message_pipeline()
        _ = FeishuSync()
        _ = ReplyEngine(llm=llm, agent_workflow=None, brain_workflow=None, system_prompt=settings.SYSTEM_PROMPT)
        _ = build_session_manager()
        logger.info("✅ 启动装配 smoke check 通过")
        return True
    except Exception as e:
        logger.error(f"❌ 启动装配 smoke check 失败: {e}")
        return False


def init_ocr() -> bool:
    global reader
    logger.info("⏳ 初始化 EasyOCR...")
    try:
        import easyocr
        reader = easyocr.Reader(settings.OCR_LANGUAGES)
        logger.info("✅ EasyOCR 就绪")
        return True
    except Exception as e:
        logger.error(f"❌ EasyOCR 初始化失败: {e}")
        return False


# ==================== 主程序 ====================

def main():
    logger.info("=" * 70)
    logger.info("🦞 Project Claw v12.0 - 工业级全集成版")
    logger.info(
        f"   LocalMemory:{'✅' if settings.LOCAL_MEMORY_ENABLED else '❌'}  "
        f"AgentWorkflow:{'✅' if settings.AGENT_WORKFLOW_ENABLED else '❌'}  "
        f"Brain:{'✅' if settings.BRAIN_ENABLED else '❌'}  "
        f"Match:{'✅' if settings.MATCH_ENABLED else '❌'}  "
        f"UIVerify:{'✅' if settings.UI_VERIFY_ENABLED else '❌'}"
    )
    logger.info("=" * 70)

    llm = build_llm_client()
    brain_wf = build_brain_workflow(llm)

    if settings.AGENT_PROTOCOL_ONLY:
        logger.info("🚦 AGENT_PROTOCOL_ONLY=true，启用 B↔C Agent 协议模式（跳过 OCR 决策链）")
        runtime = None
        try:
            d = U2Driver.connect()
            runtime = build_runtime(d)
            logger.info("✅ 设备已连接（作为执行层 sidecar）")
        except Exception as e:
            logger.warning(f"⚠️ 协议模式下设备不可用，继续无 UI sidecar 运行: {e}")

        _a2a_client = build_a2a_client(brain_wf, runtime) if runtime else None
        if not _a2a_client:
            logger.error("❌ A2ABoxClient 未启动，协议模式无法继续")
            return

        logger.info("🤝 B 端 Agent 已就绪，等待 C 端 Agent 协议请求...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("👋 协议模式停止")
        return

    # --- OCR ---
    if not init_ocr():
        logger.error("❌ OCR 初始化失败，退出")
        return

    # --- 设备 ---
    try:
        d = U2Driver.connect()
        logger.info("✅ 设备已连接")
    except Exception as e:
        logger.error(f"❌ 设备连接失败: {e}")
        return

    # --- 装配阶段 ---
    llm = build_llm_client()
    store = build_store_manager()
    agent_wf = build_agent_workflow()
    brain_wf = build_brain_workflow(llm)

    # --- 回复引擎（三级降级）---
    engine = ReplyEngine(
        llm=llm,
        agent_workflow=agent_wf,
        brain_workflow=brain_wf,
        system_prompt=settings.SYSTEM_PROMPT,
    )

    match_room = build_match_room(llm)

    # --- 核心组件 ---
    feishu = FeishuSync()
    dedup, bubble, extractor = build_message_pipeline()
    runtime = build_runtime(d)
    _a2a_client = build_a2a_client(brain_wf, runtime)
    session_mgr = build_session_manager()
    monitor = build_monitor()

    stats = {
        "total": 0, "replied": 0, "webhook": 0, "table": 0,
        "failed": 0, "duplicated": 0, "no_new": 0,
        "level1": 0, "level2": 0, "level3": 0,
    }
    ocr_fails = 0

    logger.info(f"📱 屏幕: {runtime.geometry.width}x{runtime.geometry.height}")
    logger.info("👁️ 开始监听消息...")

    # ==================== 主循环 ====================
    while True:
        try:
            # 0. 心跳（看门狗心跳）
            monitor.heartbeat()

            # 1. 截图
            runtime.driver.screenshot("current_screen.png")
            img = cv2.imread("current_screen.png")
            if img is None:
                time.sleep(settings.POLL_INTERVAL_ERROR)
                continue

            # 2. 裁剪
            crop = img[runtime.geometry.crop_top:runtime.geometry.crop_bottom, runtime.geometry.crop_left:runtime.geometry.crop_right]
            cv2.imwrite("chat_crop.png", crop)

            # 3. OCR
            try:
                ocr_results = reader.readtext("chat_crop.png", detail=1)
                ocr_fails = 0
            except Exception as e:
                ocr_fails += 1
                logger.warning(f"⚠️ OCR 异常 ({ocr_fails}): {e}")
                if ocr_fails >= settings.OCR_FAIL_MAX_RETRIES:
                    init_ocr()
                    ocr_fails = 0
                time.sleep(settings.POLL_INTERVAL_ERROR)
                continue

            # 4. 提取消息
            chat_msg = extractor.extract(
                ocr_results, runtime.geometry.crop_left, runtime.geometry.crop_top, img, bubble
            )
            if not chat_msg:
                stats["no_new"] += 1
                time.sleep(settings.POLL_INTERVAL_NO_MSG)
                continue

            # 5. 去重
            if dedup.is_dup(chat_msg):
                stats["duplicated"] += 1
                time.sleep(settings.POLL_INTERVAL_DUPLICATE)
                continue

            dedup.add(chat_msg)
            logger.info(f"🎯 新消息: {chat_msg}")
            stats["total"] += 1

            # 6. LocalMemory 注入上下文（增强 AgentWorkflow 的 RAG 精度）
            if store and store.is_ready:
                try:
                    mem_result = store.query_business_rules(chat_msg)
                    mem_ctx    = mem_result.to_context()
                    logger.debug(f"[Memory] {mem_ctx[:60]}")
                except Exception:
                    mem_ctx = ""
            else:
                mem_ctx = ""

            # 7. 三级回复引擎
            reply = engine.generate(chat_msg)

            # 若 AgentWorkflow 未能回答且有 LocalMemory 上下文，追加一次 LLM
            if not reply and mem_ctx:
                system = (
                    f"{settings.SYSTEM_PROMPT}\n"
                    f"参考本地业务信息回复顾客：\n{mem_ctx}"
                )
                reply = llm.ask(chat_msg, system=system) or ""

            if not reply:
                logger.warning("⚠️ 所有引擎均无回复，跳过")
                stats["failed"] += 1
                time.sleep(settings.POLL_INTERVAL_MAIN)
                continue

            logger.info(f"🤖 龙虾回复: {reply}")

            # 8. 发送（含 UI 校验）
            sent_ok = runtime.verifier.send_with_verify(runtime.geometry.input_x, runtime.geometry.input_y, reply)
            if sent_ok:
                stats["replied"] += 1
                dedup.add(reply)
                feishu.sync_async(chat_msg, reply, stats)
                # 将对话写入 session（用于多轮上下文）
                try:
                    sess = session_mgr.get_or_create("wechat_user")
                    sess.add(chat_msg, reply, intent="chat")
                except Exception:
                    pass
            else:
                stats["failed"] += 1

            # 9. 定期统计
            if stats["total"] % settings.STATS_REPORT_INTERVAL == 0:
                logger.info(
                    f"📊 统计 | 总:{stats['total']} 回复:{stats['replied']} "
                    f"L1:{stats['level1']} L2:{stats['level2']} L3:{stats['level3']} "
                    f"群:{stats['webhook']} 表格:{stats['table']} "
                    f"失败:{stats['failed']} 重复:{stats['duplicated']}"
                )

        except KeyboardInterrupt:
            logger.info("👋 程序停止")
            if match_room:
                s = match_room.stats()
                logger.info(
                    f"🏆 匹配统计 | 总:{s['total']} "
                    f"成功:{s['matched']} 失败:{s['rejected']} "
                    f"均耗时:{s['avg_duration']:.1f}s"
                )
            break
        except OSError as e:
            # 设备断连自愈
            logger.error(f"❌ 设备断连: {e}")
            monitor.mark_device_ok(False)
            new_d = monitor.reconnect_device()
            if new_d:
                d = new_d
                runtime.update_driver(new_d)
                monitor.mark_device_ok(True)
            else:
                time.sleep(10)
        except Exception as e:
            logger.error(f"❌ 主循环异常: {e}")
            time.sleep(settings.POLL_INTERVAL_ERROR)

        time.sleep(settings.POLL_INTERVAL_MAIN)


if __name__ == "__main__":
    main()
