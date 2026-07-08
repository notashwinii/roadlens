from __future__ import annotations

import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session, selectinload

from core.config_loader import load_config
from db.models import ViolationEvent

BACKEND_ROOT = Path(__file__).resolve().parents[1]
CONFIG_ROOT = BACKEND_ROOT / "configs"
OUTPUT_ROOT = BACKEND_ROOT / "outputs"
UPLOAD_ROOT = OUTPUT_ROOT / "uploads"
ALLOWED_VIDEO_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv"}


app = FastAPI(
    title="RoadLens API",
    version="0.1.0",
    description="Operational API for traffic evidence processing and review.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if OUTPUT_ROOT.exists():
    app.mount("/api/artifacts", StaticFiles(directory=OUTPUT_ROOT), name="artifacts")


@dataclass(frozen=True)
class UploadedVideoRecord:
    id: str
    filename: str
    path: str
    size_bytes: int
    frame_width: int
    frame_height: int
    frame_count: int
    fps: float | None


VIDEO_REGISTRY: dict[str, UploadedVideoRecord] = {}


def _model_dump(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return dict(model)


def _artifact_url(path: str) -> str:
    artifact_path = Path(path)
    output_root_name = OUTPUT_ROOT.name

    parts = artifact_path.parts
    if output_root_name in parts:
        output_index = parts.index(output_root_name)
        artifact_path = Path(*parts[output_index + 1 :])

    return f"/api/artifacts/{artifact_path.as_posix()}"


def _resolve_config_path(config_path: str) -> Path:
    candidate = Path(config_path)
    if not candidate.is_absolute():
        candidate = BACKEND_ROOT / candidate

    resolved = candidate.resolve()
    backend_root = BACKEND_ROOT.resolve()
    config_root = CONFIG_ROOT.resolve()

    if not (
        resolved.is_relative_to(backend_root) or resolved.is_relative_to(config_root)
    ):
        raise HTTPException(status_code=400, detail="Config path is outside backend.")

    if not resolved.exists():
        raise HTTPException(
            status_code=404, detail=f"Config file not found: {config_path}"
        )

    return resolved


def _video_metadata(video_path: Path) -> dict[str, int | float | None]:
    import cv2

    cap = cv2.VideoCapture(str(video_path))
    try:
        if not cap.isOpened():
            raise HTTPException(
                status_code=400, detail="Could not open uploaded video."
            )

        frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)

        return {
            "frame_width": frame_width,
            "frame_height": frame_height,
            "frame_count": frame_count,
            "fps": fps if fps > 0 else None,
        }
    finally:
        cap.release()


def _read_first_frame_jpeg(video_path: Path) -> bytes:
    import cv2

    cap = cv2.VideoCapture(str(video_path))
    try:
        if not cap.isOpened():
            raise HTTPException(
                status_code=400, detail="Could not open uploaded video."
            )

        ok, frame = cap.read()
        if not ok:
            raise HTTPException(
                status_code=422,
                detail="Could not read the first frame from uploaded video.",
            )

        encoded, buffer = cv2.imencode(".jpg", frame)
        if not encoded:
            raise HTTPException(status_code=500, detail="Could not encode first frame.")

        return buffer.tobytes()
    finally:
        cap.release()


def get_db() -> Session:
    from db.database import SessionLocal

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbSession = Annotated[Session, Depends(get_db)]
VideoUpload = Annotated[UploadFile, File(...)]


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "roadlens-api"}


@app.post("/api/videos", status_code=201)
def upload_video(file: VideoUpload) -> dict[str, Any]:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_VIDEO_SUFFIXES:
        raise HTTPException(
            status_code=415,
            detail="Unsupported video type. Use mp4, mov, avi, or mkv.",
        )

    video_id = uuid4().hex
    upload_dir = UPLOAD_ROOT / video_id
    upload_dir.mkdir(parents=True, exist_ok=False)
    video_path = upload_dir / f"source{suffix}"

    with video_path.open("wb") as target:
        shutil.copyfileobj(file.file, target)

    metadata = _video_metadata(video_path)
    record = UploadedVideoRecord(
        id=video_id,
        filename=file.filename or video_path.name,
        path=str(video_path),
        size_bytes=video_path.stat().st_size,
        frame_width=int(metadata["frame_width"] or 0),
        frame_height=int(metadata["frame_height"] or 0),
        frame_count=int(metadata["frame_count"] or 0),
        fps=metadata["fps"],
    )
    VIDEO_REGISTRY[video_id] = record

    return asdict(record)


