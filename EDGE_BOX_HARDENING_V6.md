# Project Claw Edge Box 工业级加固方案 v6.0
# 应对断电、断网、客诉合规审查

## 🔒 三大加固模块

### 1️⃣ 不可篡改审计追踪 (crypto_logger.py)

**核心特性：**
- ✅ SHA-256 哈希链式签名（区块链式）
- ✅ HMAC 数字签名防篡改
- ✅ SQLite 本地审计数据库
- ✅ 完整的事件链追踪

**关键事件类型：**
```
TRADE_EXECUTE    → 交易达成事件
PHYSICAL_ACTION  → 微信发送、支付验证
PAYMENT_VERIFY   → 支付验证事件
OVERRIDE_COMMAND → 手动覆盖命令
SYSTEM_ERROR     → 系统错误事件
```

**使用示例：**
```python
from edge_box.crypto_logger import get_crypto_logger

logger = get_crypto_logger()

# 记录交易执行
event_id = logger.log_trade_execute(
    intent_id="550e8400-e29b-41d4-a716-446655440000",
    merchant_id="box-001",
    client_id="c_xxx",
    price=12.5,
    action="PAYMENT_SENT",
    details={'payment_method': 'wechat', 'order_id': 'xxx'}
)

# 记录物理操作
logger.log_physical_action(
    intent_id="550e8400-e29b-41d4-a716-446655440000",
    merchant_id="box-001",
    client_id="c_xxx",
    price=12.5,
    action="WECHAT_SEND",
    details={'message': 'Payment received', 'status': 'sent'}
)

# 验证审计追踪完整性
is_valid = logger.verify_audit_trail()

# 导出合规审查报告
report = logger.export_audit_report(
    merchant_id="box-001",
    start_time=time.time() - 86400,  # 过去 24 小时
    end_time=time.time()
)

# 获取特定交易的完整事件链
event_chain = logger.get_event_chain("550e8400-e29b-41d4-a716-446655440000")
```

**审计数据库结构：**
```sql
audit_events:
  - event_id (主键)
  - event_type (事件类型)
  - timestamp (时间戳)
  - intent_id (意图ID)
  - merchant_id (商家ID)
  - client_id (客户ID)
  - price (价格)
  - action (动作)
  - details (详细信息 JSON)
  - previous_hash (前一个事件哈希)
  - event_hash (当前事件哈希)
  - signature (HMAC 签名)
```

---

### 2️⃣ 内存盘保护策略 (ramdisk_logger.py)

**核心特性：**
- ✅ 高频日志写入内存盘（/dev/shm）
- ✅ 防止 eMMC 闪存烧毁
- ✅ 自动缓冲和批量写入
- ✅ 自动清理过期日志

**保护的日志类型：**
```
UI 扫描心跳      → 高频（每秒多次）
连接检查心跳     → 高频（每秒）
系统监控心跳     → 高频（每秒）
```

**使用示例：**
```python
from edge_box.ramdisk_logger import get_ramdisk_logger

ramdisk = get_ramdisk_logger()

# 记录 UI 扫描心跳（高频，不写入 eMMC）
ramdisk.log_ui_scan({
    'screen_state': 'active',
    'elements_detected': 5,
    'confidence': 0.95
})

# 记录连接检查心跳
ramdisk.log_connection_check('connected')

# 清理旧日志（防止内存盘满）
ramdisk.cleanup_old_logs(keep_hours=1)
```

**内存盘日志位置：**
```
/dev/shm/claw_logs/heartbeat_YYYYMMDD_HHMMSS.jsonl
```

---

### 3️⃣ 极简硬件干预接口 (hardware_override.py)

**核心特性：**
- ✅ FastAPI 本地接口 /api/v1/override
- ✅ 支持 ACCEPT/REJECT/PAUSE/RESUME 命令
- ✅ 瞬间打断 LangGraph 运行
- ✅ 接管最终输出

**API 端点：**

```bash
# 发送硬件干预命令
POST /api/v1/override
{
    "merchant_id": "box-001",
    "command": "ACCEPT",
    "reason": "Customer confirmed via smartwatch"
}

# 获取硬件干预状态
GET /api/v1/override/status
```

