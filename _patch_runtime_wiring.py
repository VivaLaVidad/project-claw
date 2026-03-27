from pathlib import Path

# logger_setup.py
p = Path(r"d:\桌面\Project Claw\logger_setup.py")
s = p.read_text(encoding="utf-8")
s = s.replace('    log_dir = Path("logs")', '    log_dir = Path(settings.LOG_DIR)')
p.write_text(s, encoding="utf-8")

# demo_dashboard.py
p = Path(r"d:\桌面\Project Claw\demo_dashboard.py")
s = p.read_text(encoding="utf-8")
if 'from config import settings\n' not in s:
    s = s.replace('from pathlib import Path\n\n', 'from pathlib import Path\n\nfrom config import settings\n\n')
p.write_text(s, encoding="utf-8")

# consumer_agent.py
p = Path(r"d:\桌面\Project Claw\consumer_agent.py")
s = p.read_text(encoding="utf-8")
s = s.replace('        signaling_base_url: str = "http://127.0.0.1:8765",', '        signaling_base_url: str = settings.signaling_http_base_url,')
p.write_text(s, encoding="utf-8")

# cloud_server/api_server_pro.py
p = Path(r"d:\桌面\Project Claw\cloud_server\api_server_pro.py")
s = p.read_text(encoding="utf-8")
s = s.replace('import os\n', '')
if 'from llm_client import LLMClient\n' not in s:
    raise SystemExit('LLMClient import missing')
if 'from llm_client import LLMClient\n' in s:
    s = s.replace('from config import settings\nfrom logger_setup import setup_logger\n', 'from config import settings\nfrom llm_client import LLMClient\nfrom logger_setup import setup_logger\n') if 'from llm_client import LLMClient\n' not in s else s
s = s.replace('        self.signaling_base_url = (signaling_base_url or os.getenv("A2A_SIGNALING_BASE_URL", "http://127.0.0.1:8765")).rstrip("/")', '        self.signaling_base_url = (signaling_base_url or settings.signaling_http_base_url).rstrip("/")')
s = s.replace('    uvicorn.run("cloud_server.api_server_pro:app", host="0.0.0.0", port=8010, log_level="info")', '    uvicorn.run("cloud_server.api_server_pro:app", host=settings.SIRI_HOST, port=settings.SIRI_PORT, log_level="info")')
p.write_text(s, encoding="utf-8")

# a2a_box_client.py
p = Path(r"d:\桌面\Project Claw\a2a_box_client.py")
s = p.read_text(encoding="utf-8")
if 'from config import settings\n' not in s:
    s = s.replace('from logger_setup import setup_logger\n', 'from config import settings\nfrom logger_setup import setup_logger\n')
s = s.replace('        logger.a2a_handshake(f"intent:{client_id}->{self.merchant_id}:{intent_id}")\n        logger.a2a_handshake(f"intent:{client_id}->{self.merchant_id}:{intent_id}")\n', '        logger.a2a_handshake(f"intent:{client_id}->{self.merchant_id}:{intent_id}")\n')
marker = 'class A2ABoxClient:\n'
helper = 'def build_box_server_url(merchant_id: str) -> str:\n    return settings.signaling_merchant_ws_url(merchant_id)\n\n\nclass A2ABoxClient:\n'
if 'def build_box_server_url(merchant_id: str) -> str:' not in s:
    s = s.replace(marker, helper)
p.write_text(s, encoding="utf-8")

# a2a_signaling_server.py
p = Path(r"d:\桌面\Project Claw\a2a_signaling_server.py")
s = p.read_text(encoding="utf-8")
if 'from config import settings\n' not in s:
    s = s.replace('from cloud_server.match_orchestrator import MatchOrchestrator\n', 'from cloud_server.match_orchestrator import MatchOrchestrator\nfrom config import settings\n')
s = s.replace('        "a2a_signaling_server:app",\n        host="0.0.0.0",\n        port=8765,\n', '        "a2a_signaling_server:app",\n        host=settings.SIGNALING_HOST,\n        port=settings.SIGNALING_PORT,\n')
p.write_text(s, encoding="utf-8")

print("patched unified runtime wiring")
