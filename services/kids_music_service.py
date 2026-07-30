import logging
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from services.roon_service import roon_service

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = ROOT / "data" / "kids_music.db"


@dataclass
class KidsSession:
    day_key: str
    remaining_plays: int
    playing: bool
    zone_name: str
    playlist_name: str
    session_started_at: Optional[float] = None
    accrued_play_seconds: float = 0.0
    last_tick_at: Optional[float] = None


class KidsMusicService:
    """Daily play-ticket policy for the M5Paper kids music terminal."""

    def __init__(self, db_path: Optional[Path] = None, roon=None):
        self.db_path = Path(db_path or DEFAULT_DB_PATH)
        self.roon = roon or roon_service
        self._lock = threading.RLock()
        self._watchdog: Optional[threading.Thread] = None
        self._stop_watchdog = threading.Event()
        self._ensure_db()

    def _cfg(self) -> Dict[str, Any]:
        return self.roon.kids_config

    def _tz(self) -> ZoneInfo:
        return ZoneInfo(self._cfg()["timezone"])

    def _day_key(self, now: Optional[datetime] = None) -> str:
        cfg = self._cfg()
        now = now or datetime.now(self._tz())
        boundary = int(cfg["day_boundary_hour"])
        shifted = now - timedelta(hours=boundary)
        return shifted.date().isoformat()

    def _ensure_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_quota (
                    day_key TEXT PRIMARY KEY,
                    remaining_plays INTEGER NOT NULL,
                    accrued_play_seconds REAL NOT NULL DEFAULT 0,
                    session_started_at REAL,
                    playing INTEGER NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.commit()

    def _load_day(self, day_key: str) -> KidsSession:
        cfg = self._cfg()
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT remaining_plays, accrued_play_seconds, session_started_at, playing "
                "FROM daily_quota WHERE day_key = ?",
                (day_key,),
            ).fetchone()
            if row is None:
                remaining = int(cfg["daily_plays"])
                conn.execute(
                    "INSERT INTO daily_quota(day_key, remaining_plays, accrued_play_seconds, "
                    "session_started_at, playing, updated_at) VALUES (?, ?, 0, NULL, 0, ?)",
                    (day_key, remaining, time.time()),
                )
                conn.commit()
                return KidsSession(
                    day_key=day_key,
                    remaining_plays=remaining,
                    playing=False,
                    zone_name=cfg["zone_name"],
                    playlist_name=cfg["playlist_name"],
                )
        return KidsSession(
            day_key=day_key,
            remaining_plays=int(row[0]),
            accrued_play_seconds=float(row[1] or 0),
            session_started_at=float(row[2]) if row[2] is not None else None,
            playing=bool(row[3]),
            zone_name=cfg["zone_name"],
            playlist_name=cfg["playlist_name"],
        )

    def _save(self, session: KidsSession) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO daily_quota(
                    day_key, remaining_plays, accrued_play_seconds,
                    session_started_at, playing, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(day_key) DO UPDATE SET
                    remaining_plays=excluded.remaining_plays,
                    accrued_play_seconds=excluded.accrued_play_seconds,
                    session_started_at=excluded.session_started_at,
                    playing=excluded.playing,
                    updated_at=excluded.updated_at
                """,
                (
                    session.day_key,
                    session.remaining_plays,
                    session.accrued_play_seconds,
                    session.session_started_at,
                    1 if session.playing else 0,
                    time.time(),
                ),
            )
            conn.commit()

    def start_watchdog(self) -> None:
        if self._watchdog and self._watchdog.is_alive():
            return
        self._stop_watchdog.clear()
        self._watchdog = threading.Thread(
            target=self._watchdog_loop, name="kids-music-watchdog", daemon=True
        )
        self._watchdog.start()

    def stop_watchdog(self) -> None:
        self._stop_watchdog.set()
        if self._watchdog and self._watchdog.is_alive():
            self._watchdog.join(timeout=2)
        self._watchdog = None

    def _watchdog_loop(self) -> None:
        while not self._stop_watchdog.wait(5.0):
            try:
                self.tick()
            except Exception:
                logger.exception("kids music watchdog tick failed")

    def tick(self) -> Dict[str, Any]:
        """Accrue playing time and enforce unit/sleep limits."""
        with self._lock:
            cfg = self._cfg()
            unit_seconds = int(cfg["unit_minutes"]) * 60
            day_key = self._day_key()
            session = self._load_day(day_key)
            now = time.time()

            if session.playing and session.last_tick_at is None:
                session.last_tick_at = session.session_started_at or now

            if session.playing:
                # Prefer Roon truth when available.
                try:
                    zone = self.roon.zone_state(session.zone_name)
                    roon_state = (zone.get("state") or "").lower()
                except Exception:
                    roon_state = "playing"

                if roon_state == "playing":
                    delta = now - (session.last_tick_at or now)
                    if delta > 0:
                        session.accrued_play_seconds += delta
                    session.last_tick_at = now
                elif roon_state == "paused":
                    session.last_tick_at = now
                else:
                    session.playing = False
                    session.last_tick_at = None

            session.remaining_plays = max(
                0, int(cfg["daily_plays"]) - int(session.accrued_play_seconds // unit_seconds)
            )

            if session.remaining_plays <= 0 and session.playing:
                try:
                    self.roon.stop(session.zone_name)
                except Exception:
                    logger.exception("failed to stop kids zone at quota end")
                session.playing = False
                session.session_started_at = None
                session.last_tick_at = None
                session.remaining_plays = 0

            self._save(session)
            return self._public_state(session)

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            # Refresh accrual before reporting.
            return self.tick()

    def _public_state(self, session: KidsSession) -> Dict[str, Any]:
        cfg = self._cfg()
        unit_seconds = int(cfg["unit_minutes"]) * 60
        into_unit = session.accrued_play_seconds % unit_seconds if unit_seconds else 0
        return {
            "status": "success",
            "day_key": session.day_key,
            "remaining_plays": session.remaining_plays,
            "daily_plays": int(cfg["daily_plays"]),
            "unit_minutes": int(cfg["unit_minutes"]),
            "playing": session.playing,
            "zone": session.zone_name,
            "playlist": session.playlist_name,
            "accrued_play_seconds": round(session.accrued_play_seconds, 1),
            "seconds_into_current_unit": round(into_unit, 1),
            "timezone": cfg["timezone"],
            "can_start": session.remaining_plays > 0,
        }

    def playpause(self) -> Dict[str, Any]:
        with self._lock:
            cfg = self._cfg()
            day_key = self._day_key()
            session = self._load_day(day_key)
            zone = cfg["zone_name"]
            playlist = cfg["playlist_name"]
            unit_minutes = int(cfg["unit_minutes"])
            unit_seconds = unit_minutes * 60
            session.remaining_plays = max(
                0, int(cfg["daily_plays"]) - int(session.accrued_play_seconds // unit_seconds)
            )

            # Sync from Roon if possible.
            roon_state = None
            try:
                roon_state = (self.roon.zone_state(zone).get("state") or "").lower()
            except Exception as exc:
                logger.info("kids playpause could not read zone state: %s", exc)

            if session.playing or roon_state == "playing":
                result = self.roon.pause(zone)
                if result.get("status") != "success":
                    return result
                # Freeze accrual clock; pause does not consume.
                if session.playing and session.last_tick_at:
                    # flush up to pause instant
                    now = time.time()
                    session.accrued_play_seconds += max(0.0, now - session.last_tick_at)
                    session.remaining_plays = max(
                        0,
                        int(cfg["daily_plays"])
                        - int(session.accrued_play_seconds // unit_seconds),
                    )
                session.playing = False
                session.last_tick_at = None
                self._save(session)
                state = self._public_state(session)
                state["action"] = "pause"
                state["message"] = result.get("message")
                return state

            if session.remaining_plays <= 0:
                self._save(session)
                state = self._public_state(session)
                state.update(
                    {
                        "status": "error",
                        "message": "No plays remaining today",
                        "action": "denied",
                    }
                )
                return state

            # Resume existing queue if paused; otherwise start playlist.
            if roon_state == "paused":
                result = self.roon.play_queue(zone)
            else:
                result = self.roon.play_playlist(zone, playlist)
            if result.get("status") != "success":
                return result

            now = time.time()
            first_start_today = session.session_started_at is None and session.accrued_play_seconds == 0
            if session.session_started_at is None:
                session.session_started_at = now
            session.playing = True
            session.last_tick_at = now
            self._save(session)

            if first_start_today:
                # 2 plays × 15 min = 30 min sleep timer backup stop.
                minutes = max(unit_minutes, session.remaining_plays * unit_minutes)
                try:
                    self.roon.set_sleep_timer(zone, minutes)
                except Exception:
                    logger.exception("failed to set kids sleep timer")

            state = self._public_state(session)
            state["action"] = "play"
            state["message"] = result.get("message")
            state["sleep_timer_minutes"] = (
                max(unit_minutes, session.remaining_plays * unit_minutes) if first_start_today else None
            )
            return state


kids_music_service = KidsMusicService()
