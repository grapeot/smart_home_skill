import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from models.schemas import ActionResult, RoonPairStatus, RoonStatus, RoonZonesResponse
from services.auth import require_control_auth
from services.roon_service import roon_service

router = APIRouter(prefix="/api/roon", tags=["roon"])


class RoonZoneRequest(BaseModel):
    zone: str = Field(..., min_length=1, description="Roon zone or output display name")


class RoonPlayRequest(BaseModel):
    zone: str = Field(..., min_length=1)
    source: str = Field("queue", description="queue or playlist")
    playlist: Optional[str] = Field(None, description="Required when source=playlist")


class RoonSleepTimerRequest(BaseModel):
    zone: str = Field(..., min_length=1)
    minutes: float = Field(..., gt=0, le=1440)


@router.get("/status", response_model=RoonStatus, summary="Get Roon connection and zone summary")
async def get_roon_status():
    return await asyncio.to_thread(roon_service.get_status)


@router.get("/zones", response_model=RoonZonesResponse, summary="List Roon zones")
async def list_zones():
    result = await asyncio.to_thread(roon_service.list_zones)
    if result.get("status") == "error":
        raise HTTPException(status_code=503, detail=result.get("message") or "Roon unavailable")
    return result


@router.post(
    "/pair/start",
    response_model=RoonPairStatus,
    summary="Start Roon extension pairing",
    dependencies=[Depends(require_control_auth)],
)
async def pair_start():
    return await asyncio.to_thread(roon_service.start_pairing)


@router.get("/pair/status", response_model=RoonPairStatus, summary="Get Roon pairing status")
async def pair_status():
    return await asyncio.to_thread(roon_service.pair_status)


@router.post(
    "/play",
    response_model=ActionResult,
    summary="Play queue or playlist on a zone",
    dependencies=[Depends(require_control_auth)],
)
async def play(request: RoonPlayRequest):
    source = request.source.strip().lower()
    if source == "queue":
        result = await asyncio.to_thread(roon_service.play_queue, request.zone)
    elif source == "playlist":
        if not request.playlist:
            raise HTTPException(status_code=400, detail="playlist is required when source=playlist")
        result = await asyncio.to_thread(
            roon_service.play_playlist, request.zone, request.playlist
        )
    else:
        raise HTTPException(status_code=400, detail="source must be queue or playlist")
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message") or "play failed")
    return result


@router.post(
    "/pause",
    response_model=ActionResult,
    summary="Pause a zone",
    dependencies=[Depends(require_control_auth)],
)
async def pause(request: RoonZoneRequest):
    result = await asyncio.to_thread(roon_service.pause, request.zone)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message") or "pause failed")
    return result


@router.post(
    "/stop",
    response_model=ActionResult,
    summary="Stop a zone",
    dependencies=[Depends(require_control_auth)],
)
async def stop(request: RoonZoneRequest):
    result = await asyncio.to_thread(roon_service.stop, request.zone)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message") or "stop failed")
    return result


@router.post(
    "/playpause",
    response_model=ActionResult,
    summary="Toggle play/pause on a zone",
    dependencies=[Depends(require_control_auth)],
)
async def playpause(request: RoonZoneRequest):
    result = await asyncio.to_thread(roon_service.playpause, request.zone)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message") or "playpause failed")
    return result


@router.post(
    "/sleep-timer",
    response_model=ActionResult,
    summary="Stop a zone after N minutes (local timer; Roon has no native sleep timer)",
    dependencies=[Depends(require_control_auth)],
)
async def sleep_timer(request: RoonSleepTimerRequest):
    result = await asyncio.to_thread(
        roon_service.set_sleep_timer, request.zone, request.minutes
    )
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message") or "sleep timer failed")
    return result


@router.delete(
    "/sleep-timer/{zone}",
    response_model=ActionResult,
    summary="Cancel a zone sleep timer",
    dependencies=[Depends(require_control_auth)],
)
async def cancel_sleep_timer(zone: str):
    result = await asyncio.to_thread(roon_service.cancel_sleep_timer, zone)
    if result.get("status") == "error":
        raise HTTPException(status_code=404, detail=result.get("message") or "no timer")
    return result
