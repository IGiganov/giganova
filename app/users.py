import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.config import settings
from app.security import hash_password, verify_password


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    path = Path(settings.users_db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    columns = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
    if "full_name" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN full_name TEXT NOT NULL DEFAULT ''")
    conn.commit()
    return conn


def init_users_db() -> None:
    _connect().close()


def user_count() -> int:
    conn = _connect()
    try:
        row = conn.execute("SELECT COUNT(*) FROM users").fetchone()
        return int(row[0] or 0)
    finally:
        conn.close()


def user_exists(username: str) -> bool:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT 1 FROM users WHERE username = ? LIMIT 1", (username.strip(),)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def create_user(username: str, password: str, full_name: str = "") -> None:
    username = username.strip()
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, full_name, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (username, hash_password(password), full_name.strip(), _now(), _now()),
        )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        raise ValueError("That username already exists.") from exc
    finally:
        conn.close()


def get_full_name(username: str) -> Optional[str]:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT full_name FROM users WHERE username = ?", (username.strip(),)
        ).fetchone()
        if not row:
            return None
        return row[0] or None
    finally:
        conn.close()


def set_full_name(username: str, full_name: str) -> bool:
    conn = _connect()
    try:
        cursor = conn.execute(
            "UPDATE users SET full_name = ?, updated_at = ? WHERE username = ?",
            (full_name.strip(), _now(), username.strip()),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def get_password_hash(username: str) -> Optional[str]:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE username = ?", (username.strip(),)
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def verify_user(username: str, password: str) -> bool:
    stored = get_password_hash(username)
    if stored is None:
        return False
    return verify_password(password, stored)


def set_password(username: str, new_password: str) -> None:
    """Update an existing user's password, or create the user if missing (upsert)."""
    username = username.strip()
    conn = _connect()
    try:
        cursor = conn.execute(
            "UPDATE users SET password_hash = ?, updated_at = ? WHERE username = ?",
            (hash_password(new_password), _now(), username),
        )
        if cursor.rowcount == 0:
            conn.execute(
                "INSERT INTO users (username, password_hash, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (username, hash_password(new_password), _now(), _now()),
            )
        conn.commit()
    finally:
        conn.close()
