"""
openclaw_integration.py - OpenClaw 工具集成层
将 Project Claw 的功能封装为 OpenClaw 工具
"""
import logging
import json
import os
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class ToolType(str, Enum):
    """工具类型"""
    PERCEPTION = "perception"
    COGNITION = "cognition"
    ACTION = "action"
    INTEGRATION = "integration"


class OpenClawTool:
    """OpenClaw 工具基类"""
    
    def __init__(self, name: str, tool_type: ToolType, description: str):
        self.name = name
        self.tool_type = tool_type
        self.description = description
        self.metadata = {
            "created_at": datetime.now().isoformat(),
            "version": "1.0.0",
            "author": "Project Claw"
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.tool_type.value,
            "description": self.description,
            "metadata": self.metadata
        }

    def execute(self, **kwargs) -> Dict[str, Any]:
        raise NotImplementedError


class WeChatPerceptionTool(OpenClawTool):
    """微信感知工具"""
    
    def __init__(self, lobster_tool):
        super().__init__(
            name="wechat_perception",
            tool_type=ToolType.PERCEPTION,
            description="从微信获取最新用户消息"
        )
        self.lobster_tool = lobster_tool

    def execute(self, **kwargs) -> Dict[str, Any]:
        try:
            message = self.lobster_tool.get_latest_message()
            if message:
                return {
                    "status": "success",
                    "message": message,
                    "timestamp": datetime.now().isoformat(),
                    "source": "wechat"
                }
            else:
                return {
                    "status": "no_message",
                    "message": None,
                    "timestamp": datetime.now().isoformat()
                }
        except Exception as e:
            logger.error(f"❌ 微信感知工具执行失败: {e}")
            return {"status": "error", "error": str(e), "timestamp": datetime.now().isoformat()}


class InventoryQueryTool(OpenClawTool):
    """库存查询工具"""
    
    def __init__(self, inventory_db):
        super().__init__(
            name="inventory_query",
            tool_type=ToolType.COGNITION,
            description="查询商品库存和价格信息"
        )
        self.inventory_db = inventory_db

    def execute(self, **kwargs) -> Dict[str, Any]:
        try:
            query = kwargs.get("query", "")
            if not query:
                return {"status": "error", "error": "查询参数不能为空", "timestamp": datetime.now().isoformat()}
            results = self.inventory_db.search(query)
            return {
                "status": "success",
                "query": query,
                "results": results,
                "count": len(results),
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"❌ 库存查询工具执行失败: {e}")
            return {"status": "error", "error": str(e), "timestamp": datetime.now().isoformat()}


class LLMGenerationTool(OpenClawTool):
    """LLM 生成工具"""
    
    def __init__(self, teacher_agent):
        super().__init__(
            name="llm_generation",
            tool_type=ToolType.COGNITION,
            description="使用 DeepSeek LLM 生成自然语言回复"
        )
        self.teacher_agent = teacher_agent

    def execute(self, **kwargs) -> Dict[str, Any]:
        try:
            user_message = kwargs.get("user_message", "")
            assistant_analysis = kwargs.get("assistant_analysis", {})
            if not user_message:
                return {"status": "error", "error": "用户消息不能为空", "timestamp": datetime.now().isoformat()}
            result = self.teacher_agent.generate_reply(user_message, assistant_analysis)
            return {
                "status": "success",
                "reply": result.get("reply"),
                "confidence": result.get("confidence"),
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"❌ LLM 生成工具执行失败: {e}")
            return {"status": "error", "error": str(e), "timestamp": datetime.now().isoformat()}


class WeChatActionTool(OpenClawTool):
    """微信动作工具"""
    
    def __init__(self, lobster_tool):
        super().__init__(
            name="wechat_action",
            tool_type=ToolType.ACTION,
            description="向微信发送消息"
        )
        self.lobster_tool = lobster_tool

    def execute(self, **kwargs) -> Dict[str, Any]:
        try:
            text = kwargs.get("text", "")
            if not text:
                return {"status": "error", "error": "消息文本不能为空", "timestamp": datetime.now().isoformat()}
            success = self.lobster_tool.send_wechat_message(text)
            return {
                "status": "success" if success else "failed",
                "text": text,
                "sent": success,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"❌ 微信动作工具执行失败: {e}")
            return {"status": "error", "error": str(e), "timestamp": datetime.now().isoformat()}


class FeishuIntegrationTool(OpenClawTool):
    """飞书集成工具"""
    
    def __init__(self, feishu_sync):
        super().__init__(
            name="feishu_integration",
            tool_type=ToolType.INTEGRATION,
            description="将对话数据同步到飞书多维表格"
        )
        self.feishu_sync = feishu_sync

    def execute(self, **kwargs) -> Dict[str, Any]:
        try:
            user_message = kwargs.get("user_message", "")
            assistant_reply = kwargs.get("assistant_reply", "")
            if not user_message or not assistant_reply:
                return {"status": "error", "error": "用户消息和回复都不能为空", "timestamp": datetime.now().isoformat()}
            success = self.feishu_sync.send_webhook({
                "user_message": user_message,
                "teacher_reply": assistant_reply,
                "confidence_score": kwargs.get("confidence_score", 0.8),
                "timestamp": datetime.now().isoformat()
            })
            return {
                "status": "success" if success else "failed",
                "synced": success,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"❌ 飞书集成工具执行失败: {e}")
            return {"status": "error", "error": str(e), "timestamp": datetime.now().isoformat()}


