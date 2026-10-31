import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS messages (
    account TEXT, id TEXT, thread_id TEXT, sender TEXT, subject TEXT,
    snippet TEXT, received_at TEXT, class TEXT, summary TEXT,
    alerted_at TEXT, moved_by_script INTEGER DEFAULT 0,
    PRIMARY KEY (account, id)
);
CREATE TABLE IF NOT EXISTS blocked_senders (address TEXT PRIMARY KEY, blocked_at TEXT);
CREATE TABLE IF NOT EXISTS known_contacts (address TEXT PRIMARY KEY);
"""


def open_db(path="data/etat.db"):
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def get_state(conn, key, default=None):
    row = conn.execute("SELECT value FROM state WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_state(conn, key, value):
    with conn:
        conn.execute("INSERT OR REPLACE INTO state VALUES (?, ?)", (key, value))
