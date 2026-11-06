# Product requirements

## Name

Stipula. Usernames worth claiming: `@stipula_bot`, `@sealatest_bot`, `@stipulabot`.

Tagline: Seal what was said. Prove it later.

## Thesis

A chat needs a way to freeze a specific artefact and show, later, that these bytes are the ones everyone saw. The proof should be understandable in one message and should get stronger when a second person witnesses it.

## Problem

Important chat messages are hard to cite. Full history exports keep too much. Screenshots are easy to crop. File versions drift because photos are recompressed and documents are renamed.

## Solution

The bot hashes the exact bytes, writes an immutable seal into a per-chat hash chain, and returns a card. Other users witness that card. A later replay either matches the content hash or it does not.

## Audience

Small teams, freelancers, clubs, and workshops who already argue and agree in Telegram and want a receipt without standing up a document system.

## Differentiation

Task bots track work. Poll bots count votes. Notary bots often imply a legal status they do not have. Stipula only claims a SHA-256, a chain link, and a list of witnesses. The card is the product.

## Signature

The seal card, plus replay verification. Witnesses are the network effect: a seal with no witness is a personal note; a seal with witnesses is a shared claim.

## Supporting behaviour

- Commitments (`/commit`) with accept, decline, fulfill, and cancel. Self-promises start active.
- Decisions (`/decide`) with yes, no, abstain, and a sealed close.
- `/export` and `/forget` for artefact copies.
- Inline lookup of a code the bot already knows.
- Deep link `https://t.me/<bot>?start=seal_STL-XXXX-XXXX`.

## Journeys

1. Private note. `/seal`, send the text, keep the card, `/verify` later by resending it.
2. Group file. Reply to a document with `/seal`. Someone else taps Witness. A renamed re-upload still matches, because the filename is not part of the content hash.
3. Two-party promise. `/commit @name 2026-12-01 Pay the deposit`. They tap Accept. Either party taps Fulfilled.
4. Group decision. `/decide Switch supplier?` Votes land. The opener or an admin closes. `/audit` fails if the stored tally is edited.

## Account lifecycle

The first message creates a user row: Telegram id, optional username, plan `free`. There is no separate password. `/settings retain on` keeps a private copy of future notes. `/settings username off` hides `@username` on witness lines. `/forget` deletes stored note text the user authored. Shared commitment and decision wording stays, because the other party needs it.

## Privacy

Default is hash only for notes. Commitment titles, decision questions, and votes are stored because the feature does not work without them. See `SECURITY.md`.

## Monetisation

Free quota is the default. Pro is an owner-granted flag (`/grant USER_ID`) with no monthly cap and no open-commitment cap. Telegram Stars is a later adapter, not implemented. The thing worth paying for is a busy group that wants export history and no quota, not a pile of extra features.

## MVP boundary

In: private chats and groups, text and files the Bot API will download, commitments, decisions, witness, audit, export, forget, inline lookup, JSON logs, SQLite.

Out: Mini Apps, webhooks, payments, legal notarisation, external timestamps, multi-instance polling, username trading, anonymity sets.

## Success

Someone seals a real file, a second person witnesses it, and a later replay matches. A partial database edit fails `/audit`. A stranger cannot fulfill someone else's commitment. Logs from a seal flow do not contain the sealed text.
