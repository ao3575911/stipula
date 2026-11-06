# Build plan

The MVP is the seal chain. Everything else hangs off it.

1. Canonical bytes and pinned vectors. If this moves, old seals die. Tests lock `Hello, Stipula`.
2. SQLite schema and idempotent migration.
3. Service transactions: seal, witness, verify, audit, commitment, decision, export, forget, quota.
4. Command application with HTML escaping, rate limit, and owner checks. No Telegram imports.
5. aiogram adapter: long polling, bounded downloads, present() that logs API failures by exception class so a token in a URL is not written out.
6. CLI `run`, `migrate`, `check --offline`.
7. Docs that describe the behaviour above, not a larger imagined product.

Explicitly deferred: webhooks, Stars payments, Mini App, multi-process locking, external timestamp authorities.
