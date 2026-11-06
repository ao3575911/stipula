"""Service rules: chain, quota, commitments, decisions, export, forget."""

from __future__ import annotations

import pytest

from telegram_innovation.core.errors import FileTooLarge, Forbidden, QuotaExceeded
from telegram_innovation.core.sealing import sha256_text


def test_seal_verify_and_chain(world):
    first = world.service.seal_text(
        chat_id=70,
        chat_type="private",
        chat_title=None,
        actor_id=7,
        text="Hello, Stipula",
        update_id=1,
    )
    again = world.service.seal_text(
        chat_id=70,
        chat_type="private",
        chat_title=None,
        actor_id=7,
        text="Hello, Stipula",
        update_id=1,
    )
    assert again.replayed is True
    assert again.public_id == first.public_id
    assert world.service.verify_text(first.public_id, "Hello, Stipula").matched
    assert not world.service.verify_text(first.public_id, "Hello, Stipula ").matched
    second = world.service.seal_text(
        chat_id=70,
        chat_type="private",
        chat_title=None,
        actor_id=7,
        text="second",
        update_id=2,
    )
    assert second.prev_hash == first.seal_hash
    assert world.service.audit(70).ok


def test_tamper_breaks_audit(world):
    seal = world.service.seal_text(
        chat_id=5,
        chat_type="group",
        chat_title="Crew",
        actor_id=7,
        text="do not edit",
        update_id=3,
        retain=True,
    )
    world.conn.execute(
        "UPDATE seals SET seal_hash = ? WHERE public_id = ?",
        ("ab" * 32, seal.public_id),
    )
    result = world.service.audit(5)
    assert not result.ok
    assert result.problem is not None
    assert result.problem.code == "seal_mismatch"


def test_file_limit_and_hash(world):
    blob = b"\x00\x01\x02"
    sealed = world.service.seal_file(
        chat_id=5,
        chat_type="private",
        chat_title=None,
        actor_id=7,
        data=blob,
        filename="<quote>.pdf",
        mime="application/pdf",
        update_id=4,
    )
    assert sealed.filename == "<quote>.pdf"
    assert sealed.preimage is None
    assert world.service.verify_bytes(sealed.public_id, blob).matched
    with pytest.raises(FileTooLarge):
        world.service.seal_file(
            chat_id=5,
            chat_type="private",
            chat_title=None,
            actor_id=7,
            data=b"x" * 17,
            filename="big.bin",
            mime=None,
            update_id=5,
        )


def test_witness_rules(world):
    seal = world.service.seal_text(
        chat_id=9,
        chat_type="supergroup",
        chat_title="Shop",
        actor_id=7,
        text="agreed",
        update_id=6,
    )
    with pytest.raises(Forbidden):
        world.service.witness(public_id=seal.public_id, user_id=7, chat_id=9)
    with pytest.raises(Forbidden):
        world.service.witness(public_id=seal.public_id, user_id=8, chat_id=10)
    first = world.service.witness(public_id=seal.public_id, user_id=8, chat_id=9)
    second = world.service.witness(public_id=seal.public_id, user_id=8, chat_id=9)
    assert first.already is False
    assert second.already is True
    assert second.witness_count == 1
    assert world.service.audit(9).ok


def test_commitment_permissions_and_quota(world):
    commitment, _seal = world.service.propose_commitment(
        chat_id=9,
        chat_type="group",
        chat_title="Shop",
        creator_id=7,
        counterparty_id=8,
        title="Pay the deposit",
        detail="Friday latest",
        due_on="2026-12-01",
        update_id=7,
    )
    assert commitment.status == "proposed"
    with pytest.raises(Forbidden):
        world.service.transition_commitment(public_id=commitment.public_id, actor_id=7, action="accept", update_id=8)
    accepted, _event = world.service.transition_commitment(
        public_id=commitment.public_id, actor_id=8, action="accept", update_id=9
    )
    assert accepted.status == "active"
    world.service.monthly_free_seals = 1
    done, _event = world.service.transition_commitment(
        public_id=commitment.public_id, actor_id=7, action="fulfill", update_id=10
    )
    assert done.status == "fulfilled"
    assert world.service.audit(9).ok


