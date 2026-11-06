"""Short public identifiers. Crockford base32 avoids I, L, O and U."""

from __future__ import annotations

import re
import secrets

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_BODY = r"[0-9A-HJKMNP-TV-Z]{4}-[0-9A-HJKMNP-TV-Z]{4}"
SEAL_CODE = re.compile(rf"^STL-{_BODY}$")
COMMITMENT_CODE = re.compile(rf"^CMT-{_BODY}$")
DECISION_CODE = re.compile(rf"^DEC-{_BODY}$")
ANY_CODE = re.compile(rf"^(?:STL|CMT|DEC)-{_BODY}$")


def new_public_id(prefix: str) -> str:
    number = int.from_bytes(secrets.token_bytes(5), "big")
    chars: list[str] = []
    for _ in range(8):
        chars.append(ALPHABET[number & 31])
        number >>= 5
    body = "".join(reversed(chars))
    return f"{prefix}-{body[:4]}-{body[4:]}"


def find_code(text: str, pattern: re.Pattern[str]) -> str | None:
    match = pattern.search(text.upper())
    if not match:
        return None
    return match.group(0)
