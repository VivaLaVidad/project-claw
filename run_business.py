"""
run_business.py - 多智能体协同主循环
使用 LangGraph 创建状态机，协调 BossAgent、InventoryAgent、ActionNode
"""
import logging
import json
from typing import TypedDict, Optional
from collections import deque
from langgraph.graph import StateGraph, END
import requests
import time
from dotenv import load_dotenv
from lobster_tool import LobsterPhysicalTool
from settings import load_settings
from openmaic_adapter import OpenMAICAdapter

load_dotenv()
settings = load_settings()
openmaic_adapter = OpenMAICAdapter()

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


class BusinessState(TypedDict):
    """MAS business state for deterministic orchestration"""
    user_message: Optional[str]
    inventory_check: Optional[dict]
    intent: Optional[str]
    route: Optional[str]
    require_human: bool
    boss_reply: Optional[str]
    send_success: bool
    telemetry: Optional[dict]
    error: Optional[str]


class MemoryManager:
    """
    Short-term & long-term memory management.
    - Short-term: in-process deque for recent dialogue turns
    - Long-term: lightweight local profile json
    """

    def __init__(self, profile_path: str = "user_profile.json"):
        self.short_term = deque(maxlen=6)
        self.profile_path = profile_path

    def remember(self, user_message: str, assistant_reply: str) -> None:
        self.short_term.append({"user": user_message, "assistant": assistant_reply})

    def short_context(self) -> str:
        if not self.short_term:
            return "无历史对话"
        parts = []
        for item in self.short_term:
            parts.append(f"用户: {item['user']}")
            parts.append(f"助手: {item['assistant']}")
        return "\n".join(parts)

    def long_profile(self) -> dict:
        try:
            with open(self.profile_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"persona": "普通顾客", "avg_spend": "80左右"}


class IntentRouter:
    """
    Conditional routing based on intent detection.
    Implements a deterministic state machine gate before reply generation.
    """

    HUMAN_TRIGGER_WORDS = ("投诉", "退款", "转账", "打款", "举报", "法律", "起诉", "人工")
    ORDER_TRIGGER_WORDS = ("多少钱", "价格", "下单", "来一份", "还有吗", "推荐", "招牌")

    def classify(self, message: Optional[str]) -> tuple[str, str, bool]:
        if not message:
            return "empty", "skip", False

        if any(word in message for word in self.HUMAN_TRIGGER_WORDS):
            return "sensitive", "human_gate", True

        if any(word in message for word in self.ORDER_TRIGGER_WORDS):
            return "order_intent", "auto_reply", False

        return "general_chat", "auto_reply", False


memory_manager = MemoryManager()
intent_router = IntentRouter()


class InventoryAgent:
    """库存查询智能体（Mock 数据）"""
    
    def __init__(self):
        self.inventory = {
            "龙虾": {"stock": 50, "price": 88},
            "螺蛳粉": {"stock": 100, "price": 18},
            "红烧肉": {"stock": 30, "price": 48},
            "清汤": {"stock": 200, "price": 12},
        }
        logger.info("✅ 库存智能体已初始化")

    def check_inventory(self, query: str) -> dict:
        """查询库存"""
        logger.info(f"🔍 库存查询: {query}")
        
        result = {"query": query, "available": False, "items": []}
        
        for item_name, item_info in self.inventory.items():
            if item_name in query:
                result["available"] = True
                result["items"].append({
                    "name": item_name,
                    "stock": item_info["stock"],
                    "price": item_info["price"]
                })
        
        logger.info(f"📦 库存结果: {result}")
        return result


