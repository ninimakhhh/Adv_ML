-- Ticket storage schema (SQLite with Postgres-compatible DDL)
-- Run via: python -m shared.db.migrate

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS tickets (
    ticket_id               TEXT        PRIMARY KEY,
    user_id                 TEXT,
    created_at              TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at             TIMESTAMP,
    channel                 TEXT        NOT NULL
                                CHECK (channel IN ('chat', 'email', 'web')),
    classified_intent       TEXT,
    classification_confidence REAL,
    resolution_path         TEXT        NOT NULL DEFAULT 'pending'
                                CHECK (resolution_path IN (
                                    'bot_resolved',
                                    'escalated_low_confidence',
                                    'escalated_user_request',
                                    'escalated_after_failure',
                                    'escalated_sensitive',
                                    'pending'
                                )),
    final_status            TEXT        NOT NULL DEFAULT 'open'
                                CHECK (final_status IN ('open', 'in_progress', 'resolved', 'closed')),
    csat_score              INTEGER     CHECK (csat_score BETWEEN 1 AND 5),
    agent_id                TEXT,
    tags                    TEXT        NOT NULL DEFAULT '[]',
    sentiment               TEXT        CHECK (sentiment IN ('positive', 'neutral', 'negative'))
);

CREATE TABLE IF NOT EXISTS messages (
    message_id      TEXT        PRIMARY KEY,
    ticket_id       TEXT        NOT NULL REFERENCES tickets (ticket_id) ON DELETE CASCADE,
    role            TEXT        NOT NULL CHECK (role IN ('user', 'bot', 'agent')),
    body            TEXT        NOT NULL,
    sent_at         TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_redacted     INTEGER     NOT NULL DEFAULT 0   -- boolean (0/1)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_tickets_user         ON tickets  (user_id);
CREATE INDEX IF NOT EXISTS idx_tickets_status       ON tickets  (final_status);
CREATE INDEX IF NOT EXISTS idx_tickets_intent       ON tickets  (classified_intent);
CREATE INDEX IF NOT EXISTS idx_tickets_created      ON tickets  (created_at);
CREATE INDEX IF NOT EXISTS idx_messages_ticket      ON messages (ticket_id);
CREATE INDEX IF NOT EXISTS idx_messages_sent        ON messages (sent_at);
