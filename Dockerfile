FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10 \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

# 安装系统依赖（国内镜像源 + 重试）
RUN set -eux; \
    sed -i 's/deb.debian.org/mirrors.tencent.com/g' /etc/apt/sources.list.d/debian.sources; \
    sed -i 's/security.debian.org/mirrors.tencent.com/g' /etc/apt/sources.list.d/debian.sources; \
    for i in 1 2 3; do apt-get update && break || sleep 5; done; \
    apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      libsm6 \
      libxext6 \
      libxrender-dev \
      libgomp1; \
    rm -rf /var/lib/apt/lists/*

# 先复制依赖文件，提升缓存命中率
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# 复制项目文件
COPY . /app
RUN chmod +x /app/start.sh

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8765/health || exit 1

CMD ["/app/start.sh"]
