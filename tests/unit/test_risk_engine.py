"""单元测试：风险评分引擎（规则部分，不依赖 Redis）。"""
import pytest

from app.services.risk_engine import _rule_based_score
from app.services.ip_geo_service import GeoInfo


class TestRuleBasedScore:
    def _geo(self, country_code: str, lat=None, lng=None) -> GeoInfo:
        return GeoInfo(ip="1.2.3.4", country="Test", country_code=country_code, lat=lat, lng=lng)

    def test_blacklist_country_high_score(self):
        geo = self._geo("KP")
        score, rules = _rule_based_score(geo, False, False, None, "LOGIN", "CN")
        assert score >= 0.9
        assert any("BLACKLIST" in r for r in rules)

    def test_foreign_country_login(self):
        geo = self._geo("US")
        score, rules = _rule_based_score(geo, False, False, None, "LOGIN", "CN")
        assert score > 0
        assert "FOREIGN_COUNTRY_LOGIN" in rules

    def test_same_country_no_foreign_rule(self):
        geo = self._geo("CN")
        score, rules = _rule_based_score(geo, False, False, None, "LOGIN", "CN")
        assert "FOREIGN_COUNTRY_LOGIN" not in rules

    def test_new_device_login(self):
        geo = self._geo("CN")
        score, rules = _rule_based_score(geo, True, False, None, "LOGIN", "CN")
        assert "NEW_DEVICE_LOGIN" in rules

    def test_new_device_action_no_rule(self):
        geo = self._geo("CN")
        score, rules = _rule_based_score(geo, True, False, None, "ACTION", "CN")
        assert "NEW_DEVICE_LOGIN" not in rules

    def test_vpn_detected(self):
        geo = self._geo("CN")
        score, rules = _rule_based_score(geo, False, True, None, "ACTION", "CN")
        assert "VPN_DETECTED" in rules
        assert score >= 0.3

    def test_large_distance(self):
        geo = self._geo("JP")
        score, rules = _rule_based_score(geo, False, False, 5000, "LOGIN", "CN")
        assert any("LARGE_DISTANCE" in r for r in rules)

    def test_medium_distance(self):
        geo = self._geo("CN")
        score, rules = _rule_based_score(geo, False, False, 1500, "LOGIN", "CN")
        assert any("MEDIUM_DISTANCE" in r for r in rules)

    def test_score_capped_at_one(self):
        geo = self._geo("KP")  # 黑名单
        score, _ = _rule_based_score(geo, True, True, 9000, "LOGIN", "US")
        assert score <= 1.0

    def test_no_geo_returns_partial_score(self):
        score, rules = _rule_based_score(None, True, True, None, "LOGIN", "CN")
        assert score > 0
        assert "VPN_DETECTED" in rules
