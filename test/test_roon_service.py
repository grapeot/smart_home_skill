import json
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from services.kids_music_service import KidsMusicService
from services.roon_service import RoonService


class FakeZone(dict):
    pass


class FakeRoonApi:
    def __init__(self, appinfo, token, host, port, blocking_init=True):
        self.appinfo = appinfo
        self.token = token or None
        self.host = host
        self.port = port
        self.ready = bool(token)
        self.core_id = "core-1"
        self.core_name = "Quantum"
        self.zones = {
            "z1": {
                "zone_id": "z1",
                "display_name": "bedroom",
                "state": "stopped",
                "outputs": [{"output_id": "o1", "display_name": "bedroom"}],
                "now_playing": {},
            }
        }
        self.calls = []
        if token is None:
            # Simulate user enabling shortly after connect.
            threading.Thread(target=self._auto_auth, daemon=True).start()

    def _auto_auth(self):
        time.sleep(0.05)
        self.token = "token-abc"
        self.ready = True

    def stop(self):
        self.calls.append(("stop",))

    def zone_by_name(self, name):
        for zone in self.zones.values():
            if zone["display_name"] == name:
                return zone
        return None

    def playback_control(self, zone_id, control="play"):
        self.calls.append(("playback_control", zone_id, control))
        zone = self.zones[zone_id]
        if control == "play":
            zone["state"] = "playing"
        elif control == "pause":
            zone["state"] = "paused"
        elif control == "stop":
            zone["state"] = "stopped"

    def repeat(self, zone_id, repeat="loop"):
        self.calls.append(("repeat", zone_id, repeat))

    def shuffle(self, zone_id, shuffle=True):
        self.calls.append(("shuffle", zone_id, shuffle))

    def play_media(self, zone_id, path, action=None, report_error=True):
        self.calls.append(("play_media", zone_id, path, action))
        self.zones[zone_id]["state"] = "playing"
        return True

    def browse_browse(self, opts):
        self.calls.append(("browse_browse", opts))
        if opts.get("item_key") == "act-play":
            zone_id = opts.get("zone_or_output_id")
            if zone_id in self.zones:
                self.zones[zone_id]["state"] = "playing"
            return {"list": {"count": 0}}
        if opts.get("pop_all"):
            return {"list": {"count": 1}}
        if opts.get("item_key") == "pl1":
            return {"list": {"count": 1}}
        return {"list": {"count": 1}}

    def browse_load(self, opts):
        self.calls.append(("browse_load", opts))
        # After selecting playlist item.
        if any(c[0] == "browse_browse" and c[1].get("item_key") == "pl1" for c in self.calls):
            return {"items": [{"title": "Play Now", "hint": "action", "item_key": "act-play"}]}
        return {"items": [{"title": "k-pop", "item_key": "pl1", "hint": "list"}]}


@pytest.fixture
def roon_env(tmp_path, monkeypatch):
    config_path = tmp_path / "roon_config.yaml"
    auth_path = tmp_path / "roon_auth.json"
    config_path.write_text(
        """
core_host: 127.0.0.1
core_port: 9330
kids:
  zone_name: bedroom
  playlist_name: k-pop
  daily_plays: 2
  unit_minutes: 15
  timezone: America/Los_Angeles
  day_boundary_hour: 4
"""
    )
    service = RoonService(config_path=config_path, auth_path=auth_path)

    monkeypatch.setattr("roonapi.RoonApi", FakeRoonApi)
    monkeypatch.setattr(
        service,
        "_discover_core",
        lambda: ("127.0.0.1", 9330),
    )
    return service, auth_path


def test_pair_and_connect_saves_token(roon_env):
    service, auth_path = roon_env
    status = service.start_pairing(timeout_seconds=2)
    assert status["status"] == "waiting"
    deadline = time.time() + 2
    while time.time() < deadline and not service.pair_status().get("authorized"):
        time.sleep(0.05)
    pair = service.pair_status()
    assert pair["authorized"] is True
    assert auth_path.exists()
    auth = json.loads(auth_path.read_text())
    assert auth["token"] == "token-abc"
    zones = service.list_zones()
    assert zones["zones"][0]["display_name"] == "bedroom"


def test_play_playlist_pause_stop_and_sleep_timer(roon_env):
    service, auth_path = roon_env
    auth_path.write_text(
        json.dumps(
            {
                "token": "token-abc",
                "core_id": "core-1",
                "core_name": "Quantum",
                "host": "127.0.0.1",
                "port": 9330,
            }
        )
    )
    assert service.connect()["status"] == "success"
    played = service.play_playlist("bedroom", "k-pop")
    assert played["status"] == "success"
    assert service.zone_state("bedroom")["state"] == "playing"
    assert service.pause("bedroom")["state"] == "paused"
    assert service.play_queue("bedroom")["state"] == "playing"
    timer = service.set_sleep_timer("bedroom", 1 / 60)  # one second
    assert timer["status"] == "success"
    time.sleep(1.2)
    assert service.zone_state("bedroom")["state"] == "stopped"


def test_kids_music_quota_and_playpause(tmp_path, roon_env):
    service, auth_path = roon_env
    auth_path.write_text(
        json.dumps(
            {
                "token": "token-abc",
                "core_id": "core-1",
                "core_name": "Quantum",
                "host": "127.0.0.1",
                "port": 9330,
            }
        )
    )
    assert service.connect()["status"] == "success"
    kids = KidsMusicService(db_path=tmp_path / "kids.db", roon=service)

    state = kids.get_state()
    assert state["remaining_plays"] == 2
    assert state["can_start"] is True

    started = kids.playpause()
    assert started["status"] == "success"
    assert started["action"] == "play"
    assert started["playing"] is True
    assert started["sleep_timer_minutes"] == 30

    paused = kids.playpause()
    assert paused["action"] == "pause"
    assert paused["playing"] is False

    # Simulate 15 minutes accrued -> one ticket consumed.
    day = kids._load_day(kids._day_key())
    day.accrued_play_seconds = 15 * 60
    day.playing = False
    kids._save(day)
    after = kids.tick()
    assert after["remaining_plays"] == 1

    day = kids._load_day(kids._day_key())
    day.accrued_play_seconds = 30 * 60
    kids._save(day)
    exhausted = kids.tick()
    assert exhausted["remaining_plays"] == 0
    denied = kids.playpause()
    assert denied["status"] == "error"
    assert denied["action"] == "denied"
