from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Literal, Optional, TypedDict

from langgraph.graph import END, StateGraph

_PRICE_RE = re.compile(r'-?\d+(?:\.\d+)?')


class MemoryStorage:
    def __init__(self) -> None:
        self.items: List[Dict[str, Any]] = []

    def append(self, payload: Dict[str, Any]) -> None:
        self.items.append(payload)

    def tail(self, limit: int = 8) -> List[Dict[str, Any]]:
        return self.items[-limit:]


@dataclass
class AgentInstance:
    name: str
    role: str
    system_prompt: str
    memory: MemoryStorage = field(default_factory=MemoryStorage)


class AgentBus:
    def __init__(self) -> None:
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}

    async def publish(self, topic: str, message: Dict[str, Any]) -> None:
        for queue in self._subscribers.get(topic, []):
            await queue.put(message)

    def subscribe(self, topic: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.setdefault(topic, []).append(queue)
        return queue


class NegotiationState(TypedDict, total=False):
    session_id: str
    client_id: str
    merchant_id: str
    item_name: str
    expected_price: float
    buyer_price: float
    merchant_offer: float
    inventory_price: float
    inventory_stock: int
    round_count: int
    max_rounds: int
    final_deal: bool
    status: str
    final_gap: float
    moderator_decision: str
    transcript: List[Dict[str, Any]]
    client_profile: Dict[str, Any]
    merchant_profile: Dict[str, Any]
    priority_context: str


class InventoryNode:
    def lookup(self, item_name: str, merchant_profile: Dict[str, Any], expected_price: float) -> Dict[str, Any]:
        inventory = merchant_profile.get('inventory') or {}
        stock = int(inventory.get(item_name, inventory.get('default', 20)) or 20)
        strategy = str(merchant_profile.get('pricing_strategy', 'normal'))
        multiplier = 1.08 if strategy == 'aggressive' else (0.96 if strategy == 'conservative' else 1.02)
        base = max(expected_price * multiplier, expected_price + 1.0)
        if stock <= 3:
            base += 1.5
        return {'inventory_price': round(base, 2), 'inventory_stock': stock}


class MultiAgentNegotiationCluster:
    def __init__(self, llm_client: Any, agents_dir: Path):
        self.llm_client = llm_client
        self.agents_dir = Path(agents_dir)
        self.agent_bus = AgentBus()
        self.inventory_node = InventoryNode()
        self.agents = self._load_agents()
        self.graph = self._build_graph()

    def _load_agents(self) -> Dict[str, AgentInstance]:
        agents: Dict[str, AgentInstance] = {}
        for path in sorted(self.agents_dir.glob('*.y*ml')):
            raw = path.read_text(encoding='utf-8')
            parsed = self._parse_simple_yaml(raw)
            agent = AgentInstance(
                name=str(parsed.get('name') or path.stem),
                role=str(parsed.get('role') or path.stem),
                system_prompt=str(parsed.get('system_prompt') or ''),
            )
            agents[agent.name] = agent
        return agents

    def _parse_simple_yaml(self, text: str) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        lines = text.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i]
            if not line.strip() or line.strip().startswith('#'):
                i += 1
                continue
            if ':' not in line:
                i += 1
                continue
            key, value = line.split(':', 1)
            key = key.strip()
            value = value.strip()
            if value == '|':
                i += 1
                block: List[str] = []
                while i < len(lines):
                    nxt = lines[i]
                    if nxt.startswith('  '):
                        block.append(nxt[2:])
                        i += 1
                        continue
                    break
                data[key] = '\n'.join(block).strip()
                continue
            data[key] = value.strip('"\'')
            i += 1
        return data

    def _build_graph(self):
        graph = StateGraph(NegotiationState)
        graph.add_node('buyer', self._buyer_node)
        graph.add_node('merchant', self._merchant_node)
        graph.add_node('moderator', self._moderator_node)
        graph.add_node('final_deal', self._final_deal_node)
        graph.set_entry_point('buyer')
        graph.add_edge('buyer', 'merchant')
        graph.add_edge('merchant', 'moderator')
        graph.add_conditional_edges('moderator', self._route_after_moderator, {
            'deal': 'final_deal',
            'retry': 'buyer',
            'abort': END,
        })
        graph.add_edge('final_deal', END)
        return graph.compile()

    async def run(self, *, session_id: str, client_id: str, merchant_id: str, item_name: str, expected_price: float,
                  client_profile: Dict[str, Any], merchant_profile: Dict[str, Any], priority_context: str = '',
                  max_rounds: int = 6) -> Dict[str, Any]:
        state: NegotiationState = {
            'session_id': session_id,
            'client_id': client_id,
            'merchant_id': merchant_id,
            'item_name': item_name,
            'expected_price': float(expected_price),
            'buyer_price': float(expected_price),
            'merchant_offer': 0.0,
            'inventory_price': 0.0,
            'inventory_stock': 0,
            'round_count': 0,
            'max_rounds': int(max_rounds),
            'final_deal': False,
            'status': 'active',
            'final_gap': 0.0,
            'moderator_decision': '',
            'transcript': [],
            'client_profile': client_profile,
            'merchant_profile': merchant_profile,
            'priority_context': priority_context,
        }
        result = await self.graph.ainvoke(state)
        return dict(result)

    async def _buyer_node(self, state: NegotiationState) -> NegotiationState:
        state['round_count'] = int(state.get('round_count', 0)) + 1
        buyer_price = float(state['buyer_price'])
        llm_data = await self._ask_agent(
            'BuyerAgent',
            state,
            fallback={
                'thought': f'目标价控制在 {buyer_price:.2f} 元附近，争取更低成交。',
                'action': 'Create TradeRequest',
                'message': f"我想买 {state['item_name']}，我的目标价是 {buyer_price:.2f} 元。",
                'proposed_price': buyer_price,
            },
            user_prompt=(
                f"item_name={state['item_name']}; target_price={buyer_price}; "
                f"priority_context={state.get('priority_context', '')}; client_profile={json.dumps(state.get('client_profile', {}), ensure_ascii=False)}"
            ),
        )
        state['buyer_price'] = float(llm_data.get('proposed_price', buyer_price) or buyer_price)
        await self._emit('buyer', state, str(llm_data.get('thought', '正在争取更优价格。')),
                         str(llm_data.get('action', 'Create TradeRequest')),
                         str(llm_data.get('message', '我想发起询价。')), float(state['buyer_price']))
        return state

    async def _merchant_node(self, state: NegotiationState) -> NegotiationState:
        inv = self.inventory_node.lookup(state['item_name'], state.get('merchant_profile', {}), float(state['expected_price']))
        state.update(inv)
        floor = float(inv['inventory_price'])
        buyer_price = float(state.get('buyer_price', state['expected_price']))
        offer = max(floor, round((buyer_price + floor) / 2 + 0.8, 2))
        resistance = f"我要守住底价 {floor:.2f} 元和库存 {int(inv['inventory_stock'])} 份的压力。"
        llm_data = await self._ask_agent(
            'MerchantAgent',
            state,
            fallback={
                'thought': f'库存和策略要求我至少守住 {floor:.2f} 元。',
                'action': 'Generate MerchantOffer',
                'message': f"{state['item_name']} 我可以给到 {offer:.2f} 元，已经是当前很有诚意的价格。",
                'proposed_price': offer,
                'resistance': resistance,
            },
            user_prompt=(
                f"buyer_price={buyer_price}; inventory_price={floor}; inventory_stock={inv['inventory_stock']}; "
                f"priority_context={state.get('priority_context','')}; merchant_profile={json.dumps(state.get('merchant_profile', {}), ensure_ascii=False)}"
            ),
        )
        state['merchant_offer'] = max(floor, float(llm_data.get('proposed_price', offer)))
        await self._emit('merchant', state, str(llm_data.get('thought', '正在守住可成交利润。')),
                         str(llm_data.get('action', 'Generate MerchantOffer')),
                         str(llm_data.get('message', '这是我的报价。')),
                         float(state['merchant_offer']), resistance=str(llm_data.get('resistance', resistance)))
        return state

    async def _moderator_node(self, state: NegotiationState) -> NegotiationState:
        buyer_price = float(state.get('buyer_price', state['expected_price']))
        merchant_offer = float(state.get('merchant_offer', buyer_price))
        gap = round(abs(merchant_offer - buyer_price), 2)
        llm_data = await self._ask_agent(
            'ModeratorAgent',
            state,
            fallback={
                'thought': '我正在评估双方价格是否接近到可以成交。',
                'action': 'Assess gap',
                'gap': gap,
                'decision': 'deal' if gap < 2 else 'retry',
                'message': '差价已足够接近，可以成交。' if gap < 2 else '差价仍然较大，继续协调。',
            },
            user_prompt=f"buyer_price={buyer_price}; merchant_offer={merchant_offer}; gap={gap}",
        )
        state['final_gap'] = float(llm_data.get('gap', gap) or gap)
        decision = str(llm_data.get('decision', 'retry')).lower()
        if state['final_gap'] < 2:
            decision = 'deal'
        elif int(state.get('round_count', 0)) >= int(state.get('max_rounds', 6)):
            decision = 'abort'
            state['status'] = 'failed'
        else:
            midpoint = round((buyer_price + merchant_offer) / 2, 2)
            state['buyer_price'] = midpoint
            state['status'] = 'active'
        state['moderator_decision'] = decision
        await self._emit('moderator', state, str(llm_data.get('thought', '正在协调双方分歧。')),
                         str(llm_data.get('action', 'Moderate negotiation')),
                         str(llm_data.get('message', '继续推进谈判。')), merchant_offer, gap=state['final_gap'], decision=decision)
        return state

    async def _final_deal_node(self, state: NegotiationState) -> NegotiationState:
        buyer_price = float(state.get('buyer_price', state['expected_price']))
        merchant_offer = float(state.get('merchant_offer', buyer_price))
        deal_price = round((buyer_price + merchant_offer) / 2, 2)
        state['deal_price'] = deal_price
        state['final_deal'] = True
        state['status'] = 'completed'
        await self._emit('final_deal', state, '双方价格差已满足成交阈值。', 'Trigger FinalDeal',
                         f"达成协议，最终成交价 {deal_price:.2f} 元。", deal_price, gap=state.get('final_gap', 0.0), decision='deal')
        return state

    def _route_after_moderator(self, state: NegotiationState) -> Literal['deal', 'retry', 'abort']:
        decision = str(state.get('moderator_decision', 'retry')).lower()
        if decision == 'deal':
            return 'deal'
        if decision == 'abort':
            return 'abort'
        return 'retry'

    async def _emit(self, stage: str, state: NegotiationState, thought: str, action: str, message: str, price: float,
                    *, resistance: str = '', gap: float | None = None, decision: str = '') -> None:
        ts = time.time()
        agent_name = {
            'buyer': 'BuyerAgent',
            'merchant': 'MerchantAgent',
            'moderator': 'ModeratorAgent',
            'final_deal': 'FinalDeal',
        }.get(stage, stage)
        event = {
            'speaker': stage + '_agent' if stage in {'buyer', 'merchant', 'moderator'} else stage,
            'agent_name': agent_name,
            'thought': thought,
            'action': action,
            'message': message,
            'price': round(float(price), 2),
            'gap': gap,
            'decision': decision,
            'timestamp': ts,
        }
        if resistance:
            event['resistance'] = resistance
        state.setdefault('transcript', []).append(event)
        print(f"{agent_name}: Thought: {thought} | Action: {action}")
        if stage == 'buyer':
            print(f"[Buyer Thinking] {thought}")
        elif stage == 'merchant':
            print(f"[Merchant Resisting] {resistance or thought}")
        await self.agent_bus.publish(f"session:{state['session_id']}", event)
        agent = self.agents.get(agent_name)
        if agent:
            agent.memory.append(event)

    async def _ask_agent(self, agent_name: str, state: NegotiationState, fallback: Dict[str, Any], user_prompt: str) -> Dict[str, Any]:
        agent = self.agents.get(agent_name)
        if not agent or self.llm_client is None:
            return fallback
        system_prompt = agent.system_prompt
        if agent_name == 'BuyerAgent':
            buyer_system_prompt = str((state.get('client_profile') or {}).get('buyer_system_prompt', '')).strip()
            if buyer_system_prompt:
                system_prompt = f"{system_prompt}\n\nPersona Override:\n{buyer_system_prompt}"
        elif agent_name == 'MerchantAgent':
            merchant_profile = state.get('merchant_profile') or {}
            sales_system_prompt = str(merchant_profile.get('sales_system_prompt', '')).strip()
            bottom_line_rules = merchant_profile.get('bottom_line_rules') or []
            if sales_system_prompt or bottom_line_rules:
                rules_text = '；'.join(str(x).strip() for x in bottom_line_rules if str(x).strip())
                system_prompt = (
                    f"{system_prompt}\n\nPersona Override:\n{sales_system_prompt}"
                    f"\nBottom Line Rules: {rules_text or '无'}"
                )
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt + f"\nrecent_memory={json.dumps(agent.memory.tail(), ensure_ascii=False)}"},
        ]
        try:
            if hasattr(self.llm_client, 'ask_messages'):
                raw = await asyncio.to_thread(self.llm_client.ask_messages, messages, 0.2)
            elif hasattr(self.llm_client, 'chat'):
                raw = await asyncio.to_thread(self.llm_client.chat, messages)
            else:
                return fallback
            if not raw:
                return fallback
            parsed = self._parse_json(raw)
            return {**fallback, **parsed}
        except Exception:
            return fallback

    def _parse_json(self, raw: str) -> Dict[str, Any]:
        text = raw.strip()
        if '```json' in text:
            text = text.split('```json', 1)[1].split('```', 1)[0].strip()
        elif '```' in text:
            text = text.split('```', 1)[1].split('```', 1)[0].strip()
        try:
            return json.loads(text)
        except Exception:
            match = _PRICE_RE.search(text)
            return {'message': text, 'proposed_price': float(match.group(0)) if match else None}



