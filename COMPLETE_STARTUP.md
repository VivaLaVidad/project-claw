# Project Claw - 完整启动指南 v2.0

## 🚀 一键启动（推荐）

### 方式一：PowerShell 一键启动所有服务

```powershell
cd "d:\桌面\Project Claw"
.\start_all.ps1
```

**自动执行：**
- ✅ 清理占用端口 (8765, 8010)
- ✅ 启动 signaling:8765
- ✅ 启动 siri:8010
- ✅ 启动 B端 Agent (edge_box)
- ✅ 打开微信开发者工具

---

## 📋 分步启动（手动）

### 第一步：启动云端服务（signaling + siri + dashboard）

**终端 1：**
```powershell
cd "d:\桌面\Project Claw"
python run_stack.py signaling siri dashboard
```

**预期输出：**
```
[stack] signaling 已就绪 ✓
[stack] siri 已就绪 ✓
[stack] dashboard 已就绪 ✓
[stack] 全部服务已启动: ['signaling', 'siri', 'dashboard']
```

**服务地址：**
- signaling: http://127.0.0.1:8765
- siri: http://127.0.0.1:8010
- dashboard: http://127.0.0.1:8501

---

### 第二步：启动 B端 Agent

**终端 2：**
```powershell
cd "d:\桌面\Project Claw"
.\start_edge.ps1
```

**预期输出：**
```
[Edge] Project Claw B端 Agent 启动器
[Edge] 连接信令服务器...
[WSListener] connect trade channel: ws://127.0.0.1:8765/ws/a2a/merchant/box-001
[WSListener] connect dialogue channel: ws://127.0.0.1:8765/ws/a2a/dialogue/merchant/box-001
[Driver] 回退到 MockDriver（无 Android 设备）
```

---

### 第三步：打开微信开发者工具

**方式 A：自动打开（如果已安装）**
```powershell
& "C:\Program Files (x86)\Tencent\微信web开发者工具\cli.exe" open --project "d:\桌面\Project Claw\miniprogram"
```

**方式 B：手动打开**
1. 下载微信开发者工具：https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html
2. 打开后点「导入项目」
3. 项目路径：`d:\桌面\Project Claw\miniprogram`
4. AppID：使用测试号（点「使用测试号」）
5. **重要：工具 → 详情 → 本地设置 → 勾选「不校验合法域名」**

---

### 第四步：验证所有服务

**检查清单：**

```
✓ signaling 健康检查
  curl http://127.0.0.1:8765/health
  
✓ siri 健康检查
  curl http://127.0.0.1:8010/health
  
✓ 小程序顶部显示
  ● 在线 1 商家
  
✓ 上帝视角 dashboard
  http://127.0.0.1:8501
  
✓ B端控制台
  小程序 → 底部 Tab → 商家
```

---

## 🔧 环境配置

### 必需环境变量 (.env)

```bash
# ══ 信令服务器 ══════════════════════════════════════════
SIGNALING_HOST=127.0.0.1
SIGNALING_PORT=8765
SIGNALING_HTTP_SCHEME=http
SIGNALING_WS_SCHEME=ws

# ══ LLM 配置 ════════════════════════════════════════════
DEEPSEEK_API_KEY=sk-xxx  # 替换为你的 API Key
DEEPSEEK_API_URL=https://api.deepseek.com/chat/completions
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_TIMEOUT=15

# ══ A2A 安全通信 ════════════════════════════════════════
A2A_SIGNING_SECRET=claw-a2a-signing-secret-dev
A2A_ENCRYPTION_KEY=your-encryption-key-32-chars-long

# ══ Redis（可选，无则自动内存存储）═══════════════════
REDIS_URL=

# ══ 日志 ════════════════════════════════════════════════
LOG_LEVEL=INFO
LOG_FILE=claw.log
LOG_DIR=logs
```

### Python 依赖

