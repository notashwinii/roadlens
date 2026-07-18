import json

from core.camera_credentials import apply_source_credentials
from core.config_schema import RoadLensConfig
from db.database import SessionLocal
from db.models import Camera


def load_persisted_camera_config(camera_id: int) -> RoadLensConfig:
    db = SessionLocal()
    try:
        camera = db.query(Camera).filter(Camera.id == camera_id).one_or_none()
        if camera is None:
            raise ValueError(f"Persisted camera {camera_id} was not found.")
        if not camera.enabled:
            raise ValueError(f"Persisted camera {camera_id} is disabled.")
        config = RoadLensConfig.model_validate(json.loads(camera.config_json))
        return apply_source_credentials(
            config,
            camera_id=camera.id,
            encrypted_credentials=camera.source_secret_encrypted,
        )
    finally:
        db.close()
