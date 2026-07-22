import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from services.camera_service import CameraService


@pytest.fixture
def camera_service():
    service = CameraService()
    service.set_credentials("admin", "test_password")
    service.cameras = [
        {"name": "Test Camera", "id": "test_cam", "ip": "192.168.1.100"}
    ]
    return service


class TestCameraService:
    def test_get_cameras(self, camera_service):
        cameras = camera_service.get_cameras()
        assert len(cameras) == 1
        assert cameras[0]["name"] == "Test Camera"
        assert cameras[0]["id"] == "test_cam"
        assert "ip" not in cameras[0]

    def test_get_camera_by_id(self, camera_service):
        camera = camera_service.get_camera_by_id("test_cam")
        assert camera is not None
        assert camera["name"] == "Test Camera"
        assert camera["ip"] == "192.168.1.100"

    def test_get_camera_by_id_not_found(self, camera_service):
        camera = camera_service.get_camera_by_id("nonexistent")
        assert camera is None

    @pytest.mark.asyncio
    async def test_get_snapshot_success(self, camera_service):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"fake_image_data"

        with patch.object(camera_service, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            image_data, error = await camera_service.get_snapshot("test_cam")
            assert error is None
            assert image_data == b"fake_image_data"

    @pytest.mark.asyncio
    async def test_get_snapshot_camera_not_found(self, camera_service):
        image_data, error = await camera_service.get_snapshot("nonexistent")
        assert image_data is None
        assert "not found" in error

    @pytest.mark.asyncio
    async def test_get_snapshot_timeout(self, camera_service):
        import httpx

        with patch.object(camera_service, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            mock_get_client.return_value = mock_client

            image_data, error = await camera_service.get_snapshot("test_cam")
            assert image_data is None
            assert "Timeout" in error

    @pytest.mark.asyncio
    async def test_get_snapshot_retries_disconnect_with_backoff(self, camera_service):
        import httpx

        failed_client = AsyncMock()
        failed_client.get = AsyncMock(side_effect=httpx.RemoteProtocolError("disconnected"))
        success_response = MagicMock(status_code=200, content=b"fake_image_data")
        success_client = AsyncMock()
        success_client.get = AsyncMock(return_value=success_response)

        with patch.object(camera_service, "_get_client", side_effect=[failed_client, success_client]), patch.object(
            camera_service, "_reset_client", new_callable=AsyncMock
        ) as reset_client, patch("services.camera_service.asyncio.sleep", new_callable=AsyncMock) as sleep:
            image_data, error = await camera_service.get_snapshot("test_cam")

        assert error is None
        assert image_data == b"fake_image_data"
        reset_client.assert_awaited_once()
        sleep.assert_awaited_once_with(1)

    @pytest.mark.asyncio
    async def test_close_client(self, camera_service):
        mock_client = AsyncMock()
        camera_service._client = mock_client

        await camera_service.close()
        assert camera_service._client is None
        mock_client.aclose.assert_called_once()