```bash
# 安装依赖
pip install -r requirements.txt

# 或手动安装关键包
pip install fastapi uvicorn pydantic tenacity cryptography redis
```

---

## 📱 小程序配置

### 环境切换 (miniprogram/app.js)

```javascript
// 本地开发
const ENV = 'dev';

// 生产环境
// const ENV = 'prod';

const ENV_CONFIG = {
  dev: {
    serverBase: 'http://127.0.0.1:8765',
    wsBase:     'ws://127.0.0.1:8765',
    siriBase:   'http://127.0.0.1:8010',
  },
  prod: {
    serverBase: 'https://project-claw-production.up.railway.app',
    wsBase:     'wss://project-claw-production.up.railway.app',
    siriBase:   'https://project-claw-production.up.railway.app',
  },
};
```

### 微信开发者工具设置

1. **不校验合法域名**
   - 工具 → 详情 → 本地设置 → 勾选「不校验合法域名」

2. **清空缓存**
   - 工具 → 清空缓存 → 全部清空

3. **强制刷新**
   - `Ctrl + Shift + R`

---

## 🏗️ 项目结构

```
Project Claw/
├── miniprogram/                    # 小程序（C端+B端UI）
│   ├── app.js                      # 全局入口
│   ├── app.json                    # 配置
│   ├── app.wxss                    # 全局样式
│   ├── api/
│   │   └── request.js              # API 层
│   ├── utils/
│   │   └── profile.js              # 画像管理
│   └── pages/
│       ├── index/                  # C端发现页
│       ├── dialogue/               # 对话页
│       ├── orders/                 # 订单页
│       └── merchant/               # B端控制台
│
├── cloud_server/                   # 云端服务
│   ├── api_server_pro.py           # siri LLM API
│   └── ...
│
├── edge_box/                       # B端 Agent
│   ├── ws_listener.py              # WS 监听器
│   ├── negotiator.py               # 谈判引擎
│   └── ...
│
├── shared/                         # 共享层
│   ├── claw_protocol.py            # 数据模型
│   └── ...
│
├── a2a_signaling_server.py         # 信令服务器
├── run_stack.py                    # 启动脚本
├── start_all.ps1                   # 一键启动脚本
├── start_edge.ps1                  # B端启动脚本
├── god_mode_dashboard.py           # 上帝视角
├── config.py                       # 配置
├── .env                            # 环境变量
├── requirements.txt                # Python 依赖
├── STARTUP_GUIDE.md                # 启动指南
├── AGENT_DIALOGUE_SYSTEM.md        # 对话系统文档
└── README.md                       # 项目说明
```

---

## 🔄 完整启动流程图

```
用户执行 .\start_all.ps1
    ↓
清理占用端口 (8765, 8010)
    ↓
启动 signaling:8765
    ├─ 等待就绪 (最多 30s)
    └─ 成功 ✓
    ↓
启动 siri:8010
    ├─ 等待就绪 (最多 30s)
    └─ 成功 ✓
    ↓
启动 B端 Agent (edge_box)
    ├─ 连接 WS /ws/a2a/merchant/box-001
    └─ 成功 ✓
    ↓
打开微信开发者工具
    ├─ 导入 miniprogram
    ├─ 清空缓存
    └─ 刷新 ✓
    ↓
所有服务就绪！
    ├─ signaling: http://127.0.0.1:8765
    ├─ siri: http://127.0.0.1:8010
    ├─ dashboard: http://127.0.0.1:8501
    ├─ 小程序: 微信开发者工具
    └─ B端 Agent: 已连接
```

---

## 🧪 测试完整流程

### 场景：C端用户砍价

