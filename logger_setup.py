import hashlib
import json
import logging
import logging.handlers
import time
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler
from rich.text import Text

from config import settings


console = Console(force_terminal=True, soft_wrap=True)
HTTP_NOISE_LOGGERS = {
    "uvicorn",
    "uvicorn.access",
    "uvicorn.error",
    "httpx",
    "urllib3",
    "asyncio",
}
SHOWCASE_EVENT_FILE = Path(settings.SHOWCASE_EVENT_FILE)


class BusinessOnlyFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if getattr(record, "showcase", False):
            return True
        if record.name in HTTP_NOISE_LOGGERS:
            return False
        noise_tokens = ("GET /", "POST /", '" 200', '" 404', '" 500', "HTTP/")
        return not any(token in message for token in noise_tokens)


class ShowcaseEventFileHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        if not getattr(record, "showcase", False):
            return
        try:
            SHOWCASE_EVENT_FILE.parent.mkdir(exist_ok=True)
            event = getattr(record, "event_type", "")
            payload = {
                "ts": time.time(),
                "logger": record.name,
                "event_type": event,
                "message": record.getMessage(),
                "ocr_snippet": getattr(record, "ocr_snippet", None),
                "handshake_seed": getattr(record, "handshake_seed", None),
                "coords": getattr(record, "coords", None),
            }
            with SHOWCASE_EVENT_FILE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception:
            pass


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
            handshake_seed = getattr(record, "handshake_seed", record.getMessage())
            digest = "0x" + hashlib.sha256(str(handshake_seed).encode("utf-8")).hexdigest()[:18]
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
            handshake_seed = getattr(record, "handshake_seed", record.getMessage())
            digest = "0x" + hashlib.sha256(str(handshake_seed).encode("utf-8")).hexdigest()[:18]
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

    def execute_rpa(self, x: float, y: float) -> None:
        self.info(
            "execute rpa",
            extra={"showcase": True, "event_type": "execute_rpa", "coords": f"tap=({x:.1f}, {y:.1f})"},
        )


logging.setLoggerClass(ShowcaseLogger)


def _build_file_handler(log_dir: Path) -> logging.Handler:
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / settings.LOG_FILE,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(settings.LOG_FORMAT))
    return file_handler


def _build_console_handler() -> logging.Handler:
    handler = ShowcaseRichHandler(
        console=console,
        show_time=False,
        show_level=False,
        show_path=False,
        markup=True,
        rich_tracebacks=True,
    )
    handler.setLevel(getattr(logging, settings.LOG_LEVEL))
    handler.addFilter(BusinessOnlyFilter())
    return handler


def _build_showcase_event_handler() -> logging.Handler:
    handler = ShowcaseEventFileHandler()
    handler.setLevel(logging.INFO)
    return handler


def setup_logger(name: str = "lobster") -> ShowcaseLogger:
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, settings.LOG_LEVEL))
    logger.propagate = False

    log_dir = Path(settings.LOG_DIR)
    log_dir.mkdir(exist_ok=True)

    if not logger.handlers:
        logger.addHandler(_build_file_handler(log_dir))
        logger.addHandler(_build_console_handler())
        logger.addHandler(_build_showcase_event_handler())

    for noisy_name in HTTP_NOISE_LOGGERS:
        noisy_logger = logging.getLogger(noisy_name)
        noisy_logger.handlers = []
        noisy_logger.propagate = False
        noisy_logger.setLevel(logging.CRITICAL)

    return logger  # type: ignore[return-value]


logger = setup_logger()
