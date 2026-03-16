"""特征工程服务。

负责：
1. 从 Redis 获取用户近期行为序列（滑动窗口）
2. 将原始事件转换为 LSTM 输入特征向量
3. 维护序列缓存（LPUSH + LTRIM）
"""
import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any

import numpy as np

from app.core.config import settings
from app.core.redis_client import get_redis
from app.core.logging import get_logger
from app.services.ip_geo_service import GeoInfo

logger = get_logger(__name__)

FEATURE_DIM = 32          # 每个时间步的特征维度
SEQ_KEY_PREFIX = "feat:seq:"   # Redis key 前缀


# ───────────────────────────────────────────────
# 设备指纹
# ───────────────────────────────────────────────

def compute_device_fingerprint(device_info: dict | None, user_agent: str | None) -> str | None:
    """对设备信息做 SHA-256 指纹。"""
    if not device_info and not user_agent:
        return None
    raw = json.dumps(
        {
            "ua": user_agent or "",
            "screen": device_info.get("screen_resolution") if device_info else "",
            "tz": device_info.get("timezone") if device_info else "",
            "lang": device_info.get("language") if device_info else "",
            "canvas": device_info.get("canvas_hash") if device_info else "",
            "webgl": device_info.get("webgl_hash") if device_info else "",
        },
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode()).hexdigest()


# ───────────────────────────────────────────────
# 单事件向量化
# ───────────────────────────────────────────────

def _event_type_onehot(event_type: str) -> list[float]:
    types = ["LOGIN", "LOGOUT", "ACTION", "PAGE_VIEW", "API_CALL"]
    return [1.0 if event_type == t else 0.0 for t in types]


def _hour_features(ts: datetime) -> list[float]:
    """将小时转为周期性特征（sin/cos）。"""
    h = ts.hour + ts.minute / 60.0
    return [math.sin(2 * math.pi * h / 24), math.cos(2 * math.pi * h / 24)]


def _dow_features(ts: datetime) -> list[float]:
    """将星期转为周期性特征（sin/cos）。"""
    d = ts.weekday()
    return [math.sin(2 * math.pi * d / 7), math.cos(2 * math.pi * d / 7)]


def vectorize_event(
    event_type: str,
    created_at: datetime,
    geo: GeoInfo | None,
    is_new_device: bool,
    is_vpn: bool,
    distance_from_home_km: float | None,
    duration_ms: int | None,
    interval_from_last_s: float | None,
) -> list[float]:
    """
    将单个事件转换为固定长度特征向量（FEATURE_DIM=32）。
    索引布局：
      [0:5]   event_type one-hot (5)
      [5:7]   hour sin/cos (2)
      [7:9]   day-of-week sin/cos (2)
      [9]     is_new_device (1)
      [10]    is_vpn (1)
      [11]    distance_normalized (1, 0 if unknown)
      [12]    duration_log (1, 0 if unknown)
      [13]    interval_log (1, 0 if unknown)
      [14:17] country one-hot (simplified: CN/US/Other/Unknown)
      [17:22] action_feature placeholder (5, zeros)
      [22:32] padding zeros (10)
    """
    vec: list[float] = []

    # event_type one-hot [0:5]
    vec.extend(_event_type_onehot(event_type))

    # 时间周期特征 [5:9]
    vec.extend(_hour_features(created_at))
    vec.extend(_dow_features(created_at))

    # 设备/网络风险特征 [9:14]
    vec.append(1.0 if is_new_device else 0.0)
    vec.append(1.0 if is_vpn else 0.0)
    vec.append(min((distance_from_home_km or 0) / 10000.0, 1.0))  # 归一化到 [0,1]
    vec.append(math.log1p(duration_ms or 0) / 15.0)               # log 压缩后归一化
    vec.append(math.log1p(interval_from_last_s or 0) / 20.0)

    # 国家 one-hot [14:18]
    country = (geo.country_code or "").upper() if geo else ""
    vec.extend([
        1.0 if country == "CN" else 0.0,
        1.0 if country == "US" else 0.0,
        1.0 if (country not in ("CN", "US", "")) else 0.0,
        1.0 if country == "" else 0.0,
    ])

    # 预留扩展位 [18:32]
    vec.extend([0.0] * (FEATURE_DIM - len(vec)))

    assert len(vec) == FEATURE_DIM, f"特征维度错误: {len(vec)} != {FEATURE_DIM}"
    return vec


# ───────────────────────────────────────────────
# Redis 序列缓存
# ───────────────────────────────────────────────

async def push_event_to_sequence(user_id: str, feature_vec: list[float]) -> None:
    """将特征向量追加到用户的 Redis 序列（自动维护窗口长度）。"""
    redis = get_redis()
    key = f"{SEQ_KEY_PREFIX}{user_id}"
    serialized = json.dumps(feature_vec)
    await redis.lpush(key, serialized)
    await redis.ltrim(key, 0, settings.feature_sequence_length - 1)
    await redis.expire(key, 86400 * 7)  # 7 天 TTL


async def get_user_sequence(user_id: str) -> np.ndarray | None:
    """
    从 Redis 读取用户行为序列，返回形状 (T, FEATURE_DIM) 的 numpy 数组。
    序列长度不足时返回 None（等待积累足够数据）。
    """
    redis = get_redis()
    key = f"{SEQ_KEY_PREFIX}{user_id}"
    raw_list = await redis.lrange(key, 0, settings.feature_sequence_length - 1)

    if not raw_list:
        return None

    vecs = [json.loads(r) for r in raw_list]
    # Redis lpush 是头部插入，最新在前，需要反转为时序顺序
    vecs.reverse()

    # 不足窗口长度时，在前面补零（zero-padding）
    while len(vecs) < settings.feature_sequence_length:
        vecs.insert(0, [0.0] * FEATURE_DIM)

    arr = np.array(vecs, dtype=np.float32)   # (T, FEATURE_DIM)
    return arr
