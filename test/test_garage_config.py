from pathlib import Path

from services.garage_config import GarageConfig


def test_garage_config_returns_default_labels_when_config_missing(tmp_path):
    config = GarageConfig(str(tmp_path / "missing.yaml"))

    assert config.get_doors(2) == [
        {"index": 1, "label": "Garage door 1"},
        {"index": 2, "label": "Garage door 2"},
    ]


def test_garage_config_overrides_labels(tmp_path: Path):
    path = tmp_path / "garage_config.yaml"
    path.write_text(
        """
doors:
  - index: 1
    label: Garage Door Black
  - index: 2
    label: Garage Door White
""".strip(),
        encoding="utf-8",
    )
    config = GarageConfig(str(path))

    assert config.get_doors(2) == [
        {"index": 1, "label": "Garage Door Black"},
        {"index": 2, "label": "Garage Door White"},
    ]
