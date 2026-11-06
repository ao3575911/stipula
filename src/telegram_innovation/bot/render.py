"""Chat copy. Dynamic values are HTML-escaped. This bot does not claim to be a notary."""

from __future__ import annotations

from html import escape

from telegram_innovation.core.models import AuditResult, Commitment, Decision, Seal, Witness

PHOTO_NOTE = (
    "Telegram recompresses photos. This seal matches the copy Telegram stored, "
    "not necessarily the original camera file. Send it as a document to hash the original bytes."
)
FILE_NOTE = "The hash covers the file bytes only, not the caption."
GROUP_PENDING = (
    "In groups I only see a follow-up if privacy mode is off, or you reply to me. "
    "Replying to the message with /seal is the reliable path."
)


def e(value: object) -> str:
    return escape(str(value), quote=True)


def render_seal(seal: Seal, *, note: str = "", replayed: bool = False) -> str:
    head = "Already sealed" if replayed or seal.replayed else "Sealed"
    lines = [
        f"<b>{head}</b> · <code>{e(seal.public_id)}</code>",
        f"Kind · {e(seal.kind)}",
        f"Content · <code>{e(seal.content_hash)}</code>",
        f"Seal · <code>{e(seal.seal_hash)}</code>",
        f"Chain · #{seal.chain_index}",
        f"Witnesses · {seal.witness_count}",
    ]
    if seal.filename:
        lines.append(f"File · {e(seal.filename)}")
    if note:
        lines.extend(["", e(note)])
    lines.extend(["", "Resend the same bytes with /verify and this code."])
    return "\n".join(lines)


def seal_keyboard(public_id: str) -> list[list[tuple[str, str]]]:
    return [[("Witness", f"wit:{public_id}")]]


def render_witness(witness: Witness, label: str) -> str:
    state = "Already witnessed" if witness.already else "Witnessed"
    return (
        f"<b>{state}</b> · <code>{e(witness.seal_public_id)}</code>\n"
        f"{e(label)} · witnesses {witness.witness_count}\n"
        f"Witness hash · <code>{e(witness.witness_hash)}</code>\n\n"
        "Save this hash if you want a copy that does not depend on this bot."
    )


def render_commitment(commitment: Commitment, *, creator: str, counterparty: str) -> str:
    due = commitment.due_on or "no date"
    detail = f"\n{e(commitment.detail)}" if commitment.detail else ""
    return (
        f"<b>Commitment</b> · <code>{e(commitment.public_id)}</code>\n"
        f"{e(commitment.title)}{detail}\n"
        f"Status · {e(commitment.status)}\n"
        f"From {e(creator)} to {e(counterparty)}\n"
        f"Due · {e(due)}"
    )


def commitment_keyboard(commitment: Commitment) -> list[list[tuple[str, str]]] | None:
    code = commitment.public_id
    if commitment.status == "proposed":
        return [
            [("Accept", f"cac:{code}"), ("Decline", f"cde:{code}")],
            [("Cancel", f"cca:{code}")],
        ]
    if commitment.status == "active":
        return [[("Fulfilled", f"cfu:{code}"), ("Cancel", f"cca:{code}")]]
    return None


def render_decision(decision: Decision) -> str:
    state = "Open decision" if decision.status == "open" else "Closed decision"
    return (
        f"<b>{state}</b> · <code>{e(decision.public_id)}</code>\n"
        f"{e(decision.question)}\n"
        f"Yes {decision.yes_count} · No {decision.no_count} · Abstain {decision.abstain_count}"
    )


def decision_keyboard(decision: Decision) -> list[list[tuple[str, str]]] | None:
    if decision.status != "open":
        return None
    code = decision.public_id
    return [
        [("Yes", f"vy:{code}"), ("No", f"vn:{code}"), ("Abstain", f"va:{code}")],
        [("Close and seal", f"dcl:{code}")],
    ]


