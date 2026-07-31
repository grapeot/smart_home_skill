from fastapi import APIRouter, Depends

from models.schemas import ActionResult, SamsungTVStatus
from services.auth import require_control_auth
from services.samsung_service import samsung_service

router = APIRouter(prefix="/api/samsung", tags=["samsung"])


@router.get("/status", response_model=SamsungTVStatus, summary="Get Samsung TV status")
async def get_samsung_status():
    return samsung_service.get_status()


@router.post("/power/toggle", response_model=ActionResult, summary="Toggle Samsung TV power", dependencies=[Depends(require_control_auth)])
async def toggle_power():
    return await samsung_service.toggle_power()


@router.post("/power/on", response_model=ActionResult, summary="Turn Samsung TV on", dependencies=[Depends(require_control_auth)])
async def power_on():
    return await samsung_service.power_on()


@router.post("/power/off", response_model=ActionResult, summary="Turn Samsung TV off", dependencies=[Depends(require_control_auth)])
async def power_off():
    return await samsung_service.power_off()


@router.post("/volume/up", response_model=ActionResult, summary="Samsung TV volume up", dependencies=[Depends(require_control_auth)])
async def volume_up():
    return await samsung_service.volume_up()


@router.post("/volume/down", response_model=ActionResult, summary="Samsung TV volume down", dependencies=[Depends(require_control_auth)])
async def volume_down():
    return await samsung_service.volume_down()


@router.post("/mute", response_model=ActionResult, summary="Toggle Samsung TV mute", dependencies=[Depends(require_control_auth)])
async def toggle_mute():
    return await samsung_service.toggle_mute()