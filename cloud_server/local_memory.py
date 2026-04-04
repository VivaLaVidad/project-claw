from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    import chromadb
except Exception:  # pragma: no cover
    chromadb = None


@dataclass
class TenantMenuItem:
    name: str
    price: float
    floor_price: float
    spec: str = ""
    description: str = ""


class TenantLocalMemory:
    """Multi-tenant local memory: one merchant_id -> isolated collection."""

    def __init__(self, db_dir: str = "./claw_db", embed_model: str = "all-MiniLM-L6-v2"):
        self.db_dir = db_dir
        self.embed_model = embed_model
        self._client = None
        self._st_model = None
        if chromadb is not None:
            Path(db_dir).mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=db_dir)

    def _embed(self, texts: list[str]) -> list[list[float]]:
        if self._st_model is None:
            from sentence_transformers import SentenceTransformer
            self._st_model = SentenceTransformer(self.embed_model)
        vecs = self._st_model.encode(texts, show_progress_bar=False)
        return [v.tolist() for v in vecs]

    def _menu_collection(self, merchant_id: str):
        if self._client is None:
            return None
        return self._client.get_or_create_collection(name=f"tenant_{merchant_id}_menu", metadata={"hnsw:space": "cosine"})

    def _rules_collection(self, merchant_id: str):
        if self._client is None:
            return None
        return self._client.get_or_create_collection(name=f"tenant_{merchant_id}_rules", metadata={"hnsw:space": "cosine"})

    def ingest_menu_csv(self, merchant_id: str, csv_path: str) -> int:
        p = Path(csv_path)
        if not p.exists():
            return 0
        rows: list[TenantMenuItem] = []
        with open(p, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    item = TenantMenuItem(
                        name=(row.get("菜品名") or "").strip(),
                        price=float(row.get("价格") or 0),
                        floor_price=float(row.get("底价") or 0),
                        spec=(row.get("规格") or "").strip(),
                        description=(row.get("描述") or "").strip(),
                    )
                    if item.name:
                        rows.append(item)
                except Exception:
                    continue

        col = self._menu_collection(merchant_id)
        if col is None:
            return len(rows)

        docs, ids, metas = [], [], []
        for it in rows:
            docs.append(f"菜品:{it.name} 价格:{it.price} 底价:{it.floor_price} {it.spec} {it.description}")
            ids.append(it.name)
            metas.append({
                "name": it.name,
                "price": str(it.price),
                "floor_price": str(it.floor_price),
                "spec": it.spec,
                "description": it.description,
            })
        if docs:
            col.upsert(ids=ids, documents=docs, metadatas=metas, embeddings=self._embed(docs))
        return len(rows)

    def ingest_rules(self, merchant_id: str, rules: list[str]) -> int:
        cleaned = [x.strip() for x in rules if str(x).strip()]
        col = self._rules_collection(merchant_id)
        if col is None:
            return len(cleaned)
        ids = [f"r{i}" for i in range(len(cleaned))]
        if cleaned:
            col.upsert(ids=ids, documents=cleaned, metadatas=[{"rule": r} for r in cleaned], embeddings=self._embed(cleaned))
        return len(cleaned)

    def find_item(self, merchant_id: str, text: str) -> Optional[TenantMenuItem]:
        col = self._menu_collection(merchant_id)
        if col is None:
            return None
        for md in col.get(include=["metadatas"]).get("metadatas", []):
            pass
        # precise match first
        data = col.get(include=["metadatas"])
        for meta in data.get("metadatas", []):
            name = str(meta.get("name", ""))
            if name and name in text:
                return TenantMenuItem(
                    name=name,
                    price=float(meta.get("price", 0) or 0),
                    floor_price=float(meta.get("floor_price", 0) or 0),
                    spec=str(meta.get("spec", "")),
                    description=str(meta.get("description", "")),
                )
        # vector fallback
        if col.count() == 0:
            return None
        res = col.query(query_embeddings=self._embed([text]), n_results=1, include=["metadatas"])
        metas = res.get("metadatas", [[]])[0]
        if not metas:
            return None
        m = metas[0]
        return TenantMenuItem(
            name=str(m.get("name", "")),
            price=float(m.get("price", 0) or 0),
            floor_price=float(m.get("floor_price", 0) or 0),
            spec=str(m.get("spec", "")),
            description=str(m.get("description", "")),
        )
