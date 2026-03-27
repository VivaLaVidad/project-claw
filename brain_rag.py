"""
Project Claw v11.0 - RAG 检索模块

使用 ChromaDB 作为本地向量数据库，存储菜单/价格表。
当 IntentRouter 判断用户意图为「购买/点单」时，
RAG_Node 从 ChromaDB 检索最相关的菜品信息，
避免 LLM 幻觉报价。

扩展点：
- 支持从 Excel/JSON 批量导入菜单
- 支持多 Collection（菜单、活动、规则）
- 后期可替换为远程向量库（Pinecone/Weaviate）
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

# ChromaDB 懒加载，避免未安装时整个项目崩溃
try:
    import chromadb
    from chromadb.utils import embedding_functions
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    logger.warning("⚠️ chromadb 未安装，RAG 功能将降级为关键词检索")


# ==================== 数据模型 ====================

@dataclass
class MenuItem:
    """菜单项"""
    name: str
    price: float
    category: str
    description: str = ""
    available: bool = True
    tags: List[str] = field(default_factory=list)

    def to_doc(self) -> str:
        """转换为向量检索文档"""
        return (
            f"{self.name}，"
            f"{'可用' if self.available else '今日售罄'}，"
            f"价格：{self.price}元，"
            f"分类：{self.category}。"
            f"{self.description}"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "price": self.price,
            "category": self.category,
            "description": self.description,
            "available": self.available,
            "tags": ",".join(self.tags),
        }


@dataclass
class RAGResult:
    """RAG 检索结果"""
    items: List[MenuItem]
    query: str
    top_k: int

    def to_context(self) -> str:
        """转为 LLM 上下文字符串"""
        if not self.items:
            return "没有找到相关菜品信息。"
        lines = [f"以下是与「{self.query}」相关的菜品信息："]
        for item in self.items:
            status = "✅ 可点" if item.available else "❌ 今日售罄"
            lines.append(f"- {item.name}：{item.price}元 {status}  {item.description}")
        return "\n".join(lines)


# ==================== 默认菜单 ====================

DEFAULT_MENU: List[MenuItem] = [
    MenuItem("牛肉面", 18.0, "主食", "鲜嫩牛肉+秘制汤底", True, ["牛肉", "面"]),
    MenuItem("麻辣烫", 15.0, "主食", "自选食材，麻辣鲜香", True, ["辣", "烫"]),
    MenuItem("水饺", 8.0, "主食", "手工猪肉白菜馅", True, ["饺子", "猪肉"]),
    MenuItem("炒饭", 12.0, "主食", "蛋炒饭，配小咸菜", True, ["炒饭", "鸡蛋"]),
    MenuItem("凉皮", 10.0, "凉菜", "陕西风味，酸辣爽口", True, ["凉皮", "辣"]),
    MenuItem("豆浆", 3.0, "饮品", "现磨豆浆，香醇", True, ["豆浆", "早餐"]),
    MenuItem("可乐", 4.0, "饮品", "冰镇可乐", True, ["饮料", "冷饮"]),
    MenuItem("特价套餐A", 25.0, "套餐", "牛肉面+豆浆，节省5元", True, ["套餐", "优惠"]),
]


# ==================== RAG 引擎 ====================

class RAGEngine:
    """
    本地 RAG 检索引擎

    ChromaDB 可用时：使用语义向量检索（精准）
    ChromaDB 不可用时：使用关键词匹配降级（稳定）
    """

    def __init__(
        self,
        persist_dir: str = "./rag_db",
        collection_name: str = "menu",
        top_k: int = 3,
    ):
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        self.top_k = top_k
        self.menu_index: Dict[str, MenuItem] = {}
        self._client = None
        self._collection = None

        if CHROMA_AVAILABLE:
            self._init_chroma()
        else:
            logger.info("RAG 降级模式：关键词检索")

    def _init_chroma(self):
        """初始化 ChromaDB"""
        try:
            Path(self.persist_dir).mkdir(exist_ok=True)
            self._client = chromadb.PersistentClient(path=self.persist_dir)
            ef = embedding_functions.DefaultEmbeddingFunction()
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=ef,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(f"✅ ChromaDB 初始化完成 | Collection: {self.collection_name}")
        except Exception as e:
            logger.error(f"❌ ChromaDB 初始化失败，降级为关键词: {e}")
            self._collection = None

    def load_menu(self, items: List[MenuItem] = None):
        """加载菜单到向量库"""
        items = items or DEFAULT_MENU
        for item in items:
            self.menu_index[item.name] = item

        if self._collection is not None:
            try:
                existing = self._collection.get()["ids"]
                docs, ids, metas = [], [], []
                for item in items:
                    if item.name not in existing:
                        docs.append(item.to_doc())
                        ids.append(item.name)
                        metas.append(item.to_dict())
                if docs:
                    self._collection.add(documents=docs, ids=ids, metadatas=metas)
                    logger.info(f"✅ 新增 {len(docs)} 条菜单到 ChromaDB")
                else:
                    logger.info("ChromaDB 菜单已是最新，无需更新")
            except Exception as e:
                logger.error(f"❌ 菜单写入 ChromaDB 失败: {e}")
        else:
            logger.info(f"菜单关键词索引已加载 {len(items)} 条")

    def load_from_excel(self, path: str):
        """从 Excel 加载菜单"""
        try:
            import pandas as pd
            df = pd.read_excel(path)
            items = []
            for _, row in df.iterrows():
                items.append(MenuItem(
                    name=str(row.get("名称", "")),
                    price=float(row.get("价格", 0)),
                    category=str(row.get("分类", "其他")),
                    description=str(row.get("描述", "")),
                    available=bool(row.get("可用", True)),
                    tags=str(row.get("标签", "")).split(","),
                ))
            self.load_menu(items)
            logger.info(f"✅ 从 Excel 加载菜单 {len(items)} 条")
        except Exception as e:
            logger.error(f"❌ Excel 加载失败，使用默认菜单: {e}")
            self.load_menu()

    def query(self, text: str, top_k: int = None) -> RAGResult:
        """检索最相关菜品"""
        k = top_k or self.top_k

        if self._collection is not None:
            return self._chroma_query(text, k)
        return self._keyword_query(text, k)

    def _chroma_query(self, text: str, k: int) -> RAGResult:
        """ChromaDB 语义检索"""
        try:
            results = self._collection.query(
                query_texts=[text],
                n_results=min(k, self._collection.count()),
                include=["metadatas", "distances"],
            )
            items = []
            for meta in results["metadatas"][0]:
                name = meta.get("name", "")
                if name in self.menu_index:
                    items.append(self.menu_index[name])
                else:
                    items.append(MenuItem(
                        name=name,
                        price=float(meta.get("price", 0)),
                        category=meta.get("category", ""),
                        description=meta.get("description", ""),
                        available=meta.get("available", True),
                    ))
            return RAGResult(items=items, query=text, top_k=k)
        except Exception as e:
            logger.error(f"❌ ChromaDB 检索失败，降级: {e}")
            return self._keyword_query(text, k)

    def _keyword_query(self, text: str, k: int) -> RAGResult:
        """关键词匹配降级检索"""
        scored = []
        for name, item in self.menu_index.items():
            score = 0
            if name in text:
                score += 10
            for tag in item.tags:
                if tag in text:
                    score += 3
            if item.category in text:
                score += 2
            if item.description and any(w in text for w in item.description):
                score += 1
            if score > 0:
                scored.append((score, item))
        scored.sort(key=lambda x: x[0], reverse=True)
        items = [item for _, item in scored[:k]]
        return RAGResult(items=items, query=text, top_k=k)

    def update_availability(self, item_name: str, available: bool):
        """更新菜品可用状态"""
        if item_name in self.menu_index:
            self.menu_index[item_name].available = available
            if self._collection is not None:
                try:
                    self._collection.update(
                        ids=[item_name],
                        metadatas=[{"available": available}],
                    )
                except Exception as e:
                    logger.error(f"❌ ChromaDB 状态更新失败: {e}")
            logger.info(f"菜品状态更新: {item_name} = {'可用' if available else '售罄'}")
