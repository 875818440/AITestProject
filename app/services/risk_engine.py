"""多因子风险评分引擎。

评分公式：
    final_score = lstm_score×0.6 + rule_score×0.25 + velocity_score×0.15

分数范围：0~100，等级：normal / low / medium / high
"""
import uuid
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field

import numpy as np

from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis_client import get_redis
from app.ml.predictor import predictor
from app.services.feature_engineering import get_user_sequence
from app.services.ip_geo_service import GeoInfo

logger = get_logger(__name__)

# 权重
WEIGHT_LSTM = 0.60
WEIGHT_RULE = 0.25
WEIGHT_VELOCITY = 0.15

# 速率限制（Redis key 前缀）
VELOCITY_KEY = "velocity:"


@dataclass
class ScoreComponents:
    lstm_prob: float = 0.0        # 0~1
    rule_prob: float = 0.0        # 0~1
    velocity_prob: float = 0.0    # 0~1
    final_score: int = 0          # 0~100
    level: str = "normal"
    triggered_rules: list[str] = field(default_factory=list)
    attention_weights: list[float] = field(default_factory=list)


# ──────────────────────────────────────────────
# 规则引擎
# ──────────────────────────────────────────────

# 已知高危 IP 段（示例，实际应从数据库或威胁情报服务加载）
_BLACKLIST_COUNTRIES = {"KP", "IR"}   # 演示用黑名单国家

def _rule_based_score(
    geo: GeoInfo | None,
    is_new_device: bool,
    is_vpn: bool,
    distance_from_home_km: float | None,
    event_type: str,
    home_country: str | None,
) -> tuple[float, list[str]]:
    """基于规则的风险概率打分（0~1）。"""
    score = 0.0
    rules: list[str] = []

    if geo:
        # 黑名单国家
        if (geo.country_code or "").upper() in _BLACKLIST_COUNTRIES:
            score += 0.9
            rules.append(f"BLACKLIST_COUNTRY:{geo.country_code}")

        # 异地登录（与注册地不同国）
        if home_country and geo.country_code and geo.country_code.upper() != home_country.upper():
            score += 0.5
            rules.append("FOREIGN_COUNTRY_LOGIN")

        # 超远距离（>3000km）
        if distance_from_home_km and distance_from_home_km > 3000:
            score += 0.4
            rules.append(f"LARGE_DISTANCE:{distance_from_home_km:.0f}km")
        elif distance_from_home_km and distance_from_home_km > 1000:
            score += 0.2
            rules.append(f"MEDIUM_DISTANCE:{distance_from_home_km:.0f}km")

    # 新设备 + 登录操作
    if is_new_device and event_type == "LOGIN":
        score += 0.4
        rules.append("NEW_DEVICE_LOGIN")

    # VPN 使用
    if is_vpn:
        score += 0.3
        rules.append("VPN_DETECTED")

    return min(score, 1.0), rules


# ──────────────────────────────────────────────
# 速率异常检测
# ──────────────────────────────────────────────

async def _velocity_score(user_id: str, event_type: str) -> tuple[float, list[str]]:
    """检测高频操作异常（滑动窗口计数）。"""
    redis = get_redis()
    rules: list[str] = []
    score = 0.0

    now = datetime.now(timezone.utc)
    window_1min = f"{VELOCITY_KEY}{user_id}:1min"
    window_5min = f"{VELOCITY_KEY}{user_id}:5min"

    # 滑动计数
    pipe = redis.pipeline()
    pipe.incr(window_1min)
    pipe.expire(window_1min, 60)
    pipe.incr(window_5min)
    pipe.expire(window_5min, 300)
    results = await pipe.execute()

    count_1min = results[0]
    count_5min = results[2]

    if event_type == "LOGIN":
        if count_1min > 5:
            score += 0.8
            rules.append(f"LOGIN_BURST_1MIN:{count_1min}")
        elif count_1min > 3:
            score += 0.4
            rules.append(f"LOGIN_FREQ_1MIN:{count_1min}")

    if count_5min > 30:
        score += 0.5
        rules.append(f"HIGH_FREQ_5MIN:{count_5min}")
    elif count_5min > 15:
        score += 0.2
        rules.append(f"MEDIUM_FREQ_5MIN:{count_5min}")

    return min(score, 1.0), rules


# ──────────────────────────────────────────────
# 主评分入口
# ──────────────────────────────────────────────

async def compute_risk_score(
    user_id: str,
    event_type: str,
    geo: GeoInfo | None = None,
    is_new_device: bool = False,
    is_vpn: bool = False,
    distance_from_home_km: float | None = None,
    home_country: str | None = None,
) -> ScoreComponents:
    """计算综合风险评分。"""
    all_triggered_rules: list[str] = []
    attention_weights: list[float] = []

    # 1. LSTM 评分
    sequence = await get_user_sequence(user_id)
    if sequence is not None:
        lstm_prob, attention_weights = predictor.predict(sequence)
    else:
        lstm_prob = 0.0   # 序列不足，暂不使用 LSTM 分

    # 2. 规则引擎评分
    rule_prob, rule_triggered = _rule_based_score(
        geo, is_new_device, is_vpn, distance_from_home_km, event_type, home_country
    )
    all_triggered_rules.extend(rule_triggered)

    # 3. 速率异常评分
    velocity_prob, velocity_triggered = await _velocity_score(user_id, event_type)
    all_triggered_rules.extend(velocity_triggered)

    # 4. 加权融合
    weighted = (
        lstm_prob * WEIGHT_LSTM
        + rule_prob * WEIGHT_RULE
        + velocity_prob * WEIGHT_VELOCITY
    )
    final_score = min(int(round(weighted * 100)), 100)

    # 5. 确定等级
    cfg = settings
    if final_score < cfg.risk_threshold_low:
        level = "normal"
    elif final_score < cfg.risk_threshold_medium:
        level = "low"
    elif final_score < cfg.risk_threshold_high:
        level = "medium"
    else:
        level = "high"

    logger.debug(
        "风险评分计算",
        user_id=user_id,
        final_score=final_score,
        level=level,
        lstm_prob=round(lstm_prob, 4),
        rule_prob=round(rule_prob, 4),
        velocity_prob=round(velocity_prob, 4),
    )

    return ScoreComponents(
        lstm_prob=lstm_prob,
        rule_prob=rule_prob,
        velocity_prob=velocity_prob,
        final_score=final_score,
        level=level,
        triggered_rules=all_triggered_rules,
        attention_weights=attention_weights,
    )
