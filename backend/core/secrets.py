import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _master_key() -> bytes:
    encoded = os.getenv("ROADLENS_MASTER_KEY")
    if not encoded:
        raise RuntimeError("ROADLENS_MASTER_KEY is required for encrypted secrets.")
    key = base64.urlsafe_b64decode(encoded)
    if len(key) != 32:
        raise RuntimeError("ROADLENS_MASTER_KEY must decode to exactly 32 bytes.")
    return key


def encrypt_secret(value: str, context: str) -> str:
    nonce = os.urandom(12)
    ciphertext = AESGCM(_master_key()).encrypt(
        nonce, value.encode("utf-8"), context.encode("utf-8")
    )
    return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt_secret(value: str, context: str) -> str:
    payload = base64.urlsafe_b64decode(value)
    plaintext = AESGCM(_master_key()).decrypt(
        payload[:12], payload[12:], context.encode("utf-8")
    )
    return plaintext.decode("utf-8")
