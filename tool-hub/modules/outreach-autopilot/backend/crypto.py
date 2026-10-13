"""Encrypt mailbox secrets at rest. Never return decrypted values from the API."""

import base64
import hashlib
import hmac

from cryptography.fernet import Fernet, InvalidToken

from config import settings


def _fernet() -> Fernet:
    seed = settings.outreach_secret_key or settings.nextauth_secret or "leadgen-ai-dev-only"
    key = base64.urlsafe_b64encode(hashlib.sha256(seed.encode()).digest())
    return Fernet(key)


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode() if value else ""


def decrypt(value: str | None) -> str:
    if not value:
        return ""
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        return ""


def sign(value: str) -> str:
    """Short HMAC used for unsubscribe links so they can't be forged."""
    seed = (settings.outreach_secret_key or settings.nextauth_secret or "leadgen-ai-dev-only").encode()
    return hmac.new(seed, value.encode(), hashlib.sha256).hexdigest()[:24]
