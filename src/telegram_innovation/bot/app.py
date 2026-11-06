"""Command and callback application. No Telegram types in this module."""

from __future__ import annotations

import logging
import time

from telegram_innovation.bot.events import (
    Attachment,
    Event,
    InCallback,
    InInline,
    InMessage,
    OutAck,
    OutDoc,
    Outgoing,
    OutInline,
    OutText,
)
from telegram_innovation.bot.parse import (
    commitment_code,
    decision_code,
    parse_commit,
    seal_code,
    split_command,
    start_seal,
)
from telegram_innovation.bot.ports import Directory, FileSource
from telegram_innovation.bot.render import (
    FILE_NOTE,
    GROUP_PENDING,
    PHOTO_NOTE,
    commitment_keyboard,
    decision_keyboard,
    e,
    render_audit,
    render_commitment,
    render_decision,
    render_health,
    render_help,
    render_quota,
    render_seal,
    render_settings_help,
    render_start,
    render_verify,
    render_witness,
    seal_keyboard,
)
from telegram_innovation.core.config import Settings
from telegram_innovation.core.errors import NotFound, StipulaError, ValidationError
from telegram_innovation.core.models import Commitment, Decision, Seal
from telegram_innovation.features.service import StipulaService, dumps_export
from telegram_innovation.observability.logging import correlation_id, log_event
from telegram_innovation.security.ratelimit import RateLimiter

_VOTE = {"vy": "yes", "vn": "no", "va": "abstain"}
_COMMIT_ACTION = {
    "cac": "accept",
    "cde": "decline",
    "cfu": "fulfill",
    "cca": "cancel",
}


