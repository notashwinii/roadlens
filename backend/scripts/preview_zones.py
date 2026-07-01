from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config_loader import load_config  # noqa: E402
from scene.scene_builder import build_scene_from_config  # noqa: E402
from scene.zone_renderer import draw_zones  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render configured semantic zones on the first video frame.",
    )
    parser.add_argument("--config", default="configs/sample_camera.yaml")
    parser.add_argument("--output", default="outputs/zone_preview.jpg")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    scene = build_scene_from_config(config)

    preview = draw_zones(scene.first_frame, scene.zones)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not cv2.imwrite(str(output_path), preview):
        raise RuntimeError(f"Could not write zone preview to {output_path}")

    print(f"Saved zone preview to {output_path}")
    print(f"Frame: {scene.frame_width}x{scene.frame_height}")
    print(f"Zones: {len(scene.zones)}")


if __name__ == "__main__":
    main()
