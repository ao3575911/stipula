"""aiogram polling adapter.

This is the only module that imports aiogram. Core tests do not need a token
or a network connection. API errors are logged by class name because Telegram
sometimes includes the bot token in the request URL.
"""

from __future__ import annotations

import io
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Message,
    Update,
)

from telegram_innovation.bot.app import StipulaApp
from telegram_innovation.bot.events import OutAck, OutDoc, Outgoing, OutInline, OutText
from telegram_innovation.bot.parse import (
    callback_from_update,
    inline_from_update,
    message_from_update,
)
from telegram_innovation.bot.ports import Directory, FileSource
from telegram_innovation.core.errors import FileTooLarge, ValidationError
from telegram_innovation.observability.logging import log_event


class AiogramFiles(FileSource):
    def __init__(self, bot: Bot, max_bytes: int) -> None:
        self.bot = bot
        self.max_bytes = max_bytes

    async def download(self, file_id: str, declared_size: int | None) -> bytes:
        if declared_size is not None and declared_size > self.max_bytes:
            raise FileTooLarge("That file is over the 20 MB Telegram download limit.")
        remote = await self.bot.get_file(file_id)
        if remote.file_size and remote.file_size > self.max_bytes:
            raise FileTooLarge("That file is over the 20 MB Telegram download limit.")
        if not remote.file_path:
            raise ValidationError("Telegram did not return that file.")
        buffer = io.BytesIO()
        await self.bot.download_file(remote.file_path, buffer)
        data = buffer.getvalue()
        if len(data) > self.max_bytes:
            raise FileTooLarge("That file is over the 20 MB Telegram download limit.")
        return data


class AiogramDirectory(Directory):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def user_id_for_username(self, username: str) -> int | None:
        try:
            chat = await self.bot.get_chat(f"@{username}")
        except TelegramAPIError:
            return None
        if chat.type != "private":
            return None
        return int(chat.id)

    async def is_chat_admin(self, chat_id: int, user_id: int) -> bool:
        try:
            member = await self.bot.get_chat_member(chat_id, user_id)
        except TelegramAPIError:
            return False
        return member.status in {"creator", "administrator"}


def message_to_update(message: Message, update_id: int) -> dict | None:
    if message.from_user is None:
        return None
    payload: dict = {
        "update_id": update_id,
        "message": {
            "message_id": message.message_id,
            "from": _user_dict(message.from_user),
            "chat": _chat_dict(message.chat),
            "text": message.text,
            "caption": message.caption,
        },
    }
    if message.document is not None:
        document = message.document
        payload["message"]["document"] = {
            "file_id": document.file_id,
            "file_name": document.file_name,
            "mime_type": document.mime_type,
            "file_size": document.file_size,
        }
    if message.photo:
        photo = message.photo[-1]
        payload["message"]["photo"] = [
            {"file_id": photo.file_id, "file_size": photo.file_size, "mime_type": "image/jpeg"}
        ]
    reply = message.reply_to_message
    if reply is not None and getattr(reply, "from_user", None) is not None:
        payload["message"]["reply_to_message"] = {
            "message_id": reply.message_id,
            "from": _user_dict(reply.from_user),
            "text": getattr(reply, "text", None),
            "caption": getattr(reply, "caption", None),
        }
        if getattr(reply, "document", None) is not None:
            document = reply.document
            payload["message"]["reply_to_message"]["document"] = {
                "file_id": document.file_id,
                "file_name": document.file_name,
                "mime_type": document.mime_type,
                "file_size": document.file_size,
            }
        if getattr(reply, "photo", None):
            photo = reply.photo[-1]
            payload["message"]["reply_to_message"]["photo"] = [{"file_id": photo.file_id, "file_size": photo.file_size}]
    return payload


def callback_to_update(query: CallbackQuery, update_id: int) -> dict | None:
    message = query.message
    if query.from_user is None or message is None or not hasattr(message, "chat"):
        return None
    return {
        "update_id": update_id,
        "callback_query": {
            "id": query.id,
            "from": _user_dict(query.from_user),
            "data": query.data or "",
            "message": {
                "message_id": message.message_id,
                "chat": _chat_dict(message.chat),
            },
        },
    }


