# GitHub Copilot Instructions

## 项目名称与用途

**项目名称**：AI 社交媒体账号被盗风险预警系统（AICopilotProject）

**用途**：
基于深度学习（LSTM）对用户行为序列进行实时分析，计算账号被盗风险评分（0–100 分），
并在风险超过阈值时通过短信、邮件、App 推送等多渠道自动预警。
系统以 RESTful API 形式对外提供服务，供前端和第三方平台集成。

---

## 技术栈说明

| 层次 | 技术 | 说明 |
|------|------|------|
| Web 框架 | FastAPI 0.110+ | 异步 API、自动文档、依赖注入 |
| 深度学习 | PyTorch 2.2+ | LSTM 行为序列建模、FocalLoss |
| 数据库 | PostgreSQL 16 + asyncpg | 主存储，Alembic 迁移管理 |
| 缓存 / 队列 | Redis 7 | 特征序列缓存、速率统计、告警去重 |
| 异步任务 | Celery 5 + Celery Beat | 风险评分、告警分发、模型重训 |
| 数据验证 | Pydantic v2 | 请求 / 响应 Schema |
| 容器化 | Docker + docker-compose | 本地开发与生产部署 |
| Python 版本 | Python 3.11 | 全项目统一版本 |

---

## 编码规范

### 格式化

- **必须** 使用 [Black](https://black.readthedocs.io/) 进行代码格式化，行长度限制 **88** 字符。
- **必须** 使用 [isort](https://pycqa.github.io/isort/) 对导入排序，profile 设置为 `black`。
- 提交前执行：
  ```bash
  black .
  isort .
  ```

### 类型注解

- 所有函数 / 方法的参数和返回值 **必须** 添加类型注解。
- 使用 `from __future__ import annotations` 启用延迟求值（Python 3.11 可选，但推荐保持一致）。
- 复杂类型使用 `typing` 或 `collections.abc` 中的标准类型。
- 示例：
  ```python
  from __future__ import annotations

  async def calculate_risk(user_id: str, event: BehaviorEvent) -> RiskScore:
      ...
  ```

### Docstring

- 所有公开的类、函数、方法 **必须** 编写 docstring，格式遵循 **Google Style**。
- 私有方法（`_` 前缀）视复杂度酌情添加。
- 示例：
  ```python
  def compute_velocity_score(user_id: str, window_seconds: int = 60) -> float:
      """计算指定时间窗口内的用户操作速率评分。

      Args:
          user_id: 用户唯一标识符。
          window_seconds: 统计时间窗口，单位秒，默认 60。

      Returns:
          速率评分，范围 0.0–1.0，值越高风险越大。

      Raises:
          RedisConnectionError: 当 Redis 连接不可用时抛出。
      """
  ```

### 其他规范

- 禁止使用裸 `except:`，必须指定异常类型。
- 日志使用 `structlog` 结构化输出，禁止使用 `print()`。
- 常量统一在 `app/core/config.py` 的 `Settings` 类中通过环境变量管理，禁止硬编码。
- 异步函数优先使用 `async/await`，避免在异步上下文中调用阻塞 I/O。

---

## 安全要求

### API 鉴权

- **所有** API 接口（除 `/health`、`/docs`、`/openapi.json` 外）**必须** 进行 JWT 鉴权。
- 鉴权通过 `app/api/deps.py` 中的 `get_current_user` 依赖注入实现。
- Token 有效期最长 **24 小时**，刷新 Token 有效期最长 **7 天**。
- 示例：
  ```python
  @router.get("/risk/score")
  async def get_risk_score(
      current_user: User = Depends(get_current_user),
  ) -> RiskScoreResponse:
      ...
  ```

### 敏感数据加密

- 密码存储 **必须** 使用 `bcrypt`（cost factor ≥ 12）进行哈希，禁止明文存储。
- 数据库中的手机号、邮箱等 PII 字段 **必须** 使用 AES-256-GCM 加密后存储。
- 所有加密 / 解密操作统一在 `app/core/security.py` 中实现，业务层禁止直接操作加密原语。
- 密钥通过环境变量 `SECRET_KEY` / `ENCRYPTION_KEY` 注入，禁止写入代码或版本库。
- HTTPS 在生产环境为强制要求；开发环境 API 响应头中敏感字段（如 token）不得写入日志。

### 其他安全要求

- SQL 查询 **必须** 使用 SQLAlchemy ORM 或参数化查询，禁止字符串拼接构造 SQL。
- 所有外部输入（请求体、路径参数、查询参数）必须通过 Pydantic Schema 验证后再使用。
- 依赖库定期使用 `pip audit` 或 `safety` 扫描已知漏洞。
- Redis 中存储的用户数据设置合理的 TTL，避免长期留存敏感信息。

---

## 模型训练要求

### 序列化保存

- 所有训练完成的模型 **必须** 可序列化并保存为 `.pt` 文件，包含以下字段：
  ```python
  {
      "model_state_dict": model.state_dict(),   # 模型权重
      "hyperparams": { ... },                   # 超参数（hidden_dim、num_layers 等）
      "metrics": { ... },                       # 评估指标（AUC、F1、loss 等）
      "version": "1.0.0",                       # 语义化版本号
      "trained_at": "2024-01-01T00:00:00Z",     # 训练完成时间（ISO 8601）
  }
  ```
- 使用 `torch.save()` 保存，`torch.load()` 加载，加载时 **必须** 指定 `weights_only=True`（PyTorch 2.x 安全要求）。
- 模型文件命名规则：`lstm_{version}.pt`，存放于 `ml_training/models/` 目录（已加入 `.gitignore`）。

### 推理接口

- 所有模型推理通过 `app/ml/predictor.py` 中的单例 `BehaviorPredictor` 访问，不得在业务层直接实例化模型。
- 推理器支持 **热重载**（`reload_model()`），新模型训练完成后无需重启服务即可生效。

### 训练规范

- 训练脚本位于 `ml_training/train.py`，必须支持以下命令行参数：
  - `--epochs`、`--batch-size`、`--learning-rate`、`--output-dir`
- 训练过程中 **必须** 记录每个 epoch 的 loss 和验证集指标，输出至结构化日志。
- 模型上线前必须在验证集上达到 **AUC ≥ 0.85**，否则不允许替换生产模型。
- 特征维度（`FEATURE_DIM = 32`）和序列长度（`SEQUENCE_LENGTH`）变更时，必须同步更新 `app/core/config.py` 并重新训练模型。
