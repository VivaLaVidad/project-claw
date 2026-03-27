"""
Project Claw - 虚拟匹配房间（Virtual Match Room）

当两个 C 端用户靠近时，系统在后台自动拉起一个虚拟房间。
两个用户的 Agent 在 0.1 秒内就开始辩论 5 个回合。
EvaluatorAgent 打分后，匹配度 >= 90% 才推送给真人。

设计原则：
- 线程安全，支持并发多个匹配房间
- 后期可接入 OpenClaw P2P 协议做跨设备真实 Agent 通信
- 支持 WebSocket 推送匹配结果到前端
"""
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional, Callable
from enum import Enum

from llm_client import LLMClient
from multi_agent_core import MatchingResult, UserProfile
from multi_agent_workflow import build_matching_workflow, run_matching

logger = logging.getLogger(__name__)


class RoomStatus(Enum):
    PENDING = "pending"       # 等待开始
    DEBATING = "debating"     # 辩论中
    EVALUATING = "evaluating" # 评估中
    MATCHED = "matched"       # 匹配成功
    REJECTED = "rejected"     # 匹配失败
    ERROR = "error"           # 发生错误


@dataclass
class MatchRoom:
    """虚拟匹配房间"""
    room_id: str
    user1_id: str
    user2_id: str
    user1_name: str
    user2_name: str
    status: RoomStatus = RoomStatus.PENDING
    result: Optional[MatchingResult] = None
    created_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    error: Optional[str] = None

    @property
    def duration(self) -> Optional[float]:
        if self.finished_at:
            return self.finished_at - self.created_at
        return None


class VirtualMatchRoom:
    """
    虚拟匹配房间管理器

    职责：
    1. 接收两个用户 ID，拉起一个后台匹配任务
    2. 异步执行辩论 + 评估
    3. 匹配度 >= 90% 时回调通知前端/真人
    4. 维护所有房间的状态记录
    """

    def __init__(
        self,
        llm: LLMClient,
        max_rounds: int = 5,
        match_threshold: float = 90.0,
        on_match: Callable[[MatchRoom], None] = None,
        on_reject: Callable[[MatchRoom], None] = None,
    ):
        self.llm = llm
        self.match_threshold = match_threshold
        self.on_match = on_match or self._default_on_match
        self.on_reject = on_reject or self._default_on_reject
        self.rooms: Dict[str, MatchRoom] = {}
        self._lock = threading.Lock()

        # 构建可复用的匹配工作流
        self._workflow = build_matching_workflow(
            llm=llm,
            max_rounds=max_rounds,
            match_threshold=match_threshold,
        )
        logger.info("VirtualMatchRoom 初始化完成")

    # ==================== 公开接口 ====================

    def trigger_match(
        self,
        user1_id: str,
        user2_id: str,
        user1_name: str = None,
        user2_name: str = None,
    ) -> str:
        """
        触发匹配（异步，立即返回 room_id）
        调用方可用 room_id 查询进度。
        """
        room_id = str(uuid.uuid4())[:8]
        room = MatchRoom(
            room_id=room_id,
            user1_id=user1_id,
            user2_id=user2_id,
            user1_name=user1_name or f"用户{user1_id[:4]}",
            user2_name=user2_name or f"用户{user2_id[:4]}",
        )

        with self._lock:
            self.rooms[room_id] = room

        logger.info(f"[Room {room_id}] 创建: {room.user1_name} <-> {room.user2_name}")

        # 后台线程执行匹配
        thread = threading.Thread(
            target=self._run_match,
            args=(room,),
            daemon=True,
            name=f"MatchRoom-{room_id}",
        )
        thread.start()

        return room_id

    def get_room(self, room_id: str) -> Optional[MatchRoom]:
        """查询房间状态"""
        return self.rooms.get(room_id)

    def get_all_rooms(self) -> Dict[str, MatchRoom]:
        """获取所有房间记录"""
        with self._lock:
            return dict(self.rooms)

    def stats(self) -> dict:
        """统计信息"""
        rooms = list(self.rooms.values())
        return {
            "total": len(rooms),
            "matched": sum(1 for r in rooms if r.status == RoomStatus.MATCHED),
            "rejected": sum(1 for r in rooms if r.status == RoomStatus.REJECTED),
            "pending": sum(1 for r in rooms if r.status == RoomStatus.PENDING),
            "debating": sum(1 for r in rooms if r.status == RoomStatus.DEBATING),
            "error": sum(1 for r in rooms if r.status == RoomStatus.ERROR),
            "avg_duration": self._avg_duration(rooms),
        }

    # ==================== 内部逻辑 ====================

    def _run_match(self, room: MatchRoom):
        """在后台线程中执行匹配工作流"""
        try:
            room.status = RoomStatus.DEBATING
            logger.info(f"[Room {room.room_id}] 开始辩论...")

            result = run_matching(
                workflow=self._workflow,
                user1_id=room.user1_id,
                user2_id=room.user2_id,
                user1_name=room.user1_name,
                user2_name=room.user2_name,
            )

            room.status = RoomStatus.EVALUATING
            room.result = result
            room.finished_at = time.time()

            if result and result.is_match:
                room.status = RoomStatus.MATCHED
                logger.info(
                    f"[Room {room.room_id}] ✅ 匹配成功! "
                    f"分数: {result.compatibility_score:.1f}% | "
                    f"耗时: {room.duration:.2f}s"
                )
                self.on_match(room)
            else:
                room.status = RoomStatus.REJECTED
                score = result.compatibility_score if result else 0
                logger.info(
                    f"[Room {room.room_id}] ❌ 未达标 "
                    f"分数: {score:.1f}% | "
                    f"耗时: {room.duration:.2f}s"
                )
                self.on_reject(room)

        except Exception as e:
            room.status = RoomStatus.ERROR
            room.error = str(e)
            room.finished_at = time.time()
            logger.error(f"[Room {room.room_id}] 错误: {e}")

    def _default_on_match(self, room: MatchRoom):
        """默认匹配成功回调（打印日志，可替换为 WebSocket 推送）"""
        result = room.result
        logger.info(
            f"\n{'='*50}\n"
            f"🎉 匹配成功通知\n"
            f"用户 A: {room.user1_name} ({room.user1_id})\n"
            f"用户 B: {room.user2_name} ({room.user2_id})\n"
            f"匹配度: {result.compatibility_score:.1f}%\n"
            f"  消费观: {result.consumption_match:.1f}%\n"
            f"  恋爱观: {result.love_match:.1f}%\n"
            f"评价: {result.evaluator_feedback}\n"
            f"耗时: {room.duration:.2f}s\n"
            f"{'='*50}"
        )

    def _default_on_reject(self, room: MatchRoom):
        """默认未匹配回调"""
        score = room.result.compatibility_score if room.result else 0
        logger.info(
            f"[Room {room.room_id}] 用户未匹配 "
            f"({room.user1_name} <-> {room.user2_name}) "
            f"分数: {score:.1f}%"
        )

    def _avg_duration(self, rooms) -> float:
        finished = [r.duration for r in rooms if r.duration is not None]
        return sum(finished) / len(finished) if finished else 0.0
