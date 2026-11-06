"""Canonical bytes, codes, redaction, rate limits, and configuration."""

from __future__ import annotations

import logging

import pytest

from telegram_innovation.core.codes import new_public_id
from telegram_innovation.core.config import load_settings
from telegram_innovation.core.errors import ConfigError
from telegram_innovation.core.sealing import (
    genesis_hash,
    seal_canonical,
    seal_digest,
    sha256_bytes,
    sha256_text,
)
from telegram_innovation.observability.logging import JsonFormatter
from telegram_innovation.security.ratelimit import RateLimiter
from telegram_innovation.security.redaction import redact_text, user_ref

HELLO = "b8106aef372deb6cf179238a643201274b9b145704885f8f77de9a63b0fff629"
GENESIS_CHAT_1 = "e446333d818c6639485f0b86eb2803bce223887f00bbc5275e22a7ee84ace403"
SAMPLE_SEAL = "34428b8992dc27d596f61dd7d2c4fedeadc8b189354aed022a62e261870ab7cf"
BYTES_HASH = "ae4b3280e56e2faf83f414a6e3dabe9d5fbe18976544c05fed121accb85b53fc"


def test_pinned_vectors():
    assert sha256_text("Hello, Stipula") == HELLO
    assert genesis_hash(1) == GENESIS_CHAT_1
    canonical = seal_canonical(
        public_id="STL-0000-0000",
        kind="artefact",
        chat_id=1,
        actor_id=7,
        content_hash=HELLO,
        prev_hash=GENESIS_CHAT_1,
        created_at=1_700_000_000,
        byte_size=14,
        filename=None,
    )
    assert seal_digest(canonical) == SAMPLE_SEAL
    assert sha256_bytes(bytes([0, 1, 2])) == BYTES_HASH


def test_code_shape(monkeypatch):
    monkeypatch.setattr("telegram_innovation.core.codes.secrets.token_bytes", lambda _n: b"\x00" * 5)
    assert new_public_id("STL") == "STL-0000-0000"


def test_redacts_bot_token_and_hashes_ids():
    leaked = "request failed for 123456789:AAHaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert "AAH" not in redact_text(leaked)
    formatter = JsonFormatter(salt="test-salt", log_user_ids=False)
    record = logging.LogRecord(
        name="stipula",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=leaked,
        args=(),
        exc_info=None,
    )
    record.fields = {"user_id": 42, "token": "should-not-appear", "command": "seal"}
    line = formatter.format(record)
    assert "AAH" not in line
    assert "should-not-appear" not in line
    assert '"user_id": 42' not in line
    assert user_ref("test-salt", 42) in line
    assert "seal" in line


def test_rate_limit_window():
    limiter = RateLimiter(2, window_seconds=60)
    assert limiter.allow(1, 1000)
    assert limiter.allow(1, 1000)
    assert not limiter.allow(1, 1000)
    assert limiter.allow(1, 1061)


def test_config_rejects_missing_and_oversized(monkeypatch):
    with pytest.raises(ConfigError):
        load_settings({}, require_token=True)
    with pytest.raises(ConfigError):
        load_settings({"BOT_TOKEN": "not-a-token"}, require_token=True)
    with pytest.raises(ConfigError):
        load_settings(
            {"BOT_TOKEN": "1:abc", "MAX_FILE_BYTES": "99999999"},
            require_token=True,
        )
    settings = load_settings({}, require_token=False)
    assert settings.bot_token == ""
    assert settings.monthly_free_seals == 30
