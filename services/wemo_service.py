import logging
import os
from typing import Callable, Dict, Optional
from datetime import datetime

import pywemo
import yaml
from pathlib import Path

logger = logging.getLogger(__name__)


def _as_switch_state(state: object) -> Optional[bool]:
    return None if state is None else bool(state)


class WemoService:
    def __init__(self):
        self.devices: Dict[str, pywemo.WeMoDevice] = {}
        self.config_file = os.getenv("WEMO_CONFIG_FILE", "config/wemo_config.yaml")
    
    def init_devices(self) -> bool:
        config_path = Path(self.config_file)
        
        if not config_path.exists():
            logger.warning(f"Wemo config file not found: {self.config_file}")
            return False

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            devices_config = config.get('devices', [])
            logger.info(f"Loading {len(devices_config)} Wemo devices from config")
            
            for device_config in devices_config:
                name = device_config.get('name', '')
                host = device_config.get('host', '')
                port = device_config.get('port', 49153)
                
                if not name or not host:
                    continue
                
                try:
                    url = pywemo.setup_url_for_address(host, port)
                    device = pywemo.device_from_description(url)
                    self.devices[name.lower()] = device
                    logger.info(f"Registered Wemo device: {name} ({host}:{port})")
                except Exception as e:
                    logger.warning(f"Failed to connect to {name}: {e}")
            
            return len(self.devices) > 0
        except Exception as e:
            logger.error(f"Error initializing Wemo devices: {e}")
            return False

    def refresh_device(self, name: str) -> Optional[pywemo.WeMoDevice]:
        """Rediscover a Wemo device by name and update the local cache/config."""
        target_name = name.lower()

        try:
            devices = pywemo.discover_devices()
        except Exception as e:
            logger.warning(f"Failed to discover Wemo devices while refreshing {name}: {e}")
            return None

        for device in devices:
            discovered_name = getattr(device, "name", "").lower()
            if discovered_name != target_name:
                continue

            self.devices[target_name] = device
            self._update_config_device(device)
            logger.info(
                "Rediscovered Wemo device: %s (%s:%s)",
                getattr(device, "name", name),
                getattr(device, "host", "unknown"),
                getattr(device, "port", "unknown"),
            )
            return device

        logger.warning(f"Wemo device not found during rediscovery: {name}")
        return None

    def _update_config_device(self, device: pywemo.WeMoDevice) -> None:
        config_path = Path(self.config_file)
        if not config_path.exists():
            return

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}

            devices_config = config.get('devices', [])
            device_name = getattr(device, "name", "").lower()
            updated = False

            for device_config in devices_config:
                if device_config.get('name', '').lower() != device_name:
                    continue
                device_config['host'] = device.host
                device_config['port'] = device.port
                updated = True
                break

            if not updated:
                return

            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        except Exception as e:
            logger.warning(f"Failed to update Wemo config for {getattr(device, 'name', 'unknown')}: {e}")

    def _run_with_refresh(
        self,
        name: str,
        action: str,
        operation: Callable[[pywemo.WeMoDevice], dict],
    ) -> dict:
        device = self.get_device(name)
        if not device:
            device = self.refresh_device(name)
            if not device:
                return {"status": "error", "message": f"Device {name} not found"}

        try:
            return operation(device)
        except Exception as first_error:
            logger.warning(f"Wemo {action} failed for {name}, rediscovering: {first_error}")

        refreshed_device = self.refresh_device(name)
        if not refreshed_device:
            return {"status": "error", "message": f"{action} failed for {name}; rediscovery did not find device"}

        try:
            result = operation(refreshed_device)
            result["rediscovered"] = True
            return result
        except Exception as second_error:
            return {"status": "error", "message": str(second_error)}
    
    def get_all_status(self) -> dict:
        result = {}
        for name, device in list(self.devices.items()):
            try:
                state = device.get_state()
                result[name] = {
                    "name": name,
                    "is_on": _as_switch_state(state),
                    "host": device.host
                }
            except Exception as e:
                refreshed_device = self.refresh_device(name)
                if refreshed_device:
                    try:
                        state = refreshed_device.get_state()
                        result[name] = {
                            "name": name,
                            "is_on": _as_switch_state(state),
                            "host": refreshed_device.host,
                            "rediscovered": True,
                        }
                        continue
                    except Exception as refresh_error:
                        e = refresh_error

                result[name] = {
                    "name": name,
                    "is_on": None,
                    "error": str(e)
                }
        return result
    
    def get_device(self, name: str) -> Optional[pywemo.WeMoDevice]:
        return self.devices.get(name.lower())
    
    def turn_on(self, name: str) -> dict:
        def operation(device: pywemo.WeMoDevice) -> dict:
            device.on()
            return {
                "status": "success",
                "device": name,
                "action": "on",
                "is_on": device.get_state(),
                "timestamp": datetime.now().isoformat()
            }

        return self._run_with_refresh(name, "on", operation)
    
    def turn_off(self, name: str) -> dict:
        def operation(device: pywemo.WeMoDevice) -> dict:
            device.off()
            return {
                "status": "success",
                "device": name,
                "action": "off",
                "is_on": device.get_state(),
                "timestamp": datetime.now().isoformat()
            }

        return self._run_with_refresh(name, "off", operation)
    
    def toggle(self, name: str) -> dict:
        def operation(device: pywemo.WeMoDevice) -> dict:
            current_state = device.get_state()
            if current_state:
                device.off()
            else:
                device.on()
            
            return {
                "status": "success",
                "device": name,
                "action": "toggle",
                "is_on": device.get_state(),
                "previous_state": current_state,
                "timestamp": datetime.now().isoformat()
            }

        return self._run_with_refresh(name, "toggle", operation)

wemo_service = WemoService()
