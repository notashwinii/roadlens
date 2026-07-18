from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from core.config_schema import RoadLensConfig

BACKEND_ROOT = Path(__file__).resolve().parents[1]


class CameraSourceError(RuntimeError):
    pass


def capture_source_from_config(
    config: RoadLensConfig,
    *,
    backend_root: Path = BACKEND_ROOT,
) -> str | int:
    source_path = config.camera.source_path.strip()

    if config.camera.source_type == "webcam":
        try:
            return int(source_path)
        except ValueError as error:
            raise CameraSourceError("Webcam source must be a device index.") from error

    if config.camera.source_type == "rtsp":
        if not source_path.lower().startswith(("rtsp://", "rtsps://")):
            raise CameraSourceError("RTSP source must use an rtsp:// URL.")
        return source_path

    candidate = Path(source_path)
    if not candidate.is_absolute():
        candidate = backend_root / candidate
    resolved = candidate.resolve()
    root = backend_root.resolve()
    if not resolved.is_relative_to(root):
        raise CameraSourceError("Video source must be stored inside RoadLens.")
    return str(resolved)


def read_camera_frame(
    config: RoadLensConfig,
    *,
    backend_root: Path = BACKEND_ROOT,
) -> np.ndarray:
    source = capture_source_from_config(config, backend_root=backend_root)
    capture = cv2.VideoCapture(source)
    try:
        if hasattr(capture, "set"):
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        ok, frame = capture.read()
        if not ok or frame is None:
            raise CameraSourceError("Could not read a frame from this source.")
        return frame
    finally:
        capture.release()


def encode_snapshot(frame: np.ndarray, *, max_width: int = 1600) -> bytes:
    height, width = frame.shape[:2]
    if width > max_width:
        scale = max_width / width
        frame = cv2.resize(
            frame,
            (max_width, max(1, int(height * scale))),
            interpolation=cv2.INTER_AREA,
        )
    ok, encoded = cv2.imencode(
        ".jpg",
        frame,
        [int(cv2.IMWRITE_JPEG_QUALITY), 86],
    )
    if not ok:
        raise CameraSourceError("Could not encode the camera snapshot.")
    return encoded.tobytes()
