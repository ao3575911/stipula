"""Transactional use cases for seals, commitments, and decisions.

SQL lives here on purpose. Each public method owns one transaction so a seal
and the row it attests cannot commit separately.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from telegram_innovation import __version__
from telegram_innovation.core.clock import Clock, month_start
from telegram_innovation.core.codes import new_public_id
from telegram_innovation.core.errors import (
    Conflict,
    FileTooLarge,
    Forbidden,
    NotFound,
    QuotaExceeded,
    ValidationError,
)
from telegram_innovation.core.models import (
    AuditProblem,
    AuditResult,
    Commitment,
    Decision,
    Pending,
    Quota,
    Seal,
    VerifyResult,
    Witness,
)
from telegram_innovation.core.sealing import (
    commitment_preimage,
    decision_close_preimage,
    decision_open_preimage,
    genesis_hash,
    same_hex,
    seal_canonical,
    seal_digest,
    sha256_bytes,
    sha256_text,
    witness_digest,
)
from telegram_innovation.storage.db import integrity_ok

_CHOICES = {"yes", "no", "abstain"}


class _Replay(Exception):
    def __init__(self, seal: Seal) -> None:
        self.seal = seal


def clean_line(value: str, *, field: str, max_len: int) -> str:
    cleaned = "".join(ch if ch >= " " else " " for ch in value)
    cleaned = " ".join(cleaned.split())
    if not cleaned:
        raise ValidationError(f"{field} is empty.")
    if len(cleaned) > max_len:
        raise ValidationError(f"{field} is too long. Maximum is {max_len} characters.")
    return cleaned


def clean_filename(name: str | None) -> str | None:
    if not name:
        return None
    cleaned = "".join(ch if ch >= " " else " " for ch in name).strip()
    if not cleaned:
        return None
    return cleaned[:120]


def valid_due(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValidationError("Due date must look like 2026-12-01.") from exc
    return value


class StipulaService:
    def __init__(
        self,
        connection: sqlite3.Connection,
        clock: Clock,
        *,
        owner_id: int | None = None,
        monthly_free_seals: int = 30,
        free_open_commitments: int = 5,
        max_file_bytes: int = 20 * 1024 * 1024,
        pending_ttl: int = 600,
    ) -> None:
        self.conn = connection
        self.clock = clock
        self.owner_id = owner_id
        self.monthly_free_seals = monthly_free_seals
        self.free_open_commitments = free_open_commitments
        self.max_file_bytes = max_file_bytes
        self.pending_ttl = pending_ttl

    def _tx(self):
        return _Transaction(self.conn)

    def touch_user(self, user_id: int, username: str | None, first_name: str) -> None:
        with self._tx():
            self._upsert_user(user_id, username, first_name)

    def touch_chat(self, chat_id: int, chat_type: str, title: str | None) -> None:
        with self._tx():
            self._ensure_chat(chat_id, chat_type, title)

    def label_for(self, user_id: int) -> str:
        row = self.conn.execute(
            "SELECT username, show_username FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if row and row["show_username"] and row["username"]:
            return f"@{row['username']}"
        return "a member"

    def set_pending(self, chat_id: int, user_id: int, action: str, payload: str | None) -> None:
        if action not in {"seal", "verify"}:
            raise ValidationError("Unknown pending action.")
        expires = self.clock.now() + self.pending_ttl
        with self._tx():
            self.conn.execute(
                """
                INSERT INTO pending (chat_id, user_id, action, payload, expires_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(chat_id, user_id) DO UPDATE SET
                    action = excluded.action,
                    payload = excluded.payload,
                    expires_at = excluded.expires_at
                """,
                (chat_id, user_id, action, payload, expires),
            )

    def clear_pending(self, chat_id: int, user_id: int) -> None:
        with self._tx():
            self.conn.execute(
                "DELETE FROM pending WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id),
            )

    def get_pending(self, chat_id: int, user_id: int) -> Pending | None:
        row = self.conn.execute(
            "SELECT * FROM pending WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        ).fetchone()
        if row is None:
            return None
        if row["expires_at"] < self.clock.now():
            self.clear_pending(chat_id, user_id)
            return None
        return Pending(
            chat_id=row["chat_id"],
            user_id=row["user_id"],
            action=row["action"],
            payload=row["payload"],
            expires_at=row["expires_at"],
        )

    def seal_text(
        self,
        *,
        chat_id: int,
        chat_type: str,
        chat_title: str | None,
        actor_id: int,
        text: str,
        update_id: int | None,
        retain: bool | None = None,
    ) -> Seal:
        if text == "":
            raise ValidationError("There is nothing to seal.")
        if len(text) > 3500:
            raise ValidationError("That message is too long to seal. Maximum is 3500 characters.")
        with self._tx():
            replay = self._replay(update_id)
            if replay:
                return replay
            self._ensure_user(actor_id, None, "")
            self._ensure_chat(chat_id, chat_type, chat_title)
            self._enforce_monthly(actor_id)
            keep = self._retain(actor_id, retain)
            return self._insert_seal(
                chat_id=chat_id,
                actor_id=actor_id,
                kind="artefact",
                action="seal",
                subject_id=None,
                content_hash=sha256_text(text),
                preimage=text if keep else None,
                filename=None,
                byte_size=len(text.encode("utf-8")),
                mime="text/plain",
                metered=True,
                update_id=update_id,
            )

    def seal_file(
        self,
        *,
        chat_id: int,
        chat_type: str,
        chat_title: str | None,
        actor_id: int,
        data: bytes,
        filename: str | None,
        mime: str | None,
        update_id: int | None,
    ) -> Seal:
        if not data:
            raise ValidationError("That file is empty.")
        if len(data) > self.max_file_bytes:
            raise FileTooLarge("That file is over the download limit. Telegram bots can only fetch files up to 20 MB.")
        with self._tx():
            replay = self._replay(update_id)
            if replay:
                return replay
            self._ensure_user(actor_id, None, "")
            self._ensure_chat(chat_id, chat_type, chat_title)
            self._enforce_monthly(actor_id)
            return self._insert_seal(
                chat_id=chat_id,
                actor_id=actor_id,
                kind="artefact",
                action="seal",
                subject_id=None,
                content_hash=sha256_bytes(data),
                preimage=None,
                filename=clean_filename(filename),
                byte_size=len(data),
                mime=(mime or "")[:80] or None,
                metered=True,
                update_id=update_id,
            )

    def witness(self, *, public_id: str, user_id: int, chat_id: int) -> Witness:
        with self._tx():
            self._ensure_user(user_id, None, "")
            row = self._seal_row(public_id)
            if row["chat_id"] != chat_id:
                raise Forbidden("Witness this from the chat that holds the seal.")
            if row["actor_id"] == user_id:
                raise Forbidden("You can't witness your own seal.")
            existing = self.conn.execute(
                """
                SELECT witness_hash, witnessed_at FROM witnesses
                WHERE seal_public_id = ? AND user_id = ?
                """,
                (public_id, user_id),
            ).fetchone()
            if existing:
                return Witness(
                    seal_public_id=public_id,
                    user_id=user_id,
                    witness_hash=existing["witness_hash"],
                    witnessed_at=existing["witnessed_at"],
                    already=True,
                    witness_count=self._witness_count(public_id),
                )
            now = self.clock.now()
            digest = witness_digest(seal_hash_hex=row["seal_hash"], user_id=user_id, witnessed_at=now)
            self.conn.execute(
                """
                INSERT INTO witnesses (seal_public_id, user_id, witness_hash, witnessed_at)
                VALUES (?, ?, ?, ?)
                """,
                (public_id, user_id, digest, now),
            )
            return Witness(
                seal_public_id=public_id,
                user_id=user_id,
                witness_hash=digest,
                witnessed_at=now,
                already=False,
                witness_count=self._witness_count(public_id),
            )

    def verify_text(self, public_id: str, text: str) -> VerifyResult:
        seal = self.get_seal(public_id)
        return VerifyResult(
            public_id=seal.public_id,
            kind=seal.kind,
            matched=same_hex(sha256_text(text), seal.content_hash),
        )

    def verify_bytes(self, public_id: str, data: bytes) -> VerifyResult:
        seal = self.get_seal(public_id)
        return VerifyResult(
            public_id=seal.public_id,
            kind=seal.kind,
            matched=same_hex(sha256_bytes(data), seal.content_hash),
        )

    def get_seal(self, public_id: str) -> Seal:
        return self._map_seal(self._seal_row(public_id))

    def list_seals(self, chat_id: int, limit: int = 8) -> list[Seal]:
        bounded = min(max(limit, 1), 20)
        rows = self.conn.execute(
            """
            SELECT * FROM seals WHERE chat_id = ?
            ORDER BY id DESC LIMIT ?
            """,
            (chat_id, bounded),
        ).fetchall()
        return [self._map_seal(row) for row in rows]

    def propose_commitment(
        self,
        *,
        chat_id: int,
        chat_type: str,
        chat_title: str | None,
        creator_id: int,
        counterparty_id: int,
        title: str,
        detail: str | None,
        due_on: str | None,
        update_id: int | None,
    ) -> tuple[Commitment, Seal]:
        title_clean = clean_line(title, field="Title", max_len=140)
        detail_clean = clean_line(detail, field="Detail", max_len=500) if detail else None
        due = valid_due(due_on)
        try:
            with self._tx():
                replay = self._replay(update_id)
                if replay and replay.subject_id:
                    return self._map_commitment(self._commitment_row(replay.subject_id)), replay
                self._ensure_user(creator_id, None, "")
                self._ensure_user(counterparty_id, None, "")
                self._ensure_chat(chat_id, chat_type, chat_title)
                self._enforce_monthly(creator_id)
                self._enforce_open_commitments(creator_id)
                if creator_id != counterparty_id:
                    self._enforce_open_commitments(counterparty_id)
                commitment_id = self._allocate("CMT")
                action = "bind" if creator_id == counterparty_id else "propose"
                status = "active" if action == "bind" else "proposed"
                preimage = commitment_preimage(
                    commitment_id=commitment_id,
                    action=action,
                    actor_id=creator_id,
                    counterparty_id=counterparty_id,
                    title=title_clean,
                    detail=detail_clean,
                    due_on=due,
                )
                now = self.clock.now()
                self.conn.execute(
                    """
                    INSERT INTO commitments (
                        public_id, chat_id, creator_id, counterparty_id, title, detail,
                        due_on, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        commitment_id,
                        chat_id,
                        creator_id,
                        counterparty_id,
                        title_clean,
                        detail_clean,
                        due,
                        status,
                        now,
                        now,
                    ),
                )
                seal = self._insert_seal(
                    chat_id=chat_id,
                    actor_id=creator_id,
                    kind="commitment",
                    action=action,
                    subject_id=commitment_id,
                    content_hash=sha256_text(preimage),
                    preimage=preimage,
                    filename=None,
                    byte_size=len(preimage.encode("utf-8")),
                    mime=None,
                    metered=True,
                    update_id=update_id,
                )
                return self._map_commitment(self._commitment_row(commitment_id)), seal
        except _Replay as caught:
            assert caught.seal.subject_id is not None
            return self._map_commitment(self._commitment_row(caught.seal.subject_id)), caught.seal

    def transition_commitment(
        self,
        *,
        public_id: str,
        actor_id: int,
        action: str,
        update_id: int | None,
    ) -> tuple[Commitment, Seal]:
        if action not in {"accept", "decline", "fulfill", "cancel"}:
            raise ValidationError("Unknown commitment action.")
        try:
            with self._tx():
                replay = self._replay(update_id)
                if replay and replay.subject_id:
                    return self._map_commitment(self._commitment_row(replay.subject_id)), replay
                self._ensure_user(actor_id, None, "")
                row = self._commitment_row(public_id)
                self._assert_transition(row, actor_id, action)
                preimage = commitment_preimage(
                    commitment_id=row["public_id"],
                    action=action,
                    actor_id=actor_id,
                    counterparty_id=row["counterparty_id"],
                    title=row["title"],
                    detail=row["detail"],
                    due_on=row["due_on"],
                )
                status = {
                    "accept": "active",
                    "decline": "declined",
                    "fulfill": "fulfilled",
                    "cancel": "cancelled",
                }[action]
                now = self.clock.now()
                self.conn.execute(
                    """
                    UPDATE commitments SET status = ?, updated_at = ? WHERE public_id = ?
                    """,
                    (status, now, public_id),
                )
                seal = self._insert_seal(
                    chat_id=row["chat_id"],
                    actor_id=actor_id,
                    kind="commitment",
                    action=action,
                    subject_id=public_id,
                    content_hash=sha256_text(preimage),
                    preimage=preimage,
                    filename=None,
                    byte_size=len(preimage.encode("utf-8")),
                    mime=None,
                    metered=False,
                    update_id=update_id,
                )
                return self._map_commitment(self._commitment_row(public_id)), seal
        except _Replay as caught:
            assert caught.seal.subject_id is not None
            return self._map_commitment(self._commitment_row(caught.seal.subject_id)), caught.seal

    def list_commitments(self, user_id: int, chat_id: int | None = None) -> list[Commitment]:
        if chat_id is None:
            rows = self.conn.execute(
                """
                SELECT * FROM commitments
                WHERE creator_id = ? OR counterparty_id = ?
                ORDER BY updated_at DESC LIMIT 20
                """,
                (user_id, user_id),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT * FROM commitments
                WHERE chat_id = ? AND (creator_id = ? OR counterparty_id = ?)
                ORDER BY updated_at DESC LIMIT 20
                """,
                (chat_id, user_id, user_id),
            ).fetchall()
        return [self._map_commitment(row) for row in rows]

    def get_commitment(self, public_id: str) -> Commitment:
        return self._map_commitment(self._commitment_row(public_id))

    def open_decision(
        self,
        *,
        chat_id: int,
        chat_type: str,
        chat_title: str | None,
        creator_id: int,
        question: str,
        update_id: int | None,
    ) -> tuple[Decision, Seal]:
        question_clean = clean_line(question, field="Question", max_len=200)
        try:
            with self._tx():
                replay = self._replay(update_id)
                if replay and replay.subject_id:
                    return self._map_decision(self._decision_row(replay.subject_id)), replay
                self._ensure_user(creator_id, None, "")
                self._ensure_chat(chat_id, chat_type, chat_title)
                self._enforce_monthly(creator_id)
                decision_id = self._allocate("DEC")
                preimage = decision_open_preimage(decision_id=decision_id, actor_id=creator_id, question=question_clean)
                now = self.clock.now()
                self.conn.execute(
                    """
                    INSERT INTO decisions (
                        public_id, chat_id, creator_id, question, status, created_at
                    ) VALUES (?, ?, ?, ?, 'open', ?)
                    """,
                    (decision_id, chat_id, creator_id, question_clean, now),
                )
                seal = self._insert_seal(
                    chat_id=chat_id,
                    actor_id=creator_id,
                    kind="decision",
                    action="open",
                    subject_id=decision_id,
                    content_hash=sha256_text(preimage),
                    preimage=preimage,
                    filename=None,
                    byte_size=len(preimage.encode("utf-8")),
                    mime=None,
                    metered=True,
                    update_id=update_id,
                )
                return self._map_decision(self._decision_row(decision_id)), seal
        except _Replay as caught:
            assert caught.seal.subject_id is not None
            return self._map_decision(self._decision_row(caught.seal.subject_id)), caught.seal

    def vote(self, *, decision_id: str, user_id: int, chat_id: int, choice: str) -> Decision:
        if choice not in _CHOICES:
            raise ValidationError("Vote must be yes, no, or abstain.")
        with self._tx():
            self._ensure_user(user_id, None, "")
            row = self._decision_row(decision_id)
            if row["chat_id"] != chat_id:
                raise Forbidden("Vote in the chat where the decision was opened.")
            if row["status"] != "open":
                raise Conflict("This decision is already closed.")
            now = self.clock.now()
            self.conn.execute(
                """
                INSERT INTO votes (decision_id, user_id, choice, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(decision_id, user_id) DO UPDATE SET
                    choice = excluded.choice,
                    created_at = excluded.created_at
                """,
                (decision_id, user_id, choice, now),
            )
            self._sync_counts(decision_id)
            return self._map_decision(self._decision_row(decision_id))

    def close_decision(
        self,
        *,
        decision_id: str,
        actor_id: int,
        as_admin: bool,
        update_id: int | None,
    ) -> tuple[Decision, Seal]:
        try:
            with self._tx():
                replay = self._replay(update_id)
                if replay and replay.subject_id:
                    return self._map_decision(self._decision_row(replay.subject_id)), replay
                self._ensure_user(actor_id, None, "")
                row = self._decision_row(decision_id)
                if row["status"] != "open":
                    raise Conflict("This decision is already closed.")
                allowed = actor_id == row["creator_id"] or actor_id == self.owner_id or as_admin
                if not allowed:
                    raise Forbidden("Only the opener or a chat admin can close this.")
                counts = self._count_votes(decision_id)
                now = self.clock.now()
                preimage = decision_close_preimage(
                    decision_id=decision_id,
                    actor_id=actor_id,
                    yes=counts["yes"],
                    no=counts["no"],
                    abstain=counts["abstain"],
                    closed_at=now,
                )
                self.conn.execute(
                    """
                    UPDATE decisions
                    SET status = 'closed', yes_count = ?, no_count = ?, abstain_count = ?,
                        closed_at = ?
                    WHERE public_id = ?
                    """,
                    (counts["yes"], counts["no"], counts["abstain"], now, decision_id),
                )
                seal = self._insert_seal(
                    chat_id=row["chat_id"],
                    actor_id=actor_id,
                    kind="decision",
                    action="close",
                    subject_id=decision_id,
                    content_hash=sha256_text(preimage),
                    preimage=preimage,
                    filename=None,
                    byte_size=len(preimage.encode("utf-8")),
                    mime=None,
                    metered=False,
                    update_id=update_id,
                )
                return self._map_decision(self._decision_row(decision_id)), seal
        except _Replay as caught:
            assert caught.seal.subject_id is not None
            return self._map_decision(self._decision_row(caught.seal.subject_id)), caught.seal

    def list_decisions(self, chat_id: int, *, include_closed: bool = True) -> list[Decision]:
        if include_closed:
            rows = self.conn.execute(
                """
                SELECT * FROM decisions WHERE chat_id = ?
                ORDER BY created_at DESC LIMIT 20
                """,
                (chat_id,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT * FROM decisions WHERE chat_id = ? AND status = 'open'
                ORDER BY created_at DESC LIMIT 20
                """,
                (chat_id,),
            ).fetchall()
        return [self._map_decision(row) for row in rows]

    def get_decision(self, public_id: str) -> Decision:
        return self._map_decision(self._decision_row(public_id))

    def audit(self, chat_id: int) -> AuditResult:
        head = genesis_hash(chat_id)
        rows = self.conn.execute(
            "SELECT * FROM seals WHERE chat_id = ? ORDER BY id",
            (chat_id,),
        ).fetchall()
        previous = head
        for index, row in enumerate(rows, start=1):
            if row["prev_hash"] != previous:
                return self._audit_fail("prev_mismatch", index, row["public_id"], previous)
            recomputed = seal_canonical(
                public_id=row["public_id"],
                kind=row["kind"],
                chat_id=row["chat_id"],
                actor_id=row["actor_id"],
                content_hash=row["content_hash"],
                prev_hash=row["prev_hash"],
                created_at=row["created_at"],
                byte_size=row["byte_size"],
                filename=row["filename"],
            )
            if recomputed != row["canonical"]:
                return self._audit_fail("canonical_drift", index, row["public_id"], previous)
            if not same_hex(seal_digest(recomputed), row["seal_hash"]):
                return self._audit_fail("seal_mismatch", index, row["public_id"], previous)
            if row["preimage"] is not None and not same_hex(sha256_text(row["preimage"]), row["content_hash"]):
                return self._audit_fail("preimage_mismatch", index, row["public_id"], previous)
            witness_problem = self._audit_witnesses(row["public_id"], row["seal_hash"])
            if witness_problem:
                return self._audit_fail(witness_problem, index, row["public_id"], previous)
            previous = row["seal_hash"]
        chat = self.conn.execute(
            "SELECT chain_head FROM chats WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
        if chat is not None and chat["chain_head"] != previous:
            return self._audit_fail("head_mismatch", None, None, previous)
        problem = self._audit_subjects(chat_id)
        if problem:
            return AuditResult(ok=False, checked=len(rows), head=previous, problem=problem)
        return AuditResult(ok=True, checked=len(rows), head=previous, problem=None)

    def quota_for(self, user_id: int) -> Quota:
        row = self.conn.execute("SELECT plan FROM users WHERE user_id = ?", (user_id,)).fetchone()
        plan = row["plan"] if row else "free"
        used = self._metered_count(user_id)
        open_count = self._open_commitment_count(user_id)
        if plan == "pro":
            return Quota(plan, used, None, open_count, None)
        return Quota(
            plan,
            used,
            self.monthly_free_seals,
            open_count,
            self.free_open_commitments,
        )

    def set_plan(self, user_id: int, plan: str) -> None:
        if plan not in {"free", "pro"}:
            raise ValidationError("Plan must be free or pro.")
        with self._tx():
            self._ensure_user(user_id, None, "")
            self.conn.execute("UPDATE users SET plan = ? WHERE user_id = ?", (plan, user_id))

    def update_settings(
        self,
        user_id: int,
        *,
        retain: bool | None = None,
        show_username: bool | None = None,
    ) -> Quota:
        with self._tx():
            self._ensure_user(user_id, None, "")
            if retain is not None:
                self.conn.execute(
                    "UPDATE users SET retain_default = ? WHERE user_id = ?",
                    (1 if retain else 0, user_id),
                )
            if show_username is not None:
                self.conn.execute(
                    "UPDATE users SET show_username = ? WHERE user_id = ?",
                    (1 if show_username else 0, user_id),
                )
        return self.quota_for(user_id)

    def settings_snapshot(self, user_id: int) -> dict[str, object]:
        row = self.conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        quota = self.quota_for(user_id)
        retain = bool(row["retain_default"]) if row else False
        show = bool(row["show_username"]) if row else True
        return {
            "plan": quota.plan,
            "used": quota.used,
            "limit": quota.limit,
            "open_commitments": quota.open_commitments,
            "open_limit": quota.open_limit,
            "retain": retain,
            "show_username": show,
        }

    def forget_artefacts(self, user_id: int) -> int:
        with self._tx():
            cursor = self.conn.execute(
                """
                UPDATE seals SET preimage = NULL
                WHERE actor_id = ? AND kind = 'artefact' AND preimage IS NOT NULL
                """,
                (user_id,),
            )
            return int(cursor.rowcount)

    def export_user(self, user_id: int, *, exported_at: int | None = None) -> dict[str, object]:
        own = self.conn.execute(
            "SELECT * FROM seals WHERE actor_id = ? ORDER BY id LIMIT 1000",
            (user_id,),
        ).fetchall()
        commitments = self.conn.execute(
            """
            SELECT * FROM commitments
            WHERE creator_id = ? OR counterparty_id = ?
            ORDER BY created_at LIMIT 500
            """,
            (user_id, user_id),
        ).fetchall()
        related_ids = [row["public_id"] for row in commitments]
        decision_rows = self.conn.execute(
            """
            SELECT * FROM decisions WHERE creator_id = ?
            UNION
            SELECT d.* FROM decisions d
            JOIN votes v ON v.decision_id = d.public_id
            WHERE v.user_id = ?
            ORDER BY created_at LIMIT 500
            """,
            (user_id, user_id),
        ).fetchall()
        related_ids.extend(row["public_id"] for row in decision_rows)
        extra: list[sqlite3.Row] = []
        if related_ids:
            placeholders = ",".join("?" for _ in related_ids)
            extra = self.conn.execute(
                f"SELECT * FROM seals WHERE subject_id IN ({placeholders}) ORDER BY id",
                related_ids,
            ).fetchall()
        seen: set[int] = set()
        seal_rows: list[sqlite3.Row] = []
        for row in list(own) + list(extra):
            if row["id"] in seen:
                continue
            seen.add(row["id"])
            seal_rows.append(row)
        seals_out = []
        for row in seal_rows:
            include_preimage = row["kind"] != "artefact" or row["actor_id"] == user_id
            seals_out.append(
                {
                    "public_id": row["public_id"],
                    "chat_id": row["chat_id"],
                    "actor_id": row["actor_id"],
                    "kind": row["kind"],
                    "action": row["action"],
                    "subject_id": row["subject_id"],
                    "content_hash": row["content_hash"],
                    "seal_hash": row["seal_hash"],
                    "prev_hash": row["prev_hash"],
                    "canonical": row["canonical"],
                    "preimage": row["preimage"] if include_preimage else None,
                    "filename": row["filename"],
                    "byte_size": row["byte_size"],
                    "created_at": row["created_at"],
                }
            )
        return {
            "product": "stipula",
            "version": 1,
            "app_version": __version__,
            "exported_at": exported_at if exported_at is not None else self.clock.now(),
            "user_id": user_id,
            "truncated": len(own) >= 1000,
            "seals": seals_out,
            "commitments": [dict(row) for row in commitments],
            "decisions": [dict(row) for row in decision_rows],
        }

    def health(self) -> dict[str, object]:
        ok = integrity_ok(self.conn)
        seals = self.conn.execute("SELECT COUNT(*) AS c FROM seals").fetchone()["c"]
        chats = self.conn.execute("SELECT COUNT(*) AS c FROM chats").fetchone()["c"]
        return {
            "status": "ok" if ok else "degraded",
            "integrity": "ok" if ok else "failed",
            "seals": seals,
            "chats": chats,
            "version": __version__,
        }

    def _upsert_user(self, user_id: int, username: str | None, first_name: str) -> None:
        now = self.clock.now()
        self.conn.execute(
            """
            INSERT INTO users (user_id, username, first_name, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name
            """,
            (user_id, username, first_name, now),
        )

    def _ensure_user(self, user_id: int, username: str | None, first_name: str) -> None:
        self.conn.execute(
            """
            INSERT INTO users (user_id, username, first_name, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO NOTHING
            """,
            (user_id, username, first_name, self.clock.now()),
        )

    def _ensure_chat(self, chat_id: int, chat_type: str, title: str | None) -> None:
        self.conn.execute(
            """
            INSERT INTO chats (chat_id, chat_type, title, chain_head, seal_count, created_at)
            VALUES (?, ?, ?, ?, 0, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                chat_type = excluded.chat_type,
                title = COALESCE(excluded.title, chats.title)
            """,
            (chat_id, chat_type, title, genesis_hash(chat_id), self.clock.now()),
        )

    def _retain(self, actor_id: int, retain: bool | None) -> bool:
        if retain is not None:
            return retain
        row = self.conn.execute(
            "SELECT retain_default FROM users WHERE user_id = ?",
            (actor_id,),
        ).fetchone()
        return bool(row and row["retain_default"])

    def _plan(self, actor_id: int) -> str:
        row = self.conn.execute("SELECT plan FROM users WHERE user_id = ?", (actor_id,)).fetchone()
        if row is None:
            return "free"
        return str(row["plan"])

    def _metered_count(self, actor_id: int) -> int:
        start = month_start(self.clock.now())
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS c FROM seals
            WHERE actor_id = ? AND metered = 1 AND created_at >= ?
            """,
            (actor_id, start),
        ).fetchone()
        return int(row["c"])

    def _open_commitment_count(self, user_id: int) -> int:
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS c FROM commitments
            WHERE status IN ('proposed', 'active')
              AND (creator_id = ? OR counterparty_id = ?)
            """,
            (user_id, user_id),
        ).fetchone()
        return int(row["c"])

    def _enforce_monthly(self, actor_id: int) -> None:
        if self._plan(actor_id) == "pro":
            return
        if self._metered_count(actor_id) >= self.monthly_free_seals:
            raise QuotaExceeded(
                f"Free plan limit is {self.monthly_free_seals} new seals this month. "
                "Finishing an open commitment does not use another seal."
            )

    def _enforce_open_commitments(self, user_id: int) -> None:
        if self._plan(user_id) == "pro":
            return
        if self._open_commitment_count(user_id) >= self.free_open_commitments:
            raise QuotaExceeded(
                f"Free plan keeps {self.free_open_commitments} open commitments. Finish or cancel one first."
            )

    def _allocate(self, prefix: str) -> str:
        table = {"STL": "seals", "CMT": "commitments", "DEC": "decisions"}[prefix]
        for _ in range(8):
            code = new_public_id(prefix)
            row = self.conn.execute(
                f"SELECT 1 FROM {table} WHERE public_id = ?",
                (code,),
            ).fetchone()
            if row is None:
                return code
        raise RuntimeError("could not allocate a public id")

    def _replay(self, update_id: int | None) -> Seal | None:
        if update_id is None:
            return None
        row = self.conn.execute(
            "SELECT * FROM seals WHERE source_update_id = ?",
            (update_id,),
        ).fetchone()
        if row is None:
            return None
        return self._map_seal(row, replayed=True)

    def _insert_seal(
        self,
        *,
        chat_id: int,
        actor_id: int,
        kind: str,
        action: str,
        subject_id: str | None,
        content_hash: str,
        preimage: str | None,
        filename: str | None,
        byte_size: int,
        mime: str | None,
        metered: bool,
        update_id: int | None,
    ) -> Seal:
        public_id = self._allocate("STL")
        chat = self.conn.execute(
            "SELECT chain_head FROM chats WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
        if chat is None:
            raise RuntimeError("chat missing before seal")
        created_at = self.clock.now()
        canonical = seal_canonical(
            public_id=public_id,
            kind=kind,
            chat_id=chat_id,
            actor_id=actor_id,
            content_hash=content_hash,
            prev_hash=chat["chain_head"],
            created_at=created_at,
            byte_size=byte_size,
            filename=filename,
        )
        digest = seal_digest(canonical)
        try:
            cursor = self.conn.execute(
                """
                INSERT INTO seals (
                    public_id, chat_id, actor_id, kind, action, subject_id, content_hash,
                    seal_hash, prev_hash, canonical, preimage, filename, byte_size, mime,
                    metered, source_update_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    public_id,
                    chat_id,
                    actor_id,
                    kind,
                    action,
                    subject_id,
                    content_hash,
                    digest,
                    chat["chain_head"],
                    canonical,
                    preimage,
                    filename,
                    byte_size,
                    mime,
                    1 if metered else 0,
                    update_id,
                    created_at,
                ),
            )
        except sqlite3.IntegrityError as exc:
            existing = self._replay(update_id)
            if existing:
                raise _Replay(existing) from exc
            raise Conflict("That collided with an existing seal. Try again.") from exc
        self.conn.execute(
            "UPDATE chats SET chain_head = ?, seal_count = seal_count + 1 WHERE chat_id = ?",
            (digest, chat_id),
        )
        row = self.conn.execute("SELECT * FROM seals WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return self._map_seal(row)

    def _seal_row(self, public_id: str) -> sqlite3.Row:
        row = self.conn.execute(
            "SELECT * FROM seals WHERE public_id = ?",
            (public_id,),
        ).fetchone()
        if row is None:
            raise NotFound("No seal with that code.")
        return row

    def _commitment_row(self, public_id: str) -> sqlite3.Row:
        row = self.conn.execute(
            "SELECT * FROM commitments WHERE public_id = ?",
            (public_id,),
        ).fetchone()
        if row is None:
            raise NotFound("No commitment with that code.")
        return row

    def _decision_row(self, public_id: str) -> sqlite3.Row:
        row = self.conn.execute(
            "SELECT * FROM decisions WHERE public_id = ?",
            (public_id,),
        ).fetchone()
        if row is None:
            raise NotFound("No decision with that code.")
        return row

    def _assert_transition(self, row: sqlite3.Row, actor_id: int, action: str) -> None:
        status = row["status"]
        creator = row["creator_id"]
        counterparty = row["counterparty_id"]
        party = actor_id in {creator, counterparty}
        if action == "accept":
            if status != "proposed" or actor_id != counterparty or actor_id == creator:
                raise Forbidden("Only the counterparty can accept a proposed commitment.")
            return
        if action == "decline":
            if status != "proposed" or actor_id != counterparty or actor_id == creator:
                raise Forbidden("Only the counterparty can decline. The author can cancel.")
            return
        if action == "fulfill":
            if status != "active" or not party:
                raise Forbidden("Only a party can mark an active commitment fulfilled.")
            return
        if action == "cancel":
            if status not in {"proposed", "active"} or not party:
                raise Forbidden("Only a party can cancel an open commitment.")
            return
        raise ValidationError("Unknown commitment action.")

    def _count_votes(self, decision_id: str) -> dict[str, int]:
        counts = {"yes": 0, "no": 0, "abstain": 0}
        rows = self.conn.execute(
            "SELECT choice, COUNT(*) AS c FROM votes WHERE decision_id = ? GROUP BY choice",
            (decision_id,),
        ).fetchall()
        for row in rows:
            if row["choice"] in counts:
                counts[row["choice"]] = int(row["c"])
        return counts

    def _sync_counts(self, decision_id: str) -> None:
        counts = self._count_votes(decision_id)
        self.conn.execute(
            """
            UPDATE decisions SET yes_count = ?, no_count = ?, abstain_count = ?
            WHERE public_id = ?
            """,
            (counts["yes"], counts["no"], counts["abstain"], decision_id),
        )

    def _witness_count(self, public_id: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS c FROM witnesses WHERE seal_public_id = ?",
            (public_id,),
        ).fetchone()
        return int(row["c"])

    def _map_seal(self, row: sqlite3.Row, replayed: bool = False) -> Seal:
        index = self.conn.execute(
            "SELECT COUNT(*) AS c FROM seals WHERE chat_id = ? AND id <= ?",
            (row["chat_id"], row["id"]),
        ).fetchone()
        return Seal(
            id=row["id"],
            public_id=row["public_id"],
            chat_id=row["chat_id"],
            actor_id=row["actor_id"],
            kind=row["kind"],
            action=row["action"],
            subject_id=row["subject_id"],
            content_hash=row["content_hash"],
            seal_hash=row["seal_hash"],
            prev_hash=row["prev_hash"],
            canonical=row["canonical"],
            preimage=row["preimage"],
            filename=row["filename"],
            byte_size=row["byte_size"],
            mime=row["mime"],
            created_at=row["created_at"],
            chain_index=int(index["c"]),
            witness_count=self._witness_count(row["public_id"]),
            replayed=replayed,
        )

    def _map_commitment(self, row: sqlite3.Row) -> Commitment:
        return Commitment(
            public_id=row["public_id"],
            chat_id=row["chat_id"],
            creator_id=row["creator_id"],
            counterparty_id=row["counterparty_id"],
            title=row["title"],
            detail=row["detail"],
            due_on=row["due_on"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _map_decision(self, row: sqlite3.Row) -> Decision:
        return Decision(
            public_id=row["public_id"],
            chat_id=row["chat_id"],
            creator_id=row["creator_id"],
            question=row["question"],
            status=row["status"],
            yes_count=row["yes_count"],
            no_count=row["no_count"],
            abstain_count=row["abstain_count"],
            created_at=row["created_at"],
            closed_at=row["closed_at"],
        )

    def _audit_fail(self, code: str, index: int | None, public_id: str | None, head: str) -> AuditResult:
        checked = index or 0
        return AuditResult(
            ok=False,
            checked=checked,
            head=head,
            problem=AuditProblem(code=code, index=index, public_id=public_id),
        )

    def _audit_witnesses(self, public_id: str, seal_hash_hex: str) -> str | None:
        rows = self.conn.execute(
            "SELECT * FROM witnesses WHERE seal_public_id = ?",
            (public_id,),
        ).fetchall()
        for row in rows:
            expected = witness_digest(
                seal_hash_hex=seal_hash_hex,
                user_id=row["user_id"],
                witnessed_at=row["witnessed_at"],
            )
            if not same_hex(expected, row["witness_hash"]):
                return "witness_mismatch"
        return None

    def _audit_subjects(self, chat_id: int) -> AuditProblem | None:
        for row in self.conn.execute(
            "SELECT * FROM commitments WHERE chat_id = ?",
            (chat_id,),
        ):
            latest = self.conn.execute(
                """
                SELECT * FROM seals WHERE subject_id = ? ORDER BY id DESC LIMIT 1
                """,
                (row["public_id"],),
            ).fetchone()
            if latest is None:
                return AuditProblem("missing_commitment_seal", None, row["public_id"])
            expected_actions = {
                "proposed": {"propose"},
                "active": {"bind", "accept"},
                "declined": {"decline"},
                "fulfilled": {"fulfill"},
                "cancelled": {"cancel"},
            }[row["status"]]
            if latest["action"] not in expected_actions:
                return AuditProblem("commitment_status", None, row["public_id"])
            expected = commitment_preimage(
                commitment_id=row["public_id"],
                action=latest["action"],
                actor_id=latest["actor_id"],
                counterparty_id=row["counterparty_id"],
                title=row["title"],
                detail=row["detail"],
                due_on=row["due_on"],
            )
            if latest["preimage"] != expected:
                return AuditProblem("commitment_preimage", None, row["public_id"])
        for row in self.conn.execute(
            "SELECT * FROM decisions WHERE chat_id = ?",
            (chat_id,),
        ):
            opened = self.conn.execute(
                """
                SELECT * FROM seals WHERE subject_id = ? AND action = 'open' ORDER BY id LIMIT 1
                """,
                (row["public_id"],),
            ).fetchone()
            if opened is None:
                return AuditProblem("missing_open", None, row["public_id"])
            expected_open = decision_open_preimage(
                decision_id=row["public_id"],
                actor_id=opened["actor_id"],
                question=row["question"],
            )
            if opened["preimage"] != expected_open:
                return AuditProblem("question_mismatch", None, row["public_id"])
            closed = self.conn.execute(
                """
                SELECT * FROM seals WHERE subject_id = ? AND action = 'close' ORDER BY id DESC LIMIT 1
                """,
                (row["public_id"],),
            ).fetchone()
            if row["status"] == "open":
                if closed is not None:
                    return AuditProblem("unexpected_close", None, row["public_id"])
                continue
            if closed is None or row["closed_at"] is None:
                return AuditProblem("missing_close", None, row["public_id"])
            counts = self._count_votes(row["public_id"])
            if (
                counts["yes"] != row["yes_count"]
                or counts["no"] != row["no_count"]
                or counts["abstain"] != row["abstain_count"]
            ):
                return AuditProblem("tally_mismatch", None, row["public_id"])
            expected_close = decision_close_preimage(
                decision_id=row["public_id"],
                actor_id=closed["actor_id"],
                yes=counts["yes"],
                no=counts["no"],
                abstain=counts["abstain"],
                closed_at=row["closed_at"],
            )
            if closed["preimage"] != expected_close:
                return AuditProblem("tally_mismatch", None, row["public_id"])
        return None


class _Transaction:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def __enter__(self) -> sqlite3.Connection:
        self.connection.execute("BEGIN IMMEDIATE")
        return self.connection

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            self.connection.execute("COMMIT")
        else:
            self.connection.execute("ROLLBACK")


def dumps_export(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
