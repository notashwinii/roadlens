from pathlib import Path

import cv2


def write_image_artifact(
    image,
    output_dir: str,
    camera_id: str,
    video_id: int,
    event_id: int,
    artifact_type: str,
) -> tuple[str, int, int]:
    event_dir = (
        Path(output_dir)
        / str(camera_id)
        / f"video_{video_id:06d}"
        / f"event_{event_id:06d}"
    )
    event_dir.mkdir(parents=True, exist_ok=True)

    path = event_dir / f"{artifact_type}.jpg"
    if not cv2.imwrite(str(path), image):
        raise RuntimeError(f"Could not write evidence artifact: {path}")

    height, width = image.shape[:2]
    return str(path), int(width), int(height)
