"""Argument parsing for commands and raw update payloads."""

from __future__ import annotations

import re
from dataclasses import dataclass

from telegram_innovation.bot.events import Attachment, InCallback, InInline, InMessage, Person, Room
from telegram_innovation.core.codes import (
    COMMITMENT_CODE,
    DECISION_CODE,
    SEAL_CODE,
    find_code,
)
from telegram_innovation.core.errors import ValidationError

_COMMAND = re.compile(r"^/([a-z0-9_]+)(?:@[A-Za-z0-9_]+)?(?:\s+(.*))?$", re.DOTALL)
_USERNAME = re.compile(r"^@([A-Za-z0-9_]{5,32})\s+(.+)$", re.DOTALL)
_DUE = re.compile(r"^(\d{4}-\d{2}-\d{2})\s+(.+)$", re.DOTALL)
_START_SEAL = re.compile(r"^seal_(STL-[0-9A-HJKMNP-TV-Z]{4}-[0-9A-HJKMNP-TV-Z]{4})$")


@dataclass(frozen=True)
class CommitArgs:
    username: str | None
    due_on: str | None
    title: str
    detail: str | None


def split_command(text: str | None) -> tuple[str, str] | None:
    if not text:
        return None
    match = _COMMAND.match(text.strip())
    if not match:
        return None
    rest = match.group(2) or ""
    return match.group(1).lower(), rest.strip()


def parse_commit(args: str) -> CommitArgs:
    text = args.strip()
    username = None
    user_match = _USERNAME.match(text)
    if user_match:
        username = user_match.group(1)
        text = user_match.group(2).strip()
    due_on = None
    due_match = _DUE.match(text)
    if due_match:
        due_on = due_match.group(1)
        text = due_match.group(2).strip()
    detail = None
    if " -- " in text:
        title, raw_detail = text.split(" -- ", 1)
        detail = raw_detail.strip() or None
    else:
        title = text
    if not title.strip():
        raise ValidationError("Usage: /commit [@name] [YYYY-MM-DD] what was agreed")
    return CommitArgs(username=username, due_on=due_on, title=title.strip(), detail=detail)


def start_seal(args: str) -> str | None:
    match = _START_SEAL.match(args.strip())
    if not match:
        return None
    return match.group(1)


def code_of(pattern: re.Pattern[str], text: str) -> str | None:
    return find_code(text, pattern)


def seal_code(text: str) -> str | None:
    return find_code(text, SEAL_CODE)


def commitment_code(text: str) -> str | None:
    return find_code(text, COMMITMENT_CODE)


def decision_code(text: str) -> str | None:
    return find_code(text, DECISION_CODE)


def _person(raw: dict) -> Person | None:
    if "id" not in raw:
        return None
    return Person(
        id=int(raw["id"]),
        username=raw.get("username"),
        first_name=str(raw.get("first_name") or ""),
    )


def _room(raw: dict) -> Room:
    return Room(id=int(raw["id"]), type=str(raw.get("type") or "private"), title=raw.get("title"))


def _attachment(raw: dict | None, kind: str) -> Attachment | None:
    if not raw or "file_id" not in raw:
        return None
    size = raw.get("file_size")
    return Attachment(
        file_id=str(raw["file_id"]),
        file_name=raw.get("file_name"),
        mime=raw.get("mime_type"),
        file_size=int(size) if isinstance(size, int) else None,
        kind=kind,
    )


def _message_attachment(message: dict) -> Attachment | None:
    document = message.get("document")
    if isinstance(document, dict):
        return _attachment(document, "document")
    photos = message.get("photo")
    if isinstance(photos, list) and photos:
        last = photos[-1]
        if isinstance(last, dict):
            found = _attachment(last, "photo")
            if found and not found.mime:
                return Attachment(found.file_id, found.file_name, "image/jpeg", found.file_size, "photo")
            return found
    return None


def message_from_update(update: dict) -> InMessage | None:
    message = update.get("message")
    if not isinstance(message, dict):
        return None
    sender = message.get("from")
    chat = message.get("chat")
    if not isinstance(sender, dict) or not isinstance(chat, dict):
        return None
    person = _person(sender)
    if person is None:
        return None
    reply = message.get("reply_to_message")
    reply_text = None
    reply_user_id = None
    reply_username = None
    reply_attachment = None
    if isinstance(reply, dict):
        reply_text = reply.get("text") or reply.get("caption")
        reply_attachment = _message_attachment(reply)
        reply_from = reply.get("from")
        if isinstance(reply_from, dict) and "id" in reply_from:
            reply_user_id = int(reply_from["id"])
            reply_username = reply_from.get("username")
    return InMessage(
        update_id=int(update["update_id"]),
        message_id=int(message["message_id"]),
        person=person,
        room=_room(chat),
        text=message.get("text"),
        caption=message.get("caption"),
        attachment=_message_attachment(message),
        reply_text=reply_text,
        reply_user_id=reply_user_id,
        reply_username=reply_username,
        reply_attachment=reply_attachment,
    )


def callback_from_update(update: dict) -> InCallback | None:
    query = update.get("callback_query")
    if not isinstance(query, dict):
        return None
    sender = query.get("from")
    message = query.get("message")
    if not isinstance(sender, dict) or not isinstance(message, dict):
        return None
    person = _person(sender)
    chat = message.get("chat")
    if person is None or not isinstance(chat, dict) or "data" not in query:
        return None
    return InCallback(
        update_id=int(update["update_id"]),
        callback_id=str(query["id"]),
        data=str(query["data"]),
        person=person,
        room=_room(chat),
        message_id=int(message.get("message_id") or 0),
    )


def inline_from_update(update: dict) -> InInline | None:
    query = update.get("inline_query")
    if not isinstance(query, dict):
        return None
    sender = query.get("from")
    if not isinstance(sender, dict):
        return None
    person = _person(sender)
    if person is None:
        return None
    return InInline(
        update_id=int(update["update_id"]),
        query_id=str(query["id"]),
        query=str(query.get("query") or ""),
        person=person,
    )
