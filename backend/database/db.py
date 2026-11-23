"""Database metadata (SQLite) untuk user, proyek, eksekusi, audit, riwayat file, dsb."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

SCHEMA_VERSION = 2

# Kolom tambahan (migrasi ringan, idempoten): tabel -> [(kolom, definisi)]
MIGRATIONS: dict[str, list[tuple[str, str]]] = {
    "ai_proposals": [
        ("conversation_id", "INTEGER"), ("message_id", "INTEGER"),
        ("base_sha256", "TEXT"), ("new_sha256", "TEXT"), ("old_content", "TEXT"),
        ("existed", "INTEGER NOT NULL DEFAULT 1"), ("diff", "TEXT NOT NULL DEFAULT ''"),
        ("additions", "INTEGER NOT NULL DEFAULT 0"), ("deletions", "INTEGER NOT NULL DEFAULT 0"),
        ("error", "TEXT NOT NULL DEFAULT ''"),
    ],
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'developer',
    extra_perms TEXT NOT NULL DEFAULT '[]',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS revoked_tokens (jti TEXT PRIMARY KEY, exp INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL DEFAULT '',
    owner_id INTEGER NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS favorites (
    user_id INTEGER NOT NULL, project_id TEXT NOT NULL, path TEXT NOT NULL, created_at REAL NOT NULL,
    PRIMARY KEY (user_id, project_id, path)
);
CREATE TABLE IF NOT EXISTS recent_files (
    user_id INTEGER NOT NULL, project_id TEXT NOT NULL, path TEXT NOT NULL, opened_at REAL NOT NULL,
    PRIMARY KEY (user_id, project_id, path)
);
CREATE TABLE IF NOT EXISTS executions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    language TEXT NOT NULL,
    file TEXT NOT NULL DEFAULT '',
    command TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL,
    exit_code INTEGER,
    stdout TEXT NOT NULL DEFAULT '',
    stderr TEXT NOT NULL DEFAULT '',
    truncated INTEGER NOT NULL DEFAULT 0,
    error TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    start_time REAL,
    end_time REAL,
    duration REAL
);
CREATE INDEX IF NOT EXISTS ix_exec_project ON executions(project_id, created_at);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL, user_id INTEGER, username TEXT, action TEXT NOT NULL,
    target TEXT NOT NULL DEFAULT '', detail TEXT NOT NULL DEFAULT '', ip TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS file_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL, path TEXT NOT NULL, action TEXT NOT NULL,
    snapshot TEXT, sha256 TEXT, size INTEGER,
    actor_id INTEGER, actor_type TEXT NOT NULL DEFAULT 'user', note TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_hist_path ON file_history(project_id, path, created_at);
CREATE TABLE IF NOT EXISTS http_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL, collection TEXT NOT NULL DEFAULT 'default', name TEXT NOT NULL,
    method TEXT NOT NULL, url TEXT NOT NULL, headers TEXT NOT NULL DEFAULT '{}',
    params TEXT NOT NULL DEFAULT '{}', body TEXT, body_type TEXT NOT NULL DEFAULT 'none',
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS git_credentials (
    user_id INTEGER NOT NULL, host TEXT NOT NULL, username TEXT NOT NULL, secret TEXT NOT NULL,
    created_at REAL NOT NULL, PRIMARY KEY (user_id, host)
);
CREATE TABLE IF NOT EXISTS ai_connections (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL, location TEXT NOT NULL,
    base_url TEXT NOT NULL, api_key TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ai_conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, title TEXT NOT NULL DEFAULT 'Percakapan baru',
    connection_id TEXT, model TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_aiconv_user ON ai_conversations(user_id, updated_at);
CREATE TABLE IF NOT EXISTS ai_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id INTEGER NOT NULL, role TEXT NOT NULL,
    content TEXT NOT NULL, reasoning TEXT NOT NULL DEFAULT '', model TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_aimsg_conv ON ai_messages(conversation_id, id);
CREATE TABLE IF NOT EXISTS ai_proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL, user_id INTEGER NOT NULL, path TEXT NOT NULL, action TEXT NOT NULL,
    content TEXT, reason TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'pending',
    created_at REAL NOT NULL, decided_at REAL
);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._local = threading.local()
        with self._lock:
            self._conn().executescript(SCHEMA)
            self._migrate()
        with self.tx() as c:
            c.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?)", (str(SCHEMA_VERSION),))

    def _migrate(self) -> None:
        conn = self._conn()
        for table, cols in MIGRATIONS.items():
            have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
            for name, decl in cols:
                if name not in have:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, timeout=15, isolation_level=None, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=15000")
            self._local.conn = conn
        return conn

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        conn = self._conn()
        with self._lock:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise

    def execute(self, sql: str, params: tuple | dict = ()) -> sqlite3.Cursor:
        with self.tx() as c:
            return c.execute(sql, params)

    def one(self, sql: str, params: tuple | dict = ()) -> dict[str, Any] | None:
        row = self._conn().execute(sql, params).fetchone()
        return dict(row) if row else None

    def all(self, sql: str, params: tuple | dict = ()) -> list[dict[str, Any]]:
        return [dict(r) for r in self._conn().execute(sql, params).fetchall()]

    def audit(self, action: str, *, user: dict | None = None, target: str = "", detail: Any = "", ip: str = "") -> None:
        if not isinstance(detail, str):
            detail = json.dumps(detail, ensure_ascii=False, default=str)
        self.execute(
            "INSERT INTO audit_log(ts, user_id, username, action, target, detail, ip) VALUES(?,?,?,?,?,?,?)",
            (time.time(), user.get("id") if user else None, user.get("username") if user else None, action, target, detail[:4000], ip),
        )
        import logging

        logging.getLogger("coding_server.audit").info(
            "%s user=%s target=%s", action, user.get("username") if user else "-", target
        )
