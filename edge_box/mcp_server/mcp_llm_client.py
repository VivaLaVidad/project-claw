from __future__ import annotations

from typing import Any

from llm_client import LLMClient
from edge_box.mcp_server.client import call_tool_sync


class MCPEnabledLLMClient:
    """让模型自主决定何时调用 MCP Tool 的轻量客户端封装。"""

    def __init__(self, llm: LLMClient, max_steps: int = 4):
        self.llm = llm
        self.max_steps = max_steps

    def negotiate_decision(self, item_name: str, expected_price: float) -> dict[str, Any]:
        messages: list[dict[str, Any]] = []
        system = (
            "你是 A2A 交易谈判代理。你可以按需调用 MCP 工具。\n"
            "可用工具：\n"
            "1) get_bottom_price(item_name:str)\n"
            "2) check_inventory(item_name:str)\n"
            "输出必须是 JSON，且只能二选一：\n"
            "A. 工具调用：{\"action\":\"tool_call\",\"tool\":\"get_bottom_price\",\"arguments\":{\"item_name\":\"牛肉面\"}}\n"
            "B. 最终决策：{\"action\":\"final\",\"result\":{\"is_accepted\":bool,\"offered_price\":number,\"reason\":string,\"bottom_price\":number,\"normal_price\":number,\"stock\":number}}\n"
            "必须先拿到足够事实再 final，不得臆造底价和库存。"
        )

        user = f"item_name={item_name}; expected_price={expected_price}. 请输出 JSON。"
        messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})

        for _ in range(self.max_steps):
            resp = self.llm.ask_json(prompt=messages[-1]["content"], system=system)
            if not resp:
                break

            action = str(resp.get("action", "")).lower()
            if action == "tool_call":
                tool = str(resp.get("tool", ""))
                arguments = resp.get("arguments", {}) or {}
                tool_result = call_tool_sync(tool, arguments)
                messages.append(
                    {
                        "role": "user",
                        "content": f"tool_result[{tool}]={tool_result}. 请继续输出 JSON。",
                    }
                )
                continue

            if action == "final":
                result = resp.get("result") or {}
                if isinstance(result, dict):
                    return result

        # 容灾：兜底走本地工具，保证可用
        b = call_tool_sync("get_bottom_price", {"item_name": item_name})
        i = call_tool_sync("check_inventory", {"item_name": item_name})
        bottom_price = float((b.get("bottom_price") or i.get("bottom_price") or 0))
        normal_price = float((b.get("normal_price") or i.get("normal_price") or bottom_price or 0))
        stock = int(i.get("stock") or 0)
        if bottom_price <= 0:
            bottom_price = max(1.0, expected_price * 0.75)
        if normal_price <= 0:
            normal_price = max(bottom_price, expected_price)

        return {
            "is_accepted": expected_price >= bottom_price,
            "offered_price": max(bottom_price, min(normal_price, expected_price)),
            "reason": "MCP fallback",
            "bottom_price": bottom_price,
            "normal_price": normal_price,
            "stock": stock,
        }
