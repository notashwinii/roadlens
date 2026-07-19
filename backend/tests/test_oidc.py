import base64
import time
from http.cookies import SimpleCookie
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
import sqlalchemy
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Request, Response
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import api.oidc as oidc
import api.product as product_api
from api.oidc import (
    OidcError,
    authorization_url,
    discovery_document,
    exchange_code,
    oidc_config,
    pkce_challenge,
    validate_id_token,
)
from api.product import (
    InvitationCreate,
    SetupRequest,
    begin_sso_login,
    create_invitation,
    finish_sso_login,
    setup_product,
)
from api.security import hash_session_token
from db.database import Base
from db.models import ActionToken, Invitation, SsoIdentity, User, WorkspaceMembership


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
            "method": "GET",
            "path": "/api/auth/sso/login",
            "headers": [],
            "client": ("127.0.0.1", 1234),
        }
    )


def _cookie(response: Response) -> str:
    cookie = SimpleCookie()
    cookie.load(response.headers["set-cookie"])
    return cookie["roadlens_session"].value


def _configure_oidc(monkeypatch, *, auto_provision: bool = False) -> None:
    monkeypatch.setenv("ROADLENS_PUBLIC_URL", "http://localhost:5173")
    monkeypatch.setenv("ROADLENS_OIDC_ISSUER", "https://identity.example.com")
    monkeypatch.setenv("ROADLENS_OIDC_CLIENT_ID", "roadlens-client")
    monkeypatch.setenv("ROADLENS_OIDC_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("ROADLENS_OIDC_PROVIDER_NAME", "Example Identity")
    monkeypatch.setenv(
        "ROADLENS_MASTER_KEY",
        base64.urlsafe_b64encode(b"o" * 32).decode("ascii"),
    )
    monkeypatch.setenv(
        "ROADLENS_OIDC_AUTO_PROVISION",
        "true" if auto_provision else "false",
    )


def _metadata() -> dict:
    return {
        "issuer": "https://identity.example.com",
        "authorization_endpoint": "https://identity.example.com/authorize",
        "token_endpoint": "https://identity.example.com/token",
        "jwks_uri": "https://identity.example.com/jwks",
        "token_endpoint_auth_methods_supported": ["client_secret_basic"],
        "id_token_signing_alg_values_supported": ["RS256"],
    }


def _setup_owner(db) -> tuple[dict, str]:
    response = Response()
    result = setup_product(
        SetupRequest(
            name="Owner",
            email="owner@example.com",
            password="secure-password",
            workspace_name="Test Workspace",
            timezone="Asia/Kathmandu",
        ),
        response,
        db,
    )
    return result, _cookie(response)


def test_oidc_authorization_uses_discovery_state_nonce_and_pkce(monkeypatch):
    _configure_oidc(monkeypatch)
    discovery_document.cache_clear()
    monkeypatch.setattr(oidc, "_fetch_json", lambda _request: _metadata())
    config = oidc_config()

    assert config is not None
    metadata = discovery_document(config.issuer)
    url = authorization_url(
        config,
        metadata,
        state="state-token",
        nonce="nonce-token",
        code_challenge=pkce_challenge("v" * 43),
    )
    query = parse_qs(urlsplit(url).query)

    assert query["response_type"] == ["code"]
    assert query["scope"] == ["openid email profile"]
    assert query["state"] == ["state-token"]
    assert query["nonce"] == ["nonce-token"]
    assert query["code_challenge_method"] == ["S256"]


def test_oidc_id_token_validates_signature_claims_and_nonce(monkeypatch):
    _configure_oidc(monkeypatch)
    config = oidc_config()
    assert config is not None
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = int(time.time())
    id_token = jwt.encode(
        {
            "iss": config.issuer,
            "aud": config.client_id,
            "sub": "user-subject",
            "email": "owner@example.com",
            "email_verified": True,
            "nonce": "expected-nonce",
            "iat": now,
            "exp": now + 300,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )

    class FakeJwkClient:
        def __init__(self, *_args, **_kwargs):
            pass

        def get_signing_key_from_jwt(self, _token):
            return SimpleNamespace(key=private_key.public_key())

    monkeypatch.setattr(oidc.jwt, "PyJWKClient", FakeJwkClient)
    oidc._jwk_client.cache_clear()
    claims = validate_id_token(
        config,
        _metadata(),
        id_token=id_token,
        nonce="expected-nonce",
    )

    assert claims["sub"] == "user-subject"
    with pytest.raises(OidcError, match="nonce"):
        validate_id_token(
            config,
            _metadata(),
            id_token=id_token,
            nonce="wrong-nonce",
        )


def test_oidc_code_exchange_uses_pkce_and_client_secret_basic(monkeypatch):
    _configure_oidc(monkeypatch)
    config = oidc_config()
    assert config is not None
    captured = {}

    def fake_fetch(request):
        captured["authorization"] = request.get_header("Authorization")
        captured["form"] = parse_qs(request.data.decode("utf-8"))
        return {"id_token": "signed-id-token"}

    monkeypatch.setattr(oidc, "_fetch_json", fake_fetch)
    id_token = exchange_code(
        config,
        _metadata(),
        code="authorization-code",
        code_verifier="v" * 43,
    )

    assert id_token == "signed-id-token"
    assert str(captured["authorization"]).startswith("Basic ")
    assert captured["form"]["code_verifier"] == ["v" * 43]
    assert "client_secret" not in captured["form"]


def test_sso_callback_links_existing_account_and_prevents_state_replay(monkeypatch):
    _configure_oidc(monkeypatch)
    db = _db()
    try:
        _setup_owner(db)
        monkeypatch.setattr(
            product_api, "discovery_document", lambda _issuer: _metadata()
        )
        start = begin_sso_login(_request(), db)
        query = parse_qs(urlsplit(start.headers["location"]).query)
        state = query["state"][0]
        stored_state = db.get(ActionToken, hash_session_token(state))
        assert stored_state is not None
        assert "code_verifier" not in (stored_state.payload_json or "")

        monkeypatch.setattr(
            product_api, "exchange_code", lambda *_args, **_kwargs: "id-token"
        )
        monkeypatch.setattr(
            product_api,
            "validate_id_token",
            lambda *_args, **_kwargs: {
                "sub": "owner-subject",
                "email": "owner@example.com",
                "email_verified": True,
            },
        )
        callback = finish_sso_login(db, code="authorization-code", state=state)
        identity = db.query(SsoIdentity).one()
        linked_user = db.get(User, identity.user_id)

        assert callback.headers["location"] == "/"
        assert _cookie(callback)
        assert linked_user is not None
        assert linked_user.email == "owner@example.com"

        replay = finish_sso_login(db, code="authorization-code", state=state)
        assert "sso_error=" in replay.headers["location"]
        assert db.query(SsoIdentity).count() == 1
    finally:
        db.close()


def test_invited_sso_user_is_provisioned_and_added_to_workspace(monkeypatch):
    _configure_oidc(monkeypatch, auto_provision=False)
    db = _db()
    monkeypatch.setattr(product_api, "send_email", lambda *_args, **_kwargs: "test")
    monkeypatch.setattr(product_api, "discovery_document", lambda _issuer: _metadata())
    monkeypatch.setattr(
        product_api, "exchange_code", lambda *_args, **_kwargs: "id-token"
    )
    try:
        setup, owner_session = _setup_owner(db)
        create_invitation(
            setup["workspace_id"],
            InvitationCreate(
                name="SSO Operator",
                email="operator@example.com",
                role="operator",
            ),
            _request(),
            db,
            owner_session,
        )
        start = begin_sso_login(_request(), db)
        state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
        monkeypatch.setattr(
            product_api,
            "validate_id_token",
            lambda *_args, **_kwargs: {
                "sub": "operator-subject",
                "email": "operator@example.com",
                "email_verified": True,
                "name": "SSO Operator",
            },
        )
        callback = finish_sso_login(db, code="authorization-code", state=state)
        user = db.query(User).filter(User.email == "operator@example.com").one()
        membership = db.get(
            WorkspaceMembership,
            (user.id, setup["workspace_id"]),
        )
        invitation = (
            db.query(Invitation)
            .filter(Invitation.email == "operator@example.com")
            .one()
        )

        assert _cookie(callback)
        assert membership is not None
        assert membership.role == "operator"
        assert invitation.accepted_at is not None
    finally:
        db.close()