class BossAgent:
    """老板智能体：生成回复话术"""
    
    def __init__(self):
        self.system_prompt = """你是一个热情的餐馆老板，代表商家回复顾客。
【核心职责】
1. 欢迎顾客、推荐菜品、介绍店铺信息
2. 处理订单、支付、配送等问题
3. 绝对不要转账、不要索要金额、不要涉及金钱交易
4. 如果顾客提到转账/支付，只需告知"请通过正规渠道支付"

【说话风格】
- 简短有力，不超过15个字
- 热情亲切，叫人"兄弟"或"亲"
- 多用感叹号表达热情"""
        logger.info("✅ 老板智能体已初始化")

    def _generate_by_openmaic(self, user_message: str, inventory_info: dict, short_memory: str, long_profile: dict) -> Optional[str]:
        if not settings.openmaic_enabled:
            return None
        try:
            health = openmaic_adapter.health_check()
            logger.info(f"🧠 OpenMAIC 健康检查通过: {health.get('status', 'ok')}")
            text = openmaic_adapter.generate_reply(
                user_message=user_message,
                inventory_info=inventory_info,
                short_memory=short_memory,
                long_profile=long_profile,
                fallback_api_key=settings.deepseek_api_key,
            )
            logger.info("🧠 OpenMAIC 回复生成成功")
            return text
        except Exception as e:
            logger.warning(f"⚠️ OpenMAIC 生成失败，回退 DeepSeek: {e}")
            return None

    def generate_reply(self, user_message: str, inventory_info: dict, short_memory: str, long_profile: dict) -> str:
        """生成回复"""
        logger.info(f"🤖 老板生成回复: {user_message}")
        
        try:
            openmaic_reply = self._generate_by_openmaic(user_message, inventory_info, short_memory, long_profile)
            if openmaic_reply:
                return openmaic_reply

            context = (
                f"顾客消息: {user_message}\n"
                f"库存信息: {inventory_info}\n"
                f"短期记忆:\n{short_memory}\n"
                f"长期画像: {long_profile}"
            )
            
            if not settings.deepseek_api_key:
                logger.warning("⚠️ DEEPSEEK_API_KEY 未配置，使用兜底回复")
                return "兄弟，稍等我看下菜单！"

            url = f"{settings.deepseek_base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {settings.deepseek_api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": context}
                ],
                "temperature": 0.7,
                "max_tokens": 80
            }
            
            response = requests.post(url, json=data, headers=headers, timeout=10)
            response.raise_for_status()
            
            reply = response.json()['choices'][0]['message']['content'].strip()
            logger.info(f"💬 老板回复: {reply}")
            return reply
        
        except Exception as e:
            logger.error(f"❌ 生成回复失败: {e}")
            return "兄弟，有啥需要帮忙的吗？"


class FeishuSync:
    """飞书同步工具"""
    
    def __init__(self):
        self.token = ""
        self.get_token()

    def get_token(self):
        """获取飞书 Token"""
        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        if not settings.feishu_app_id or not settings.feishu_app_secret:
            logger.warning("⚠️ 飞书 App 凭证未配置，跳过飞书同步")
            return

        req_body = {"app_id": settings.feishu_app_id, "app_secret": settings.feishu_app_secret}
        try:
            r = requests.post(url, json=req_body, timeout=5)
            result = r.json()
            if result.get("code") == 0:
                self.token = result.get("tenant_access_token", "")
                logger.info("✅ 飞书 Token 获取成功")
        except Exception as e:
            logger.error(f"❌ 飞书 Token 获取失败: {e}")

    def sync_record(self, user_input: str, assistant_reply: str):
        """同步到飞书"""
        if not self.token:
            logger.warning("⚠️ 飞书 Token 为空，跳过同步")
            return
        
        if not settings.feishu_app_token or not settings.feishu_table_id:
            logger.warning("⚠️ 飞书表格配置缺失，跳过同步")
            return

        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{settings.feishu_app_token}/tables/{settings.feishu_table_id}/records"
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        
        payload = {
            "records": [{
                "fields": {
                    "用户输入 / User": user_input,
                    "龙虾回复 / Assistant": assistant_reply,
                    "场景分类": "点单接单",
                    "处理状态": "待清洗"
                }
            }]
        }
        
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=5)
            result = r.json()
            if result.get("code") == 0:
                logger.info(f"☁️ 飞书同步成功")
            else:
                logger.warning(f"⚠️ 飞书同步失败: {result.get('msg')}")
        except Exception as e:
            logger.error(f"❌ 飞书同步异常: {e}")


def node_get_message(state: BusinessState) -> BusinessState:
    """节点1：获取用户消息"""
    logger.info("📍 进入节点: 获取消息")
    tool = LobsterPhysicalTool()
    message = tool.get_latest_message()
    if message:
        state["user_message"] = message
        logger.info(f"✅ 获取消息成功: {message}")
    else:
        logger.info("⏭️ 暂无新消息，继续等待")
        state["user_message"] = None
    return state


