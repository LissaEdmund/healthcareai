"""SQLite connection handling and the versioned migration runner."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from .config import get_settings

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


class DatabaseError(RuntimeError):
    """Raised when the database is unavailable or a statement fails unexpectedly."""


def utcnow() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def connect(path: Path | None = None) -> sqlite3.Connection:
    db_path = path or get_settings().database_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        # check_same_thread=False: a request-scoped connection may be created in the threadpool and used
        # by an async endpoint; it is never shared between concurrent requests.
        conn = sqlite3.connect(db_path, timeout=10, isolation_level=None, check_same_thread=False)
    except sqlite3.Error as exc:  # pragma: no cover - depends on filesystem state
        raise DatabaseError(f"Cannot open database: {exc}") from exc
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


@contextmanager
def get_conn(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = connect(path)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """BEGIN IMMEDIATE ... COMMIT, rolling back on any exception."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def applied_migrations(conn: sqlite3.Connection) -> set[str]:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    return {row["version"] for row in conn.execute("SELECT version FROM schema_migrations")}


def migrate(conn: sqlite3.Connection) -> list[str]:
    """Apply pending migrations in filename order. Returns the versions applied."""
    done = applied_migrations(conn)
    applied: list[str] = []
    for script in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = script.stem
        if version in done:
            continue
        sql = script.read_text(encoding="utf-8")
        try:
            conn.executescript(f"BEGIN;\n{sql}\nINSERT INTO schema_migrations VALUES ('{version}', '{utcnow()}');\nCOMMIT;")
        except sqlite3.Error as exc:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise DatabaseError(f"Migration {version} failed: {exc}") from exc
        applied.append(version)
    return applied


def check_health(path: Path | None = None) -> tuple[bool, str]:
    try:
        with get_conn(path) as conn:
            versions = applied_migrations(conn)
            if not versions:
                return False, "database has no applied migrations (run: uv run hcai init-db)"
            return True, f"ok (migrations: {', '.join(sorted(versions))})"
    except (sqlite3.Error, DatabaseError) as exc:
        return False, f"database error: {exc}"
