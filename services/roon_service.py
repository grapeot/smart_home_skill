import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = ROOT / "config" / "roon_config.yaml"
EXAMPLE_CONFIG_PATH = ROOT / "config" / "roon_config.example.yaml"
AUTH_PATH = ROOT / "data" / "roon_auth.json"


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open() as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Invalid YAML object in {path}")
    return data


class RoonService:
    """Long-lived Roon Extension adapter backed by roonapi."""

    def __init__(
        self,
        config_path: Optional[Path] = None,
        auth_path: Optional[Path] = None,
    ):
        self.config_path = Path(config_path or os.getenv("ROON_CONFIG_PATH", DEFAULT_CONFIG_PATH))
        self.auth_path = Path(auth_path or os.getenv("ROON_AUTH_PATH", AUTH_PATH))
        self._lock = threading.RLock()
        self._api = None
        self._pair_thread: Optional[threading.Thread] = None
        self._pair_status: Dict[str, Any] = {
            "status": "idle",
            "message": "Not pairing",
            "authorized": False,
        }
        self._sleep_timers: Dict[str, threading.Timer] = {}
        self._config = self._read_config()

    def _read_config(self) -> Dict[str, Any]:
        cfg = _load_yaml(EXAMPLE_CONFIG_PATH)
        cfg.update(_load_yaml(self.config_path))
        return cfg

    def reload_config(self) -> None:
        with self._lock:
            self._config = self._read_config()


    def _load_auth(self) -> Dict[str, Any]:
        if not self.auth_path.exists():
            return {}
        try:
            return json.loads(self.auth_path.read_text())
        except Exception as exc:  # pragma: no cover - corrupt local file
            logger.warning("Failed to read Roon auth file: %s", exc)
            return {}

    def _save_auth(self, payload: Dict[str, Any]) -> None:
        self.auth_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.auth_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2) + "\n")
        os.chmod(tmp, 0o600)
        tmp.replace(self.auth_path)

    def _appinfo(self) -> Dict[str, str]:
        return {
            "extension_id": self._config.get("extension_id", "com.grapeot.smart-home-roon"),
            "display_name": self._config.get("display_name", "Smart Home Roon"),
            "display_version": str(self._config.get("display_version", "1.0.0")),
            "publisher": self._config.get("publisher", "grapeot"),
            "email": self._config.get("email", "local@invalid"),
        }

    def _discover_core(self) -> Optional[Tuple[str, int]]:
        from roonapi import RoonDiscovery

        preferred_host = self._config.get("core_host")
        preferred_port = int(self._config.get("core_port") or 9330)
        preferred_id = self._config.get("core_id")
        auth = self._load_auth()
        preferred_host = preferred_host or auth.get("host")
        preferred_id = preferred_id or auth.get("core_id")
        preferred_port = int(auth.get("port") or preferred_port)

        if preferred_host:
            return preferred_host, preferred_port

        discovery = RoonDiscovery(preferred_id)
        try:
            cores = discovery.all() or []
        finally:
            discovery.stop()
        if not cores:
            return None
        host, port = cores[0]
        return host, int(port)

    def connect(self) -> Dict[str, Any]:
        """Connect using a saved token when available. Non-blocking if unauthorized."""
        with self._lock:
            auth = self._load_auth()
            token = auth.get("token")
            if not token:
                return {
                    "status": "error",
                    "message": "Roon not paired. Call POST /api/roon/pair/start",
                    "authorized": False,
                }
            core = self._discover_core()
            if not core:
                return {"status": "error", "message": "No Roon Core discovered", "authorized": False}
            host, port = core
            return self._connect_locked(host, port, token, wait_seconds=20)

    def _connect_locked(
        self,
        host: str,
        port: int,
        token: Optional[str],
        wait_seconds: float = 20,
        keep_pending: bool = False,
    ) -> Dict[str, Any]:
        from roonapi import RoonApi

        if self._api is not None:
            try:
                self._api.stop()
            except Exception:
                pass
            self._api = None

        api = RoonApi(self._appinfo(), token, host, port, blocking_init=False)
        self._api = api
        deadline = time.monotonic() + wait_seconds
        while time.monotonic() < deadline:
            if api.token and api.ready:
                break
            time.sleep(0.1)

        if not api.token:
            if not keep_pending:
                try:
                    api.stop()
                except Exception:
                    pass
                self._api = None
            return {
                "status": "pending",
                "message": "Waiting for Enable in Roon Settings → Extensions",
                "authorized": False,
                "host": host,
                "port": port,
                "display_name": self._appinfo()["display_name"],
            }

        # Wait briefly for zone subscription fill.
        wait_zones = time.monotonic() + 3
        while time.monotonic() < wait_zones and not api.zones:
            time.sleep(0.1)

        self._save_auth(
            {
                "token": api.token,
                "core_id": api.core_id,
                "core_name": api.core_name,
                "host": host,
                "port": port,
            }
        )
        self._pair_status = {
            "status": "authorized",
            "message": f"Paired with {api.core_name}",
            "authorized": True,
            "core_id": api.core_id,
            "core_name": api.core_name,
            "host": host,
            "port": port,
        }
        return {
            "status": "success",
            "message": f"Connected to {api.core_name}",
            "authorized": True,
            "core_id": api.core_id,
            "core_name": api.core_name,
            "host": host,
            "port": port,
        }

    def start_pairing(self, timeout_seconds: int = 600) -> Dict[str, Any]:
        with self._lock:
            if self._api is not None and getattr(self._api, "token", None):
                auth = {
                    "token": self._api.token,
                    "core_id": self._api.core_id,
                    "core_name": self._api.core_name,
                    "host": getattr(self._api, "host", None),
                    "port": getattr(self._api, "port", None) or 9330,
                }
                self._save_auth(auth)
                self._pair_status = {
                    "status": "authorized",
                    "message": f"Already paired with {self._api.core_name}",
                    "authorized": True,
                    "core_id": self._api.core_id,
                    "core_name": self._api.core_name,
                    "host": auth.get("host"),
                    "port": auth.get("port"),
                    "display_name": self._appinfo()["display_name"],
                }
                return dict(self._pair_status)
            if self._pair_thread and self._pair_thread.is_alive():
                return dict(self._pair_status)
            # Prefer reconnect with saved token before a fresh Enable flow.
            auth = self._load_auth()
            if auth.get("token"):
                connected = self.connect()
                if connected.get("authorized"):
                    self._pair_status = {
                        "status": "authorized",
                        "message": connected.get("message"),
                        "authorized": True,
                        "core_id": connected.get("core_id"),
                        "core_name": connected.get("core_name"),
                        "host": connected.get("host"),
                        "port": connected.get("port"),
                        "display_name": self._appinfo()["display_name"],
                    }
                    return dict(self._pair_status)
            self._pair_status = {
                "status": "waiting",
                "message": (
                    f"Enable '{self._appinfo()['display_name']}' in "
                    "Roon Settings → Extensions"
                ),
                "authorized": False,
                "display_name": self._appinfo()["display_name"],
            }
            self._pair_thread = threading.Thread(
                target=self._pair_worker,
                args=(timeout_seconds,),
                daemon=True,
                name="roon-pair",
            )
            self._pair_thread.start()
            return dict(self._pair_status)

    def _pair_worker(self, timeout_seconds: int) -> None:
        try:
            core = self._discover_core()
            if not core:
                with self._lock:
                    self._pair_status = {
                        "status": "error",
                        "message": "No Roon Core discovered on the LAN",
                        "authorized": False,
                    }
                return
            host, port = core
            with self._lock:
                self._pair_status.update({"host": host, "port": port, "status": "waiting"})
                # Keep the websocket open while Roon shows the pending extension.
                result = self._connect_locked(
                    host, port, None, wait_seconds=2, keep_pending=True
                )
            if result.get("authorized"):
                return
            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline:
                with self._lock:
                    api = self._api
                    if api and api.token:
                        # Wait until ready/zones if needed.
                        ready_deadline = time.monotonic() + 5
                        while time.monotonic() < ready_deadline and not api.ready:
                            time.sleep(0.05)
                        self._save_auth(
                            {
                                "token": api.token,
                                "core_id": api.core_id,
                                "core_name": api.core_name,
                                "host": host,
                                "port": port,
                            }
                        )
                        self._pair_status = {
                            "status": "authorized",
                            "message": f"Paired with {api.core_name}",
                            "authorized": True,
                            "core_id": api.core_id,
                            "core_name": api.core_name,
                            "host": host,
                            "port": port,
                        }
                        return
                    if api is None:
                        reconnect = self._connect_locked(
                            host, port, None, wait_seconds=2, keep_pending=True
                        )
                        if reconnect.get("authorized"):
                            return
                time.sleep(0.5)
            with self._lock:
                api = self._api
                if api is not None and getattr(api, "token", None):
                    self._save_auth(
                        {
                            "token": api.token,
                            "core_id": api.core_id,
                            "core_name": api.core_name,
                            "host": host,
                            "port": port,
                        }
                    )
                    self._pair_status = {
                        "status": "authorized",
                        "message": f"Paired with {api.core_name}",
                        "authorized": True,
                        "core_id": api.core_id,
                        "core_name": api.core_name,
                        "host": host,
                        "port": port,
                    }
                    return
                # Keep pending socket if still open so a late Enable can finish.
                self._pair_status = {
                    "status": "timeout",
                    "message": "Pairing timed out before Enable",
                    "authorized": False,
                    "host": host,
                    "port": port,
                }
        except Exception as exc:
            logger.exception("Roon pairing failed")
            with self._lock:
                self._pair_status = {
                    "status": "error",
                    "message": str(exc),
                    "authorized": False,
                }

    def pair_status(self) -> Dict[str, Any]:
        with self._lock:
            status = dict(self._pair_status)
            if self._api and self._api.token:
                self._save_auth(
                    {
                        "token": self._api.token,
                        "core_id": self._api.core_id,
                        "core_name": self._api.core_name,
                        "host": getattr(self._api, "host", status.get("host")),
                        "port": getattr(self._api, "port", status.get("port")) or 9330,
                    }
                )
                status.update(
                    {
                        "authorized": True,
                        "core_name": self._api.core_name,
                        "core_id": self._api.core_id,
                        "status": "authorized",
                        "message": f"Paired with {self._api.core_name}",
                        "host": getattr(self._api, "host", status.get("host")),
                        "port": getattr(self._api, "port", status.get("port")) or 9330,
                    }
                )
            return status

    def _require_api(self):
        if self._api is None or not self._api.token:
            connected = self.connect()
            if connected.get("status") != "success":
                raise RuntimeError(connected.get("message") or "Roon not connected")
        return self._api

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            auth = self._load_auth()
            if self._api is None and auth.get("token"):
                try:
                    self.connect()
                except Exception as exc:
                    return {
                        "configured": bool(auth.get("token")),
                        "authorized": False,
                        "connected": False,
                        "error": str(exc),
                    }
            api = self._api
            if api is None or not api.token:
                return {
                    "configured": bool(auth.get("token")),
                    "authorized": False,
                    "connected": False,
                    "pair": dict(self._pair_status),
                }
            zones = self._serialize_zones(api)
            return {
                "configured": True,
                "authorized": True,
                "connected": bool(api.ready),
                "core_name": api.core_name,
                "core_id": api.core_id,
                "host": getattr(api, "host", auth.get("host")),
                "zone_count": len(zones),
                "zones": zones,
            }

    def _serialize_zones(self, api) -> List[Dict[str, Any]]:
        zones = []
        for zone_id, zone in (api.zones or {}).items():
            now_playing = zone.get("now_playing") or {}
            three = now_playing.get("three_line") or {}
            zones.append(
                {
                    "zone_id": zone_id,
                    "display_name": zone.get("display_name"),
                    "state": zone.get("state"),
                    "now_playing": {
                        "title": three.get("line1"),
                        "artist": three.get("line2"),
                        "album": three.get("line3"),
                    }
                    if three
                    else None,
                    "outputs": [
                        {
                            "output_id": output.get("output_id"),
                            "display_name": output.get("display_name"),
                        }
                        for output in zone.get("outputs", [])
                    ],
                }
            )
        zones.sort(key=lambda item: (item.get("display_name") or "").lower())
        return zones

    def list_zones(self) -> Dict[str, Any]:
        with self._lock:
            api = self._require_api()
            return {"status": "success", "zones": self._serialize_zones(api)}

    def _resolve_zone(self, api, zone_name: str) -> Dict[str, Any]:
        zone = api.zone_by_name(zone_name)
        if zone:
            return zone
        # Case-insensitive fallback.
        target = zone_name.strip().lower()
        for candidate in (api.zones or {}).values():
            if (candidate.get("display_name") or "").strip().lower() == target:
                return candidate
            for output in candidate.get("outputs") or []:
                if (output.get("display_name") or "").strip().lower() == target:
                    return candidate
        raise KeyError(f"Zone not found: {zone_name}")

    def play_queue(self, zone_name: str) -> Dict[str, Any]:
        with self._lock:
            api = self._require_api()
            zone = self._resolve_zone(api, zone_name)
            api.playback_control(zone["zone_id"], "play")
            return {
                "status": "success",
                "message": f"Play queue on {zone.get('display_name')}",
                "zone": zone.get("display_name"),
                "state": "playing",
            }

    def list_playlists(self) -> Dict[str, Any]:
        with self._lock:
            api = self._require_api()
            zones = self._serialize_zones(api)
            if not zones:
                return {"status": "error", "message": "No zones available", "playlists": []}
            zone_id = zones[0]["zone_id"]
            names = self._list_playlist_titles(api, zone_id)
            return {"status": "success", "playlists": names}

    def play_playlist(self, zone_name: str, playlist_name: str) -> Dict[str, Any]:
        with self._lock:
            api = self._require_api()
            zone = self._resolve_zone(api, zone_name)
            zone_id = zone["zone_id"]
            matched = self._play_playlist_hierarchy(api, zone_id, playlist_name)
            if not matched:
                # Fallback through generic browse path used by Home Assistant.
                for path in (
                    ["Playlists", playlist_name],
                    ["Playlists", playlist_name.strip()],
                ):
                    if api.play_media(zone_id, path, action="Play Now", report_error=False):
                        matched = playlist_name
                        break
            if not matched:
                available = self._list_playlist_titles(api, zone_id)[:12]
                return {
                    "status": "error",
                    "message": f"Playlist not found or not playable: {playlist_name}",
                    "zone": zone.get("display_name"),
                    "available_playlists": available,
                }
            api.repeat(zone_id, "loop")
            api.shuffle(zone_id, False)
            return {
                "status": "success",
                "message": f"Playing playlist '{matched}' on {zone.get('display_name')}",
                "zone": zone.get("display_name"),
                "playlist": matched,
                "state": "playing",
            }

    def _list_playlist_titles(self, api, zone_id: str) -> List[str]:
        opts = {
            "zone_or_output_id": zone_id,
            "hierarchy": "playlists",
            "pop_all": True,
            "count": 100,
        }
        header = api.browse_browse(opts)
        if not header or "list" not in header:
            return []
        total = int(header["list"].get("count") or 0)
        offset = 0
        names: List[str] = []
        while offset < max(total, 1):
            loaded = api.browse_load(
                {
                    "zone_or_output_id": zone_id,
                    "hierarchy": "playlists",
                    "count": 100,
                    "offset": offset,
                }
            )
            items = (loaded or {}).get("items") or []
            if not items:
                break
            for item in items:
                title = (item.get("title") or "").strip()
                if title:
                    names.append(title)
            offset += len(items)
            if len(items) < 100:
                break
        return names

    def _play_playlist_hierarchy(self, api, zone_id: str, playlist_name: str) -> Optional[str]:
        target = playlist_name.strip().lower()
        opts = {
            "zone_or_output_id": zone_id,
            "hierarchy": "playlists",
            "pop_all": True,
            "count": 100,
        }
        header = api.browse_browse(opts)
        if not header or "list" not in header:
            return None
        total = int(header["list"].get("count") or 0)
        offset = 0
        item_key = None
        matched_title = None
        fuzzy_key = None
        fuzzy_title = None
        while offset < max(total, 1):
            loaded = api.browse_load(
                {
                    "zone_or_output_id": zone_id,
                    "hierarchy": "playlists",
                    "count": 100,
                    "offset": offset,
                }
            )
            items = (loaded or {}).get("items") or []
            if not items:
                break
            for item in items:
                title = (item.get("title") or "").strip()
                low = title.lower()
                if low == target:
                    item_key = item.get("item_key")
                    matched_title = title
                    break
                if fuzzy_key is None and (target in low or low in target):
                    fuzzy_key = item.get("item_key")
                    fuzzy_title = title
            if item_key:
                break
            offset += len(items)
        if not item_key and fuzzy_key:
            item_key = fuzzy_key
            matched_title = fuzzy_title
        if not item_key:
            return None

        browse = api.browse_browse(
            {
                "zone_or_output_id": zone_id,
                "hierarchy": "playlists",
                "item_key": item_key,
                "count": 100,
            }
        )
        if not browse:
            return None
        loaded = api.browse_load(
            {
                "zone_or_output_id": zone_id,
                "hierarchy": "playlists",
                "count": 100,
                "offset": 0,
            }
        )
        actions = (loaded or {}).get("items") or []
        play_key = None
        for action in actions:
            title = (action.get("title") or "").lower()
            hint = action.get("hint")
            if hint in ("action", "action_list") and (
                "play now" in title or title == "play" or "play" in title
            ):
                play_key = action.get("item_key")
                if "play now" in title:
                    break
        if not play_key and actions:
            # Default first action list/action.
            first = actions[0]
            if first.get("hint") in ("action", "action_list"):
                play_key = first.get("item_key")
        if not play_key:
            return None
        api.browse_browse(
            {
                "zone_or_output_id": zone_id,
                "hierarchy": "playlists",
                "item_key": play_key,
            }
        )
        return matched_title or playlist_name

    def pause(self, zone_name: str) -> Dict[str, Any]:
        with self._lock:
            api = self._require_api()
            zone = self._resolve_zone(api, zone_name)
            api.playback_control(zone["zone_id"], "pause")
            return {
                "status": "success",
                "message": f"Paused {zone.get('display_name')}",
                "zone": zone.get("display_name"),
                "state": "paused",
            }

    def stop(self, zone_name: str) -> Dict[str, Any]:
        with self._lock:
            api = self._require_api()
            zone = self._resolve_zone(api, zone_name)
            api.playback_control(zone["zone_id"], "stop")
            self._cancel_sleep_timer_locked(zone.get("display_name") or zone_name)
            return {
                "status": "success",
                "message": f"Stopped {zone.get('display_name')}",
                "zone": zone.get("display_name"),
                "state": "stopped",
            }

    def playpause(self, zone_name: str) -> Dict[str, Any]:
        with self._lock:
            api = self._require_api()
            zone = self._resolve_zone(api, zone_name)
            state = (zone.get("state") or "").lower()
            if state == "playing":
                api.playback_control(zone["zone_id"], "pause")
                new_state = "paused"
            else:
                api.playback_control(zone["zone_id"], "play")
                new_state = "playing"
            return {
                "status": "success",
                "message": f"{new_state.title()} {zone.get('display_name')}",
                "zone": zone.get("display_name"),
                "state": new_state,
            }

    def zone_state(self, zone_name: str) -> Dict[str, Any]:
        with self._lock:
            api = self._require_api()
            zone = self._resolve_zone(api, zone_name)
            return {
                "status": "success",
                "zone": zone.get("display_name"),
                "state": zone.get("state"),
                "zone_id": zone.get("zone_id"),
            }

    def set_sleep_timer(self, zone_name: str, minutes: float) -> Dict[str, Any]:
        """Stop zone after N minutes. Roon has no native sleep-timer API."""
        if minutes <= 0 or minutes > 24 * 60:
            return {"status": "error", "message": "minutes must be in (0, 1440]"}
        with self._lock:
            api = self._require_api()
            zone = self._resolve_zone(api, zone_name)
            name = zone.get("display_name") or zone_name
            self._cancel_sleep_timer_locked(name)

            def _fire(target=name):
                try:
                    self.stop(target)
                except Exception:
                    logger.exception("Roon sleep timer stop failed for %s", target)

            timer = threading.Timer(minutes * 60.0, _fire)
            timer.daemon = True
            self._sleep_timers[name.lower()] = timer
            timer.start()
            return {
                "status": "success",
                "message": f"Sleep timer set for {minutes} minutes on {name}",
                "zone": name,
                "minutes": minutes,
            }

    def cancel_sleep_timer(self, zone_name: str) -> Dict[str, Any]:
        with self._lock:
            cancelled = self._cancel_sleep_timer_locked(zone_name)
            if not cancelled:
                return {"status": "error", "message": f"No sleep timer for {zone_name}"}
            return {
                "status": "success",
                "message": f"Cancelled sleep timer for {zone_name}",
                "zone": zone_name,
            }

    def _cancel_sleep_timer_locked(self, zone_name: str) -> bool:
        key = zone_name.strip().lower()
        timer = self._sleep_timers.pop(key, None)
        if timer is None:
            return False
        timer.cancel()
        return True

    def close(self) -> None:
        with self._lock:
            for timer in list(self._sleep_timers.values()):
                timer.cancel()
            self._sleep_timers.clear()
            if self._api is not None:
                try:
                    self._api.stop()
                except Exception:
                    pass
                self._api = None


roon_service = RoonService()
