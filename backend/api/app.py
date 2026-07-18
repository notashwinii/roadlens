from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session, selectinload

from api.product import router as product_router
from core.config_loader import load_config
from db.database import create_tables
from db.models import ViolationEvent

BACKEND_ROOT = Path(__file__).resolve().parents[1]
CONFIG_ROOT = BACKEND_ROOT / "configs"
OUTPUT_ROOT = BACKEND_ROOT / "outputs"


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_tables()
    yield


app = FastAPI(
    title="RoadLens API",
    version="0.1.0",
    description="Operational API for traffic evidence processing and review.",
    lifespan=lifespan,
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

app.include_router(product_router)


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


def get_db() -> Session:
    from db.database import SessionLocal

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbSession = Annotated[Session, Depends(get_db)]


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "roadlens-api"}


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