def test_self_commitment_and_open_cap(world):
    first, _seal = world.service.propose_commitment(
        chat_id=1,
        chat_type="private",
        chat_title=None,
        creator_id=7,
        counterparty_id=7,
        title="Send the quote",
        detail=None,
        due_on=None,
        update_id=11,
    )
    assert first.status == "active"
    world.service.propose_commitment(
        chat_id=1,
        chat_type="private",
        chat_title=None,
        creator_id=7,
        counterparty_id=7,
        title="Second",
        detail=None,
        due_on=None,
        update_id=12,
    )
    with pytest.raises(QuotaExceeded):
        world.service.propose_commitment(
            chat_id=1,
            chat_type="private",
            chat_title=None,
            creator_id=7,
            counterparty_id=7,
            title="Third",
            detail=None,
            due_on=None,
            update_id=13,
        )


def test_decision_tally_detects_tamper(world):
    decision, _seal = world.service.open_decision(
        chat_id=9,
        chat_type="group",
        chat_title="Shop",
        creator_id=7,
        question="Switch supplier?",
        update_id=14,
    )
    world.service.vote(decision_id=decision.public_id, user_id=7, chat_id=9, choice="yes")
    world.service.vote(decision_id=decision.public_id, user_id=8, chat_id=9, choice="no")
    closed, _seal = world.service.close_decision(
        decision_id=decision.public_id, actor_id=7, as_admin=False, update_id=15
    )
    assert (closed.yes_count, closed.no_count, closed.abstain_count) == (1, 1, 0)
    assert world.service.audit(9).ok
    world.conn.execute(
        "UPDATE decisions SET yes_count = 9 WHERE public_id = ?",
        (decision.public_id,),
    )
    broken = world.service.audit(9)
    assert not broken.ok
    assert broken.problem is not None
    assert broken.problem.code == "tally_mismatch"


def test_forget_and_export_boundaries(world):
    world.service.update_settings(7, retain=True)
    note = world.service.seal_text(
        chat_id=70,
        chat_type="private",
        chat_title=None,
        actor_id=7,
        text="secret note",
        update_id=16,
    )
    assert note.preimage == "secret note"
    world.service.seal_text(
        chat_id=71,
        chat_type="private",
        chat_title=None,
        actor_id=8,
        text="sam secret",
        update_id=17,
        retain=True,
    )
    exported = world.service.export_user(8)
    assert all(row["preimage"] != "secret note" for row in exported["seals"])
    assert sha256_text("secret note") not in {row["content_hash"] for row in exported["seals"]}
    removed = world.service.forget_artefacts(7)
    assert removed == 1
    assert world.service.get_seal(note.public_id).preimage is None
    assert world.service.verify_text(note.public_id, "secret note").matched
    assert world.service.audit(70).ok


def test_pending_expires(world):
    world.service.set_pending(70, 7, "seal", None)
    world.clock.advance(601)
    assert world.service.get_pending(70, 7) is None


def test_pro_plan_skips_quota(world):
    world.service.set_plan(7, "pro")
    world.service.monthly_free_seals = 1
    world.service.seal_text(chat_id=1, chat_type="private", chat_title=None, actor_id=7, text="a", update_id=20)
    world.service.seal_text(chat_id=1, chat_type="private", chat_title=None, actor_id=7, text="b", update_id=21)
    assert world.service.quota_for(7).limit is None


def test_migrations_are_idempotent(world):
    from telegram_innovation.storage.db import apply_migrations, integrity_ok

    assert apply_migrations(world.conn) == []
    assert integrity_ok(world.conn)
