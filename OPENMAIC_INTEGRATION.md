# Project Claw 与 OpenMAIC 完整集成指南

## 架构对齐

### OpenMAIC 的多智能体模式
```
StateGraph
  ├─ Node 1: 感知层（获取输入）
  ├─ Node 2: 认知层（多 Agent 协作）
  ├─ Node 3: 执行层（输出动作）
  └─ Node 4: 反馈层（记录结果）
```

### Project Claw 的多智能体模式
```
ConversationState
  ├─ AssistantAgent（后厨）→ 分析需求 + 查库存
  ├─ TeacherAgent（老板）→ 生成回复
  ├─ FeishuWebhookSync → 飞书同步
  └─ LobsterPhysicalTool → 微信发送
```

---

## 集成步骤

### 第一步：复制文件到 OpenMAIC

```bash
# 复制后端模块
cp multi_agent_orchestrator.py OpenMAIC/app/agents/
cp lobster_tool.py OpenMAIC/app/agents/
cp lobster_mvp_v2.py OpenMAIC/app/agents/

# 复制前端组件
cp openmaic_integration.tsx OpenMAIC/components/agent/
```

### 第二步：在 OpenMAIC 中注册 Agent

编辑 `OpenMAIC/app/agents/registry.ts`：

```typescript
import { LobsterAgent } from '@/components/agent/openmaic_integration'
import { MultiAgentOrchestrator } from './multi_agent_orchestrator'

export const AGENT_REGISTRY = {
  lobster: {
    name: '龙虾自动回复',
    description: '多智能体微信自动回复系统',
    component: LobsterAgent,
    backend: MultiAgentOrchestrator,
    icon: '🦞'
  },
  // ... 其他 Agent
}
```

### 第三步：启动后端服务

```bash
# 方式1：直接运行
python lobster_mvp_v2.py

# 方式2：通过 API 服务
python api_server_pro.py
```

### 第四步：启动 OpenMAIC 前端

```bash
cd OpenMAIC
npm run dev
# 访问 http://localhost:3000
```

---

## 数据流向

```
┌─────────────────────────────────────────────────────────┐
│                   OpenMAIC 前端                          │
│  (openmaic_integration.tsx)                             │
└────────────────────┬────────────────────────────────────┘
                     │ WebSocket / REST API
                     ▼
┌─────────────────────────────────────────────────────────┐
│              Project Claw 后端服务                       │
│  (api_server_pro.py)                                    │
└────────────────────┬────────────────────────────────────┘
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ MultiAgent   │ │ LobsterTool  │ │ FeishuSync   │
│ Orchestrator │ │ (物理执行)   │ │ (飞书同步)   │
└──────────────┘ └──────────────┘ └──────────────┘
        │            │            │
        └────────────┼────────────┘
                     ▼
        ┌────────────────────────┐
        │   微信 + 飞书 + 向量库  │
        └────────────────────────┘
```

---

## API 端点

### 基础端点

| 端点 | 方法 | 功能 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/metrics` | GET | 系统指标 |
| `/search` | GET | 向量搜索 |
| `/run-agent` | POST | 运行 Agent |
| `/ws/agent-stream` | WS | 实时推送 |

### 请求示例

```bash
# 运行 Agent
curl -X POST http://localhost:8000/run-agent \
  -H "Content-Type: application/json" \
  -d '{"message": "龙虾多少钱？"}'

# 获取指标
curl http://localhost:8000/metrics

# 搜索相似对话
curl "http://localhost:8000/search?query=龙虾&top_k=3"
```

---

## 配置文件

### `config.yaml`

```yaml
# DeepSeek API
api:
  api_key: "sk-..."
  model: "deepseek-chat"
  timeout: 10

# 飞书配置
feishu:
  app_id: "cli_..."
  app_secret: "..."
  webhook_url: "https://open.feishu.cn/open-apis/bot/v2/hook/..."

# 系统配置
system:
  check_interval: 5
  dedup_window: 30
  max_failures: 5
```

---

## 多智能体工作流

### 完整流程

```
用户消息: "龙虾多少钱？"
  │
  ▼
AssistantAgent（后厨）
  ├─ 分析: 用户想查龙虾价格
  ├─ 查库: 龙虾有 50 份，88 元/份
  └─ 输出: {
       "requested_items": ["龙虾"],
       "availability": {"龙虾": {"stock": 50, "price": 88}},
       "recommendations": ["龙虾有货，50份库存"]
     }
  │
  ▼