def render_verify(matched: bool, public_id: str) -> str:
    if matched:
        return (
            f"<b>Match.</b> Those bytes are what <code>{e(public_id)}</code> commits to.\n"
            "This is a hash check, not a legal notarisation."
        )
    return f"<b>No match.</b> Those bytes are not what <code>{e(public_id)}</code> commits to."


def render_audit(result: AuditResult) -> str:
    if result.ok:
        return (
            f"<b>Chain OK</b> · {result.checked} seals\n"
            f"Head · <code>{e(result.head)}</code>\n\n"
            "This checks the bot's own log for torn writes and partial edits. "
            "It is not an external timestamp. A full offline rewrite by whoever "
            "holds the database would still verify, so keep the seal card."
        )
    problem = result.problem
    where = ""
    if problem and problem.public_id:
        where = f" · <code>{e(problem.public_id)}</code>"
    code = problem.code if problem else "unknown"
    return f"<b>Chain broken</b>{where}\nProblem · {e(code)}\nChecked · {result.checked}"


def render_help() -> str:
    return (
        "<b>Stipula</b> seals what was said so you can prove it later.\n\n"
        "/seal — seal the next message, or reply to one\n"
        "/verify CODE — resend the original bytes\n"
        "/show CODE — metadata for a seal, commitment, or decision\n"
        "/witness CODE — co-sign a seal in this chat\n"
        "/seals — recent seals here\n"
        "/audit — check this chat's hash chain\n"
        "/commit [@name] [YYYY-MM-DD] what was agreed\n"
        "/commitments — open promises you are party to\n"
        "/decide the question\n"
        "/decisions — decisions in this chat\n"
        "/export — your JSON proof pack\n"
        "/forget — delete private copies of notes you sealed\n"
        "/settings — retention and username display\n"
        "/quota — what the free plan still allows\n"
        "/cancel — drop a pending seal, or cancel a commitment code\n\n"
        "Hashes are SHA-256. The bot does not move Telegram usernames, "
        "and it cannot see a file Telegram refuses to hand over (over 20 MB)."
    )


def render_start() -> str:
    return (
        "<b>Stipula</b>\n"
        "Seal a message or a file. Anyone in the chat can witness it. "
        "Later, resend the same bytes and I'll tell you if they match.\n\n"
        "Try /seal, then send the text you want locked.\n\n"
        "I store the hash either way. I only keep the text itself if you turn retention on "
        "in /settings. Shared commitments and decisions keep their wording, because both "
        "sides need it.\n\n"
        "This is not a court, a blockchain, or an anonymity tool."
    )


def render_quota(snapshot: dict[str, object]) -> str:
    limit = snapshot["limit"]
    used = snapshot["used"]
    cap = "unlimited" if limit is None else str(limit)
    open_limit = snapshot["open_limit"]
    open_cap = "unlimited" if open_limit is None else str(open_limit)
    retain = "on" if snapshot["retain"] else "off"
    shown = "on" if snapshot["show_username"] else "off"
    return (
        f"Plan · {e(snapshot['plan'])}\n"
        f"Seals this month · {e(used)} / {e(cap)}\n"
        f"Open commitments · {e(snapshot['open_commitments'])} / {e(open_cap)}\n"
        f"Keep a private copy of notes · {retain}\n"
        f"Show @username on witness lines · {shown}"
    )


def render_health(health: dict[str, object], *, owner_set: bool, rate_limit: int) -> str:
    return (
        f"Status · {e(health['status'])}\n"
        f"Integrity · {e(health['integrity'])}\n"
        f"Seals · {e(health['seals'])}\n"
        f"Chats · {e(health['chats'])}\n"
        f"Version · {e(health['version'])}\n"
        f"Owner configured · {'yes' if owner_set else 'no'}\n"
        f"Rate limit · {rate_limit}/min"
    )


def render_settings_help() -> str:
    return "Usage:\n/settings retain on|off\n/settings username on|off"
