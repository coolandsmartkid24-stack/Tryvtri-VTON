"""Password hashing and admin session tokens.

PBKDF2-HMAC-SHA256 is used instead of bcrypt so the backend has no compiled
dependency (the package must install cleanly on Windows and on the Linux
inference image alike).  Parameters follow the OWASP 2023 guidance.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Any, Dict, Optional

import jwt

from ..config import get_settings
from .errors import Unauthorized

PBKDF2_ITERATIONS = 310_000
_PBKDF2_DIGEST = "sha256"
_SALT_BYTES = 16


# --------------------------------------------------------------- passwords --
def hash_password(password: str, *, salt: Optional[bytes] = None) -> str:
    if not password:
        raise ValueError("password must not be empty")
    salt = salt or secrets.token_bytes(_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac(
        _PBKDF2_DIGEST, password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return f"pbkdf2${PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        return False
    try:
        dk = hashlib.pbkdf2_hmac(
            _PBKDF2_DIGEST, password.encode("utf-8"), salt, int(iterations)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(dk, expected)


def password_strength_ok(password: str) -> bool:
    """Minimum bar for admin passwords configured through the environment."""
    return isinstance(password, str) and len(password) >= 10


# ------------------------------------------------------------------- tokens --
def create_admin_token(
    username: str,
    *,
    role: str = "admin",
    ttl_minutes: Optional[int] = None,
    token_id: Optional[str] = None,
) -> str:
    settings = get_settings()
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET is not configured")
    ttl = ttl_minutes if ttl_minutes is not None else settings.jwt_ttl_minutes
    now = int(time.time())
    payload: Dict[str, Any] = {
        "sub": username,
        "role": role,
        "iat": now,
        "exp": now + ttl * 60,
        "jti": token_id or secrets.token_urlsafe(16),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_admin_token(token: str) -> Dict[str, Any]:
    settings = get_settings()
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET is not configured")
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise Unauthorized("Your session has expired. Please sign in again.")
    except jwt.InvalidTokenError:
        raise Unauthorized("Invalid session token.")
    if not payload.get("sub"):
        raise Unauthorized("Invalid session token.")
    return payload


def bearer_token(authorization: Optional[str]) -> str:
    if not authorization:
        raise Unauthorized("Missing Authorization header.")
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise Unauthorized("Authorization header must be 'Bearer <token>'.")
    return parts[1].strip()
