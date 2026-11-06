"""Errors whose messages are written for humans and are safe to show."""

from __future__ import annotations


class StipulaError(Exception):
    """Expected failure. `safe` messages may be sent to the chat."""

    safe = True


class ValidationError(StipulaError):
    pass


class NotFound(StipulaError):
    pass


class Forbidden(StipulaError):
    pass


class Conflict(StipulaError):
    pass


class QuotaExceeded(StipulaError):
    pass


class FileTooLarge(StipulaError):
    pass


class ConfigError(StipulaError):
    """Startup configuration problem. Never include a secret in the message."""
