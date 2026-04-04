from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, List, Optional

import networkx as nx
from llm_client import LLMClient
from config import settings
from shared.claw_protocol import TradeRequest

logger = logging.getLogger("claw.client.brain")

class PersonalBrain:
    """
    Project Claw - Personal Brain (C-side)
    基于 NetworkX 的本地个人知识图谱，管理用户隐性偏好。
    """

    def __init__(self, db_path: str = "./personal_graph.gml"):
        self.db_path = db_path
        self.graph = nx.MultiDiGraph()
        self._load_graph()
        
        self.llm = LLMClient(
            api_key=settings.DEEPSEEK_API_KEY,
            api_url=settings.DEEPSEEK_API_URL,
            model=settings.DEEPSEEK_MODEL,
            temperature=0.1,
            max_tokens=300
        )

    def _load_graph(self):
        if Path(self.db_path).exists():
            try:
                self.graph = nx.read_gml(self.db_path)
                logger.info(f"[PersonalBrain] 已加载知识图谱: {len(self.graph.nodes)} 节点")
            except Exception as e:
                logger.error(f"[PersonalBrain] 加载图谱失败: {e}")

    def _save_graph(self):
        try:
            nx.write_gml(self.graph, self.db_path)
        except Exception as e:
            logger.error(f"[PersonalBrain] 保存图谱失败: {e}")

    def ingest_memory(self, text: str):
        """
        用户日常输入提取实体关系并存入图谱。
        例如: '我穿42码鞋' -> (User, wears_size, 42_shoes)
        """
        prompt = (
            "你是一个知识图谱提取专家。从以下用户日常输入中提取实体关系三元组。\n"
            "只输出 JSON 数组，格式: [{\"subject\": \"...\", \"relation\": \"...\", \"object\": \"...\"}]\n"
            f"输入: {text}"
        )
        
        try:
            raw = self.llm.ask(prompt)
            # 简单清理 JSON
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()
                
            triples = json.loads(raw)
            for t in triples:
                s, r, o = t["subject"], t["relation"], t["object"]
                self.graph.add_edge(s, o, relation=r)
                logger.info(f"[PersonalBrain] 记录记忆: {s} --({r})--> {o}")
            
            self._save_graph()
        except Exception as e:
            logger.error(f"[PersonalBrain] 摄入记忆失败: {e}")

    def retrieve_context(self, item_name: str) -> str:
        """
        检索与特定商品相关的个人偏好上下文。
        """
        all_facts = []
        for u, v, data in self.graph.edges(data=True):
            all_facts.append(f"{u} {data.get('relation', 'related_to')} {v}")
            
        if not all_facts:
            return ""

        # 使用 LLM 筛选相关偏好
        prompt = (
            f"基于以下用户的个人事实库，筛选出与购买『{item_name}』相关的偏好信息（如尺寸、忌口、品牌偏好、预算习惯等）。\n"
            "直接输出简洁的约束短句，不要解释。如果没有相关信息，输出『无』。\n"
            "事实库:\n" + "\n".join(all_facts)
        )
        
        try:
            res = self.llm.ask(prompt).strip()
            return "" if "无" in res else res
        except Exception:
            return ""

class ContextInjector:
    """
    在发起 TradeRequest 前，通过图谱检索将隐性偏好打包进 A2A 询价 Payload。
    """
    def __init__(self, brain: PersonalBrain):
        self.brain = brain

    def inject(self, request: TradeRequest) -> TradeRequest:
        preference_context = self.brain.retrieve_context(request.item_name)
        if preference_context:
            # 将偏好注入需求描述中
            original_demand = request.demand_text or ""
            request.demand_text = f"{original_demand} (用户个人偏好约束: {preference_context})".strip()
            logger.info(f"[ContextInjector] 已为 {request.item_name} 注入偏好: {preference_context}")
        return request
