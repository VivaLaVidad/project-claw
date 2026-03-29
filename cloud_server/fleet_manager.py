"""Project Claw 多智能体指挥中心 - cloud_server/fleet_manager.py"""
import asyncio, logging, json, time, uuid
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
import redis.asyncio as redis
import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)

class AgentStatus(str, Enum):
    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"
    SUSPENDED = "suspended"

class TaskStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    OVERRIDDEN = "overridden"
    EXECUTING = "executing"
    COMPLETED = "completed"

@dataclass
class EdgeBoxTelemetry:
    box_id: str
    status: AgentStatus
    daily_orders: int
    timestamp: float
    confidence: float = 1.0
    current_task_id: Optional[str] = None

@dataclass
class SuspendedTask:
    task_id: str
    box_id: str
    state_data: Dict[str, Any]
    reason: str
    confidence: float
    created_at: float
    requires_approval: bool = True

@dataclass
class ApprovalDecision:
    task_id: str
    decision: str  # "accept", "override", "reject"
    override_params: Optional[Dict[str, Any]] = None
    notes: str = ""
    approved_by: str = ""
    approved_at: float = 0.0

class FleetManager:
    """多智能体指挥中心"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.redis_client = None
        self.mqtt_client = None
        self.boxes: Dict[str, EdgeBoxTelemetry] = {}
        self.suspended_tasks: Dict[str, SuspendedTask] = {}
    
    async def init(self):
        """初始化"""
        self.redis_client = await redis.from_url(self.redis_url)
        logger.info("✓ Redis 连接成功")
        
        # 初始化 MQTT
        self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
        self.mqtt_client.on_connect = self._on_mqtt_connect
        self.mqtt_client.on_message = self._on_mqtt_message
        self.mqtt_client.connect("localhost", 1883, 60)
        self.mqtt_client.loop_start()
        logger.info("✓ MQTT 连接成功")
    
    def _on_mqtt_connect(self, client, userdata, flags, rc):
        """MQTT 连接回调"""
        if rc == 0:
            logger.info("MQTT 已连接")
            client.subscribe("edge_box/telemetry/#")
        else:
            logger.error(f"MQTT 连接失败: {rc}")
    
    def _on_mqtt_message(self, client, userdata, msg):
        """MQTT 消息回调"""
        try:
            payload = json.loads(msg.payload.decode())
            box_id = payload.get("box_id")
            
            # 更新盒子状态
            telemetry = EdgeBoxTelemetry(
                box_id=box_id,
                status=AgentStatus(payload.get("status", "idle")),
                daily_orders=payload.get("daily_orders", 0),
                timestamp=time.time(),
                confidence=payload.get("confidence", 1.0),
                current_task_id=payload.get("current_task_id")
            )
            
            self.boxes[box_id] = telemetry
            logger.info(f"更新盒子状态: {box_id} - {telemetry.status.value}")
        
        except Exception as e:
            logger.error(f"处理 MQTT 消息失败: {e}")
    
    async def register_suspended_task(self, task: SuspendedTask) -> bool:
        """注册挂起的任务"""
        try:
            # 保存到 Redis
            task_key = f"suspended_task:{task.task_id}"
            await self.redis_client.set(
                task_key,
                json.dumps(asdict(task)),
                ex=86400  # 24 小时过期
            )
            
            # 添加到待审批队列
            await self.redis_client.lpush(
                "hitl_pending_queue",
                task.task_id
            )
            
            # 本地缓存
            self.suspended_tasks[task.task_id] = task
            
            logger.info(f"✓ 任务已挂起: {task.task_id} (置信度: {task.confidence})")
            return True
        
        except Exception as e:
            logger.error(f"注册挂起任务失败: {e}")
            return False
    
    async def get_pending_tasks(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取所有待审批任务"""
        try:
            # 从 Redis 获取任务 ID
            task_ids = await self.redis_client.lrange("hitl_pending_queue", 0, limit - 1)
            
            tasks = []
            for task_id in task_ids:
                task_key = f"suspended_task:{task_id.decode()}"
                task_data = await self.redis_client.get(task_key)
                
                if task_data:
                    task = json.loads(task_data)
                    tasks.append(task)
            
            logger.info(f"获取 {len(tasks)} 个待审批任务")
            return tasks
        
        except Exception as e:
            logger.error(f"获取待审批任务失败: {e}")
            return []
    
    async def approve_task(self, decision: ApprovalDecision) -> bool:
        """批准任务"""
        try:
            # 保存决策
            decision.approved_at = time.time()
            decision_key = f"approval_decision:{decision.task_id}"
            await self.redis_client.set(
                decision_key,
                json.dumps(asdict(decision)),
                ex=86400
            )
            
            # 发布到 Redis Pub/Sub
            channel = f"task_approval:{decision.task_id}"
            await self.redis_client.publish(
                channel,
                json.dumps(asdict(decision))
            )
            
            # 从待审批队列移除
            await self.redis_client.lrem("hitl_pending_queue", 1, decision.task_id)
            
            logger.info(f"✓ 任务已批准: {decision.task_id} ({decision.decision})")
            return True
        
        except Exception as e:
            logger.error(f"批准任务失败: {e}")
            return False
    
    async def get_fleet_status(self) -> Dict[str, Any]:
        """获取整个舰队状态"""
        try:
            total_boxes = len(self.boxes)
            idle_boxes = sum(1 for b in self.boxes.values() if b.status == AgentStatus.IDLE)
            busy_boxes = sum(1 for b in self.boxes.values() if b.status == AgentStatus.BUSY)
            error_boxes = sum(1 for b in self.boxes.values() if b.status == AgentStatus.ERROR)
            suspended_boxes = sum(1 for b in self.boxes.values() if b.status == AgentStatus.SUSPENDED)
            
            total_orders = sum(b.daily_orders for b in self.boxes.values())
            avg_confidence = sum(b.confidence for b in self.boxes.values()) / total_boxes if total_boxes > 0 else 0
            
            pending_tasks_count = await self.redis_client.llen("hitl_pending_queue")
            
            return {
                "total_boxes": total_boxes,
                "idle_boxes": idle_boxes,
                "busy_boxes": busy_boxes,
                "error_boxes": error_boxes,
                "suspended_boxes": suspended_boxes,
                "total_orders": total_orders,
                "avg_confidence": avg_confidence,
                "pending_tasks": pending_tasks_count,
                "boxes": [asdict(b) for b in self.boxes.values()]
            }
        
        except Exception as e:
            logger.error(f"获取舰队状态失败: {e}")
            return {}
    
    async def close(self):
        """关闭连接"""
        if self.redis_client:
            await self.redis_client.close()
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
        logger.info("✓ 连接已关闭")
