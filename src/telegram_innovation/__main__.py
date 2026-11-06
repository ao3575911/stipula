"""CLI: run the bot, migrate, or run an offline health check."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from telegram_innovation import __version__
from telegram_innovation.bot.app import StipulaApp
from telegram_innovation.core.config import Settings, load_settings
from telegram_innovation.core.errors import ConfigError
from telegram_innovation.core.sealing import sha256_text
from telegram_innovation.features.service import StipulaService
from telegram_innovation.observability.logging import configure_logging, log_event
from telegram_innovation.security.ratelimit import RateLimiter
from telegram_innovation.storage.db import apply_migrations, connect, integrity_ok

PINNED_HELLO = "b8106aef372deb6cf179238a643201274b9b145704885f8f77de9a63b0fff629"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="telegram-innovation")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run", help="poll Telegram and serve updates")
    sub.add_parser("migrate", help="apply SQLite migrations and exit")
    check = sub.add_parser("check", help="migrate, integrity-check, and pin the hash vector")
    check.add_argument(
        "--offline",
        action="store_true",
        help="do not require BOT_TOKEN",
    )
    args = parser.parse_args(argv)
    try:
        if args.cmd == "run":
            settings = load_settings(require_token=True)
            return asyncio.run(run_bot(settings))
        if args.cmd == "migrate":
            settings = load_settings(require_token=False)
            return migrate(settings)
        if args.cmd == "check":
            settings = load_settings(require_token=not args.offline)
            return check_install(settings)
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 1


def migrate(settings: Settings) -> int:
    logger = _logger(settings)
    connection = connect(settings.database_path)
    try:
        applied = apply_migrations(connection)
        log_event(logger, logging.INFO, "migrations_applied", applied=applied)
    finally:
        connection.close()
    return 0


def check_install(settings: Settings) -> int:
    logger = _logger(settings)
    connection = connect(settings.database_path)
    try:
        applied = apply_migrations(connection)
        healthy = integrity_ok(connection)
        vector_ok = sha256_text("Hello, Stipula") == PINNED_HELLO
        report = {
            "version": __version__,
            "integrity": "ok" if healthy else "failed",
            "vector_ok": vector_ok,
            "migrations": applied,
            "owner_set": settings.owner_id is not None,
        }
        print(json.dumps(report))
        log_event(
            logger,
            logging.INFO if healthy and vector_ok else logging.ERROR,
            "check_complete",
            integrity=healthy,
            vector_ok=vector_ok,
        )
        return 0 if healthy and vector_ok else 1
    finally:
        connection.close()


async def run_bot(settings: Settings) -> int:
    # Imported here so `check --offline` does not require aiogram at import of tests
    # that call check_install. aiogram is still installed for a real run.
    from telegram_innovation.core.clock import SystemClock
    from telegram_innovation.integrations.telegram import (
        AiogramDirectory,
        AiogramFiles,
        build_dispatcher,
        make_bot,
    )

    logger = _logger(settings)
    if settings.log_salt == "change-me":
        log_event(logger, logging.WARNING, "log_salt_default")
    if settings.owner_id is None:
        log_event(logger, logging.WARNING, "owner_unset")
    log_event(logger, logging.INFO, "bot_starting", version=__version__)
    connection = connect(settings.database_path)
    bot = make_bot(settings.bot_token)
    try:
        apply_migrations(connection)
        if not integrity_ok(connection):
            log_event(logger, logging.ERROR, "database_unhealthy")
            raise ConfigError("SQLite integrity check failed.")
        service = StipulaService(
            connection,
            SystemClock(),
            owner_id=settings.owner_id,
            monthly_free_seals=settings.monthly_free_seals,
            free_open_commitments=settings.free_open_commitments,
            max_file_bytes=settings.max_file_bytes,
            pending_ttl=settings.pending_ttl_seconds,
        )
        app = StipulaApp(
            service,
            settings,
            AiogramFiles(bot, settings.max_file_bytes),
            AiogramDirectory(bot),
            RateLimiter(settings.rate_limit_per_minute),
            logger,
        )
        dispatcher = build_dispatcher(app, bot, logger)
        log_event(logger, logging.INFO, "polling_started")
        await dispatcher.start_polling(bot)
        return 0
    finally:
        log_event(logger, logging.INFO, "bot_stopping")
        await bot.session.close()
        connection.close()


def _logger(settings: Settings):
    return configure_logging(
        level=settings.log_level,
        path=settings.log_path,
        salt=settings.log_salt,
        log_user_ids=settings.log_user_ids,
    )


if __name__ == "__main__":
    sys.exit(main())
