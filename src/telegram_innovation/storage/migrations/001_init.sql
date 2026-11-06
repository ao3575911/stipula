CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS chats (
    chat_id INTEGER PRIMARY KEY,
    chat_type TEXT NOT NULL,
    title TEXT,
    chain_head TEXT NOT NULL,
    seal_count INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    plan TEXT NOT NULL DEFAULT 'free',
    retain_default INTEGER NOT NULL DEFAULT 0,
    show_username INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS seals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    public_id TEXT NOT NULL UNIQUE,
    chat_id INTEGER NOT NULL REFERENCES chats(chat_id),
    actor_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    action TEXT NOT NULL,
    subject_id TEXT,
    content_hash TEXT NOT NULL,
    seal_hash TEXT NOT NULL UNIQUE,
    prev_hash TEXT NOT NULL,
    canonical TEXT NOT NULL,
    preimage TEXT,
    filename TEXT,
    byte_size INTEGER,
    mime TEXT,
    metered INTEGER NOT NULL DEFAULT 1,
    source_update_id INTEGER UNIQUE,
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_seals_chat ON seals(chat_id, id);
CREATE INDEX IF NOT EXISTS idx_seals_actor_time ON seals(actor_id, created_at);
CREATE INDEX IF NOT EXISTS idx_seals_subject ON seals(subject_id);

CREATE TABLE IF NOT EXISTS witnesses (
    seal_public_id TEXT NOT NULL REFERENCES seals(public_id),
    user_id INTEGER NOT NULL,
    witness_hash TEXT NOT NULL,
    witnessed_at INTEGER NOT NULL,
    PRIMARY KEY (seal_public_id, user_id)
);

CREATE TABLE IF NOT EXISTS commitments (
    public_id TEXT PRIMARY KEY,
    chat_id INTEGER NOT NULL REFERENCES chats(chat_id),
    creator_id INTEGER NOT NULL,
    counterparty_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    detail TEXT,
    due_on TEXT,
    status TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS decisions (
    public_id TEXT PRIMARY KEY,
    chat_id INTEGER NOT NULL REFERENCES chats(chat_id),
    creator_id INTEGER NOT NULL,
    question TEXT NOT NULL,
    status TEXT NOT NULL,
    yes_count INTEGER NOT NULL DEFAULT 0,
    no_count INTEGER NOT NULL DEFAULT 0,
    abstain_count INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    closed_at INTEGER
);

CREATE TABLE IF NOT EXISTS votes (
    decision_id TEXT NOT NULL REFERENCES decisions(public_id),
    user_id INTEGER NOT NULL,
    choice TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (decision_id, user_id)
);

CREATE TABLE IF NOT EXISTS pending (
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    payload TEXT,
    expires_at INTEGER NOT NULL,
    PRIMARY KEY (chat_id, user_id)
);
