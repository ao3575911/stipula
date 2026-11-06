# Validation

Run on the implementation in this tree. Numbers below are from that run, not a target.

## Automated

- `pytest`: 23 passed.
- `ruff check src tests`: clean.
- `ruff format --check src tests`: clean after formatting.
- `python -m telegram_innovation check --offline`: `integrity` ok, `vector_ok` true, migration `001_init.sql` applied. No token used.
- Pinned vector: SHA-256 of `Hello, Stipula` is `b8106aef372deb6cf179238a643201274b9b145704885f8f77de9a63b0fff629`. The sample seal canonical and witness canonical are in `tests/fixtures/vectors.json`.

Covered by those tests:

- Seal, replay the same update id, verify match and mismatch, chain link.
- Tampered `seal_hash` fails audit.
- File hash, filename, and the size cap.
- Witness: not the author, not another chat, duplicate witness is idempotent.
- Commitment: counterparty accept, author cannot accept, fulfill after the monthly meter is exhausted.
- Open-commitment cap, pro plan bypass.
- Decision tally tamper fails audit.
- Forget removes a retained note and leaves the hash verifiable.
- Export does not include another user's retained note.
- Pending actions expire.
- HTML in a commitment title is escaped.
- Group chatter is ignored. Reply `/seal` and the witness button work through the application, using fixture payloads.
- Owner `/health` and `/grant` are refused for everyone else.
- Rate limit returns the slow-down message.
- Logs of a seal do not contain the sealed phrase.
- A bot-token-shaped string is redacted. User ids are HMAC'd when `LOG_USER_IDS` is false.
- Config rejects a missing token, a malformed token, and `MAX_FILE_BYTES` above 20 MB.
- Migrations apply twice without error.

## Not verified

These were not executed, and this file does not claim they passed:

- A real `getUpdates` / `sendMessage` / `getFile` round trip against Telegram.
- Privacy mode behaviour in a live group. The documented limitation follows Telegram's privacy-mode rules; it was not re-checked on a production chat in this run.
- `getChat` username resolution and `getChatMember` admin checks against the live API. The adapter maps those calls and treats `TelegramAPIError` as "not resolved" / "not admin".
- Docker image build and systemd start on a Debian host.
- GitHub Actions on a remote runner. The workflow file matches the local commands.

Python used for the local run was 3.10 with aiogram 3.31.0. The package metadata allows 3.10 and CI is set to 3.12. 3.12 was not installed in the verification environment.
