from types import SimpleNamespace

import numpy as np

import pipeline
from core.config_schema import (
    ConditionConfig,
    ConditionPredicateConfig,
    RoadLensConfig,
    RuleConfig,
    RuleWhenConfig,
    ZoneEventPredicateConfig,
)
from rules.action_runner import ActionRunner
from rules.conditions import ConditionProvider
from rules.rule_engine import RuleEngine
from scene.runtime_zone import RuntimeZone


class FakeCap:
    def isOpened(self):
        return True

    def read(self):
        return True, np.zeros((20, 30, 3), dtype=np.uint8)

    def release(self):
        pass


class FakeVehicleDetector:
    def vehicle_coordinates(self, frame, conf_threshold=0.35):
        assert frame.shape == (20, 30, 3)
        assert conf_threshold == 0.35
        return [("car", 0.95, 2, 3, 22, 18)]

    def crop_vehicle(self, frame, x1, y1, x2, y2):
        assert (x1, y1, x2, y2) == (2, 3, 22, 18)
        return np.zeros((15, 20, 3), dtype=np.uint8)


class FakePlateDetector:
    def license_coordinates(self, frame, min_confidence=0.0):
        assert frame.shape == (15, 20, 3)
        assert min_confidence == 0.25
        return SimpleNamespace(coords=(1, 2, 11, 12), confidence=0.9)

    def crop_into_plate(self, frame, x1, y1, x2, y2):
        assert frame.shape == (15, 20, 3)
        assert (x1, y1, x2, y2) == (1, 2, 11, 12)
        return np.zeros((10, 20, 3), dtype=np.uint8)


class FakeOCR:
    def ocr_inference(self, plate_img):
        assert plate_img.shape == (10, 20, 3)
        return SimpleNamespace(
            text="BA 12 PA 3456",
            confidence=0.82,
            segments=["BA", "12", "PA", "3456"],
            segment_confidences=[0.8, 0.85, 0.81, 0.82],
        )


def runtime_zone(
    zone_id="restricted_lane_left",
    points_pixel=None,
    enabled=True,
):
    return RuntimeZone(
        id=zone_id,
        name="Restricted Left Lane",
        type="restricted_zone",
        shape="polygon",
        enabled=enabled,
        points_normalized=[(0, 0), (1, 0), (1, 1), (0, 1)],
        points_pixel=points_pixel or [(0, 0), (40, 0), (40, 40), (0, 40)],
        bounding_rect=(0, 0, 40, 40),
    )


def restricted_zone_rule_engine():
    rule = RuleConfig(
        id="restricted_zone_entry",
        name="Restricted Zone Entry",
        enabled=True,
        when=RuleWhenConfig(
            all=[
                ZoneEventPredicateConfig(
                    event="vehicle_intersects_zone",
                    zone_type="restricted_zone",
                ),
                ConditionPredicateConfig(condition="always_forbidden"),
            ]
        ),
        actions=["create_violation_event", "capture_license_plate"],
    )
    return RuleEngine(
        [rule],
        ConditionProvider(
            [
                ConditionConfig(
                    id="always_forbidden",
                    name="Always Forbidden",
                    type="always_true",
                )
            ]
        ),
    )


def fake_selected_frames(
    _cap,
    roi=None,
    motion_threshold=100,
    cooldown_frames=10,
):
    assert roi == (5, 7, 30, 20)
    assert motion_threshold == 100
    assert cooldown_frames == 10
    yield {
        "image": np.zeros((20, 30, 3), dtype=np.uint8),
        "frame_number": 4,
        "roi": (5, 7, 30, 20),
        "motion_area": 125.0,
        "sharpness": 3.0,
        "score": 375.0,
        "timestamp_seconds": 0.4,
        "selection_reason": "motion_cooldown",
    }


def setup_pipeline_fakes(monkeypatch):
    monkeypatch.setattr(pipeline.cv2, "VideoCapture", lambda _path: FakeCap())
    monkeypatch.setattr(pipeline, "selected_frames", fake_selected_frames)


