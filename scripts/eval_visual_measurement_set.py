#!/usr/bin/env python3
import argparse
import asyncio
import json
import mimetypes
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.visual_check_service import Snapshot, VisualCheckService  # noqa: E402


def _door_map(payload: dict[str, Any]) -> dict[str, str]:
    return {
        item.get("bay"): item.get("state")
        for item in payload.get("garage_doors", [])
        if item.get("bay")
    }


async def _run(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = ROOT / manifest_path
    measurement_dir = manifest_path.parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    service = VisualCheckService(args.config)
    config = service.load_config()
    checks = config.get("checks", {}) or {}
    check_id = args.check_id or manifest.get("check_id")
    if check_id not in checks:
        raise SystemExit(f"Check not found in config: {check_id}")

    check_config = checks[check_id]
    lmstudio_config = config.get("lmstudio", {}) or {}
    service._ensure_lmstudio(lmstudio_config)
    prompt = service._read_text(check_config["prompt_file"])
    schema = service._read_json(check_config["schema_file"])

    results = []
    total_assertions = 0
    passed_assertions = 0

    for case in manifest.get("cases", []):
        image_path = measurement_dir / case["image"]
        mime_type = mimetypes.guess_type(image_path.name)[0] or "image/jpeg"
        snapshot = Snapshot(
            content=image_path.read_bytes(),
            mime_type=mime_type,
            source={"type": "measurement_set", "image": str(image_path)},
        )
        raw = service._call_lmstudio(lmstudio_config, snapshot, prompt, schema)
        payload = service._extract_json(raw)

        expected_doors = case["expected"].get("garage_doors", {})
        actual_doors = _door_map(payload)
        door_results = []
        for bay, expected_state in expected_doors.items():
            actual_state = actual_doors.get(bay)
            passed = actual_state == expected_state
            total_assertions += 1
            passed_assertions += int(passed)
            door_results.append(
                {
                    "bay": bay,
                    "expected": expected_state,
                    "actual": actual_state,
                    "passed": passed,
                }
            )

        for key, expected_value in case["expected"].get("overall", {}).items():
            actual_value = payload.get("overall", {}).get(key)
            passed = actual_value == expected_value
            total_assertions += 1
            passed_assertions += int(passed)
            door_results.append(
                {
                    "path": f"overall.{key}",
                    "expected": expected_value,
                    "actual": actual_value,
                    "passed": passed,
                }
            )

        results.append(
            {
                "id": case["id"],
                "passed": all(item["passed"] for item in door_results),
                "checks": door_results,
                "model_result": payload,
            }
        )

    accuracy = passed_assertions / total_assertions if total_assertions else 0.0
    output = {
        "schema_version": "smart_home.visual_check_measurement_eval.v1",
        "manifest": str(manifest_path),
        "check_id": check_id,
        "case_count": len(results),
        "assertion_count": total_assertions,
        "passed_assertions": passed_assertions,
        "accuracy": accuracy,
        "all_cases_passed": all(item["passed"] for item in results),
        "results": results,
    }
    print(json.dumps(output, ensure_ascii=False, indent=None if args.json else 2))
    return 0 if output["all_cases_passed"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate a VisualCheck measurement set")
    parser.add_argument("manifest", help="Path to measurement set manifest.json")
    parser.add_argument("--config", default="config/vision_checks.yaml")
    parser.add_argument("--check-id", default=None)
    parser.add_argument("--json", action="store_true")
    return asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
