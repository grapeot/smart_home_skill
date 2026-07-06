import os
from pathlib import Path
from typing import Any, Optional

import yaml


class GarageConfig:
    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file or os.getenv("GARAGE_CONFIG_FILE", "config/garage_config.yaml")

    def load(self) -> dict[str, Any]:
        path = Path(self.config_file)
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def get_doors(self, door_count: int) -> list[dict[str, Any]]:
        configured = self.load().get("doors", []) or []
        labels = {
            int(item["index"]): item.get("label")
            for item in configured
            if isinstance(item, dict) and item.get("index") is not None and item.get("label")
        }
        return [
            {"index": index, "label": labels.get(index, f"Garage door {index}")}
            for index in range(1, door_count + 1)
        ]


garage_config = GarageConfig()