def inline_to_update(query: InlineQuery, update_id: int) -> dict:
    return {
        "update_id": update_id,
        "inline_query": {
            "id": query.id,
            "from": _user_dict(query.from_user),
            "query": query.query,
        },
    }


def _user_dict(user) -> dict:
    return {"id": user.id, "username": user.username, "first_name": user.first_name or ""}


def _chat_dict(chat) -> dict:
    raw_type = getattr(chat, "type", "private")
    chat_type = getattr(raw_type, "value", raw_type)
    return {
        "id": chat.id,
        "type": str(chat_type),
        "title": getattr(chat, "title", None),
    }


async def present(bot: Bot, outgoing: list[Outgoing], logger: logging.Logger) -> None:
    for item in outgoing:
        try:
            await _present_one(bot, item)
        except TelegramRetryAfter as exc:
            log_event(
                logger,
                logging.WARNING,
                "telegram_rate_limited",
                retry_after=int(exc.retry_after),
                method=type(item).__name__,
            )
        except TelegramAPIError as exc:
            log_event(
                logger,
                logging.ERROR,
                "telegram_api_error",
                error_type=type(exc).__name__,
                method=type(item).__name__,
            )


async def _present_one(bot: Bot, item: Outgoing) -> None:
    if isinstance(item, OutText):
        markup = None
        if item.keyboard:
            markup = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=label, callback_data=data) for label, data in row]
                    for row in item.keyboard
                ]
            )
        await bot.send_message(item.chat_id, item.text, reply_markup=markup)
        return
    if isinstance(item, OutDoc):
        await bot.send_document(
            item.chat_id,
            BufferedInputFile(item.data, filename=item.filename),
            caption=item.caption,
        )
        return
    if isinstance(item, OutAck):
        await bot.answer_callback_query(item.callback_id, text=item.text, show_alert=item.alert)
        return
    if isinstance(item, OutInline):
        results = []
        if item.title:
            results.append(
                InlineQueryResultArticle(
                    id=item.result_id[:64],
                    title=item.title[:64],
                    description=(item.description or "")[:120],
                    input_message_content=InputTextMessageContent(
                        message_text=item.message_text[:4000],
                        parse_mode=ParseMode.HTML,
                    ),
                )
            )
        await bot.answer_inline_query(
            item.query_id,
            results=results,
            cache_time=item.cache_time,
            is_personal=True,
        )


def build_dispatcher(app: StipulaApp, bot: Bot, logger: logging.Logger) -> Dispatcher:
    dispatcher = Dispatcher()

    @dispatcher.message()
    async def on_message(message: Message, event_update: Update) -> None:
        payload = message_to_update(message, event_update.update_id)
        if payload is None:
            return
        event = message_from_update(payload)
        if event is None:
            return
        await present(bot, await app.handle(event), logger)

    @dispatcher.callback_query()
    async def on_callback(query: CallbackQuery, event_update: Update) -> None:
        payload = callback_to_update(query, event_update.update_id)
        if payload is None:
            await query.answer("That button isn't attached to a chat.", show_alert=True)
            return
        event = callback_from_update(payload)
        if event is None:
            return
        await present(bot, await app.handle(event), logger)

    @dispatcher.inline_query()
    async def on_inline(query: InlineQuery, event_update: Update) -> None:
        event = inline_from_update(inline_to_update(query, event_update.update_id))
        if event is None:
            return
        await present(bot, await app.handle(event), logger)

    @dispatcher.errors()
    async def on_error(event) -> bool:
        log_event(logger, logging.ERROR, "dispatcher_error", error_type=type(event.exception).__name__)
        return True

    @dispatcher.shutdown()
    async def on_shutdown() -> None:
        log_event(logger, logging.INFO, "dispatcher_shutdown")

    return dispatcher


def make_bot(token: str) -> Bot:
    return Bot(token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
