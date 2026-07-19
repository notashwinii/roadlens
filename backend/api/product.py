from __future__ import annotations

import json
import logging
import os
import re
import secrets
import threading
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, selectinload

from api.email_delivery import send_email
from api.mfa import generate_totp_secret, provisioning_uri, verify_totp
from api.security import (
    SESSION_DAYS,
    create_session_token,
    hash_password,
    hash_session_token,
    session_expiry,
    verify_password,
)
from core.camera_credentials import (
    apply_source_credentials,
    encrypt_source_credentials,
)
from core.camera_source import CameraSourceError, encode_snapshot, read_camera_frame
from core.config_loader import load_config
from core.config_schema import ConditionConfig, RoadLensConfig, RuleConfig, ZoneConfig
from core.secrets import decrypt_secret, encrypt_secret
from db.database import SessionLocal
from db.models import (
    ActionToken,
    AuthSession,
    Camera,
    Invitation,
    ProcessingJob,
    User,
    Video,
    ViolationEvent,
    Workspace,
    WorkspaceMembership,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SESSION_COOKIE = "roadlens_session"
Role = Literal["owner", "admin", "operator", "viewer"]
logger = logging.getLogger(__name__)
DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))

router = APIRouter(prefix="/api", tags=["product"])


class _SlidingWindowLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, *, limit: int, window_seconds: int) -> None:
        now = datetime.utcnow().timestamp()
        cutoff = now - window_seconds
        with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                raise HTTPException(
                    status_code=429,
                    detail="Too many requests. Try again later.",
                )
            events.append(now)


_auth_limiter = _SlidingWindowLimiter()


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbSession = Annotated[Session, Depends(get_db)]
SessionCookie = Annotated[str | None, Cookie(alias=SESSION_COOKIE)]


class SetupRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=200)
    workspace_name: str = Field(min_length=2, max_length=120)
    timezone: str = Field(default="UTC", min_length=2, max_length=80)


class LoginRequest(BaseModel):
    email: str
    password: str
    mfa_code: str | None = None


class PasswordResetRequest(BaseModel):
    email: str


class PasswordResetConfirm(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=200)


class MfaCodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=20)


class MfaDisableRequest(MfaCodeRequest):
    password: str = Field(min_length=8, max_length=200)


class InvitationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=3, max_length=320)
    role: Role = "viewer"


class InvitationAccept(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=200)
    mfa_code: str | None = Field(default=None, min_length=6, max_length=20)


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    timezone: str = Field(default="UTC", min_length=2, max_length=80)


class WorkspaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    timezone: str | None = Field(default=None, min_length=2, max_length=80)


class MemberCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=3, max_length=320)
    password: str | None = Field(default=None, min_length=8, max_length=200)
    role: Role = "viewer"


class MemberUpdate(BaseModel):
    role: Role


class CameraCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    camera_key: str | None = Field(default=None, max_length=100)
    source_type: Literal["video_file", "rtsp", "webcam"] = "video_file"
    source_path: str = Field(min_length=1, max_length=500)
    reference_width: int = Field(default=1920, ge=1, le=16384)
    reference_height: int = Field(default=1080, ge=1, le=16384)
    timezone: str = Field(default="UTC", min_length=2, max_length=80)
    enabled: bool = True
    source_username: str | None = Field(default=None, max_length=200)
    source_password: str | None = Field(default=None, max_length=500)


class CameraUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    camera_key: str | None = Field(default=None, min_length=1, max_length=100)
    source_type: Literal["video_file", "rtsp", "webcam"] | None = None
    source_path: str | None = Field(default=None, min_length=1, max_length=500)
    reference_width: int | None = Field(default=None, ge=1, le=16384)
    reference_height: int | None = Field(default=None, ge=1, le=16384)
    timezone: str | None = Field(default=None, min_length=2, max_length=80)
    enabled: bool | None = None
    vehicle_detector: str | None = Field(default=None, min_length=1, max_length=500)
    plate_detector: str | None = Field(default=None, min_length=1, max_length=500)
    motion_threshold: int | None = Field(default=None, ge=1)
    cooldown_frames: int | None = Field(default=None, ge=0)
    vehicle_confidence: float | None = Field(default=None, ge=0, le=1)
    plate_confidence: float | None = Field(default=None, ge=0, le=1)
    save_to_db: bool | None = None
    save_evidence_images: bool | None = None
    source_username: str | None = Field(default=None, max_length=200)
    source_password: str | None = Field(default=None, max_length=500)
    clear_source_credentials: bool = False


class JobCreate(BaseModel):
    camera_id: int
    job_type: Literal["process_camera"] = "process_camera"


def _normalize_email(value: str) -> str:
    email = value.strip().lower()
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    return email


def _request_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _public_url(path: str) -> str:
    base = os.getenv("ROADLENS_PUBLIC_URL", "http://localhost:5173").rstrip("/")
    return f"{base}{path}"


def _new_action_token(
    db: Session,
    *,
    user_id: int | None,
    purpose: str,
    expires_at: datetime,
    payload_json: str | None = None,
) -> str:
    raw_token = secrets.token_urlsafe(32)
    db.add(
        ActionToken(
            token_hash=hash_session_token(raw_token),
            user_id=user_id,
            purpose=purpose,
            payload_json=payload_json,
            expires_at=expires_at,
        )
    )
    return raw_token


def _valid_action_token(
    db: Session,
    raw_token: str,
    purpose: str,
) -> ActionToken:
    token = (
        db.query(ActionToken)
        .filter(
            ActionToken.token_hash == hash_session_token(raw_token),
            ActionToken.purpose == purpose,
            ActionToken.used_at.is_(None),
            ActionToken.expires_at > datetime.utcnow(),
        )
        .one_or_none()
    )
    if token is None:
        raise HTTPException(status_code=400, detail="This link is invalid or expired.")
    return token


def _mfa_context(user_id: int) -> str:
    return f"user:{user_id}:mfa"


def _mfa_secret(user: User) -> str:
    if not user.mfa_secret_encrypted:
        raise HTTPException(status_code=409, detail="MFA enrollment has not started.")
    try:
        return decrypt_secret(user.mfa_secret_encrypted, _mfa_context(user.id))
    except (RuntimeError, ValueError) as error:
        raise HTTPException(
            status_code=503,
            detail="MFA configuration could not be decrypted.",
        ) from error


def _new_recovery_codes(db: Session, user_id: int) -> list[str]:
    db.query(ActionToken).filter(
        ActionToken.user_id == user_id,
        ActionToken.purpose == "mfa_recovery",
        ActionToken.used_at.is_(None),
    ).delete(synchronize_session=False)
    codes: list[str] = []
    expires_at = datetime.utcnow() + timedelta(days=3650)
    for _ in range(8):
        compact = secrets.token_hex(4).upper()
        code = f"{compact[:4]}-{compact[4:]}"
        codes.append(code)
        db.add(
            ActionToken(
                token_hash=hash_session_token(code),
                user_id=user_id,
                purpose="mfa_recovery",
                expires_at=expires_at,
            )
        )
    return codes


