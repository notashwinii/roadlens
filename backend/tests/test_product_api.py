import asyncio
import base64
import os
from http.cookies import SimpleCookie
from io import BytesIO

import sqlalchemy
from fastapi import Response, UploadFile
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import api.product as product_api
from api.product import (
    CameraCreate,
    JobCreate,
    MemberCreate,
    SetupRequest,
    add_member,
    auth_session,
    cancel_processing_job,
    create_camera,
    create_processing_job,
    list_cameras,
    list_processing_jobs,
    setup_product,
)
from api.security import hash_password, verify_password
from db.database import Base
from db.models import Camera


def test_password_hash_round_trip_and_rejects_wrong_password():
    encoded = hash_password("strong-test-password")

    assert encoded != "strong-test-password"
    assert verify_password("strong-test-password", encoded)
    assert not verify_password("wrong-password", encoded)


def test_first_run_setup_creates_owner_workspace_without_demo_camera(
    tmp_path,
    monkeypatch,
):
    engine = sqlalchemy.create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    response = Response()

    try:
        result = setup_product(
            SetupRequest(
                name="Test Owner",
                email="OWNER@example.com",
                password="secure-password",
                workspace_name="Test Workspace",
                timezone="Asia/Kathmandu",
            ),
            response,
            db,
        )

        cookie = SimpleCookie()
        cookie.load(response.headers["set-cookie"])
        token = cookie["roadlens_session"].value
        session = auth_session(db, token)
        cameras = list_cameras(result["workspace_id"], db, token)

        assert session["authenticated"] is True
        assert session["user"]["email"] == "owner@example.com"
        assert session["workspaces"][0]["role"] == "owner"
        assert cameras["items"] == []

        backend_root = product_api.BACKEND_ROOT
        monkeypatch.setattr(product_api, "BACKEND_ROOT", tmp_path)
        upload = UploadFile(filename="traffic.mp4", file=BytesIO(b"video-bytes"))
        uploaded = asyncio.run(
            product_api.upload_camera_video(
                result["workspace_id"],
                db,
                upload,
                token,
            )
        )
        assert uploaded["file_name"] == "traffic.mp4"
        assert (tmp_path / uploaded["source_path"]).read_bytes() == b"video-bytes"
        monkeypatch.setattr(product_api, "BACKEND_ROOT", backend_root)

        camera = create_camera(
            result["workspace_id"],
            CameraCreate(
                name="Gate camera",
                source_type="video_file",
                source_path=uploaded["source_path"],
            ),
            db,
            token,
        )
        job = create_processing_job(
            result["workspace_id"],
            JobCreate(camera_id=camera["id"]),
            db,
            token,
        )
        assert job["status"] == "queued"
        assert list_processing_jobs(
            result["workspace_id"],
            db,
            token,
            camera_id=camera["id"],
        )["items"][0]["id"] == job["id"]
        canceled = cancel_processing_job(
            result["workspace_id"],
            job["id"],
            db,
            token,
        )
        assert canceled["status"] == "canceled"
        assert canceled["finished_at"] is not None

        monkeypatch.setenv(
            "ROADLENS_MASTER_KEY",
            base64.urlsafe_b64encode(b"t" * 32).decode("ascii"),
        )
        rtsp_camera = create_camera(
            result["workspace_id"],
            CameraCreate(
                name="Live gate",
                source_type="rtsp",
                source_path="rtsp://camera.local/live",
                source_username="operator",
                source_password="private-password",
            ),
            db,
            token,
        )
        stored_rtsp = db.get(Camera, rtsp_camera["id"])
        assert rtsp_camera["has_source_credentials"] is True
        assert stored_rtsp is not None
        assert stored_rtsp.source_path == "rtsp://camera.local/live"
        assert "private-password" not in stored_rtsp.source_secret_encrypted

        member = add_member(
            result["workspace_id"],
            MemberCreate(
                name="Test Operator",
                email="operator@example.com",
                password="operator-password",
                role="operator",
            ),
            db,
            token,
        )
        assert member["role"] == "operator"
    finally:
        db.close()
