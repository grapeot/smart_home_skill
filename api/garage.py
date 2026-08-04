from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from models.schemas import (
    ApiError,
    GarageBridgeCommandRequest,
    GarageBridgeCommandResponse,
    GarageStatus,
    GarageToggleResponse,
)
from services.auth import require_control_auth, require_garage_bridge_auth
from services.garage_bridge_service import (
    GarageBridgeConfigurationError,
    GarageBridgeConflictError,
    get_command,
    submit_command,
)
from services.garage_config import garage_config
from services.meross_service import meross_service

router = APIRouter(prefix="/api/garage", tags=["garage"])

@router.get("/status", response_model=GarageStatus, summary="Get Meross garage controller status")
async def get_garage_status():
    door_count = meross_service.get_door_count()
    return {
        "door_count": door_count,
        "available": meross_service._connected,
        "doors": garage_config.get_doors(door_count),
    }

async def _toggle_garage(door_index: int):
    door_count = meross_service.get_door_count()
    if door_index < 1 or door_index > door_count:
        raise HTTPException(400, f"door_index must be between 1 and {door_count}")
    return await meross_service.toggle_door(door_index)


@router.post(
    "/{door_index}/toggle",
    response_model=GarageToggleResponse,
    responses={400: {"model": ApiError}},
    summary="Toggle a garage door",
    description="Sensitive physical action. Uses POST only and sends an optional notification when configured.",
    dependencies=[Depends(require_control_auth)],
)
async def garage_toggle(door_index: int = Path(..., ge=1)):
    return await _toggle_garage(door_index)


@router.post(
    "/bridge/commands",
    response_model=GarageBridgeCommandResponse,
    dependencies=[Depends(require_garage_bridge_auth)],
    summary="Submit an idempotent ESP-NOW bridge command",
)
async def garage_bridge_submit(command: GarageBridgeCommandRequest, response: Response):
    try:
        resource, created = await submit_command(command)
    except GarageBridgeConfigurationError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except GarageBridgeConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return resource


@router.get(
    "/bridge/commands/{command_id}",
    response_model=GarageBridgeCommandResponse,
    dependencies=[Depends(require_garage_bridge_auth)],
    summary="Query an idempotent ESP-NOW bridge command",
)
async def garage_bridge_get(command_id: str = Path(..., pattern=r"^[0-9a-f]{32}$")):
    try:
        resource = get_command(command_id)
    except GarageBridgeConfigurationError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    if resource is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Garage bridge command not found")
    return resource
