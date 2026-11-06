"""Shared fixtures. SQLite stays in memory; nothing talks to Telegram."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from telegram_innovation.bot.app import StipulaApp
from telegram_innovation.bot.events import Attachment, InCallback, InMessage, Person, Room
from telegram_innovation.bot.ports import MemoryDirectory, MemoryFiles
from telegram_innovation.core.clock import Clock
from telegram_innovation.core.config import Settings
from telegram_innovation.features.service import StipulaService
from telegram_innovation.observability.logging import configure_logging
from telegram_innovation.security.ratelimit import RateLimiter
from telegram_innovation.storage.db import apply_migrations, connect

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class FakeClock(Clock):
    def __init__(self, now: int = 1_700_000_000) -> None:
        self.value = now

    def now(self) -> int:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += seconds


class World:
    def __init__(self) -> None:
        self.conn = connect(":memory:")
        apply_migrations(self.conn)
        self.clock = FakeClock()
        self.service = StipulaService(
            self.conn,
            self.clock,
            owner_id=1,
            monthly_free_seals=3,
            free_open_commitments=2,
            max_file_bytes=16,
            pending_ttl=600,
        )
        self.files = MemoryFiles()
        self.directory = MemoryDirectory()
        self.logger = configure_logging(level="INFO", path=None, salt="test-salt", log_user_ids=False)
        self.settings = Settings(
            bot_token="123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef",
            owner_id=1,
            database_path=":memory:",
            log_level="INFO",
            log_path=None,
            log_user_ids=False,
            log_salt="test-salt",
            monthly_free_seals=3,
            free_open_commitments=2,
            max_file_bytes=16,
            rate_limit_per_minute=5,
            pending_ttl_seconds=600,
        )
        self.app = StipulaApp(
            self.service,
            self.settings,
            self.files,
            self.directory,
            RateLimiter(self.settings.rate_limit_per_minute),
            self.logger,
        )

    def close(self) -> None:
        self.conn.close()


@pytest.fixture
def world():
    built = World()
    yield built
    built.close()


def person(user_id: int = 7, username: str = "ada", first_name: str = "Ada") -> Person:
    return Person(id=user_id, username=username, first_name=first_name)


def room(chat_id: int = 70, chat_type: str = "private", title: str | None = None) -> Room:
    return Room(id=chat_id, type=chat_type, title=title)


def text_message(
    text: str,
    *,
    user_id: int = 7,
    username: str = "ada",
    chat_id: int = 70,
    chat_type: str = "private",
    update_id: int = 1,
    reply_text: str | None = None,
    reply_user_id: int | None = None,
    attachment: Attachment | None = None,
    reply_attachment: Attachment | None = None,
) -> InMessage:
    return InMessage(
        update_id=update_id,
        message_id=update_id,
        person=person(user_id, username),
        room=room(chat_id, chat_type, "Workshop" if chat_type != "private" else None),
        text=text,
        caption=None,
        attachment=attachment,
        reply_text=reply_text,
        reply_user_id=reply_user_id,
        reply_username=None,
        reply_attachment=reply_attachment,
    )


def callback(
    data: str,
    *,
    user_id: int = 8,
    username: str = "sam",
    chat_id: int = 70,
    update_id: int = 50,
    chat_type: str = "private",
) -> InCallback:
    return InCallback(
        update_id=update_id,
        callback_id=f"cb-{update_id}",
        data=data,
        person=person(user_id, username, "Sam"),
        room=room(chat_id, chat_type),
        message_id=1,
    )


def load_fixture(name: str) -> dict:
    payload = json.loads((FIXTURES / "updates.json").read_text(encoding="utf-8"))
    return payload[name]
