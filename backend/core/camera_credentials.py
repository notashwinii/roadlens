from __future__ import annotations

import json
from urllib.parse import quote, urlsplit, urlunsplit

from core.config_schema import RoadLensConfig
from core.secrets import decrypt_secret, encrypt_secret


def _context(camera_id: int) -> str:
    return f"camera:{camera_id}:source"


def encrypt_source_credentials(
    camera_id: int,
    *,
    username: str,
    password: str,
) -> str:
    return encrypt_secret(
        json.dumps({"username": username, "password": password}),
        _context(camera_id),
    )


def apply_source_credentials(
    config: RoadLensConfig,
    *,
    camera_id: int,
    encrypted_credentials: str | None,
) -> RoadLensConfig:
    if config.camera.source_type != "rtsp" or not encrypted_credentials:
        return config

    credentials = json.loads(
        decrypt_secret(encrypted_credentials, _context(camera_id))
    )
    parsed = urlsplit(config.camera.source_path)
    hostname = parsed.hostname or ""
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    host = f"{hostname}:{parsed.port}" if parsed.port is not None else hostname
    username = quote(str(credentials.get("username", "")), safe="")
    password = quote(str(credentials.get("password", "")), safe="")
    userinfo = username
    if password:
        userinfo = f"{userinfo}:{password}"
    config.camera.source_path = urlunsplit(
        (parsed.scheme, f"{userinfo}@{host}", parsed.path, parsed.query, parsed.fragment)
    )
    return config
