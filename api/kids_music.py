import asyncio

from fastapi import APIRouter, Depends, HTTPException

from models.schemas import KidsMusicState
from services.auth import require_control_auth
from services.kids_music_service import kids_music_service

router = APIRouter(prefix="/api/kids-music", tags=["kids-music"])


@router.get(
    "/state",
    response_model=KidsMusicState,
    summary="Kids music ticket state for M5Paper",
)
async def kids_state():
    return await asyncio.to_thread(kids_music_service.get_state)


@router.post(
    "/playpause",
    response_model=KidsMusicState,
    summary="Toggle kids music play/pause under daily ticket policy",
    dependencies=[Depends(require_control_auth)],
)
async def kids_playpause():
    result = await asyncio.to_thread(kids_music_service.playpause)
    if result.get("status") == "error":
        # Policy denial still returns body fields for the device UI.
        if result.get("action") == "denied":
            return result
        raise HTTPException(status_code=400, detail=result.get("message") or "kids playpause failed")
    return result
