"""
Project Claw - 多智能体核心模块
包含：数据模型、基础 Agent 类、BossAgent、InventoryAgent、EvaluatorAgent
"""
import json
import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from llm_client import LLMClient

logger = logging.getLogger(__name__)


# ==================== 数据模型 ====================

@dataclass
class InventoryItem:
    name: str
    quantity: int
    cost: float
    price: float
    available: bool = True

    @property
    def margin(self) -> float:
        return (self.price - self.cost) / self.price if self.price else 0


@dataclass
class UserProfile:
    user_id: str
    name: str
    consumption_values: Dict[str, float] = field(default_factory=dict)
    love_values: Dict[str, float] = field(default_factory=dict)
    preferences: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


@dataclass
class MatchingResult:
    user1_id: str
    user2_id: str
    compatibility_score: float
    consumption_match: float
    love_match: float
    debate_rounds: int
    evaluator_feedback: str
    timestamp: float = field(default_factory=time.time)

    @property
    def is_match(self) -> bool:
        return self.compatibility_score >= 90.0


# ==================== 状态定义 ====================

class ConversationState(dict):
    """对话状态（可扩展的字典）"""
    def __init__(
        self,
        user_message: str = "",
        user_id: str = "",
        boss_thought: str = "",
        inventory_query: Optional[str] = None,
        inventory_result: Dict = None,
        final_reply: str = "",
        timestamp: float = None,
    ):
        super().__init__()
        self["user_message"] = user_message
        self["user_id"] = user_id
        self["boss_thought"] = boss_thought
        self["inventory_query"] = inventory_query
        self["inventory_result"] = inventory_result or {}
        self["final_reply"] = final_reply
        self["timestamp"] = timestamp or time.time()


class MatchingState(dict):
    """匹配状态"""
    def __init__(
        self,
        user1_id: str = "",
        user2_id: str = "",
        user1_profile: UserProfile = None,
        user2_profile: UserProfile = None,
        debate_history: List[Dict] = None,
        round_count: int = 0,
        evaluator_score: float = 0.0,
        matching_result: Optional[MatchingResult] = None,
    ):
        super().__init__()
        self["user1_id"] = user1_id
        self["user2_id"] = user2_id
        self["user1_profile"] = user1_profile
        self["user2_profile"] = user2_profile
        self["debate_history"] = debate_history or []
        self["round_count"] = round_count
        self["evaluator_score"] = evaluator_score
        self["matching_result"] = matching_result


# ==================== 基础 Agent ====================

class BaseAgent(ABC):
    def __init__(self, name: str, llm: LLMClient):
        self.name = name
        self.llm = llm
        self.logger = logging.getLogger(f"Agent.{name}")

    def _log(self, level: str, msg: str):
        getattr(self.logger, level)(f"[{self.name}] {msg}")

    @abstractmethod
    def process(self, state: dict) -> dict:
        pass


# ==================== B 端对话 Agents ====================

class BossAgent(BaseAgent):
    """前厅智能体：理解用户意图，决定是否需要查库存"""

    def __init__(self, llm: LLMClient, system_prompt: str = None):
        super().__init__("BossAgent", llm)
        self.system_prompt = system_prompt or "你是一个热情的餐厅老板的前厅，叫人'兄弟'，语气接地气。"

    def process(self, state: dict) -> dict:
        user_message = state["user_message"]
        self._log("info", f"接收: {user_message}")

        prompt = f"""用户说：{user_message}

请分析：
1. 用户的真实需求
2. 是否涉及菜品/库存（需要查后厨）
3. 如果需要查，生成查询词

返回 JSON：
{{"needs_inventory_check": true/false, "query": "查询词或空字符串", "thought": "分析思路"}}"""

        result = self.llm.ask_json(prompt, system=self.system_prompt)
        if result:
            state["boss_thought"] = result.get("thought", "")
            if result.get("needs_inventory_check"):
                state["inventory_query"] = result.get("query", "")
            self._log("info", f"意图: {state['boss_thought']}")
        else:
            state["boss_thought"] = user_message

        return state


class InventoryAgent(BaseAgent):
    """后厨智能体：查询库存、判断是否可做"""

    def __init__(self, llm: LLMClient, inventory: Dict[str, InventoryItem] = None):
        super().__init__("InventoryAgent", llm)
        self.inventory = inventory or self._default_inventory()

    def _default_inventory(self) -> Dict[str, InventoryItem]:
        return {
            "牛肉面": InventoryItem("牛肉面", 10, 8.5, 18.0),
            "麻辣烫": InventoryItem("麻辣烫", 15, 6.0, 15.0),
            "水饺": InventoryItem("水饺", 20, 3.0, 8.0),
            "葱": InventoryItem("葱", 5, 0.5, 1.0),
            "香菜": InventoryItem("香菜", 8, 0.8, 1.5),
            "猪肉": InventoryItem("猪肉", 12, 15.0, 30.0),
            "鸡蛋": InventoryItem("鸡蛋", 30, 0.8, 2.0),
        }

    def process(self, state: dict) -> dict:
        query = state.get("inventory_query")
        if not query:
            state["inventory_result"] = {}
            return state

        self._log("info", f"查询: {query}")
        found = {}
        for name, item in self.inventory.items():
            if name in query:
                found = {
                    "item_name": name,
                    "available": item.available and item.quantity > 0,
                    "quantity": item.quantity,
                    "price": item.price,
                    "margin": round(item.margin, 2),
                }
                break

        state["inventory_result"] = found
        self._log("info", f"结果: {found}")
        return state

    def update(self, item_name: str, delta: int):
        if item_name in self.inventory:
            self.inventory[item_name].quantity += delta
            self._log("info", f"库存更新 {item_name}: {delta:+d}")

    def load_from_excel(self, path: str):
        """从 Excel 加载库存（生产环境使用）"""
        try:
            import pandas as pd
            df = pd.read_excel(path)
            for _, row in df.iterrows():
                name = str(row.get("名称", ""))
                if name:
                    self.inventory[name] = InventoryItem(
                        name=name,
                        quantity=int(row.get("库存", 0)),
                        cost=float(row.get("成本", 0)),
                        price=float(row.get("售价", 0)),
                        available=bool(row.get("可用", True)),
                    )
            self._log("info", f"从 Excel 加载 {len(self.inventory)} 条库存")
        except Exception as e:
            self._log("error", f"Excel 加载失败: {e}")


