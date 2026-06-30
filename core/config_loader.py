from pathlib import Path

import yaml

from core.config_schema import RoadLensConfig


def load_config(path: str | Path) -> RoadLensConfig:
    config_path = Path(path)

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as config_file:
        raw_config = yaml.safe_load(config_file)

    if raw_config is None:
        raise ValueError(f"Config file is empty: {config_path}")

    return RoadLensConfig.model_validate(raw_config)