```bash
# 1. 小程序输入商品+预算
# 页面：pages/index
# 输入：商品名「牛肉面」，预算「15元」

# 2. 点击「Agent 全自动砍价」
# 后台流程：
#   C端 → POST /a2a/intent → signaling
#   signaling → WS广播 → B端 Agent
#   B端 Agent → 调用 LLM → siri:8010
#   B端 Agent → 返回报价 → signaling
#   signaling → GET /a2a/intent/:id/result → C端

# 3. 小程序收到报价，显示「最优报价 ¥12.75」

# 4. 点击「立即下单」
# 后台流程：
#   C端 → POST /a2a/dialogue/start → signaling
#   signaling → 创建会话 → B端 Agent
#   C端 ← WS /ws/a2a/client/:id → 建立连接
#   B端 ← WS /ws/a2a/dialogue/merchant/:id → 建立连接

# 5. 进入对话页，实时对话
# C端发送：「预算15元，能给我最优惠的吗？」
# B端收到 → 调用 LLM → 生成回复
# B端发送：「兄弟，新鲜现做，12块钱给你来一份，保证好吃！」
# C端收到 → 显示对话

# 6. 成交条件：¥12 <= ¥15 * 0.9 (13.5) → True
# 显示「✅ 成交！¥12.0」

# 7. 上报满意度
# C端 → POST /a2a/dialogue/satisfaction → signaling
# signaling → 存储反馈 → Redis
# B端 Agent → 读取反馈 → 优化策略
```

---

## 📊 监控与调试

### 查看实时日志

```bash
# signaling 日志
tail -f logs/claw.log

# 上帝视角 dashboard
http://127.0.0.1:8501

# 小程序控制台
微信开发者工具 → 调试器 → Console
```

### 健康检查

```bash
# signaling 健康检查
curl http://127.0.0.1:8765/health

# siri 健康检查
curl http://127.0.0.1:8010/health

# 获取统计数据
curl http://127.0.0.1:8765/stats
```

---

## 🛑 停止服务

### 停止所有服务

```bash
# 方式 1：在各终端按 Ctrl+C

# 方式 2：PowerShell 杀进程
taskkill /F /IM python.exe
```

---

## ⚠️ 常见问题

### Q: 启动后小程序显示「离线」？
A: 
1. 检查 signaling 是否启动成功
2. 清空小程序缓存：工具 → 清空缓存 → 全部清空
3. 强制刷新：Ctrl + Shift + R

### Q: B端 Agent 无法连接？
A:
1. 检查 signaling 是否启动
2. 检查 start_edge.ps1 是否运行
3. 查看 B端终端是否有错误日志

### Q: 报价为空？
A:
1. 检查 siri:8010 是否启动
2. 检查 DEEPSEEK_API_KEY 是否配置
3. 查看 siri 日志

### Q: 微信开发者工具无法连接？
A:
1. 勾选「不校验合法域名」
2. 确保 127.0.0.1:8765 可访问
3. 清空缓存并刷新

---

## 📚 相关文档

- **启动指南**：`STARTUP_GUIDE.md`
- **对话系统**：`AGENT_DIALOGUE_SYSTEM.md`
- **API 文档**：`a2a_signaling_server.py`
- **配置说明**：`config.py`

---

## ✅ 启动检查清单

- [ ] Python 3.11+ 已安装
- [ ] `.env` 文件存在且配置正确
- [ ] 端口 8765、8010 未被占用
- [ ] 微信开发者工具已安装
- [ ] 小程序「不校验合法域名」已勾选
- [ ] 所有依赖已安装：`pip install -r requirements.txt`

---

## 🎯 快速启动命令速查

```bash
# 一键启动所有服务
.\start_all.ps1

# 仅启动后端服务
python run_stack.py signaling siri dashboard

# 仅启动 B端 Agent
.\start_edge.ps1

# 打开上帝视角 dashboard
http://127.0.0.1:8501

# 清空小程序缓存
# 微信开发者工具 → 工具 → 清空缓存 → 全部清空

# 强制刷新小程序
# Ctrl + Shift + R
```

---

**现在你已经拥有完整的启动指南！祝你砍价愉快！🦞**
