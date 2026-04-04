from __future__ import annotations

import csv
import os
import sqlite3
from pathlib import Path

DB_PATH = os.getenv("MCP_SQLITE_PATH", "./edge_box/mcp_server/mcp_inventory.db")
MENU_CSV = os.getenv("MCP_MENU_CSV", "menu.csv")


def _conn() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS inventory (
              item_name TEXT PRIMARY KEY,
              normal_price REAL NOT NULL,
              bottom_price REAL NOT NULL,
              stock INTEGER NOT NULL DEFAULT 20
            )
            """
        )
        c.commit()


def seed_from_csv_if_empty(csv_path: str = MENU_CSV) -> None:
    init_db()
    with _conn() as c:
        row = c.execute("SELECT COUNT(1) AS cnt FROM inventory").fetchone()
        if int(row["cnt"] or 0) > 0:
            return

        if not os.path.exists(csv_path):
            return

        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                name = (r.get("菜品名") or "").strip()
                if not name:
                    continue
                price = float(r.get("价格") or 0)
                floor = float(r.get("底价") or 0)
                if price <= 0 and floor <= 0:
                    continue
                c.execute(
                    "INSERT OR REPLACE INTO inventory(item_name, normal_price, bottom_price, stock) VALUES(?,?,?,?)",
                    (name, float(price or floor), float(floor or price), 20),
                )
        c.commit()


def get_bottom_price(item_name: str) -> dict:
    init_db()
    with _conn() as c:
        row = c.execute(
            "SELECT item_name, normal_price, bottom_price FROM inventory WHERE item_name=?",
            (item_name,),
        ).fetchone()
    if not row:
        return {"found": False, "item_name": item_name, "bottom_price": 0.0, "normal_price": 0.0}
    return {
        "found": True,
        "item_name": row["item_name"],
        "bottom_price": float(row["bottom_price"] or 0),
        "normal_price": float(row["normal_price"] or 0),
    }


def check_inventory(item_name: str) -> dict:
    init_db()
    with _conn() as c:
        row = c.execute(
            "SELECT item_name, stock, normal_price, bottom_price FROM inventory WHERE item_name=?",
            (item_name,),
        ).fetchone()
    if not row:
        return {"found": False, "item_name": item_name, "stock": 0, "normal_price": 0.0, "bottom_price": 0.0}
    return {
        "found": True,
        "item_name": row["item_name"],
        "stock": int(row["stock"] or 0),
        "normal_price": float(row["normal_price"] or 0),
        "bottom_price": float(row["bottom_price"] or 0),
    }
