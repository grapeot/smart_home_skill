import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, Mock

import main
from main import app


client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_control_token(monkeypatch):
    monkeypatch.delenv("SMART_HOME_API_TOKEN", raising=False)


class TestHealthEndpoint:
    
    def test_health_check(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestOpenAPI:

    def test_openapi_contains_agent_contract(self):
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        paths = schema["paths"]

        assert "/api/garage/{door_index}/toggle" in paths
        assert "post" in paths["/api/garage/{door_index}/toggle"]
        assert "get" not in paths["/api/garage/{door_index}/toggle"]
        for path in [
            "/api/hue/off",
            "/api/hue/on",
            "/api/hue/on/{brightness}",
            "/api/hue/toggle",
            "/api/wemo/{device_name}/toggle",
            "/api/wemo/{device_name}/on",
            "/api/wemo/{device_name}/off",
            "/api/rinnai/maintenance",
            "/api/rinnai/circulate",
            "/api/roon/play",
            "/api/roon/pause",
            "/api/roon/stop",
            "/api/roon/playpause",
            "/api/roon/sleep-timer",
            "/api/roon/pair/start",
            "/api/kids-music/playpause",
        ]:
            assert "post" in paths[path]
            assert "get" not in paths[path]
        assert "get" in paths["/api/roon/status"]
        assert "get" in paths["/api/roon/zones"]
        assert "get" in paths["/api/roon/pair/status"]
        assert "get" in paths["/api/kids-music/state"]
        assert "/{full_path}" not in paths
        assert schema["info"]["title"] == "Smart Home Skill"

    @pytest.mark.parametrize("path", [
        "/api/hue/toggle",
        "/api/hue/off",
        "/api/hue/on",
        "/api/wemo/coffee/toggle",
        "/api/wemo/coffee/on",
        "/api/wemo/coffee/off",
        "/api/rinnai/maintenance",
        "/api/rinnai/circulate",
    ])
    def test_retired_get_mutations_do_not_fall_through_to_spa(self, path):
        response = client.get(path)

        assert response.status_code == 404
        assert "text/html" not in response.headers.get("content-type", "")
        assert response.json()["detail"] == "API route not found"


class TestRootEndpoint:
    
    def test_root_serves_spa(self):
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert "<!doctype html>" in response.text.lower() or "<html" in response.text.lower()

    def test_spa_rejects_path_traversal(self, tmp_path, monkeypatch):
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "index.html").write_text("<html>spa</html>")
        (tmp_path / "secret.txt").write_text("do-not-serve")
        monkeypatch.setattr(main, "FRONTEND_DIST", dist)

        response = client.get("/%2e%2e/secret.txt")

        assert response.status_code == 200
        assert response.text == "<html>spa</html>"


class TestControlAuth:

    @patch('services.hue_service.hue_service.toggle')
    def test_control_token_required_when_configured(self, mock_toggle, monkeypatch):
        monkeypatch.setenv("SMART_HOME_API_TOKEN", "test-token")
        mock_toggle.return_value = {"status": "success"}

        response = client.post("/api/hue/toggle")

        assert response.status_code == 401
        mock_toggle.assert_not_called()

    @patch('services.hue_service.hue_service.toggle')
    def test_control_token_allows_mutation(self, mock_toggle, monkeypatch):
        monkeypatch.setenv("SMART_HOME_API_TOKEN", "test-token")
        mock_toggle.return_value = {"status": "success"}

        response = client.post("/api/hue/toggle", headers={"X-Smart-Home-Token": "test-token"})

        assert response.status_code == 200
        assert response.json()["status"] == "success"


class TestHueEndpoints:
    
    @patch('services.hue_service.hue_service.get_status')
    def test_get_hue_status(self, mock_get_status):
        mock_get_status.return_value = {"name": "Baby room", "is_on": True, "brightness": 128}
        
        response = client.get("/api/hue/status")
        assert response.status_code == 200
        assert response.json()["is_on"] == True
    
    @patch('services.hue_service.hue_service.turn_off')
    def test_hue_off(self, mock_turn_off):
        mock_turn_off.return_value = {"status": "success", "light": "Baby room"}
        
        response = client.post("/api/hue/off")
        assert response.status_code == 200
        assert response.json()["status"] == "success"
    
    @patch('services.hue_service.hue_service.turn_on')
    def test_hue_on(self, mock_turn_on):
        mock_turn_on.return_value = {"status": "success", "light": "Baby room", "brightness": 128}
        
        response = client.post("/api/hue/on")
        assert response.status_code == 200

    def test_hue_brightness_validation(self):
        response = client.post("/api/hue/on/999")
        assert response.status_code == 422


