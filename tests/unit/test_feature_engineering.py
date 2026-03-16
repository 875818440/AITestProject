"""单元测试：特征工程。"""
import math
import pytest
import numpy as np

from app.services.feature_engineering import (
    FEATURE_DIM,
    compute_device_fingerprint,
    vectorize_event,
    _event_type_onehot,
    _hour_features,
    _dow_features,
)
from app.services.ip_geo_service import GeoInfo
from datetime import datetime, timezone


class TestEventTypeOneHot:
    def test_login(self):
        vec = _event_type_onehot("LOGIN")
        assert vec[0] == 1.0
        assert sum(vec) == 1.0

    def test_unknown_returns_zeros(self):
        vec = _event_type_onehot("UNKNOWN")
        assert all(v == 0.0 for v in vec)


class TestHourFeatures:
    def test_midnight(self):
        ts = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        sin_h, cos_h = _hour_features(ts)
        assert abs(sin_h - 0.0) < 1e-5
        assert abs(cos_h - 1.0) < 1e-5

    def test_noon(self):
        ts = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        sin_h, cos_h = _hour_features(ts)
        assert abs(sin_h - 0.0) < 1e-5
        assert abs(cos_h - (-1.0)) < 1e-5


class TestVectorizeEvent:
    def test_output_dimension(self):
        ts = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
        geo = GeoInfo(ip="1.2.3.4", country="China", country_code="CN")
        vec = vectorize_event(
            event_type="LOGIN",
            created_at=ts,
            geo=geo,
            is_new_device=False,
            is_vpn=False,
            distance_from_home_km=None,
            duration_ms=None,
            interval_from_last_s=None,
        )
        assert len(vec) == FEATURE_DIM

    def test_new_device_flag(self):
        ts = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
        vec = vectorize_event(
            event_type="ACTION",
            created_at=ts,
            geo=None,
            is_new_device=True,
            is_vpn=False,
            distance_from_home_km=None,
            duration_ms=None,
            interval_from_last_s=None,
        )
        assert vec[9] == 1.0  # is_new_device index

    def test_vpn_flag(self):
        ts = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
        vec = vectorize_event(
            event_type="ACTION",
            created_at=ts,
            geo=None,
            is_new_device=False,
            is_vpn=True,
            distance_from_home_km=None,
            duration_ms=None,
            interval_from_last_s=None,
        )
        assert vec[10] == 1.0  # is_vpn index

    def test_all_values_bounded(self):
        ts = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
        geo = GeoInfo(ip="8.8.8.8", country="United States", country_code="US")
        vec = vectorize_event(
            event_type="LOGIN",
            created_at=ts,
            geo=geo,
            is_new_device=True,
            is_vpn=True,
            distance_from_home_km=5000,
            duration_ms=3000,
            interval_from_last_s=60,
        )
        # sin/cos 特征超出 [-1, 1]，其余应在 [0, 1]
        for i, v in enumerate(vec):
            assert -1.1 <= v <= 1.1, f"vec[{i}]={v} 超出范围"


class TestDeviceFingerprint:
    def test_same_input_same_hash(self):
        device_info = {"screen_resolution": "1920x1080", "timezone": "Asia/Shanghai"}
        h1 = compute_device_fingerprint(device_info, "Mozilla/5.0")
        h2 = compute_device_fingerprint(device_info, "Mozilla/5.0")
        assert h1 == h2

    def test_different_input_different_hash(self):
        h1 = compute_device_fingerprint({"screen_resolution": "1080p"}, "Chrome")
        h2 = compute_device_fingerprint({"screen_resolution": "4K"}, "Chrome")
        assert h1 != h2

    def test_none_input_returns_none(self):
        assert compute_device_fingerprint(None, None) is None
