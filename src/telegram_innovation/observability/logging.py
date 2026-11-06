"""JSON logs with redaction. Message text is not a log field we accept."""

from __future__ import annotations

import json
import logging
import sys
import traceback
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler
from pathlib import Path

from telegram_innovation.security.redaction import redact_field, redact_text

correlation_id: ContextVar[str] = ContextVar("correlation_id", default="-")


class JsonFormatter(logging.Formatter):
    def __init__(self, salt: str, log_user_ids: bool) -> None:
        super().__init__()
        self.salt = salt
        self.log_user_ids = log_user_ids

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_text(record.getMessage()),
            "correlation_id": correlation_id.get(),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            for key, value in fields.items():
                if key in payload:
                    continue
                payload[key] = redact_field(key, value, salt=self.salt, log_user_ids=self.log_user_ids)
        if record.exc_info:
            rendered = "".join(traceback.format_exception(*record.exc_info))
            payload["error"] = redact_text(rendered)
        return json.dumps(payload, ensure_ascii=True, default=str)


def configure_logging(
    *,
    level: str,
    path: str | None,
    salt: str,
    log_user_ids: bool,
) -> logging.Logger:
    logger = logging.getLogger("stipula")
    logger.handlers.clear()
    logger.setLevel(level)
    logger.propagate = False
    formatter = JsonFormatter(salt, log_user_ids)
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(formatter)
    logger.addHandler(stream)
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        rotating = RotatingFileHandler(path, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
        rotating.setFormatter(formatter)
        logger.addHandler(rotating)
    return logger


def log_event(logger: logging.Logger, level: int, message: str, **fields: object) -> None:
    logger.log(level, message, extra={"fields": fields})