TeacherAgent（老板）
  ├─ 输入: 用户消息 + 后厨分析
  ├─ 调用: DeepSeek API
  └─ 输出: "兄弟，龙虾88块一份，现在有货！"
  │
  ▼
FeishuWebhookSync
  ├─ 发送: Webhook 到飞书
  └─ 记录: 对话历史
  │
  ▼
LobsterPhysicalTool
  ├─ 点击: 输入框
  ├─ 输入: "兄弟，龙虾88块一份，现在有货！"
  ├─ 点击: 发送按钮
  └─ 完成: ✅
```

---

## 监控和调试

### 查看日志

```bash
# 实时日志
tail -f lobster_v2.log

# 搜索错误
grep "ERROR" lobster_v2.log

# 查看统计
grep "📊 统计" lobster_v2.log
```

### 性能指标

```bash
# 获取系统指标
curl http://localhost:8000/metrics

# 响应示例
{
  "total_requests": 100,
  "total_errors": 2,
  "error_rate": "2.00%",
  "avg_latency_ms": "45.23",
  "p95_latency_ms": "120.45"
}
```

### 向量搜索

```bash
# 搜索相似对话
curl "http://localhost:8000/search?query=龙虾多少钱&top_k=3"

# 响应示例
{
  "status": "success",
  "query": "龙虾多少钱",
  "results": [
    "用户: 龙虾多少钱？\n龙虾: 兄弟，龙虾88块一份，现在有货！",
    "用户: 龙虾贵吗？\n龙虾: 亲，龙虾88块，很划算！",
    "用户: 你们龙虾怎么卖？\n龙虾: 兄弟，龙虾88块一份！"
  ]
}
```

---

## 故障排查

### 问题1：WebSocket 连接失败

**症状**：前端显示"未连接"

**解决**：
```bash
# 检查后端是否运行
curl http://localhost:8000/health

# 检查防火墙
netstat -an | grep 8000

# 重启后端
python api_server_pro.py
```

### 问题2：飞书同步失败

**症状**：日志显示"飞书 Webhook 发送失败"

**解决**：
1. 检查 Webhook URL 是否正确
2. 检查 APP_ID 和 APP_SECRET
3. 确保飞书应用已授权

### 问题3：消息识别不到

**症状**：日志显示"暂无新消息"

**解决**：
1. 确保手机已连接 uiautomator2
2. 确保微信在前台
3. 确保消息在聊天区域（左边灰色气泡）

---

## 性能优化

### 1. 缓存优化

```python
# 启用 ChromaDB 缓存
from multi_agent_orchestrator import ChromaDBRetriever

retriever = ChromaDBRetriever()
similar_replies = retriever.search_similar(user_message, top_k=3)
```

### 2. 并发优化

```python
# 使用异步处理
import asyncio

async def process_batch(messages):
    tasks = [orchestrator.process_message(msg) for msg in messages]
    return await asyncio.gather(*tasks)
```

### 3. 熔断器优化

```python
# 调整熔断器参数
circuit_breaker = CircuitBreaker(
    failure_threshold=3,  # 降低阈值
    timeout_sec=30       # 缩短恢复时间
)
```

---

## 扩展功能

### 添加新的 Agent

```python
class CustomAgent:
    def __init__(self):
        self.name = "custom_agent"
    
    def process(self, state: ConversationState) -> ConversationState:
        # 自定义逻辑
        return state

# 在状态机中添加节点
graph.add_node("custom_agent", custom_agent.process)
```

### 添加新的数据源

```python
class DatabaseConnector:
    def __init__(self, connection_string):
        self.conn = connect(connection_string)
    
    def query(self, sql):
        return self.conn.execute(sql).fetchall()

# 在 AssistantAgent 中使用
db = DatabaseConnector("postgresql://...")
results = db.query("SELECT * FROM inventory")
```

---

## 部署到生产环境

### Docker 部署

```dockerfile
FROM python:3.10

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["python", "api_server_pro.py"]
```

### Kubernetes 部署

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: project-claw
spec:
  replicas: 3
  selector:
    matchLabels:
      app: project-claw
  template:
    metadata:
      labels:
        app: project-claw
    spec:
      containers:
      - name: project-claw
        image: project-claw:latest
        ports:
        - containerPort: 8000
```

---

## 最佳实践

1. **日志记录**：使用结构化日志便于分析
2. **错误处理**：优雅降级，不中断主流程
3. **性能监控**：定期检查指标和延迟
4. **安全性**：保护 API Key 和敏感信息
5. **可扩展性**：设计模块化架构，便于扩展

---

**最后更新**：2026-03-21
**版本**：v2.0
**作者**：Project Claw Team
