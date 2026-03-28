# Project Claw 前置环境准备指南 v1.0

## 📋 系统要求

### 操作系统
- ✅ Linux (Ubuntu 20.04+, CentOS 8+)
- ✅ macOS (10.15+)
- ✅ Windows 10/11

### 硬件要求
```
最低配置：
- CPU: 4 核
- 内存: 8GB
- 存储: 20GB

推荐配置：
- CPU: 8 核
- 内存: 16GB
- 存储: 50GB
```

---

## 🔧 第一步：安装 Python

### Linux (Ubuntu/Debian)
```bash
sudo apt update
sudo apt install python3.11 python3.11-venv python3.11-dev -y
python3.11 --version
```

### macOS
```bash
brew install python@3.11
python3.11 --version
```

### Windows
1. 下载 Python 3.11 安装程序：https://www.python.org/downloads/
2. 运行安装程序，勾选 "Add Python to PATH"
3. 验证安装：
```bash
python --version
```

---

## 🔧 第二步：安装系统依赖

### Linux (Ubuntu/Debian)
```bash
sudo apt install -y \
    build-essential \
    libssl-dev \
    libffi-dev \
    python3-dev \
    git \
    redis-server \
    sqlite3
```

### macOS
```bash
brew install \
    openssl \
    libffi \
    git \
    redis \
    sqlite3
```

### Windows
1. 安装 Git：https://git-scm.com/download/win
2. 安装 Redis（可选）：https://github.com/microsoftarchive/redis/releases
3. SQLite3 已内置在 Python 中

---

## 🔧 第三步：克隆项目

```bash
# 克隆项目
git clone https://github.com/VivaLaVidad/project-claw.git
cd project-claw

# 查看分支
git branch -a

# 切换到主分支
git checkout main
```

---

## 🔧 第四步：创建虚拟环境

### Linux/macOS
```bash
# 创建虚拟环境
python3.11 -m venv venv

# 激活虚拟环境
source venv/bin/activate

# 验证激活
which python
```

### Windows
```bash
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
venv\Scripts\activate.bat

# 验证激活
where python
```

---

## 🔧 第五步：安装项目依赖

```bash
# 升级 pip
pip install --upgrade pip setuptools wheel

# 安装项目依赖
pip install -r requirements.txt

# 验证安装
pip list
```

---

## 🔧 第六步：配置环境变量

### 创建 .env 文件
```bash
cp .env.example .env
```

### 编辑 .env 文件
```bash
# .env

# ═══ DeepSeek LLM ══════════════════════════════════════════
DEEPSEEK_API_KEY=sk-your-api-key-here
DEEPSEEK_API_URL=https://api.deepseek.com/chat/completions
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_TIMEOUT=15
DEEPSEEK_MAX_TOKENS=200
DEEPSEEK_TEMPERATURE=0.7
DEEPSEEK_MAX_RETRIES=3

# ═══ GPT-4o (可选) ════════════════════════════════════════
OPENAI_API_KEY=sk-your-api-key-here

# ═══ 系统配置 ══════════════════════════════════════════════
SYSTEM_PROMPT=你是一个热情的店老板，回话简短接地气，叫人'兄弟'。

# ═══ 本地记忆 ══════════════════════════════════════════════
LOCAL_MEMORY_ENABLED=true
LOCAL_MEMORY_DB_DIR=./claw_db
LOCAL_MEMORY_CSV=menu.csv

# ═══ Redis ════════════════════════════════════════════════
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# ═══ 数据库 ════════════════════════════════════════════════
AUDIT_DB_PATH=./audit.db
DLQ_DB_PATH=./dlq.db
```

---

## 🔧 第七步：初始化数据库

