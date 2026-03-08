"""SQLite persistence layer for AI Assistant CLI V2."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from utils.logger import logger


class Storage:
    """
    Manages the SQLite database.

    Tables:
      - file_summaries: AST summaries keyed by absolute filepath
      - query_cache:    LLM responses keyed by MD5(query) with TTL
      - session_stats:  Per-query analytics
    """

    def __init__(self, db_path: Path = Path("data/ai_assistant.db")) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection = sqlite3.connect(
            str(self.db_path), check_same_thread=False
        )
        self._conn.row_factory = sqlite3.Row
        self._apply_schema()

    # ── Schema ─────────────────────────────────────────────────────────────

    def _apply_schema(self) -> None:
        """Create tables if they don't exist."""
        schema_path = Path(__file__).parent.parent / "data" / "schema.sql"
        if schema_path.exists():
            sql = schema_path.read_text()
        else:
            # Inline fallback schema
            sql = _INLINE_SCHEMA
        with self._conn:
            self._conn.executescript(sql)
        logger.debug("Database schema applied at %s", self.db_path)

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._conn:
            return self._conn.execute(sql, params)

    def _query_one(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        return self._conn.execute(sql, params).fetchone()

    def _query_all(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        return self._conn.execute(sql, params).fetchall()

    # ── File Summaries ──────────────────────────────────────────────────────

    def get_file_summary(self, filepath: str) -> str | None:
        """
        Return cached AST summary for *filepath* if still fresh.

        A summary is fresh when ``file_mtime`` matches the current mtime.
        """
        row = self._query_one(
            "SELECT summary, file_mtime FROM file_summaries WHERE filepath = ?",
            (filepath,),
        )
        if row is None:
            return None

        try:
            current_mtime = os.path.getmtime(filepath)
        except OSError:
            return None

        if abs(row["file_mtime"] - current_mtime) > 0.01:
            # File changed — cache stale
            logger.debug("Cache stale for %s (mtime changed)", filepath)
            return None

        return row["summary"]

    def save_file_summary(self, filepath: str, summary: str, token_count: int) -> None:
        """Persist an AST summary, overwriting any prior entry."""
        mtime = os.path.getmtime(filepath)
        self._execute(
            """
            INSERT OR REPLACE INTO file_summaries
                (filepath, summary, token_count, file_mtime, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (filepath, summary, token_count, mtime, time.time()),
        )

    # ── Query Cache ─────────────────────────────────────────────────────────

    @staticmethod
    def _query_hash(query: str) -> str:
        return hashlib.md5(query.encode()).hexdigest()

    def get_cached_response(self, query: str) -> dict[str, Any] | None:
        """Return cached LLM response if not expired, else None."""
        row = self._query_one(
            """
            SELECT response, method, token_count
            FROM query_cache
            WHERE query_hash = ? AND expires_at > ?
            """,
            (self._query_hash(query), time.time()),
        )
        if row is None:
            return None
        return {
            "response": row["response"],
            "method": row["method"],
            "token_count": row["token_count"],
        }

    def cache_response(
        self,
        query: str,
        response: str,
        method: str,
        token_count: int,
        ttl: int = 3600,
    ) -> None:
        """Persist an LLM response with a TTL (seconds)."""
        self._execute(
            """
            INSERT OR REPLACE INTO query_cache
                (query_hash, response, method, token_count, expires_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                self._query_hash(query),
                response,
                method,
                token_count,
                time.time() + ttl,
                time.time(),
            ),
        )

    def cleanup_expired_cache(self) -> int:
        """Delete expired cache entries. Returns number of rows deleted."""
        cur = self._execute(
            "DELETE FROM query_cache WHERE expires_at < ?", (time.time(),)
        )
        return cur.rowcount

    # ── Session Stats ───────────────────────────────────────────────────────

    def log_query(
        self,
        session_id: str,
        query: str,
        method: str,
        tokens_used: int,
        files_searched: int = 0,
        iterations: int = 0,
        cache_hit: bool = False,
    ) -> None:
        """Record a query result for analytics."""
        self._execute(
            """
            INSERT INTO session_stats
                (session_id, query, method, tokens_used, files_searched,
                 iterations, cache_hit, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                query,
                method,
                tokens_used,
                files_searched,
                iterations,
                1 if cache_hit else 0,
                time.time(),
            ),
        )

    def get_stats(self, session_id: str | None = None) -> dict[str, Any]:
        """Aggregate session stats.  Pass None for all-time stats."""
        where = "WHERE session_id = ?" if session_id else ""
        params: tuple = (session_id,) if session_id else ()

        rows = self._query_all(
            f"""
            SELECT
                method,
                COUNT(*)          AS count,
                SUM(tokens_used)  AS total_tokens,
                SUM(cache_hit)    AS cache_hits
            FROM session_stats
            {where}
            GROUP BY method
            """,
            params,
        )

        total_queries = sum(r["count"] for r in rows)
        total_cache_hits = sum(r["cache_hits"] for r in rows)
        total_tokens = sum(r["total_tokens"] or 0 for r in rows)

        by_method: dict[str, int] = {r["method"]: r["count"] for r in rows}

        return {
            "total_queries": total_queries,
            "cache_hits": total_cache_hits,
            "cache_hit_rate": total_cache_hits / total_queries if total_queries else 0,
            "total_tokens": total_tokens,
            "by_method": by_method,
        }

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()


# ── Inline fallback schema (if data/schema.sql is missing) ──────────────────

_INLINE_SCHEMA = """
CREATE TABLE IF NOT EXISTS file_summaries (
    filepath     TEXT    PRIMARY KEY,
    summary      TEXT    NOT NULL,
    token_count  INTEGER NOT NULL,
    file_mtime   REAL    NOT NULL,
    created_at   REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS query_cache (
    query_hash   TEXT    PRIMARY KEY,
    response     TEXT    NOT NULL,
    method       TEXT    NOT NULL,
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
    cache_hit       INTEGER NOT NULL,
    timestamp       REAL    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_query_cache_expires  ON query_cache(expires_at);
CREATE INDEX IF NOT EXISTS idx_session_stats_ts     ON session_stats(timestamp);
CREATE INDEX IF NOT EXISTS idx_session_stats_sid    ON session_stats(session_id);
"""
