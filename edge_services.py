from __future__ import annotations

import asyncio
import threading
import time
from datetime import datetime
from typing import Optional

import requests

from agent_workflow import run_async as run_agent_async
from business_brain import run_brain
from config import settings
from llm_client import LLMClient
from logger_setup import setup_logger

logger = setup_logger("claw.services")


class FeishuSync:
    def __init__(self):
        self.token = ""
        self.expire = 0
        self._refresh()

    def _refresh(self):
        try:
            r = requests.post(
                settings.FEISHU_AUTH_URL,
                json={"app_id": settings.FEISHU_APP_ID, "app_secret": settings.FEISHU_APP_SECRET},
                timeout=settings.FEISHU_TOKEN_TIMEOUT,
            )
            d = r.json()
            if d.get("code") == 0:
                self.token = d["tenant_access_token"]
                self.expire = time.time() + d.get("expire", 7200) - 60
                logger.info("✅ 飞书 Token 刷新成功")
        except Exception as e:
            logger.error(f"❌ 飞书 Token 刷新失败: {e}")

    def _ensure(self):
        if not self.token or time.time() > self.expire:
            self._refresh()

    def webhook(self, user_msg: str, reply: str) -> bool:
        try:
            payload = {
                "msg_type": "interactive",
                "card": {
                    "config": {"wide_screen_mode": True},
                    "elements": [
                        {"tag": "div", "text": {"tag": "lark_md", "content": f"**👤 用户:**\n{user_msg}"}},
                        {"tag": "div", "text": {"tag": "lark_md", "content": f"**🤖 龙虾:**\n{reply}"}},
                        {"tag": "div", "text": {"tag": "lark_md", "content": f"⏰ {datetime.now().strftime('%H:%M:%S')}"}},
                    ],
                },
            }
            r = requests.post(settings.FEISHU_BOT_WEBHOOK, json=payload, timeout=settings.FEISHU_TOKEN_TIMEOUT)
            return r.json().get("code") == 0
        except Exception as e:
            logger.error(f"❌ Webhook 失败: {e}")
            return False

    def table(self, user_msg: str, reply: str) -> bool:
        self._ensure()
        if not self.token:
            return False
        try:
            url = (
                f"{settings.FEISHU_BITABLE_URL}/"
                f"{settings.FEISHU_APP_TOKEN}/tables/"
                f"{settings.FEISHU_TABLE_ID}/records"
            )
            r = requests.post(
                url,
                headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
                json={
                    "fields": {
                        "用户消息 / User": user_msg,
                        "龙虾回复 / Assistant": reply,
                        "场景分类": "点单接单",
                        "处理状态": "待清洗",
                    }
                },
                timeout=settings.FEISHU_TOKEN_TIMEOUT,
            )
            return r.json().get("code") == 0
        except Exception as e:
            logger.error(f"❌ 表格写入失败: {e}")
            return False

    def sync_async(self, user_msg: str, reply: str, stats: dict):
        def _work():
            if self.webhook(user_msg, reply):
                stats["webhook"] += 1
                logger.info("☁️ 飞书群同步成功")
            if self.table(user_msg, reply):
                stats["table"] += 1
                logger.info("📊 多维表格同步成功")

        threading.Thread(target=_work, daemon=True).start()


class ReplyEngine:
    def __init__(
        self,
        llm: LLMClient,
        agent_workflow: Optional[object] = None,
        brain_workflow: Optional[object] = None,
        system_prompt: str = "",
    ):
        self.llm = llm
        self.agent_workflow = agent_workflow
        self.brain_workflow = brain_workflow
        self.system_prompt = system_prompt
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(target=self._loop.run_forever, daemon=True, name="ReplyEngineLoop")
        self._loop_thread.start()
        logger.info("✅ ReplyEngine 就绪（3级降级）")

    def generate(self, user_msg: str) -> str:
        if self.agent_workflow:
            try:
                future = asyncio.run_coroutine_threadsafe(run_agent_async(self.agent_workflow, user_msg), self._loop)
                reply = future.result(timeout=20)
                if reply:
                    logger.info("[ReplyEngine] Level1 AgentWorkflow ✅")
                    return reply
            except Exception as e:
                logger.warning(f"[ReplyEngine] Level1 失败，降级: {e}")

        if self.brain_workflow:
            try:
                reply = run_brain(self.brain_workflow, user_msg)
                if reply:
                    logger.info("[ReplyEngine] Level2 BusinessBrain ✅")
                    return reply
            except Exception as e:
                logger.warning(f"[ReplyEngine] Level2 失败，降级: {e}")

        try:
            reply = self.llm.ask(user_msg, system=self.system_prompt) or ""
            if reply:
                logger.info("[ReplyEngine] Level3 直接LLM ✅")
            return reply
        except Exception as e:
            logger.error(f"[ReplyEngine] Level3 也失败: {e}")
            return ""
