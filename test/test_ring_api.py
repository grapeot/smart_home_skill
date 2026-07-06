from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app
from services.ring_service import _public_status


client = TestClient(app)


def test_ring_status_endpoint_returns_read_only_sensor_payload():
    payload = {
        "schema_version": "smart_home.ring_client_status.v0",
        "source": "ring-client-api",
        "configured": True,
        "locations": [
            {
                "name": "Home",
                "has_alarm_base_station": True,
                "devices": [
                    {
                        "name": "Back Door",
                        "device_type": "contact_sensor",
                        "faulted": False,
                        "battery_level": 91,
                    }
                ],
            }
        ],
    }

    with patch("api.ring.ring_service.get_status", return_value=payload):
        response = client.get("/api/ring/status")

    assert response.status_code == 200
    assert response.json()["locations"][0]["devices"][0]["name"] == "Back Door"
    assert response.json()["locations"][0]["devices"][0]["faulted"] is False


def test_ring_status_endpoint_handles_unconfigured_host():
    payload = {
        "schema_version": "smart_home.ring_client_status.v0",
        "source": "ring-client-api",
        "configured": False,
        "locations": [],
        "error": "Ring private config not found",
    }

    with patch("api.ring.ring_service.get_status", return_value=payload):
        response = client.get("/api/ring/status")

    assert response.status_code == 200
    assert response.json()["configured"] is False
    assert response.json()["locations"] == []


def test_public_status_removes_ring_identifiers():
    payload = {
        "schema_version": "smart_home.ring_client_status.v0",
        "source": "ring-client-api",
        "configured": True,
        "locations": [
            {
                "id": "location-under-test",
                "name": "Home",
                "devices": [
                    {
                        "id": "device-under-test",
                        "name": "Back Door",
                        "device_type": "contact_sensor",
                        "faulted": False,
                        "room_id": 123,
                        "parent_zid": "private-parent-id",
                    }
                ],
            }
        ],
    }

    public = _public_status(payload)

    assert public["locations"][0]["name"] == "Home"
    assert public["locations"][0]["devices"][0]["name"] == "Back Door"
    assert "id" not in public["locations"][0]
    assert "id" not in public["locations"][0]["devices"][0]
    assert "room_id" not in public["locations"][0]["devices"][0]
    assert "parent_zid" not in public["locations"][0]["devices"][0]
