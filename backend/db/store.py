"""Tiny SQLite store (stdlib). Sessions, recommendations and plans are JSON documents.

The TRD's SQLAlchemy model is simplified to JSON blobs for the prototype; the table
names match so a migration later is mechanical.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone

from config import get_settings

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None
_path: str | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, data TEXT NOT NULL, created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS recommendations (id TEXT PRIMARY KEY, session_id TEXT, data TEXT NOT NULL, created_at TEXT);
CREATE TABLE IF NOT EXISTS plans (id TEXT PRIMARY KEY, session_id TEXT, recommendation_id TEXT, data TEXT NOT NULL, created_at TEXT);
CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, kind TEXT, data TEXT, created_at TEXT);
"""


def _db() -> sqlite3.Connection:
    global _conn, _path
    path = str(get_settings().db_path)
    if _conn is None or _path != path:
        _conn = sqlite3.connect(path, check_same_thread=False)
        _conn.executescript(SCHEMA)
        _path = path
    return _conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def put(table: str, doc_id: str, data: dict, **cols) -> None:
    with _lock:
        db = _db()
        payload = json.dumps(data, ensure_ascii=False)
        if table == "sessions":
            db.execute("INSERT INTO sessions(id,data,created_at,updated_at) VALUES(?,?,?,?) "
                       "ON CONFLICT(id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
                       (doc_id, payload, _now(), _now()))
        else:
            keys = ["id", "data", "created_at", *cols.keys()]
            vals = [doc_id, payload, _now(), *cols.values()]
            db.execute(f"INSERT OR REPLACE INTO {table}({','.join(keys)}) VALUES({','.join('?' * len(keys))})", vals)
        db.commit()


def get(table: str, doc_id: str) -> dict | None:
    with _lock:
        row = _db().execute(f"SELECT data FROM {table} WHERE id=?", (doc_id,)).fetchone()
    return json.loads(row[0]) if row else None


def log_event(session_id: str, kind: str, data: dict) -> None:
    with _lock:
        db = _db()
        db.execute("INSERT INTO events(session_id,kind,data,created_at) VALUES(?,?,?,?)",
                   (session_id, kind, json.dumps(data, ensure_ascii=False), _now()))
        db.commit()
