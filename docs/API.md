# Interfaces

There is no public HTTP API. The bot is the interface. This file is the internal contract tests lock.

## Content hashes

- Text: SHA-256 of the UTF-8 bytes Telegram put in `message.text` or, for a reply, `reply_to_message.text`. No normalisation, no trimming.
- File or photo: SHA-256 of the downloaded bytes. The caption is not included. The filename is metadata on the seal, not part of the content hash.

## Seal record `stipula-seal-v1`

```text
stipula-seal-v1
public_id=STL-XXXX-XXXX
kind=artefact|commitment|decision
chat_id=<int>
actor_id=<int>
content_hash=<64 hex>
prev_hash=<64 hex>
created_at=<unix>
byte_size=<int or ->
filename=<one line or ->
```

`seal_hash` is SHA-256 of that UTF-8 text, including the trailing newline.

Genesis for chat `C` is SHA-256 of `stipula-genesis-v1\nC` with no extra newline.

## Witness `stipula-witness-v1`

```text
stipula-witness-v1
seal_hash=<seal hash>
user_id=<int>
witnessed_at=<unix>
```

## Commitment preimage `stipula-commit-v1`

```text
stipula-commit-v1
commitment_id=CMT-XXXX-XXXX
action=propose|bind|accept|decline|fulfill|cancel
actor_id=<int>
counterparty_id=<int>
title=<single line>
detail=<single line or ->
due_on=<YYYY-MM-DD or ->
```

`bind` is a self-commitment and starts active. `propose` waits for accept.

## Decision preimage `stipula-decision-v1`

Open:

```text
stipula-decision-v1
decision_id=DEC-XXXX-XXXX
action=open
actor_id=<int>
question=<single line>
```

Close:

```text
stipula-decision-v1
decision_id=DEC-XXXX-XXXX
action=close
actor_id=<int>
yes=<int>
no=<int>
abstain=<int>
closed_at=<unix>
```

## Codes

Crockford base32, alphabet `0123456789ABCDEFGHJKMNPQRSTVWXYZ`, eight characters as `XXXX-XXXX`, prefixed `STL`, `CMT`, or `DEC`.

## Callback data

`wit:`, `cac:`, `cde:`, `cfu:`, `cca:`, `vy:`, `vn:`, `va:`, `dcl:`, `fgt:`. The value is the public code, except `fgt:1`.

## Export JSON

Top-level keys: `product` (`stipula`), `version` (1), `app_version`, `exported_at`, `user_id`, `truncated`, `seals`, `commitments`, `decisions`. Sorted keys, UTF-8, pretty-printed. At most 1000 seals authored by the user are scanned; `truncated` is true when that cap is hit.

## Environment

See `.env.example`. `check --offline` does not require `BOT_TOKEN`. `run` does.