def _consume_mfa_code(db: Session, user: User, code: str) -> bool:
    normalized = code.strip().upper()
    counter = verify_totp(
        _mfa_secret(user),
        normalized,
        last_counter=user.mfa_last_counter,
    )
    if counter is not None:
        user.mfa_last_counter = counter
        return True

    recovery = (
        db.query(ActionToken)
        .filter(
            ActionToken.token_hash == hash_session_token(normalized),
            ActionToken.user_id == user.id,
            ActionToken.purpose == "mfa_recovery",
            ActionToken.used_at.is_(None),
            ActionToken.expires_at > datetime.utcnow(),
        )
        .one_or_none()
    )
    if recovery is None:
        return False
    recovery.used_at = datetime.utcnow()
    return True


def _slugify(value: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return (slug or fallback)[:100]


def _unique_workspace_slug(db: Session, name: str) -> str:
    base = _slugify(name, "workspace")
    slug = base
    suffix = 2
    while db.query(Workspace).filter(Workspace.slug == slug).first():
        slug = f"{base[:90]}-{suffix}"
        suffix += 1
    return slug


def _unique_camera_key(db: Session, workspace_id: int, value: str) -> str:
    base = _slugify(value, "camera").replace("-", "_")
    key = base
    suffix = 2
    while (
        db.query(Camera)
        .filter(Camera.workspace_id == workspace_id, Camera.camera_key == key)
        .first()
    ):
        key = f"{base[:90]}_{suffix}"
        suffix += 1
    return key


def _session_user(
    db: Session,
    token: str | None,
    *,
    required: bool,
) -> User | None:
    if not token:
        if required:
            raise HTTPException(status_code=401, detail="Authentication required.")
        return None

    session = (
        db.query(AuthSession)
        .options(selectinload(AuthSession.user))
        .filter(AuthSession.token_hash == hash_session_token(token))
        .one_or_none()
    )
    if session is None or session.expires_at <= datetime.utcnow():
        if session is not None:
            db.delete(session)
            db.commit()
        if required:
            raise HTTPException(status_code=401, detail="Session expired.")
        return None
    if not session.user.is_active:
        raise HTTPException(status_code=403, detail="User account is disabled.")
    return session.user


def _current_user(db: Session, token: str | None) -> User:
    user = _session_user(db, token, required=True)
    assert user is not None
    return user


def _membership(
    db: Session,
    user_id: int,
    workspace_id: int,
    allowed_roles: set[str] | None = None,
) -> WorkspaceMembership:
    membership = (
        db.query(WorkspaceMembership)
        .filter(
            WorkspaceMembership.user_id == user_id,
            WorkspaceMembership.workspace_id == workspace_id,
        )
        .one_or_none()
    )
    if membership is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    if allowed_roles is not None and membership.role not in allowed_roles:
        raise HTTPException(status_code=403, detail="Insufficient workspace role.")
    return membership


def _workspace_payload(workspace: Workspace, role: str) -> dict[str, Any]:
    return {
        "id": workspace.id,
        "name": workspace.name,
        "slug": workspace.slug,
        "timezone": workspace.timezone,
        "role": role,
        "camera_count": len(workspace.cameras),
        "member_count": len(workspace.memberships),
        "created_at": workspace.created_at.isoformat(),
        "updated_at": workspace.updated_at.isoformat(),
    }


def _user_payload(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "is_active": user.is_active,
        "mfa_enabled": user.mfa_enabled,
        "created_at": user.created_at.isoformat(),
    }


def _camera_config(camera: Camera) -> RoadLensConfig:
    return RoadLensConfig.model_validate(json.loads(camera.config_json))


def _camera_payload(camera: Camera) -> dict[str, Any]:
    config = _camera_config(camera)
    return {
        "id": camera.id,
        "workspace_id": camera.workspace_id,
        "camera_key": camera.camera_key,
        "name": camera.name,
        "source_type": camera.source_type,
        "source_path": camera.source_path,
        "timezone": camera.timezone,
        "enabled": camera.enabled,
        "has_source_credentials": camera.source_secret_encrypted is not None,
        "reference_resolution": list(config.camera.reference_resolution),
        "zone_count": len(config.zones),
        "rule_count": len(config.rules),
        "active_rule_count": sum(rule.enabled for rule in config.rules),
        "created_at": camera.created_at.isoformat(),
        "updated_at": camera.updated_at.isoformat(),
    }


def _job_payload(job: ProcessingJob) -> dict[str, Any]:
    progress = None
    if job.payload_json:
        try:
            progress = json.loads(job.payload_json)
        except json.JSONDecodeError:
            progress = {"message": job.payload_json}

    return {
        "id": job.id,
        "workspace_id": job.workspace_id,
        "camera_id": job.camera_id,
        "job_type": job.job_type,
        "status": job.status,
        "progress": progress,
        "error": job.error,
        "result": json.loads(job.result_json) if job.result_json else None,
        "claimed_by": job.claimed_by,
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


def _artifact_url(path: str) -> str:
    artifact_path = Path(path)
    if "outputs" in artifact_path.parts:
        artifact_path = Path(
            *artifact_path.parts[artifact_path.parts.index("outputs") + 1 :]
        )
    return f"/api/artifacts/{artifact_path.as_posix()}"


def _evidence_payload(event: ViolationEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "rule": {"id": event.rule_id, "name": event.rule_name},
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
        },
        "review_status": event.review_status,
        "created_at": event.created_at.isoformat(),
        "detections": [
            {
                "id": detection.id,
                "plate_text": detection.plate_text,
                "detector_confidence": detection.detector_confidence,
                "ocr_confidence": detection.ocr_confidence,
            }
            for detection in event.detections
        ],
        "artifacts": [
            {
                "id": artifact.id,
                "type": artifact.artifact_type,
                "url": _artifact_url(artifact.path),
                "width": artifact.width,
                "height": artifact.height,
            }
            for artifact in event.artifacts
        ],
    }


def _new_camera_config(payload: CameraCreate, camera_key: str) -> RoadLensConfig:
    config = load_config(BACKEND_ROOT / "configs" / "default.yaml")
    config.camera.id = camera_key
    config.camera.name = payload.name
    config.camera.source_type = payload.source_type
    config.camera.source_path = payload.source_path
    config.camera.reference_resolution = (
        payload.reference_width,
        payload.reference_height,
    )
    config.camera.timezone = payload.timezone
    config.zones = []
    config.conditions = []
    config.rules = []
    return config


def _validate_public_source(source_type: str, source_path: str) -> None:
    if source_type != "rtsp":
        return

    parsed = urlsplit(source_path)
    if parsed.scheme.lower() not in {"rtsp", "rtsps"}:
        raise HTTPException(status_code=422, detail="Enter a valid RTSP source URL.")
    if parsed.username is not None or parsed.password is not None:
        raise HTTPException(
            status_code=422,
            detail="Store RTSP credentials in the username and password fields.",
        )


def _save_source_credentials(
    camera: Camera,
    *,
    username: str | None,
    password: str | None,
) -> None:
    if username is None and password is None:
        return
    try:
        camera.source_secret_encrypted = encrypt_source_credentials(
            camera.id,
            username=(username or "").strip(),
            password=password or "",
        )
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


def _runtime_camera_config(camera: Camera) -> RoadLensConfig:
    config = _camera_config(camera)
    try:
        return apply_source_credentials(
            config,
            camera_id=camera.id,
            encrypted_credentials=camera.source_secret_encrypted,
        )
    except (RuntimeError, ValueError, json.JSONDecodeError) as error:
        raise HTTPException(
            status_code=503,
            detail="Camera credentials could not be decrypted.",
        ) from error


def _create_camera(
    db: Session,
    workspace_id: int,
    payload: CameraCreate,
) -> Camera:
    _validate_public_source(payload.source_type, payload.source_path)
    camera_key = _unique_camera_key(
        db, workspace_id, payload.camera_key or payload.name
    )
    config = _new_camera_config(payload, camera_key)
    camera = Camera(
        workspace_id=workspace_id,
        camera_key=camera_key,
        name=payload.name.strip(),
        source_type=payload.source_type,
        source_path=payload.source_path.strip(),
        timezone=payload.timezone.strip(),
        enabled=payload.enabled,
        config_json=json.dumps(config.model_dump(mode="json")),
    )
    db.add(camera)
    db.flush()
    if payload.source_type == "rtsp":
        _save_source_credentials(
            camera,
            username=payload.source_username,
            password=payload.source_password,
        )
    return camera


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_DAYS * 24 * 60 * 60,
        httponly=True,
        samesite="lax",
        secure=os.getenv("ROADLENS_COOKIE_SECURE", "").lower() in {"1", "true", "yes"},
        path="/",
    )