def test_process_video_excludes_images_by_default(monkeypatch):
    setup_pipeline_fakes(monkeypatch)

    results = pipeline.process_video(
        "fake.mp4",
        roi=(5, 7, 30, 20),
        save_to_db=False,
        vehicle_detector=FakeVehicleDetector(),
        plate_detector=FakePlateDetector(),
        ocr=FakeOCR(),
        min_detection_confidence=0.25,
    )

    assert len(results) == 1

    result = results[0]

    assert "plate_img" not in result
    assert "vehicle_img" not in result

    assert result["plate_text"] == "BA 12 PA 3456"

    # Full-frame coords = ROI offset + vehicle offset + plate offset.
    #
    # ROI:       x=5, y=7
    # Vehicle:   x=2, y=3
    # Plate box: x1=1, y1=2, x2=11, y2=12
    #
    # Final:
    # x1 = 5 + 2 + 1  = 8
    # y1 = 7 + 3 + 2  = 12
    # x2 = 5 + 2 + 11 = 18
    # y2 = 7 + 3 + 12 = 22
    assert result["coords"] == (8, 12, 18, 22)

    assert result["roi_coords"] == (1, 2, 11, 12)
    assert result["source_frame_number"] == 4
    assert result["roi"] == (5, 7, 30, 20)

    assert result["vehicle_class"] == "car"
    assert result["vehicle_confidence"] == 0.95
    assert result["vehicle_coords"] == (7, 10, 27, 25)

    assert result["detector_confidence"] == 0.9
    assert result["ocr_confidence"] == 0.82
    assert result["ocr_segments"] == ["BA", "12", "PA", "3456"]
    assert result["crop_shape"] == (10, 20, 3)

    assert result["frame_metadata"] == {
        "motion_area": 125.0,
        "sharpness": 3.0,
        "score": 375.0,
        "timestamp_seconds": 0.4,
        "selection_reason": "motion_cooldown",
    }
    assert result["violation_event_id"] is None
    assert result["violation_event_ids"] == []
    assert result["review_status"] is None
    assert result["evidence_artifacts"] == []
    assert result["violation_candidate"] is False
    assert result["rule_matches"] == []


def test_process_video_includes_images_when_requested(monkeypatch):
    setup_pipeline_fakes(monkeypatch)

    results = pipeline.process_video(
        "fake.mp4",
        roi=(5, 7, 30, 20),
        save_to_db=False,
        include_images=True,
        vehicle_detector=FakeVehicleDetector(),
        plate_detector=FakePlateDetector(),
        ocr=FakeOCR(),
        min_detection_confidence=0.25,
    )

    assert len(results) == 1
    assert results[0]["plate_img"].shape == (10, 20, 3)
    assert results[0]["vehicle_img"].shape == (15, 20, 3)


def test_process_video_skips_when_no_vehicle_detected(monkeypatch):
    setup_pipeline_fakes(monkeypatch)

    class NoVehicleDetector:
        def vehicle_coordinates(self, frame, conf_threshold=0.35):
            return []

    results = pipeline.process_video(
        "fake.mp4",
        roi=(5, 7, 30, 20),
        save_to_db=False,
        vehicle_detector=NoVehicleDetector(),
        plate_detector=FakePlateDetector(),
        ocr=FakeOCR(),
        min_detection_confidence=0.25,
    )

    assert results == []


def test_process_video_skips_when_no_plate_detected(monkeypatch):
    setup_pipeline_fakes(monkeypatch)

    class NoPlateDetector:
        def license_coordinates(self, frame, min_confidence=0.0):
            return None

        def crop_into_plate(self, frame, x1, y1, x2, y2):
            raise AssertionError("crop_into_plate should not be called")

    results = pipeline.process_video(
        "fake.mp4",
        roi=(5, 7, 30, 20),
        save_to_db=False,
        vehicle_detector=FakeVehicleDetector(),
        plate_detector=NoPlateDetector(),
        ocr=FakeOCR(),
        min_detection_confidence=0.25,
    )

    assert results == []


def test_process_video_skips_when_ocr_fails(monkeypatch):
    setup_pipeline_fakes(monkeypatch)

    class NoOCR:
        def ocr_inference(self, plate_img):
            return None

    results = pipeline.process_video(
        "fake.mp4",
        roi=(5, 7, 30, 20),
        save_to_db=False,
        vehicle_detector=FakeVehicleDetector(),
        plate_detector=FakePlateDetector(),
        ocr=NoOCR(),
        min_detection_confidence=0.25,
    )

    assert results == []


def test_process_video_calls_progress_callback(monkeypatch):
    setup_pipeline_fakes(monkeypatch)

    callback_results = []

    results = pipeline.process_video(
        "fake.mp4",
        roi=(5, 7, 30, 20),
        save_to_db=False,
        vehicle_detector=FakeVehicleDetector(),
        plate_detector=FakePlateDetector(),
        ocr=FakeOCR(),
        min_detection_confidence=0.25,
        progress_callback=callback_results.append,
    )

    assert len(results) == 1
    assert callback_results == results


