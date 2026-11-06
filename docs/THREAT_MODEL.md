# Threat model

## Assets

The seal card a user saved, the hash chain in SQLite, commitment and decision wording, and the bot token.

## Actors

- A chat member, honest or not.
- A stranger who can message the bot.
- The operator who can read the database and the environment.
- Telegram, which delivers updates and file bytes.

## In scope

| Threat | Response |
| --- | --- |
| Replay of the same update | `source_update_id` unique. The original seal is returned. |
| Author witnessing themselves | Rejected. |
| Witness button used from another chat | Rejected. The callback chat must own the seal. |
| Stranger fulfilling a commitment | Rejected. |
| Vote after close | Rejected. A vote inserted directly into SQLite fails `/audit`. |
| Edited tally column | `/audit` recomputes votes and the close preimage. |
| Edited seal hash or canonical text | `/audit` stops at the first break. |
| Sealed text leaking into logs | Command name is logged. Body is not. Formatter redacts sensitive keys and bot tokens. |
| HTML injection in a title | Rendered with `html.escape`. |
| Oversized file | Rejected before hashing a huge buffer past the cap, and again after download. |
| Flood | Per-user sliding window. |
| Token in an API error string | Exception class only, plus a token regex scrubber. |

## Out of scope, stated on purpose

- A hostile operator rewriting the entire chain and every witness row. `/audit` will pass. Users who saved the card can compare hashes by hand. The product does not claim otherwise.
- Telegram changing photo bytes. The seal matches the bytes Telegram returned.
- Privacy mode hiding a follow-up message. The bot says so and recommends reply-to-seal.
- Legal admissibility.
- Malware in an uploaded file. Bytes are hashed and discarded. They are not executed.
- Multi-account Sybil witnesses. A witness is a Telegram account that can press the button. That is an attestation, not a proof of personhood.

## Residual

User ids are personal data and are required as primary keys. Exports contain the exporter's id and counterparty ids. Operators who set `LOG_USER_IDS=true` store raw ids in logs. Don't do that unless you mean to.