def _create_login_session(db: Session, response: Response, user: User) -> None:
    token = create_session_token()
    db.add(
        AuthSession(
            token_hash=hash_session_token(token),
            user_id=user.id,
            expires_at=session_expiry(),
        )
    )
    db.commit()
    _set_session_cookie(response, token)


@router.get("/auth/session")
def auth_session(
    db: DbSession, roadlens_session: SessionCookie = None
) -> dict[str, Any]:
    user = _session_user(db, roadlens_session, required=False)
    setup_required = db.query(User.id).first() is None
    if user is None:
        return {
            "authenticated": False,
            "setup_required": setup_required,
            "user": None,
            "workspaces": [],
        }

    memberships = (
        db.query(WorkspaceMembership)
        .options(
            selectinload(WorkspaceMembership.workspace).selectinload(Workspace.cameras),
            selectinload(WorkspaceMembership.workspace).selectinload(
                Workspace.memberships
            ),
        )
        .filter(WorkspaceMembership.user_id == user.id)
        .all()
    )
    return {
        "authenticated": True,
        "setup_required": False,
        "user": _user_payload(user),
        "workspaces": [
            _workspace_payload(membership.workspace, membership.role)
            for membership in memberships
        ],
    }


@router.post("/auth/setup", status_code=201)
def setup_product(
    payload: SetupRequest,
    response: Response,
    db: DbSession,
) -> dict[str, Any]:
    if db.query(User.id).first() is not None:
        raise HTTPException(status_code=409, detail="RoadLens is already configured.")

    user = User(
        email=_normalize_email(payload.email),
        name=payload.name.strip(),
        password_hash=hash_password(payload.password),
    )
    workspace = Workspace(
        name=payload.workspace_name.strip(),
        slug=_unique_workspace_slug(db, payload.workspace_name),
        timezone=payload.timezone.strip(),
    )
    db.add_all([user, workspace])
    db.flush()
    db.add(
        WorkspaceMembership(
            user_id=user.id,
            workspace_id=workspace.id,
            role="owner",
        )
    )
    db.commit()
    _create_login_session(db, response, user)
    return {"user": _user_payload(user), "workspace_id": workspace.id}


@router.post("/auth/login")
def login(
    payload: LoginRequest,
    response: Response,
    request: Request,
    db: DbSession,
) -> dict[str, Any]:
    email = _normalize_email(payload.email)
    _auth_limiter.check(f"login:email:{email}", limit=10, window_seconds=15 * 60)
    _auth_limiter.check(
        f"login:ip:{_request_ip(request)}", limit=50, window_seconds=15 * 60
    )
    user = db.query(User).filter(User.email == email).one_or_none()
    password_matches = verify_password(
        payload.password,
        user.password_hash if user is not None else DUMMY_PASSWORD_HASH,
    )
    if user is None or not password_matches:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User account is disabled.")
    if user.mfa_enabled:
        if not payload.mfa_code:
            raise HTTPException(status_code=428, detail="MFA code required.")
        if not _consume_mfa_code(db, user, payload.mfa_code):
            raise HTTPException(status_code=401, detail="Invalid authentication code.")
        db.commit()
    _create_login_session(db, response, user)
    return {"user": _user_payload(user)}


@router.post("/auth/password-reset/request", status_code=202)
def request_password_reset(
    payload: PasswordResetRequest,
    request: Request,
    db: DbSession,
) -> dict[str, str]:
    email = _normalize_email(payload.email)
    _auth_limiter.check(f"reset:email:{email}", limit=5, window_seconds=60 * 60)
    _auth_limiter.check(
        f"reset:ip:{_request_ip(request)}", limit=20, window_seconds=60 * 60
    )
    user = db.query(User).filter(User.email == email).one_or_none()
    if user is not None and user.is_active:
        db.query(ActionToken).filter(
            ActionToken.user_id == user.id,
            ActionToken.purpose == "password_reset",
            ActionToken.used_at.is_(None),
        ).delete(synchronize_session=False)
        raw_token = _new_action_token(
            db,
            user_id=user.id,
            purpose="password_reset",
            expires_at=datetime.utcnow() + timedelta(minutes=30),
        )
        db.commit()
        try:
            send_email(
                user.email,
                "Reset your RoadLens password",
                (
                    f"Reset your password within 30 minutes:\n\n"
                    f"{_public_url(f'/reset-password?token={raw_token}')}\n\n"
                    "If you did not request this, you can ignore this email."
                ),
            )
        except Exception:
            logger.exception("Password reset email delivery failed")
    return {
        "message": (
            "If an account exists for that email, a password reset link has been sent."
        )
    }


