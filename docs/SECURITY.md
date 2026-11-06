# Security

## Secrets

`BOT_TOKEN` comes from the environment. The sample file is `.env.example`. The token format is checked and the value is never logged. Telegram errors are logged as the exception class name, because the library sometimes includes the token in a request URL. A redaction filter also strips `\d{6,}:[A-Za-z0-9_-]{20,}` from any string that does reach the formatter.

`LOG_SALT` defaults to `change-me` and the process warns when that value is still set.

## Data

Stored because the product needs it:

- Telegram user id, username if they have one, first name.
- Chat id and title.
- Seal metadata and hashes.
- Note text only when that user turned retention on.
- Commitment title, optional detail, due date, and the parties' ids.
- Decision question, votes (user id and choice), and the sealed tally.

Not stored: file bytes, captions, messages that were not sealed, bot tokens.

`/forget` nulls artefact preimages the user authored. Hashes remain so a saved original still verifies. Shared commitments and decisions are not erased by one party's forget.

`/export` includes another person's artefact text only never. Commitment and decision preimages are included for people who are parties, because they are shared records.

## Permissions

- Witness: same chat, not the author.
- Accept or decline: the counterparty, and only while proposed.
- Fulfill or cancel: a party, and only in a state that allows it.
- Close a decision: the opener, the configured owner, or a current chat admin (`getChatMember`).
- `/health`, `/grant`, `/revoke`: `BOT_OWNER_ID` only. If it is unset, those commands refuse everyone.

HTML sent to Telegram is escaped at the render boundary. Callback data is a short prefix plus a code, well under 64 bytes.

## Abuse

An in-process sliding window limits commands and callbacks per user. It resets when the process restarts and does not coordinate across machines. Run one poller.

File downloads are refused above `MAX_FILE_BYTES`, which cannot be configured past the Bot API's 20 MB `getFile` cap.

## Logs

JSON, one event per line, rotating at 2 MB with five backups when `LOG_PATH` is set. Correlation id is `u<update_id>`. With `LOG_USER_IDS=false` (the default), user and chat ids are replaced with a 12-hex HMAC. Fields named like token, text, title, preimage, or filename are replaced with `[redacted]`.

## Cryptography

SHA-256 and HMAC-SHA256 from the Python standard library only. No custom primitive. Hash comparisons use `hmac.compare_digest` when the lengths match.
