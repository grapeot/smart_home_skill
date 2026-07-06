import json
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional


class RingStatusService:
    def __init__(self, root: Optional[Path] = None):
        self.root = root or Path(__file__).resolve().parents[1]
        self.config_path = self.root / "config" / "ring_client_status.json"
        self.script_path = self.root / "scripts" / "ring_client_status.mjs"

    def get_status(self, timeout_seconds: int = 45) -> Dict[str, Any]:
        if not self.config_path.exists():
            return {
                "schema_version": "smart_home.ring_client_status.v0",
                "source": "ring-client-api",
                "configured": False,
                "locations": [],
                "error": "Ring private config not found",
            }

        try:
            completed = subprocess.run(
                ["node", str(self.script_path), "--config", str(self.config_path)],
                cwd=self.root,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {
                "schema_version": "smart_home.ring_client_status.v0",
                "source": "ring-client-api",
                "configured": True,
                "locations": [],
                "error": f"Ring status timed out after {timeout_seconds}s",
            }

        if completed.returncode != 0:
            return {
                "schema_version": "smart_home.ring_client_status.v0",
                "source": "ring-client-api",
                "configured": True,
                "locations": [],
                "error": _redact_error(completed.stderr or completed.stdout),
            }

        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            return {
                "schema_version": "smart_home.ring_client_status.v0",
                "source": "ring-client-api",
                "configured": True,
                "locations": [],
                "error": f"Invalid Ring status JSON: {exc}",
            }

        payload["configured"] = True
        return _public_status(payload)


def _redact_error(value: str) -> str:
    value = value.strip()
    if not value:
        return "Ring status command failed"
    # The Node script keeps tokens out of stdout/stderr by default. Keep backend
    # errors short anyway so vendor payloads do not leak through API responses.
    return value[-500:]


def _public_status(payload: Dict[str, Any]) -> Dict[str, Any]:
    sanitized = {
        "schema_version": payload.get("schema_version"),
        "source": payload.get("source"),
        "observed_at": payload.get("observed_at"),
        "updated_refresh_token_available": payload.get("updated_refresh_token_available"),
        "configured": payload.get("configured", True),
        "locations": [],
    }
    if payload.get("error"):
        sanitized["error"] = payload.get("error")

    for location in payload.get("locations", []):
        sanitized_location = {
            "name": location.get("name"),
            "has_hubs": location.get("has_hubs"),
            "has_alarm_base_station": location.get("has_alarm_base_station"),
            "devices": [],
        }
        for device in location.get("devices", []):
            sanitized_location["devices"].append(
                {
                    "name": device.get("name"),
                    "device_type": device.get("device_type"),
                    "category_id": device.get("category_id"),
                    "faulted": device.get("faulted"),
                    "derived_state": device.get("derived_state"),
                    "tamper_status": device.get("tamper_status"),
                    "comm_status": device.get("comm_status"),
                    "battery_level": device.get("battery_level"),
                    "battery_status": device.get("battery_status"),
                    "last_update": device.get("last_update"),
                    "last_comm_time": device.get("last_comm_time"),
                }
            )
        sanitized["locations"].append(sanitized_location)

    return sanitized


ring_service = RingStatusService()
