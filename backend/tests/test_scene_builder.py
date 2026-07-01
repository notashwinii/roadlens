import numpy as np

from core.config_loader import load_config
from scene.scene_builder import (
    build_runtime_zones,
    build_scene_from_config,
    first_detection_roi_from_config,
    get_frame_size,
    runtime_roi_for_video,
)


def test_get_frame_size_returns_width_then_height():
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    assert get_frame_size(frame) == (1280, 720)


def test_build_runtime_zones_from_config_skips_disabled_zones():
    config = load_config("configs/sample_camera.yaml")
    config.zones[0].enabled = False

    zones = build_runtime_zones(config, 1920, 1080)

    assert zones
    assert not any(zone.id == "detection_roi_main" for zone in zones)
    assert all(zone.bounding_rect[2] > 0 for zone in zones)
    assert all(zone.bounding_rect[3] > 0 for zone in zones)


def test_first_detection_roi_from_config_ignores_disabled_roi():
    config = load_config("configs/sample_camera.yaml")

    assert first_detection_roi_from_config(config).id == "detection_roi_main"

    config.zones[0].enabled = False

    assert first_detection_roi_from_config(config) is None


def test_runtime_roi_for_video_uses_actual_frame_size(monkeypatch):
    config = load_config("configs/sample_camera.yaml")

    class FakeCap:
        def read(self):
            return True, np.zeros((720, 1280, 3), dtype=np.uint8)

        def release(self):
            pass

    monkeypatch.setattr("scene.scene_builder.cv2.VideoCapture", lambda _path: FakeCap())

    assert runtime_roi_for_video(config) == (128, 180, 1024, 468)


def test_build_scene_from_config(monkeypatch):
    config = load_config("configs/sample_camera.yaml")

    class FakeCap:
        def read(self):
            return True, np.zeros((720, 1280, 3), dtype=np.uint8)

        def release(self):
            pass

    monkeypatch.setattr("scene.scene_builder.cv2.VideoCapture", lambda _path: FakeCap())

    scene = build_scene_from_config(config)

    assert scene.frame_width == 1280
    assert scene.frame_height == 720
    assert len(scene.zones) == 4
    assert any(zone.type == "detection_roi" for zone in scene.zones)