class StipulaApp:
    def __init__(
        self,
        service: StipulaService,
        settings: Settings,
        files: FileSource,
        directory: Directory,
        limiter: RateLimiter,
        logger: logging.Logger,
    ) -> None:
        self.service = service
        self.settings = settings
        self.files = files
        self.directory = directory
        self.limiter = limiter
        self.logger = logger

    async def handle(self, event: Event) -> list[Outgoing]:
        token = correlation_id.set(f"u{event.update_id}")
        started = time.perf_counter()
        try:
            if not self.limiter.allow(event.person.id, self.service.clock.now()):
                log_event(
                    self.logger,
                    logging.WARNING,
                    "rate_limited",
                    user_id=event.person.id,
                    update_id=event.update_id,
                )
                return self._limited(event)
            try:
                outgoing = await self._dispatch(event)
            except StipulaError as exc:
                log_event(
                    self.logger,
                    logging.INFO,
                    "rejected",
                    user_id=event.person.id,
                    update_id=event.update_id,
                    outcome=type(exc).__name__,
                    duration_ms=_millis(started),
                )
                return self._tell(event, str(exc), alert=True)
            except Exception:
                self.logger.exception("handler_failed")
                return self._tell(event, self._generic(), alert=True)
            log_event(
                self.logger,
                logging.INFO,
                "handled",
                user_id=event.person.id,
                update_id=event.update_id,
                outcome="ok",
                duration_ms=_millis(started),
            )
            return outgoing
        finally:
            correlation_id.reset(token)

    async def _dispatch(self, event: Event) -> list[Outgoing]:
        if isinstance(event, InCallback):
            return await self._callback(event)
        if isinstance(event, InInline):
            return [self._inline(event)]
        return await self._message(event)

    async def _message(self, message: InMessage) -> list[Outgoing]:
        self.service.touch_user(message.person.id, message.person.username, message.person.first_name)
        self.service.touch_chat(message.room.id, message.room.type, message.room.title)
        command = split_command(message.text)
        if command:
            name, args = command
            log_event(self.logger, logging.INFO, "command", command=name, user_id=message.person.id)
            return await self._command(message, name, args)
        pending = self.service.get_pending(message.room.id, message.person.id)
        if pending and pending.action == "seal":
            outgoing = await self._seal_current(message)
            self.service.clear_pending(message.room.id, message.person.id)
            return outgoing
        if pending and pending.action == "verify" and pending.payload:
            outgoing = await self._verify_current(message, pending.payload)
            self.service.clear_pending(message.room.id, message.person.id)
            return outgoing
        if message.room.type == "private":
            return [self._text(message.room.id, "Send /seal, or /help for the full list.")]
        return []

    async def _command(self, message: InMessage, name: str, args: str) -> list[Outgoing]:
        if name == "start":
            linked = start_seal(args)
            if linked:
                return [self._text(message.room.id, self._show_seal(linked, message))]
            return [self._text(message.room.id, render_start())]
        if name in {"help", "commands"}:
            return [self._text(message.room.id, render_help())]
        if name == "seal":
            return await self._cmd_seal(message)
        if name == "verify":
            return await self._cmd_verify(message, args)
        if name == "show":
            return [self._text(message.room.id, self._show_any(args, message))]
        if name == "witness":
            return self._cmd_witness(message, args)
        if name == "seals":
            return [self._text(message.room.id, self._cmd_seals(message))]
        if name == "audit":
            return [self._text(message.room.id, render_audit(self.service.audit(message.room.id)))]
        if name == "commit":
            return await self._cmd_commit(message, args)
        if name == "commitments":
            return [self._text(message.room.id, self._cmd_commitments(message))]
        if name == "fulfill":
            code = commitment_code(args)
            if code is None:
                raise ValidationError("Usage: /fulfill CMT-XXXX-XXXX")
            return self._transition(message.room.id, code, message.person.id, "fulfill", message.update_id)
        if name == "cancel" and commitment_code(args):
            return self._transition(
                message.room.id,
                commitment_code(args) or "",
                message.person.id,
                "cancel",
                message.update_id,
            )
        if name == "cancel":
            self.service.clear_pending(message.room.id, message.person.id)
            return [self._text(message.room.id, "Pending action cleared.")]
        if name == "decide":
            return self._cmd_decide(message, args)
        if name == "decisions":
            return [self._text(message.room.id, self._cmd_decisions(message))]
        if name == "close":
            return await self._cmd_close(message, args)
        if name == "export":
            return [self._cmd_export(message)]
        if name == "forget":
            return [
                self._text(
                    message.room.id,
                    "This deletes private copies of notes you sealed. "
                    "Hashes stay so a saved original can still be checked. "
                    "Shared commitments are not erased.",
                    [[("Delete my note copies", "fgt:1")]],
                )
            ]
        if name == "settings":
            return [self._text(message.room.id, self._cmd_settings(message, args))]
        if name == "quota":
            return [self._text(message.room.id, render_quota(self.service.settings_snapshot(message.person.id)))]
        if name == "health":
            return [self._text(message.room.id, self._cmd_health(message))]
        if name == "grant":
            return [self._text(message.room.id, self._cmd_grant(message, args, "pro"))]
        if name == "revoke":
            return [self._text(message.room.id, self._cmd_grant(message, args, "free"))]
        return [self._text(message.room.id, "Unknown command. /help lists the ones I know.")]

    async def _cmd_seal(self, message: InMessage) -> list[Outgoing]:
        if message.reply_attachment or message.reply_text:
            return await self._seal_reply(message)
        self.service.set_pending(message.room.id, message.person.id, "seal", None)
        text = "Send the next message or file and I'll seal it."
        if message.room.type != "private":
            text = f"{text}\n\n{GROUP_PENDING}"
        return [self._text(message.room.id, text)]

    async def _seal_reply(self, message: InMessage) -> list[Outgoing]:
        if message.reply_attachment:
            data = await self.files.download(message.reply_attachment.file_id, message.reply_attachment.file_size)
            seal = self.service.seal_file(
                chat_id=message.room.id,
                chat_type=message.room.type,
                chat_title=message.room.title,
                actor_id=message.person.id,
                data=data,
                filename=message.reply_attachment.file_name,
                mime=message.reply_attachment.mime,
                update_id=message.update_id,
            )
            return [self._seal_out(message.room.id, seal, message.reply_attachment)]
        seal = self.service.seal_text(
            chat_id=message.room.id,
            chat_type=message.room.type,
            chat_title=message.room.title,
            actor_id=message.person.id,
            text=message.reply_text or "",
            update_id=message.update_id,
        )
        return [self._seal_out(message.room.id, seal, None)]

    async def _seal_current(self, message: InMessage) -> list[Outgoing]:
        if message.attachment:
            data = await self.files.download(message.attachment.file_id, message.attachment.file_size)
            seal = self.service.seal_file(
                chat_id=message.room.id,
                chat_type=message.room.type,
                chat_title=message.room.title,
                actor_id=message.person.id,
                data=data,
                filename=message.attachment.file_name,
                mime=message.attachment.mime,
                update_id=message.update_id,
            )
            return [self._seal_out(message.room.id, seal, message.attachment)]
        body = message.text or message.caption
        if body is None:
            raise ValidationError("Send text or a file to seal.")
        seal = self.service.seal_text(
            chat_id=message.room.id,
            chat_type=message.room.type,
            chat_title=message.room.title,
            actor_id=message.person.id,
            text=body,
            update_id=message.update_id,
        )
        return [self._seal_out(message.room.id, seal, None)]

    async def _cmd_verify(self, message: InMessage, args: str) -> list[Outgoing]:
        code = seal_code(args)
        if code is None:
            raise ValidationError("Usage: /verify STL-XXXX-XXXX, then resend the original bytes.")
        self.service.get_seal(code)
        if message.reply_attachment or message.reply_text is not None:
            return await self._verify_reply(message, code)
        self.service.set_pending(message.room.id, message.person.id, "verify", code)
        follow = "Send the original text or file."
        if message.room.type != "private":
            follow = f"{follow}\n\n{GROUP_PENDING}"
        return [self._text(message.room.id, f"Checking <code>{code}</code>.\n{follow}")]

    async def _verify_reply(self, message: InMessage, code: str) -> list[Outgoing]:
        if message.reply_attachment:
            data = await self.files.download(message.reply_attachment.file_id, message.reply_attachment.file_size)
            result = self.service.verify_bytes(code, data)
        else:
            result = self.service.verify_text(code, message.reply_text or "")
        return [self._text(message.room.id, render_verify(result.matched, result.public_id))]

    async def _verify_current(self, message: InMessage, code: str) -> list[Outgoing]:
        if message.attachment:
            data = await self.files.download(message.attachment.file_id, message.attachment.file_size)
            result = self.service.verify_bytes(code, data)
        else:
            body = message.text if message.text is not None else message.caption
            if body is None:
                raise ValidationError("Send the original text or file.")
            result = self.service.verify_text(code, body)
        return [self._text(message.room.id, render_verify(result.matched, result.public_id))]

    def _cmd_witness(self, message: InMessage, args: str) -> list[Outgoing]:
        code = seal_code(args)
        if code is None:
            raise ValidationError("Usage: /witness STL-XXXX-XXXX")
        witness = self.service.witness(public_id=code, user_id=message.person.id, chat_id=message.room.id)
        return [self._text(message.room.id, render_witness(witness, self.service.label_for(message.person.id)))]

    def _cmd_seals(self, message: InMessage) -> str:
        seals = self.service.list_seals(message.room.id)
        if not seals:
            return "No seals in this chat yet. /seal to make the first."
        lines = ["<b>Recent seals</b>"]
        for seal in seals:
            lines.append(
                f"#{seal.chain_index} <code>{e(seal.public_id)}</code> · "
                f"{e(seal.kind)} · {seal.witness_count} witnesses"
            )
        return "\n".join(lines)

    async def _cmd_commit(self, message: InMessage, args: str) -> list[Outgoing]:
        parsed = parse_commit(args)
        if message.reply_user_id and parsed.username:
            raise ValidationError("Reply to someone or type @name, not both.")
        if message.reply_user_id:
            counterparty = message.reply_user_id
        elif parsed.username:
            resolved = await self.directory.user_id_for_username(parsed.username)
            if resolved is None:
                raise ValidationError("I can't resolve that username. Reply to their message with /commit instead.")
            self.service.touch_user(resolved, parsed.username, "")
            counterparty = resolved
        else:
            counterparty = message.person.id
        commitment, _seal = self.service.propose_commitment(
            chat_id=message.room.id,
            chat_type=message.room.type,
            chat_title=message.room.title,
            creator_id=message.person.id,
            counterparty_id=counterparty,
            title=parsed.title,
            detail=parsed.detail,
            due_on=parsed.due_on,
            update_id=message.update_id,
        )
        return [self._commitment_out(message.room.id, commitment)]

    def _cmd_commitments(self, message: InMessage) -> str:
        rows = self.service.list_commitments(message.person.id, message.room.id)
        if not rows:
            return "No commitments for you in this chat."
        lines = ["<b>Commitments</b>"]
        for row in rows:
            lines.append(f"<code>{e(row.public_id)}</code> · {e(row.status)} · {e(row.title)}")
        return "\n".join(lines)

    def _cmd_decide(self, message: InMessage, args: str) -> list[Outgoing]:
        if not args.strip():
            raise ValidationError("Usage: /decide the question, as one line.")
        decision, _seal = self.service.open_decision(
            chat_id=message.room.id,
            chat_type=message.room.type,
            chat_title=message.room.title,
            creator_id=message.person.id,
            question=args,
            update_id=message.update_id,
        )
        return [self._decision_out(message.room.id, decision)]

    def _cmd_decisions(self, message: InMessage) -> str:
        rows = self.service.list_decisions(message.room.id)
        if not rows:
            return "No decisions in this chat yet."
        lines = ["<b>Decisions</b>"]
        for row in rows:
            lines.append(
                f"<code>{e(row.public_id)}</code> · {e(row.status)} · {e(row.question)} "
                f"({row.yes_count}/{row.no_count}/{row.abstain_count})"
            )
        return "\n".join(lines)

    async def _cmd_close(self, message: InMessage, args: str) -> list[Outgoing]:
        code = decision_code(args)
        if code is None:
            raise ValidationError("Usage: /close DEC-XXXX-XXXX")
        as_admin = False
        decision = self.service.get_decision(code)
        if message.person.id != decision.creator_id and message.room.type != "private":
            as_admin = await self.directory.is_chat_admin(message.room.id, message.person.id)
        closed, _seal = self.service.close_decision(
            decision_id=code,
            actor_id=message.person.id,
            as_admin=as_admin,
            update_id=message.update_id,
        )
        return [self._decision_out(message.room.id, closed)]

    def _cmd_export(self, message: InMessage) -> OutDoc:
        payload = self.service.export_user(message.person.id)
        return OutDoc(
            chat_id=message.room.id,
            filename="stipula-export.json",
            data=dumps_export(payload),
            caption="Your seals, commitments, and decisions. Artefact text is included only where you kept a copy.",
        )

    def _cmd_settings(self, message: InMessage, args: str) -> str:
        parts = args.lower().split()
        if not parts:
            return render_quota(self.service.settings_snapshot(message.person.id)) + "\n\n" + render_settings_help()
        if len(parts) != 2 or parts[1] not in {"on", "off"}:
            raise ValidationError(render_settings_help())
        enabled = parts[1] == "on"
        if parts[0] == "retain":
            self.service.update_settings(message.person.id, retain=enabled)
        elif parts[0] == "username":
            self.service.update_settings(message.person.id, show_username=enabled)
        else:
            raise ValidationError(render_settings_help())
        return render_quota(self.service.settings_snapshot(message.person.id))

    def _cmd_health(self, message: InMessage) -> str:
        self._require_owner(message.person.id)
        return render_health(
            self.service.health(),
            owner_set=self.settings.owner_id is not None,
            rate_limit=self.settings.rate_limit_per_minute,
        )

    def _cmd_grant(self, message: InMessage, args: str, plan: str) -> str:
        self._require_owner(message.person.id)
        bits = args.split()
        if not bits or not bits[0].isdigit():
            raise ValidationError("Usage: /grant USER_ID or /revoke USER_ID")
        user_id = int(bits[0])
        chosen = bits[1] if len(bits) > 1 else plan
        if chosen not in {"free", "pro"}:
            raise ValidationError("Plan must be free or pro.")
        self.service.set_plan(user_id, chosen)
        log_event(
            self.logger,
            logging.INFO,
            "plan_changed",
            actor_id=message.person.id,
            user_id=user_id,
            plan=chosen,
        )
        return f"Plan for that account is now {chosen}."

    async def _callback(self, query: InCallback) -> list[Outgoing]:
        self.service.touch_user(query.person.id, query.person.username, query.person.first_name)
        prefix, _, rest = query.data.partition(":")
        if prefix == "wit":
            witness = self.service.witness(public_id=rest, user_id=query.person.id, chat_id=query.room.id)
            label = self.service.label_for(query.person.id)
            toast = "Already witnessed." if witness.already else "Witness recorded."
            return [
                OutAck(query.callback_id, toast, alert=False),
                self._text(query.room.id, render_witness(witness, label)),
            ]
        if prefix in _COMMIT_ACTION:
            return self._ack_then(
                query,
                self._transition(
                    query.room.id,
                    rest,
                    query.person.id,
                    _COMMIT_ACTION[prefix],
                    query.update_id,
                ),
            )
        if prefix in _VOTE:
            decision = self.service.vote(
                decision_id=rest,
                user_id=query.person.id,
                chat_id=query.room.id,
                choice=_VOTE[prefix],
            )
            toast = (
                f"Recorded {_VOTE[prefix]}. "
                f"{decision.yes_count} yes · {decision.no_count} no · {decision.abstain_count} abstain"
            )
            return [OutAck(query.callback_id, toast[:180], alert=False)]
        if prefix == "dcl":
            as_admin = False
            try:
                decision = self.service.get_decision(rest)
            except NotFound as exc:
                raise NotFound(str(exc)) from exc
            if query.person.id != decision.creator_id and query.room.type != "private":
                as_admin = await self.directory.is_chat_admin(query.room.id, query.person.id)
            closed, _seal = self.service.close_decision(
                decision_id=rest,
                actor_id=query.person.id,
                as_admin=as_admin,
                update_id=query.update_id,
            )
            return self._ack_then(query, [self._decision_out(query.room.id, closed)])
        if prefix == "fgt":
            removed = self.service.forget_artefacts(query.person.id)
            return [
                OutAck(query.callback_id, "Private copies deleted.", alert=False),
                self._text(
                    query.room.id,
                    f"Removed {removed} stored note(s). Hashes and shared commitments stay.",
                ),
            ]
        return [OutAck(query.callback_id, "That button has expired.", alert=True)]

    def _inline(self, query: InInline) -> OutInline:
        self.service.touch_user(query.person.id, query.person.username, query.person.first_name)
        text = query.query.strip()
        code = seal_code(text) or commitment_code(text) or decision_code(text)
        if not text:
            return OutInline(
                query_id=query.query_id,
                title="Seal a message with Stipula",
                description="Open the bot and send /seal",
                message_text=render_start(),
                result_id="help",
            )
        if code is None:
            return OutInline(query_id=query.query_id, title=None)
        try:
            body = self._show_any(code, None)
        except StipulaError:
            return OutInline(query_id=query.query_id, title=None)
        return OutInline(
            query_id=query.query_id,
            title=code,
            description="Stipula record",
            message_text=body,
            result_id=code,
        )

    def _show_any(self, args: str, message: InMessage | None) -> str:
        seal = seal_code(args)
        if seal:
            return self._show_seal(seal, message)
        commitment = commitment_code(args)
        if commitment:
            row = self.service.get_commitment(commitment)
            return render_commitment(
                row,
                creator=self.service.label_for(row.creator_id),
                counterparty=self.service.label_for(row.counterparty_id),
            )
        decision = decision_code(args)
        if decision:
            return render_decision(self.service.get_decision(decision))
        raise ValidationError("Give a STL, CMT, or DEC code.")

    def _show_seal(self, public_id: str, message: InMessage | None) -> str:
        seal = self.service.get_seal(public_id)
        note = ""
        if (
            seal.preimage
            and message is not None
            and message.room.type == "private"
            and message.person.id == seal.actor_id
        ):
            note = "Private copy still on file. It is not repeated here; use /export if you need it."
        elif seal.kind == "artefact":
            note = (
                "A private copy is stored." if seal.preimage else "No copy stored. Replay the original bytes to verify."
            )
        return render_seal(seal, note=note)

    def _transition(
        self,
        chat_id: int,
        public_id: str,
        actor_id: int,
        action: str,
        update_id: int | None,
    ) -> list[Outgoing]:
        commitment, _seal = self.service.transition_commitment(
            public_id=public_id,
            actor_id=actor_id,
            action=action,
            update_id=update_id,
        )
        return [self._commitment_out(chat_id, commitment)]

    def _commitment_out(self, chat_id: int, commitment: Commitment) -> OutText:
        same = commitment.creator_id == commitment.counterparty_id
        counterparty = "you" if same else self.service.label_for(commitment.counterparty_id)
        text = render_commitment(
            commitment,
            creator=self.service.label_for(commitment.creator_id),
            counterparty=counterparty,
        )
        return self._text(chat_id, text, commitment_keyboard(commitment))

    def _decision_out(self, chat_id: int, decision: Decision) -> OutText:
        return self._text(chat_id, render_decision(decision), decision_keyboard(decision))

    def _seal_out(self, chat_id: int, seal: Seal, attachment: Attachment | None) -> OutText:
        note = ""
        if attachment and attachment.kind == "photo":
            note = PHOTO_NOTE
        elif attachment:
            note = FILE_NOTE
        return self._text(chat_id, render_seal(seal, note=note), seal_keyboard(seal.public_id))

    def _require_owner(self, user_id: int) -> None:
        if self.settings.owner_id is None:
            log_event(self.logger, logging.WARNING, "owner_unset")
            raise ValidationError("Owner commands are off until BOT_OWNER_ID is set.")
        if user_id != self.settings.owner_id:
            log_event(
                self.logger,
                logging.WARNING,
                "authz_denied",
                user_id=user_id,
                command="owner",
            )
            raise ValidationError("That command is only for the bot owner.")

    def _text(
        self,
        chat_id: int,
        text: str,
        keyboard: list[list[tuple[str, str]]] | None = None,
    ) -> OutText:
        return OutText(chat_id=chat_id, text=text, keyboard=keyboard)

    def _tell(self, event: Event, text: str, *, alert: bool) -> list[Outgoing]:
        if isinstance(event, InCallback):
            return [OutAck(event.callback_id, text[:180], alert=alert)]
        if isinstance(event, InInline):
            return [OutInline(event.query_id, title=None)]
        if isinstance(event, InMessage):
            return [self._text(event.room.id, text)]
        return []

    def _limited(self, event: Event) -> list[Outgoing]:
        return self._tell(event, "Too many requests. Wait a minute and try again.", alert=True)

    def _generic(self) -> str:
        return f"Something went wrong. Reference {correlation_id.get()}."

    def _ack_then(self, query: InCallback, outgoing: list[Outgoing]) -> list[Outgoing]:
        return [OutAck(query.callback_id, "Updated.", alert=False), *outgoing]


def _millis(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
