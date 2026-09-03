"""SQLite database connection factory with safe defaults for SMB."""

import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

from molkey.infrastructure.migrations import SCHEMA_VERSION, get_schema_version, migrate


class DatabaseError(Exception):
    """Database operation error."""

    pass


def connect(
    db_path: Path,
    require_existing: bool = True,
    *,
    apply_migrations: bool = True,
) -> sqlite3.Connection:
    """Create a SQLite connection with safe defaults for shared-drive use.

    Args:
        db_path: Path to the SQLite database file.
        require_existing: If True, raise DatabaseError if database doesn't exist.
        apply_migrations: If True, run migrations on new databases.

    Returns:
        Configured sqlite3.Connection with:
        - foreign_keys=ON
        - journal_mode=DELETE (not WAL, for SMB safety)
        - synchronous=FULL
        - busy_timeout=30000ms (readers survive slow SMB commits)
        - temp_store=MEMORY
        - Row factory for dict-like access

    Raises:
        DatabaseError: If database doesn't exist and require_existing=True.
    """
    if require_existing and not db_path.exists():
        raise DatabaseError(f"Database not found at {db_path}")

    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn: sqlite3.Connection = sqlite3.connect(
        db_path,
        detect_types=sqlite3.PARSE_DECLTYPES,
        isolation_level="DEFERRED",
    )

    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = DELETE")
    conn.execute("PRAGMA synchronous = 3")  # FULL = 3
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA temp_store = MEMORY")
    conn.row_factory = sqlite3.Row

    if apply_migrations and get_schema_version(db_path) < SCHEMA_VERSION:
        migrate(db_path)

    return conn


@contextmanager
def transaction(
    db_path: Path,
    *,
    retry_on_busy: bool = True,
    max_retries: int = 3,
) -> Iterator[sqlite3.Connection]:
    """Run one short write transaction under the registry writer lock.

    The application lock is acquired before SQLite's ``BEGIN IMMEDIATE``.
    Busy errors while beginning the transaction use bounded exponential
    backoff. Once control is yielded to the caller, the body is never replayed.
    """
    from molkey.infrastructure.writer_lock import writer_lock

    if max_retries < 0:
        raise ValueError("max_retries must be zero or greater")

    with writer_lock(db_path.parent):
        conn = connect(db_path, require_existing=True, apply_migrations=False)
        # We perform our own short, bounded retry loop for BEGIN IMMEDIATE.
        conn.execute("PRAGMA busy_timeout = 0")
        attempts = max_retries + 1 if retry_on_busy else 1

        try:
            for attempt in range(1, attempts + 1):
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    break
                except sqlite3.OperationalError as exc:
                    is_busy = "locked" in str(exc).lower() or "busy" in str(exc).lower()
                    if not is_busy:
                        raise DatabaseError(f"Database operation failed: {exc}") from exc
                    if attempt == attempts:
                        raise DatabaseError(f"Database busy after {attempts} attempts: {exc}") from exc
                    time.sleep(0.05 * (2 ** (attempt - 1)))

            # BEGIN IMMEDIATE only needs the RESERVED lock, which coexists with
            # readers; the collision point is COMMIT, which needs EXCLUSIVE and
            # blocks while any reader holds SHARED. Let COMMIT wait out readers
            # instead of failing instantly.
            conn.execute("PRAGMA busy_timeout = 30000")

            try:
                yield conn
            except sqlite3.Error as exc:
                with suppress(sqlite3.Error):
                    conn.rollback()
                raise DatabaseError(f"Database operation failed: {exc}") from exc
            except BaseException:
                with suppress(sqlite3.Error):
                    conn.rollback()
                raise
            else:
                conn.commit()
                # Keep query-planner statistics current without blocking readers
                # (cheap no-op until the tables grow; a periodic ANALYZE fires on close thresholds)
                with suppress(sqlite3.Error):
                    conn.execute("PRAGMA optimize")
        finally:
            conn.close()


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        db = Path(tmpdir) / "test.db"
        conn = connect(db, require_existing=False)
        print("Connected:", conn.execute("PRAGMA journal_mode").fetchone())
        print("Foreign keys:", conn.execute("PRAGMA foreign_keys").fetchone())
        print("Synchronous:", conn.execute("PRAGMA synchronous").fetchone())
        print("Busy timeout:", conn.execute("PRAGMA busy_timeout").fetchone())
        print("Temp store:", conn.execute("PRAGMA temp_store").fetchone())
        conn.close()
