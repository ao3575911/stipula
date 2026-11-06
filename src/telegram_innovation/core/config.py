"""Environment configuration. Secrets stay in the environment, never in code."""

from __future__ import annotations

import os
from dataclasses import dataclass

from telegram_innovation.core.errors import ConfigError

TELEGRAM_GETFILE_LIMIT = 20 * 1024 * 1024
_TOKEN_SHAPE = __import__("re").compile(r"^\d+:[A-Za-z0-9_-]+$")


@dataclass(frozen=True)
class Settings:
    bot_token: str
    owner_id: int | None
    database_path: str
    log_level: str
    log_path: str | None
    log_user_ids: bool
    log_salt: str
    monthly_free_seals: int
    free_open_commitments: int
    max_file_bytes: int
    rate_limit_per_minute: int
    pending_ttl_seconds: int


def _optional(env: dict[str, str], key: str, default: str) -> str:
    value = env.get(key)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def _flag(env: dict[str, str], key: str, default: bool) -> bool:
    raw = env.get(key)
    if raw is None or raw.strip() == "":
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{key} must be true or false.")


def _positive_int(env: dict[str, str], key: str, default: int) -> int:
    raw = env.get(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise ConfigError(f"{key} must be an integer.") from exc
    if value < 1:
        raise ConfigError(f"{key} must be at least 1.")
    return value


def load_settings(env: dict[str, str] | None = None, *, require_token: bool = True) -> Settings:
    source = os.environ if env is None else env
    token = source.get("BOT_TOKEN", "").strip()
    if require_token and not token:
        raise ConfigError("BOT_TOKEN is required. Copy .env.example to .env and set it.")
    if token and not _TOKEN_SHAPE.match(token):
        raise ConfigError("BOT_TOKEN does not look like a Telegram bot token.")

    owner_raw = source.get("BOT_OWNER_ID", "").strip()
    owner_id: int | None
    if not owner_raw:
        owner_id = None
    else:
        try:
            owner_id = int(owner_raw)
        except ValueError as exc:
            raise ConfigError("BOT_OWNER_ID must be a numeric Telegram user id.") from exc
        if owner_id <= 0:
            raise ConfigError("BOT_OWNER_ID must be a positive integer.")

    log_level = _optional(source, "LOG_LEVEL", "INFO").upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
        raise ConfigError("LOG_LEVEL must be DEBUG, INFO, WARNING, or ERROR.")

    log_path_raw = source.get("LOG_PATH")
    if log_path_raw is None:
        log_path: str | None = "data/stipula.log.jsonl"
    elif log_path_raw.strip() == "":
        log_path = None
    else:
        log_path = log_path_raw.strip()

    max_file = _positive_int(source, "MAX_FILE_BYTES", TELEGRAM_GETFILE_LIMIT)
    if max_file > TELEGRAM_GETFILE_LIMIT:
        raise ConfigError("MAX_FILE_BYTES cannot exceed 20971520. The Bot API getFile method refuses larger files.")

    salt = _optional(source, "LOG_SALT", "change-me")
    return Settings(
        bot_token=token,
        owner_id=owner_id,
        database_path=_optional(source, "DATABASE_PATH", "data/stipula.sqlite3"),
        log_level=log_level,
        log_path=log_path,
        log_user_ids=_flag(source, "LOG_USER_IDS", False),
        log_salt=salt,
        monthly_free_seals=_positive_int(source, "MONTHLY_FREE_SEALS", 30),
        free_open_commitments=_positive_int(source, "FREE_OPEN_COMMITMENTS", 5),
        max_file_bytes=max_file,
        rate_limit_per_minute=_positive_int(source, "RATE_LIMIT_PER_MINUTE", 20),
        pending_ttl_seconds=_positive_int(source, "PENDING_TTL_SECONDS", 600),
    )