**使用示例：**
```python
from fastapi import FastAPI
from edge_box.hardware_override import create_override_api, get_override_manager

app = FastAPI()

# 创建硬件干预 API
override_manager = create_override_api(app)

# 注册回调
async def on_accept(negotiation_data):
    print(f"Accepted: {negotiation_data}")

override_manager.register_override_callback(
    OverrideCommand.ACCEPT,
    on_accept
)

# 在 LangGraph 中集成中断机制
from edge_box.hardware_override import LangGraphInterruptor

interruptor = LangGraphInterruptor(override_manager)

async def negotiation_loop():
    # 设置当前谈判
    await override_manager.set_current_negotiation({
        'intent_id': 'xxx',
        'merchant_id': 'box-001',
        'price': 12.5
    })
    
    # 等待硬件干预或谈判完成
    override_cmd = await override_manager.wait_for_override(timeout=300)
    
    if override_cmd:
        # 处理硬件干预
        result = await interruptor.handle_interrupt(override_cmd)
        return result
    else:
        # 正常谈判完成
        return normal_negotiation_result
```

---

## 🔄 完整集成流程

### 启动时初始化

```python
# edge_box/main.py
from edge_box.crypto_logger import init_crypto_logger
from edge_box.ramdisk_logger import get_ramdisk_logger
from edge_box.hardware_override import create_override_api

# 初始化审计日志
init_crypto_logger(
    db_path="./audit.db",
    secret_key="your-secret-key"
)

# 初始化内存盘日志
ramdisk = get_ramdisk_logger()

# 创建硬件干预 API
override_manager = create_override_api(app)
```

### 交易执行流程

```python
async def execute_trade(intent_id, merchant_id, client_id, price):
    logger = get_crypto_logger()
    ramdisk = get_ramdisk_logger()
    override_manager = get_override_manager()
    
    # 1. 设置当前谈判
    await override_manager.set_current_negotiation({
        'intent_id': intent_id,
        'merchant_id': merchant_id,
        'client_id': client_id,
        'price': price
    })
    
    # 2. 记录交易开始
    logger.log_trade_execute(
        intent_id=intent_id,
        merchant_id=merchant_id,
        client_id=client_id,
        price=price,
        action="TRADE_START",
        details={'status': 'initiated'}
    )
    
    # 3. 等待硬件干预或谈判完成
    override_cmd = await override_manager.wait_for_override(timeout=300)
    
    if override_cmd == OverrideCommand.ACCEPT:
        # 4. 执行支付
        logger.log_physical_action(
            intent_id=intent_id,
            merchant_id=merchant_id,
            client_id=client_id,
            price=price,
            action="WECHAT_SEND",
            details={'status': 'sent'}
        )
        
        # 5. 记录成交
        logger.log_trade_execute(
            intent_id=intent_id,
            merchant_id=merchant_id,
            client_id=client_id,
            price=price,
            action="TRADE_COMPLETED",
            details={'status': 'success'}
        )
    
    elif override_cmd == OverrideCommand.REJECT:
        # 记录拒绝
        logger.log_override_command(
            merchant_id=merchant_id,
            command="REJECT",
            reason="Hardware override"
        )
```

---

## 📊 合规审查支持

### 导出审计报告

```python
logger = get_crypto_logger()

# 导出完整审计报告
report = logger.export_audit_report(
    merchant_id="box-001",
    start_time=time.time() - 30*86400,  # 过去 30 天
    end_time=time.time()
)

# 报告包含：
# - 所有交易事件
# - 所有物理操作
# - 所有手动覆盖命令
# - 审计追踪完整性验证结果
# - 统计摘要

import json
with open("audit_report.json", "w") as f:
    json.dump(report, f, indent=2)
```

### 验证审计完整性

```python
# 验证审计追踪是否被篡改
is_valid = logger.verify_audit_trail()

if is_valid:
    print("✅ 审计追踪完整，未被篡改")
else:
    print("❌ 审计追踪被篡改，需要调查")
```

---

## 🛡️ 断电/断网保护

### 断电保护
- ✅ 所有关键事件立即写入 SQLite（持久化）
- ✅ 审计数据库存储在本地 eMMC
- ✅ 支持离线模式继续记录

### 断网保护
- ✅ 所有数据本地存储
- ✅ 网络恢复后自动同步
- ✅ 不依赖云端服务

### eMMC 保护
- ✅ 高频日志写入内存盘
- ✅ 定期清理过期日志
- ✅ 防止闪存颗粒烧毁

---

## ✅ 检查清单

- [x] 不可篡改审计追踪系统
- [x] SHA-256 哈希链式签名
- [x] SQLite 本地审计数据库
- [x] 内存盘保护策略
- [x] 硬件干预接口
- [x] LangGraph 中断机制
- [x] 合规审查报告导出
- [x] 断电/断网保护
- [x] eMMC 保护

---

**Project Claw Edge Box 现已具备金融级的可靠性和合规性！** 🏆
