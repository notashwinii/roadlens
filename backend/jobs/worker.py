from __future__ import annotations

import argparse
import json
import os
import socket
import time
from datetime import datetime

from core.persisted_config import load_persisted_camera_config
from db.database import SessionLocal, create_tables
from db.models import ProcessingJob
from pipeline import process_video_from_config


class JobCanceled(RuntimeError):
    pass


def worker_identity() -> str:
    return os.getenv(
        "ROADLENS_WORKER_ID",
        f"{socket.gethostname()}:{os.getpid()}",
    )


def claim_next_job(worker_id: str) -> int | None:
    db = SessionLocal()
    try:
        candidate = (
            db.query(ProcessingJob)
            .filter(ProcessingJob.status == "queued")
            .order_by(ProcessingJob.created_at.asc())
            .first()
        )
        if candidate is None:
            return None
        claimed_at = datetime.utcnow()
        claimed = (
            db.query(ProcessingJob)
            .filter(
                ProcessingJob.id == candidate.id,
                ProcessingJob.status == "queued",
            )
            .update(
                {
                    ProcessingJob.status: "running",
                    ProcessingJob.claimed_by: worker_id,
                    ProcessingJob.claimed_at: claimed_at,
                    ProcessingJob.started_at: claimed_at,
                },
                synchronize_session=False,
            )
        )
        db.commit()
        return candidate.id if claimed == 1 else None
    finally:
        db.close()


def _record_progress(job_id: int, payload: dict) -> None:
    db = SessionLocal()
    try:
        job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).one()
        if job.status == "cancel_requested":
            raise JobCanceled("Processing canceled.")
        job.payload_json = json.dumps(payload)
        db.commit()
    finally:
        db.close()


def _finish_job(
    job_id: int,
    *,
    status: str,
    result: dict | None = None,
    error: str | None = None,
) -> None:
    db = SessionLocal()
    try:
        job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).one()
        job.status = status
        job.result_json = json.dumps(result) if result is not None else None
        job.error = error
        job.finished_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()


def _cancel_requested(job_id: int) -> bool:
    db = SessionLocal()
    try:
        job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).one()
        return job.status == "cancel_requested"
    finally:
        db.close()


def run_job(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).one()
        camera_id = job.camera_id
    finally:
        db.close()

    try:
        _record_progress(
            job_id,
            {"event": "starting", "message": "Preparing the camera pipeline."},
        )
        config = load_persisted_camera_config(camera_id)
        results = process_video_from_config(
            config,
            camera_profile_id=camera_id,
            status_callback=lambda payload: _record_progress(job_id, payload),
        )
        _record_progress(
            job_id,
            {
                "event": "completed",
                "message": "Processing completed.",
                "detection_count": len(results),
            },
        )
        _finish_job(
            job_id,
            status="completed",
            result={"detection_count": len(results)},
        )
    except JobCanceled:
        _finish_job(job_id, status="canceled")
    except Exception as error:
        if _cancel_requested(job_id):
            _finish_job(job_id, status="canceled")
        else:
            _finish_job(
                job_id,
                status="failed",
                error=str(error)[:2000],
            )


def run_worker(*, once: bool = False, poll_interval: float = 2.0) -> None:
    create_tables()
    worker_id = worker_identity()
    while True:
        job_id = claim_next_job(worker_id)
        if job_id is not None:
            run_job(job_id)
            if once:
                return
            continue
        if once:
            return
        time.sleep(max(0.25, poll_interval))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the RoadLens job worker.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process at most one queued job and exit.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=float(os.getenv("ROADLENS_WORKER_POLL_SECONDS", "2")),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_worker(once=args.once, poll_interval=args.poll_interval)


if __name__ == "__main__":
    main()