class BossReplyAgent(BaseAgent):
    """前厅回复智能体：根据库存结果生成最终回复"""

    def __init__(self, llm: LLMClient, system_prompt: str = None):
        super().__init__("BossReplyAgent", llm)
        self.system_prompt = system_prompt or "你是一个热情的餐厅老板，叫人'兄弟'，回复简短接地气，不超过30字。"

    def process(self, state: dict) -> dict:
        user_message = state["user_message"]
        inv = state.get("inventory_result", {})

        if inv.get("available"):
            ctx = f"库存充足（{inv['quantity']} 份），可以做。"
        elif inv:
            ctx = f"库存不足或没有此菜，建议替代方案。"
        else:
            ctx = ""

        prompt = f"用户问：{user_message}\n{ctx}\n请回复："
        reply = self.llm.ask(prompt, system=self.system_prompt)
        state["final_reply"] = reply or "兄弟，稍等，问问后厨！"
        self._log("info", f"回复: {state['final_reply']}")
        return state


# ==================== C 端匹配 Agents ====================

CONSUMPTION_TOPICS = [
    "你觉得一顿饭花多少钱算合理？",
    "买东西你更看重品质还是价格？",
]
LOVE_TOPICS = [
    "你觉得恋爱中最重要的是什么？",
    "你能接受异地恋吗？",
]
LIFE_TOPICS = [
    "工作日你几点睡觉？",
]
ALL_TOPICS = CONSUMPTION_TOPICS + LOVE_TOPICS + LIFE_TOPICS


class DebateAgent(BaseAgent):
    """辩论智能体：模拟两个用户就三观话题展开 5 轮辩论"""

    def __init__(self, llm: LLMClient, max_rounds: int = 5):
        super().__init__("DebateAgent", llm)
        self.max_rounds = max_rounds
        self.topics = ALL_TOPICS

    def run_single_round(self, state: dict) -> dict:
        """执行一轮辩论"""
        rnd = state["round_count"]
        if rnd >= self.max_rounds:
            return state

        topic = self.topics[rnd % len(self.topics)]
        u1 = state["user1_profile"]
        u2 = state["user2_profile"]
        self._log("info", f"Round {rnd+1}: {topic}")

        sys1 = f"你是 {u1.name}，请用一句话（不超过15字）回答："
        sys2 = f"你是 {u2.name}，请用一句话（不超过15字）回答："

        v1 = self.llm.ask(topic, system=sys1) or "我觉得都行"
        v2 = self.llm.ask(topic, system=sys2) or "看情况吧"

        state["debate_history"].append({
            "round": rnd + 1,
            "topic": topic,
            "user1": v1,
            "user2": v2,
        })
        state["round_count"] += 1
        self._log("info", f"  {u1.name}: {v1} | {u2.name}: {v2}")
        return state

    def process(self, state: dict) -> dict:
        """执行所有轮次"""
        while state["round_count"] < self.max_rounds:
            state = self.run_single_round(state)
        return state


class EvaluatorAgent(BaseAgent):
    """裁判智能体：对辩论结果打分，>=90 则推送真人"""

    def __init__(self, llm: LLMClient, match_threshold: float = 90.0):
        super().__init__("EvaluatorAgent", llm)
        self.match_threshold = match_threshold

    def process(self, state: dict) -> dict:
        history = state["debate_history"]
        u1 = state["user1_profile"]
        u2 = state["user2_profile"]

        if not history:
            state["evaluator_score"] = 0.0
            state["matching_result"] = None
            return state

        debate_text = "\n".join(
            f"Round {d['round']} [{d['topic']}]\n  {u1.name}: {d['user1']}\n  {u2.name}: {d['user2']}"
            for d in history
        )

        prompt = f"""请评估以下两人的三观匹配度：

{debate_text}

返回 JSON：
{{"consumption_match": 0-100, "love_match": 0-100, "overall_score": 0-100, "feedback": "简短评语"}}"""

        result = self.llm.ask_json(prompt)
        if not result:
            result = {"consumption_match": 50, "love_match": 50, "overall_score": 50, "feedback": "数据不足"}

        score = float(result.get("overall_score", 0))
        state["evaluator_score"] = score
        state["matching_result"] = MatchingResult(
            user1_id=state["user1_id"],
            user2_id=state["user2_id"],
            compatibility_score=score,
            consumption_match=float(result.get("consumption_match", 0)),
            love_match=float(result.get("love_match", 0)),
            debate_rounds=len(history),
            evaluator_feedback=result.get("feedback", ""),
        )

        self._log(
            "info",
            f"匹配分: {score:.1f}% | {'✅ 推送真人' if score >= self.match_threshold else '❌ 未达标'}",
        )
        return state
