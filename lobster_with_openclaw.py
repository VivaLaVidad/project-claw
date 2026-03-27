"""
lobster_with_openclaw.py - 完整集成 OpenClaw 的龙虾系统
工业级多智能体 + OpenClaw 工具集成
"""
import logging
from multi_agent_orchestrator import MultiAgentOrchestrator, InventoryDatabase
from openclaw_integration import OpenClawIntegrator
from lobster_tool import LobsterPhysicalTool
import time

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('lobster_openclaw.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class LobsterWithOpenClaw:
    """龙虾系统 + OpenClaw 集成版本"""
    
    def __init__(
        self,
        deepseek_api_key: str,
        feishu_webhook_url: str = "",
        feishu_app_id: str = "",
        feishu_app_secret: str = "",
        openclaw_config_path: str = "d:\\OpenClaw_System\\Config\\openclaw.json"
    ):
        logger.info("=" * 70)
        logger.info("🦞 Project Claw + OpenClaw 集成版本启动")
        logger.info("=" * 70)
        
        # 初始化核心组件
        self.inventory_db = InventoryDatabase()
        self.lobster_tool = LobsterPhysicalTool()
        
        # 初始化多智能体编排器
        self.orchestrator = MultiAgentOrchestrator(
            deepseek_api_key=deepseek_api_key,
            feishu_webhook_url=feishu_webhook_url,
            feishu_app_id=feishu_app_id,
            feishu_app_secret=feishu_app_secret
        )
        
        # 初始化 OpenClaw 集成器
        self.openclaw_integrator = OpenClawIntegrator(
            lobster_tool=self.lobster_tool,
            inventory_db=self.inventory_db,
            teacher_agent=self.orchestrator.teacher,
            feishu_sync=self.orchestrator.feishu,
            openclaw_config_path=openclaw_config_path
        )
        
        # 导出工具清单到 OpenClaw
        self.export_tools_to_openclaw()
        
        logger.info("✅ 龙虾 + OpenClaw 系统已初始化")

    def export_tools_to_openclaw(self):
        """导出工具清单到 OpenClaw"""
        try:
            output_path = self.openclaw_integrator.export_to_openclaw()
            logger.info(f"✅ 工具已导出到 OpenClaw: {output_path}")
            
            # 显示工具清单
            tools_manifest = self.openclaw_integrator.list_all_tools()
            logger.info(f"📦 工具清单:")
            logger.info(f"  - 感知工具: {len(tools_manifest['tool_groups']['perception'])} 个")
            logger.info(f"  - 认知工具: {len(tools_manifest['tool_groups']['cognition'])} 个")
            logger.info(f"  - 动作工具: {len(tools_manifest['tool_groups']['action'])} 个")
            logger.info(f"  - 集成工具: {len(tools_manifest['tool_groups']['integration'])} 个")
        except Exception as e:
            logger.error(f"❌ 导出工具失败: {e}")

    def process_message_with_openclaw(self, user_message: str) -> dict:
        """使用 OpenClaw 工具处理消息"""
        logger.info(f"🔄 使用 OpenClaw 工具处理消息: {user_message}")
        
        # 执行 OpenClaw 工作流
        workflow_result = self.openclaw_integrator.execute_workflow(user_message)
        
        return workflow_result

    def process_message_with_orchestrator(self, user_message: str) -> dict:
        """使用多智能体编排器处理消息"""
        logger.info(f"🔄 使用多智能体编排器处理消息: {user_message}")
        
        # 执行多智能体流程
        result = self.orchestrator.process_message(user_message)
        
        return result

    def run_with_openclaw(self, check_interval: int = 5):
        """使用 OpenClaw 工具的主循环"""
        logger.info(f"👁️ 开始监听消息（使用 OpenClaw 工具，间隔 {check_interval}s）...")
        
        stats = {
            "total_messages": 0,
            "successful_replies": 0,
            "failed_replies": 0
        }
        
        while True:
            try:
                # 使用 OpenClaw 感知工具获取消息
                perception_result = self.openclaw_integrator.registry.execute_tool("wechat_perception")
                
                if perception_result.get("status") != "success":
                    time.sleep(check_interval)
                    continue
                
                user_message = perception_result.get("message")
                if not user_message:
                    time.sleep(check_interval)
                    continue
                
                logger.info(f"🎯 新消息: {user_message}")
                stats["total_messages"] += 1
                
                # 处理消息
                workflow_result = self.process_message_with_openclaw(user_message)
                
                if workflow_result.get("success"):
                    stats["successful_replies"] += 1
                else:
                    stats["failed_replies"] += 1
                
                # 定期输出统计
                if stats["total_messages"] % 5 == 0:
                    logger.info(
                        f"📊 统计 | 总消息: {stats['total_messages']} | "
                        f"成功: {stats['successful_replies']} | "
                        f"失败: {stats['failed_replies']}"
                    )
                
                time.sleep(check_interval)
            
            except Exception as e:
                logger.error(f"❌ 主循环异常: {e}")
                time.sleep(check_interval)

    def run_with_orchestrator(self, check_interval: int = 5):
        """使用多智能体编排器的主循环"""
        logger.info(f"👁️ 开始监听消息（使用多智能体编排器，间隔 {check_interval}s）...")
        
        stats = {
            "total_messages": 0,
            "successful_replies": 0,
            "failed_replies": 0
        }
        
        while True:
            try:
                # 获取消息
                user_message = self.lobster_tool.get_latest_message()
                
                if not user_message:
                    time.sleep(check_interval)
                    continue
                
                logger.info(f"🎯 新消息: {user_message}")
                stats["total_messages"] += 1
                
                # 处理消息
                result = self.process_message_with_orchestrator(user_message)
                
                if result.get("teacher_reply"):
                    stats["successful_replies"] += 1
                else:
                    stats["failed_replies"] += 1
                
                # 定期输出统计
                if stats["total_messages"] % 5 == 0:
                    logger.info(
                        f"📊 统计 | 总消息: {stats['total_messages']} | "
                        f"成功: {stats['successful_replies']} | "
                        f"失败: {stats['failed_replies']}"
                    )
                
                time.sleep(check_interval)
            
            except Exception as e:
                logger.error(f"❌ 主循环异常: {e}")
                time.sleep(check_interval)

    def get_tool_info(self) -> dict:
        """获取工具信息"""
        return self.openclaw_integrator.list_all_tools()


def main():
    """主函数"""
    # 配置参数
    DEEPSEEK_API_KEY = "sk-4aab42a0cace4e9a8c9bb31faa8c8f01"
    FEISHU_WEBHOOK_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/cb21b82b-96d6-4513-bb34-190b7fa8b0fc"
    FEISHU_APP_ID = "cli_a937f9e24c21dbc8"
    FEISHU_APP_SECRET = "REZKNlpObMfWsPJwnSloJhIwiaB2FGVZ"
    OPENCLAW_CONFIG_PATH = "d:\\OpenClaw_System\\Config\\openclaw.json"
    
    # 启动系统
    system = LobsterWithOpenClaw(
        deepseek_api_key=DEEPSEEK_API_KEY,
        feishu_webhook_url=FEISHU_WEBHOOK_URL,
        feishu_app_id=FEISHU_APP_ID,
        feishu_app_secret=FEISHU_APP_SECRET,
        openclaw_config_path=OPENCLAW_CONFIG_PATH
    )
    
    # 选择运行模式
    logger.info("选择运行模式:")
    logger.info("1. 使用 OpenClaw 工具（推荐）")
    logger.info("2. 使用多智能体编排器")
    
    # 默认使用 OpenClaw 工具
    system.run_with_openclaw(check_interval=5)


if __name__ == "__main__":
    main()
