import base64
import hashlib
import hmac
import os
import struct
import time
from urllib.parse import quote


def generate_totp_secret() -> str:
    return base64.b32encode(os.urandom(20)).decode("ascii").rstrip("=")


def totp_counter(timestamp: int | None = None) -> int:
    return (timestamp or int(time.time())) // 30


def generate_totp(secret: str, counter: int | None = None) -> str:
    padded = secret + "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(padded, casefold=True)
    moving = totp_counter() if counter is None else counter
    digest = hmac.new(key, struct.pack(">Q", moving), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{code % 1_000_000:06d}"


def verify_totp(secret: str, code: str, last_counter: int | None = None) -> int | None:
    current = totp_counter()
    for counter in range(current - 1, current + 2):
        if last_counter is not None and counter <= last_counter:
            continue
        if hmac.compare_digest(generate_totp(secret, counter), code.strip()):
            return counter
    return None


def provisioning_uri(secret: str, email: str) -> str:
    issuer = "RoadLens"
    return (
        f"otpauth://totp/{quote(issuer)}:{quote(email)}"
        f"?secret={secret}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"
    )
