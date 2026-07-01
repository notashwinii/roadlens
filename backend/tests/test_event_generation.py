from rules.events import generate_vehicle_zone_events
from scene.runtime_zone import RuntimeZone


def test_generate_vehicle_zone_events_for_intersection_and_center():
    zone = RuntimeZone(
        id="restricted_lane_left",
        name="Restricted Left Lane",
        type="restricted_zone",
        shape="polygon",
        enabled=True,
        points_normalized=[(0, 0), (1, 0), (1, 1), (0, 1)],
        points_pixel=[(10, 10), (110, 10), (110, 110), (10, 110)],
        bounding_rect=(10, 10, 100, 100),
    )

    events = generate_vehicle_zone_events(
        [("car", 0.9, 0, 0, 20, 20)],
        [zone],
        frame_number=12,
        timestamp_seconds=0.4,
        bbox_offset=(5, 5),
    )

    assert [event.event for event in events] == [
        "vehicle_intersects_zone",
        "vehicle_center_inside_zone",
    ]
    assert events[0].vehicle_bbox == (5, 5, 25, 25)
    assert events[0].zone_type == "restricted_zone"
    assert events[0].zone_name == "Restricted Left Lane"


def test_generate_vehicle_zone_events_ignores_disabled_zones():
    zone = RuntimeZone(
        id="restricted_lane_left",
        name="Restricted Left Lane",
        type="restricted_zone",
        shape="polygon",
        enabled=False,
        points_normalized=[(0, 0), (1, 0), (1, 1), (0, 1)],
        points_pixel=[(0, 0), (100, 0), (100, 100), (0, 100)],
        bounding_rect=(0, 0, 100, 100),
    )

    events = generate_vehicle_zone_events(
        [("car", 0.9, 10, 10, 20, 20)],
        [zone],
        frame_number=12,
        timestamp_seconds=0.4,
    )

    assert events == []
