import pytest

from services.notification_service import NotificationService


def test_recipients_support_comma_and_semicolon(monkeypatch):
    monkeypatch.setenv("GARAGE_NOTIFY_RECIPIENTS", "a@example.com; b@example.com, c@example.com")

    service = NotificationService()

    assert service._recipients() == ["a@example.com", "b@example.com", "c@example.com"]


def test_is_configured_requires_all_settings(monkeypatch):
    service = NotificationService()
    monkeypatch.setenv("GARAGE_NOTIFY_ENABLED", "true")
    monkeypatch.setenv("RESEND_API_KEY", "key")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "Smart Home <noreply@example.com>")
    monkeypatch.setenv("GARAGE_NOTIFY_RECIPIENTS", "a@example.com")

    assert service.is_configured() is True

    monkeypatch.delenv("GARAGE_NOTIFY_RECIPIENTS")
    assert service.is_configured() is False


def test_send_garage_toggle_noops_when_not_configured(monkeypatch):
    monkeypatch.delenv("GARAGE_NOTIFY_ENABLED", raising=False)

    service = NotificationService()

    assert service.send_garage_toggle({"door": 1}) == {
        "enabled": False,
        "sent": False,
        "reason": "not_configured",
    }


def test_send_garage_toggle_uses_resend(monkeypatch):
    monkeypatch.setenv("GARAGE_NOTIFY_ENABLED", "true")
    monkeypatch.setenv("RESEND_API_KEY", "test-api-key")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "Smart Home <noreply@example.com>")
    monkeypatch.setenv("GARAGE_NOTIFY_RECIPIENTS", "outlook@example.com; pushover@example.com")

    calls = []

    class FakeResponse:
        content = b'{"id":"email-123"}'

        def raise_for_status(self):
            return None

        def json(self):
            return {"id": "email-123"}

    def fake_post(url, headers, json, timeout):
        calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setattr("services.notification_service.requests.post", fake_post)
    service = NotificationService()

    result = service.send_garage_toggle(
        {
            "door": 1,
            "target_open": False,
            "timestamp": "2026-06-25T18:00:00",
        }
    )

    assert result == {"enabled": True, "sent": True, "recipients": 2, "resend_id": "email-123"}
    assert calls[0]["url"] == "https://api.resend.com/emails"
    assert calls[0]["headers"]["Authorization"] == "Bearer test-api-key"
    assert calls[0]["json"]["to"] == ["outlook@example.com", "pushover@example.com"]
    assert "Garage door 1" in calls[0]["json"]["subject"]


@pytest.mark.asyncio
async def test_meross_toggle_includes_notification(monkeypatch):
    from services.meross_service import MerossService

    class DummyDevice:
        uuid = "device-uuid"
        channels = [{}, {}]

        def get_is_open(self, door_index):
            return True

    service = MerossService()
    service.device = DummyDevice()
    service._local_ip = "192.0.2.10"
    service._key = "test-key"
    service._connected = True

    def fake_local_request(namespace, method, payload):
        if method == "GET":
            return {"state": {"channel": 1, "open": 1}}
        return {"state": {"channel": 1, "open": 1, "execute": 1}}

    monkeypatch.setattr(service, "_local_request", fake_local_request)
    monkeypatch.setattr(
        "services.meross_service.notification_service.send_garage_toggle",
        lambda result: {"enabled": True, "sent": True},
    )

    result = await service.toggle_door(1)

    assert result["notification"] == {"enabled": True, "sent": True}
