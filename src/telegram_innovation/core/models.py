"""Plain records returned across the service boundary."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Seal:
    id: int
    public_id: str
    chat_id: int
    actor_id: int
    kind: str
    action: str
    subject_id: str | None
    content_hash: str
    seal_hash: str
    prev_hash: str
    canonical: str
    preimage: str | None
    filename: str | None
    byte_size: int | None
    mime: str | None
    created_at: int
    chain_index: int
    witness_count: int
    replayed: bool = False


@dataclass(frozen=True)
class Witness:
    seal_public_id: str
    user_id: int
    witness_hash: str
    witnessed_at: int
    already: bool
    witness_count: int


@dataclass(frozen=True)
class Commitment:
    public_id: str
    chat_id: int
    creator_id: int
    counterparty_id: int
    title: str
    detail: str | None
    due_on: str | None
    status: str
    created_at: int
    updated_at: int


@dataclass(frozen=True)
class Decision:
    public_id: str
    chat_id: int
    creator_id: int
    question: str
    status: str
    yes_count: int
    no_count: int
    abstain_count: int
    created_at: int
    closed_at: int | None


@dataclass(frozen=True)
class Pending:
    chat_id: int
    user_id: int
    action: str
    payload: str | None
    expires_at: int


@dataclass(frozen=True)
class AuditProblem:
    code: str
    index: int | None
    public_id: str | None


@dataclass(frozen=True)
class AuditResult:
    ok: bool
    checked: int
    head: str
    problem: AuditProblem | None


@dataclass(frozen=True)
class Quota:
    plan: str
    used: int
    limit: int | None
    open_commitments: int
    open_limit: int | None


@dataclass(frozen=True)
class VerifyResult:
    public_id: str
    kind: str
    matched: bool
