import yaml
from unittest.mock import MagicMock

from services.wemo_schedule import WemoScheduleManager


def make_manager(tmp_path):
    config_path = tmp_path / "wemo_config.yaml"
    config_path.write_text(
        yaml.dump(
            {
                "devices": [{"name": "Coffee", "host": "192.0.2.10", "port": 49153}],
                "schedule": {"tasks": []},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    manager = WemoScheduleManager(str(config_path))
    return manager


def test_execute_task_delegates_to_wemo_service(tmp_path, monkeypatch):
    manager = make_manager(tmp_path)
    pinned_device = MagicMock(name="pinned")
    manager.register_device("Coffee", pinned_device)

    calls = []
    monkeypatch.setattr(
        "services.wemo_service.wemo_service.turn_on",
        lambda name: calls.append(("on", name)) or {"status": "success", "device": name, "action": "on"},
    )
    monkeypatch.setattr(
        "services.wemo_service.wemo_service.turn_off",
        lambda name: calls.append(("off", name)) or {"status": "success", "device": name, "action": "off"},
    )

    manager.execute_task("Coffee", "off")
    manager.execute_task("Coffee", "on")

    assert calls == [("off", "Coffee"), ("on", "Coffee")]
    pinned_device.on.assert_not_called()
    pinned_device.off.assert_not_called()


def test_execute_task_works_without_startup_registration(tmp_path, monkeypatch):
    manager = make_manager(tmp_path)

    result = {"status": "success", "device": "Coffee", "action": "off"}
    monkeypatch.setattr("services.wemo_service.wemo_service.turn_off", lambda name: result)

    manager.execute_task("Coffee", "off")

    assert result["status"] == "success"


def test_execute_task_ignores_unknown_action(tmp_path, monkeypatch):
    manager = make_manager(tmp_path)
    calls = []
    monkeypatch.setattr(
        "services.wemo_service.wemo_service.turn_on",
        lambda name: calls.append(("on", name)),
    )
    monkeypatch.setattr(
        "services.wemo_service.wemo_service.turn_off",
        lambda name: calls.append(("off", name)),
    )

    manager.execute_task("Coffee", "warp")

    assert calls == []
