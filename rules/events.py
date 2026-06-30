from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from scene.geometry import bbox_center, bbox_intersects_polygon, point_in_polygon
from scene.runtime_zone import RuntimeZone

VehicleDetectionTuple = tuple[str, float, float, float, float, float]
BBox = tuple[float, float, float, float]


@dataclass(frozen=True)
class VehicleZoneEvent:
    event: str
    frame_number: int
    timestamp_seconds: float | None
    vehicle_index: int
    vehicle_class: str
    vehicle_confidence: float
    vehicle_bbox: BBox
    zone_id: str
    zone_type: str
    zone_name: str


def _offset_bbox(
    bbox: BBox,
    bbox_offset: tuple[float, float],
) -> BBox:
    offset_x, offset_y = bbox_offset
    x1, y1, x2, y2 = bbox
    return (
        offset_x + x1,
        offset_y + y1,
        offset_x + x2,
        offset_y + y2,
    )


def _build_event(
    event: str,
    frame_number: int,
    timestamp_seconds: float | None,
    vehicle_index: int,
    vehicle_class: str,
    vehicle_confidence: float,
    vehicle_bbox: BBox,
    zone: RuntimeZone,
) -> VehicleZoneEvent:
    return VehicleZoneEvent(
        event=event,
        frame_number=frame_number,
        timestamp_seconds=timestamp_seconds,
        vehicle_index=vehicle_index,
        vehicle_class=vehicle_class,
        vehicle_confidence=vehicle_confidence,
        vehicle_bbox=vehicle_bbox,
        zone_id=zone.id,
        zone_type=zone.type,
        zone_name=zone.name,
    )


def generate_vehicle_zone_events(
    vehicles: Iterable[VehicleDetectionTuple],
    zones: list[RuntimeZone],
    frame_number: int,
    timestamp_seconds: float | None,
    bbox_offset: tuple[float, float] = (0, 0),
) -> list[VehicleZoneEvent]:
    events = []

    for vehicle_index, vehicle in enumerate(vehicles, start=1):
        vehicle_class, vehicle_confidence, x1, y1, x2, y2 = vehicle
        vehicle_bbox = _offset_bbox((x1, y1, x2, y2), bbox_offset)

        for zone in zones:
            if not zone.enabled:
                continue

            if bbox_intersects_polygon(vehicle_bbox, zone.points_pixel):
                events.append(
                    _build_event(
                        "vehicle_intersects_zone",
                        frame_number,
                        timestamp_seconds,
                        vehicle_index,
                        vehicle_class,
                        vehicle_confidence,
                        vehicle_bbox,
                        zone,
                    )
                )

            if point_in_polygon(bbox_center(vehicle_bbox), zone.points_pixel):
                events.append(
                    _build_event(
                        "vehicle_center_inside_zone",
                        frame_number,
                        timestamp_seconds,
                        vehicle_index,
                        vehicle_class,
                        vehicle_confidence,
                        vehicle_bbox,
                        zone,
                    )
                )

    return events
