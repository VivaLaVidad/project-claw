# Project Claw 完整部署指南

## 部署方式对比

| 方式 | 环境 | 难度 | 推荐场景 |
|------|------|------|---------|
| **本地运行** | 开发机 | ⭐ | 开发测试 |
| **Docker** | 单容器 | ⭐⭐ | 小规模部署 |
| **Docker Compose** | 多容器 | ⭐⭐⭐ | 生产环境 |

---

## 方式1：本地运行（推荐开发环境）

### 前置条件

- Python 3.10+
- pip 包管理器
- 微信已连接 uiautomator2

### 安装步骤

**第一步：克隆项目**
```bash
cd d:\桌面\Project Claw
```

**第二步：创建虚拟环境（可选但推荐）**
```bash
python -m venv venv
venv\Scripts\activate
```

**第三步：安装依赖**
```bash
pip install -r requirements.txt
```

**第四步：配置环境变量**
```bash
# 复制示例文件
copy .env.example .env

# 编辑 .env 文件，填入实际值
# DEEPSEEK_API_KEY=sk-...
# FEISHU_APP_ID=cli_...
# FEISHU_APP_SECRET=...
```

**第五步：运行系统**
```bash
# 使用部署脚本
deploy.bat local

# 或直接运行
python lobster_with_openclaw.py
```

### 查看日志

```bash
# 实时日志
tail -f lobster_openclaw.log

# 或在 Windows 中
type lobster_openclaw.log
```

---

## 方式2：Docker 单容器部署

### 前置条件

- Docker 已安装
- Docker 守护进程正在运行

### 安装步骤

**第一步：构建镜像**
```bash
deploy.bat docker-build

# 或手动构建
docker build -t project-claw:latest .
```

**第二步：配置环境变量**
```bash
copy .env.example .env
# 编辑 .env 文件
```

**第三步：运行容器**
```bash
deploy.bat docker-run

# 或手动运行
docker run -it ^
    --name project-claw ^
    -p 8000:8000 ^
    -e DEEPSEEK_API_KEY=sk-... ^
    -e FEISHU_APP_ID=cli_... ^
    -e FEISHU_APP_SECRET=... ^
    -v %cd%\logs:/app/logs ^
    project-claw:latest
```

**第四步：查看日志**
```bash
docker logs -f project-claw
```

**第五步：停止容器**
```bash
docker stop project-claw
docker rm project-claw
```

---

## 方式3：Docker Compose 多容器部署（推荐生产环境）

### 前置条件

- Docker 已安装
- Docker Compose 已安装
- Docker 守护进程正在运行

### 安装步骤

**第一步：配置环境变量**
```bash
copy .env.example .env
# 编辑 .env 文件，填入实际值
```

**第二步：启动服务**
```bash
deploy.bat docker-compose

# 或手动启动
docker-compose up -d
```

**第三步：查看服务状态**
```bash
docker-compose ps

# 输出示例
NAME                COMMAND             STATUS
project-claw-main   python ...          Up 2 minutes
project-claw-api    python ...          Up 1 minute
```

**第四步：查看日志**
```bash
# 查看所有服务日志
docker-compose logs -f

# 查看特定服务日志
docker-compose logs -f project-claw

# 查看 API 服务日志
docker-compose logs -f api-server
```

**第五步：访问服务**
```
主服务: http://localhost:8000
API 服务: http://localhost:8001/docs
```

**第六步：停止服务**
```bash
deploy.bat docker-stop

# 或手动停止
docker-compose down
```

---

## 环境变量配置

### 必需变量

```bash
# DeepSeek API
DEEPSEEK_API_KEY=sk-4aab42a0cace4e9a8c9bb31faa8c8f01

# 飞书配置
FEISHU_APP_ID=cli_a937f9e24c21dbc8
FEISHU_APP_SECRET=REZKNlpObMfWsPJwnSloJhIwiaB2FGVZ

# OpenClaw 配置
OPENCLAW_CONFIG_PATH=d:\OpenClaw_System\Config\openclaw.json
```

### 可选变量

```bash
# 飞书 Webhook（可选）
FEISHU_WEBHOOK_URL=

# 日志配置
LOG_LEVEL=INFO
LOG_PATH=./logs

# 系统配置
CHECK_INTERVAL=5
DEDUP_WINDOW=30
MAX_FAILURES=5
```

---

## 部署脚本使用

### Windows 部署脚本

