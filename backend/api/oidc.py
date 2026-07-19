from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urlencode, urlsplit
from urllib.request import Request, urlopen

import jwt

ALLOWED_ID_TOKEN_ALGORITHMS = {
    "RS256",
    "RS384",
    "RS512",
    "PS256",
    "PS384",
    "PS512",
    "ES256",
    "ES384",
    "ES512",
    "EdDSA",
}


class OidcError(RuntimeError):
    pass


@dataclass(frozen=True)
class OidcConfig:
    issuer: str
    client_id: str
    client_secret: str | None
    redirect_uri: str
    provider_name: str
    auto_provision: bool
    require_verified_email: bool


def _enabled(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def oidc_config() -> OidcConfig | None:
    issuer = os.getenv("ROADLENS_OIDC_ISSUER", "").strip().rstrip("/")
    client_id = os.getenv("ROADLENS_OIDC_CLIENT_ID", "").strip()
    if not issuer or not client_id:
        return None
    if len(issuer) > 500:
        raise OidcError("OIDC issuer is too long.")
    _require_safe_endpoint(issuer, "OIDC issuer")

    public_url = os.getenv("ROADLENS_PUBLIC_URL", "http://localhost:5173").rstrip("/")
    redirect_uri = (
        os.getenv("ROADLENS_OIDC_REDIRECT_URI", "").strip()
        or f"{public_url}/api/auth/sso/callback"
    )
    _require_safe_endpoint(redirect_uri, "OIDC redirect URI")
    return OidcConfig(
        issuer=issuer,
        client_id=client_id,
        client_secret=os.getenv("ROADLENS_OIDC_CLIENT_SECRET") or None,
        redirect_uri=redirect_uri,
        provider_name=os.getenv("ROADLENS_OIDC_PROVIDER_NAME", "Company SSO").strip()
        or "Company SSO",
        auto_provision=_enabled(os.getenv("ROADLENS_OIDC_AUTO_PROVISION")),
        require_verified_email=_enabled(
            os.getenv("ROADLENS_OIDC_REQUIRE_VERIFIED_EMAIL"),
            default=True,
        ),
    )


def _require_safe_endpoint(value: str, label: str) -> str:
    parsed = urlsplit(value)
    local_http = parsed.scheme == "http" and parsed.hostname in {
        "localhost",
        "127.0.0.1",
        "::1",
    }
    if parsed.scheme != "https" and not local_http:
        raise OidcError(f"{label} must use HTTPS outside local development.")
    if not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise OidcError(f"{label} is not a valid endpoint.")
    return value


def _fetch_json(request: Request) -> dict[str, Any]:
    try:
        with urlopen(request, timeout=10) as response:
            _require_safe_endpoint(response.geturl(), "OIDC response URL")
            raw_payload = response.read(1_048_577)
            if len(raw_payload) > 1_048_576:
                raise OidcError("The identity provider response is too large.")
            payload = json.loads(raw_payload.decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
        raise OidcError("The identity provider could not be reached.") from error
    if not isinstance(payload, dict):
        raise OidcError("The identity provider returned an invalid response.")
    return payload


@lru_cache(maxsize=8)
def discovery_document(issuer: str) -> dict[str, Any]:
    _require_safe_endpoint(issuer, "OIDC issuer")
    metadata = _fetch_json(
        Request(
            f"{issuer}/.well-known/openid-configuration",
            headers={"Accept": "application/json"},
        )
    )
    if metadata.get("issuer") != issuer:
        raise OidcError("The identity provider issuer does not match.")
    for field in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        endpoint = metadata.get(field)
        if not isinstance(endpoint, str):
            raise OidcError(f"The identity provider is missing {field}.")
        _require_safe_endpoint(endpoint, f"OIDC {field}")
    return metadata


def pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def authorization_url(
    config: OidcConfig,
    metadata: dict[str, Any],
    *,
    state: str,
    nonce: str,
    code_challenge: str,
) -> str:
    query = urlencode(
        {
            "client_id": config.client_id,
            "redirect_uri": config.redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{metadata['authorization_endpoint']}?{query}"


def exchange_code(
    config: OidcConfig,
    metadata: dict[str, Any],
    *,
    code: str,
    code_verifier: str,
) -> str:
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": config.redirect_uri,
        "client_id": config.client_id,
        "code_verifier": code_verifier,
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    methods = metadata.get("token_endpoint_auth_methods_supported")
    supported = methods if isinstance(methods, list) else ["client_secret_basic"]
    if config.client_secret and "client_secret_basic" in supported:
        basic_value = (
            f"{quote_plus(config.client_id)}:{quote_plus(config.client_secret)}"
        )
        headers["Authorization"] = "Basic " + base64.b64encode(
            basic_value.encode("utf-8")
        ).decode("ascii")
    elif config.client_secret:
        form["client_secret"] = config.client_secret
    elif "none" not in supported:
        raise OidcError("The identity provider requires a client secret.")

    tokens = _fetch_json(
        Request(
            metadata["token_endpoint"],
            data=urlencode(form).encode("utf-8"),
            headers=headers,
            method="POST",
        )
    )
    id_token = tokens.get("id_token")
    if not isinstance(id_token, str) or not id_token:
        raise OidcError("The identity provider did not return an ID token.")
    return id_token


@lru_cache(maxsize=8)
def _jwk_client(jwks_uri: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(
        jwks_uri,
        lifespan=300,
        timeout=10,
    )


def validate_id_token(
    config: OidcConfig,
    metadata: dict[str, Any],
    *,
    id_token: str,
    nonce: str,
) -> dict[str, Any]:
    try:
        algorithm = jwt.get_unverified_header(id_token).get("alg")
    except jwt.PyJWTError as error:
        raise OidcError(
            "The identity provider returned an invalid ID token."
        ) from error
    supported_algorithms = metadata.get("id_token_signing_alg_values_supported")
    provider_algorithms = (
        set(supported_algorithms)
        if isinstance(supported_algorithms, list)
        else {"RS256"}
    )
    if (
        not isinstance(algorithm, str)
        or algorithm not in ALLOWED_ID_TOKEN_ALGORITHMS
        or algorithm not in provider_algorithms
    ):
        raise OidcError("The ID token uses an unsupported signing algorithm.")

    try:
        signing_key = _jwk_client(metadata["jwks_uri"]).get_signing_key_from_jwt(
            id_token
        )
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=[algorithm],
            audience=config.client_id,
            issuer=config.issuer,
            leeway=30,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
    except jwt.PyJWTError as error:
        raise OidcError("The ID token could not be verified.") from error

    token_nonce = claims.get("nonce")
    if not isinstance(token_nonce, str) or not hmac.compare_digest(token_nonce, nonce):
        raise OidcError("The ID token nonce does not match.")
    email = claims.get("email")
    if not isinstance(email, str) or not email.strip():
        raise OidcError("The identity provider did not return an email address.")
    if config.require_verified_email and claims.get("email_verified") is not True:
        raise OidcError("The identity provider did not verify the email address.")
    audience = claims.get("aud")
    authorized_party = claims.get("azp")
    if (
        isinstance(audience, list)
        and len(audience) > 1
        and authorized_party != config.client_id
    ):
        raise OidcError("The ID token authorized party does not match.")
    if authorized_party is not None and authorized_party != config.client_id:
        raise OidcError("The ID token authorized party does not match.")
    return claims
