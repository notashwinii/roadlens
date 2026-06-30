import numpy as np

from core.config_schema import ZoneConfig
from scene.runtime_zone import build_runtime_zone
from scene.zone_renderer import draw_zones


def test_draw_zones_returns_overlay_copy():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    zone = build_runtime_zone(
        ZoneConfig(
            id="roi",
            name="ROI",
            type="detection_roi",
            shape="rectangle",
            points_normalized=[
                (0.1, 0.1),
                (0.9, 0.1),
                (0.9, 0.9),
                (0.1, 0.9),
            ],
        ),
        100,
        100,
    )

    output = draw_zones(frame, [zone])

    assert output is not frame
    assert output.shape == frame.shape
    assert np.count_nonzero(output) > 0
    assert np.count_nonzero(frame) == 0
