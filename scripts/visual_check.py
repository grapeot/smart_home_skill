#!/usr/bin/env python3
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.camera_service import camera_service  # noqa: E402
from services.visual_check_service import VisualCheckError, VisualCheckService  # noqa: E402


def _init_camera_service() -> None:
    load_dotenv(ROOT / ".env")
    user = os.getenv("CAMERA_USER")
    password = os.getenv("CAMERA_PASSWORD")
    if user and password:
        camera_service.set_credentials(user, password)
        camera_service.load_config()


async def _run(args: argparse.Namespace) -> int:
    _init_camera_service()
    service = VisualCheckService(args.config)
    try:
        if args.command == "list":
            payload = {"checks": service.list_checks()}
        elif args.command == "run":
            payload = await service.run_check(args.check_id, save_artifacts=not args.no_artifacts)
        elif args.command == "run-all":
            payload = await service.run_group(args.group, save_artifacts=not args.no_artifacts)
        else:
            raise VisualCheckError(f"Unknown command: {args.command}")
    except VisualCheckError as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    finally:
        await camera_service.close()

    print(json.dumps(payload, indent=None if args.json else 2, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Smart Home visual checks")
    parser.add_argument("--config", default=os.getenv("VISUAL_CHECK_CONFIG", "config/vision_checks.yaml"))
    parser.add_argument("--json", action="store_true", help="Emit compact JSON")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List configured visual checks")

    run = sub.add_parser("run", help="Run one visual check")
    run.add_argument("check_id")
    run.add_argument("--no-artifacts", action="store_true")

    run_all = sub.add_parser("run-all", help="Run all visual checks in a group")
    run_all.add_argument("--group", default="nightly")
    run_all.add_argument("--no-artifacts", action="store_true")

    return asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
