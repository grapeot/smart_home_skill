import asyncio
import base64
import json
import logging
import os
import ssl
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

import websockets

logger = logging.getLogger(__name__)

DEFAULT_APP_NAME = "SmartHome"
REST_DEVICE_INFO = "/api/v2/"
WS_CHANNEL = "/api/v2/channels/samsung.remote.control"
DEFAULT_PORT = 8002
POWER_SETTLE_SECONDS = 3


class SamsungService:
    """Control Samsung TV via local Tizen WebSocket API.

    Replaces the previous SmartThings cloud PAT implementation. The local WS
    protocol talks directly to the TV on the LAN; the token is a one-time
    device-local credential that does not expire like a SmartThings PAT.
    """

    def __init__(self):
        self._host: Optional[str] = os.getenv("SAMSUNG_TV_HOST")
        try:
            self._port: int = int(os.getenv("SAMSUNG_TV_PORT", str(DEFAULT_PORT)))
        except (ValueError, TypeError):
            self._port = DEFAULT_PORT
        self._app_name: str = os.getenv("SAMSUNG_TV_APP_NAME", DEFAULT_APP_NAME)
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        self._token_file: str = os.getenv(
            "SAMSUNG_TV_TOKEN_FILE", os.path.join(data_dir, "samsung_tv_ws_token.txt")
        )
        # Serialize power operations to prevent concurrent toggle races.
        self._power_lock: asyncio.Lock = asyncio.Lock()

    @property
    def configured(self) -> bool:
        return bool(self._host and self._token_file and os.path.exists(self._token_file))

    def _read_token(self) -> Optional[str]:
        try:
            with open(self._token_file) as f:
                tok = f.read().strip()
                return tok or None
        except OSError:
            return None

    def _ws_url(self, token: str) -> str:
        name_b64 = base64.b64encode(self._app_name.encode()).decode()
        params = urllib.parse.urlencode({"name": name_b64, "token": token})
        return f"wss://{self._host}:{self._port}{WS_CHANNEL}?{params}"

    def _ssl_context(self) -> ssl.SSLContext:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    async def _send_key(self, key: str) -> Dict[str, Any]:
        """Open a fresh WS connection, send one key event, then close.

        Tizen WS resets connections that send multiple keys in quick succession,
        so each command gets its own short-lived connection.
        """
        token = self._read_token()
        if not token:
            return {"status": "error", "message": "Samsung TV not paired (no local token)"}
        if not self._host:
            return {"status": "error", "message": "Samsung TV host not configured"}

        url = self._ws_url(token)
        ctx = self._ssl_context()
        try:
            async with websockets.connect(url, ssl=ctx, open_timeout=10) as ws:
                # Validate the handshake frame; reject unauthorized/timeout.
                raw = await asyncio.wait_for(ws.recv(), timeout=5)
                frame = json.loads(raw)
                event = frame.get("event", "")
                if event != "ms.channel.connect":
                    if "unauthorized" in event or "timeOut" in event:
                        return {"status": "error", "message": f"TV rejected connection: {event}"}
                    return {"status": "error", "message": f"Unexpected handshake: {event}"}
                payload = json.dumps(
                    {
                        "method": "ms.remote.control",
                        "params": {
                            "Cmd": "Click",
                            "DataOfCmd": key,
                            "Option": "false",
                            "TypeOfRemote": "SendRemoteKey",
                        },
                    }
                )
                await ws.send(payload)
            return {"status": "success"}
        except Exception as e:
            logger.warning(f"Samsung key '{key}' failed: {e}")
            return {"status": "error", "message": str(e)}

    def _rest_power_state(self) -> Optional[str]:
        """Query PowerState via the TV's REST device-info endpoint.

        Returns 'on', 'standby', '' (transient), or None (unreachable).
        """
        if not self._host:
            return None
        ctx = self._ssl_context()
        try:
            req = urllib.request.Request(
                f"https://{self._host}:{self._port}{REST_DEVICE_INFO}"
            )
            with urllib.request.urlopen(req, context=ctx, timeout=6) as resp:
                data = json.load(resp)
                return data.get("device", {}).get("PowerState", "")
        except Exception:
            return None

    async def _power_state_async(self) -> Optional[str]:
        """Non-blocking wrapper around _rest_power_state for use in async contexts."""
        return await asyncio.to_thread(self._rest_power_state)

    def get_status(self) -> Dict[str, Any]:
        if not self._host:
            return {"configured": False}
        if not self._read_token():
            return {"configured": False}

        power = self._rest_power_state()
        if power is None:
            return {"configured": True, "error": "TV unreachable"}
        is_on = power == "on" if power else None
        return {
            "configured": True,
            "is_on": is_on,
            "volume": None,
            "muted": None,
        }

    async def power_on(self) -> Dict[str, Any]:
        async with self._power_lock:
            power = await self._power_state_async()
            if power == "on":
                return {"status": "success", "message": "already on"}
            if power is None:
                return {"status": "error", "message": "TV unreachable"}
            # power == "standby" or transient "" — safe to send toggle.
            result = await self._send_key("KEY_POWER")
            if result.get("status") == "success":
                await asyncio.sleep(POWER_SETTLE_SECONDS)
            return result

    async def power_off(self) -> Dict[str, Any]:
        async with self._power_lock:
            power = await self._power_state_async()
            if power == "standby":
                return {"status": "success", "message": "already off"}
            if power is None:
                return {"status": "error", "message": "TV unreachable"}
            if not power:
                # Transient empty string — cannot determine state safely.
                return {"status": "error", "message": "TV state unknown (transient)"}
            # power == "on" — safe to send toggle.
            result = await self._send_key("KEY_POWER")
            if result.get("status") == "success":
                await asyncio.sleep(POWER_SETTLE_SECONDS)
            return result

    async def toggle_power(self) -> Dict[str, Any]:
        return await self._send_key("KEY_POWER")

    async def volume_up(self) -> Dict[str, Any]:
        return await self._send_key("KEY_VOLUP")

    async def volume_down(self) -> Dict[str, Any]:
        return await self._send_key("KEY_VOLDOWN")

    async def toggle_mute(self) -> Dict[str, Any]:
        return await self._send_key("KEY_MUTE")


samsung_service = SamsungService()