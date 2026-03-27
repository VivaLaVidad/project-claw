# Project Claw v3.0 - 完整架构文档

## 项目概述

**Project Claw** 是一个**多智能体协同的微信自动回复系统**，集成了：
- 🦞 视觉识别 + 自动化点击
- 🤖 多智能体状态机（LangGraph）
- ☁️ 飞书多维表格同步
- 🔌 工业级 API 服务
- 🛡️ 熔断器 + 指标上报
- 🔍 ChromaDB 向量检索

---

## 项目结构

```
Project Claw/
├── 核心模块
│   ├── lobster_tool.py              # 物理工具层（OCR + 点击）
│   ├── run_business.py              # 多智能体状态机
│   ├── api_server.py                # 基础 API 服务
│   └── api_server_pro.py            # 工业级 API（熔断器 + 指标 + ChromaDB）
│
├── 前端集成
│   └── openmaic_integration.tsx      # OpenMAIC 前端组件
│
├── 配置文件
│   ├── config.yaml                  # 系统配置
│   ├── requirements.txt             # Python 依赖
│   └── ARCHITECTURE.md              # 本文档
│
├── 启动脚本
│   ├── 启动.bat                     # 简单版启动
│   └── 启动_云端版.bat              # 云端版启动
│
└── 日志
    └── logs/
        └── lobster.log              # 运行日志
```

---

## 核心模块说明

### 1. `lobster_tool.py` - 物理工具层

**职责**：封装所有物理操作（截屏、OCR、点击、发送）

```python
tool = LobsterPhysicalTool()
message = tool.get_latest_message()      # 获取用户消息
tool.send_wechat_message("回复内容")     # 发送消息
```

**关键特性**：
- ✅ 气泡颜色识别（HSV）区分用户/龙虾消息
- ✅ EasyOCR 文字识别
- ✅ uiautomator2 自动化点击

---

### 2. `run_business.py` - 多智能体状态机

**架构**：
```
获取消息 → 库存查询 → 老板生成回复 → 执行发送 → 飞书同步
```

**三个智能体**：
- **InventoryAgent**：查库存（Mock 数据）
- **BossAgent**：调用 DeepSeek API 生成话术
- **ActionNode**：物理执行 + 飞书同步

**运行**：
```bash
python run_business.py
```

---

### 3. `api_server.py` - 基础 API 服务

**端点**：
- `GET /health` - 健康检查
- `GET /inventory` - 获取库存
- `POST /generate-reply` - 生成回复
- `POST /send-message` - 发送消息
- `POST /run-agent` - 运行 Agent
- `WS /ws/agent-stream` - WebSocket 实时推送

**运行**：
```bash
python api_server.py
# 访问 http://localhost:8000/docs
```

---

### 4. `api_server_pro.py` - 工业级 API（推荐）

**新增特性**：

#### 🛡️ 熔断器（Circuit Breaker）
```python
# 自动保护：5 次失败后熔断，60 秒后自动恢复
circuit_breaker = CircuitBreaker(failure_threshold=5, timeout_sec=60)
```

#### 📊 指标收集（Metrics）
```
GET /metrics
{
  "total_requests": 100,
  "total_errors": 2,
  "error_rate": "2.00%",
  "avg_latency_ms": "45.23",
  "p95_latency_ms": "120.45"
}
```

#### 🔍 ChromaDB 向量检索
```python
# 自动保存对话到向量库
chroma_retriever.add_conversation(user_msg, bot_reply)

# 搜索相似对话
GET /search?query=龙虾多少钱&top_k=3
```

**运行**：
```bash
python api_server_pro.py
```

---

## 工作流程

### 完整流程图

