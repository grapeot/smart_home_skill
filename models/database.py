import sqlite3
import json
import os
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "smart_home.db"

def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS device_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_type TEXT NOT NULL,
            device_name TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            data JSON NOT NULL
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_device_history_type_name 
        ON device_history(device_type, device_name)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_device_history_timestamp 
        ON device_history(timestamp)
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS garage_bridge_commands (
            principal_id TEXT NOT NULL,
            command_id TEXT NOT NULL,
            request_hash TEXT NOT NULL,
            request_json TEXT NOT NULL,
            counter_decimal TEXT NOT NULL,
            operation TEXT NOT NULL,
            door_index INTEGER NOT NULL,
            effective_mode TEXT NOT NULL,
            status TEXT NOT NULL,
            terminal INTEGER NOT NULL DEFAULT 0,
            blocks_target INTEGER NOT NULL DEFAULT 0,
            result_json TEXT,
            error_code TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            dispatch_started_at TEXT,
            completed_at TEXT,
            PRIMARY KEY (principal_id, command_id),
            UNIQUE (principal_id, counter_decimal)
        )
    """)
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_garage_bridge_target_fence
        ON garage_bridge_commands(door_index)
        WHERE blocks_target = 1
    """)
    cursor.execute("""
        UPDATE garage_bridge_commands
        SET status = 'failed_before_dispatch', terminal = 1, blocks_target = 0,
            error_code = 'server_restarted_before_dispatch',
            updated_at = CURRENT_TIMESTAMP, completed_at = CURRENT_TIMESTAMP
        WHERE status = 'accepted' AND terminal = 0
    """)
    cursor.execute("""
        UPDATE garage_bridge_commands
        SET status = 'outcome_unknown', terminal = 1, blocks_target = 1,
            error_code = 'server_restarted_during_dispatch',
            updated_at = CURRENT_TIMESTAMP, completed_at = CURRENT_TIMESTAMP
        WHERE status = 'dispatching' AND terminal = 0
    """)
    conn.commit()
    conn.close()

def save_device_state(device_type: str, device_name: str, data: dict):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO device_history (device_type, device_name, data)
        VALUES (?, ?, ?)
    """, (device_type, device_name, json.dumps(data)))
    conn.commit()
    conn.close()

def delete_rinnai_zero_temp_records(dry_run: bool = False):
    """Remove Rinnai records where inlet_temp or outlet_temp is 0 or NULL (invalid/stale data)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, timestamp, json_extract(data, '$.inlet_temp') as inlet, json_extract(data, '$.outlet_temp') as outlet
        FROM device_history
        WHERE device_type = 'rinnai'
        AND (
            json_extract(data, '$.inlet_temp') IS NULL OR json_extract(data, '$.inlet_temp') = 0
            OR json_extract(data, '$.outlet_temp') IS NULL OR json_extract(data, '$.outlet_temp') = 0
        )
    """)
    to_delete = cursor.fetchall()
    if dry_run:
        conn.close()
        return [(r[0], r[1], r[2], r[3]) for r in to_delete]
    for row in to_delete:
        cursor.execute("DELETE FROM device_history WHERE id = ?", (row[0],))
    deleted = len(to_delete)
    conn.commit()
    conn.close()
    return deleted


def get_device_history(device_type: str = None, device_name: str = None, hours: int = 24):
    conn = get_connection()
    cursor = conn.cursor()
    
    query = """
        SELECT * FROM device_history 
        WHERE timestamp >= datetime('now', ?)
    """
    params = [f"-{hours} hours"]
    
    if device_type:
        query += " AND device_type = ?"
        params.append(device_type)
    
    if device_name:
        query += " AND device_name = ?"
        params.append(device_name)
    
    query += " ORDER BY timestamp DESC"
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


def claim_garage_bridge_command(
    principal_id: str,
    command_id: str,
    request_hash: str,
    request_json: str,
    counter_decimal: str,
    operation: str,
    door_index: int,
    effective_mode: str,
):
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT * FROM garage_bridge_commands WHERE principal_id = ? AND command_id = ?",
            (principal_id, command_id),
        ).fetchone()
        if existing is not None:
            conn.commit()
            return dict(existing), False, existing["request_hash"] != request_hash
        try:
            conn.execute(
                """
                INSERT INTO garage_bridge_commands (
                    principal_id, command_id, request_hash, request_json,
                    counter_decimal, operation, door_index, effective_mode,
                    status, terminal, blocks_target
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'accepted', 0, ?)
                """,
                (
                    principal_id,
                    command_id,
                    request_hash,
                    request_json,
                    counter_decimal,
                    operation,
                    door_index,
                    effective_mode,
                    1 if effective_mode == "live" else 0,
                ),
            )
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            return None, False, str(exc)
        row = conn.execute(
            "SELECT * FROM garage_bridge_commands WHERE principal_id = ? AND command_id = ?",
            (principal_id, command_id),
        ).fetchone()
        conn.commit()
        return dict(row), True, False
    finally:
        conn.close()


def get_garage_bridge_command(principal_id: str, command_id: str):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM garage_bridge_commands WHERE principal_id = ? AND command_id = ?",
            (principal_id, command_id),
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def get_garage_bridge_target_blocker(
    door_index: int,
    *,
    exclude_principal_id: str | None = None,
    exclude_command_id: str | None = None,
):
    conn = get_connection()
    try:
        try:
            row = conn.execute(
                """
                SELECT * FROM garage_bridge_commands
                WHERE door_index = ? AND blocks_target = 1
                  AND NOT (principal_id = ? AND command_id = ?)
                LIMIT 1
                """,
                (door_index, exclude_principal_id or "", exclude_command_id or ""),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            if "no such table" not in str(exc):
                raise
            return None
        return dict(row) if row is not None else None
    finally:
        conn.close()


def update_garage_bridge_command(
    principal_id: str,
    command_id: str,
    status: str,
    *,
    terminal: bool,
    blocks_target: bool,
    result: dict | None = None,
    error_code: str | None = None,
):
    conn = get_connection()
    try:
        dispatch_started = "CURRENT_TIMESTAMP" if status == "dispatching" else "dispatch_started_at"
        completed = "CURRENT_TIMESTAMP" if terminal else "completed_at"
        conn.execute(
            f"""
            UPDATE garage_bridge_commands
            SET status = ?, terminal = ?, blocks_target = ?, result_json = ?, error_code = ?,
                updated_at = CURRENT_TIMESTAMP, dispatch_started_at = {dispatch_started},
                completed_at = {completed}
            WHERE principal_id = ? AND command_id = ?
            """,
            (
                status,
                int(terminal),
                int(blocks_target),
                json.dumps(result, sort_keys=True) if result is not None else None,
                error_code,
                principal_id,
                command_id,
            ),
        )
        conn.commit()
        return get_garage_bridge_command(principal_id, command_id)
    finally:
        conn.close()
