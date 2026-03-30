"""
Project Claw v14.0 - edge_box/local_memory.py
【B端】本地菜单 + 底价 RAG 检索

物理边界：
  - 只在 edge_box 内使用
  - 数据不出设备
"""
from __future__ import annotations

import csv
import logging
import os
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger("claw.edge.memory")


@dataclass
class MenuItem:
    name: str
    price: float
    floor_price: float
    spec: str = ""
    description: str = ""

    @property
    def margin(self) -> float:
        return (self.price - self.floor_price) / self.price if self.price else 0


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


class LocalMenuRAG:
    """
    本地菜单 RAG（商业版）：
      - 优先语义向量检索（sentence-transformers）
      - 自动降级关键词匹配（离线稳定）
    """

    def __init__(self, menu_csv: str = "menu.csv"):
        self.menu_csv = menu_csv
        self._items: List[MenuItem] = []
        self._emb_model = None
        self._emb_vectors = None
        self._semantic_ready = False
        self._load()
        self._init_semantic()

    def _load(self):
        if not os.path.exists(self.menu_csv):
            logger.warning(f"[LocalMenuRAG] 菜单文件不存在: {self.menu_csv}")
            return
        with open(self.menu_csv, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    item = MenuItem(
                        name=row.get("菜品名", "").strip(),
                        price=float(row.get("价格", 0)),
                        floor_price=float(row.get("底价", 0)),
                        spec=row.get("规格", ""),
                        description=row.get("描述", ""),
                    )
                    if item.name and item.price > 0:
                        self._items.append(item)
                except Exception as e:
                    logger.warning(f"[LocalMenuRAG] 行解析失败: {e}")
        logger.info(f"[LocalMenuRAG] 加载 {len(self._items)} 个菜品")

    def _init_semantic(self):
        """初始化语义检索（失败自动降级）"""
        if not self._items:
            return
        if os.getenv("SKIP_SEMANTIC_RAG", "0") == "1":
            logger.info("[LocalMenuRAG] SKIP_SEMANTIC_RAG=1，使用关键词匹配")
            return
        try:
            from sentence_transformers import SentenceTransformer
            import numpy as np

            self._emb_model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
            corpus = [f"{i.name} {i.spec} {i.description}".strip() for i in self._items]
            self._emb_vectors = np.array(
                self._emb_model.encode(corpus, normalize_embeddings=True, show_progress_bar=False)
            )
            self._semantic_ready = True
            logger.info(f"[LocalMenuRAG] 语义检索已启用，items={len(corpus)}")
        except Exception as e:
            self._semantic_ready = False
            logger.warning(f"[LocalMenuRAG] 语义模型不可用，降级关键词匹配: {e}")

    def _query_semantic(self, text: str) -> Optional[MenuItem]:
        if not self._semantic_ready or self._emb_model is None or self._emb_vectors is None:
            return None
        try:
            import numpy as np

            q = self._emb_model.encode([text], normalize_embeddings=True, show_progress_bar=False)[0]
            scores = self._emb_vectors @ q
            idx = int(np.argmax(scores))
            best_score = float(scores[idx])
            # 商业稳定阈值：低于阈值视为不匹配，避免幻觉报价
            if best_score < 0.35:
                return None
            return self._items[idx]
        except Exception as e:
            logger.warning(f"[LocalMenuRAG] 语义检索失败，降级关键词: {e}")
            return None

    def _query_keyword(self, text: str) -> Optional[MenuItem]:
        text_lower = text.lower()
        for item in self._items:
            if item.name in text or item.name.lower() in text_lower:
                return item
        return None

    def query(self, text: str) -> RAGResult:
        """语义优先，关键词兜底"""
        best = self._query_semantic(text) or self._query_keyword(text)
        if best is None:
            ctx = "本店菜单：\n" + "\n".join(
                f"  {i.name} {i.price}元（规格：{i.spec}）{i.description}" for i in self._items[:8]
            )
            return RAGResult(found=False, context_str=ctx)

        ctx = (
            f"菜品：{best.name}\n"
            f"正常价格：{best.price}元\n"
            f"规格：{best.spec}\n"
            f"描述：{best.description}"
        )
        return RAGResult(item=best, found=True, context_str=ctx)

    def get_all_context(self) -> str:
        return "\n".join(f"{i.name} {i.price}元" for i in self._items)
