import hashlib
import json
import os

from models import database
from services.meross_service import meross_service


class GarageBridgeConfigurationError(RuntimeError):
    pass


class GarageBridgeConflictError(RuntimeError):
    pass


def _principal() -> str:
    principal = os.getenv("GARAGE_BRIDGE_PRINCIPAL", "").strip()
    if not principal:
        raise GarageBridgeConfigurationError("Garage bridge principal is not configured")
    return principal


def _configuration() -> tuple[str, str, int]:
    mode = os.getenv("GARAGE_BRIDGE_MODE", "disabled").strip().lower()
    principal = _principal()
    door_value = os.getenv("GARAGE_BRIDGE_DOOR_INDEX", "").strip()
    if mode not in {"dry_run", "live"}:
        raise GarageBridgeConfigurationError("Garage bridge is disabled")
    if not door_value.isdigit() or int(door_value) < 1:
        raise GarageBridgeConfigurationError("Garage bridge target mapping is not configured")
    return mode, principal, int(door_value)


def _canonical_request(command) -> tuple[str, str]:
    body = {
        "schema_version": command.schema_version,
        "command_id": command.command_id,
        "counter": command.counter,
        "operation": command.operation,
    }
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return encoded, hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _resource(row: dict) -> dict:
    return {
        "schema_version": 1,
        "command_id": row["command_id"],
        "request_hash": row["request_hash"],
        "mode": row["effective_mode"],
        "status": row["status"],
        "terminal": bool(row["terminal"]),
        "blocks_target": bool(row["blocks_target"]),
        "result": json.loads(row["result_json"]) if row.get("result_json") else None,
        "error_code": row.get("error_code"),
    }


async def submit_command(command) -> tuple[dict, bool]:
    mode, principal, door_index = _configuration()
    request_json, request_hash = _canonical_request(command)
    row, created, conflict = database.claim_garage_bridge_command(
        principal,
        command.command_id,
        request_hash,
        request_json,
        command.counter,
        command.operation,
        door_index,
        mode,
    )
    if conflict:
        raise GarageBridgeConflictError("command_id, counter, or target is already claimed")
    if not created:
        return _resource(row), False

    if mode == "dry_run":
        row = database.update_garage_bridge_command(
            principal,
            command.command_id,
            "dry_run",
            terminal=True,
            blocks_target=False,
            result={"operation": command.operation, "door_index": door_index, "would_dispatch": True},
        )
        return _resource(row), True

    # Persist crossing the physical side-effect boundary before calling Meross.
    current_mode, current_principal, current_door = _configuration()
    if (current_mode, current_principal, current_door) != (mode, principal, door_index):
        row = database.update_garage_bridge_command(
            principal,
            command.command_id,
            "rejected",
            terminal=True,
            blocks_target=False,
            error_code="policy_changed_before_dispatch",
        )
        return _resource(row), True

    database.update_garage_bridge_command(
        principal,
        command.command_id,
        "dispatching",
        terminal=False,
        blocks_target=True,
    )
    try:
        result = await meross_service.toggle_door(door_index)
    except Exception as exc:
        result = {"status": "error", "message": str(exc)}

    action_status = result.get("status") if isinstance(result, dict) else None
    if action_status == "success":
        status, blocks_target, error_code = "verified", False, None
    elif action_status == "triggered_unverified":
        status, blocks_target, error_code = "unverified", True, "final_state_unverified"
    else:
        status, blocks_target, error_code = "outcome_unknown", True, "dispatch_outcome_unknown"
    row = database.update_garage_bridge_command(
        principal,
        command.command_id,
        status,
        terminal=True,
        blocks_target=blocks_target,
        result=result if isinstance(result, dict) else {"raw_result": repr(result)},
        error_code=error_code,
    )
    return _resource(row), True


def get_command(command_id: str) -> dict | None:
    principal = _principal()
    row = database.get_garage_bridge_command(principal, command_id)
    return _resource(row) if row is not None else None
