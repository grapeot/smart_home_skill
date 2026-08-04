import asyncio
import json
import stat

import pytest

from models import database
from services.meross_service import MerossService


class DummyDevice:
    uuid = "device-uuid"
    name = "Garage Controller"
    channels = [{}, {}, {}]

    def __init__(self, is_open=False):
        self._is_open = is_open

    def get_is_open(self, door_index):
        return self._is_open


def write_local_cache(path, device_uuid="device-uuid"):
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "device_uuid": device_uuid,
                "device_name": "Garage Controller",
                "local_ip": "192.0.2.10",
                "key": "test-key",
                "door_count": 2,
                "updated_at": "2026-08-01T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )


def test_build_local_message_has_signed_header(monkeypatch):
    service = MerossService()
    service.device = DummyDevice()
    service._local_ip = "192.0.2.10"
    service._key = "test-key"

    monkeypatch.setattr("services.meross_service.time.time", lambda: 1234567890)
    monkeypatch.setattr("services.meross_service.secrets.token_hex", lambda n: "abc123")

    message = service._build_local_message(
        "Appliance.GarageDoor.State",
        "SET",
        {"state": {"channel": 1, "open": 0}},
    )

    header = message["header"]
    assert header["messageId"] == "abc123"
    assert header["namespace"] == "Appliance.GarageDoor.State"
    assert header["method"] == "SET"
    assert header["from"] == "http://192.0.2.10/config"
    assert header["uuid"] == "device-uuid"
    assert header["sign"] == "f94a53353b58257ae7b1aa38561bf2c6"


def test_get_current_open_state_prefers_local_payload():
    service = MerossService()
    service.device = DummyDevice(is_open=False)

    assert service._get_current_open_state(1, {"open": 1}) is True
    assert service._get_current_open_state(1, {"open": 0}) is False


def test_get_current_open_state_falls_back_to_sdk_state():
    service = MerossService()
    service.device = DummyDevice(is_open=True)

    assert service._get_current_open_state(1, {}) is True


def test_select_garage_device_by_uuid(monkeypatch):
    service = MerossService()
    devices = [DummyDevice(), DummyDevice()]
    devices[0].uuid = "wrong"
    devices[1].uuid = "expected"

    monkeypatch.setenv("MEROSS_GARAGE_UUID", "expected")

    assert service._select_garage_device(devices) is devices[1]


def test_select_garage_device_requires_selector_for_multiple_devices(monkeypatch):
    service = MerossService()
    monkeypatch.delenv("MEROSS_GARAGE_UUID", raising=False)
    monkeypatch.delenv("MEROSS_GARAGE_NAME", raising=False)

    assert service._select_garage_device([DummyDevice(), DummyDevice()]) is None


