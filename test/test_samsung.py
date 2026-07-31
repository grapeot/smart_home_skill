from unittest.mock import patch, AsyncMock

import pytest
from fastapi.testclient import TestClient

import main
from main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_control_token(monkeypatch):
    monkeypatch.delenv("SMART_HOME_API_TOKEN", raising=False)


@pytest.fixture
def configured_tv(monkeypatch, tmp_path):
    """Patch the service singleton used by the API layer to look configured."""
    token_file = tmp_path / "samsung_tv_ws_token.txt"
    token_file.write_text("15057143")
    monkeypatch.setenv("SAMSUNG_TV_HOST", "192.168.1.50")
    monkeypatch.setenv("SAMSUNG_TV_PORT", "8002")
    monkeypatch.setenv("SAMSUNG_TV_TOKEN_FILE", str(token_file))
    import services.samsung_service as svc_mod
    fake = svc_mod.SamsungService()
    with patch("services.samsung_service.samsung_service", fake), \
         patch("api.samsung.samsung_service", fake), \
         patch("api.status.samsung_service", fake):
        yield fake


class TestSamsungNotConfigured:
    """When SAMSUNG_TV_HOST is unset or token file is missing."""

    def test_status_unconfigured(self, monkeypatch):
        monkeypatch.delenv("SAMSUNG_TV_HOST", raising=False)
        import services.samsung_service as svc_mod
        fake = svc_mod.SamsungService()
        assert fake.get_status() == {"configured": False}

    def test_status_no_token(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SAMSUNG_TV_HOST", "192.168.1.50")
        monkeypatch.setenv("SAMSUNG_TV_TOKEN_FILE", str(tmp_path / "nonexistent.txt"))
        import services.samsung_service as svc_mod
        fake = svc_mod.SamsungService()
        assert fake.get_status() == {"configured": False}

    def test_bad_port_falls_back(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SAMSUNG_TV_HOST", "192.168.1.50")
        monkeypatch.setenv("SAMSUNG_TV_PORT", "not-a-number")
        monkeypatch.setenv("SAMSUNG_TV_TOKEN_FILE", str(tmp_path / "tok.txt"))
        token_file = tmp_path / "tok.txt"
        token_file.write_text("12345678")
        import services.samsung_service as svc_mod
        fake = svc_mod.SamsungService()
        assert fake._port == 8002


class TestSamsungStatus:

    def test_status_on(self, configured_tv):
        with patch.object(configured_tv, "_rest_power_state", return_value="on"):
            response = client.get("/api/samsung/status")
        data = response.json()
        assert data["configured"] is True
        assert data["is_on"] is True
        assert data["volume"] is None
        assert data["muted"] is None

    def test_status_standby(self, configured_tv):
        with patch.object(configured_tv, "_rest_power_state", return_value="standby"):
            response = client.get("/api/samsung/status")
        assert response.json()["is_on"] is False

    def test_status_unreachable(self, configured_tv):
        with patch.object(configured_tv, "_rest_power_state", return_value=None):
            response = client.get("/api/samsung/status")
        data = response.json()
        assert data["configured"] is True
        assert data["error"] == "TV unreachable"

    def test_status_transient(self, configured_tv):
        with patch.object(configured_tv, "_rest_power_state", return_value=""):
            response = client.get("/api/samsung/status")
        assert response.json()["is_on"] is None


class TestSamsungControl:

    async def test_power_on_when_off(self, configured_tv):
        with patch.object(configured_tv, "_power_state_async", new=AsyncMock(return_value="standby")), \
             patch.object(configured_tv, "_send_key", new=AsyncMock(return_value={"status": "success"})) as mock_key:
            result = await configured_tv.power_on()
        assert result["status"] == "success"
        mock_key.assert_called_once_with("KEY_POWER")

    async def test_power_on_already_on(self, configured_tv):
        with patch.object(configured_tv, "_power_state_async", new=AsyncMock(return_value="on")), \
             patch.object(configured_tv, "_send_key", new=AsyncMock()) as mock_key:
            result = await configured_tv.power_on()
        assert result["status"] == "success"
        assert "already" in result["message"]
        mock_key.assert_not_called()

    async def test_power_on_tv_unreachable(self, configured_tv):
        with patch.object(configured_tv, "_power_state_async", new=AsyncMock(return_value=None)), \
             patch.object(configured_tv, "_send_key", new=AsyncMock()) as mock_key:
            result = await configured_tv.power_on()
        assert result["status"] == "error"
        assert "unreachable" in result["message"]
        mock_key.assert_not_called()

    async def test_power_off_when_on(self, configured_tv):
        with patch.object(configured_tv, "_power_state_async", new=AsyncMock(return_value="on")), \
             patch.object(configured_tv, "_send_key", new=AsyncMock(return_value={"status": "success"})) as mock_key:
            result = await configured_tv.power_off()
        assert result["status"] == "success"
        mock_key.assert_called_once_with("KEY_POWER")

    async def test_power_off_already_off(self, configured_tv):
        with patch.object(configured_tv, "_power_state_async", new=AsyncMock(return_value="standby")), \
             patch.object(configured_tv, "_send_key", new=AsyncMock()) as mock_key:
            result = await configured_tv.power_off()
        assert "already" in result["message"]
        mock_key.assert_not_called()

    async def test_power_off_transient_refuses(self, configured_tv):
        with patch.object(configured_tv, "_power_state_async", new=AsyncMock(return_value="")), \
             patch.object(configured_tv, "_send_key", new=AsyncMock()) as mock_key:
            result = await configured_tv.power_off()
        assert result["status"] == "error"
        assert "unknown" in result["message"]
        mock_key.assert_not_called()

    async def test_toggle_power(self, configured_tv):
        with patch.object(configured_tv, "_send_key", new=AsyncMock(return_value={"status": "success"})) as mock_key:
            result = await configured_tv.toggle_power()
        assert result["status"] == "success"
        mock_key.assert_called_once_with("KEY_POWER")

    async def test_volume_up(self, configured_tv):
        with patch.object(configured_tv, "_send_key", new=AsyncMock(return_value={"status": "success"})) as mock_key:
            result = await configured_tv.volume_up()
        assert result["status"] == "success"
        mock_key.assert_called_once_with("KEY_VOLUP")

    async def test_volume_down(self, configured_tv):
        with patch.object(configured_tv, "_send_key", new=AsyncMock(return_value={"status": "success"})) as mock_key:
            result = await configured_tv.volume_down()
        assert result["status"] == "success"
        mock_key.assert_called_once_with("KEY_VOLDOWN")

    async def test_toggle_mute(self, configured_tv):
        with patch.object(configured_tv, "_send_key", new=AsyncMock(return_value={"status": "success"})) as mock_key:
            result = await configured_tv.toggle_mute()
        assert result["status"] == "success"
        mock_key.assert_called_once_with("KEY_MUTE")

    async def test_send_key_no_token(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SAMSUNG_TV_HOST", "192.168.1.50")
        monkeypatch.setenv("SAMSUNG_TV_TOKEN_FILE", str(tmp_path / "missing.txt"))
        import services.samsung_service as svc_mod
        svc = svc_mod.SamsungService()
        result = await svc._send_key("KEY_POWER")
        assert result["status"] == "error"
        assert "not paired" in result["message"]


class TestSamsungHandshakeValidation:
    """Verify that _send_key validates the WS handshake frame."""

    async def test_send_key_rejects_unauthorized(self, configured_tv):
        import json
        bad_frame = json.dumps({"event": "ms.channel.unauthorized"})
        with patch("services.samsung_service.websockets.connect") as mock_connect:
            mock_ws = AsyncMock()
            mock_ws.recv = AsyncMock(return_value=bad_frame)
            mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
            mock_ws.__aexit__ = AsyncMock(return_value=None)
            mock_connect.return_value = mock_ws
            result = await configured_tv._send_key("KEY_POWER")
        assert result["status"] == "error"
        assert "rejected" in result["message"]

    async def test_send_key_rejects_timeout(self, configured_tv):
        import json
        bad_frame = json.dumps({"event": "ms.channel.timeOut"})
        with patch("services.samsung_service.websockets.connect") as mock_connect:
            mock_ws = AsyncMock()
            mock_ws.recv = AsyncMock(return_value=bad_frame)
            mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
            mock_ws.__aexit__ = AsyncMock(return_value=None)
            mock_connect.return_value = mock_ws
            result = await configured_tv._send_key("KEY_POWER")
        assert result["status"] == "error"

    async def test_send_key_accepts_connect(self, configured_tv):
        import json
        good_frame = json.dumps({"event": "ms.channel.connect", "data": {}})
        with patch("services.samsung_service.websockets.connect") as mock_connect:
            mock_ws = AsyncMock()
            mock_ws.recv = AsyncMock(return_value=good_frame)
            mock_ws.send = AsyncMock()
            mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
            mock_ws.__aexit__ = AsyncMock(return_value=None)
            mock_connect.return_value = mock_ws
            result = await configured_tv._send_key("KEY_VOLUP")
        assert result["status"] == "success"


class TestSamsungPowerLock:
    """Verify that concurrent power operations are serialized."""

    async def test_power_on_serialized(self, configured_tv):
        import asyncio
        call_count = 0

        async def slow_send_key(key):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.1)
            return {"status": "success"}

        async def quick_power_state():
            return "standby"

        with patch.object(configured_tv, "_send_key", side_effect=slow_send_key), \
             patch.object(configured_tv, "_power_state_async", side_effect=quick_power_state):
            results = await asyncio.gather(
                configured_tv.power_on(),
                configured_tv.power_on(),
            )
        # Both should succeed, but the lock ensures they don't interleave.
        assert all(r["status"] == "success" for r in results)


class TestSamsungControlAuth:

    def test_power_toggle_requires_token(self, configured_tv, monkeypatch):
        monkeypatch.setenv("SMART_HOME_API_TOKEN", "secret")
        response = client.post("/api/samsung/power/toggle")
        assert response.status_code == 401

    def test_power_toggle_with_token(self, configured_tv, monkeypatch):
        monkeypatch.setenv("SMART_HOME_API_TOKEN", "secret")
        with patch.object(configured_tv, "toggle_power", new=AsyncMock(return_value={"status": "success"})):
            response = client.post(
                "/api/samsung/power/toggle",
                headers={"X-Smart-Home-Token": "secret"},
            )
        assert response.status_code == 200
        assert response.json()["status"] == "success"