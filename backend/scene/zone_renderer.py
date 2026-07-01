from __future__ import annotations

import cv2

from scene.runtime_zone import RuntimeZone

ZONE_COLORS = {
    "detection_roi": (255, 255, 0),
    "stop_line": (0, 0, 255),
    "zebra_crossing": (255, 0, 255),
    "restricted_zone": (0, 165, 255),
    "no_entry": (0, 0, 128),
}


def draw_zones(frame, zones: list[RuntimeZone]):
    output = frame.copy()

    for zone in zones:
        color = ZONE_COLORS.get(zone.type, (0, 255, 0))
        points = zone.points_pixel
        if len(points) < 2:
            continue

        for index, start_point in enumerate(points):
            end_point = points[(index + 1) % len(points)]
            cv2.line(output, start_point, end_point, color, 2)

        label_x, label_y = points[0]
        cv2.putText(
            output,
            f"{zone.name} ({zone.type})",
            (label_x, max(20, label_y - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            color,
            2,
            cv2.LINE_AA,
        )

    return output