@router.post("/auth/password-reset/confirm")
def confirm_password_reset(
    payload: PasswordResetConfirm,
    db: DbSession,
) -> dict[str, str]:
    token = _valid_action_token(db, payload.token, "password_reset")
    if token.user_id is None:
        raise HTTPException(status_code=400, detail="This link is invalid or expired.")
    user = db.get(User, token.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=400, detail="This link is invalid or expired.")
    user.password_hash = hash_password(payload.password)
    token.used_at = datetime.utcnow()
    db.query(AuthSession).filter(AuthSession.user_id == user.id).delete(
        synchronize_session=False
    )
    db.commit()
    return {"message": "Password updated. Sign in with your new password."}


@router.get("/auth/security")
def account_security(
    db: DbSession,
    roadlens_session: SessionCookie = None,
) -> dict[str, Any]:
    user = _current_user(db, roadlens_session)
    remaining_codes = (
        db.query(ActionToken)
        .filter(
            ActionToken.user_id == user.id,
            ActionToken.purpose == "mfa_recovery",
            ActionToken.used_at.is_(None),
            ActionToken.expires_at > datetime.utcnow(),
        )
        .count()
    )
    return {
        "mfa_enabled": user.mfa_enabled,
        "recovery_codes_remaining": remaining_codes,
    }


@router.post("/auth/mfa/enroll")
def enroll_mfa(
    response: Response,
    db: DbSession,
    roadlens_session: SessionCookie = None,
) -> dict[str, str]:
    user = _current_user(db, roadlens_session)
    if user.mfa_enabled:
        raise HTTPException(status_code=409, detail="MFA is already enabled.")
    secret = generate_totp_secret()
    try:
        user.mfa_secret_encrypted = encrypt_secret(secret, _mfa_context(user.id))
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    user.mfa_last_counter = None
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return {
        "secret": secret,
        "provisioning_uri": provisioning_uri(secret, user.email),
    }


@router.post("/auth/mfa/confirm")
def confirm_mfa(
    payload: MfaCodeRequest,
    response: Response,
    db: DbSession,
    roadlens_session: SessionCookie = None,
) -> dict[str, Any]:
    user = _current_user(db, roadlens_session)
    if user.mfa_enabled:
        raise HTTPException(status_code=409, detail="MFA is already enabled.")
    counter = verify_totp(_mfa_secret(user), payload.code)
    if counter is None:
        raise HTTPException(status_code=400, detail="Invalid authentication code.")
    user.mfa_enabled = True
    user.mfa_last_counter = counter
    codes = _new_recovery_codes(db, user.id)
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return {"mfa_enabled": True, "recovery_codes": codes}


@router.post("/auth/mfa/recovery-codes")
def regenerate_mfa_recovery_codes(
    payload: MfaCodeRequest,
    response: Response,
    db: DbSession,
    roadlens_session: SessionCookie = None,
) -> dict[str, Any]:
    user = _current_user(db, roadlens_session)
    if not user.mfa_enabled:
        raise HTTPException(status_code=409, detail="MFA is not enabled.")
    if not _consume_mfa_code(db, user, payload.code):
        raise HTTPException(status_code=400, detail="Invalid authentication code.")
    codes = _new_recovery_codes(db, user.id)
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return {"recovery_codes": codes}


@router.post("/auth/mfa/disable")
def disable_mfa(
    payload: MfaDisableRequest,
    db: DbSession,
    roadlens_session: SessionCookie = None,
) -> dict[str, bool]:
    user = _current_user(db, roadlens_session)
    if not user.mfa_enabled:
        raise HTTPException(status_code=409, detail="MFA is not enabled.")
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid password.")
    if not _consume_mfa_code(db, user, payload.code):
        raise HTTPException(status_code=400, detail="Invalid authentication code.")
    user.mfa_enabled = False
    user.mfa_secret_encrypted = None
    user.mfa_last_counter = None
    db.query(ActionToken).filter(
        ActionToken.user_id == user.id,
        ActionToken.purpose == "mfa_recovery",
    ).delete(synchronize_session=False)
    db.commit()
    return {"mfa_enabled": False}


@router.post("/auth/logout", status_code=204)
def logout(
    response: Response,
    db: DbSession,
    roadlens_session: SessionCookie = None,
) -> None:
    if roadlens_session:
        db.query(AuthSession).filter(
            AuthSession.token_hash == hash_session_token(roadlens_session)
        ).delete()
        db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/workspaces")
def list_workspaces(
    db: DbSession,
    roadlens_session: SessionCookie = None,
) -> dict[str, Any]:
    user = _current_user(db, roadlens_session)
    memberships = (
        db.query(WorkspaceMembership)
        .options(
            selectinload(WorkspaceMembership.workspace).selectinload(Workspace.cameras),
            selectinload(WorkspaceMembership.workspace).selectinload(
                Workspace.memberships
            ),
        )
        .filter(WorkspaceMembership.user_id == user.id)
        .all()
    )
    return {
        "items": [
            _workspace_payload(membership.workspace, membership.role)
            for membership in memberships
        ]
    }


@router.post("/workspaces", status_code=201)
def create_workspace(
    payload: WorkspaceCreate,
    db: DbSession,
    roadlens_session: SessionCookie = None,
) -> dict[str, Any]:
    user = _current_user(db, roadlens_session)
    workspace = Workspace(
        name=payload.name.strip(),
        slug=_unique_workspace_slug(db, payload.name),
        timezone=payload.timezone.strip(),
    )
    db.add(workspace)
    db.flush()
    membership = WorkspaceMembership(
        user_id=user.id, workspace_id=workspace.id, role="owner"
    )
    db.add(membership)
    db.commit()
    db.refresh(workspace)
    return _workspace_payload(workspace, membership.role)


@router.patch("/workspaces/{workspace_id}")
def update_workspace(
    workspace_id: int,
    payload: WorkspaceUpdate,
    db: DbSession,
    roadlens_session: SessionCookie = None,
) -> dict[str, Any]:
    user = _current_user(db, roadlens_session)
    membership = _membership(db, user.id, workspace_id, {"owner", "admin"})
    workspace = membership.workspace
    if payload.name is not None:
        workspace.name = payload.name.strip()
    if payload.timezone is not None:
        workspace.timezone = payload.timezone.strip()
    db.commit()
    db.refresh(workspace)
    return _workspace_payload(workspace, membership.role)


@router.get("/workspaces/{workspace_id}/members")
def list_members(
    workspace_id: int,
    db: DbSession,
    roadlens_session: SessionCookie = None,
) -> dict[str, Any]:
    user = _current_user(db, roadlens_session)
    _membership(db, user.id, workspace_id)
    memberships = (
        db.query(WorkspaceMembership)
        .options(selectinload(WorkspaceMembership.user))
        .filter(WorkspaceMembership.workspace_id == workspace_id)
        .all()
    )
    return {
        "items": [
            {**_user_payload(item.user), "role": item.role} for item in memberships
        ]
    }


