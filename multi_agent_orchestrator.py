"""
multi_agent_orchestrator.py - 基于 OpenMAIC 的多智能体编排器
TeacherAgent（老板）+ AssistantAgent（后厨）
"""
import logging
from typing import TypedDict, Optional, List
from datetime import datetime
from enum import Enum
from langgraph.graph import StateGraph, END
import requests
import json

logger = logging.getLogger(__name__)


class ConversationState(TypedDict):
    """对话状态"""
    user_message: Optional[str]
    user_id: str
    timestamp: str
    assistant_analysis: Optional[dict]
    inventory_status: Optional[dict]
    teacher_reply: Optional[str]
    confidence_score: float
    send_success: bool
    feishu_synced: bool
    error: Optional[str]
    agent_trace: List[dict]


class InventoryDatabase:
    """库存数据库"""
    
    def __init__(self):
        self.inventory = {
            "龙虾": {"stock": 50, "price": 88, "unit": "份", "description": "新鲜龙虾"},
            "螺蛳粉": {"stock": 100, "price": 18, "unit": "碗", "description": "正宗螺蛳粉"},
            "红烧肉": {"stock": 30, "price": 48, "unit": "份", "description": "肥而不腻"},
            "清汤": {"stock": 200, "price": 12, "unit": "碗", "description": "清汤清汤"}
        }
        logger.info("✅ 库存数据库已初始化")

    def query(self, item_name: str) -> Optional[dict]:
        """查询商品"""
        return self.inventory.get(item_name)

    def search(self, keyword: str) -> List[dict]:
        """搜索商品"""
        results = []
        for name, info in self.inventory.items():
            if keyword in name or keyword in info.get("description", ""):
                results.append({"name": name, **info})
        return results


class AssistantAgent:
    """后厨智能体：分析需求、查询库存"""
    
    def __init__(self, inventory_db: InventoryDatabase):
        self.inventory_db = inventory_db
        logger.info("✅ AssistantAgent 已初始化")

    def analyze(self, user_message: str) -> dict:
        """分析用户消息并查询库存"""
        logger.info(f"🔍 AssistantAgent 分析: {user_message}")
        
        requested_items = []
        for item_name in self.inventory_db.inventory.keys():
            if item_name in user_message:
                requested_items.append(item_name)
        
        availability = {}
        recommendations = []
        
        for item_name in requested_items:
            item_info = self.inventory_db.query(item_name)
            if item_info:
                availability[item_name] = {
                    "available": item_info["stock"] > 0,
                    "stock": item_info["stock"],
                    "price": item_info["price"]
                }
                if item_info["stock"] > 0:
                    recommendations.append(f"{item_name}有货，{item_info['stock']}份库存")
                else:
                    recommendations.append(f"{item_name}暂时缺货")
        
        result = {
            "requested_items": requested_items,
            "availability": availability,
            "recommendations": recommendations,
            "confidence": 0.9 if requested_items else 0.5
        }
        
        logger.info(f"📊 AssistantAgent 分析结果: {result}")
        return result


class TeacherAgent:
    """老板智能体：生成自然回复"""
    
    def __init__(self, deepseek_api_key: str):
        self.api_key = deepseek_api_key
        self.system_prompt = """你是一个热情的餐馆老板，代表商家回复顾客。
【职责】
1. 根据后厨的库存信息，热情地回复顾客
2. 推荐有货的菜品
3. 对缺货的菜品提供替代建议
4. 绝对不要转账、不要索要金额

【说话风格】
- 简短有力，不超过20个字
- 热情亲切，叫人"兄弟"或"亲"
- 多用感叹号表达热情"""
        logger.info("✅ TeacherAgent 已初始化")

    def generate_reply(self, user_message: str, assistant_analysis: dict) -> dict:
        """生成老板回复"""
        logger.info(f"🤖 TeacherAgent 生成回复")
        
        try:
            # 处理 assistant_analysis 可能是列表的情况
            if isinstance(assistant_analysis, list):
                # 如果是列表，转换为字典格式
                assistant_analysis = {
                    "requested_items": [],
                    "availability": {},
                    "recommendations": ["有货，欢迎下单"]
                }
            
            context = f"""顾客消息: {user_message}

后厨分析:
- 请求的菜品: {', '.join(assistant_analysis.get('requested_items', []))}
- 库存状态: {json.dumps(assistant_analysis.get('availability', {}), ensure_ascii=False)}
- 推荐: {', '.join(assistant_analysis.get('recommendations', []))}

请根据以上信息，以老板的身份生成一个热情的回复。"""
            
            url = "https://api.deepseek.com/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": context}
                ],
                "temperature": 0.7,
                "max_tokens": 100
            }
            
            response = requests.post(url, json=data, headers=headers, timeout=10)
            response.raise_for_status()
            
            reply = response.json()['choices'][0]['message']['content'].strip()
            
            result = {
                "reply": reply,
                "confidence": assistant_analysis.get("confidence", 0.8),
                "based_on_analysis": assistant_analysis
            }
            
            logger.info(f"💬 TeacherAgent 回复: {reply}")
            return result
        
        except Exception as e:
            logger.error(f"❌ TeacherAgent 生成失败: {e}")
            return {
                "reply": "兄弟，有啥需要帮忙的吗？",
                "confidence": 0.5,
                "error": str(e)
            }