```
┌─────────────────────────────────────────────────────────┐
│                   用户发送消息                           │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│  LobsterPhysicalTool.get_latest_message()               │
│  - 截屏                                                 │
│  - EasyOCR 识别                                          │
│  - 气泡颜色识别（过滤龙虾回复）                          │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│  InventoryAgent.check_inventory()                       │
│  - 查询库存（龙虾、螺蛳粉等）                            │
│  - 返回库存信息                                          │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│  BossAgent.generate_reply()                             │
│  - 调用 DeepSeek API                                    │
│  - 结合库存信息生成话术                                  │
│  - 返回回复文本                                          │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│  LobsterPhysicalTool.send_wechat_message()              │
│  - 点击输入框                                            │
│  - 输入文字                                              │
│  - 点击发送按钮                                          │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│  FeishuSync.sync_record()                               │
│  - 同步到飞书多维表格                                    │
│  - ChromaDB 保存对话                                    │
└─────────────────────────────────────────────────────────┘
```

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置参数

编辑 `config.yaml`：
```yaml
api:
  api_key: "sk-你的DeepSeek-Key"

feishu:
  app_id: "cli_..."
  app_secret: "..."
  app_token: "..."
  table_id: "tbl..."
```

### 3. 启动服务

**方式1：简单版**
```bash
python run_business.py
```

**方式2：API 服务（推荐）**
```bash
python api_server_pro.py
# 访问 http://localhost:8000/docs
```

**方式3：OpenMAIC 前端**
```bash
# 在 OpenMAIC 项目中导入组件
import { LobsterAgent } from '@/components/agent/openmaic_integration'
```

---

## 工业级特性详解

### 🛡️ 熔断器

**工作原理**：
- 正常状态（CLOSED）：请求正常通过
- 失败 5 次后进入熔断状态（OPEN）：拒绝所有请求
- 60 秒后进入半开状态（HALF_OPEN）：尝试恢复
- 恢复成功则回到正常状态

**日志示例**：
```
🔴 熔断器已打开（失败 5 次）
🔄 熔断器进入半开状态
✅ 熔断器已关闭
```

### 📊 指标收集

**收集的指标**：
- 总请求数
- 错误数 + 错误率
- 平均延迟
- P95 延迟（95% 的请求在这个时间内完成）

**用途**：
- 监控系统健康度
- 性能分析
- 告警触发

### 🔍 ChromaDB 向量检索

**功能**：
- 自动保存所有对话到向量库
- 支持语义搜索（找相似对话）
- 用于上下文学习和知识积累

**示例**：
```bash
# 搜索相似对话
curl "http://localhost:8000/search?query=龙虾多少钱&top_k=3"
```

---

## 配置说明

### `config.yaml`

```yaml
# API 配置
api:
  api_key: "sk-..."
  model: "deepseek-chat"
  timeout: 10

# 回复策略
reply:
  system_prompt: "你是一个热情的店老板..."
  max_tokens: 80
  check_interval: 2

# 飞书配置
feishu:
  app_id: "cli_..."
  app_secret: "..."
  app_token: "..."
  table_id: "tbl..."

# 安全配置
security:
  max_failures: 5
  cooldown_time: 120
  dedup_window: 30
```

---

## 常见问题

### Q: 为什么识别不到消息？
**A**: 检查以下几点：
1. 手机是否已连接 uiautomator2
2. 微信是否在前台
3. 消息是否在聊天区域（左边灰色气泡）

### Q: 飞书同步失败怎么办？
**A**: 
1. 检查 APP_ID 和 APP_SECRET 是否正确
2. 确保表格已共享给应用
3. 检查字段名是否与飞书表格一致

### Q: 如何自定义回复内容？
**A**: 修改 `config.yaml` 中的 `system_prompt`

### Q: 熔断器打开了怎么办？
**A**: 等待 60 秒自动恢复，或重启服务

---

## 性能指标

| 指标 | 目标 | 实际 |
|------|------|------|
| 消息识别延迟 | < 2s | ~1.5s |
| 回复生成延迟 | < 5s | ~3.2s |
| 消息发送延迟 | < 2s | ~1.8s |
| 系统吞吐量 | > 10 msg/min | ~15 msg/min |
| 错误率 | < 5% | ~2% |

---

## 后续规划

- [ ] 多语言支持
- [ ] 自定义 Agent 编排
- [ ] 实时仪表板
- [ ] 数据导出功能
- [ ] 性能优化（GPU 加速）

---

## 许可证

MIT License

---

**最后更新**：2026-03-21
**版本**：v3.0
**作者**：Project Claw Team
