from __future__ import annotations

import cv2
import numpy as np


def normalized_points_to_pixels(
    points: list[tuple[float, float]],
    frame_width: int,
    frame_height: int,
) -> list[tuple[int, int]]:
    return [(int(x * frame_width), int(y * frame_height)) for x, y in points]


def polygon_to_bounding_rect(
    points: list[tuple[int, int]],
) -> tuple[int, int, int, int]:
    if not points:
        raise ValueError("Cannot build a bounding rectangle for an empty polygon.")

    xs = [x for x, _ in points]
    ys = [y for _, y in points]

    x_min = min(xs)
    y_min = min(ys)
    x_max = max(xs)
    y_max = max(ys)

    return (x_min, y_min, x_max - x_min, y_max - y_min)


def polygon_mask(
    points: list[tuple[int, int]],
    frame_width: int,
    frame_height: int,
) -> np.ndarray:
    mask = np.zeros((frame_height, frame_width), dtype=np.uint8)
    polygon = np.array(points, dtype=np.int32)
    cv2.fillPoly(mask, [polygon], 255)
    return mask


def bbox_center(
    bbox: tuple[float, float, float, float],
) -> tuple[float, float]:
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) / 2, (y1 + y2) / 2)


def point_in_polygon(
    point: tuple[float, float],
    polygon_points: list[tuple[int, int]],
) -> bool:
    if len(polygon_points) < 3:
        return False

    contour = np.array(polygon_points, dtype=np.int32)
    return cv2.pointPolygonTest(contour, point, False) >= 0


def bbox_intersects_polygon(
    bbox: tuple[float, float, float, float],
    polygon_points: list[tuple[int, int]],
) -> bool:
    x1, y1, x2, y2 = bbox
    test_points = [
        bbox_center(bbox),
        (x1, y1),
        (x2, y1),
        (x2, y2),
        (x1, y2),
    ]
    return any(point_in_polygon(point, polygon_points) for point in test_points)
