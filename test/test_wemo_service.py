import yaml

from services.wemo_service import WemoService


class FakeWemoDevice:
    def __init__(self, name, host, port, state=0, fail_on=None):
        self.name = name
        self.host = host
        self.port = port
        self.state = state
        self.fail_on = set(fail_on or [])

    def on(self):
        if "on" in self.fail_on:
            raise TimeoutError("old endpoint timed out")
        self.state = 1

    def off(self):
        if "off" in self.fail_on:
            raise TimeoutError("old endpoint timed out")
        self.state = 0

    def get_state(self):
        if "get_state" in self.fail_on:
            raise TimeoutError("old endpoint timed out")
        return self.state


def test_turn_on_rediscoveries_device_and_updates_config(tmp_path, monkeypatch):
    config_path = tmp_path / "wemo_config.yaml"
    config_path.write_text(
        yaml.dump(
            {
                "devices": [
                    {
                        "name": "Coffee",
                        "host": "192.0.2.10",
                        "port": 49153,
                        "description": "coffee switch",
                    }
                ],
                "schedule": {"tasks": []},
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    stale_device = FakeWemoDevice("Coffee", "192.0.2.10", 49153, fail_on={"on"})
    discovered_device = FakeWemoDevice("Coffee", "192.0.2.10", 49154)

    service = WemoService()
    service.config_file = str(config_path)
    service.devices = {"coffee": stale_device}

    monkeypatch.setattr("services.wemo_service.pywemo.discover_devices", lambda: [discovered_device])

    result = service.turn_on("coffee")

    assert result["status"] == "success"
    assert result["is_on"] == 1
    assert result["rediscovered"] is True
    assert service.devices["coffee"] is discovered_device

    updated_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert updated_config["devices"][0]["host"] == "192.0.2.10"
    assert updated_config["devices"][0]["port"] == 49154
    assert updated_config["devices"][0]["description"] == "coffee switch"


def test_init_devices_loads_configured_devices(tmp_path, monkeypatch):
    config_path = tmp_path / "wemo_config.yaml"
    config_path.write_text(
        yaml.dump(
            {
                "devices": [
                    {"name": "Coffee", "host": "192.0.2.10", "port": 49154}
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    device = FakeWemoDevice("Coffee", "192.0.2.10", 49154)
    monkeypatch.setattr(
        "services.wemo_service.pywemo.setup_url_for_address",
        lambda host, port: f"http://{host}:{port}/setup.xml",
    )
    monkeypatch.setattr(
        "services.wemo_service.pywemo.device_from_description",
        lambda url: device,
    )

    service = WemoService()
    service.config_file = str(config_path)

    assert service.init_devices() is True
    assert service.devices["coffee"] is device


def test_get_all_status_refreshes_failed_device(monkeypatch):
    stale_device = FakeWemoDevice("Coffee", "192.0.2.10", 49153, fail_on={"get_state"})
    discovered_device = FakeWemoDevice("Coffee", "192.0.2.10", 49154, state=1)

    service = WemoService()
    service.config_file = "/tmp/nonexistent_wemo_config.yaml"
    service.devices = {"coffee": stale_device}

    monkeypatch.setattr("services.wemo_service.pywemo.discover_devices", lambda: [discovered_device])

    result = service.get_all_status()

    assert result["coffee"]["is_on"] == 1
    assert result["coffee"]["host"] == "192.0.2.10"
    assert result["coffee"]["rediscovered"] is True


def test_get_all_status_normalizes_non_boolean_state():
    service = WemoService()
    service.devices = {"veggie": FakeWemoDevice("Veggie", "192.0.2.11", 49153, state=8)}

    result = service.get_all_status()

    assert result["veggie"]["is_on"] is True
