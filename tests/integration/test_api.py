"""集成测试：API 端点（健康检查、事件上报、风险查询、告警）。"""
import uuid
import pytest


class TestHealth:
    @pytest.mark.asyncio
    async def test_health_check(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestEventsAPI:
    @pytest.mark.asyncio
    async def test_create_event_requires_auth(self, client):
        resp = await client.post("/api/v1/events/", json={})
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_create_event_success(self, client, auth_headers, sample_user_id):
        payload = {
            "user_id": sample_user_id,
            "event_type": "LOGIN",
            "ip_address": "192.168.1.1",
            "device_info": {
                "user_agent": "Mozilla/5.0",
                "timezone": "Asia/Shanghai",
            },
        }
        resp = await client.post("/api/v1/events/", json=payload, headers=auth_headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["event_type"] == "LOGIN"
        assert data["user_id"] == sample_user_id

    @pytest.mark.asyncio
    async def test_create_event_invalid_type(self, client, auth_headers, sample_user_id):
        payload = {"user_id": sample_user_id, "event_type": "INVALID_TYPE"}
        resp = await client.post("/api/v1/events/", json=payload, headers=auth_headers)
        assert resp.status_code == 422


class TestRiskAPI:
    @pytest.mark.asyncio
    async def test_get_score_not_found(self, client, auth_headers, sample_user_id):
        resp = await client.get(
            f"/api/v1/risk/{sample_user_id}/score", headers=auth_headers
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_history_empty(self, client, auth_headers, sample_user_id):
        resp = await client.get(
            f"/api/v1/risk/{sample_user_id}/history", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_get_summary(self, client, auth_headers, sample_user_id):
        resp = await client.get(
            f"/api/v1/risk/{sample_user_id}/summary", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_score"] == 0
        assert data["level"] == "normal"


class TestAlertsAPI:
    @pytest.mark.asyncio
    async def test_list_alerts_empty(self, client, auth_headers):
        resp = await client.get("/api/v1/alerts/", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_get_nonexistent_alert(self, client, auth_headers):
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/api/v1/alerts/{fake_id}", headers=auth_headers)
        assert resp.status_code == 404
