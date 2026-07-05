import asyncio
import logging
import os
import socket
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional, Set, Tuple

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv
import uvicorn

from api import hue, wemo, rinnai, garage, status, history, cameras, schedule, visual_check
from models.schemas import HealthResponse
from services.hue_service import hue_service
from services.wemo_service import wemo_service
from services.rinnai_service import rinnai_service
from services.meross_service import meross_service
from services.camera_service import camera_service
from services.scheduler import init_scheduler, shutdown_scheduler
from services.wemo_schedule import WemoScheduleManager
from services.action_executor import init_action_executor

load_dotenv(Path(__file__).parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


DEFAULT_TAILSCALE_HOST = os.getenv("SMART_HOME_TAILSCALE_HOST", "localhost")


def _split_env_list(value: Optional[str], default: List[str]) -> List[str]:
    if not value:
        return default
    items = [item.strip() for item in value.split(",") if item.strip()]
    return items or default


def _safe_frontend_file(path: str) -> Optional[Path]:
    frontend_root = FRONTEND_DIST.resolve()
    candidate = (FRONTEND_DIST / path).resolve()
    if not candidate.is_relative_to(frontend_root):
        return None
    if candidate.exists() and candidate.is_file():
        return candidate
    return None


def _bind_sockets(hosts: List[str], port: int) -> List[socket.socket]:
    sockets: List[socket.socket] = []
    seen: Set[Tuple[int, str, int]] = set()
    for host in hosts:
        try:
            addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            logger.warning("Skipping unresolved bind host %s: %s", host, exc)
            continue

        for family, socktype, proto, _canonname, sockaddr in addresses:
            key = (family, sockaddr[0], sockaddr[1])
            if key in seen:
                continue
            sock = socket.socket(family, socktype, proto)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(sockaddr)
                sock.listen(2048)
            except OSError as exc:
                sock.close()
                logger.warning("Skipping bind address %s:%s: %s", sockaddr[0], sockaddr[1], exc)
                continue
            sockets.append(sock)
            seen.add(key)
            logger.info("Listening on %s:%s", sockaddr[0], sockaddr[1])

    if not sockets:
        raise RuntimeError(f"Could not bind any configured host on port {port}: {hosts}")
    return sockets


def _run_uvicorn() -> None:
    port = int(os.getenv("PORT", "7999"))
    bind_hosts = _split_env_list(os.getenv("SMART_HOME_BIND_HOSTS"), ["127.0.0.1"])
    sockets = _bind_sockets(bind_hosts, port)
    config = uvicorn.Config(app, log_level="info")
    server = uvicorn.Server(config)
    server.run(sockets=sockets)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Smart Home Dashboard...")
    hue_ip = os.getenv("HUE_BRIDGE_IP")
    logger.info(f"Debug: HUE_BRIDGE_IP={hue_ip or '(not configured)'}, .env exists={Path(__file__).parent.joinpath('.env').exists()}")
    hue_service.connect()

    wemo_service.init_devices()

    await rinnai_service.connect()

    await meross_service.connect()

    camera_user = os.getenv("CAMERA_USER")
    camera_password = os.getenv("CAMERA_PASSWORD")
    if camera_user and camera_password:
        camera_service.set_credentials(camera_user, camera_password)
        camera_service.load_config()
    else:
        logger.warning("Camera credentials not configured, camera feature disabled")

    init_scheduler()

    init_action_executor()

    wemo_schedule_manager = WemoScheduleManager("config/wemo_config.yaml")
    for name, device in wemo_service.devices.items():
        wemo_schedule_manager.register_device(name, device)
    wemo_schedule_manager.start()

    logger.info("Smart Home Dashboard started")

    yield

    logger.info("Shutting down Smart Home Dashboard...")

    shutdown_scheduler()

    if wemo_schedule_manager:
        wemo_schedule_manager.stop()

    await camera_service.close()

    await rinnai_service.close()
    await meross_service.close()

    logger.info("Smart Home Dashboard shutdown complete")


app = FastAPI(
    title="Smart Home Skill",
    version="2.0.0",
    description=(
        "Local AI-facing smart home control layer. Fetch this OpenAPI schema "
        "before invoking device actions, then use private overlays only for "
        "house-specific names, defaults, and safety policy."
    ),
    lifespan=lifespan,
)

cors_origins = _split_env_list(
    os.getenv("SMART_HOME_CORS_ORIGINS"),
    [
        "http://localhost:7999",
        "http://127.0.0.1:7999",
        f"http://{DEFAULT_TAILSCALE_HOST}:7999",
        f"https://{DEFAULT_TAILSCALE_HOST}",
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(hue.router)
app.include_router(wemo.router)
app.include_router(rinnai.router)
app.include_router(garage.router)
app.include_router(status.router)
app.include_router(history.router)
app.include_router(cameras.router)
app.include_router(schedule.router)
app.include_router(visual_check.router)

@app.get("/health", response_model=HealthResponse, tags=["health"], summary="Health check")
async def health_check():
    return {"status": "healthy"}

FRONTEND_DIST = Path(__file__).parent / "frontend" / "dist"

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")
    
    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API route not found")
        file_path = _safe_frontend_file(full_path)
        if file_path:
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIST / "index.html")
    
    logger.info(f"Serving frontend from {FRONTEND_DIST}")

if __name__ == "__main__":
    _run_uvicorn()
