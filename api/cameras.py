import logging
import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse
from models.schemas import ApiError, CameraListResponse

from services.camera_service import camera_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cameras", tags=["cameras"])


@router.get("", response_model=CameraListResponse, summary="List configured cameras")
async def get_cameras():
    return {"cameras": camera_service.get_cameras()}


@router.get(
    "/snapshot/{camera_id}",
    responses={
        200: {"content": {"image/jpeg": {}}},
        404: {"model": ApiError},
        502: {"model": ApiError},
        504: {"model": ApiError},
    },
    summary="Fetch a camera snapshot",
)
async def get_snapshot(camera_id: str):
    image_data, error = await camera_service.get_snapshot(camera_id)
    
    if error:
        logger.warning(f"Snapshot error for {camera_id}: {error}")
        if "not found" in error:
            raise HTTPException(status_code=404, detail=error)
        elif "Timeout" in error:
            raise HTTPException(status_code=504, detail=error)
        else:
            raise HTTPException(status_code=502, detail=error)
    
    return Response(content=image_data, media_type="image/jpeg")


@router.get(
    "/stream/{camera_id}",
    responses={200: {"content": {"multipart/x-mixed-replace": {}}}},
    summary="Proxy MJPG video stream from camera sub stream",
)
async def get_stream(camera_id: str):
    camera = camera_service.get_camera_by_id(camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail=f"Camera not found: {camera_id}")

    ip = camera["ip"]
    url = f"http://{ip}/cgi-bin/mjpg/video.cgi?subtype=1"
    user = camera_service.user
    password = camera_service.password
    if not user or not password:
        raise HTTPException(status_code=500, detail="Camera credentials not configured")

    async def stream_generator():
        async with httpx.AsyncClient(auth=httpx.DigestAuth(user, password), timeout=httpx.Timeout(30.0, connect=5.0)) as client:
            async with client.stream("GET", url) as resp:
                async for chunk in resp.aiter_raw():
                    yield chunk

    return StreamingResponse(
        stream_generator(),
        media_type="multipart/x-mixed-replace; boundary=myboundary",
    )
