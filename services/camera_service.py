import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

import httpx
import yaml

logger = logging.getLogger(__name__)
SNAPSHOT_RETRY_DELAYS_SECONDS = (1, 3)


class CameraService:
    def __init__(self):
        self.cameras: list[dict] = []
        self.user: Optional[str] = None
        self.password: Optional[str] = None
        self._client: Optional[httpx.AsyncClient] = None

    def load_config(self, config_path: str = "config/cameras.yaml"):
        config_file = Path(__file__).parent.parent / config_path
        if config_file.exists():
            with open(config_file) as f:
                config = yaml.safe_load(f)
                self.cameras = config.get("cameras", [])
            logger.info(f"Loaded {len(self.cameras)} cameras from config")
        else:
            logger.warning(f"Camera config not found: {config_file}")
            self.cameras = []

    def set_credentials(self, user: str, password: str):
        self.user = user
        self.password = password

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            if not self.user or not self.password:
                raise ValueError("Camera credentials not configured")
            user: str = self.user
            password: str = self.password
            self._client = httpx.AsyncClient(
                auth=httpx.DigestAuth(user, password),
                timeout=httpx.Timeout(15.0, connect=5.0),
                headers={"Connection": "close"},
            )
        return self._client

    async def _reset_client(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None

    async def close(self):
        await self._reset_client()

    def get_cameras(self) -> list[dict]:
        return [{"name": c["name"], "id": c["id"]} for c in self.cameras]

    def get_camera_by_id(self, camera_id: str) -> Optional[dict]:
        for camera in self.cameras:
            if camera["id"] == camera_id:
                return camera
        return None

    async def get_snapshot(self, camera_id: str) -> tuple[Optional[bytes], Optional[str]]:
        camera = self.get_camera_by_id(camera_id)
        if not camera:
            return None, f"Camera not found: {camera_id}"

        ip = camera["ip"]
        url = f"http://{ip}/cgi-bin/snapshot.cgi"

        for attempt in range(len(SNAPSHOT_RETRY_DELAYS_SECONDS) + 1):
            try:
                client = await self._get_client()
                response = await client.get(url)
                if response.status_code == 200:
                    return response.content, None
                if attempt < len(SNAPSHOT_RETRY_DELAYS_SECONDS):
                    await self._reset_client()
                    await asyncio.sleep(SNAPSHOT_RETRY_DELAYS_SECONDS[attempt])
                    continue
                return None, f"Camera returned status {response.status_code}"
            except httpx.TimeoutException:
                if attempt < len(SNAPSHOT_RETRY_DELAYS_SECONDS):
                    await self._reset_client()
                    await asyncio.sleep(SNAPSHOT_RETRY_DELAYS_SECONDS[attempt])
                    continue
                return None, f"Timeout fetching snapshot from {camera['name']}"
            except Exception as e:
                if attempt < len(SNAPSHOT_RETRY_DELAYS_SECONDS):
                    await self._reset_client()
                    await asyncio.sleep(SNAPSHOT_RETRY_DELAYS_SECONDS[attempt])
                    continue
                return None, f"Error fetching snapshot: {str(e)}"
        return None, f"Error fetching snapshot: exhausted retries for {camera['name']}"


camera_service = CameraService()
