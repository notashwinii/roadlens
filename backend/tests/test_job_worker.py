import json
import os

import sqlalchemy
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import jobs.worker as worker
from db.database import Base
from db.models import Camera, ProcessingJob, User, Workspace, WorkspaceMembership


def test_worker_claims_and_completes_a_processing_job(monkeypatch):
    engine = sqlalchemy.create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    try:
        user = User(
            email="owner@example.com",
            name="Owner",
            password_hash="hash",
        )
        workspace = Workspace(name="RoadLens", slug="roadlens", timezone="UTC")
        db.add_all([user, workspace])
        db.flush()
        db.add(
            WorkspaceMembership(
                user_id=user.id,
                workspace_id=workspace.id,
                role="owner",
            )
        )
        camera = Camera(
            workspace_id=workspace.id,
            camera_key="gate",
            name="Gate",
            source_type="video_file",
            source_path="uploads/gate.mp4",
            timezone="UTC",
            config_json="{}",
        )
        db.add(camera)
        db.flush()
        job = ProcessingJob(
            workspace_id=workspace.id,
            camera_id=camera.id,
            created_by_user_id=user.id,
            status="queued",
        )
        db.add(job)
        db.commit()
        job_id = job.id
    finally:
        db.close()

    monkeypatch.setattr(worker, "SessionLocal", session_factory)
    monkeypatch.setattr(
        worker,
        "load_persisted_camera_config",
        lambda camera_id: {"camera_id": camera_id},
    )

    def process(config, *, camera_profile_id, status_callback):
        assert config == {"camera_id": camera_profile_id}
        status_callback({"event": "frame_started", "message": "Scanning frame 1."})
        return [{"plate": "BA 1 PA 1234"}]

    monkeypatch.setattr(worker, "process_video_from_config", process)

    assert worker.claim_next_job("test-worker") == job_id
    worker.run_job(job_id)

    db = session_factory()
    try:
        completed = db.get(ProcessingJob, job_id)
        assert completed is not None
        assert completed.status == "completed"
        assert completed.claimed_by == "test-worker"
        assert json.loads(completed.result_json) == {"detection_count": 1}
        assert json.loads(completed.payload_json)["event"] == "completed"
        assert completed.finished_at is not None
    finally:
        db.close()