```bash
# 显示帮助
deploy.bat help

# 本地运行
deploy.bat local

# Docker 构建
deploy.bat docker-build

# Docker 运行
deploy.bat docker-run

# Docker Compose 运行
deploy.bat docker-compose

# 停止 Docker Compose
deploy.bat docker-stop
```

### Linux/Mac 部署脚本

```bash
# 赋予执行权限
chmod +x deploy.sh

# 显示帮助
./deploy.sh help

# 本地运行
./deploy.sh local

# Docker 构建
./deploy.sh docker-build

# Docker 运行
./deploy.sh docker-run

# Docker Compose 运行
./deploy.sh docker-compose

# 停止 Docker Compose
./deploy.sh docker-stop
```

---

## Docker 常用命令

### 镜像管理

```bash
# 列出镜像
docker images

# 删除镜像
docker rmi project-claw:latest

# 标记镜像
docker tag project-claw:latest project-claw:v1.0
```

### 容器管理

```bash
# 列出运行中的容器
docker ps

# 列出所有容器
docker ps -a

# 查看容器日志
docker logs -f project-claw

# 进入容器
docker exec -it project-claw bash

# 停止容器
docker stop project-claw

# 删除容器
docker rm project-claw
```

### Docker Compose 管理

```bash
# 启动服务
docker-compose up -d

# 停止服务
docker-compose down

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f

# 重启服务
docker-compose restart

# 更新服务
docker-compose up -d --build
```

---

## 故障排查

### 问题1：Docker 镜像构建失败

**症状**：`docker build` 命令失败

**解决**：
```bash
# 检查 Dockerfile 是否存在
ls Dockerfile

# 检查 requirements.txt 是否存在
ls requirements.txt

# 查看详细错误
docker build -t project-claw:latest . --verbose
```

### 问题2：容器启动失败

**症状**：容器立即退出

**解决**：
```bash
# 查看容器日志
docker logs project-claw

# 检查环境变量是否正确
docker inspect project-claw | grep -A 20 "Env"

# 手动运行容器查看错误
docker run -it project-claw:latest bash
```

### 问题3：端口被占用

**症状**：`bind: address already in use`

**解决**：
```bash
# 查看占用端口的进程
netstat -ano | findstr :8000

# 杀死进程
taskkill /PID <PID> /F

# 或修改 docker-compose.yml 中的端口
# ports:
#   - "8002:8000"
```

### 问题4：环境变量未生效

**症状**：系统无法读取环境变量

**解决**：
```bash
# 检查 .env 文件是否存在
ls .env

# 检查 .env 文件格式
cat .env

# 手动设置环境变量
set DEEPSEEK_API_KEY=sk-...
docker-compose up -d
```

---

## 性能优化

### 1. 资源限制

编辑 `docker-compose.yml`：

```yaml
services:
  project-claw:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
```

### 2. 日志管理

```yaml
services:
  project-claw:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

### 3. 健康检查

```yaml
services:
  project-claw:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

---

## 监控和日志

### 查看实时日志

```bash
# Docker Compose
docker-compose logs -f

# 特定服务
docker-compose logs -f project-claw

# 最后 100 行
docker-compose logs --tail=100
```

### 日志文件位置

```
本地运行: ./logs/lobster_openclaw.log
Docker: /app/logs/lobster_openclaw.log
```

### 日志级别

```python
# 在代码中设置
logging.basicConfig(level=logging.INFO)

# 或通过环境变量
export LOG_LEVEL=DEBUG
```

---

## 生产环境建议

1. **使用 Docker Compose**：便于管理多个服务
2. **配置健康检查**：自动重启失败的容器
3. **设置资源限制**：防止资源耗尽
4. **启用日志轮转**：防止日志文件过大
5. **使用环境变量**：敏感信息不要硬编码
6. **定期备份**：备份配置和数据
7. **监控告警**：监控系统状态和性能

---

## 快速参考

### 本地开发

```bash
# 一键启动
deploy.bat local
```

### Docker 开发

```bash
# 构建并运行
deploy.bat docker-build
deploy.bat docker-run
```

### 生产部署

```bash
# 配置环境变量
copy .env.example .env
# 编辑 .env

# 启动所有服务
deploy.bat docker-compose

# 查看日志
docker-compose logs -f

# 停止服务
deploy.bat docker-stop
```

---

**最后更新**：2026-03-21
**版本**：v3.0
**作者**：Project Claw Team
