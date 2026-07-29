import logging
import os
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

ST_API_BASE = "https://api.smartthings.com/v1/devices"


class SamsungService:
    """Control Samsung TV via SmartThings API."""

    def __init__(self):
        self._token: Optional[str] = os.getenv("SAMSUNG_ST_TOKEN")
        self._device_id: Optional[str] = os.getenv("SAMSUNG_TV_DEVICE_ID")

    @property
    def configured(self) -> bool:
        return bool(self._token and self._device_id)

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    def _cmd_url(self) -> str:
        return f"{ST_API_BASE}/{self._device_id}/commands"

    def _status_url(self) -> str:
        return f"{ST_API_BASE}/{self._device_id}/components/main/status"

    def send_command(self, capability: str, command: str) -> Dict[str, Any]:
        if not self.configured:
            return {"status": "error", "message": "Samsung TV not configured"}

        body = {
            "commands": [
                {"component": "main", "capability": capability, "command": command}
            ]
        }

        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(self._cmd_url(), json=body, headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
                results = data.get("results", [])
                if results and results[0].get("status") in ("COMPLETED", "ACCEPTED"):
                    return {"status": "success"}
                return {"status": "error", "message": str(data)}
        except Exception as e:
            logger.warning(f"Samsung command failed: {e}")
            return {"status": "error", "message": str(e)}

    def get_status(self) -> Dict[str, Any]:
        if not self.configured:
            return {"configured": False}

        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(self._status_url(), headers=self._headers())
                resp.raise_for_status()
                data = resp.json()

                switch_val = (
                    data.get("switch", {}).get("switch", {}).get("value", "unknown")
                )
                vol_val = (
                    data.get("audioVolume", {}).get("volume", {}).get("value")
                )
                mute_val = (
                    data.get("audioMute", {}).get("mute", {}).get("value", "unknown")
                )

                return {
                    "configured": True,
                    "is_on": switch_val == "on",
                    "volume": int(vol_val) if vol_val is not None else None,
                    "muted": mute_val == "mute",
                }
        except Exception as e:
            logger.warning(f"Samsung status failed: {e}")
            return {"configured": True, "error": str(e)}

    def power_on(self) -> Dict[str, Any]:
        return self.send_command("switch", "on")

    def power_off(self) -> Dict[str, Any]:
        return self.send_command("switch", "off")

    def toggle_power(self) -> Dict[str, Any]:
        status = self.get_status()
        if status.get("error"):
            return {"status": "error", "message": status["error"]}
        if status.get("is_on"):
            return self.power_off()
        return self.power_on()

    def volume_up(self) -> Dict[str, Any]:
        return self.send_command("audioVolume", "volumeUp")

    def volume_down(self) -> Dict[str, Any]:
        return self.send_command("audioVolume", "volumeDown")

    def toggle_mute(self) -> Dict[str, Any]:
        status = self.get_status()
        if status.get("muted"):
            return self.send_command("audioMute", "unmute")
        return self.send_command("audioMute", "mute")


samsung_service = SamsungService()