"""
Project Claw v13.0 - match_engine.py
商家-客户匿名对话撮合引擎

设计：
  商家端（龙虾盒子）捕获到潜在客户信号后，
  系统在云端拉起一个「匿名沙盒」：
    - MerchantAgent：代表商家，掌握菜单/价格/活动
    - CustomerAgent：代表客户，基于历史问题模拟偏好
  双方进行 N 轮对话，Evaluator 评分后：
    - 匹配度 >= 阈值 → 推送真实联系方式给双方
    - 匹配度 <  阈值 → 静默丢弃，双方无感知

扩展点：
  - 接入 OpenClaw P2P 协议实现跨设备真实通信
  - 替换 CustomerAgent 为真实客户小程序 WebSocket
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Callable

from llm_client import LLMClient

logger = logging.getLogger("claw.match")


# ==================== 数据结构 ====================

class MatchStatus(str, Enum):
    PENDING  = "pending"
    RUNNING  = "running"
    MATCHED  = "matched"
    REJECTED = "rejected"
    ERROR    = "error"


@dataclass
class MatchTurn:
    round:     int
    merchant:  str
    customer:  str
    timestamp: float = field(default_factory=time.time)


@dataclass
class MatchResult:
    session_id:   str
    status:       MatchStatus
    score:        float          # 0-100
    turns:        List[MatchTurn]
    merchant_id:  str
    customer_id:  str
    summary:      str            # Evaluator 总结
    duration:     float          # 耗时秒
    created_at:   float = field(default_factory=time.time)

    @property
    def is_match(self) -> bool:
        return self.status == MatchStatus.MATCHED

    def to_dict(self) -> dict:
        return {
            "session_id":  self.session_id,
            "status":      self.status.value,
            "score":       round(self.score, 1),
            "matched":     self.is_match,
            "merchant_id": self.merchant_id,
            "customer_id": self.customer_id,
            "summary":     self.summary,
            "duration":    round(self.duration, 2),
            "rounds":      len(self.turns),
        }


# ==================== Agent 提示词 ====================

MERCHANT_SYSTEM = """\
你是一家餐厅的智能销售助手。
你的任务是通过对话了解顾客需求，推荐合适的菜品和套餐。
你掌握以下信息：
{menu_context}

规则：
- 简短热情，不超过50字
- 主动挖掘顾客预算、口味偏好、用餐人数
- 不要捏造价格，只介绍上面列出的菜品
- 在第3轮后尝试促成预约
"""

CUSTOMER_SYSTEM = """\
你是一个真实的顾客，正在考虑去附近的一家餐厅用餐。
背景：{customer_profile}

规则：
- 用自然的口语表达，不超过40字
- 会关心价格、口味、环境
- 适当问问题，不要太主动
- 如果觉得合适，第4-5轮可以表示有兴趣
"""

EVALUATOR_SYSTEM = """\
你是一个专业的餐饮撮合评估师。
请分析以下商家与顾客的对话，给出撮合评分（0-100）。

评分维度：
1. 需求匹配度（顾客需求与商家产品的匹配程度）
2. 价格接受度（顾客对价格区间的接受程度）  
3. 意向强度（顾客表现出的用餐意愿）
4. 对话质量（沟通是否顺畅、信息是否充分）

