import base64
from pathlib import Path

import numpy as np
import pytest

from core.camera_credentials import (
    apply_source_credentials,
    encrypt_source_credentials,
)
from core.camera_source import (
    CameraSourceError,
    capture_source_from_config,
    encode_snapshot,
)
from core.config_schema import CameraConfig, ModelConfig, RoadLensConfig


def camera_config(source_type: str, source_path: str) -> RoadLensConfig:
    return RoadLensConfig(
        camera=CameraConfig(
            id="camera-1",
            name="Camera 1",
            source_type=source_type,
            source_path=source_path,
            reference_resolution=(1920, 1080),
        ),
        models=ModelConfig(
            vehicle_detector="vehicle.pt",
            plate_detector="plate.pt",
            ocr_engine="paddleocr",
        ),
    )


def test_video_sources_resolve_only_inside_backend_root(tmp_path: Path):
    video = tmp_path / "uploads" / "camera.mp4"
    video.parent.mkdir()
    video.write_bytes(b"video")

    source = capture_source_from_config(
        camera_config("video_file", "uploads/camera.mp4"),
        backend_root=tmp_path,
    )

    assert source == str(video.resolve())
    with pytest.raises(CameraSourceError, match="inside RoadLens"):
        capture_source_from_config(
            camera_config("video_file", "../private.mp4"),
            backend_root=tmp_path,
        )


def test_live_sources_are_validated_and_snapshots_are_jpeg(tmp_path: Path):
    assert (
        capture_source_from_config(
            camera_config("rtsp", "rtsp://camera.local/live"),
            backend_root=tmp_path,
        )
        == "rtsp://camera.local/live"
    )
    assert (
        capture_source_from_config(
            camera_config("webcam", "2"),
            backend_root=tmp_path,
        )
        == 2
    )
    with pytest.raises(CameraSourceError, match="rtsp://"):
        capture_source_from_config(
            camera_config("rtsp", "https://camera.local/live"),
            backend_root=tmp_path,
        )

    encoded = encode_snapshot(np.zeros((64, 96, 3), dtype=np.uint8))
    assert encoded.startswith(b"\xff\xd8")
    assert encoded.endswith(b"\xff\xd9")


def test_rtsp_credentials_are_encrypted_and_applied_only_at_runtime(monkeypatch):
    monkeypatch.setenv(
        "ROADLENS_MASTER_KEY",
        base64.urlsafe_b64encode(b"k" * 32).decode("ascii"),
    )
    encrypted = encrypt_source_credentials(
        7,
        username="camera operator",
        password="secret/@pass",
    )
    assert "camera operator" not in encrypted
    assert "secret" not in encrypted

    config = camera_config("rtsp", "rtsp://camera.local:8554/live?profile=main")
    runtime = apply_source_credentials(
        config,
        camera_id=7,
        encrypted_credentials=encrypted,
    )
    assert (
        runtime.camera.source_path
        == "rtsp://camera%20operator:secret%2F%40pass@camera.local:8554/live"
        "?profile=main"
    )
