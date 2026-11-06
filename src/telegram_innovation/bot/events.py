"""Transport-neutral events. The aiogram adapter is the only Telegram import path."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Person:
    id: int
    username: str | None
    first_name: str


@dataclass(frozen=True)
class Room:
    id: int
    type: str
    title: str | None


@dataclass(frozen=True)
class Attachment:
    file_id: str
    file_name: str | None
    mime: str | None
    file_size: int | None
    kind: str


@dataclass(frozen=True)
class InMessage:
    update_id: int
    message_id: int
    person: Person
    room: Room
    text: str | None
    caption: str | None
    attachment: Attachment | None
    reply_text: str | None
    reply_user_id: int | None
    reply_username: str | None
    reply_attachment: Attachment | None


@dataclass(frozen=True)
class InCallback:
    update_id: int
    callback_id: str
    data: str
    person: Person
    room: Room
    message_id: int


@dataclass(frozen=True)
class InInline:
    update_id: int
    query_id: str
    query: str
    person: Person


Event = InMessage | InCallback | InInline


@dataclass(frozen=True)
class OutText:
    chat_id: int
    text: str
    keyboard: list[list[tuple[str, str]]] | None = None


@dataclass(frozen=True)
class OutDoc:
    chat_id: int
    filename: str
    data: bytes
    caption: str


@dataclass(frozen=True)
class OutAck:
    callback_id: str
    text: str | None = None
    alert: bool = False


@dataclass(frozen=True)
class OutInline:
    query_id: str
    title: str | None
    description: str = ""
    message_text: str = ""
    result_id: str = "seal"
    cache_time: int = 15


Outgoing = OutText | OutDoc | OutAck | OutInline
