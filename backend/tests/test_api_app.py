import os
from io import BytesIO
from types import SimpleNamespace

import pytest

fastapi = pytest.importorskip("fastapi")
sqlalchemy = pytest.importorskip("sqlalchemy")

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")


def test_health_endpoint():
    from api.app import health

    assert health() == {"status": "ok", "service": "roadlens-api"}


def test_config_endpoint_returns_camera_and_detection_settings():
    from api.app import read_config

    payload = read_config(path="configs/default.yaml")

    assert payload["camera"]["id"] == "demo_camera_01"
    assert payload["models"]["ocr_engine"] == "paddleocr"
    assert payload["frame_selection"]["score_method"] == ("motion_area_times_sharpness")


def test_upload_video_rejects_unsupported_suffix():
    from fastapi import HTTPException, UploadFile

    from api.app import upload_video

    with pytest.raises(HTTPException) as exc_info:
        upload_video(UploadFile(filename="notes.txt", file=BytesIO(b"not video")))

    assert exc_info.value.status_code == 415


def test_read_video_uses_upload_registry():
    from api.app import VIDEO_REGISTRY, UploadedVideoRecord, read_video

    VIDEO_REGISTRY.clear()
    VIDEO_REGISTRY["video-1"] = UploadedVideoRecord(
        id="video-1",
        filename="sample.mp4",
        path="outputs/uploads/video-1/source.mp4",
        size_bytes=128,
        frame_width=1920,
        frame_height=1080,
        frame_count=250,
        fps=25.0,
    )

    payload = read_video("video-1")

    assert payload["id"] == "video-1"
    assert payload["filename"] == "sample.mp4"
    assert payload["frame_width"] == 1920


def test_evidence_endpoint_serializes_persisted_event():
    import numpy as np
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from api.app import list_evidence
    from db.database import Base
    from db.repository import (
        save_detection,
        save_evidence_artifact,
        save_video,
        save_violation_event,
    )

    engine = sqlalchemy.create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    db = session_factory()
    try:
        video = save_video(db, "test_video.mp4")
        rule_match = SimpleNamespace(
            rule_id="restricted_zone_entry",
            rule_name="Restricted Zone Entry",
            event=SimpleNamespace(
                zone_id="restricted_lane_left",
                zone_type="restricted_zone",
                zone_name="Restricted Left Lane",
                event="vehicle_intersects_zone",
                frame_number=12,
                timestamp_seconds=0.5,
                vehicle_class="car",
                vehicle_confidence=0.91,
                vehicle_bbox=(1.0, 2.0, 30.0, 40.0),
            ),
        )
        event = save_violation_event(db, video.id, rule_match)
        save_detection(
            db,
            video.id,
            "BA 12 PA 3456",
            (3.0, 4.0, 25.0, 14.0),
            np.zeros((12, 34, 3), dtype=np.uint8),
            detector_confidence=0.93,
            ocr_confidence=0.84,
            violation_event_id=event.id,
        )
        save_evidence_artifact(
            db,
            event.id,
            "plate_crop",
            "outputs/evidence/demo/video_1/event_1/plate_crop.jpg",
            width=34,
            height=12,
        )

        payload = list_evidence(db=db, limit=50, review_status=None)

        assert payload["count"] == 1
        item = payload["items"][0]
        assert item["rule"]["name"] == "Restricted Zone Entry"
        assert item["detections"][0]["plate_text"] == "BA 12 PA 3456"
        assert item["artifacts"][0]["url"].endswith("plate_crop.jpg")
    finally:
        db.close()
