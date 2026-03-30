FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY . .

# 创建日志目录
RUN mkdir -p /app/logs

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV DEEPSEEK_API_KEY=""
ENV REDIS_URL=""
ENV LEDGER_ENABLED="0"
ENV CLEARING_ENABLED="0"
ENV SOCIAL_ENABLED="0"
ENV HUB_JWT_SECRET="claw-change-in-prod"
ENV HUB_MERCHANT_KEY="merchant-shared-key"

# 暴露端口（Railway 会注入 PORT，默认 8080）
EXPOSE 8080

# 启动命令（必须使用动态 PORT，避免 healthcheck 失败）
CMD ["sh", "-c", "uvicorn cloud_server.signaling_hub:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1 --log-level info"]
