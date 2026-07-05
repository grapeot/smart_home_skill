import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import yaml

from services.visual_check_service import VisualCheckService


ROOT = Path(__file__).resolve().parents[1]


def write_config(tmp_path: Path, result_schema: Path, prompt: Path, image: Path) -> Path:
    config = {
        "lmstudio": {"api_base": "http://127.0.0.1:1234/v1", "model": "test-model"},
        "artifact_dir": str(tmp_path / "artifacts"),
        "retries": 1,
        "checks": {
            "garage": {
                "group": "nightly",
                "source": {"type": "http_snapshot", "url": "http://example.test/snapshot.svg"},
                "prompt_file": str(prompt),
                "schema_file": str(result_schema),
                "assertions": [
                    {"name": "all_closed", "path": "$.overall.any_door_open", "equals": False}
                ],
            }
        },
    }
    path = tmp_path / "vision_checks.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


@pytest.mark.asyncio
async def test_visual_check_validates_schema_and_assertions(tmp_path):
    prompt = tmp_path / "prompt.md"
    prompt.write_text("inspect", encoding="utf-8")
    schema = ROOT / "config/visual_check_schemas/example_garage.schema.json"
    image = ROOT / "test/fixtures/visual_check/synthetic_garage_after.jpg"
    ground_truth = json.loads((ROOT / "test/fixtures/visual_check/synthetic_garage_after.ground_truth.json").read_text())
    config_path = write_config(tmp_path, schema, prompt, image)

    service = VisualCheckService(str(config_path))

    with patch.object(service, "_ensure_lmstudio"), patch.object(service, "_fetch_snapshot") as snapshot, patch.object(service, "_call_lmstudio") as call:
        snapshot.return_value.content = image.read_bytes()
        snapshot.return_value.mime_type = "image/jpeg"
        snapshot.return_value.source = {"type": "http_snapshot", "url": "http://example.test/snapshot.svg"}
        call.return_value = {"choices": [{"message": {"content": json.dumps(ground_truth)}}]}

        result = await service.run_check("garage")

    assert result["status"] == "ok"
    assert result["result"]["overall"]["all_visible_doors_closed"] is True
    assert result["assertions"][0]["passed"] is True
    assert Path(result["artifacts"]["image_path"]).exists()


@pytest.mark.asyncio
async def test_visual_check_retries_invalid_json(tmp_path):
    prompt = tmp_path / "prompt.md"
    prompt.write_text("inspect", encoding="utf-8")
    schema = ROOT / "config/visual_check_schemas/example_garage.schema.json"
    image = ROOT / "test/fixtures/visual_check/synthetic_garage_after.jpg"
    ground_truth = json.loads((ROOT / "test/fixtures/visual_check/synthetic_garage_after.ground_truth.json").read_text())
    config_path = write_config(tmp_path, schema, prompt, image)
    service = VisualCheckService(str(config_path))

    with patch.object(service, "_ensure_lmstudio"), patch.object(service, "_fetch_snapshot") as snapshot, patch.object(service, "_call_lmstudio") as call:
        snapshot.return_value.content = image.read_bytes()
        snapshot.return_value.mime_type = "image/jpeg"
        snapshot.return_value.source = {"type": "http_snapshot", "url": "http://example.test/snapshot.svg"}
        call.side_effect = [
            {"choices": [{"message": {"content": "not json"}}]},
            {"choices": [{"message": {"content": json.dumps(ground_truth)}}]},
        ]

        result = await service.run_check("garage")

    assert result["status"] == "ok"
    assert call.call_count == 2
