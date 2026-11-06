"""Versioned canonical bytes for Stipula seals.

These strings are the product contract. A seal already issued stays verifiable
only if this format does not change. New behaviour gets a new version label.
"""

from __future__ import annotations

import hashlib
import hmac

GENESIS_LABEL = "stipula-genesis-v1\n"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def same_hex(left: str, right: str) -> bool:
    if len(left) != len(right):
        return False
    return hmac.compare_digest(left.encode("ascii"), right.encode("ascii"))


def genesis_hash(chat_id: int) -> str:
    """Chat-scoped chain origin. Not a shared constant, so logs cannot be spliced."""
    return sha256_text(f"{GENESIS_LABEL}{int(chat_id)}")


def _one_line(value: str) -> str:
    return value.replace("\r", " ").replace("\n", " ")


def seal_canonical(
    *,
    public_id: str,
    kind: str,
    chat_id: int,
    actor_id: int,
    content_hash: str,
    prev_hash: str,
    created_at: int,
    byte_size: int | None,
    filename: str | None,
) -> str:
    size = "-" if byte_size is None else str(int(byte_size))
    name = "-" if not filename else _one_line(filename)
    return (
        "stipula-seal-v1\n"
        f"public_id={public_id}\n"
        f"kind={kind}\n"
        f"chat_id={int(chat_id)}\n"
        f"actor_id={int(actor_id)}\n"
        f"content_hash={content_hash}\n"
        f"prev_hash={prev_hash}\n"
        f"created_at={int(created_at)}\n"
        f"byte_size={size}\n"
        f"filename={name}\n"
    )


def seal_digest(canonical: str) -> str:
    return sha256_text(canonical)


def witness_canonical(*, seal_hash_hex: str, user_id: int, witnessed_at: int) -> str:
    return f"stipula-witness-v1\nseal_hash={seal_hash_hex}\nuser_id={int(user_id)}\nwitnessed_at={int(witnessed_at)}\n"


def witness_digest(*, seal_hash_hex: str, user_id: int, witnessed_at: int) -> str:
    return sha256_text(
        witness_canonical(
            seal_hash_hex=seal_hash_hex,
            user_id=user_id,
            witnessed_at=witnessed_at,
        )
    )


def commitment_preimage(
    *,
    commitment_id: str,
    action: str,
    actor_id: int,
    counterparty_id: int,
    title: str,
    detail: str | None,
    due_on: str | None,
) -> str:
    detail_value = "-" if not detail else _one_line(detail)
    due_value = due_on or "-"
    return (
        "stipula-commit-v1\n"
        f"commitment_id={commitment_id}\n"
        f"action={action}\n"
        f"actor_id={int(actor_id)}\n"
        f"counterparty_id={int(counterparty_id)}\n"
        f"title={_one_line(title)}\n"
        f"detail={detail_value}\n"
        f"due_on={due_value}\n"
    )


def decision_open_preimage(*, decision_id: str, actor_id: int, question: str) -> str:
    return (
        "stipula-decision-v1\n"
        f"decision_id={decision_id}\n"
        f"action=open\n"
        f"actor_id={int(actor_id)}\n"
        f"question={_one_line(question)}\n"
    )


def decision_close_preimage(
    *,
    decision_id: str,
    actor_id: int,
    yes: int,
    no: int,
    abstain: int,
    closed_at: int,
) -> str:
    return (
        "stipula-decision-v1\n"
        f"decision_id={decision_id}\n"
        f"action=close\n"
        f"actor_id={int(actor_id)}\n"
        f"yes={int(yes)}\n"
        f"no={int(no)}\n"
        f"abstain={int(abstain)}\n"
        f"closed_at={int(closed_at)}\n"
    )
