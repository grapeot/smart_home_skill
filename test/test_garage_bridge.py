from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app
from models import database


client = TestClient(app)
HEADERS = {"X-Garage-Bridge-Token": "bridge-test-token"}


def command(command_id="00112233445566778899aabbccddeeff", counter="1"):
    return {
        "schema_version": 1,
        "command_id": command_id,
        "counter": counter,
        "operation": "garage.toggle",
    }


@pytest.fixture(autouse=True)
def bridge_environment(tmp_path, monkeypatch):
    original_path = database.DB_PATH
    database.DB_PATH = tmp_path / "bridge.db"
    database.init_db()
    monkeypatch.setenv("GARAGE_BRIDGE_TOKEN", "bridge-test-token")
    monkeypatch.setenv("GARAGE_BRIDGE_PRINCIPAL", "test-xiao")
    monkeypatch.setenv("GARAGE_BRIDGE_DOOR_INDEX", "1")
    monkeypatch.setenv("GARAGE_BRIDGE_MODE", "dry_run")
    yield
    database.DB_PATH = original_path


def test_bridge_auth_is_fail_closed(monkeypatch):
    monkeypatch.delenv("GARAGE_BRIDGE_TOKEN")
    response = client.post("/api/garage/bridge/commands", json=command())
    assert response.status_code == 503


@patch("services.garage_bridge_service.meross_service.toggle_door", new_callable=AsyncMock)
def test_dry_run_is_durable_and_never_calls_meross(mock_toggle):
    first = client.post("/api/garage/bridge/commands", headers=HEADERS, json=command())
    duplicate = client.post("/api/garage/bridge/commands", headers=HEADERS, json=command())
    query = client.get(
        "/api/garage/bridge/commands/00112233445566778899aabbccddeeff",
        headers=HEADERS,
    )

    assert first.status_code == 201
    assert duplicate.status_code == 200
    assert first.json() == duplicate.json() == query.json()
    assert first.json()["status"] == "dry_run"
    assert first.json()["terminal"] is True
    mock_toggle.assert_not_awaited()


def test_same_command_id_with_different_body_conflicts():
    assert client.post(
        "/api/garage/bridge/commands", headers=HEADERS, json=command()
    ).status_code == 201
    response = client.post(
        "/api/garage/bridge/commands", headers=HEADERS, json=command(counter="2")
    )
    assert response.status_code == 409


def test_query_remains_available_when_dispatch_is_disabled(monkeypatch):
    created = client.post(
        "/api/garage/bridge/commands", headers=HEADERS, json=command()
    )
    monkeypatch.setenv("GARAGE_BRIDGE_MODE", "disabled")

    queried = client.get(
        "/api/garage/bridge/commands/00112233445566778899aabbccddeeff",
        headers=HEADERS,
    )

    assert created.status_code == 201
    assert queried.status_code == 200
    assert queried.json() == created.json()


@patch("services.garage_bridge_service.meross_service.toggle_door", new_callable=AsyncMock)
def test_live_duplicate_dispatches_exactly_once(mock_toggle, monkeypatch):
    monkeypatch.setenv("GARAGE_BRIDGE_MODE", "live")
    mock_toggle.return_value = {"status": "success", "verified": True}

    first = client.post("/api/garage/bridge/commands", headers=HEADERS, json=command())
    duplicate = client.post("/api/garage/bridge/commands", headers=HEADERS, json=command())

    assert first.status_code == 201
    assert duplicate.status_code == 200
    assert first.json()["status"] == "verified"
    assert first.json() == duplicate.json()
    mock_toggle.assert_awaited_once_with(
        1,
        bridge_principal_id="test-xiao",
        bridge_command_id="00112233445566778899aabbccddeeff",
    )


@patch("services.garage_bridge_service.meross_service.toggle_door", new_callable=AsyncMock)
def test_live_timeout_becomes_unknown_and_blocks_another_action(mock_toggle, monkeypatch):
    monkeypatch.setenv("GARAGE_BRIDGE_MODE", "live")
    mock_toggle.side_effect = TimeoutError("response lost")

    first = client.post("/api/garage/bridge/commands", headers=HEADERS, json=command())
    duplicate = client.post("/api/garage/bridge/commands", headers=HEADERS, json=command())
    second = client.post(
        "/api/garage/bridge/commands",
        headers=HEADERS,
        json=command("ffeeddccbbaa99887766554433221100", "2"),
    )

    assert first.json()["status"] == "outcome_unknown"
    assert first.json()["blocks_target"] is True
    assert duplicate.json() == first.json()
    assert second.status_code == 409
    mock_toggle.assert_awaited_once_with(
        1,
        bridge_principal_id="test-xiao",
        bridge_command_id="00112233445566778899aabbccddeeff",
    )