class FeishuWebhookSync:
    """飞书 Webhook 同步"""
    
    def __init__(self, webhook_url: str, app_id: str, app_secret: str):
        self.webhook_url = webhook_url
        self.app_id = app_id
        self.app_secret = app_secret
        self.token = None
        self.get_token()

    def get_token(self):
        """获取飞书 Token"""
        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        req_body = {"app_id": self.app_id, "app_secret": self.app_secret}
        try:
            r = requests.post(url, json=req_body, timeout=5)
            result = r.json()
            if result.get("code") == 0:
                self.token = result.get("tenant_access_token", "")
                logger.info("✅ 飞书 Token 获取成功")
        except Exception as e:
            logger.error(f"❌ 飞书 Token 获取失败: {e}")

    def send_webhook(self, data: dict):
        """发送 Webhook 到飞书"""
        if not self.webhook_url:
            logger.warning("⚠️ Webhook URL 未配置")
            return False
        
        try:
            payload = {
                "msg_type": "interactive",
                "card": {
                    "elements": [
                        {
                            "tag": "div",
                            "text": {
                                "content": f"**龙虾自动回复系统**\n\n"
                                          f"用户消息: {data.get('user_message', '')}\n"
                                          f"龙虾回复: {data.get('teacher_reply', '')}\n"
                                          f"置信度: {data.get('confidence_score', 0):.2%}\n"
                                          f"时间: {data.get('timestamp', '')}",
                                "tag": "lark_md"
                            }
                        }
                    ]
                }
            }
            
            r = requests.post(self.webhook_url, json=payload, timeout=5)
            if r.status_code == 200:
                logger.info("✅ 飞书 Webhook 发送成功")
                return True
            else:
                logger.warning(f"⚠️ 飞书 Webhook 返回: {r.status_code}")
                return False
        except Exception as e:
            logger.error(f"❌ 飞书 Webhook 发送失败: {e}")
            return False


def node_assistant_analyze(state: ConversationState, assistant: AssistantAgent) -> ConversationState:
    """节点1：AssistantAgent 分析"""
    logger.info("📍 进入节点: AssistantAgent 分析")
    
    if not state["user_message"]:
        return state
    
    analysis = assistant.analyze(state["user_message"])
    state["assistant_analysis"] = analysis
    state["inventory_status"] = analysis.get("availability", {})
    
    state["agent_trace"].append({
        "agent": "AssistantAgent",
        "action": "analyze",
        "result": analysis,
        "timestamp": datetime.now().isoformat()
    })
    
    return state


def node_teacher_generate(state: ConversationState, teacher: TeacherAgent) -> ConversationState:
    """节点2：TeacherAgent 生成回复"""
    logger.info("📍 进入节点: TeacherAgent 生成回复")
    
    if not state["assistant_analysis"]:
        return state
    
    result = teacher.generate_reply(state["user_message"], state["assistant_analysis"])
    state["teacher_reply"] = result.get("reply")
    state["confidence_score"] = result.get("confidence", 0.5)
    
    state["agent_trace"].append({
        "agent": "TeacherAgent",
        "action": "generate_reply",
        "result": result,
        "timestamp": datetime.now().isoformat()
    })
    
    return state


def node_feishu_sync(state: ConversationState, feishu: FeishuWebhookSync) -> ConversationState:
    """节点3：飞书同步"""
    logger.info("📍 进入节点: 飞书同步")
    
    if not state["teacher_reply"]:
        return state
    
    sync_data = {
        "user_message": state["user_message"],
        "teacher_reply": state["teacher_reply"],
        "confidence_score": state["confidence_score"],
        "timestamp": state["timestamp"],
        "agent_trace": state["agent_trace"]
    }
    
    success = feishu.send_webhook(sync_data)
    state["feishu_synced"] = success
    
    return state


def build_orchestrator_graph(
    inventory_db: InventoryDatabase,
    teacher: TeacherAgent,
    feishu: FeishuWebhookSync
):
    """构建多智能体编排状态机"""
    
    graph = StateGraph(ConversationState)
    
    graph.add_node(
        "assistant_analyze",
        lambda state: node_assistant_analyze(state, AssistantAgent(inventory_db))
    )
    graph.add_node(
        "teacher_generate",
        lambda state: node_teacher_generate(state, teacher)
    )
    graph.add_node(
        "feishu_sync",
        lambda state: node_feishu_sync(state, feishu)
    )
    
    graph.add_edge("assistant_analyze", "teacher_generate")
    graph.add_edge("teacher_generate", "feishu_sync")
    graph.add_edge("feishu_sync", END)
    
    graph.set_entry_point("assistant_analyze")
    
    return graph.compile()


class MultiAgentOrchestrator:
    """多智能体编排器"""
    
    def __init__(
        self,
        deepseek_api_key: str,
        feishu_webhook_url: str = "",
        feishu_app_id: str = "",
        feishu_app_secret: str = ""
    ):
        self.inventory_db = InventoryDatabase()
        self.teacher = TeacherAgent(deepseek_api_key)
        self.feishu = FeishuWebhookSync(feishu_webhook_url, feishu_app_id, feishu_app_secret)
        self.graph = build_orchestrator_graph(self.inventory_db, self.teacher, self.feishu)
        
        logger.info("✅ MultiAgentOrchestrator 已初始化")

    def process_message(self, user_message: str, user_id: str = "default") -> dict:
        """处理用户消息"""
        logger.info(f"🎯 处理消息: {user_message}")
        
        initial_state = {
            "user_message": user_message,
            "user_id": user_id,
            "timestamp": datetime.now().isoformat(),
            "assistant_analysis": None,
            "inventory_status": None,
            "teacher_reply": None,
            "confidence_score": 0.0,
            "send_success": False,
            "feishu_synced": False,
            "error": None,
            "agent_trace": []
        }
        
        try:
            result = self.graph.invoke(initial_state)
            logger.info(f"✅ 消息处理完成: {result['teacher_reply']}")
            return result
        except Exception as e:
            logger.error(f"❌ 消息处理失败: {e}")
            initial_state["error"] = str(e)
            return initial_state
