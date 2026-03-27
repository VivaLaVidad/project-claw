"""
Project Claw doctor tool.
Checks runtime dependencies, environment variables, adb device status and Feishu token access.
"""
import importlib
import os
import subprocess
import sys
from typing import List, Tuple

import requests
from dotenv import load_dotenv

from settings import load_settings
from openmaic_adapter import OpenMAICAdapter


REQUIRED_MODULES = [
    "langgraph",
    "fastapi",
    "uvicorn",
    "dotenv",
    "uiautomator2",
    "easyocr",
    "cv2",
]


def _check_python_modules() -> Tuple[bool, List[str]]:
    missing = []
    for module_name in REQUIRED_MODULES:
        try:
            importlib.import_module(module_name)
        except Exception:
            missing.append(module_name)
    ok = len(missing) == 0
    if ok:
        return True, ["Python 依赖检查通过"]
    return False, [f"缺少模块: {', '.join(missing)}"]


def _check_env(settings_obj) -> Tuple[bool, List[str]]:
    required_keys = {
        "DEEPSEEK_API_KEY": settings_obj.deepseek_api_key,
        "FEISHU_APP_ID": settings_obj.feishu_app_id,
        "FEISHU_APP_SECRET": settings_obj.feishu_app_secret,
        "FEISHU_APP_TOKEN": settings_obj.feishu_app_token,
        "FEISHU_TABLE_ID": settings_obj.feishu_table_id,
    }
    missing = [k for k, v in required_keys.items() if not v]
    if missing:
        return False, [f".env 缺少: {', '.join(missing)}"]
    return True, ["环境变量检查通过"]


def _check_adb() -> Tuple[bool, List[str]]:
    try:
        result = subprocess.run(
            ["adb", "devices"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        device_lines = [line for line in lines[1:] if "\tdevice" in line]
        if device_lines:
            return True, [f"ADB 在线设备: {len(device_lines)} 台"]
        return False, ["ADB 无在线设备（请先连接手机或启动模拟器）"]
    except FileNotFoundError:
        return False, ["未找到 adb 命令（请安装 Android Platform Tools）"]
    except Exception as exc:
        return False, [f"ADB 检查失败: {exc}"]


def _check_feishu_token(settings_obj) -> Tuple[bool, List[str]]:
    if not settings_obj.feishu_app_id or not settings_obj.feishu_app_secret:
        return False, ["飞书凭证缺失，跳过 token 测试"]
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    payload = {
        "app_id": settings_obj.feishu_app_id,
        "app_secret": settings_obj.feishu_app_secret,
    }
    try:
        resp = requests.post(url, json=payload, timeout=8)
        data = resp.json()
        if data.get("code") == 0 and data.get("tenant_access_token"):
            return True, ["飞书 token 获取成功"]
        return False, [f"飞书 token 获取失败: {data.get('msg', 'unknown error')}"]
    except Exception as exc:
        return False, [f"飞书 token 请求异常: {exc}"]


def _check_openmaic(settings_obj) -> Tuple[bool, List[str]]:
    if not settings_obj.openmaic_enabled:
        return True, ["OPENMAIC_ENABLED=false，跳过检查"]
    try:
        adapter = OpenMAICAdapter()
        health = adapter.health_check()
        capabilities = health.get("capabilities")
        if capabilities:
            return True, [f"OpenMAIC 可用: status={health.get('status')}, capabilities={capabilities}"]
        return True, [f"OpenMAIC 可用: status={health.get('status')}"]
    except Exception as exc:
        return False, [f"OpenMAIC 健康检查失败: {exc}"]


def _print_result(name: str, ok: bool, lines: List[str]) -> bool:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}")
    for line in lines:
        print(f"  - {line}")
    return ok


def main() -> int:
    load_dotenv()
    settings_obj = load_settings()

    print("=== Project Claw Doctor ===")
    print(f"Python: {sys.executable}")
    print(f"OPENMAIC_ENABLED: {settings_obj.openmaic_enabled}")
    print()

    checks = [
        ("Python modules", _check_python_modules()),
        ("Environment variables", _check_env(settings_obj)),
        ("ADB connection", _check_adb()),
        ("Feishu token", _check_feishu_token(settings_obj)),
        ("OpenMAIC health", _check_openmaic(settings_obj)),
    ]

    all_ok = True
    for name, (ok, lines) in checks:
        result = _print_result(name, ok, lines)
        all_ok = all_ok and result
        print()

    if all_ok:
        print("✅ 所有检查通过，可以启动项目。")
        return 0

    print("❌ 存在未通过项，请先修复后再启动。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
