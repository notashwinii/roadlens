import base64
import re
from http.cookies import SimpleCookie

import sqlalchemy
from fastapi import HTTPException, Request, Response
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import api.product as product_api
from api.mfa import generate_totp, totp_counter
from api.product import (
    InvitationAccept,
    InvitationCreate,
    LoginRequest,
    MfaCodeRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    SetupRequest,
    accept_invitation,
    confirm_mfa,
    confirm_password_reset,
    create_invitation,
    enroll_mfa,
    invitation_details,
    login,
    request_password_reset,
    setup_product,
)
from api.security import hash_session_token, verify_password
from db.database import Base
from db.models import ActionToken, AuthSession, User, WorkspaceMembership


def _db():
    engine = sqlalchemy.create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [],
            "client": ("127.0.0.1", 1234),
        }
    )


def _cookie(response: Response) -> str:
    cookie = SimpleCookie()
    cookie.load(response.headers["set-cookie"])
    return cookie["roadlens_session"].value


def _setup(db, email: str = "owner@example.com") -> tuple[dict, str]:
    response = Response()
    result = setup_product(
        SetupRequest(
            name="Owner",
            email=email,
            password="secure-password",
            workspace_name="Test Workspace",
            timezone="Asia/Kathmandu",
        ),
        response,
        db,
    )
    return result, _cookie(response)


def _token_from_email(body: str, route: str) -> str:
    match = re.search(rf"{route}\?token=([^\s]+)", body)
    assert match is not None
    return match.group(1)


def test_password_reset_is_single_use_and_invalidates_existing_sessions(monkeypatch):
    db = _db()
    emails: list[str] = []
    monkeypatch.setattr(
        product_api,
        "send_email",
        lambda _to, _subject, body: emails.append(body) or "test",
    )
    try:
        _, old_session = _setup(db)
        result = request_password_reset(
            PasswordResetRequest(email="owner@example.com"),
            _request(),
            db,
        )
        raw_token = _token_from_email(emails[0], "/reset-password")
        stored = db.get(ActionToken, hash_session_token(raw_token))

        assert result["message"].startswith("If an account exists")
        assert stored is not None
        assert raw_token not in stored.token_hash

        confirmed = confirm_password_reset(
            PasswordResetConfirm(token=raw_token, password="new-secure-password"),
            db,
        )
        user = db.query(User).filter(User.email == "owner@example.com").one()

        assert confirmed["message"].startswith("Password updated")
        assert verify_password("new-secure-password", user.password_hash)
        assert db.get(AuthSession, hash_session_token(old_session)) is None

        try:
            confirm_password_reset(
                PasswordResetConfirm(token=raw_token, password="another-password"),
                db,
            )
        except HTTPException as error:
            assert error.status_code == 400
        else:
            raise AssertionError("A password reset token must only work once")
    finally:
        db.close()


def test_email_invitation_creates_membership_and_session(monkeypatch):
    db = _db()
    emails: list[str] = []
    monkeypatch.setattr(
        product_api,
        "send_email",
        lambda _to, _subject, body: emails.append(body) or "test",
    )
    try:
        setup, owner_session = _setup(db)
        invitation = create_invitation(
            setup["workspace_id"],
            InvitationCreate(
                name="New Operator",
                email="operator@example.com",
                role="operator",
            ),
            _request(),
            db,
            owner_session,
        )
        raw_token = _token_from_email(emails[0], "/accept-invitation")
        details = invitation_details(raw_token, db)
        response = Response()
        accepted = accept_invitation(
            InvitationAccept(token=raw_token, password="operator-password"),
            response,
            db,
        )
        user = db.query(User).filter(User.email == "operator@example.com").one()
        membership = db.get(
            WorkspaceMembership,
            (user.id, setup["workspace_id"]),
        )

        assert invitation["email"] == "operator@example.com"
        assert details["workspace_name"] == "Test Workspace"
        assert details["existing_account"] is False
        assert accepted["workspace_id"] == setup["workspace_id"]
        assert membership is not None
        assert membership.role == "operator"
        assert _cookie(response)
    finally:
        db.close()


def test_mfa_requires_second_factor_and_recovery_codes_are_single_use(monkeypatch):
    db = _db()
    monkeypatch.setenv(
        "ROADLENS_MASTER_KEY",
        base64.urlsafe_b64encode(b"m" * 32).decode("ascii"),
    )
    try:
        _, session = _setup(db, "mfa-owner@example.com")
        enrollment = enroll_mfa(Response(), db, session)
        code = generate_totp(enrollment["secret"])
        confirmed = confirm_mfa(MfaCodeRequest(code=code), Response(), db, session)
        recovery_code = confirmed["recovery_codes"][0]

        try:
            login(
                LoginRequest(
                    email="mfa-owner@example.com",
                    password="secure-password",
                ),
                Response(),
                _request(),
                db,
            )
        except HTTPException as error:
            assert error.status_code == 428
        else:
            raise AssertionError("MFA login must require a second factor")

        login(
            LoginRequest(
                email="mfa-owner@example.com",
                password="secure-password",
                mfa_code=recovery_code,
            ),
            Response(),
            _request(),
            db,
        )

        try:
            login(
                LoginRequest(
                    email="mfa-owner@example.com",
                    password="secure-password",
                    mfa_code=recovery_code,
                ),
                Response(),
                _request(),
                db,
            )
        except HTTPException as error:
            assert error.status_code == 401
        else:
            raise AssertionError("A recovery code must only work once")

        next_code = generate_totp(enrollment["secret"], totp_counter() + 1)
        result = login(
            LoginRequest(
                email="mfa-owner@example.com",
                password="secure-password",
                mfa_code=next_code,
            ),
            Response(),
            _request(),
            db,
        )
        assert result["user"]["mfa_enabled"] is True
    finally:
        db.close()