class OpenClawToolRegistry:
    """OpenClaw 工具注册表"""
    
    def __init__(self):
        self.tools: Dict[str, OpenClawTool] = {}
        self.tool_groups: Dict[str, List[str]] = {
            "perception": [],
            "cognition": [],
            "action": [],
            "integration": []
        }
        logger.info("✅ OpenClaw 工具注册表已初始化")

    def register(self, tool: OpenClawTool):
        self.tools[tool.name] = tool
        self.tool_groups[tool.tool_type.value].append(tool.name)
        logger.info(f"✅ 工具已注册: {tool.name} ({tool.tool_type.value})")

    def get_tool(self, name: str) -> Optional[OpenClawTool]:
        return self.tools.get(name)

    def list_tools(self, tool_type: Optional[ToolType] = None) -> List[Dict[str, Any]]:
        if tool_type:
            tool_names = self.tool_groups[tool_type.value]
            return [self.tools[name].to_dict() for name in tool_names]
        else:
            return [tool.to_dict() for tool in self.tools.values()]

    def execute_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        tool = self.get_tool(tool_name)
        if not tool:
            return {"status": "error", "error": f"工具 {tool_name} 不存在", "timestamp": datetime.now().isoformat()}
        logger.info(f"🔧 执行工具: {tool_name}")
        result = tool.execute(**kwargs)
        logger.info(f"✅ 工具执行完成: {tool_name}")
        return result

    def export_manifest(self) -> Dict[str, Any]:
        return {
            "name": "Project Claw Tools",
            "version": "1.0.0",
            "description": "龙虾自动回复系统的 OpenClaw 工具集",
            "tools": self.list_tools(),
            "tool_groups": {
                "perception": self.list_tools(ToolType.PERCEPTION),
                "cognition": self.list_tools(ToolType.COGNITION),
                "action": self.list_tools(ToolType.ACTION),
                "integration": self.list_tools(ToolType.INTEGRATION)
            },
            "exported_at": datetime.now().isoformat()
        }

    def save_manifest(self, path: str):
        manifest = self.export_manifest()
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        logger.info(f"✅ 工具清单已保存: {path}")


class OpenClawIntegrator:
    """OpenClaw 集成器"""
    
    def __init__(
        self,
        lobster_tool,
        inventory_db,
        teacher_agent,
        feishu_sync,
        openclaw_config_path: str = "d:\\OpenClaw_System\\Config\\openclaw.json"
    ):
        self.registry = OpenClawToolRegistry()
        self.openclaw_config_path = openclaw_config_path
        self.register_tools(lobster_tool, inventory_db, teacher_agent, feishu_sync)
        logger.info("✅ OpenClaw 集成器已初始化")

    def register_tools(self, lobster_tool, inventory_db, teacher_agent, feishu_sync):
        self.registry.register(WeChatPerceptionTool(lobster_tool))
        self.registry.register(InventoryQueryTool(inventory_db))
        self.registry.register(LLMGenerationTool(teacher_agent))
        self.registry.register(WeChatActionTool(lobster_tool))
        self.registry.register(FeishuIntegrationTool(feishu_sync))

    def get_registry(self) -> OpenClawToolRegistry:
        return self.registry

    def export_to_openclaw(self, output_path: str = None):
        if output_path is None:
            output_path = os.path.join(
                os.path.dirname(self.openclaw_config_path),
                "project_claw_tools.json"
            )
        self.registry.save_manifest(output_path)
        logger.info(f"✅ 工具已导出到 OpenClaw: {output_path}")
        return output_path

    def list_all_tools(self) -> Dict[str, Any]:
        return self.registry.export_manifest()

    def execute_workflow(self, user_message: str) -> Dict[str, Any]:
        logger.info(f"🔄 执行 OpenClaw 工作流: {user_message}")
        workflow_result = {
            "user_message": user_message,
            "steps": [],
            "success": True,
            "timestamp": datetime.now().isoformat()
        }
        try:
            perception_result = self.registry.execute_tool("wechat_perception")
            workflow_result["steps"].append({"name": "wechat_perception", "result": perception_result})
            
            inventory_result = self.registry.execute_tool("inventory_query", query=user_message)
            workflow_result["steps"].append({"name": "inventory_query", "result": inventory_result})
            
            llm_result = self.registry.execute_tool(
                "llm_generation",
                user_message=user_message,
                assistant_analysis=inventory_result.get("results", [])
            )
            workflow_result["steps"].append({"name": "llm_generation", "result": llm_result})
            
            if llm_result.get("status") == "success":
                action_result = self.registry.execute_tool("wechat_action", text=llm_result.get("reply"))
                workflow_result["steps"].append({"name": "wechat_action", "result": action_result})
                
                if action_result.get("status") == "success":
                    feishu_result = self.registry.execute_tool(
                        "feishu_integration",
                        user_message=user_message,
                        assistant_reply=llm_result.get("reply"),
                        confidence_score=llm_result.get("confidence", 0.8)
                    )
                    workflow_result["steps"].append({"name": "feishu_integration", "result": feishu_result})
        except Exception as e:
            logger.error(f"❌ 工作流执行失败: {e}")
            workflow_result["success"] = False
            workflow_result["error"] = str(e)
        logger.info(f"✅ 工作流执行完成")
        return workflow_result