必须严格按 JSON 格式输出：
{"score": 85, "summary": "顾客对价格和菜品均感兴趣，有明确用餐意向", "dimensions": {"need_match": 90, "price_ok": 80, "intent": 85, "quality": 85}}
"""


# ==================== Agent ====================

class MerchantAgent:
    def __init__(self, llm: LLMClient, menu_context: str):
        self.llm     = llm
        self.system  = MERCHANT_SYSTEM.format(menu_context=menu_context)
        self.history: List[dict] = []

    async def respond(self, customer_msg: str) -> str:
        self.history.append({"role": "user", "content": customer_msg})
        msgs = [{"role": "system", "content": self.system}] + self.history[-8:]
        reply = await asyncio.to_thread(self.llm.ask_messages, msgs)
        reply = reply or "欢迎光临，有什么可以帮您？"
        self.history.append({"role": "assistant", "content": reply})
        return reply


class CustomerAgent:
    def __init__(self, llm: LLMClient, profile: str):
        self.llm     = llm
        self.system  = CUSTOMER_SYSTEM.format(customer_profile=profile)
        self.history: List[dict] = []

    async def respond(self, merchant_msg: str) -> str:
        self.history.append({"role": "user", "content": merchant_msg})
        msgs = [{"role": "system", "content": self.system}] + self.history[-8:]
        reply = await asyncio.to_thread(self.llm.ask_messages, msgs)
        reply = reply or "嗯，我看看吧。"
        self.history.append({"role": "assistant", "content": reply})
        return reply


class EvaluatorAgent:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def evaluate(self, turns: List[MatchTurn]) -> tuple[float, str]:
        dialogue = "\n".join(
            f"[第{t.round}轮] 商家: {t.merchant}\n[第{t.round}轮] 顾客: {t.customer}"
            for t in turns
        )
        msgs = [
            {"role": "system", "content": EVALUATOR_SYSTEM},
            {"role": "user",   "content": f"以下是对话记录：\n\n{dialogue}"},
        ]
        try:
            raw = await asyncio.to_thread(self.llm.ask_messages, msgs)
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()
            data = json.loads(raw)
            score   = float(data.get("score", 0))
            summary = data.get("summary", "")
            return score, summary
        except Exception as e:
            logger.error(f"[Evaluator] 评分失败: {e}")
            return 0.0, "评估失败"


# ==================== 撮合引擎 ====================

class MatchSession:
    """单次撮合会话"""

    def __init__(
        self,
        session_id:   str,
        merchant_id:  str,
        customer_id:  str,
        merchant_agent: MerchantAgent,
        customer_agent: CustomerAgent,
        evaluator:    EvaluatorAgent,
        max_rounds:   int   = 5,
        threshold:    float = 75.0,
    ):
        self.session_id     = session_id
        self.merchant_id    = merchant_id
        self.customer_id    = customer_id
        self.merchant_agent = merchant_agent
        self.customer_agent = customer_agent
        self.evaluator      = evaluator
        self.max_rounds     = max_rounds
        self.threshold      = threshold
        self.turns: List[MatchTurn] = []

    async def run(self) -> MatchResult:
        start = time.time()
        logger.info(f"[Match {self.session_id}] 开始撮合 {self.merchant_id} <-> {self.customer_id}")

        # 客户先开口
        customer_msg = "你好，请问你们有什么特色菜？"

        for rnd in range(1, self.max_rounds + 1):
            try:
                merchant_reply = await self.merchant_agent.respond(customer_msg)
                customer_msg   = await self.customer_agent.respond(merchant_reply)
                self.turns.append(MatchTurn(
                    round=rnd,
                    merchant=merchant_reply,
                    customer=customer_msg,
                ))
                logger.debug(f"[Match {self.session_id}] 第{rnd}轮完成")
            except Exception as e:
                logger.error(f"[Match {self.session_id}] 第{rnd}轮异常: {e}")
                break

        # 评分
        score, summary = await self.evaluator.evaluate(self.turns)
        status = MatchStatus.MATCHED if score >= self.threshold else MatchStatus.REJECTED
        duration = time.time() - start

        logger.info(
            f"[Match {self.session_id}] {'✅ 匹配成功' if status == MatchStatus.MATCHED else '❌ 未达标'} "
            f"score={score:.1f} duration={duration:.1f}s"
        )

        return MatchResult(
            session_id=self.session_id,
            status=status,
            score=score,
            turns=self.turns,
            merchant_id=self.merchant_id,
            customer_id=self.customer_id,
            summary=summary,
            duration=duration,
        )


class MatchEngine:
    """
    撮合引擎管理器

    用法：
        engine = MatchEngine(llm, menu_context)
        result = await engine.match(merchant_id, customer_id, customer_profile)
        if result.is_match:
            notify(result)
    """

    def __init__(
        self,
        llm:           LLMClient,
        menu_context:  str   = "",
        max_rounds:    int   = 5,
        threshold:     float = 75.0,
        on_match:      Optional[Callable[[MatchResult], None]] = None,
        on_reject:     Optional[Callable[[MatchResult], None]] = None,
    ):
        self.llm          = llm
        self.menu_context = menu_context
        self.max_rounds   = max_rounds
        self.threshold    = threshold
        self.on_match     = on_match
        self.on_reject    = on_reject
        self._results: Dict[str, MatchResult] = {}
        self._evaluator   = EvaluatorAgent(llm)

    async def match(
        self,
        merchant_id:      str,
        customer_id:      str,
        customer_profile: str = "普通顾客，喜欢性价比高的餐厅",
    ) -> MatchResult:
        session_id = str(uuid.uuid4())[:8]
        session = MatchSession(
            session_id=session_id,
            merchant_id=merchant_id,
            customer_id=customer_id,
            merchant_agent=MerchantAgent(self.llm, self.menu_context),
            customer_agent=CustomerAgent(self.llm, customer_profile),
            evaluator=self._evaluator,
            max_rounds=self.max_rounds,
            threshold=self.threshold,
        )
        result = await session.run()
        self._results[session_id] = result

        if result.is_match and self.on_match:
            try:
                self.on_match(result)
            except Exception as e:
                logger.error(f"[MatchEngine] on_match 回调失败: {e}")
        elif not result.is_match and self.on_reject:
            try:
                self.on_reject(result)
            except Exception as e:
                logger.error(f"[MatchEngine] on_reject 回调失败: {e}")

        return result

    def match_async_fire(
        self,
        merchant_id:      str,
        customer_id:      str,
        customer_profile: str = "普通顾客",
    ) -> str:
        """后台异步触发撮合，立即返回 session_id"""
        session_id = str(uuid.uuid4())[:8]

        async def _run():
            result = await self.match(merchant_id, customer_id, customer_profile)
            return result

        def _thread():
            asyncio.run(_run())

        import threading
        threading.Thread(target=_thread, daemon=True, name=f"Match-{session_id}").start()
        return session_id

    def get_result(self, session_id: str) -> Optional[MatchResult]:
        return self._results.get(session_id)

    def stats(self) -> dict:
        results = list(self._results.values())
        matched  = [r for r in results if r.is_match]
        rejected = [r for r in results if not r.is_match]
        avg_score = sum(r.score for r in results) / len(results) if results else 0
        avg_dur   = sum(r.duration for r in results) / len(results) if results else 0
        return {
            "total":     len(results),
            "matched":   len(matched),
            "rejected":  len(rejected),
            "match_rate": f"{len(matched)/len(results)*100:.1f}%" if results else "0%",
            "avg_score": round(avg_score, 1),
            "avg_duration": round(avg_dur, 1),
        }
