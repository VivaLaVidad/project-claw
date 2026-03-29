"""Project Claw 人工干预分流系统 - cloud_server/hitl_triage.py"""
import asyncio, logging, json, time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
import redis.asyncio as redis
from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter()

class TriageLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class TriageRule:
    rule_id: str
    name: str
    condition: str  # 条件表达式
    triage_level: TriageLevel
    auto_approve: bool = False
    priority: int = 0

class HITLTriage:
    """人工干预分流系统"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.redis_client = None
        self.rules: Dict[str, TriageRule] = {}
    
    async def init(self):
        """初始化"""
        self.redis_client = await redis.from_url(self.redis_url)
        await self._load_rules()
        logger.info("✓ HITL 分流系统已初始化")
    
    async def _load_rules(self):
        """加载分流规则"""
        try:
            rules_data = await self.redis_client.get("triage_rules")
            if rules_data:
                rules_dict = json.loads(rules_data)
                for rule_id, rule_data in rules_dict.items():
                    self.rules[rule_id] = TriageRule(**rule_data)
            logger.info(f"✓ 加载 {len(self.rules)} 条分流规则")
        except Exception as e:
            logger.error(f"加载分流规则失败: {e}")
    
    async def add_rule(self, rule: TriageRule) -> bool:
        """添加分流规则"""
        try:
            self.rules[rule.rule_id] = rule
            
            # 保存到 Redis
            rules_dict = {rid: asdict(r) for rid, r in self.rules.items()}
            await self.redis_client.set(
                "triage_rules",
                json.dumps(rules_dict)
            )
            
            logger.info(f"✓ 分流规则已添加: {rule.name}")
            return True
        except Exception as e:
            logger.error(f"添加分流规则失败: {e}")
            return False
    
    async def evaluate_task(self, task_data: Dict[str, Any]) -> TriageLevel:
        """评估任务的分流级别"""
        try:
            # 提取关键指标
            confidence = task_data.get("confidence", 1.0)
            box_status = task_data.get("box_status", "idle")
            task_complexity = task_data.get("task_complexity", "low")
            
            # 应用分流规则
            triage_level = TriageLevel.LOW
            
            # 规则 1: 低置信度 -> 高优先级
            if confidence < 0.5:
                triage_level = TriageLevel.CRITICAL
            elif confidence < 0.7:
                triage_level = TriageLevel.HIGH
            elif confidence < 0.85:
                triage_level = TriageLevel.MEDIUM
            
            # 规则 2: 盒子错误状态 -> 提升优先级
            if box_status == "error":
                triage_level = TriageLevel.CRITICAL
            
            # 规则 3: 复杂任务 -> 提升优先级
            if task_complexity == "high":
                if triage_level == TriageLevel.LOW:
                    triage_level = TriageLevel.MEDIUM
                elif triage_level == TriageLevel.MEDIUM:
                    triage_level = TriageLevel.HIGH
            
            logger.info(f"任务分流级别: {triage_level.value} (置信度: {confidence})")
            return triage_level
        
        except Exception as e:
            logger.error(f"评估任务失败: {e}")
            return TriageLevel.HIGH
    
    async def route_to_queue(
        self,
        task_id: str,
        triage_level: TriageLevel,
        task_data: Dict[str, Any]
    ) -> bool:
        """将任务路由到相应的队列"""
        try:
            queue_name = f"triage_queue:{triage_level.value}"
            
            # 添加到队列
            await self.redis_client.lpush(
                queue_name,
                json.dumps({
                    "task_id": task_id,
                    "data": task_data,
                    "timestamp": time.time()
                })
            )
            
            # 设置队列过期时间
            await self.redis_client.expire(queue_name, 86400)
            
            logger.info(f"✓ 任务已路由到队列: {queue_name}")
            return True
        
        except Exception as e:
            logger.error(f"路由任务失败: {e}")
            return False
    
    async def get_queue_stats(self) -> Dict[str, int]:
        """获取各队列统计"""
        try:
            stats = {}
            for level in TriageLevel:
                queue_name = f"triage_queue:{level.value}"
                count = await self.redis_client.llen(queue_name)
                stats[level.value] = count
            return stats
        except Exception as e:
            logger.error(f"获取队列统计失败: {e}")
            return {}
    
    async def close(self):
        """关闭连接"""
        if self.redis_client:
            await self.redis_client.close()
        logger.info("✓ HITL 分流系统已关闭")

# 全局实例
triage_system = HITLTriage()

@router.post("/hitl/triage/rules")
async def add_triage_rule(rule_data: Dict[str, Any]):
    """添加分流规则"""
    try:
        rule = TriageRule(**rule_data)
        success = await triage_system.add_rule(rule)
        
        if success:
            return {"success": True, "message": "规则已添加"}
        else:
            raise HTTPException(status_code=500, detail="添加规则失败")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/hitl/triage/rules")
async def get_triage_rules():
    """获取所有分流规则"""
    try:
        rules = [asdict(r) for r in triage_system.rules.values()]
        return {"success": True, "data": rules}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/hitl/triage/evaluate")
async def evaluate_task(task_data: Dict[str, Any]):
    """评估任务分流级别"""
    try:
        triage_level = await triage_system.evaluate_task(task_data)
        return {"success": True, "triage_level": triage_level.value}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/hitl/triage/stats")
async def get_triage_stats():
    """获取分流队列统计"""
    try:
        stats = await triage_system.get_queue_stats()
        return {"success": True, "data": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/hitl/triage/queue/{level}")
async def get_queue_tasks(level: str, limit: int = 50):
    """获取指定级别队列的任务"""
    try:
        queue_name = f"triage_queue:{level}"
        tasks = await triage_system.redis_client.lrange(queue_name, 0, limit - 1)
        
        task_list = [json.loads(t.decode()) for t in tasks]
        return {"success": True, "data": task_list}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
