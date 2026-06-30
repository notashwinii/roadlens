import numpy as np
import pytest

from scene.geometry import (
    bbox_intersects_polygon,
    normalized_points_to_pixels,
    point_in_polygon,
    polygon_mask,
    polygon_to_bounding_rect,
)


def test_normalized_points_to_pixels():
    assert normalized_points_to_pixels([(0.5, 0.5)], 1920, 1080) == [(960, 540)]


def test_polygon_to_bounding_rect():
    points = [(10, 20), (90, 25), (80, 70), (15, 75)]

    assert polygon_to_bounding_rect(points) == (10, 20, 80, 55)


def test_polygon_to_bounding_rect_rejects_empty_polygon():
    with pytest.raises(ValueError):
        polygon_to_bounding_rect([])


def test_polygon_mask_fills_polygon_area():
    mask = polygon_mask([(1, 1), (8, 1), (8, 8), (1, 8)], 10, 10)

    assert mask.shape == (10, 10)
    assert mask.dtype == np.uint8
    assert mask[4, 4] == 255
    assert mask[0, 0] == 0


def test_point_in_polygon():
    polygon = [(0, 0), (100, 0), (100, 100), (0, 100)]

    assert point_in_polygon((50, 50), polygon)
    assert not point_in_polygon((150, 50), polygon)


def test_bbox_intersects_polygon_by_center():
    polygon = [(0, 0), (100, 0), (100, 100), (0, 100)]
    bbox = (25, 25, 75, 75)

    assert bbox_intersects_polygon(bbox, polygon)
