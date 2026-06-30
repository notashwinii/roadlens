from typing import Literal

from pydantic import BaseModel, Field, field_validator


class CameraConfig(BaseModel):
    id: str
    name: str
    source_type: Literal["video_file", "rtsp", "webcam"] = "video_file"
    source_path: str
    reference_resolution: tuple[int, int]
    timezone: str = "UTC"


class ModelConfig(BaseModel):
    vehicle_detector: str
    plate_detector: str
    ocr_engine: Literal["paddleocr"] = "paddleocr"


class ZoneConfig(BaseModel):
    id: str
    name: str
    type: Literal[
        "detection_roi",
        "stop_line",
        "zebra_crossing",
        "restricted_zone",
        "no_entry",
    ]
    shape: Literal["rectangle", "polygon"] = "polygon"
    points_normalized: list[tuple[float, float]]

    @field_validator("points_normalized")
    @classmethod
    def validate_points(
        cls,
        points: list[tuple[float, float]],
    ) -> list[tuple[float, float]]:
        if len(points) < 3:
            raise ValueError("A zone must have at least 3 points.")

        for x, y in points:
            if not 0 <= x <= 1:
                raise ValueError(f"Normalized x coordinate out of range: {x}")
            if not 0 <= y <= 1:
                raise ValueError(f"Normalized y coordinate out of range: {y}")

        return points


class FrameSelectionConfig(BaseModel):
    motion_threshold: int = Field(default=100, ge=1)
    cooldown_frames: int = Field(default=10, ge=0)
    sharpness_method: Literal["laplacian_variance"] = "laplacian_variance"
    score_method: Literal["motion_area_times_sharpness"] = (
        "motion_area_times_sharpness"
    )


class DetectionConfig(BaseModel):
    vehicle_confidence: float = Field(default=0.35, ge=0.0, le=1.0)
    plate_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class StorageConfig(BaseModel):
    save_to_db: bool = False
    save_evidence_images: bool = False
    output_dir: str = "outputs/evidence"


class RoadLensConfig(BaseModel):
    camera: CameraConfig
    models: ModelConfig
    zones: list[ZoneConfig] = Field(default_factory=list)
    frame_selection: FrameSelectionConfig = Field(
        default_factory=FrameSelectionConfig
    )
    detection: DetectionConfig = Field(default_factory=DetectionConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
