FROM python:3.11-slim

WORKDIR /app

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# 依赖安装（利用 Docker 层缓存）
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dev]"

# 拷贝源码
COPY . .

# 创建非 root 用户运行
RUN adduser --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s \
  CMD curl -f http://localhost:8000/health || exit 1
