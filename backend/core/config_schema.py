from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


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


ZoneType = Literal[
    "detection_roi",
    "stop_line",
    "zebra_crossing",
    "restricted_zone",
    "no_entry",
]
ConditionType = Literal["always_true", "manual_state"]
RuleEventType = Literal[
    "vehicle_intersects_zone",
    "vehicle_center_inside_zone",
]
RuleActionType = Literal[
    "create_violation_event",
    "capture_license_plate",
    "send_to_review",
]


class ZoneConfig(BaseModel):
    id: str
    name: str
    type: ZoneType
    shape: Literal["rectangle", "polygon"] = "polygon"
    points_normalized: list[tuple[float, float]]
    enabled: bool = True
    description: str | None = None

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


class ConditionConfig(BaseModel):
    id: str
    name: str
    type: ConditionType
    enabled: bool = True
    key: str | None = None
    value: str | bool | int | float | None = None


class ZoneEventPredicateConfig(BaseModel):
    kind: Literal["zone_event"] = "zone_event"
    event: RuleEventType
    zone_type: ZoneType


class ConditionPredicateConfig(BaseModel):
    kind: Literal["condition"] = "condition"
    condition: str


RulePredicateConfig = Annotated[
    ZoneEventPredicateConfig | ConditionPredicateConfig,
    Field(discriminator="kind"),
]


class RuleWhenConfig(BaseModel):
    all: list[RulePredicateConfig] = Field(min_length=1)

    @field_validator("all", mode="before")
    @classmethod
    def infer_predicate_kind(cls, predicates):
        if not isinstance(predicates, list):
            return predicates

        normalized_predicates = []
        for predicate in predicates:
            if not isinstance(predicate, dict) or "kind" in predicate:
                normalized_predicates.append(predicate)
                continue

            if "event" in predicate:
                normalized_predicates.append({"kind": "zone_event", **predicate})
            elif "condition" in predicate:
                normalized_predicates.append({"kind": "condition", **predicate})
            else:
                normalized_predicates.append(predicate)

        return normalized_predicates


class RuleConfig(BaseModel):
    id: str
    name: str
    enabled: bool = True
    when: RuleWhenConfig
    actions: list[RuleActionType] = Field(min_length=1)


class FrameSelectionConfig(BaseModel):
    motion_threshold: int = Field(default=100, ge=1)
    cooldown_frames: int = Field(default=10, ge=0)
    sharpness_method: Literal["laplacian_variance"] = "laplacian_variance"
    score_method: Literal["motion_area_times_sharpness"] = "motion_area_times_sharpness"


class DetectionConfig(BaseModel):
    vehicle_confidence: float = Field(default=0.35, ge=0.0, le=1.0)
    plate_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class StorageConfig(BaseModel):
    save_to_db: bool = False
    save_evidence_images: bool = False
    output_dir: str = "outputs/evidence"
    review_status_default: Literal["pending", "accepted", "rejected", "corrected"] = (
        "pending"
    )
    save_selected_frame: bool = True
    save_vehicle_crop: bool = True
    save_plate_crop: bool = True


class RoadLensConfig(BaseModel):
    camera: CameraConfig
    models: ModelConfig
    zones: list[ZoneConfig] = Field(default_factory=list)
    conditions: list[ConditionConfig] = Field(default_factory=list)
    rules: list[RuleConfig] = Field(default_factory=list)
    frame_selection: FrameSelectionConfig = Field(default_factory=FrameSelectionConfig)
    detection: DetectionConfig = Field(default_factory=DetectionConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)

    @model_validator(mode="after")
    def validate_rule_references(self):
        condition_ids = {condition.id for condition in self.conditions}
        for rule in self.rules:
            for predicate in rule.when.all:
                if (
                    isinstance(predicate, ConditionPredicateConfig)
                    and predicate.condition not in condition_ids
                ):
                    raise ValueError(
                        f"Rule '{rule.id}' references unknown condition "
                        f"'{predicate.condition}'."
                    )

        return self
