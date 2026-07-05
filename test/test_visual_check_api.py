from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def test_openapi_contains_visual_check_routes():
    schema = client.get("/openapi.json").json()

    assert "/api/visual-checks" in schema["paths"]
    assert "/api/visual-checks/{check_id}/run" in schema["paths"]
    assert "post" in schema["paths"]["/api/visual-checks/{check_id}/run"]


@patch("api.visual_check.visual_check_service.list_checks")
def test_list_visual_checks(mock_list):
    mock_list.return_value = [{"id": "garage", "group": "nightly", "source": "camera_snapshot"}]

    response = client.get("/api/visual-checks")

    assert response.status_code == 200
    assert response.json()["checks"][0]["id"] == "garage"


@patch("api.visual_check.visual_check_service.run_check", new_callable=AsyncMock)
def test_run_visual_check(mock_run):
    mock_run.return_value = {"schema_version": "smart_home.visual_check_result.v1", "check_id": "garage", "status": "ok"}

    response = client.post("/api/visual-checks/garage/run")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    mock_run.assert_awaited_once_with("garage")
