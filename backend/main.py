import argparse
import os

from core.config_loader import load_config
from core.persisted_config import load_persisted_camera_config
from pipeline import process_video_from_config


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default=os.getenv("ROADLENS_CONFIG", "configs/default.yaml"),
        help="Path to RoadLens YAML config.",
    )
    parser.add_argument(
        "--camera-id",
        type=int,
        default=(
            int(os.environ["ROADLENS_CAMERA_ID"])
            if os.getenv("ROADLENS_CAMERA_ID")
            else None
        ),
        help="Database camera ID. Overrides --config when provided.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    config = (
        load_persisted_camera_config(args.camera_id)
        if args.camera_id is not None
        else load_config(args.config)
    )

    results = process_video_from_config(
        config,
        camera_profile_id=args.camera_id,
    )

    print(
        f"Finished processing {config.camera.source_path}. "
        f"Found {len(results)} detection(s)."
    )

    for result in results:
        detection_id = result.get("detection_id")
        rule_matches = result.get("rule_matches", [])
        rule_summary = ""
        if rule_matches:
            matched_rules = ", ".join(match["rule_name"] for match in rule_matches)
            rule_summary = f" | violation candidate: {matched_rules}"

        print(
            f"Detection {detection_id or result['frame_index']}: "
            f"{result['vehicle_class']} ({result['vehicle_confidence']:.2%}) | "
            f"{result['plate_text']} at {result['coords']}"
            f"{rule_summary}"
        )


if __name__ == "__main__":
    main()
