"""
Project Claw - LangGraph 工作流编排

B 端工作流：BossAgent -> InventoryAgent -> BossReplyAgent
C 端工作流：DebateAgent (5 rounds) -> EvaluatorAgent

设计原则：
- 每个节点是纯函数式调用，状态不可变地传递
- 预留 OpenClaw Desktop / 更多节点的扩展接口
"""
import logging
import time
from typing import Optional
from langgraph.graph import StateGraph, END

from llm_client import LLMClient
from multi_agent_core import (
    ConversationState,
    MatchingState,
    UserProfile,
    MatchingResult,
    BossAgent,
    InventoryAgent,
    BossReplyAgent,
    DebateAgent,
    EvaluatorAgent,
)

logger = logging.getLogger(__name__)


# ==================== B 端：对话工作流 ====================

def build_conversation_workflow(
    llm: LLMClient,
    system_prompt: str = None,
    inventory_excel: str = None,
) -> "CompiledGraph":
    """
    构建 B 端对话工作流

    流程：
    [START] -> boss_understand -> inventory_check -> boss_reply -> [END]

    扩展点：
    - 可在 inventory_check 后插入 ERPSyncAgent（OpenClaw Desktop）
    - 可在 boss_reply 后插入 SentimentAgent（情绪检测）
    """
    boss = BossAgent(llm, system_prompt=system_prompt)
    inventory = InventoryAgent(llm)
    reply = BossReplyAgent(llm, system_prompt=system_prompt)

    if inventory_excel:
        inventory.load_from_excel(inventory_excel)

    def node_boss_understand(state: dict) -> dict:
        return boss.process(state)

    def node_inventory_check(state: dict) -> dict:
        # 只有需要查库存时才进入
        if state.get("inventory_query"):
            return inventory.process(state)
        return state

    def node_boss_reply(state: dict) -> dict:
        return reply.process(state)

    def should_check_inventory(state: dict) -> str:
        """条件分支：是否需要查库存"""
        if state.get("inventory_query"):
            return "inventory_check"
        return "boss_reply"

    graph = StateGraph(dict)
    graph.add_node("boss_understand", node_boss_understand)
    graph.add_node("inventory_check", node_inventory_check)
    graph.add_node("boss_reply", node_boss_reply)

    graph.set_entry_point("boss_understand")
    graph.add_conditional_edges(
        "boss_understand",
        should_check_inventory,
        {
            "inventory_check": "inventory_check",
            "boss_reply": "boss_reply",
        },
    )
    graph.add_edge("inventory_check", "boss_reply")
    graph.add_edge("boss_reply", END)

    return graph.compile()


def run_conversation(
    workflow,
    user_message: str,
    user_id: str = "anonymous",
) -> str:
    """
    执行 B 端对话工作流，返回最终回复
    """
    state = ConversationState(
        user_message=user_message,
        user_id=user_id,
    )
    t0 = time.time()
    try:
        result = workflow.invoke(dict(state))
        elapsed = time.time() - t0
        logger.info(f"对话工作流完成 ({elapsed:.2f}s): {result.get('final_reply', '')}")
        return result.get("final_reply", "")
    except Exception as e:
        logger.error(f"对话工作流失败: {e}")
        return ""


# ==================== C 端：匹配工作流 ====================

def build_matching_workflow(
    llm: LLMClient,
    max_rounds: int = 5,
    match_threshold: float = 90.0,
) -> "CompiledGraph":
    """
    构建 C 端匹配工作流

    流程：
    [START] -> debate_loop (x5) -> evaluator -> [END]

    扩展点：
    - 可在 evaluator 后插入 NotificationAgent（弹窗通知）
    - 可在 debate_loop 中插入更多话题维度
    - 后期可接入 OpenClaw P2P 协议做跨设备匹配
    """
    debater = DebateAgent(llm, max_rounds=max_rounds)
    evaluator = EvaluatorAgent(llm, match_threshold=match_threshold)

    def node_debate(state: dict) -> dict:
        return debater.process(state)

    def node_evaluate(state: dict) -> dict:
        return evaluator.process(state)

    graph = StateGraph(dict)
    graph.add_node("debate", node_debate)
    graph.add_node("evaluate", node_evaluate)

    graph.set_entry_point("debate")
    graph.add_edge("debate", "evaluate")
    graph.add_edge("evaluate", END)

    return graph.compile()


def run_matching(
    workflow,
    user1_id: str,
    user2_id: str,
    user1_name: str = None,
    user2_name: str = None,
) -> Optional[MatchingResult]:
    """
    执行 C 端匹配工作流，返回 MatchingResult 或 None
    """
    state = MatchingState(
        user1_id=user1_id,
        user2_id=user2_id,
        user1_profile=UserProfile(
            user_id=user1_id,
            name=user1_name or f"用户{user1_id[:4]}",
        ),
        user2_profile=UserProfile(
            user_id=user2_id,
            name=user2_name or f"用户{user2_id[:4]}",
        ),
    )
    t0 = time.time()
    try:
        result = workflow.invoke(dict(state))
        elapsed = time.time() - t0
        matching = result.get("matching_result")
        if matching:
            logger.info(
                f"匹配工作流完成 ({elapsed:.2f}s) | "
                f"分数: {matching.compatibility_score:.1f}% | "
                f"{'✅ 推送' if matching.is_match else '❌ 未达标'}"
            )
        return matching
    except Exception as e:
        logger.error(f"匹配工作流失败: {e}")
        return None
