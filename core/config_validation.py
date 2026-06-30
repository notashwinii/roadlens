from core.config_schema import ZoneConfig


def normalized_points_to_pixels(
    points: list[tuple[float, float]],
    frame_width: int,
    frame_height: int,
) -> list[tuple[int, int]]:
    return [(int(x * frame_width), int(y * frame_height)) for x, y in points]


def polygon_to_bounding_rect(
    points: list[tuple[int, int]],
) -> tuple[int, int, int, int]:
    xs = [x for x, _ in points]
    ys = [y for _, y in points]

    x_min = min(xs)
    y_min = min(ys)
    x_max = max(xs)
    y_max = max(ys)

    return (x_min, y_min, x_max - x_min, y_max - y_min)


def zone_to_roi(
    zone: ZoneConfig,
    reference_resolution: tuple[int, int],
) -> tuple[int, int, int, int]:
    frame_width, frame_height = reference_resolution
    pixel_points = normalized_points_to_pixels(
        zone.points_normalized,
        frame_width,
        frame_height,
    )
    return polygon_to_bounding_rect(pixel_points)
