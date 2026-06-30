from pathlib import Path

from core.config_loader import load_config


def test_load_default_config():
    config = load_config(Path("configs/default.yaml"))

    assert config.camera.id == "demo_camera_01"
    assert config.models.ocr_engine == "paddleocr"
    assert config.frame_selection.motion_threshold > 0
