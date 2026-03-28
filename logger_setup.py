import hashlib
import json
import logging
import logging.handlers
import os
import time
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler
from rich.text import Text

from config import settings

console = Console(force_terminal=True, soft_wrap=True)

HTTP_NOISE_LOGGERS = {
    "uvicorn", "uvicorn.access", "uvicorn.error",
    "httpx", "urllib3", "asyncio",
}
SHOWCASE_EVENT_FILE = Path(settings.SHOWCASE_EVENT_FILE)

# ─── 生产环境 JSON 日志（Railway / Docker 采集）────────────────
_IS_PRODUCTION = os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("PRODUCTION", "")


class JSONFormatter(logging.Formatter):
    """
    结构化 JSON 日志格式（生产环境）。
    每行一个 JSON，方便 Datadog/Loki/Railway 日志采集。
    """
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts":      time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level":   record.levelname,
            "logger":  record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # 附加 showcase 字段
        for attr in ("event_type", "ocr_snippet", "handshake_seed", "coords"):
            val = getattr(record, attr, None)
            if val is not None:
                payload[attr] = val
        return json.dumps(payload, ensure_ascii=False)


# ─── 过滤器 ──────────────────────────────────────────────────
class BusinessOnlyFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if getattr(record, "showcase", False):
            return True
        if record.name in HTTP_NOISE_LOGGERS:
            return False
        noise_tokens = ("GET /", "POST /", '" 200', '" 404', '" 500', "HTTP/")
        return not any(token in record.getMessage() for token in noise_tokens)


# ─── Showcase 文件 Handler ────────────────────────────────────
class ShowcaseEventFileHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        if not getattr(record, "showcase", False):
            return
        try:
            SHOWCASE_EVENT_FILE.parent.mkdir(exist_ok=True)
            payload = {
                "ts":             time.time(),
                "logger":         record.name,
                "event_type":     getattr(record, "event_type", ""),
                "message":        record.getMessage(),
                "ocr_snippet":    getattr(record, "ocr_snippet", None),
                "handshake_seed": getattr(record, "handshake_seed", None),
                "coords":         getattr(record, "coords", None),
            }
            with SHOWCASE_EVENT_FILE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception:
            pass


# ─── Rich 控制台 Formatter（开发环境）────────────────────────
class ShowcaseFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        event = getattr(record, "event_type", "")
        if event == "vision_scan":
            snippet = getattr(record, "ocr_snippet", None) or record.getMessage()
            return console.render_str(
                f"[bold bright_green][👁️ VISION-SCAN][/bold bright_green] "
                f"[white]{snippet[:120]}[/white]"
            ).plain
        if event == "a2a_handshake":
            seed   = getattr(record, "handshake_seed", record.getMessage())
            digest = "0x" + hashlib.sha256(str(seed).encode()).hexdigest()[:18]
            return console.render_str(
                f"[bold bright_magenta][🔗 A2A-HANDSHAKE][/bold bright_magenta] "
                f"[white]Hash:[/white] [magenta]{digest}[/magenta]"
            ).plain
        if event == "execute_rpa":
            coords = getattr(record, "coords", None) or record.getMessage()
            return console.render_str(
                f"[bold bright_red][⚡ EXECUTE-RPA][/bold bright_red] "
                f"[white]{coords}[/white]"
            ).plain
        return ""


class ShowcaseRichHandler(RichHandler):
    def render_message(self, record: logging.LogRecord, message: str):
        event = getattr(record, "event_type", "")
        if event == "vision_scan":
            snippet = getattr(record, "ocr_snippet", None) or record.getMessage()
            return Text.assemble(
                ("[👁️ VISION-SCAN] ", "bold bright_green"),
                (snippet[:140], "white"),
            )
        if event == "a2a_handshake":
            seed   = getattr(record, "handshake_seed", record.getMessage())
            digest = "0x" + hashlib.sha256(str(seed).encode()).hexdigest()[:18]
            return Text.assemble(
                ("[🔗 A2A-HANDSHAKE] ", "bold bright_magenta"),
                ("Hash: ", "white"),
                (digest, "magenta"),
            )
        if event == "execute_rpa":
            coords = getattr(record, "coords", None) or record.getMessage()
            return Text.assemble(
                ("[⚡ EXECUTE-RPA] ", "bold bright_red"),
                (str(coords), "white"),
            )
        return Text(message)


# ─── ShowcaseLogger ───────────────────────────────────────────
class ShowcaseLogger(logging.Logger):
    def vision_scan(self, snippet: str) -> None:
        self.info(
            "vision scan",
            extra={"showcase": True, "event_type": "vision_scan", "ocr_snippet": snippet},
        )

    def a2a_handshake(self, seed: str) -> None:
        self.info(
            "a2a handshake",
            extra={"showcase": True, "event_type": "a2a_handshake", "handshake_seed": seed},
        )

    def execute_rpa(self, coords: str) -> None:
        self.info(
            "execute rpa",
            extra={"showcase": True, "event_type": "execute_rpa", "coords": coords},
        )


# ─── 主入口 ───────────────────────────────────────────────────
def setup_logger(name: str, level: str = "") -> ShowcaseLogger:
    """
    创建 ShowcaseLogger。

    生产环境（RAILWAY_ENVIRONMENT 或 PRODUCTION 已设置）：
      - JSON 结构化日志输出到 stdout
      - 日志轮转文件（10MB × 5份）

    开发环境：
      - Rich 彩色控制台
      - Showcase 事件写入 JSONL 文件
    """
    logging.setLoggerClass(ShowcaseLogger)
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # type: ignore[return-value]

    effective_level = getattr(logging, (level or settings.LOG_LEVEL).upper(), logging.INFO)
    logger.setLevel(effective_level)
    logger.addFilter(BusinessOnlyFilter())

    log_dir = Path(settings.LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)

    if _IS_PRODUCTION:
        # ── 生产：JSON stdout ──
        sh = logging.StreamHandler()
        sh.setFormatter(JSONFormatter())
        logger.addHandler(sh)
    else:
        # ── 开发：Rich 彩色控制台 ──
        rh = ShowcaseRichHandler(
            console=console,
            show_time=True,
            show_path=False,
            rich_tracebacks=True,
        )
        logger.addHandler(rh)
        # Showcase 事件文件
        logger.addHandler(ShowcaseEventFileHandler())

    # ── 日志轮转文件（生产+开发均开启）──
    log_file = log_dir / settings.LOG_FILE
    fh = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes   = 10 * 1024 * 1024,  # 10 MB
        backupCount = 5,
        encoding   = "utf-8",
    )
    fh.setFormatter(JSONFormatter() if _IS_PRODUCTION else logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(fh)

    return logger  # type: ignore[return-value]
