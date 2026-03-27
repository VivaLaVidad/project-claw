"""
lobster_mvp_v2.py - 重构版本
集成 MultiAgentOrchestrator，基于 OpenMAIC 架构
"""
import logging
import time
import hashlib
from collections import deque
from datetime import datetime
from typing import Optional
from multi_agent_orchestrator import MultiAgentOrchestrator
from lobster_tool import LobsterPhysicalTool

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('lobster_v2.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class MessageDedup:
    """消息去重器"""
    
    def __init__(self, window_size: int = 30, time_window_sec: int = 60):
        self.cache = deque(maxlen=window_size)
        self.time_window = time_window_sec

    def add(self, text: str):
        """添加消息"""
        msg_hash = hashlib.md5(text.encode()).hexdigest()
        self.cache.append({
            'hash': msg_hash,
            'text': text,
            'time': time.time()
        })

    def is_duplicate(self, text: str) -> bool:
        """检查重复"""
        msg_hash = hashlib.md5(text.encode()).hexdigest()
        now = time.time()
        
        for item in self.cache:
            if now - item['time'] < self.time_window:
                if item['hash'] == msg_hash:
                    logger.debug(f"🔄 检测到重复消息: {text}")
                    return True
        return False


class LobsterMVPv2:
    """龙虾 MVP v2 - 多智能体版本"""
    
    def __init__(
        self,
        deepseek_api_key: str,
        feishu_webhook_url: str = "",
        feishu_app_id: str = "",
        feishu_app_secret: str = ""
    ):
        self.orchestrator = MultiAgentOrchestrator(
            deepseek_api_key=deepseek_api_key,
            feishu_webhook_url=feishu_webhook_url,
            feishu_app_id=feishu_app_id,
            feishu_app_secret=feishu_app_secret
        )
        
        self.tool = LobsterPhysicalTool()
        self.dedup = MessageDedup(window_size=30, time_window_sec=60)
        
        self.stats = {
            "total_messages": 0,
            "successful_replies": 0,
            "failed_replies": 0,
            "duplicated": 0
        }
        
        logger.info("=" * 70)
        logger.info("🦞 Project Claw MVP v2 - 多智能体版本启动")
        logger.info("=" * 70)

    def run(self, check_interval: int = 5):
        """主循环"""
        logger.info(f"👁️ 开始监听消息（间隔 {check_interval}s）...")
        
        while True:
            try:
                # 1. 获取最新消息
                user_message = self.tool.get_latest_message()
                
                if not user_message:
                    time.sleep(check_interval)
                    continue
                
                # 2. 检查重复
                if self.dedup.is_duplicate(user_message):
                    self.stats["duplicated"] += 1
                    time.sleep(check_interval)
                    continue
                
                self.dedup.add(user_message)
                self.stats["total_messages"] += 1
                
                logger.info(f"🎯 新消息: {user_message}")
                
                # 3. 多智能体处理
                result = self.orchestrator.process_message(user_message)
                
                teacher_reply = result.get("teacher_reply")
                if not teacher_reply:
                    self.stats["failed_replies"] += 1
                    time.sleep(check_interval)
                    continue
                
                logger.info(f"💬 老板回复: {teacher_reply}")
                
                # 4. 发送消息
                success = self.tool.send_wechat_message(teacher_reply)
                
                if success:
                    self.stats["successful_replies"] += 1
                    self.dedup.add(teacher_reply)
                    logger.info(f"🚀 消息已发送")
                else:
                    self.stats["failed_replies"] += 1
                
                # 5. 定期输出统计
                if self.stats["total_messages"] % 5 == 0:
                    logger.info(
                        f"📊 统计 | 总消息: {self.stats['total_messages']} | "
                        f"成功: {self.stats['successful_replies']} | "
                        f"失败: {self.stats['failed_replies']} | "
                        f"重复: {self.stats['duplicated']}"
                    )
                
                time.sleep(check_interval)
            
            except Exception as e:
                logger.error(f"❌ 主循环异常: {e}")
                time.sleep(check_interval)


def main():
    """主函数"""
    # 配置参数
    DEEPSEEK_API_KEY = "sk-4aab42a0cace4e9a8c9bb31faa8c8f01"
    FEISHU_WEBHOOK_URL = ""  # 可选
    FEISHU_APP_ID = "cli_a937f9e24c21dbc8"
    FEISHU_APP_SECRET = "REZKNlpObMfWsPJwnSloJhIwiaB2FGVZ"
    
    # 启动
    bot = LobsterMVPv2(
        deepseek_api_key=DEEPSEEK_API_KEY,
        feishu_webhook_url=FEISHU_WEBHOOK_URL,
        feishu_app_id=FEISHU_APP_ID,
        feishu_app_secret=FEISHU_APP_SECRET
    )
    
    bot.run(check_interval=5)


if __name__ == "__main__":
    main()
