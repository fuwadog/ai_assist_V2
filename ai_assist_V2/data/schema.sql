-- AI Assistant CLI V2 - SQLite Schema
-- Auto-created by core/storage.py on first run

CREATE TABLE IF NOT EXISTS file_summaries (
    filepath     TEXT    PRIMARY KEY,
    summary      TEXT    NOT NULL,
    token_count  INTEGER NOT NULL,
    file_mtime   REAL    NOT NULL,  -- os.path.getmtime() at save time
    created_at   REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS query_cache (
    query_hash   TEXT    PRIMARY KEY,
    response     TEXT    NOT NULL,
    method       TEXT    NOT NULL,   -- 'baseline' or 'deep_research'
    token_count  INTEGER NOT NULL,
    expires_at   REAL    NOT NULL,
    created_at   REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS session_stats (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT    NOT NULL,
    query           TEXT    NOT NULL,
    method          TEXT    NOT NULL,
    tokens_used     INTEGER NOT NULL,
    files_searched  INTEGER DEFAULT 0,
    iterations      INTEGER DEFAULT 0,
    cache_hit       INTEGER NOT NULL,  -- SQLite boolean: 0/1
    timestamp       REAL    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_query_cache_expires  ON query_cache(expires_at);
CREATE INDEX IF NOT EXISTS idx_session_stats_ts     ON session_stats(timestamp);
CREATE INDEX IF NOT EXISTS idx_session_stats_sid    ON session_stats(session_id);
