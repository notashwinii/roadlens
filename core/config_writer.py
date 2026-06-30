from pathlib import Path

import yaml

from core.config_schema import RoadLensConfig


def save_config(config: RoadLensConfig, path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as config_file:
        yaml.safe_dump(
            config.model_dump(mode="json"),
            config_file,
            sort_keys=False,
        )
