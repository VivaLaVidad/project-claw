"""
Project Claw v12.0 - local_memory.py
本地业务记忆，数据绝不上云。

ChromaDB 直接传入预计算 embedding，完全绕过 EmbeddingFunction 接口。
"""
from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("claw.memory")

try:
    import chromadb
    _CHROMA_OK = True
except ImportError:
    _CHROMA_OK = False
    logger.warning("chromadb 未安装，本地记忆功能降级")

_FALLBACK    = "抱歉，本地系统升级中，请稍后再试或直接联系店员。"
_DB_DIR      = "./claw_db"
_COL_NAME    = "menu"
_EMBED_MODEL = "all-MiniLM-L6-v2"


@dataclass
class MenuItem:
    name:        str
    price:       float
    spec:        str
    floor_price: float
    description: str

    def to_doc(self) -> str:
        if self.price == 0:
            return f"【商家规矩】{self.name}：{self.description}"
        return (
            f"菜品：{self.name}，价格：{self.price}元，"
            f"规格：{self.spec}，底价：{self.floor_price}元。"
            f"{self.description}"
        )

    def to_meta(self) -> dict:
        return {
            "name": self.name, "price": str(self.price),
            "spec": self.spec, "floor_price": str(self.floor_price),
            "description": self.description,
        }


@dataclass
class QueryResult:
    items:    List[MenuItem]
    query:    str
    top_k:    int
    fallback: bool = False

    def to_context(self) -> str:
        if self.fallback:
            return _FALLBACK
        if not self.items:
            return "本地数据库未找到相关信息，请直接回答顾客。"
        lines = [f"以下是与「{self.query}」最相关的本地业务信息："]
        for i, item in enumerate(self.items, 1):
            lines.append(f"{i}. {item.to_doc()}")
        return "\n".join(lines)


