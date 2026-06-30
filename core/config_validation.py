from core.config_schema import ZoneConfig
from scene.geometry import normalized_points_to_pixels, polygon_to_bounding_rect


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
