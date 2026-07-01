import os
from types import SimpleNamespace

import numpy as np
import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")
orm = pytest.importorskip("sqlalchemy.orm")

os.environ["DATABASE_URL"] = "sqlite:///:memory:"


def test_save_violation_event_detection_and_artifact_relationships():
    from db.database import Base
    from db.repository import (
        save_detection,
        save_evidence_artifact,
        save_video,
        save_violation_event,
    )

    engine = sqlalchemy.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = orm.sessionmaker(bind=engine)()

    try:
        video = save_video(session, "test_video.mp4")
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

        violation_event = save_violation_event(session, video.id, rule_match)
        plate_img = np.zeros((12, 34, 3), dtype=np.uint8)
        detection = save_detection(
            session,
            video.id,
            "BA 12 PA 3456",
            (3.0, 4.0, 25.0, 14.0),
            plate_img,
            detector_confidence=0.93,
            ocr_confidence=0.84,
            violation_event_id=violation_event.id,
        )
        artifact = save_evidence_artifact(
            session,
            violation_event.id,
            "plate_crop",
            "outputs/evidence/camera_1/video_000001/event_000001/plate_crop.jpg",
            width=34,
            height=12,
        )

        session.refresh(video)
        session.refresh(violation_event)
        session.refresh(detection)
        session.refresh(artifact)

        assert violation_event.id is not None
        assert violation_event.review_status == "pending"
        assert violation_event.video == video
        assert violation_event.vehicle_x1 == 1.0
        assert violation_event.vehicle_y2 == 40.0

        assert detection.violation_event_id == violation_event.id
        assert detection.violation_event == violation_event
        assert violation_event.detections == [detection]

        assert artifact.violation_event_id == violation_event.id
        assert artifact.width == 34
        assert artifact.height == 12
        assert violation_event.artifacts == [artifact]
        assert video.violation_events == [violation_event]
    finally:
        session.close()
