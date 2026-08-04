import asyncio
import hashlib
import ipaddress
import json
import logging
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

from services.notification_service import notification_service

load_dotenv()

logger = logging.getLogger(__name__)
logging.getLogger("meross_iot").setLevel(logging.INFO)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CACHE_SCHEMA_VERSION = 1


class MerossService:
    def __init__(self):
        self.client = None
        self.manager = None
        self.device = None
        self._local_ip = None
        self._key = None
        self._device_uuid = None
        self._door_count = 0
        self._connected = False
        self._door_action_locks: dict[int, asyncio.Lock] = {}
        self._verify_timeout_seconds = float(os.getenv("MEROSS_GARAGE_VERIFY_TIMEOUT_SECONDS", "20"))
        self._verify_poll_interval_seconds = float(os.getenv("MEROSS_GARAGE_VERIFY_POLL_INTERVAL_SECONDS", "2"))
        self._cloud_timeout_seconds = float(os.getenv("MEROSS_GARAGE_CLOUD_TIMEOUT_SECONDS", "10"))
        cache_path = Path(os.getenv("MEROSS_GARAGE_LOCAL_CACHE_PATH", "data/meross_garage_local.json"))
        self._cache_path = cache_path if cache_path.is_absolute() else PROJECT_ROOT / cache_path

    def _reset_connection_state(self) -> None:
        self.device = None
        self._local_ip = None
        self._key = None
        self._device_uuid = None
        self._door_count = 0
        self._connected = False

    def _get_device_uuid(self):
        return self._device_uuid or getattr(self.device, "uuid", None)

    def _load_local_cache(self) -> bool:
        try:
            if self._cache_path.is_symlink():
                raise ValueError("cache path must not be a symlink")
            data = json.loads(self._cache_path.read_text(encoding="utf-8"))
            if data.get("schema_version") != CACHE_SCHEMA_VERSION:
                raise ValueError("unsupported cache schema")

            device_uuid = data.get("device_uuid")
            local_ip = data.get("local_ip")
            key = data.get("key")
            door_count = data.get("door_count")
            device_name = data.get("device_name")
            if not all(isinstance(value, str) and value for value in (device_uuid, local_ip, key)):
                raise ValueError("cache is missing local connection fields")
            ipaddress.IPv4Address(local_ip)
            if not isinstance(door_count, int) or isinstance(door_count, bool) or door_count < 1:
                raise ValueError("cache has an invalid door count")

            expected_uuid = os.getenv("MEROSS_GARAGE_UUID")
            expected_name = os.getenv("MEROSS_GARAGE_NAME")
            if expected_uuid and device_uuid != expected_uuid:
                raise ValueError("cached device does not match MEROSS_GARAGE_UUID")
            if not expected_uuid and expected_name and (
                not isinstance(device_name, str) or device_name.lower() != expected_name.lower()
            ):
                raise ValueError("cached device does not match MEROSS_GARAGE_NAME")

            os.chmod(self._cache_path, 0o600)
            self._device_uuid = device_uuid
            self._local_ip = local_ip
            self._key = key
            self._door_count = door_count
            self.device = None
            self._connected = True
            logger.info("Loaded cached Meross garage LAN configuration")
            return True
        except Exception as exc:
            logger.warning("Meross garage LAN cache unavailable: %s", type(exc).__name__)
            return False

    def _save_local_cache(self) -> None:
        device_uuid = self._get_device_uuid()
        door_count = self.get_door_count()
        if not all((device_uuid, self._local_ip, self._key)) or door_count < 1:
            raise ValueError("Meross local connection fields are incomplete")

        data = {
            "schema_version": CACHE_SCHEMA_VERSION,
            "device_uuid": device_uuid,
            "device_name": getattr(self.device, "name", None),
            "local_ip": self._local_ip,
            "key": self._key,
            "door_count": door_count,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._cache_path.with_name(f".{self._cache_path.name}.{secrets.token_hex(8)}.tmp")
        try:
            fd = os.open(temp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump(data, file, indent=2)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(temp_path, self._cache_path)
            os.chmod(self._cache_path, 0o600)
            directory_fd = os.open(self._cache_path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            temp_path.unlink(missing_ok=True)

    def _select_garage_device(self, devices: list):
        expected_uuid = os.getenv("MEROSS_GARAGE_UUID")
        expected_name = os.getenv("MEROSS_GARAGE_NAME")

        if expected_uuid:
            for device in devices:
                if getattr(device, "uuid", None) == expected_uuid:
                    return device
            return None

        if expected_name:
            expected_name_lower = expected_name.lower()
            for device in devices:
                if getattr(device, "name", "").lower() == expected_name_lower:
                    return device
            return None

        if len(devices) == 1:
            return devices[0]

        return None
    
    async def _connect_cloud(self, email: str, password: str) -> bool:
        from meross_iot.http_api import MerossHttpClient
        from meross_iot.manager import MerossManager

        self.client = await MerossHttpClient.async_from_user_password(
            api_base_url="https://iot.meross.com",
            email=email,
            password=password,
        )

        self.manager = MerossManager(http_client=self.client)
        await self.manager.async_init()
        await self.manager.async_device_discovery()
        await asyncio.sleep(2)

        selected_device = self._select_garage_device(self.manager.find_devices())
        if not selected_device:
            logger.error("No matching Meross garage found; set MEROSS_GARAGE_UUID or MEROSS_GARAGE_NAME")
            return False

        self.device = selected_device
        await self.device.async_update()
        self._local_ip = getattr(self.device, "_inner_ip", None)
        self._key = self.client.cloud_credentials.key
        self._device_uuid = self.device.uuid
        self._door_count = len(self.device.channels) - 1
        if not all((self._device_uuid, self._local_ip, self._key)) or self._door_count < 1:
            raise ValueError("Meross cloud discovery returned incomplete LAN configuration")

        self._connected = True
        try:
            self._save_local_cache()
            logger.info("Connected to Meross garage and refreshed local cache")
        except Exception as exc:
            logger.warning("Connected to Meross garage but could not refresh local cache: %s", type(exc).__name__)
        return True

    async def connect(self) -> bool:
        email = os.getenv("MEROSS_EMAIL")
        password = os.getenv("MEROSS_PASSWORD")
        self._reset_connection_state()

        if not email or not password:
            logger.warning("Meross cloud credentials not set; attempting local cache")
            return self._load_local_cache()

        try:
            timeout = max(0.1, self._cloud_timeout_seconds)
            return await asyncio.wait_for(self._connect_cloud(email, password), timeout=timeout)
        except Exception as exc:
            self._reset_connection_state()
            logger.warning("Meross cloud connection failed (%s); attempting local cache", type(exc).__name__)
            return self._load_local_cache()
    
    async def close(self):
        pass
    
    def get_door_count(self) -> int:
        if self.device:
            return len(self.device.channels) - 1
        return self._door_count

    def _build_local_message(self, namespace: str, method: str, payload: dict) -> dict:
        timestamp = int(time.time())
        message_id = secrets.token_hex(16)
        sign = hashlib.md5(
            f"{message_id}{self._key}{timestamp}".encode(),
            usedforsecurity=False,
        ).hexdigest()
        return {
            "header": {
                "messageId": message_id,
                "namespace": namespace,
                "method": method,
                "payloadVersion": 1,
                "from": f"http://{self._local_ip}/config",
                "triggerSrc": "AndroidLocal",
                "timestamp": timestamp,
                "timestampMs": 0,
                "sign": sign,
                "uuid": self._get_device_uuid(),
            },
            "payload": payload,
        }

    def _local_request(self, namespace: str, method: str, payload: dict) -> dict:
        if not self._local_ip or not self._key:
            raise RuntimeError("Meross local IP or key is not available")

        response = requests.post(
            f"http://{self._local_ip}/config",
            json=self._build_local_message(namespace, method, payload),
            timeout=8,
        )
        response.raise_for_status()
        return response.json().get("payload", {})

    def _get_current_open_state(self, door_index: int, current_state: dict) -> bool:
        if "open" in current_state:
            return bool(current_state["open"])
        if not self.device:
            raise RuntimeError("Meross local response did not include door state")
        return bool(self.device.get_is_open(door_index))

    def _read_door_state(self, door_index: int) -> tuple[dict, bool]:
        payload = self._local_request(
            "Appliance.GarageDoor.State",
            "GET",
            {"state": {"channel": door_index}},
        )
        state = payload.get("state", {}) if isinstance(payload, dict) else {}
        return state, self._get_current_open_state(door_index, state)

    async def _wait_for_target_state(self, door_index: int, target_open: bool) -> tuple[bool, dict]:
        timeout = max(0.0, self._verify_timeout_seconds)
        interval = max(0.1, self._verify_poll_interval_seconds)
        deadline = time.monotonic() + timeout
        last_state = {}

        while True:
            last_state, is_open = await asyncio.to_thread(self._read_door_state, door_index)
            if is_open == target_open:
                return True, last_state

            if time.monotonic() >= deadline:
                return False, last_state

            await asyncio.sleep(min(interval, max(0.0, deadline - time.monotonic())))
    
    async def toggle_door(
        self,
        door_index: int,
        *,
        bridge_principal_id: str | None = None,
        bridge_command_id: str | None = None,
    ) -> dict:
        lock = self._door_action_locks.setdefault(door_index, asyncio.Lock())
        async with lock:
            return await self._toggle_door_locked(
                door_index,
                bridge_principal_id=bridge_principal_id,
                bridge_command_id=bridge_command_id,
            )

    async def _toggle_door_locked(
        self,
        door_index: int,
        *,
        bridge_principal_id: str | None,
        bridge_command_id: str | None,
    ) -> dict:
        from models.database import get_garage_bridge_target_blocker

        blocker = get_garage_bridge_target_blocker(
            door_index,
            exclude_principal_id=bridge_principal_id,
            exclude_command_id=bridge_command_id,
        )
        if blocker is not None:
            return {
                "status": "error",
                "error_code": "garage_bridge_target_blocked",
                "message": "Garage action blocked by an unresolved bridge command",
            }
        device_uuid = self._get_device_uuid()
        if not self._connected:
            return {"status": "error", "message": "Not connected"}

        if not device_uuid or door_index < 1 or door_index > self.get_door_count():
            return {"status": "error", "message": f"Invalid door index: {door_index}"}
        
        try:
            if self.device and not hasattr(self.device, "get_is_open"):
                return {"status": "error", "message": "Connected Meross device is not a garage opener"}

            current_state, current_is_open = await asyncio.to_thread(self._read_door_state, door_index)
            target_open = not current_is_open
            response_payload = await asyncio.to_thread(
                self._local_request,
                "Appliance.GarageDoor.State",
                "SET",
                {
                    "state": {
                        "channel": door_index,
                        "open": int(target_open),
                        "uuid": device_uuid,
                    }
                },
            )
            state = response_payload.get("state") if isinstance(response_payload, dict) else None
            if isinstance(state, list):
                state = state[0] if state else None
            verified, final_state = await self._wait_for_target_state(door_index, target_open)
            status = "success" if verified else "triggered_unverified"
            result = {
                "status": status,
                "door": door_index,
                "action": "toggle",
                "backend": "meross_local_http",
                "previous_state": current_state,
                "target_open": target_open,
                "reported_state": state,
                "final_state": final_state,
                "verified": verified,
                "executed": state.get("execute") if isinstance(state, dict) else None,
                "timestamp": datetime.now().isoformat()
            }
            if not verified:
                result["message"] = "Garage command was sent, but final door state was not verified"
            try:
                result["notification"] = await asyncio.to_thread(
                    notification_service.send_garage_toggle,
                    result,
                )
            except Exception as e:
                logger.error(f"Error sending garage notification: {e}")
                result["notification"] = {"enabled": True, "sent": False, "error": str(e)}
            return result
        except Exception as e:
            logger.error(f"Error toggling door {door_index}: {e}")
            return {"status": "error", "message": str(e)}

meross_service = MerossService()
