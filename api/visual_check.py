from fastapi import APIRouter, HTTPException

from models.schemas import VisualCheckListResponse, VisualCheckRunResponse
from services.visual_check_service import VisualCheckError, visual_check_service

router = APIRouter(prefix="/api/visual-checks", tags=["visual-checks"])


@router.get("", response_model=VisualCheckListResponse, summary="List configured visual checks")
async def list_visual_checks():
    try:
        return {"checks": visual_check_service.list_checks()}
    except VisualCheckError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/{check_id}/run", response_model=VisualCheckRunResponse, summary="Run a visual check")
async def run_visual_check(check_id: str):
    try:
        return await visual_check_service.run_check(check_id)
    except VisualCheckError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/groups/{group}/run", response_model=VisualCheckRunResponse, summary="Run all visual checks in a group")
async def run_visual_check_group(group: str):
    try:
        return await visual_check_service.run_group(group)
    except VisualCheckError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