class TestWemoEndpoints:
    
    @patch('services.wemo_service.wemo_service.get_all_status')
    def test_get_wemo_status(self, mock_get_status):
        mock_get_status.return_value = {"coffee": {"name": "coffee", "is_on": True}}
        
        response = client.get("/api/wemo/status")
        assert response.status_code == 200
    
    @patch('services.wemo_service.wemo_service.toggle')
    def test_wemo_toggle(self, mock_toggle):
        mock_toggle.return_value = {"status": "success", "device": "coffee"}
        
        response = client.post("/api/wemo/coffee/toggle")
        assert response.status_code == 200


class TestRinnaiEndpoints:

    @patch('api.rinnai.rinnai_service.get_status', new_callable=AsyncMock)
    def test_get_rinnai_status(self, mock_get_status):
        mock_get_status.return_value = {
            "device_id": "test-device",
            "is_online": True,
            "set_temperature": 120
        }

        response = client.get("/api/rinnai/status")
        assert response.status_code == 200
        data = response.json()
        assert data["is_online"] is True
        assert data["set_temperature"] == 120

    @patch('api.rinnai.rinnai_service.trigger_maintenance_retrieval', new_callable=AsyncMock)
    def test_get_rinnai_maintenance(self, mock_maintenance):
        mock_maintenance.return_value = {"status": "success", "is_online": True}

        response = client.post("/api/rinnai/maintenance")
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_rinnai_circulate_duration_validation(self):
        response = client.post("/api/rinnai/circulate?duration=0")
        assert response.status_code == 422


class TestGarageEndpoints:

    @patch('api.garage.meross_service.get_door_count')
    @patch('api.garage.garage_config.get_doors')
    def test_get_garage_status_includes_display_labels(self, mock_get_doors, mock_door_count):
        mock_door_count.return_value = 2
        mock_get_doors.return_value = [
            {"index": 1, "label": "Garage door 1"},
            {"index": 2, "label": "Garage door 2"},
        ]

        response = client.get("/api/garage/status")

        assert response.status_code == 200
        data = response.json()
        assert data["door_count"] == 2
        assert data["doors"][0]["label"] == "Garage door 1"

    @patch('api.garage.meross_service.get_door_count')
    @patch('api.garage.meross_service.toggle_door', new_callable=AsyncMock)
    def test_garage_toggle_post(self, mock_toggle, mock_door_count):
        mock_door_count.return_value = 2
        mock_toggle.return_value = {"status": "success", "door": 1}

        response = client.post("/api/garage/1/toggle")

        assert response.status_code == 200
        assert response.json()["status"] == "success"
        mock_toggle.assert_awaited_once_with(1)

class TestStatusEndpoint:

    @patch('api.status._safe_ring_status')
    @patch('api.status.rinnai_service.get_status', new_callable=AsyncMock)
    def test_get_status_with_rinnai_refresh(self, mock_rinnai_status, mock_ring_status):
        mock_ring_status.return_value = {"configured": True, "locations": []}
        mock_rinnai_status.return_value = {
            "device_id": "test",
            "is_online": True,
            "set_temperature": 125,
        }

        response = client.get("/api/status?rinnai_refresh=true")
        assert response.status_code == 200
        data = response.json()
        assert "rinnai" in data
        assert data["rinnai"]["is_online"] is True
        mock_rinnai_status.assert_called_once_with(trigger_maintenance=True)

    @patch('services.wemo_service.wemo_service.get_all_status')
    def test_get_status_devices_wemo_only(self, mock_wemo):
        mock_wemo.return_value = {"coffee": {"name": "coffee", "is_on": True}}
        response = client.get("/api/status?devices=wemo")
        assert response.status_code == 200
        data = response.json()
        assert "wemo" in data
        assert "hue" not in data
        assert "rinnai" not in data
        assert "garage" not in data


class TestHistoryEndpoint:

    @patch('api.history.get_device_history')
    def test_history_timestamps_have_utc_suffix(self, mock_get_history):
        mock_get_history.return_value = [
            {
                "id": 1,
                "device_type": "rinnai",
                "device_name": "main_house",
                "timestamp": "2026-02-19 00:47:05",
                "data": {"inlet_temp": 66, "outlet_temp": 125},
            },
        ]
        response = client.get("/api/history?hours=24")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["timestamp"] == "2026-02-19T00:47:05Z"

    def test_history_hours_validation(self):
        response = client.get("/api/history?hours=9999")
        assert response.status_code == 422


