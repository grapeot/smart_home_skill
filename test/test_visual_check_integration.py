import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from fastapi.testclient import TestClient

import api.visual_check as visual_check_api
from main import app
from services.visual_check_service import VisualCheckService


ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)


def write_camera_visual_check_config(tmp_path: Path) -> Path:
    config = {
        'lmstudio': {'api_base': 'http://127.0.0.1:1234/v1', 'model': 'test-model'},
        'artifact_dir': str(tmp_path / 'artifacts'),
        'retries': 0,
        'checks': {
            'garage': {
                'group': 'e2e-safe',
                'source': {'type': 'camera_snapshot', 'camera_id': 'garage'},
                'prompt_file': str(tmp_path / 'prompt.md'),
                'schema_file': str(ROOT / 'config/visual_check_schemas/example_garage.schema.json'),
            }
        },
    }
    (tmp_path / 'prompt.md').write_text('inspect garage', encoding='utf-8')
    path = tmp_path / 'vision_checks.yaml'
    path.write_text(yaml.safe_dump(config), encoding='utf-8')
    return path


@pytest.mark.asyncio
async def test_visual_check_api_runs_camera_snapshot_without_device_actions(tmp_path, monkeypatch):
    service = VisualCheckService(str(write_camera_visual_check_config(tmp_path)))
    monkeypatch.setattr(visual_check_api, 'visual_check_service', service)
    ground_truth = json.loads((ROOT / 'test/fixtures/visual_check/synthetic_garage_after.ground_truth.json').read_text())
    image = (ROOT / 'test/fixtures/visual_check/synthetic_garage_after.jpg').read_bytes()

    with patch.object(service, '_ensure_lmstudio'), patch.object(service, '_call_lmstudio') as call, patch('services.camera_service.camera_service.get_snapshot') as snapshot:
        snapshot.return_value = (image, None)
        call.return_value = {'choices': [{'message': {'content': json.dumps(ground_truth)}}]}

        response = client.post('/api/visual-checks/garage/run')

    assert response.status_code == 200
    data = response.json()
    assert data['schema_version'] == 'smart_home.visual_check_result.v1'
    assert data['check_id'] == 'garage'
    assert data['status'] == 'ok'
    assert data['source'] == {'type': 'camera_snapshot', 'camera_id': 'garage'}
    snapshot.assert_called_once_with('garage')
    call.assert_called_once()
