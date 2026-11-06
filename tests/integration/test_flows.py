"""Command, callback, and inline flows against the application service."""

from __future__ import annotations

import json
from types import SimpleNamespace

from tests.conftest import callback, load_fixture, text_message

from telegram_innovation.bot.events import InInline, OutDoc, OutInline, OutText
from telegram_innovation.bot.parse import message_from_update
from telegram_innovation.integrations.telegram import message_to_update


def _text(outgoing) -> str:
    chunks = [item.text for item in outgoing if isinstance(item, OutText)]
    return "\n".join(chunks)


async def test_private_seal_verify_and_log_does_not_keep_text(world):
    import io
    import logging

    from telegram_innovation.observability.logging import JsonFormatter

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter("test-salt", False))
    world.logger.handlers = [handler]
    secret = "super-secret-phrase"
    await world.app.handle(text_message("/seal", update_id=1))
    sealed = await world.app.handle(text_message(secret, update_id=2))
    body = _text(sealed)
    assert "Sealed" in body
    assert secret not in stream.getvalue()
    assert "super-secret-phrase" not in body
    code = world.service.list_seals(70)[0].public_id
    checked = await world.app.handle(text_message(f"/verify {code}", update_id=3, reply_text=secret))
    assert "Match." in _text(checked)
    missed = await world.app.handle(text_message(f"/verify {code}", update_id=4, reply_text="nope"))
    assert "No match." in _text(missed)


async def test_group_reply_seal_witness_and_ignores_chatter(world):
    fixture = load_fixture("group_reply_seal")
    event = message_from_update(fixture)
    assert event is not None
    sealed = await world.app.handle(event)
    assert "Sealed" in _text(sealed)
    chatter = text_message("just talking", chat_id=-100, chat_type="supergroup", update_id=200)
    assert await world.app.handle(chatter) == []
    code = world.service.list_seals(-100)[0].public_id
    witnessed = await world.app.handle(callback(f"wit:{code}", chat_id=-100, chat_type="supergroup", update_id=201))
    assert "Witnessed" in _text(witnessed)
    own = await world.app.handle(
        callback(f"wit:{code}", user_id=7, username="ada", chat_id=-100, chat_type="supergroup", update_id=202)
    )
    assert own[0].alert is True
    assert "can't witness" in (own[0].text or "")


async def test_commitment_and_decision_flow(world):
    world.directory.users["samuel"] = 8
    proposed = await world.app.handle(text_message("/commit @samuel 2026-12-01 Pay the deposit -- cash", update_id=10))
    assert "proposed" in _text(proposed)
    assert "@samuel" in _text(proposed)
    code = world.service.list_commitments(7, 70)[0].public_id
    accepted = await world.app.handle(callback(f"cac:{code}", user_id=8, chat_id=70, update_id=11))
    assert "active" in _text(accepted)
    stranger = await world.app.handle(callback(f"cfu:{code}", user_id=9, username="nope", chat_id=70, update_id=12))
    assert stranger[0].alert is True
    opened = await world.app.handle(
        text_message("/decide Switch supplier?", chat_id=-50, chat_type="group", update_id=13)
    )
    assert "Open decision" in _text(opened)
    decision = world.service.list_decisions(-50)[0].public_id
    await world.app.handle(callback(f"vy:{decision}", user_id=7, chat_id=-50, chat_type="group", update_id=14))
    await world.app.handle(callback(f"vn:{decision}", user_id=8, chat_id=-50, chat_type="group", update_id=15))
    closed = await world.app.handle(text_message(f"/close {decision}", chat_id=-50, chat_type="group", update_id=16))
    assert "Closed decision" in _text(closed)
    assert world.service.audit(-50).ok
    hostile = text_message(
        "/commit <b>bold</b>",
        update_id=17,
    )
    rendered = _text(await world.app.handle(hostile))
    from html import escape

    assert "<b>bold</b>" not in rendered
    assert escape("<b>bold</b>") in rendered


async def test_owner_boundary_export_and_rate_limit(world):
    denied = await world.app.handle(text_message("/health", user_id=7, update_id=30))
    assert "only for the bot owner" in _text(denied)
    health = await world.app.handle(text_message("/health", user_id=1, username="owner", update_id=31))
    assert "Integrity" in _text(health)
    assert "123456:" not in _text(health)
    await world.app.handle(text_message("/grant 7", user_id=1, username="owner", update_id=32))
    assert world.service.quota_for(7).plan == "pro"
    exported = await world.app.handle(text_message("/export", update_id=33))
    document = next(item for item in exported if isinstance(item, OutDoc))
    payload = json.loads(document.data)
    assert payload["product"] == "stipula"
    assert "123456:" not in document.data.decode()
    world.app.limiter = __import__("telegram_innovation.security.ratelimit", fromlist=["RateLimiter"]).RateLimiter(1)
    await world.app.handle(text_message("/quota", update_id=40))
    limited = await world.app.handle(text_message("/quota", update_id=41))
    assert "Too many requests" in _text(limited)


async def test_fixture_and_aiogram_mapping_round_trip():
    event = message_from_update(load_fixture("private_seal_command"))
    assert event is not None
    assert event.text == "/seal"
    message = SimpleNamespace(
        message_id=5,
        from_user=SimpleNamespace(id=7, username="ada", first_name="Ada"),
        chat=SimpleNamespace(id=7, type="private", title=None),
        text="/seal",
        caption=None,
        document=None,
        photo=None,
        reply_to_message=None,
    )
    mapped = message_to_update(message, 100)
    assert mapped is not None
    parsed = message_from_update(mapped)
    assert parsed is not None
    assert parsed.person.id == 7
    assert parsed.text == "/seal"


async def test_inline_unknown_is_empty(world):
    found = await world.app.handle(InInline(update_id=1, query_id="q", query="", person=text_message("/start").person))
    assert isinstance(found[0], OutInline)
    assert found[0].title is not None
    missing = await world.app.handle(
        InInline(
            update_id=2,
            query_id="q2",
            query="STL-0000-0000",
            person=text_message("/start").person,
        )
    )
    assert isinstance(missing[0], OutInline)
    assert missing[0].title is None


def test_offline_check(tmp_path, monkeypatch):
    from telegram_innovation.__main__ import check_install
    from telegram_innovation.core.config import load_settings

    database = tmp_path / "stipula.sqlite3"
    monkeypatch.setenv("DATABASE_PATH", str(database))
    monkeypatch.setenv("LOG_PATH", "")
    monkeypatch.setenv("LOG_SALT", "unit")
    settings = load_settings(require_token=False)
    assert check_install(settings) == 0
    report_path = database
    assert report_path.exists()
