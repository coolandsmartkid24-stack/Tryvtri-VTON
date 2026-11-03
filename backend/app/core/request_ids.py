"""Request ids and idempotency helpers."""

from __future__ import annotations

import re
import secrets
import uuid
from typing import Optional

_IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


def new_request_id() -> str:
    return uuid.uuid4().hex


def new_idempotency_key() -> str:
    return f"idem-{secrets.token_urlsafe(18)}"


def normalise_idempotency_key(value: Optional[str]) -> Optional[str]:
    """Return a cleaned key, or ``None`` when the caller supplied junk.

    An idempotency key lets a customer retry a network-interrupted try-on
    without burning a second free try.
    """
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if not _IDEMPOTENCY_RE.match(value):
        return None
    return value
