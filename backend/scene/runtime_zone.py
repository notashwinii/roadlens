from __future__ import annotations

from dataclasses import dataclass

from core.config_schema import ZoneConfig
from scene.geometry import normalized_points_to_pixels, polygon_to_bounding_rect


@dataclass(frozen=True)
class RuntimeZone:
    id: str
    name: str
    type: str
    shape: str
    enabled: bool
    points_normalized: list[tuple[float, float]]
    points_pixel: list[tuple[int, int]]
    bounding_rect: tuple[int, int, int, int]
    description: str | None = None


def build_runtime_zone(
    zone: ZoneConfig,
    frame_width: int,
    frame_height: int,
) -> RuntimeZone:
    points_pixel = normalized_points_to_pixels(
        zone.points_normalized,
        frame_width,
        frame_height,
    )
    return RuntimeZone(
        id=zone.id,
        name=zone.name,
        type=zone.type,
        shape=zone.shape,
        enabled=zone.enabled,
        points_normalized=zone.points_normalized,
        points_pixel=points_pixel,
        bounding_rect=polygon_to_bounding_rect(points_pixel),
        description=zone.description,
    )
