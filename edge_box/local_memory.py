from __future__ import annotations

"""edge_box/local_memory.py
Local RAG + long-term persona memory with session recycle hook.
"""

import csv
import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger("claw.edge.memory")

try:
    from mem0 import Memory  # type: ignore
    _MEM0_OK = True
except Exception:
    Memory = None
    _MEM0_OK = False


@dataclass
class MenuItem:
    name: str
    price: float
    floor_price: float
    spec: str = ""
    description: str = ""


@dataclass
class RAGResult:
    item: Optional[MenuItem] = None
    context_str: str = ""
    found: bool = False

    def to_context(self) -> str:
        return self.context_str

    @property
    def price(self) -> float:
        return self.item.price if self.item else 0.0

    @property
    def floor_price(self) -> float:
        return self.item.floor_price if self.item else 0.0

    @property
    def item_name(self) -> str:
        return self.item.name if self.item else ""


@dataclass
class UserPersona:
    user_id: str
    taste_preferences: list[str] = field(default_factory=list)
    dietary_restrictions: list[str] = field(default_factory=list)
    frequent_items: list[str] = field(default_factory=list)
    price_preference: str = ""
    notes: str = ""
    updated_at: float = 0.0


class PersonaMemoryStore:
    def __init__(self, db_path: str = "./edge_box/persona_memory.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self.deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "")
        self.deepseek_api_url = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com")
        self.deepseek_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        self._mem0 = None
        if _MEM0_OK:
            try:
                self._mem0 = Memory()
            except Exception:
                self._mem0 = None

    def _conn(self):
        c = sqlite3.connect(self.db_path, check_same_thread=False)
        c.row_factory = sqlite3.Row
        return c

    def _init_db(self):
        with self._conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS user_persona(
                  user_id TEXT PRIMARY KEY,
                  taste_preferences TEXT NOT NULL DEFAULT '[]',
                  dietary_restrictions TEXT NOT NULL DEFAULT '[]',
                  frequent_items TEXT NOT NULL DEFAULT '[]',
                  price_preference TEXT NOT NULL DEFAULT '',
                  notes TEXT NOT NULL DEFAULT '',
                  updated_at REAL NOT NULL DEFAULT 0
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS session_archive(
                  session_id TEXT PRIMARY KEY,
                  user_id TEXT NOT NULL,
                  transcript TEXT NOT NULL,
                  archived_at REAL NOT NULL
                )
            """)
            c.commit()

    def get_persona(self, user_id: str) -> Optional[UserPersona]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM user_persona WHERE user_id=?", (user_id,)).fetchone()
        if not row:
            return None
        return UserPersona(
            user_id=user_id,
            taste_preferences=json.loads(row["taste_preferences"] or "[]"),
            dietary_restrictions=json.loads(row["dietary_restrictions"] or "[]"),
            frequent_items=json.loads(row["frequent_items"] or "[]"),
            price_preference=row["price_preference"] or "",
            notes=row["notes"] or "",
            updated_at=float(row["updated_at"] or 0),
        )

    def upsert_persona(self, p: UserPersona):
        with self._conn() as c:
            c.execute("""
                INSERT INTO user_persona(user_id,taste_preferences,dietary_restrictions,frequent_items,price_preference,notes,updated_at)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(user_id) DO UPDATE SET
                  taste_preferences=excluded.taste_preferences,
                  dietary_restrictions=excluded.dietary_restrictions,
                  frequent_items=excluded.frequent_items,
                  price_preference=excluded.price_preference,
                  notes=excluded.notes,
                  updated_at=excluded.updated_at
            """, (
                p.user_id,
                json.dumps(p.taste_preferences, ensure_ascii=False),
                json.dumps(p.dietary_restrictions, ensure_ascii=False),
                json.dumps(p.frequent_items, ensure_ascii=False),
                p.price_preference,
                p.notes,
                p.updated_at,
            ))
            c.commit()
        if self._mem0 is not None:
            try:
                self._mem0.add(
                    f"用户偏好 user={p.user_id} 口味={p.taste_preferences} 忌口={p.dietary_restrictions} 常点={p.frequent_items} 价格偏好={p.price_preference}",
                    user_id=p.user_id,
                )
            except Exception:
                pass

    def build_priority_context(self, user_id: str) -> str:
        p = self.get_persona(user_id)
        if not p:
            return ""
        return "\n".join([
            "【最高优先级用户画像】",
            f"用户: {p.user_id}",
            f"口味偏好: {', '.join(p.taste_preferences) if p.taste_preferences else '未知'}",
            f"忌口: {', '.join(p.dietary_restrictions) if p.dietary_restrictions else '无'}",
            f"常点: {', '.join(p.frequent_items) if p.frequent_items else '未知'}",
            f"价格偏好: {p.price_preference or '未知'}",
            f"备注: {p.notes or '无'}",
            "要求: 以上信息优先级高于默认推荐。",
        ])

    async def extract_entities_and_store(self, user_id: str, session_id: str, transcript: str) -> Optional[UserPersona]:
        if not transcript.strip() or not self.deepseek_api_key:
            return self.get_persona(user_id)

        sys_prompt = (
            "你是用户偏好抽取器。仅输出JSON。"
            "schema={taste_preferences:string[],dietary_restrictions:string[],frequent_items:string[],price_preference:string,notes:string}"
        )
        payload = {
            "model": self.deepseek_model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": transcript[:6000]},
            ],
        }
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{self.deepseek_api_url.rstrip('/')}/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.deepseek_api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            resp.raise_for_status()
            obj = json.loads(resp.json()["choices"][0]["message"]["content"])

        old = self.get_persona(user_id) or UserPersona(user_id=user_id)
        merged = UserPersona(
            user_id=user_id,
            taste_preferences=_merge_list(old.taste_preferences, obj.get("taste_preferences", [])),
            dietary_restrictions=_merge_list(old.dietary_restrictions, obj.get("dietary_restrictions", [])),
            frequent_items=_merge_list(old.frequent_items, obj.get("frequent_items", [])),
            price_preference=str(obj.get("price_preference", old.price_preference or "")).strip(),
            notes=str(obj.get("notes", old.notes or "")).strip(),
            updated_at=time.time(),
        )
        self.upsert_persona(merged)
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO session_archive(session_id,user_id,transcript,archived_at) VALUES(?,?,?,?)",
                      (session_id, user_id, transcript[:12000], time.time()))
            c.commit()
        return merged


def _merge_list(a: list[str], b: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in (a or []) + (b or []):
        s = str(x).strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out[:20]


@dataclass
class SessionState:
    session_id: str
    user_id: str
    turns: list[dict[str, str]] = field(default_factory=list)


class SessionManager:
    def __init__(self, persona_store: PersonaMemoryStore):
        self.persona_store = persona_store
        self._sessions: dict[str, SessionState] = {}

    def create_session(self, session_id: str, user_id: str):
        self._sessions[session_id] = SessionState(session_id=session_id, user_id=user_id)

    def append_turn(self, session_id: str, role: str, text: str):
        s = self._sessions.get(session_id)
        if s:
            s.turns.append({"role": role, "text": text})

    def build_priority_context(self, user_id: str) -> str:
        return self.persona_store.build_priority_context(user_id)

    async def recycle_session(self, session_id: str) -> Optional[UserPersona]:
        s = self._sessions.pop(session_id, None)
        if not s:
            return None
        transcript = "\n".join([f"{t['role']}: {t['text']}" for t in s.turns])
        return await self.persona_store.extract_entities_and_store(s.user_id, s.session_id, transcript)


class LocalMenuRAG:
    def __init__(self, menu_csv: str = "menu.csv", persona_store: Optional[PersonaMemoryStore] = None):
        self.menu_csv = menu_csv
        self._items: list[MenuItem] = []
        self._load()
        self.persona_store = persona_store or PersonaMemoryStore()

    def _load(self):
        if not os.path.exists(self.menu_csv):
            return
        with open(self.menu_csv, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    it = MenuItem(
                        name=row.get("菜品名", "").strip(),
                        price=float(row.get("价格", 0) or 0),
                        floor_price=float(row.get("底价", 0) or 0),
                        spec=row.get("规格", "") or "",
                        description=row.get("描述", "") or "",
                    )
                    if it.name and it.price > 0:
                        self._items.append(it)
                except Exception:
                    continue

    def _query_keyword(self, text: str) -> Optional[MenuItem]:
        t = text.lower()
        for item in self._items:
            if item.name in text or item.name.lower() in t:
                return item
        return None

    def query(self, text: str, user_id: str = "") -> RAGResult:
        persona_ctx = self.persona_store.build_priority_context(user_id) if user_id else ""
        hit = self._query_keyword(text)
        if not hit:
            menu_ctx = "本店菜单:\n" + "\n".join([f"{i.name} {i.price}元（规格：{i.spec}）{i.description}" for i in self._items[:8]])
            full = f"{persona_ctx}\n\n{menu_ctx}".strip() if persona_ctx else menu_ctx
            return RAGResult(found=False, context_str=full)
        menu_ctx = f"菜品：{hit.name}\n正常价格：{hit.price}元\n规格：{hit.spec}\n描述：{hit.description}"
        full = f"{persona_ctx}\n\n{menu_ctx}".strip() if persona_ctx else menu_ctx
        return RAGResult(item=hit, found=True, context_str=full)

    def get_all_context(self) -> str:
        return "\n".join([f"{i.name} {i.price}元" for i in self._items])


_default_store: Optional[LocalMenuRAG] = None
_default_session_manager: Optional[SessionManager] = None


def get_store(menu_csv: str = "menu.csv") -> LocalMenuRAG:
    global _default_store
    if _default_store is None:
        _default_store = LocalMenuRAG(menu_csv=menu_csv)
    return _default_store


def get_session_manager(menu_csv: str = "menu.csv") -> SessionManager:
    global _default_session_manager
    if _default_session_manager is None:
        store = get_store(menu_csv)
        _default_session_manager = SessionManager(store.persona_store)
    return _default_session_manager
