from core.config_schema import ZoneConfig
from core.config_validation import (
    normalized_points_to_pixels,
    polygon_to_bounding_rect,
    zone_to_roi,
)


def test_normalized_points_to_pixels():
    points = [(0.5, 0.5), (1.0, 1.0)]
    pixels = normalized_points_to_pixels(points, 1920, 1080)

    assert pixels == [(960, 540), (1920, 1080)]


def test_polygon_to_bounding_rect():
    points = [(10, 20), (90, 25), (80, 70), (15, 75)]

    assert polygon_to_bounding_rect(points) == (10, 20, 80, 55)


def test_zone_to_roi_uses_reference_resolution():
    zone = ZoneConfig(
        id="roi",
        name="ROI",
        type="detection_roi",
        shape="rectangle",
        points_normalized=[
            (0.10, 0.25),
            (0.90, 0.25),
            (0.90, 0.90),
            (0.10, 0.90),
        ],
    )

    assert zone_to_roi(zone, (1920, 1080)) == (192, 270, 1536, 702)
