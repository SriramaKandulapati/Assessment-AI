import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from app.config import DATABASE_PATH


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def init_db():
    folder = os.path.dirname(os.path.abspath(DATABASE_PATH))
    os.makedirs(folder, exist_ok=True)
    with connect() as db:
        db.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS links (
            code TEXT PRIMARY KEY,
            target_url TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT,
            disabled INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS clicks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL REFERENCES links(code),
            clicked_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_clicks_code_time ON clicks(code, clicked_at);
        CREATE TABLE IF NOT EXISTS workflow_runs (
            id TEXT PRIMARY KEY,
            scenario TEXT NOT NULL,
            requirement TEXT NOT NULL,
            state TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS workflow_events (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL REFERENCES workflow_runs(id),
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            stage TEXT,
            detail TEXT NOT NULL
        );
        """)


@contextmanager
def connect():
    db = sqlite3.connect(DATABASE_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def json_dump(value):
    return json.dumps(value, separators=(",", ":"), sort_keys=True)
