from core.config_loader import load_config
from core.config_writer import save_config


def test_save_and_reload_config(tmp_path):
    config = load_config("configs/default.yaml")
    output_path = tmp_path / "saved.yaml"

    save_config(config, output_path)
    reloaded = load_config(output_path)

    assert reloaded.camera.id == config.camera.id
    assert reloaded.models.plate_detector == config.models.plate_detector
    assert reloaded.zones[0].enabled == config.zones[0].enabled
