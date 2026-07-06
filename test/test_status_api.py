from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


@patch('api.status._safe_hue_status')
@patch('api.status._safe_ring_status')
@patch('api.status._safe_garage_status')
@patch('api.status.rinnai_service.get_status', new_callable=AsyncMock)
@patch('api.status.wemo_service.get_all_status')
def test_status_fast_subset_does_not_wait_for_wemo(mock_wemo, mock_rinnai, mock_garage, mock_ring, mock_hue):
    mock_hue.return_value = {'name': 'Baby room', 'is_on': True, 'brightness': 128}
    mock_rinnai.return_value = {'is_online': True, 'set_temperature': 120}
    mock_garage.return_value = {'door_count': 2, 'available': True}

    response = client.get('/api/status?devices=hue,rinnai,garage')

    assert response.status_code == 200
    assert response.json().keys() == {'hue', 'rinnai', 'garage'}
    mock_wemo.assert_not_called()
    mock_ring.assert_not_called()


@patch('api.status._safe_hue_status')
@patch('api.status._safe_ring_status')
@patch('api.status._safe_garage_status')
@patch('api.status.rinnai_service.get_status', new_callable=AsyncMock)
@patch('api.status.wemo_service.get_all_status')
def test_status_wemo_subset_does_not_query_fast_devices(mock_wemo, mock_rinnai, mock_garage, mock_ring, mock_hue):
    mock_wemo.return_value = {'coffee': {'name': 'coffee', 'is_on': True}}

    response = client.get('/api/status?devices=wemo')

    assert response.status_code == 200
    assert response.json() == {'wemo': {'coffee': {'name': 'coffee', 'is_on': True}}}
    mock_hue.assert_not_called()
    mock_rinnai.assert_not_called()
    mock_garage.assert_not_called()
    mock_ring.assert_not_called()


@patch('api.status._safe_ring_status')
def test_status_ring_subset(mock_ring):
    mock_ring.return_value = {
        'configured': True,
        'locations': [
            {
                'name': 'Home',
                'devices': [
                    {'name': 'Back Door', 'device_type': 'contact_sensor', 'faulted': False}
                ],
            }
        ],
    }

    response = client.get('/api/status?devices=ring')

    assert response.status_code == 200
    assert response.json() == {
        'ring': {
            'configured': True,
            'locations': [
                {
                    'name': 'Home',
                    'devices': [
                        {'name': 'Back Door', 'device_type': 'contact_sensor', 'faulted': False}
                    ],
                }
            ],
        }
    }
