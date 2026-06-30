from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from core.config_schema import RoadLensConfig, ZoneConfig
from scene.runtime_zone import RuntimeZone, build_runtime_zone


class SceneBuildError(RuntimeError):
    pass


@dataclass(frozen=True)
class RuntimeScene:
    first_frame: np.ndarray
    frame_width: int
    frame_height: int
    zones: list[RuntimeZone]


def read_first_frame(video_path: str) -> np.ndarray:
    cap = cv2.VideoCapture(video_path)
    try:
        ret, frame = cap.read()
        if not ret:
            raise SceneBuildError(f"Could not read first frame from {video_path}")
        return frame
    finally:
        cap.release()


def get_frame_size(frame: np.ndarray) -> tuple[int, int]:
    height, width = frame.shape[:2]
    return width, height


def enabled_zones(zones: list[ZoneConfig]) -> list[ZoneConfig]:
    return [zone for zone in zones if zone.enabled]


def first_detection_roi_from_config(config: RoadLensConfig) -> ZoneConfig | None:
    return next(
        (zone for zone in enabled_zones(config.zones) if zone.type == "detection_roi"),
        None,
    )


def build_runtime_zones(
    config: RoadLensConfig,
    frame_width: int,
    frame_height: int,
) -> list[RuntimeZone]:
    return [
        build_runtime_zone(zone, frame_width, frame_height)
        for zone in enabled_zones(config.zones)
    ]


def build_scene_from_config(config: RoadLensConfig) -> RuntimeScene:
    first_frame = read_first_frame(config.camera.source_path)
    frame_width, frame_height = get_frame_size(first_frame)
    runtime_zones = build_runtime_zones(config, frame_width, frame_height)

    return RuntimeScene(
        first_frame=first_frame,
        frame_width=frame_width,
        frame_height=frame_height,
        zones=runtime_zones,
    )


def runtime_roi_for_video(config: RoadLensConfig) -> tuple[int, int, int, int] | None:
    detection_zone = first_detection_roi_from_config(config)
    if detection_zone is None:
        return None

    first_frame = read_first_frame(config.camera.source_path)
    frame_width, frame_height = get_frame_size(first_frame)
    runtime_zone = build_runtime_zone(detection_zone, frame_width, frame_height)
    return runtime_zone.bounding_rect
