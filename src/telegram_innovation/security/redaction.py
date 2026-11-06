"""Strip secrets and, by default, raw Telegram ids from operational logs."""

from __future__ import annotations

import hashlib
import hmac
import re

_TOKEN = re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b")
_SENSITIVE = {
    "token",
    "bot_token",
    "secret",
    "password",
    "authorization",
    "preimage",
    "text",
    "body",
    "detail",
    "title",
    "question",
    "caption",
    "filename",
}
_ID_KEYS = {"user_id", "actor_id", "counterparty_id", "creator_id", "owner_id", "chat_id"}


def redact_text(value: str) -> str:
    return _TOKEN.sub("[redacted-token]", value)


def user_ref(salt: str, raw_id: int) -> str:
    digest = hmac.new(salt.encode("utf-8"), str(int(raw_id)).encode("ascii"), hashlib.sha256)
    return digest.hexdigest()[:12]


def redact_field(key: str, value: object, *, salt: str, log_user_ids: bool) -> object:
    lowered = key.lower()
    if lowered in _SENSITIVE or "token" in lowered or "secret" in lowered:
        return "[redacted]"
    if not log_user_ids and lowered in _ID_KEYS and isinstance(value, int):
        return user_ref(salt, value)
    if isinstance(value, str):
        return redact_text(value)
    return value
