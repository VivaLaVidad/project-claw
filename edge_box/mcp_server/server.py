from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from edge_box.mcp_server.storage import (
    seed_from_csv_if_empty,
    get_bottom_price as _get_bottom_price,
    check_inventory as _check_inventory,
)

mcp = FastMCP("project-claw-mcp")


@mcp.tool()
def get_bottom_price(item_name: str) -> dict:
    """查询菜品底价与常规价。"""
    return _get_bottom_price(item_name)


@mcp.tool()
def check_inventory(item_name: str) -> dict:
    """查询菜品库存与价格。"""
    return _check_inventory(item_name)


def main() -> None:
    seed_from_csv_if_empty()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
