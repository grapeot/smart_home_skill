import os

import pytest
import requests


pytestmark = [
    pytest.mark.live_e2e,
    pytest.mark.skipif(
        os.getenv('SMART_HOME_RUN_REAL_E2E') != '1',
        reason='Real visual-check E2E is skipped by default. Set SMART_HOME_RUN_REAL_E2E=1 to run.',
    ),
]


def test_real_garage_visual_check_returns_json_without_triggering_garage():
    base_url = os.getenv('SMART_HOME_REAL_BASE_URL', 'http://localhost:7999').rstrip('/')
    check_id = os.getenv('SMART_HOME_REAL_VISUAL_CHECK_ID', 'garage')

    response = requests.post(f'{base_url}/api/visual-checks/{check_id}/run', timeout=240)

    assert response.status_code == 200
    data = response.json()
    assert data['schema_version'] == 'smart_home.visual_check_result.v1'
    assert data['check_id'] == check_id
    assert data['status'] in {'ok', 'problem', 'failed'}
    assert isinstance(data.get('source'), dict)
    assert isinstance(data.get('artifacts'), dict)