@app.get("/api/videos/{video_id}")
def read_video(video_id: str) -> dict[str, Any]:
    record = VIDEO_REGISTRY.get(video_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Uploaded video not found.")

    return asdict(record)


@app.get("/api/videos/{video_id}/first-frame")
def read_video_first_frame(video_id: str) -> Response:
    record = VIDEO_REGISTRY.get(video_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Uploaded video not found.")

    frame = _read_first_frame_jpeg(Path(record.path))
    return Response(content=frame, media_type="image/jpeg")


@app.get("/api/config")
def read_config(
    path: str = Query("configs/default.yaml", description="Path relative to backend/."),
) -> dict[str, Any]:
    config = load_config(_resolve_config_path(path))
    return _model_dump(config)


@app.get("/api/zones")
def read_zones(
    path: str = Query("configs/default.yaml", description="Path relative to backend/."),
) -> dict[str, Any]:
    config = load_config(_resolve_config_path(path))
    return {
        "camera": _model_dump(config.camera),
        "zones": [_model_dump(zone) for zone in config.zones],
    }


@app.get("/api/rules")
def read_rules(
    path: str = Query("configs/default.yaml", description="Path relative to backend/."),
) -> dict[str, Any]:
    config = load_config(_resolve_config_path(path))
    return {
        "conditions": [_model_dump(condition) for condition in config.conditions],
        "rules": [_model_dump(rule) for rule in config.rules],
    }


@app.get("/api/evidence")
def list_evidence(
    db: DbSession,
    limit: int = Query(50, ge=1, le=200),
    review_status: str | None = Query(None),
) -> dict[str, Any]:
    query = (
        db.query(ViolationEvent)
        .options(
            selectinload(ViolationEvent.artifacts),
            selectinload(ViolationEvent.detections),
        )
        .order_by(ViolationEvent.created_at.desc())
    )

    if review_status:
        query = query.filter(ViolationEvent.review_status == review_status)

    events = query.limit(limit).all()
    return {
        "items": [_serialize_violation_event(event) for event in events],
        "count": len(events),
    }


@app.get("/api/evidence/{event_id}")
def read_evidence(event_id: int, db: DbSession) -> dict[str, Any]:
    event = (
        db.query(ViolationEvent)
        .options(
            selectinload(ViolationEvent.artifacts),
            selectinload(ViolationEvent.detections),
        )
        .filter(ViolationEvent.id == event_id)
        .one_or_none()
    )

    if event is None:
        raise HTTPException(status_code=404, detail="Evidence event not found.")

    return _serialize_violation_event(event)


def _serialize_violation_event(event: ViolationEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "video_id": event.video_id,
        "rule": {
            "id": event.rule_id,
            "name": event.rule_name,
        },
        "zone": {
            "id": event.zone_id,
            "type": event.zone_type,
            "name": event.zone_name,
        },
        "event_type": event.event_type,
        "source_frame_number": event.source_frame_number,
        "timestamp_seconds": event.timestamp_seconds,
        "vehicle": {
            "class": event.vehicle_class,
            "confidence": event.vehicle_confidence,
            "bbox": [
                event.vehicle_x1,
                event.vehicle_y1,
                event.vehicle_x2,
                event.vehicle_y2,
            ],
        },
        "review_status": event.review_status,
        "created_at": event.created_at.isoformat(),
        "detections": [
            {
                "id": detection.id,
                "plate_text": detection.plate_text,
                "bbox": [detection.x1, detection.y1, detection.x2, detection.y2],
                "crop_width": detection.crop_width,
                "crop_height": detection.crop_height,
                "detector_confidence": detection.detector_confidence,
                "ocr_confidence": detection.ocr_confidence,
                "created_at": detection.created_at.isoformat(),
            }
            for detection in event.detections
        ],
        "artifacts": [
            {
                "id": artifact.id,
                "type": artifact.artifact_type,
                "path": artifact.path,
                "url": _artifact_url(artifact.path),
                "width": artifact.width,
                "height": artifact.height,
                "created_at": artifact.created_at.isoformat(),
            }
            for artifact in event.artifacts
        ],
    }
