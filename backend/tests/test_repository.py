import os

import numpy as np
import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")
orm = pytest.importorskip("sqlalchemy.orm")

os.environ["DATABASE_URL"] = "sqlite:///:memory:"


def test_save_detection_accepts_confidence_values():
    from db.database import Base
    from db.repository import save_detection, save_video

    engine = sqlalchemy.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = orm.sessionmaker(bind=engine)()

    try:
        video = save_video(session, "test_video.mp4")
        plate_img = np.zeros((12, 34, 3), dtype=np.uint8)

        detection = save_detection(
            session,
            video.id,
            "BA 12 PA 3456",
            (1.0, 2.0, 30.0, 14.0),
            plate_img,
            detector_confidence=0.91,
            ocr_confidence=0.82,
        )

        assert detection.id is not None
        assert detection.detector_confidence == 0.91
        assert detection.ocr_confidence == 0.82
        assert detection.crop_width == 34
        assert detection.crop_height == 12
        assert detection.created_at is not None
    finally:
        session.close()
