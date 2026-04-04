from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any


def _server_script_path() -> str:
    return str(Path(__file__).with_name("server.py"))


def _parse_tool_result(result: Any) -> dict:
    # FastMCP 常见返回：CallToolResult(content=[TextContent(text='...')], isError=False)
    content = getattr(result, "content", None)
    if content and len(content) > 0:
        text = getattr(content[0], "text", "") or ""
        if text:
            try:
                return json.loads(text)
            except Exception:
                return {"raw": text}

    # 若 SDK 已直接返回 dict
    if isinstance(result, dict):
        return result

    return {"raw": str(result)}


async def call_tool(tool_name: str, arguments: dict) -> dict:
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        server_params = StdioServerParameters(
            command=sys.executable,
            args=[_server_script_path()],
            env={**os.environ},
        )
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                return _parse_tool_result(result)
    except Exception:
        # SDK 不可用或 stdio 失败时，退回本地直连，保证不中断
        from edge_box.mcp_server.storage import get_bottom_price, check_inventory, seed_from_csv_if_empty

        seed_from_csv_if_empty()
        if tool_name == "get_bottom_price":
            return get_bottom_price(arguments.get("item_name", ""))
        if tool_name == "check_inventory":
            return check_inventory(arguments.get("item_name", ""))
        return {"error": f"unknown tool: {tool_name}"}


def call_tool_sync(tool_name: str, arguments: dict) -> dict:
    return asyncio.run(call_tool(tool_name, arguments))