def _invitation_payload(invitation: Invitation) -> dict[str, Any]:
    return {
        "id": invitation.id,
        "workspace_id": invitation.workspace_id,
        "email": invitation.email,
        "name": invitation.name,
        "role": invitation.role,
        "expires_at": invitation.expires_at.isoformat(),
        "accepted_at": (
            invitation.accepted_at.isoformat() if invitation.accepted_at else None
        ),
        "created_at": invitation.created_at.isoformat(),
    }


@router.get("/workspaces/{workspace_id}/invitations")
def list_invitations(
    workspace_id: int,
    db: DbSession,
    roadlens_session: SessionCookie = None,
) -> dict[str, Any]:
    current_user = _current_user(db, roadlens_session)
    _membership(db, current_user.id, workspace_id, {"owner", "admin"})
    invitations = (
        db.query(Invitation)
        .filter(
            Invitation.workspace_id == workspace_id,
            Invitation.accepted_at.is_(None),
            Invitation.expires_at > datetime.utcnow(),
        )
        .order_by(Invitation.created_at.desc())
        .all()
    )
    return {"items": [_invitation_payload(item) for item in invitations]}


@router.post("/workspaces/{workspace_id}/invitations", status_code=201)
def create_invitation(
    workspace_id: int,
    payload: InvitationCreate,
    request: Request,
    db: DbSession,
    roadlens_session: SessionCookie = None,
) -> dict[str, Any]:
    current_user = _current_user(db, roadlens_session)
    membership = _membership(db, current_user.id, workspace_id, {"owner", "admin"})
    _auth_limiter.check(
        f"invite:user:{current_user.id}", limit=20, window_seconds=60 * 60
    )
    _auth_limiter.check(
        f"invite:ip:{_request_ip(request)}", limit=50, window_seconds=60 * 60
    )
    email = _normalize_email(payload.email)
    existing_user = db.query(User).filter(User.email == email).one_or_none()
    if (
        existing_user is not None
        and db.query(WorkspaceMembership)
        .filter(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == existing_user.id,
        )
        .first()
    ):
        raise HTTPException(status_code=409, detail="User is already a member.")

    db.query(Invitation).filter(
        Invitation.workspace_id == workspace_id,
        Invitation.email == email,
        Invitation.accepted_at.is_(None),
    ).delete(synchronize_session=False)
    raw_token = secrets.token_urlsafe(32)
    invitation = Invitation(
        token_hash=hash_session_token(raw_token),
        workspace_id=workspace_id,
        invited_by_user_id=current_user.id,
        email=email,
        name=payload.name.strip(),
        role=payload.role,
        expires_at=datetime.utcnow() + timedelta(days=7),
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)
    try:
        send_email(
            email,
            f"Join {membership.workspace.name} on RoadLens",
            (
                f"{current_user.name} invited you to {membership.workspace.name} "
                f"as {payload.role}.\n\n"
                f"Accept within 7 days:\n"
                f"{_public_url(f'/accept-invitation?token={raw_token}')}"
            ),
        )
    except Exception as error:
        logger.exception("Invitation email delivery failed")
        raise HTTPException(
            status_code=502,
            detail="The invitation was saved, but email delivery failed.",
        ) from error
    return _invitation_payload(invitation)


@router.delete(
    "/workspaces/{workspace_id}/invitations/{invitation_id}",
    status_code=204,
)
def revoke_invitation(
    workspace_id: int,
    invitation_id: int,
    db: DbSession,
    roadlens_session: SessionCookie = None,
) -> Response:
    current_user = _current_user(db, roadlens_session)
    _membership(db, current_user.id, workspace_id, {"owner", "admin"})
    invitation = (
        db.query(Invitation)
        .filter(
            Invitation.id == invitation_id,
            Invitation.workspace_id == workspace_id,
            Invitation.accepted_at.is_(None),
        )
        .one_or_none()
    )
    if invitation is None:
        raise HTTPException(status_code=404, detail="Invitation not found.")
    db.delete(invitation)
    db.commit()
    return Response(status_code=204)


@router.get("/invitations/{token}")
def invitation_details(token: str, db: DbSession) -> dict[str, Any]:
    invitation = (
        db.query(Invitation)
        .filter(
            Invitation.token_hash == hash_session_token(token),
            Invitation.accepted_at.is_(None),
            Invitation.expires_at > datetime.utcnow(),
        )
        .one_or_none()
    )
    if invitation is None:
        raise HTTPException(
            status_code=400, detail="This invitation is invalid or expired."
        )
    workspace = db.get(Workspace, invitation.workspace_id)
    if workspace is None:
        raise HTTPException(
            status_code=400, detail="This invitation is invalid or expired."
        )
    return {
        **_invitation_payload(invitation),
        "workspace_name": workspace.name,
        "existing_account": (
            db.query(User.id).filter(User.email == invitation.email).first() is not None
        ),
        "mfa_required": (
            db.query(User.mfa_enabled).filter(User.email == invitation.email).scalar()
            is True
        ),
    }


@router.post("/auth/invitations/accept")
def accept_invitation(
    payload: InvitationAccept,
    response: Response,
    db: DbSession,
) -> dict[str, Any]:
    invitation = (
        db.query(Invitation)
        .filter(
            Invitation.token_hash == hash_session_token(payload.token),
            Invitation.accepted_at.is_(None),
            Invitation.expires_at > datetime.utcnow(),
        )
        .one_or_none()
    )
    if invitation is None:
        raise HTTPException(
            status_code=400, detail="This invitation is invalid or expired."
        )
    user = db.query(User).filter(User.email == invitation.email).one_or_none()
    if user is None:
        user = User(
            email=invitation.email,
            name=invitation.name,
            password_hash=hash_password(payload.password),
        )
        db.add(user)
        db.flush()
    elif not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=401,
            detail="Enter your existing RoadLens password to accept.",
        )
    if user.mfa_enabled:
        if not payload.mfa_code:
            raise HTTPException(status_code=428, detail="MFA code required.")
        if not _consume_mfa_code(db, user, payload.mfa_code):
            raise HTTPException(status_code=401, detail="Invalid authentication code.")
    existing = (
        db.query(WorkspaceMembership)
        .filter(
            WorkspaceMembership.workspace_id == invitation.workspace_id,
            WorkspaceMembership.user_id == user.id,
        )
        .one_or_none()
    )
    if existing is None:
        db.add(
            WorkspaceMembership(
                workspace_id=invitation.workspace_id,
                user_id=user.id,
                role=invitation.role,
            )
        )
    invitation.accepted_at = datetime.utcnow()
    db.commit()
    _create_login_session(db, response, user)
    return {"user": _user_payload(user), "workspace_id": invitation.workspace_id}


