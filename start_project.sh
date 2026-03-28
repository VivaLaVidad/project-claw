#!/bin/bash
# Project Claw 一键启动脚本 v1.0
# 用法：bash start_project.sh

set -e

echo "🚀 Project Claw 启动系统"
echo "================================"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 1. 检查 Python 版本
echo -e "${YELLOW}[1/10] 检查 Python 版本...${NC}"
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo -e "${GREEN}✓ Python 版本: $python_version${NC}"

# 2. 创建虚拟环境
echo -e "${YELLOW}[2/10] 创建虚拟环境...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "${GREEN}✓ 虚拟环境已创建${NC}"
else
    echo -e "${GREEN}✓ 虚拟环境已存在${NC}"
fi

# 3. 激活虚拟环境
echo -e "${YELLOW}[3/10] 激活虚拟环境...${NC}"
source venv/bin/activate
echo -e "${GREEN}✓ 虚拟环境已激活${NC}"

# 4. 升级 pip
echo -e "${YELLOW}[4/10] 升级 pip...${NC}"
pip install --upgrade pip setuptools wheel -q
echo -e "${GREEN}✓ pip 已升级${NC}"

# 5. 安装依赖
echo -e "${YELLOW}[5/10] 安装项目依赖...${NC}"
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt -q
    echo -e "${GREEN}✓ 依赖已安装${NC}"
else
    echo -e "${RED}✗ requirements.txt 不存在${NC}"
    exit 1
fi

# 6. 初始化数据库
echo -e "${YELLOW}[6/10] 初始化数据库...${NC}"
mkdir -p claw_db
python3 << 'PYEOF'
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
else:
    print("✓ 审计数据库已存在")

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
else:
    print("✓ 死信队列数据库已存在")
PYEOF

# 7. 检查环境变量
echo -e "${YELLOW}[7/10] 检查环境变量...${NC}"
if [ -f ".env" ]; then
    source .env
    echo -e "${GREEN}✓ 环境变量已加载${NC}"
else
    echo -e "${YELLOW}⚠ .env 文件不存在，使用默认配置${NC}"
fi

# 8. 启动 Redis（如果需要）
echo -e "${YELLOW}[8/10] 检查 Redis...${NC}"
if command -v redis-server &> /dev/null; then
    if ! pgrep -x "redis-server" > /dev/null; then
        redis-server --daemonize yes
        echo -e "${GREEN}✓ Redis 已启动${NC}"
    else
        echo -e "${GREEN}✓ Redis 已在运行${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Redis 未安装，某些功能可能不可用${NC}"
fi

# 9. 启动后端服务
echo -e "${YELLOW}[9/10] 启动后端服务...${NC}"
python3 -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload &
BACKEND_PID=$!
echo -e "${GREEN}✓ 后端服务已启动 (PID: $BACKEND_PID)${NC}"

# 10. 启动融资路演大屏
echo -e "${YELLOW}[10/10] 启动融资路演大屏...${NC}"
streamlit run cloud_server/god_dashboard.py --server.port 8501 &
DASHBOARD_PID=$!
echo -e "${GREEN}✓ 融资路演大屏已启动 (PID: $DASHBOARD_PID)${NC}"

# 显示启动信息
echo ""
echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}🎉 Project Claw 已启动！${NC}"
echo -e "${GREEN}================================${NC}"
echo ""
echo "📍 服务地址："
echo "  - 后端 API: http://localhost:8765"
echo "  - API 文档: http://localhost:8765/docs"
echo "  - 融资路演大屏: http://localhost:8501"
echo "  - C 端演示前端: file://$(pwd)/mock_client/index.html"
echo ""
echo "📝 进程 ID："
echo "  - 后端服务: $BACKEND_PID"
echo "  - 融资路演大屏: $DASHBOARD_PID"
echo ""
echo "🛑 停止服务："
echo "  - kill $BACKEND_PID $DASHBOARD_PID"
echo ""
echo "📚 文档："
echo "  - 架构宪法: .cursorrules"
echo "  - 代码检查: CODE_REVIEW_AND_INTEGRATION_CHECK.md"
echo "  - 优化方案: COMPREHENSIVE_LOGIC_CHECK_AND_OPTIMIZATION_V8.md"
echo ""

# 保持脚本运行
wait
