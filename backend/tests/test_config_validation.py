import pytest
from pydantic import ValidationError

from core.config_schema import RoadLensConfig, ZoneConfig


def test_zone_rejects_invalid_normalized_coordinate():
    with pytest.raises(ValidationError):
        ZoneConfig(
            id="bad_zone",
            name="Bad Zone",
            type="detection_roi",
            shape="polygon",
            points_normalized=[
                (1.2, 0.5),
                (0.2, 0.2),
                (0.4, 0.4),
            ],
        )


def test_config_rejects_unknown_rule_condition_reference():
    with pytest.raises(ValidationError, match="unknown condition"):
        RoadLensConfig.model_validate(
            {
                "camera": {
                    "id": "demo_camera_01",
                    "name": "Demo Road Camera",
                    "source_type": "video_file",
                    "source_path": "demo.mp4",
                    "reference_resolution": [1000, 500],
                },
                "models": {
                    "vehicle_detector": "vehicle.pt",
                    "plate_detector": "plate.pt",
                    "ocr_engine": "paddleocr",
                },
                "rules": [
                    {
                        "id": "restricted_zone_entry",
                        "name": "Restricted Zone Entry",
                        "when": {
                            "all": [
                                {
                                    "event": "vehicle_intersects_zone",
                                    "zone_type": "restricted_zone",
                                },
                                {"condition": "missing_condition"},
                            ]
                        },
                        "actions": ["create_violation_event"],
                    }
                ],
            }
        )
