"""
Project Claw v11.0 - 工业级配置管理
"""
from typing import List, Optional
try:
    from pydantic_settings import BaseSettings
except ImportError:
    from pydantic import BaseSettings


class Settings(BaseSettings):
    # ===== DeepSeek LLM =====
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_API_URL: str = "https://api.deepseek.com/chat/completions"
    DEEPSEEK_MODEL: str = "deepseek-chat"
    DEEPSEEK_TIMEOUT: int = 15
    DEEPSEEK_MAX_TOKENS: int = 200
    DEEPSEEK_TEMPERATURE: float = 0.7
    DEEPSEEK_MAX_RETRIES: int = 3

    # ===== 飞书 =====
    FEISHU_BOT_WEBHOOK: str = ""
    FEISHU_APP_ID: str = ""
    FEISHU_APP_SECRET: str = ""
    FEISHU_APP_TOKEN: str = ""
    FEISHU_TABLE_ID: str = ""
    FEISHU_AUTH_URL: str = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    FEISHU_BITABLE_URL: str = "https://open.feishu.cn/open-apis/bitable/v1/apps"
    FEISHU_TOKEN_TIMEOUT: int = 8

    # ===== 支付执行 =====
    PAYMENT_QR_PATH: str = "./payment_qr.png"

    # ===== 系统提示词 =====
    SYSTEM_PROMPT: str = "你是一个热情的店老板，回话简短接地气，叫人'兄弟'。"

    # ===== OCR =====
    OCR_LANGUAGES: List[str] = ["ch_sim", "en"]
    OCR_FAIL_MAX_RETRIES: int = 3

    # ===== 消息处理 =====
    MESSAGE_DEDUP_WINDOW: int = 50
    MESSAGE_DEDUP_TIME_WINDOW: int = 120
    MESSAGE_BBOX_DISTANCE_THRESHOLD: int = 50

    # ===== 截图裁剪 =====
    CROP_TOP_RATIO: float = 0.15
    CROP_BOTTOM_RATIO: float = 0.88
    CROP_LEFT_RATIO: float = 0.05
    CROP_RIGHT_RATIO: float = 0.95

    # ===== 输入 =====
    INPUT_Y_OFFSET: int = 150
    INPUT_DELAY_BEFORE: float = 0.05
    INPUT_DELAY_AFTER: float = 0.05

    # ===== UI 状态校验 =====
    UI_VERIFY_ENABLED: bool = False
    UI_VERIFY_TIMEOUT: float = 2.0
    UI_VERIFY_MAX_RETRIES: int = 2

    # ===== 轮询 =====
    POLL_INTERVAL_NO_MSG: float = 0.3
    POLL_INTERVAL_DUPLICATE: float = 0.3
    POLL_INTERVAL_ERROR: float = 1.0
    POLL_INTERVAL_MAIN: float = 0.2

    # ===== 日志 =====
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "lobster.log"
    LOG_FORMAT: str = "%(asctime)s [%(levelname)s] %(message)s"
    LOG_DIR: str = "logs"
    SHOWCASE_EVENT_FILE: str = "logs/showcase_events.jsonl"

    # ===== 统计 =====
    STATS_REPORT_INTERVAL: int = 5

    # ===== 商业大脑（B 端）=====
    BRAIN_ENABLED: bool = True
    RAG_PERSIST_DIR: str = "./rag_db"
    RAG_COLLECTION: str = "menu"
    RAG_TOP_K: int = 3
    MENU_EXCEL_PATH: Optional[str] = None

    # ===== 本地记忆（LocalMemory）=====
    LOCAL_MEMORY_ENABLED: bool = True
    LOCAL_MEMORY_DB_DIR: str = "./claw_db"
    LOCAL_MEMORY_CSV: str = "menu.csv"
    LOCAL_MEMORY_TOP_K: int = 3
    LOCAL_MEMORY_EMBED_MODEL: str = "all-MiniLM-L6-v2"

    # ===== Agent Workflow（async 状态机）=====
    AGENT_WORKFLOW_ENABLED: bool = True

    # ===== 社交匹配（C 端）=====
    MATCH_ENABLED: bool = True
    MATCH_ROUNDS: int = 5
    MATCH_THRESHOLD: float = 90.0

    # ===== A2A 协议 =====
    A2A_ENABLED: bool = False
    A2A_HOST: str = "127.0.0.1"
    A2A_PORT: int = 9000
    A2A_SIGNALING_URL: str = ""
    A2A_MERCHANT_ID: str = "box-001"
    A2A_MERCHANT_TAGS: str = ""
    A2A_SIGNING_SECRET: str = "claw-a2a-signing-secret"
    A2A_ENCRYPTION_KEY: str = ""

    # ===== 运行模式 =====
    AGENT_PROTOCOL_ONLY: bool = False

    # ===== 内部接口鉴权 =====
    INTERNAL_API_TOKEN: str = ""

    # ===== Redis（幂等/状态存储） =====
    REDIS_URL: str = ""
    IDEMPOTENCY_TTL_SECONDS: int = 300
    EXECUTE_TRADE_SEND_TIMEOUT_SECONDS: float = 4.0
    PROFILE_TTL_SECONDS: int = 86400

    # ===== 云端运行时接线 =====
    SIGNALING_HOST: str = "127.0.0.1"
    SIGNALING_PORT: int = 8765
    SIGNALING_HTTP_SCHEME: str = "http"
    SIGNALING_WS_SCHEME: str = "ws"
    SIRI_HOST: str = "0.0.0.0"
    SIRI_PORT: int = 8010

    # ===== OpenClaw 扩展预留 =====
    OPENCLAW_ENABLED: bool = False
    OPENCLAW_ENDPOINT: Optional[str] = None
    OPENCLAW_API_KEY: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"

    @property
    def signaling_http_base_url(self) -> str:
        # 若直接设置了 A2A_SIGNALING_URL，转换为 http base
        if self.A2A_SIGNALING_URL:
            import re
            m = re.match(r"(wss?://[^/]+)", self.A2A_SIGNALING_URL)
            if m:
                base = m.group(1).replace("wss://", "https://").replace("ws://", "http://")
                return base
        return f"{self.SIGNALING_HTTP_SCHEME}://{self.SIGNALING_HOST}:{self.SIGNALING_PORT}"

    @property
    def signaling_ws_base_url(self) -> str:
        # 若直接设置了 A2A_SIGNALING_URL，提取 base（scheme+host+port）
        if self.A2A_SIGNALING_URL:
            import re
            m = re.match(r"(wss?://[^/]+)", self.A2A_SIGNALING_URL)
            if m:
                return m.group(1)
        return f"{self.SIGNALING_WS_SCHEME}://{self.SIGNALING_HOST}:{self.SIGNALING_PORT}"

    @property
    def siri_base_url(self) -> str:
        host = self.SIGNALING_HOST if self.SIRI_HOST == "0.0.0.0" else self.SIRI_HOST
        return f"http://{host}:{self.SIRI_PORT}"

    def signaling_merchant_ws_url(self, merchant_id: str) -> str:
        return f"{self.signaling_ws_base_url}/ws/merchant/{merchant_id}"

    def social_stream_url(self, client_id: str) -> str:
        return f"{self.signaling_http_base_url}/socialstream/{client_id}"


settings = Settings()