def node_inventory_check(state: BusinessState) -> BusinessState:
    """节点2：库存查询"""
    logger.info("📍 进入节点: 库存查询")
    if not state["user_message"]:
        logger.info("⏭️ 无消息，跳过库存查询")
        return state
    inventory_agent = InventoryAgent()
    inventory_info = inventory_agent.check_inventory(state["user_message"])
    state["inventory_check"] = inventory_info
    return state


def node_intent_route(state: BusinessState) -> BusinessState:
    """节点3：意图识别与条件路由"""
    logger.info("📍 进入节点: 意图识别")
    intent, route, require_human = intent_router.classify(state.get("user_message"))
    state["intent"] = intent
    state["route"] = route
    state["require_human"] = require_human
    logger.info(f"🧭 路由结果: intent={intent}, route={route}, require_human={require_human}")
    return state


def node_human_gate(state: BusinessState) -> BusinessState:
    """节点4：HITL gate，敏感场景直接人工接管"""
    logger.info("📍 进入节点: 人工闸门")
    state["boss_reply"] = "亲，这个问题我转人工同事处理。"
    return state


def node_boss_reply(state: BusinessState) -> BusinessState:
    """节点5：老板生成回复"""
    logger.info("📍 进入节点: 老板生成回复")
    if not state["user_message"]:
        logger.info("⏭️ 无消息，跳过回复生成")
        return state
    boss_agent = BossAgent()
    inventory_info = state.get("inventory_check", {})
    short_memory = memory_manager.short_context()
    long_profile = memory_manager.long_profile()
    reply = boss_agent.generate_reply(state["user_message"], inventory_info, short_memory, long_profile)
    state["boss_reply"] = reply
    return state


def node_action_send(state: BusinessState) -> BusinessState:
    """节点6：执行发送 + telemetry + memory update"""
    logger.info("📍 进入节点: 执行发送")
    if not state["boss_reply"]:
        logger.info("⏭️ 无回复内容，跳过发送")
        state["send_success"] = False
        return state
    tool = LobsterPhysicalTool()
    success = tool.send_wechat_message(state["boss_reply"])
    state["send_success"] = success
    state["telemetry"] = {
        "intent": state.get("intent"),
        "route": state.get("route"),
        "send_success": success,
    }
    if success:
        feishu = FeishuSync()
        feishu.sync_record(state["user_message"], state["boss_reply"])
        if state.get("user_message"):
            memory_manager.remember(state["user_message"], state["boss_reply"])
    return state


def _route_after_intent(state: BusinessState) -> str:
    """LangGraph conditional routing"""
    return "human_gate" if state.get("require_human") else "boss_reply"


def build_graph():
    """构建 Deterministic State Machine via LangGraph"""
    graph = StateGraph(BusinessState)
    graph.add_node("get_message", node_get_message)
    graph.add_node("inventory_check", node_inventory_check)
    graph.add_node("intent_route", node_intent_route)
    graph.add_node("human_gate", node_human_gate)
    graph.add_node("boss_reply", node_boss_reply)
    graph.add_node("action_send", node_action_send)

    graph.add_edge("get_message", "inventory_check")
    graph.add_edge("inventory_check", "intent_route")
    graph.add_conditional_edges(
        "intent_route",
        _route_after_intent,
        {
            "human_gate": "human_gate",
            "boss_reply": "boss_reply",
        },
    )
    graph.add_edge("human_gate", "action_send")
    graph.add_edge("boss_reply", "action_send")
    graph.add_edge("action_send", END)
    graph.set_entry_point("get_message")
    return graph.compile()


def main():
    logger.info("=" * 70)
    logger.info("🦞 Project Claw - 多智能体协同主循环")
    logger.info("=" * 70)
    logger.info(f"🔧 OPENMAIC_ENABLED={settings.openmaic_enabled}")
    
    app = build_graph()
    logger.info("👁️ 开始监听消息...")
    
    while True:
        try:
            initial_state = {
                "user_message": None,
                "inventory_check": None,
                "intent": None,
                "route": None,
                "require_human": False,
                "boss_reply": None,
                "send_success": False,
                "telemetry": None,
                "error": None
            }
            
            final_state = app.invoke(initial_state)
            logger.info(
                "📊 本轮结果: "
                f"消息={final_state.get('user_message')}, "
                f"意图={final_state.get('intent')}, "
                f"路由={final_state.get('route')}, "
                f"发送={final_state.get('send_success')}"
            )
            time.sleep(5)
        
        except Exception as e:
            logger.error(f"❌ 主循环异常: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
