# Decisions

Weights: originality 15, utility 20, Telegram-native fit 15, feasibility 15, privacy 15, retention 10, monetisation 5, low ongoing cost 5.

| Concept | Score | Why it lost or won |
| --- | --- | --- |
| Stipula, sealed artefacts and witnessed commitments | 8.6 | One card people can forward. Feasible entirely on the Bot API. Privacy is honest because the default is a hash. |
| Handoff Latch, shift handoffs | 7.7 | Useful and buildable, but it is a task bot with a timer. Easy to ignore after a week. |
| Triagewire, assign messages in a group | 7.1 | Real ops need, crowded category, weak reason to invite the next person. |
| Spelltable, async cipher duel | 6.7 | Fun, not a recurring tool. |
| Roomrights, per-topic permission namespaces | 5.7 | Bots cannot actually enforce Telegram's own admin rights. The pitch would over-claim. |
| Unlink, per-chat pseudonyms | 5.0 | A bot cannot hide a Telegram user id from admins or from Telegram. Shipping it would be a false privacy product. |

## Why Stipula, after arguing with it

The first sketch bundled commitments, decisions, file receipts, and a public registry. The registry went away: the bot cannot publish an independent timestamp, and pretending otherwise is the failure mode of notary bots. Commitments and decisions stayed only as extra seal kinds. If they had needed a second storage model, they would have been cut.

The signature is the card. Witness is the reason a second person installs it. Replay is the reason the first person comes back.

## Engineering choices

- Python, not Rust. The work is I/O and careful bytes, and the standard library already has SHA-256, HMAC, and SQLite. aiogram is the one substantial dependency.
- Python 3.10 is the floor so the code runs where 3.12 is not installed. CI targets 3.12. No 3.12-only syntax.
- Sync SQLite inside short transactions, called from async handlers. Aiosqlite would add a dependency without changing the one-writer model.
- SQL lives in the service module. A separate repository layer made it easier to commit a commitment row without its seal. One method, one transaction.
- In-memory rate limit. Documented as single-process.
- No Mini App in the bot. A browser desk that implements the same canonical bytes is a demo of the format, not a second backend.

## Rejected security theatre

- No "zero knowledge" wording. The bot sees the bytes in order to hash them.
- No claim that witnesses are unlinkable. Their Telegram account pressed the button.
- No home-grown signature. Witness hashes are SHA-256 of a versioned string.