class StoreManager:
    """本地业务记忆管理器（ChromaDB + sentence-transformers，完全离线）"""

    def __init__(
        self,
        db_dir: str = _DB_DIR,
        collection_name: str = _COL_NAME,
        embed_model: str = _EMBED_MODEL,
        top_k: int = 3,
    ):
        self.db_dir          = db_dir
        self.collection_name = collection_name
        self.embed_model     = embed_model
        self.top_k           = top_k
        self._client         = None
        self._collection     = None
        self._st_model       = None
        self._items: List[MenuItem] = []
        self._ready          = False
        if _CHROMA_OK:
            self._init_db()
        else:
            logger.error("ChromaDB 不可用，以容灾模式运行")

    def _load_model(self):
        """懒加载 sentence_transformers（首次调用时加载）"""
        if self._st_model is None:
            from sentence_transformers import SentenceTransformer
            self._st_model = SentenceTransformer(self.embed_model)

    def _embed(self, texts: List[str]) -> List[List[float]]:
        """生成 embedding 向量列表"""
        self._load_model()
        vecs = self._st_model.encode(texts, show_progress_bar=False)
        return [v.tolist() for v in vecs]

    def _init_db(self):
        """初始化 ChromaDB，不使用 EmbeddingFunction"""
        try:
            Path(self.db_dir).mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=self.db_dir)
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            self._ready = True
            logger.info(f"[StoreManager] ✅ ChromaDB 就绪 | dir={self.db_dir}")
        except Exception as e:
            logger.error(f"[StoreManager] ChromaDB 初始化失败: {e}")
            self._ready = False

    def load_csv(self, csv_path: str) -> int:
        """读取 CSV，向量化并写入 ChromaDB"""
        path = Path(csv_path)
        if not path.exists():
            logger.error(f"[StoreManager] CSV 不存在: {csv_path}")
            return 0
        items: List[MenuItem] = []
        try:
            with open(path, encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    try:
                        items.append(MenuItem(
                            name=row.get("菜品名", "").strip(),
                            price=float(row.get("价格", 0) or 0),
                            spec=row.get("规格", "").strip(),
                            floor_price=float(row.get("底价", 0) or 0),
                            description=row.get("描述", "").strip(),
                        ))
                    except Exception as e:
                        logger.warning(f"[StoreManager] 跳过无效行: {e}")
        except Exception as e:
            logger.error(f"[StoreManager] CSV 读取失败: {e}")
            return 0
        self._items = items
        logger.info(f"[StoreManager] 读取 CSV: {len(items)} 条")
        if not self._ready or self._collection is None:
            logger.warning("[StoreManager] 向量库未就绪，仅内存索引")
            return len(items)
        return self._upsert(items)

    def _upsert(self, items: List[MenuItem]) -> int:
        """Upsert 到 ChromaDB，自行提供 embedding"""
        try:
            existing = set(self._collection.get()["ids"])
            docs, ids, metas = [], [], []
            for item in items:
                if item.name and item.name not in existing:
                    docs.append(item.to_doc())
                    ids.append(item.name)
                    metas.append(item.to_meta())
            if docs:
                embeddings = self._embed(docs)
                self._collection.add(
                    documents=docs, ids=ids,
                    metadatas=metas, embeddings=embeddings,
                )
                logger.info(f"[StoreManager] 新增 {len(docs)} 条到 ChromaDB")
            else:
                logger.info("[StoreManager] ChromaDB 已最新")
            return len(items)
        except Exception as e:
            logger.error(f"[StoreManager] ChromaDB 写入失败: {e}")
            return 0

    def reload(self, csv_path: str) -> int:
        """热更新菜单"""
        try:
            if self._ready and self._client:
                self._client.delete_collection(self.collection_name)
                self._init_db()
            return self.load_csv(csv_path)
        except Exception as e:
            logger.error(f"[StoreManager] reload 失败: {e}")
            return 0

    def query_business_rules(self, user_text: str, top_k: int = None) -> QueryResult:
        """相似度检索，三级容灾"""
        k = top_k or self.top_k
        try:
            return self._chroma_query(user_text, k)
        except Exception as e:
            logger.error(f"[StoreManager] 向量检索失败，降级: {e}")
            try:
                return self._keyword_query(user_text, k)
            except Exception as e2:
                logger.error(f"[StoreManager] 关键词降级失败: {e2}")
                return QueryResult(items=[], query=user_text, top_k=k, fallback=True)

    def _chroma_query(self, text: str, k: int) -> QueryResult:
        if not self._ready or self._collection is None:
            raise RuntimeError("ChromaDB 未就绪")
        count = self._collection.count()
        if count == 0:
            raise RuntimeError("ChromaDB 为空")
        query_emb = self._embed([text])
        results = self._collection.query(
            query_embeddings=query_emb,
            n_results=min(k, count),
            include=["metadatas", "distances"],
        )
        items = []
        for meta in results["metadatas"][0]:
            try:
                items.append(MenuItem(
                    name=meta.get("name", ""),
                    price=float(meta.get("price", 0)),
                    spec=meta.get("spec", ""),
                    floor_price=float(meta.get("floor_price", 0)),
                    description=meta.get("description", ""),
                ))
            except Exception:
                pass
        return QueryResult(items=items, query=text, top_k=k)

    def _keyword_query(self, text: str, k: int) -> QueryResult:
        """关键词降级检索"""
        scored = []
        for item in self._items:
            score = 0
            if item.name        in text: score += 10
            if item.description in text: score += 5
            if item.spec        in text: score += 2
            for ch in text:
                if ch in item.to_doc(): score += 1
            if score > 0:
                scored.append((score, item))
        scored.sort(key=lambda x: x[0], reverse=True)
        return QueryResult(items=[i for _, i in scored[:k]], query=text, top_k=k)

    def update_item(self, name: str, price: float = None, floor_price: float = None) -> bool:
        """更新单条菜品价格"""
        try:
            meta = {}
            if price       is not None: meta["price"]       = str(price)
            if floor_price is not None: meta["floor_price"] = str(floor_price)
            if meta and self._collection:
                self._collection.update(ids=[name], metadatas=[meta])
            for item in self._items:
                if item.name == name:
                    if price       is not None: item.price       = price
                    if floor_price is not None: item.floor_price = floor_price
            return True
        except Exception as e:
            logger.error(f"[StoreManager] 更新失败: {e}")
            return False

    @property
    def item_count(self) -> int:
        return len(self._items)

    @property
    def is_ready(self) -> bool:
        return self._ready

    def status(self) -> dict:
        chroma_count = 0
        if self._ready and self._collection:
            try:
                chroma_count = self._collection.count()
            except Exception:
                pass
        return {
            "ready":        self._ready,
            "item_count":   self.item_count,
            "chroma_count": chroma_count,
            "db_dir":       self.db_dir,
            "embed_model":  self.embed_model,
        }


_default_store: Optional[StoreManager] = None


def get_store(csv_path: str = "menu.csv", db_dir: str = _DB_DIR, top_k: int = 3) -> StoreManager:
    """全局单例"""
    global _default_store
    if _default_store is None:
        _default_store = StoreManager(db_dir=db_dir, top_k=top_k)
        if Path(csv_path).exists():
            _default_store.load_csv(csv_path)
    return _default_store


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s",
                        stream=sys.stdout)
    store = StoreManager()
    n = store.load_csv("menu.csv")
    print(f"\n加载: {n} 条  状态: {store.status()}")
    for q in ["牛肉面多少钱", "有没有素菜", "店里有什么规矩"]:
        print(f"\n[查询] {q}")
        print(store.query_business_rules(q).to_context())
    print("\n✅ 完成")
