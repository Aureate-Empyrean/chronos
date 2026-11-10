"""Rehearse Chronos's schema migration on a throwaway copy of a database.

    python scripts/rehearse_migration.py <path to chronos.sqlite3>

Only reads the given file (and its -wal), and migrates its own temporary copy. Prints counts and
verdicts, never content. Exits non-zero if anything that existed before the migration changed.
Requires the backend on PYTHONPATH."""

import hashlib
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

from chronos.db import MIGRATIONS, Database


def inventory(conn):
    """For every table: its columns and a digest of those columns in every row."""
    tables = {}
    names = "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    for (table,) in conn.execute(names).fetchall():
        columns = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
        tables[table] = columns
    return tables


def digest(conn, table, columns):
    selected = ",".join(f'"{c}"' for c in columns)
    rows = sorted(repr(tuple(row)) for row in conn.execute(f'SELECT {selected} FROM "{table}"'))
    return len(rows), hashlib.sha256("\n".join(rows).encode()).hexdigest()


def rehearse(source: Path) -> bool:
    with tempfile.TemporaryDirectory() as folder:
        copy = Path(folder) / "chronos.sqlite3"
        shutil.copyfile(source, copy)
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{source}{suffix}")
            if sidecar.exists():
                shutil.copyfile(sidecar, f"{copy}{suffix}")

        conn = sqlite3.connect(copy)
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        columns = inventory(conn)
        before = {table: digest(conn, table, cols) for table, cols in columns.items()}
        conn.close()
        print(f"schema {version} -> {len(MIGRATIONS)}")

        db = Database(copy)
        good = True
        with db.connect() as conn:
            after = {table: digest(conn, table, cols) for table, cols in columns.items()}
            for table, (count, value) in sorted(before.items()):
                unchanged = after[table] == (count, value)
                good &= unchanged
                print(f"{table}: {count} rows, {'unchanged' if unchanged else 'CHANGED'}")
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            orphans = conn.execute("PRAGMA foreign_key_check").fetchall()
            total, active = conn.execute(
                "SELECT count(*), coalesce(sum(trashed_at IS NULL),0) FROM events"
            ).fetchone()
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        print(f"integrity {integrity}; foreign key violations {len(orphans)}")
        print(f"events {total}, active {active}; schema now {version}")
        return good and integrity == "ok" and not orphans and total == active


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    if not rehearse(Path(sys.argv[1])):
        raise SystemExit("Rehearsal FAILED: do not apply this migration.")
    print("Rehearsal passed.")
