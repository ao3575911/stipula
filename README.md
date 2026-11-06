# Stipula

Seal what was said. Prove it later.

Stipula is a Telegram bot that commits to the exact bytes of a message or file, links that commitment into a per-chat hash chain, and lets other people in the chat witness it. Later, anyone can resend the original bytes and the bot reports match or miss.

It is a hash log with a shareable card. It is not a court, a blockchain, a notary, or an anonymity tool.

Suggested usernames: `@stipula_bot`, `@sealatest_bot`, `@stipulabot`.

## Why it exists

Agreements, file versions, and group decisions made in chat are hard to cite later. Exporting a whole history is noisy and keeps more text than anyone wanted. Stipula keeps a SHA-256 of the bytes, a chain link, and optional witnesses. The words stay with the people who already have them unless someone explicitly turns retention on.

## What you can do

- `/seal` a text message or a file (reply to it, or send it next in a private chat).
- Tap **Witness**. The author cannot witness their own seal.
- `/verify CODE` and resend the original bytes.
- `/commit` a promise, accept it, and mark it fulfilled. Each step is its own seal.
- `/decide` a question, vote, and close it. The tally is sealed. Editing the count breaks `/audit`.
- `/export` a JSON pack of your own records.
- `/forget` private copies of notes you sealed. The hashes stay.

Free plan defaults: 30 new seals a month, 5 open commitments. Finishing a commitment does not spend another seal. The bot owner can `/grant` a pro plan. There is no in-bot payment yet.

## Quick start

Requires Python 3.10 or newer. Continuous integration runs on 3.12.

```bash
scripts/install.sh
# edit .env and set BOT_TOKEN, and BOT_OWNER_ID if you want owner commands
scripts/check.sh
scripts/run.sh
```

In BotFather:

1. Create a bot and put the token in `.env`.
2. Disable privacy mode if you want `/seal` as a reply to work reliably in groups. With privacy mode on, the bot mainly sees commands, mentions, and replies to itself.
3. Enable inline mode if you want `@yourbot STL-XXXX-XXXX` to post a seal card.

One process only. Two pollers will double-handle updates.

## Honesty

- Content hash is SHA-256 of the exact UTF-8 text, or of the file bytes Telegram actually returned. No extra prefix.
- Photos are recompressed by Telegram. Seal a document if the original file matters.
- Bots cannot download files over 20 MB (`getFile`).
- `/audit` detects torn writes and partial edits. Someone who holds the database can recompute a whole new chain. Keep the seal card if you need a copy the operator does not control.
- The bot cannot transfer Telegram usernames, hide your Telegram identity from chat admins, or timestamp anything outside its own clock.
- Logs do not store message text. User and chat ids are HMAC-truncated unless `LOG_USER_IDS=true`.

## Layout

`src/telegram_innovation/` is the package. `features/service.py` owns the transactions. `bot/app.py` is the command application and does not import aiogram. `integrations/telegram.py` is the only Telegram adapter. Docs in `docs/` match this behaviour.

## Tests

`scripts/check.sh` runs Ruff, pytest, and `python -m telegram_innovation check --offline`. Offline mode does not need a token. It migrates SQLite, runs `PRAGMA integrity_check`, and recomputes the pinned `Hello, Stipula` vector.

Live Bot API calls were not part of the automated suite. See `docs/VALIDATION.md`.