@router.post("/workspaces/{workspace_id}/members", status_code=201)
def add_member(
    workspace_id: int,
    payload: MemberCreate,
    db: DbSession,
    roadlens_session: SessionCookie = None,
) -> dict[str, Any]:
    current_user = _current_user(db, roadlens_session)
    _membership(db, current_user.id, workspace_id, {"owner", "admin"})
    email = _normalize_email(payload.email)
    user = db.query(User).filter(User.email == email).one_or_none()
    if user is None:
        if payload.password is None:
            raise HTTPException(
                status_code=422,
                detail="A temporary password is required for a new user.",
            )
        user = User(
            email=email,
            name=payload.name.strip(),
            password_hash=hash_password(payload.password),
        )
        db.add(user)
        db.flush()
    elif (
        db.query(WorkspaceMembership)
        .filter(
            WorkspaceMembership.user_id == user.id,
            WorkspaceMembership.workspace_id == workspace_id,
        )
        .first()
    ):
        raise HTTPException(status_code=409, detail="User is already a member.")

    membership = WorkspaceMembership(
        user_id=user.id,
        workspace_id=workspace_id,
        role=payload.role,
    )
    db.add(membership)
    db.commit()
    return {**_user_payload(user), "role": membership.role}


@router.patch("/workspaces/{workspace_id}/members/{user_id}")
def update_member(
    workspace_id: int,
    user_id: int,
    payload: MemberUpdate,
    db: DbSession,
    roadlens_session: SessionCookie = None,
) -> dict[str, Any]:
    current_user = _current_user(db, roadlens_session)
    _membership(db, current_user.id, workspace_id, {"owner", "admin"})
    membership = _membership(db, user_id, workspace_id)
    if membership.role == "owner" and payload.role != "owner":
        owner_count = (
            db.query(WorkspaceMembership)
            .filter(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.role == "owner",
            )
            .count()
        )
        if owner_count <= 1:
            raise HTTPException(
                status_code=409, detail="A workspace must retain an owner."
            )
    membership.role = payload.role
    db.commit()
    return {**_user_payload(membership.user), "role": membership.role}


@router.delete("/workspaces/{workspace_id}/members/{user_id}", status_code=204)
def remove_member(
    workspace_id: int,
    user_id: int,
    db: DbSession,
    roadlens_session: SessionCookie = None,
) -> Response:
    current_user = _current_user(db, roadlens_session)
    _membership(db, current_user.id, workspace_id, {"owner", "admin"})
    membership = _membership(db, user_id, workspace_id)
    if membership.role == "owner":
        owner_count = (
            db.query(WorkspaceMembership)
            .filter(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.role == "owner",
            )
            .count()
        )
        if owner_count <= 1:
            raise HTTPException(
                status_code=409, detail="A workspace must retain an owner."
            )
    db.delete(membership)
    db.commit()
    return Response(status_code=204)


@router.get("/workspaces/{workspace_id}/cameras")
def list_cameras(
    workspace_id: int,
    db: DbSession,
    roadlens_session: SessionCookie = None,
) -> dict[str, Any]:
    user = _current_user(db, roadlens_session)
    _membership(db, user.id, workspace_id)
    cameras = (
        db.query(Camera)
        .filter(Camera.workspace_id == workspace_id)
        .order_by(Camera.created_at.asc())
        .all()
    )
    return {"items": [_camera_payload(camera) for camera in cameras]}