def test_process_video_reports_status_events(monkeypatch):
    setup_pipeline_fakes(monkeypatch)

    status_events = []

    results = pipeline.process_video(
        "fake.mp4",
        roi=(5, 7, 30, 20),
        save_to_db=False,
        vehicle_detector=FakeVehicleDetector(),
        plate_detector=FakePlateDetector(),
        ocr=FakeOCR(),
        min_detection_confidence=0.25,
        status_callback=status_events.append,
    )

    assert len(results) == 1
    assert [event["event"] for event in status_events] == [
        "frame_started",
        "vehicles_detected",
        "plate_detection_started",
        "plate_detected",
        "ocr_started",
        "detection_succeeded",
    ]
    assert status_events[0]["frame_index"] == 0
    assert status_events[0]["source_frame_number"] == 4
    assert status_events[1]["vehicle_count"] == 1
    assert status_events[-1]["plate_text"] == "BA 12 PA 3456"


def test_process_video_attaches_matching_rule_metadata(monkeypatch):
    setup_pipeline_fakes(monkeypatch)

    results = pipeline.process_video(
        "fake.mp4",
        roi=(5, 7, 30, 20),
        save_to_db=False,
        vehicle_detector=FakeVehicleDetector(),
        plate_detector=FakePlateDetector(),
        ocr=FakeOCR(),
        min_detection_confidence=0.25,
        runtime_zones=[runtime_zone()],
        rule_engine=restricted_zone_rule_engine(),
        action_runner=ActionRunner(),
    )

    assert len(results) == 1
    assert results[0]["violation_candidate"] is True
    assert results[0]["violation_event_id"] is None
    assert results[0]["review_status"] is None
    assert results[0]["evidence_artifacts"] == []
    assert results[0]["rule_matches"] == [
        {
            "rule_id": "restricted_zone_entry",
            "rule_name": "Restricted Zone Entry",
            "zone_id": "restricted_lane_left",
            "zone_type": "restricted_zone",
            "zone_name": "Restricted Left Lane",
            "event": "vehicle_intersects_zone",
            "actions": ["create_violation_event", "capture_license_plate"],
        }
    ]


def test_process_video_skips_plate_detection_when_rules_do_not_match(monkeypatch):
    setup_pipeline_fakes(monkeypatch)

    class UnexpectedPlateDetector:
        def license_coordinates(self, frame, min_confidence=0.0):
            raise AssertionError("plate detection should not run without rule matches")

    status_events = []

    results = pipeline.process_video(
        "fake.mp4",
        roi=(5, 7, 30, 20),
        save_to_db=False,
        vehicle_detector=FakeVehicleDetector(),
        plate_detector=UnexpectedPlateDetector(),
        ocr=FakeOCR(),
        min_detection_confidence=0.25,
        runtime_zones=[
            runtime_zone(points_pixel=[(100, 100), (140, 100), (140, 140), (100, 140)])
        ],
        rule_engine=restricted_zone_rule_engine(),
        action_runner=ActionRunner(),
        status_callback=status_events.append,
    )

    assert results == []
    assert [event["event"] for event in status_events] == [
        "frame_started",
        "vehicles_detected",
        "rule_no_match",
    ]


def test_process_video_reports_no_vehicle_status(monkeypatch):
    setup_pipeline_fakes(monkeypatch)

    class NoVehicleDetector:
        def vehicle_coordinates(self, frame, conf_threshold=0.35):
            return []

    status_events = []

    results = pipeline.process_video(
        "fake.mp4",
        roi=(5, 7, 30, 20),
        save_to_db=False,
        vehicle_detector=NoVehicleDetector(),
        plate_detector=FakePlateDetector(),
        ocr=FakeOCR(),
        min_detection_confidence=0.25,
        status_callback=status_events.append,
    )

    assert results == []
    assert [event["event"] for event in status_events] == [
        "frame_started",
        "vehicles_detected",
        "no_vehicles",
    ]


def test_process_video_accepts_runtime_thresholds(monkeypatch):
    def selected_frames_with_config(
        _cap,
        roi=None,
        motion_threshold=100,
        cooldown_frames=10,
    ):
        assert roi == (5, 7, 30, 20)
        assert motion_threshold == 250
        assert cooldown_frames == 4
        yield {
            "image": np.zeros((20, 30, 3), dtype=np.uint8),
            "frame_number": 4,
            "roi": (5, 7, 30, 20),
            "motion_area": 125.0,
            "sharpness": 3.0,
            "score": 375.0,
            "timestamp_seconds": 0.4,
            "selection_reason": "motion_cooldown",
        }

    class ConfiguredVehicleDetector(FakeVehicleDetector):
        def vehicle_coordinates(self, frame, conf_threshold=0.35):
            assert conf_threshold == 0.7
            return super().vehicle_coordinates(frame, conf_threshold=0.35)

    monkeypatch.setattr(pipeline.cv2, "VideoCapture", lambda _path: FakeCap())
    monkeypatch.setattr(pipeline, "selected_frames", selected_frames_with_config)

    results = pipeline.process_video(
        "fake.mp4",
        roi=(5, 7, 30, 20),
        save_to_db=False,
        vehicle_detector=ConfiguredVehicleDetector(),
        plate_detector=FakePlateDetector(),
        ocr=FakeOCR(),
        min_detection_confidence=0.25,
        motion_threshold=250,
        cooldown_frames=4,
        vehicle_confidence=0.7,
    )

    assert len(results) == 1


