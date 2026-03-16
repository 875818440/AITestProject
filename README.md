# 社交媒体账号被盗风险预警系统

基于深度学习（LSTM）的实时账号安全预警平台。

## 技术栈

- **Python 3.11** + **FastAPI** — 异步 Web 框架
- **PyTorch** — LSTM 异常检测模型
- **PostgreSQL** — 主数据库（按月分区表）
- **Redis** — 特征序列缓存 + 告警去重
- **Celery** — 异步任务队列
- **Docker Compose** — 容器编排

## 快速启动

### 1. 环境配置

```bash
cp .env.example .env
# 编辑 .env，填写 PostgreSQL/Redis/SMTP/SMS/FCM 等配置
```

### 2. 启动依赖服务

```bash
cd docker
docker compose up -d postgres redis
```

### 3. 数据库迁移

```bash
pip install -e ".[dev]"
alembic upgrade head
```

### 4. 训练初始模型

```bash
python ml_training/train.py --epochs 50 --version v1
```

### 5. 启动服务

```bash
# API 服务
uvicorn app.main:app --reload

# Celery Worker（新终端）
celery -A app.tasks.celery_app worker --loglevel=info

# Celery Beat 定时任务（新终端）
celery -A app.tasks.celery_app beat --loglevel=info
```

### 6. 完整 Docker 启动

```bash
cd docker
docker compose up -d
```

访问 API 文档：http://localhost:8000/docs

## 项目结构

```
app/
├── api/v1/endpoints/   # RESTful 端点（auth/events/risk/alerts/ml）
├── core/               # 配置、数据库、Redis、JWT
├── models/             # ORM 模型 + Pydantic Schema
├── services/           # 特征工程、GeoIP、风险评分、告警分发
├── ml/                 # LSTM 模型定义 + 推理引擎
└── tasks/              # Celery 异步任务
ml_training/            # 离线训练脚本
migrations/             # Alembic 数据库迁移
tests/                  # 单元 + 集成测试
```

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/auth/register` | 用户注册 |
| POST | `/api/v1/auth/login` | 获取 JWT Token |
| POST | `/api/v1/events/` | 上报行为事件 |
| GET  | `/api/v1/risk/{user_id}/score` | 最新风险评分 |
| GET  | `/api/v1/risk/{user_id}/history` | 风险评分历史 |
| GET  | `/api/v1/risk/{user_id}/summary` | 风险摘要（含趋势） |
| GET  | `/api/v1/alerts/` | 告警列表 |
| PATCH| `/api/v1/alerts/{id}/acknowledge` | 确认告警 |
| POST | `/api/v1/ml/retrain` | 触发模型重训练 |
| GET  | `/api/v1/ml/models` | 模型版本列表 |
| GET  | `/health` | 健康检查 |
| GET  | `/metrics` | Prometheus 指标 |

## 风险等级

| 评分 | 等级 | 处理策略 |
|------|------|---------|
| 0–30 | 🟢 normal | 仅记录日志 |
| 31–60 | 🟡 low | 记录 + 标记 |
| 61–80 | 🟠 medium | 二次验证 + 告警 |
| 81–100 | 🔴 high | 强制告警 + 临时封禁 |

## 运行测试

```bash
pytest tests/ -v
```
