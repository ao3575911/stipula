# Architecture

```text
Telegram
  -> integrations/telegram.py     aiogram polling, file download, username lookup
  -> bot/parse.py                 commands and raw update payloads
  -> bot/app.py                   journeys, HTML cards, authorisation calls
  -> features/service.py          one transaction per use case
  -> storage/db.py + SQLite
  -> core/sealing.py              versioned canonical bytes
```

`bot/app.py` speaks in `InMessage`, `InCallback`, and `InInline`. Tests build those directly. aiogram is imported only from `integrations/telegram.py` and the `run` command.

## Seal

Two hashes:

- `content_hash` is SHA-256 of the exact text (UTF-8) or the exact file bytes. There is no domain prefix, so an external SHA-256 tool matches a file.
- `seal_hash` is SHA-256 of the `stipula-seal-v1` record. That record includes the content hash, the previous seal hash, the chat, the actor, the time, the size, and the filename. It does not include the text.

The first `prev_hash` in a chat is SHA-256 of `stipula-genesis-v1\n` plus the chat id. Chains are not interchangeable across chats.

Witnesses do not rewrite the seal. A witness hash covers the seal hash, the user id, and the time. If the seal hash changes, saved witness hashes stop matching.

Commitments and decisions store a canonical preimage. Its SHA-256 is the seal's content hash. Status changes append a new seal. They do not edit the old one.

## Transactions

Each public service method runs `BEGIN IMMEDIATE` and commits the subject row and the seal together. `source_update_id` is unique, so a redelivered Telegram update returns the original seal instead of a second link.

SQLite is the right store: one bot process, one file, no extra service. WAL is on for file databases. `:memory:` is for tests.

## Quotas

Metered seals are new artefacts, new commitments, and opened decisions. Accept, decline, fulfill, cancel, and decision close are not metered, so a workflow can finish after the monthly cap is hit. Open commitments are capped separately on the free plan.

## Time

`created_at` is the bot server's unix time. It is not Telegram's message date and not a third-party timestamp.

## What the bot cannot do

The Bot API cannot atomically move usernames, cannot read a file over 20 MB, cannot see every group message while privacy mode is on, and cannot prove the operator's disk was not rewritten offline. Those limits are enforced or documented, not papered over.
