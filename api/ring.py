from fastapi import APIRouter

from models.schemas import RingStatusResponse
from services.ring_service import ring_service

router = APIRouter(tags=["ring"])


@router.get(
    "/api/ring/status",
    response_model=RingStatusResponse,
    response_model_exclude_none=True,
    summary="Get read-only Ring Alarm sensor status",
)
async def get_ring_status():
    return ring_service.get_status()
