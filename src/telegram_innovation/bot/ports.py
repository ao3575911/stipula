"""Boundaries the Telegram adapter implements and tests fake."""

from __future__ import annotations

from typing import Protocol

from telegram_innovation.core.errors import ValidationError


class FileSource(Protocol):
    async def download(self, file_id: str, declared_size: int | None) -> bytes: ...


class Directory(Protocol):
    async def user_id_for_username(self, username: str) -> int | None: ...

    async def is_chat_admin(self, chat_id: int, user_id: int) -> bool: ...


class MemoryFiles:
    def __init__(self, blobs: dict[str, bytes] | None = None) -> None:
        self.blobs = blobs or {}

    async def download(self, file_id: str, declared_size: int | None) -> bytes:
        del declared_size
        if file_id not in self.blobs:
            raise ValidationError("Telegram did not return that file.")
        return self.blobs[file_id]


class MemoryDirectory:
    def __init__(self) -> None:
        self.users: dict[str, int] = {}
        self.admins: set[tuple[int, int]] = set()

    async def user_id_for_username(self, username: str) -> int | None:
        return self.users.get(username.lower())

    async def is_chat_admin(self, chat_id: int, user_id: int) -> bool:
        return (chat_id, user_id) in self.admins