def test_process_video_from_config_maps_config_to_pipeline(monkeypatch):
    captured_kwargs = {}

    def fake_process_video(**kwargs):
        captured_kwargs.update(kwargs)
        return [{"plate_text": "BA 12 PA 3456"}]

    monkeypatch.setattr(pipeline, "process_video", fake_process_video)
    monkeypatch.setattr("scene.scene_builder.cv2.VideoCapture", lambda _path: FakeCap())

    config = RoadLensConfig.model_validate(
        {
            "camera": {
                "id": "demo_camera_01",
                "name": "Demo Road Camera",
                "source_type": "video_file",
                "source_path": "demo.mp4",
                "reference_resolution": [1000, 500],
                "timezone": "Asia/Kathmandu",
            },
            "models": {
                "vehicle_detector": "vehicle.pt",
                "plate_detector": "plate.pt",
                "ocr_engine": "paddleocr",
            },
            "zones": [
                {
                    "id": "roi_main",
                    "name": "Main ROI",
                    "type": "detection_roi",
                    "shape": "rectangle",
                    "points_normalized": [
                        [0.1, 0.2],
                        [0.9, 0.2],
                        [0.9, 0.8],
                        [0.1, 0.8],
                    ],
                }
            ],
            "frame_selection": {
                "motion_threshold": 200,
                "cooldown_frames": 7,
            },
            "detection": {
                "vehicle_confidence": 0.6,
                "plate_confidence": 0.25,
            },
            "storage": {
                "save_to_db": False,
                "save_evidence_images": False,
                "output_dir": "outputs/evidence",
                "review_status_default": "pending",
                "save_selected_frame": True,
                "save_vehicle_crop": True,
                "save_plate_crop": True,
            },
        }
    )

    results = pipeline.process_video_from_config(config)

    assert results == [{"plate_text": "BA 12 PA 3456"}]
    assert captured_kwargs == {
        "video_path": "demo.mp4",
        "model_path": "plate.pt",
        "vehicle_model_path": "vehicle.pt",
        "roi": (3, 4, 24, 12),
        "save_to_db": False,
        "camera_id": "demo_camera_01",
        "save_evidence_images": False,
        "output_dir": "outputs/evidence",
        "review_status_default": "pending",
        "save_selected_frame": True,
        "save_vehicle_crop": True,
        "save_plate_crop": True,
        "min_detection_confidence": 0.25,
        "motion_threshold": 200,
        "cooldown_frames": 7,
        "vehicle_confidence": 0.6,
    }


def test_process_video_from_config_builds_rule_runtime(monkeypatch):
    captured_kwargs = {}

    def fake_process_video(**kwargs):
        captured_kwargs.update(kwargs)
        return []

    monkeypatch.setattr(pipeline, "process_video", fake_process_video)
    monkeypatch.setattr("scene.scene_builder.cv2.VideoCapture", lambda _path: FakeCap())

    config = RoadLensConfig.model_validate(
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
            "zones": [
                {
                    "id": "restricted_lane_left",
                    "name": "Restricted Left Lane",
                    "type": "restricted_zone",
                    "shape": "polygon",
                    "points_normalized": [
                        [0.1, 0.2],
                        [0.9, 0.2],
                        [0.9, 0.8],
                        [0.1, 0.8],
                    ],
                }
            ],
            "conditions": [
                {
                    "id": "always_forbidden",
                    "name": "Always Forbidden",
                    "type": "always_true",
                }
            ],
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
                            {"condition": "always_forbidden"},
                        ]
                    },
                    "actions": ["create_violation_event"],
                }
            ],
        }
    )

    results = pipeline.process_video_from_config(config)

    assert results == []
    assert captured_kwargs["rule_engine"].has_rules is True
    assert isinstance(captured_kwargs["action_runner"], ActionRunner)
    assert len(captured_kwargs["runtime_zones"]) == 1
    assert captured_kwargs["runtime_zones"][0].id == "restricted_lane_left"