class TestScheduleEndpoints:
    
    def test_create_action(self):
        with patch('api.schedule.dynamic_scheduler.schedule') as mock_schedule:
            mock_action = Mock()
            mock_action.to_dict.return_value = {
                'id': 'test123',
                'action': {'type': 'wemo.off', 'params': {'device': 'tree'}},
                'action_display': 'Turn tree off',
                'minutes': 5,
                'created_at': '2026-02-19T12:00:00',
                'execute_at': '2026-02-19T12:05:00',
                'status': 'pending',
            }
            mock_schedule.return_value = mock_action
            
            response = client.post("/api/schedule/actions", json={
                "minutes": 5,
                "action": {"type": "wemo.off", "params": {"device": "tree"}}
            })
            assert response.status_code == 200
            data = response.json()
            assert data["action"]["type"] == "wemo.off"
            assert data["minutes"] == 5
            assert data["status"] == "pending"
    
    def test_create_action_invalid_minutes(self):
        response = client.post("/api/schedule/actions", json={
            "minutes": 0,
            "action": {"type": "wemo.off", "params": {}}
        })
        assert response.status_code == 422

    def test_create_action_rejects_too_long_delay(self):
        response = client.post("/api/schedule/actions", json={
            "minutes": 1441,
            "action": {"type": "hue.off", "params": {}}
        })
        assert response.status_code == 422

    def test_create_action_rejects_unknown_type(self):
        response = client.post("/api/schedule/actions", json={
            "minutes": 5,
            "action": {"type": "unknown.action", "params": {}}
        })
        assert response.status_code == 422

    def test_create_action_requires_wemo_device(self):
        response = client.post("/api/schedule/actions", json={
            "minutes": 5,
            "action": {"type": "wemo.off", "params": {}}
        })
        assert response.status_code == 422

    def test_create_action_validates_rinnai_duration(self):
        response = client.post("/api/schedule/actions", json={
            "minutes": 5,
            "action": {"type": "rinnai.circulate", "params": {"duration": 120}}
        })
        assert response.status_code == 422

    def test_create_action_rejects_garage_by_default(self):
        response = client.post("/api/schedule/actions", json={
            "minutes": 5,
            "action": {"type": "garage.toggle", "params": {"door": 1}}
        })
        assert response.status_code == 403
    
    def test_list_actions(self):
        with patch('api.schedule.dynamic_scheduler.get_all') as mock_get_all:
            mock_get_all.return_value = []
            
            response = client.get("/api/schedule/actions")
            assert response.status_code == 200
            data = response.json()
            assert "actions" in data
    
    def test_list_actions_with_status_filter(self):
        with patch('api.schedule.dynamic_scheduler.get_all') as mock_get_all:
            mock_get_all.return_value = []
            
            response = client.get("/api/schedule/actions?status=pending")
            assert response.status_code == 200
            data = response.json()
            assert "actions" in data
    
    def test_cancel_action(self):
        with patch('api.schedule.dynamic_scheduler.cancel') as mock_cancel:
            mock_action = Mock()
            mock_action.to_dict.return_value = {
                'id': 'test123',
                'status': 'cancelled',
            }
            mock_cancel.return_value = mock_action
            
            response = client.delete("/api/schedule/actions/test123")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "cancelled"
    
    def test_cancel_nonexistent_action(self):
        with patch('api.schedule.dynamic_scheduler.cancel') as mock_cancel:
            mock_cancel.return_value = None
            
            response = client.delete("/api/schedule/actions/nonexistent")
            assert response.status_code == 404


class TestRoonApi:

    @patch("api.roon.roon_service.get_status")
    def test_roon_status(self, mock_status):
        mock_status.return_value = {
            "configured": True,
            "authorized": True,
            "connected": True,
            "core_name": "Quantum",
            "zones": [],
        }
        response = client.get("/api/roon/status")
        assert response.status_code == 200
        assert response.json()["core_name"] == "Quantum"

    @patch("api.roon.roon_service.play_playlist")
    def test_roon_play_playlist(self, mock_play):
        mock_play.return_value = {
            "status": "success",
            "message": "Playing",
            "zone": "bedroom",
            "playlist": "k-pop",
        }
        response = client.post(
            "/api/roon/play",
            json={"zone": "bedroom", "source": "playlist", "playlist": "k-pop"},
        )
        assert response.status_code == 200
        mock_play.assert_called_once_with("bedroom", "k-pop")

    @patch("api.kids_music.kids_music_service.playpause")
    def test_kids_music_playpause(self, mock_pp):
        mock_pp.return_value = {
            "status": "success",
            "action": "play",
            "remaining_plays": 2,
            "playing": True,
        }
        response = client.post("/api/kids-music/playpause")
        assert response.status_code == 200
        assert response.json()["action"] == "play"

    def test_create_roon_schedule_action_shape(self):
        with patch("api.schedule.dynamic_scheduler.schedule") as mock_schedule:
            mock_action = Mock()
            mock_action.to_dict.return_value = {
                "id": "r1",
                "action": {"type": "roon.stop", "params": {"zone": "bedroom"}},
                "action_display": "Stop bedroom",
                "minutes": 30,
                "status": "pending",
            }
            mock_schedule.return_value = mock_action
            response = client.post(
                "/api/schedule/actions",
                json={
                    "minutes": 30,
                    "action": {"type": "roon.stop", "params": {"zone": "bedroom"}},
                },
            )
            assert response.status_code == 200
            assert response.json()["action"]["type"] == "roon.stop"