```bash
# 自动初始化（启动脚本会自动执行）
python3 << 'EOF'
import sqlite3
from pathlib import Path

# 创建审计数据库
audit_db = Path("./audit.db")
if not audit_db.exists():
    conn = sqlite3.connect(str(audit_db))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            timestamp REAL NOT NULL,
            intent_id TEXT NOT NULL,
            merchant_id TEXT NOT NULL,
            client_id TEXT NOT NULL,
            price REAL NOT NULL,
            action TEXT NOT NULL,
            details TEXT NOT NULL,
            previous_hash TEXT NOT NULL,
            event_hash TEXT NOT NULL,
            signature TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
    print("✓ 审计数据库已初始化")

# 创建死信队列数据库
dlq_db = Path("./dlq.db")
if not dlq_db.exists():
    conn = sqlite3.connect(str(dlq_db))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dead_letters (
            id TEXT PRIMARY KEY,
            trade_id TEXT NOT NULL,
            merchant_id TEXT NOT NULL,
            client_id TEXT NOT NULL,
            amount REAL NOT NULL,
            status TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at REAL NOT NULL,
            retry_count INTEGER DEFAULT 0,
            last_error TEXT DEFAULT ''
        )
    """)
    conn.commit()
    conn.close()
    print("✓ 死信队列数据库已初始化")
EOF
```

---

## 🚀 第八步：一键启动项目

### Linux/macOS
```bash
# 给脚本添加执行权限
chmod +x start_project.sh

# 运行启动脚本
bash start_project.sh
```

### Windows
```bash
# 直接运行批处理脚本
start_project.bat
```

---

## 📍 启动后的服务地址

```
后端 API: http://localhost:8765
API 文档: http://localhost:8765/docs
融资路演大屏: http://localhost:8501
C 端演示前端: file:///path/to/project/mock_client/index.html
```

---

## 🔍 验证启动

### 检查后端服务
```bash
curl http://localhost:8765/docs
# 应该返回 Swagger UI 页面
```

### 检查融资路演大屏
```bash
curl http://localhost:8501
# 应该返回 Streamlit 页面
```

### 检查数据库
```bash
sqlite3 audit.db ".tables"
# 应该显示 audit_events 表

sqlite3 dlq.db ".tables"
# 应该显示 dead_letters 表
```

---

## 🛑 停止服务

### Linux/macOS
```bash
# 查找进程
ps aux | grep python
ps aux | grep streamlit

# 杀死进程
kill -9 <PID>

# 或者按 Ctrl+C 停止前台进程
```

### Windows
```bash
# 关闭对应的命令行窗口
# 或者使用任务管理器结束进程
```

---

## 🐛 常见问题

### 问题 1：Python 版本不兼容
```bash
# 解决方案：使用 Python 3.11+
python3.11 --version
python3.11 -m venv venv
```

### 问题 2：pip 安装超时
```bash
# 解决方案：使用国内镜像
pip install -r requirements.txt -i https://pypi.tsinghua.edu.cn/simple
```

### 问题 3：Redis 连接失败
```bash
# 解决方案：启动 Redis
redis-server

# 或者在 macOS 上
brew services start redis
```

### 问题 4：端口被占用
```bash
# 查找占用端口的进程
lsof -i :8765
lsof -i :8501

# 杀死进程
kill -9 <PID>

# 或者修改启动脚本中的端口号
```

### 问题 5：权限不足
```bash
# Linux/macOS 解决方案
sudo chown -R $USER:$USER .
chmod -R 755 .

# Windows 解决方案
# 以管理员身份运行命令行
```

---

## 📚 后续步骤

1. ✅ 阅读架构宪法：`.cursorrules`
2. ✅ 查看代码检查报告：`CODE_REVIEW_AND_INTEGRATION_CHECK.md`
3. ✅ 了解优化方案：`COMPREHENSIVE_LOGIC_CHECK_AND_OPTIMIZATION_V8.md`
4. ✅ 开始开发：修改代码并测试

---

## 📞 获取帮助

- 📖 查看文档：`README.md`
- 🐛 报告问题：GitHub Issues
- 💬 讨论功能：GitHub Discussions

---

**祝你启动顺利！** 🚀
