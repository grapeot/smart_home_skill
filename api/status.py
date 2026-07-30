import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Query
from models.schemas import AllStatusResponse
from services.hue_service import hue_service
from services.wemo_service import wemo_service
from services.rinnai_service import rinnai_service
from services.meross_service import meross_service
from services.garage_config import garage_config
from services.ring_service import ring_service
from services.samsung_service import samsung_service
from services.roon_service import roon_service
from models.database import save_device_state

router = APIRouter(tags=["status"])
logger = logging.getLogger(__name__)

ALL_DEVICES = {"hue", "wemo", "rinnai", "garage", "ring", "samsung", "roon"}


def _safe_hue_status():
    try:
        return hue_service.get_status()
    except Exception as e:
        logger.warning(f"Hue status failed: {e}")
        return {
            "name": hue_service.light_name,
            "error": str(e),
            "is_on": False,
            "brightness": 0,
            "timer_active": False,
        }


def _safe_wemo_status():
    try:
        return wemo_service.get_all_status()
    except Exception as e:
        logger.warning(f"Wemo status failed: {e}")
        return {"error": str(e)}


async def _safe_rinnai_status(trigger_maintenance: bool = False):
    try:
        return await rinnai_service.get_status(trigger_maintenance=trigger_maintenance)
    except Exception as e:
        logger.warning(f"Rinnai status failed: {e}")
        return {"error": str(e), "is_online": False}


def _safe_garage_status():
    try:
        door_count = meross_service.get_door_count()
        available = meross_service._connected
        return {"door_count": door_count, "available": available, "doors": garage_config.get_doors(door_count)}
    except Exception as e:
        logger.warning(f"Garage status failed: {e}")
        return {"door_count": 0, "available": False}


def _safe_ring_status():
    try:
        return ring_service.get_status()
    except Exception as e:
        logger.warning(f"Ring status failed: {e}")
        return {"configured": True, "locations": [], "error": "Ring status failed"}


@router.get(
    "/api/status",
    response_model=AllStatusResponse,
    response_model_exclude_none=True,
    summary="Get aggregate device status",
)
async def get_all_status(
    devices: Optional[str] = Query(None, description="Comma-separated: hue,wemo,rinnai,garage,ring. Omit to fetch all."),
    rinnai_refresh: bool = Query(False, description="Trigger Rinnai maintenance before fetching"),
):
    requested = ALL_DEVICES if not devices else {s.strip().lower() for s in devices.split(",") if s.strip()}
    result = {}

    if "hue" in requested:
        result["hue"] = _safe_hue_status()

    if "rinnai" in requested:
        rinnai_status = await _safe_rinnai_status(trigger_maintenance=rinnai_refresh)
        result["rinnai"] = rinnai_status
        if rinnai_refresh and "error" not in rinnai_status:
            inlet = rinnai_status.get("inlet_temp")
            outlet = rinnai_status.get("outlet_temp")
            if (inlet is not None and inlet != 0) or (outlet is not None and outlet != 0):
                try:
                    save_device_state("rinnai", "main_house", {
                        "set_temperature": rinnai_status.get("set_temperature"),
                        "inlet_temp": inlet,
                        "outlet_temp": outlet,
                        "water_flow": rinnai_status.get("water_flow"),
                        "recirculation_enabled": rinnai_status.get("recirculation_enabled"),
                    })
                except Exception as e:
                    logger.warning(f"Failed to save Rinnai state to DB: {e}")

    if "wemo" in requested:
        result["wemo"] = await asyncio.to_thread(_safe_wemo_status)

    if "garage" in requested:
        result["garage"] = _safe_garage_status()

    if "ring" in requested:
        result["ring"] = await asyncio.to_thread(_safe_ring_status)

    if "samsung" in requested:
        result["samsung"] = await asyncio.to_thread(samsung_service.get_status)

    if "roon" in requested:
        try:
            result["roon"] = await asyncio.to_thread(roon_service.get_status)
        except Exception as e:
            logger.warning(f"Roon status failed: {e}")
            result["roon"] = {"configured": False, "error": str(e)}

    return result