def test_save_local_cache_is_private_and_loadable(tmp_path, monkeypatch):
    cache_path = tmp_path / "meross.json"
    monkeypatch.setenv("MEROSS_GARAGE_LOCAL_CACHE_PATH", str(cache_path))
    service = MerossService()
    service.device = DummyDevice()
    service._local_ip = "192.0.2.10"
    service._key = "test-key"

    service._save_local_cache()

    data = json.loads(cache_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["device_uuid"] == "device-uuid"
    assert data["door_count"] == 2
    assert stat.S_IMODE(cache_path.stat().st_mode) == 0o600

    cached_service = MerossService()
    assert cached_service._load_local_cache() is True
    assert cached_service._connected is True
    assert cached_service.get_door_count() == 2
    assert cached_service._get_device_uuid() == "device-uuid"


@pytest.mark.asyncio
async def test_connect_without_cloud_credentials_uses_local_cache(tmp_path, monkeypatch):
    cache_path = tmp_path / "meross.json"
    write_local_cache(cache_path)
    monkeypatch.setenv("MEROSS_GARAGE_LOCAL_CACHE_PATH", str(cache_path))
    monkeypatch.delenv("MEROSS_EMAIL", raising=False)
    monkeypatch.delenv("MEROSS_PASSWORD", raising=False)

    service = MerossService()

    assert await service.connect() is True
    assert service.device is None
    assert service._connected is True
    assert service.get_door_count() == 2


@pytest.mark.asyncio
async def test_connect_uses_local_cache_when_cloud_login_fails(tmp_path, monkeypatch):
    from meross_iot.http_api import MerossHttpClient

    cache_path = tmp_path / "meross.json"
    write_local_cache(cache_path)
    monkeypatch.setenv("MEROSS_GARAGE_LOCAL_CACHE_PATH", str(cache_path))
    monkeypatch.setenv("MEROSS_EMAIL", "user@example.com")
    monkeypatch.setenv("MEROSS_PASSWORD", "password")

    async def fail_cloud_login(*args, **kwargs):
        raise RuntimeError("offline")

    monkeypatch.setattr(MerossHttpClient, "async_from_user_password", fail_cloud_login)

    service = MerossService()

    assert await service.connect() is True
    assert service.device is None
    assert service._connected is True
    assert service.get_door_count() == 2


@pytest.mark.asyncio
async def test_connect_bounds_cloud_wait_before_using_local_cache(tmp_path, monkeypatch):
    cache_path = tmp_path / "meross.json"
    write_local_cache(cache_path)
    monkeypatch.setenv("MEROSS_GARAGE_LOCAL_CACHE_PATH", str(cache_path))
    monkeypatch.setenv("MEROSS_GARAGE_CLOUD_TIMEOUT_SECONDS", "0.01")
    monkeypatch.setenv("MEROSS_EMAIL", "user@example.com")
    monkeypatch.setenv("MEROSS_PASSWORD", "password")
    service = MerossService()

    async def hanging_cloud_login(*args, **kwargs):
        await asyncio.sleep(60)

    monkeypatch.setattr(service, "_connect_cloud", hanging_cloud_login)

    assert await service.connect() is True
    assert service.device is None
    assert service._connected is True


@pytest.mark.asyncio
async def test_connect_does_not_use_cache_after_ambiguous_cloud_discovery(tmp_path, monkeypatch):
    cache_path = tmp_path / "meross.json"
    write_local_cache(cache_path)
    monkeypatch.setenv("MEROSS_GARAGE_LOCAL_CACHE_PATH", str(cache_path))
    monkeypatch.setenv("MEROSS_EMAIL", "user@example.com")
    monkeypatch.setenv("MEROSS_PASSWORD", "password")
    service = MerossService()

    async def ambiguous_cloud_discovery(*args, **kwargs):
        return False

    monkeypatch.setattr(service, "_connect_cloud", ambiguous_cloud_discovery)

    assert await service.connect() is False
    assert service._connected is False


@pytest.mark.asyncio
async def test_failed_connect_clears_partial_device_state(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("MEROSS_GARAGE_LOCAL_CACHE_PATH", str(tmp_path / "missing.json"))
    monkeypatch.setenv("MEROSS_EMAIL", "user@example.com")
    monkeypatch.setenv("MEROSS_PASSWORD", "password")
    service = MerossService()

    async def partial_cloud_failure(*args, **kwargs):
        service.device = DummyDevice()
        service._local_ip = "192.0.2.10"
        service._key = "stale-key"
        raise RuntimeError("login-secret")

    monkeypatch.setattr(service, "_connect_cloud", partial_cloud_failure)

    assert await service.connect() is False
    assert service.device is None
    assert service._local_ip is None
    assert service._key is None
    assert await service.toggle_door(1) == {"status": "error", "message": "Not connected"}
    assert "login-secret" not in caplog.text
    assert "stale-key" not in caplog.text


def test_local_cache_rejects_different_configured_uuid(tmp_path, monkeypatch):
    cache_path = tmp_path / "meross.json"
    write_local_cache(cache_path, device_uuid="cached-device")
    monkeypatch.setenv("MEROSS_GARAGE_LOCAL_CACHE_PATH", str(cache_path))
    monkeypatch.setenv("MEROSS_GARAGE_UUID", "different-device")

    service = MerossService()

    assert service._load_local_cache() is False
    assert service._connected is False


def test_local_cache_rejects_invalid_ip_address(tmp_path, monkeypatch):
    cache_path = tmp_path / "meross.json"
    write_local_cache(cache_path)
    data = json.loads(cache_path.read_text(encoding="utf-8"))
    data["local_ip"] = "example.com/path"
    cache_path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setenv("MEROSS_GARAGE_LOCAL_CACHE_PATH", str(cache_path))

    service = MerossService()

    assert service._load_local_cache() is False
    assert service._connected is False


@pytest.mark.asyncio
async def test_toggle_door_uses_local_http_backend(monkeypatch):
    service = MerossService()
    service.device = DummyDevice(is_open=True)
    service._connected = True
    service._local_ip = "192.0.2.10"
    service._key = "test-key"
    service._verify_timeout_seconds = 0.1
    service._verify_poll_interval_seconds = 0.01

    calls = []
    get_calls = 0

    def fake_local_request(namespace, method, payload):
        nonlocal get_calls
        calls.append((namespace, method, payload))
        if method == "GET":
            get_calls += 1
            return {"state": {"channel": 1, "open": 1 if get_calls == 1 else 0}}
        return {"state": {"channel": 1, "open": 1, "execute": 1}}

    monkeypatch.setattr(service, "_local_request", fake_local_request)

    result = await service.toggle_door(1)

    assert result["status"] == "success"
    assert result["target_open"] is False
    assert result["verified"] is True
    assert calls[:2] == [
        ("Appliance.GarageDoor.State", "GET", {"state": {"channel": 1}}),
        (
            "Appliance.GarageDoor.State",
            "SET",
            {"state": {"channel": 1, "open": 0, "uuid": "device-uuid"}},
        ),
    ]


@pytest.mark.asyncio
async def test_toggle_door_reports_unverified_when_state_does_not_change(monkeypatch):
    service = MerossService()
    service.device = DummyDevice(is_open=True)
    service._connected = True
    service._local_ip = "192.0.2.10"
    service._key = "test-key"
    service._verify_timeout_seconds = 0.01
    service._verify_poll_interval_seconds = 0.01

    def fake_local_request(namespace, method, payload):
        if method == "GET":
            return {"state": {"channel": 1, "open": 1}}
        return {"state": {"channel": 1, "open": 1, "execute": 1}}

    monkeypatch.setattr(service, "_local_request", fake_local_request)

    result = await service.toggle_door(1)

    assert result["status"] == "triggered_unverified"
    assert result["verified"] is False
    assert result["target_open"] is False
    assert "not verified" in result["message"]


@pytest.mark.asyncio
async def test_toggle_door_works_with_cached_local_configuration(monkeypatch):
    service = MerossService()
    service._device_uuid = "device-uuid"
    service._door_count = 2
    service._local_ip = "192.0.2.10"
    service._key = "test-key"
    service._connected = True
    service._verify_timeout_seconds = 0.1
    service._verify_poll_interval_seconds = 0.01

    calls = []
    get_calls = 0

    def fake_local_request(namespace, method, payload):
        nonlocal get_calls
        calls.append((namespace, method, payload))
        if method == "GET":
            get_calls += 1
            return {"state": {"channel": 1, "open": 1 if get_calls == 1 else 0}}
        return {"state": {"channel": 1, "open": 1, "execute": 1}}

    monkeypatch.setattr(service, "_local_request", fake_local_request)

    result = await service.toggle_door(1)

    assert result["status"] == "success"
    assert result["verified"] is True
    assert calls[1][2]["state"]["uuid"] == "device-uuid"


@pytest.mark.asyncio
async def test_toggle_door_honors_unresolved_bridge_fence(tmp_path, monkeypatch):
    original_path = database.DB_PATH
    database.DB_PATH = tmp_path / "bridge.db"
    database.init_db()
    try:
        database.claim_garage_bridge_command(
            "bridge", "00112233445566778899aabbccddeeff", "hash", "{}", "1",
            "garage.toggle", 1, "live",
        )
        service = MerossService()
        service._connected = True

        result = await service.toggle_door(1)

        assert result["status"] == "error"
        assert result["error_code"] == "garage_bridge_target_blocked"
    finally:
        database.DB_PATH = original_path