@router.get("/workspaces/{workspace_id}/evidence")
def list_workspace_evidence(
    workspace_id: int,
    db: DbSession,
    roadlens_session: SessionCookie = None,
    camera_id: int | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    user = _current_user(db, roadlens_session)
    _membership(db, user.id, workspace_id)
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=422, detail="Limit must be between 1 and 200.")

    camera_query = db.query(Camera.id).filter(Camera.workspace_id == workspace_id)
    if camera_id is not None:
        _get_camera(db, workspace_id, camera_id)
        camera_query = camera_query.filter(Camera.id == camera_id)
    camera_ids = [row[0] for row in camera_query.all()]
    if not camera_ids:
        return {"items": [], "count": 0}

    events = (
        db.query(ViolationEvent)
        .join(Video, ViolationEvent.video_id == Video.id)
        .options(
            selectinload(ViolationEvent.artifacts),
            selectinload(ViolationEvent.detections),
        )
        .filter(Video.camera_id.in_(camera_ids))
        .order_by(ViolationEvent.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "items": [_evidence_payload(event) for event in events],
        "count": len(events),
    }


@router.post("/workspaces/{workspace_id}/cameras", status_code=201)
def create_camera(
    workspace_id: int,
    payload: CameraCreate,
    db: DbSession,
    roadlens_session: SessionCookie = None,
) -> dict[str, Any]:
    user = _current_user(db, roadlens_session)
    _membership(db, user.id, workspace_id, {"owner", "admin", "operator"})
    camera = _create_camera(db, workspace_id, payload)
    db.commit()
    db.refresh(camera)
    return _camera_payload(camera)


@router.post("/workspaces/{workspace_id}/camera-sources/video", status_code=201)
def upload_camera_video(
    workspace_id: int,
    db: DbSession,
    video: Annotated[UploadFile, File()],
    roadlens_session: SessionCookie = None,
) -> dict[str, str]:
    user = _current_user(db, roadlens_session)
    _membership(db, user.id, workspace_id, {"owner", "admin", "operator"})

    suffix = Path(video.filename or "").suffix.lower()
    allowed_suffixes = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
    if suffix not in allowed_suffixes:
        raise HTTPException(
            status_code=422,
            detail="Upload an MP4, MOV, MKV, AVI, WEBM, or M4V video.",
        )

    relative_path = Path("uploads") / str(workspace_id) / f"{uuid.uuid4().hex}{suffix}"
    destination = BACKEND_ROOT / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        with destination.open("wb") as output:
            while chunk := video.file.read(1024 * 1024):
                output.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        video.file.close()

    return {
        "source_path": relative_path.as_posix(),
        "file_name": Path(video.filename or destination.name).name,
    }


def _get_camera(db: Session, workspace_id: int, camera_id: int) -> Camera:
    camera = (
        db.query(Camera)
        .filter(Camera.workspace_id == workspace_id, Camera.id == camera_id)
        .one_or_none()
    )
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found.")
    return camera


@router.get("/workspaces/{workspace_id}/cameras/{camera_id}")
def read_camera(
    workspace_id: int,
    camera_id: int,
    db: DbSession,
    roadlens_session: SessionCookie = None,
) -> dict[str, Any]:
    user = _current_user(db, roadlens_session)
    _membership(db, user.id, workspace_id)
    camera = _get_camera(db, workspace_id, camera_id)
    return {
        **_camera_payload(camera),
        "config": _camera_config(camera).model_dump(mode="json"),
    }


@router.get("/workspaces/{workspace_id}/cameras/{camera_id}/snapshot")
def camera_snapshot(
    workspace_id: int,
    camera_id: int,
    db: DbSession,
    roadlens_session: SessionCookie = None,
) -> Response:
    user = _current_user(db, roadlens_session)
    _membership(db, user.id, workspace_id)
    camera = _get_camera(db, workspace_id, camera_id)
    try:
        snapshot = encode_snapshot(read_camera_frame(_runtime_camera_config(camera)))
    except CameraSourceError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return Response(
        content=snapshot,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/workspaces/{workspace_id}/jobs")
def list_processing_jobs(
    workspace_id: int,
    db: DbSession,
    roadlens_session: SessionCookie = None,
    camera_id: int | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    user = _current_user(db, roadlens_session)
    _membership(db, user.id, workspace_id)
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=422, detail="Limit must be between 1 and 100.")
    query = db.query(ProcessingJob).filter(ProcessingJob.workspace_id == workspace_id)
    if camera_id is not None:
        _get_camera(db, workspace_id, camera_id)
        query = query.filter(ProcessingJob.camera_id == camera_id)
    jobs = query.order_by(ProcessingJob.created_at.desc()).limit(limit).all()
    return {"items": [_job_payload(job) for job in jobs]}


@router.post("/workspaces/{workspace_id}/jobs", status_code=201)
def create_processing_job(
    workspace_id: int,
    payload: JobCreate,
    db: DbSession,
    roadlens_session: SessionCookie = None,
) -> dict[str, Any]:
    user = _current_user(db, roadlens_session)
    _membership(db, user.id, workspace_id, {"owner", "admin", "operator"})
    camera = _get_camera(db, workspace_id, payload.camera_id)
    if not camera.enabled:
        raise HTTPException(
            status_code=409, detail="Enable the camera before processing."
        )

    active = (
        db.query(ProcessingJob)
        .filter(
            ProcessingJob.workspace_id == workspace_id,
            ProcessingJob.camera_id == camera.id,
            ProcessingJob.status.in_(["queued", "running", "cancel_requested"]),
        )
        .one_or_none()
    )
    if active is not None:
        raise HTTPException(
            status_code=409,
            detail="This camera already has an active processing job.",
        )

    job = ProcessingJob(
        workspace_id=workspace_id,
        camera_id=camera.id,
        created_by_user_id=user.id,
        job_type=payload.job_type,
        status="queued",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return _job_payload(job)


@router.post("/workspaces/{workspace_id}/jobs/{job_id}/cancel")
def cancel_processing_job(
    workspace_id: int,
    job_id: int,
    db: DbSession,
    roadlens_session: SessionCookie = None,
) -> dict[str, Any]:
    user = _current_user(db, roadlens_session)
    _membership(db, user.id, workspace_id, {"owner", "admin", "operator"})
    job = (
        db.query(ProcessingJob)
        .filter(
            ProcessingJob.workspace_id == workspace_id,
            ProcessingJob.id == job_id,
        )
        .one_or_none()
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Processing job not found.")
    if job.status == "queued":
        job.status = "canceled"
        job.finished_at = datetime.utcnow()
    elif job.status == "running":
        job.status = "cancel_requested"
    elif job.status != "cancel_requested":
        raise HTTPException(
            status_code=409, detail="Processing job is already finished."
        )
    db.commit()
    db.refresh(job)
    return _job_payload(job)


@router.patch("/workspaces/{workspace_id}/cameras/{camera_id}")
def update_camera(
    workspace_id: int,
    camera_id: int,
    payload: CameraUpdate,
    db: DbSession,
    roadlens_session: SessionCookie = None,
) -> dict[str, Any]:
    user = _current_user(db, roadlens_session)
    _membership(db, user.id, workspace_id, {"owner", "admin", "operator"})
    camera = _get_camera(db, workspace_id, camera_id)
    config = _camera_config(camera)
    next_source_type = payload.source_type or camera.source_type
    next_source_path = payload.source_path or camera.source_path
    _validate_public_source(next_source_type, next_source_path)

    if payload.name is not None:
        camera.name = payload.name.strip()
        config.camera.name = camera.name
    if payload.camera_key is not None and payload.camera_key != camera.camera_key:
        camera.camera_key = _unique_camera_key(db, workspace_id, payload.camera_key)
        config.camera.id = camera.camera_key
    if payload.source_type is not None:
        camera.source_type = payload.source_type
        config.camera.source_type = payload.source_type
        if payload.source_type != "rtsp":
            camera.source_secret_encrypted = None
    if payload.source_path is not None:
        camera.source_path = payload.source_path.strip()
        config.camera.source_path = camera.source_path
    if payload.timezone is not None:
        camera.timezone = payload.timezone.strip()
        config.camera.timezone = camera.timezone
    if payload.reference_width is not None or payload.reference_height is not None:
        width, height = config.camera.reference_resolution
        config.camera.reference_resolution = (
            payload.reference_width or width,
            payload.reference_height or height,
        )
    if payload.enabled is not None:
        camera.enabled = payload.enabled
    if payload.vehicle_detector is not None:
        config.models.vehicle_detector = payload.vehicle_detector.strip()
    if payload.plate_detector is not None:
        config.models.plate_detector = payload.plate_detector.strip()
    if payload.motion_threshold is not None:
        config.frame_selection.motion_threshold = payload.motion_threshold
    if payload.cooldown_frames is not None:
        config.frame_selection.cooldown_frames = payload.cooldown_frames
    if payload.vehicle_confidence is not None:
        config.detection.vehicle_confidence = payload.vehicle_confidence
    if payload.plate_confidence is not None:
        config.detection.plate_confidence = payload.plate_confidence
    if payload.save_to_db is not None:
        config.storage.save_to_db = payload.save_to_db
    if payload.save_evidence_images is not None:
        config.storage.save_evidence_images = payload.save_evidence_images
    if payload.clear_source_credentials:
        camera.source_secret_encrypted = None
    elif camera.source_type == "rtsp":
        _save_source_credentials(
            camera,
            username=payload.source_username,
            password=payload.source_password,
        )
    camera.config_json = json.dumps(config.model_dump(mode="json"))
    db.commit()
    db.refresh(camera)
    return _camera_payload(camera)


@router.delete("/workspaces/{workspace_id}/cameras/{camera_id}", status_code=204)
def delete_camera(
    workspace_id: int,
    camera_id: int,
    db: DbSession,
    roadlens_session: SessionCookie = None,
) -> Response:
    user = _current_user(db, roadlens_session)
    _membership(db, user.id, workspace_id, {"owner", "admin"})
    camera = _get_camera(db, workspace_id, camera_id)
    db.query(Video).filter(Video.camera_id == camera.id).update({"camera_id": None})
    db.delete(camera)
    db.commit()
    return Response(status_code=204)


@router.put("/workspaces/{workspace_id}/cameras/{camera_id}/config")
def replace_camera_config(
    workspace_id: int,
    camera_id: int,
    payload: RoadLensConfig,
    db: DbSession,
    roadlens_session: SessionCookie = None,
) -> dict[str, Any]:
    user = _current_user(db, roadlens_session)
    _membership(db, user.id, workspace_id, {"owner", "admin", "operator"})
    camera = _get_camera(db, workspace_id, camera_id)
    camera.camera_key = payload.camera.id
    camera.name = payload.camera.name
    camera.source_type = payload.camera.source_type
    camera.source_path = payload.camera.source_path
    camera.timezone = payload.camera.timezone
    camera.config_json = json.dumps(payload.model_dump(mode="json"))
    db.commit()
    return {"config": payload.model_dump(mode="json")}


def _save_config(db: Session, camera: Camera, config: RoadLensConfig) -> None:
    camera.config_json = json.dumps(config.model_dump(mode="json"))
    db.commit()


@router.post("/workspaces/{workspace_id}/cameras/{camera_id}/zones", status_code=201)
def add_zone(
    workspace_id: int,
    camera_id: int,
    payload: ZoneConfig,
    db: DbSession,
    roadlens_session: SessionCookie = None,
) -> dict[str, Any]:
    user = _current_user(db, roadlens_session)
    _membership(db, user.id, workspace_id, {"owner", "admin", "operator"})
    camera = _get_camera(db, workspace_id, camera_id)
    config = _camera_config(camera)
    if any(zone.id == payload.id for zone in config.zones):
        raise HTTPException(status_code=409, detail="Zone ID already exists.")
    config.zones.append(payload)
    _save_config(db, camera, config)
    return payload.model_dump(mode="json")


@router.patch("/workspaces/{workspace_id}/cameras/{camera_id}/zones/{zone_id}")
def update_zone(
    workspace_id: int,
    camera_id: int,
    zone_id: str,
    payload: dict[str, Any],
    db: DbSession,
    roadlens_session: SessionCookie = None,
) -> dict[str, Any]:
    user = _current_user(db, roadlens_session)
    _membership(db, user.id, workspace_id, {"owner", "admin", "operator"})
    camera = _get_camera(db, workspace_id, camera_id)
    config = _camera_config(camera)
    for index, zone in enumerate(config.zones):
        if zone.id == zone_id:
            updated = ZoneConfig.model_validate(
                {**zone.model_dump(mode="json"), **payload}
            )
            config.zones[index] = updated
            _save_config(db, camera, config)
            return updated.model_dump(mode="json")
    raise HTTPException(status_code=404, detail="Zone not found.")


@router.delete(
    "/workspaces/{workspace_id}/cameras/{camera_id}/zones/{zone_id}",
    status_code=204,
)
def delete_zone(
    workspace_id: int,
    camera_id: int,
    zone_id: str,
    db: DbSession,
    roadlens_session: SessionCookie = None,
) -> Response:
    user = _current_user(db, roadlens_session)
    _membership(db, user.id, workspace_id, {"owner", "admin", "operator"})
    camera = _get_camera(db, workspace_id, camera_id)
    config = _camera_config(camera)
    remaining = [zone for zone in config.zones if zone.id != zone_id]
    if len(remaining) == len(config.zones):
        raise HTTPException(status_code=404, detail="Zone not found.")
    config.zones = remaining
    _save_config(db, camera, config)
    return Response(status_code=204)


@router.post(
    "/workspaces/{workspace_id}/cameras/{camera_id}/conditions",
    status_code=201,
)
def add_condition(
    workspace_id: int,
    camera_id: int,
    payload: ConditionConfig,
    db: DbSession,
    roadlens_session: SessionCookie = None,
) -> dict[str, Any]:
    user = _current_user(db, roadlens_session)
    _membership(db, user.id, workspace_id, {"owner", "admin", "operator"})
    camera = _get_camera(db, workspace_id, camera_id)
    config = _camera_config(camera)
    if any(condition.id == payload.id for condition in config.conditions):
        raise HTTPException(status_code=409, detail="Condition ID already exists.")
    config.conditions.append(payload)
    _save_config(db, camera, config)
    return payload.model_dump(mode="json")


@router.post("/workspaces/{workspace_id}/cameras/{camera_id}/rules", status_code=201)
def add_rule(
    workspace_id: int,
    camera_id: int,
    payload: RuleConfig,
    db: DbSession,
    roadlens_session: SessionCookie = None,
) -> dict[str, Any]:
    user = _current_user(db, roadlens_session)
    _membership(db, user.id, workspace_id, {"owner", "admin", "operator"})
    camera = _get_camera(db, workspace_id, camera_id)
    config = _camera_config(camera)
    if any(rule.id == payload.id for rule in config.rules):
        raise HTTPException(status_code=409, detail="Rule ID already exists.")
    config.rules.append(payload)
    config = RoadLensConfig.model_validate(config.model_dump(mode="json"))
    _save_config(db, camera, config)
    return payload.model_dump(mode="json")


@router.patch("/workspaces/{workspace_id}/cameras/{camera_id}/rules/{rule_id}")
def update_rule(
    workspace_id: int,
    camera_id: int,
    rule_id: str,
    payload: dict[str, Any],
    db: DbSession,
    roadlens_session: SessionCookie = None,
) -> dict[str, Any]:
    user = _current_user(db, roadlens_session)
    _membership(db, user.id, workspace_id, {"owner", "admin", "operator"})
    camera = _get_camera(db, workspace_id, camera_id)
    config = _camera_config(camera)
    for index, rule in enumerate(config.rules):
        if rule.id == rule_id:
            updated = RuleConfig.model_validate(
                {**rule.model_dump(mode="json"), **payload}
            )
            config.rules[index] = updated
            config = RoadLensConfig.model_validate(config.model_dump(mode="json"))
            _save_config(db, camera, config)
            return updated.model_dump(mode="json")
    raise HTTPException(status_code=404, detail="Rule not found.")


@router.delete(
    "/workspaces/{workspace_id}/cameras/{camera_id}/rules/{rule_id}",
    status_code=204,
)
def delete_rule(
    workspace_id: int,
    camera_id: int,
    rule_id: str,
    db: DbSession,
    roadlens_session: SessionCookie = None,
) -> Response:
    user = _current_user(db, roadlens_session)
    _membership(db, user.id, workspace_id, {"owner", "admin", "operator"})
    camera = _get_camera(db, workspace_id, camera_id)
    config = _camera_config(camera)
    remaining = [rule for rule in config.rules if rule.id != rule_id]
    if len(remaining) == len(config.rules):
        raise HTTPException(status_code=404, detail="Rule not found.")
    config.rules = remaining
    _save_config(db, camera, config)
    return Response(status_code=204)
