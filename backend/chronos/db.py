import sqlite3
from contextlib import contextmanager
from pathlib import Path

# Times: timed events store UTC instants as "YYYY-MM-DDTHH:MM:SSZ" plus their IANA zone;
# all-day events store "YYYY-MM-DD" dates with an exclusive end and no zone.
# range_start/range_end are UTC instants used only to index candidate rows for a query
# window; range_end NULL means an unbounded recurrence.
MIGRATIONS = [
    """
CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE calendars(id TEXT PRIMARY KEY,
 kind TEXT NOT NULL CHECK(kind IN ('native','import','subscription')),
 name TEXT NOT NULL, color TEXT NOT NULL, visible INTEGER NOT NULL DEFAULT 1,
 position INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE subscriptions(calendar_id TEXT PRIMARY KEY REFERENCES calendars(id) ON DELETE CASCADE,
 url TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1, refresh_minutes INTEGER NOT NULL DEFAULT 360,
 last_attempt_at TEXT, last_success_at TEXT, last_error TEXT, last_warning TEXT,
 etag TEXT, last_modified TEXT, content_hash TEXT, next_attempt REAL NOT NULL DEFAULT 0,
 failures INTEGER NOT NULL DEFAULT 0, running INTEGER NOT NULL DEFAULT 0);
CREATE TABLE imports(id TEXT PRIMARY KEY, calendar_id TEXT NOT NULL REFERENCES calendars(id) ON DELETE CASCADE,
 filename TEXT NOT NULL, imported_at TEXT NOT NULL, created INTEGER NOT NULL, updated INTEGER NOT NULL,
 unchanged INTEGER NOT NULL, skipped INTEGER NOT NULL);
CREATE TABLE categories(id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE,
 color TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE events(id TEXT PRIMARY KEY, calendar_id TEXT NOT NULL REFERENCES calendars(id) ON DELETE CASCADE,
 origin TEXT NOT NULL CHECK(origin IN ('native','import','subscription')),
 title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', location TEXT NOT NULL DEFAULT '',
 all_day INTEGER NOT NULL, start TEXT NOT NULL, end TEXT NOT NULL, time_zone TEXT,
 rrule TEXT, exdates TEXT NOT NULL DEFAULT '[]', recurrence_id TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'confirmed' CHECK(status IN ('confirmed','tentative','cancelled')),
 category_id TEXT REFERENCES categories(id) ON DELETE SET NULL, color TEXT NOT NULL DEFAULT '',
 source_uid TEXT, sequence INTEGER NOT NULL DEFAULT 0, content_hash TEXT,
 range_start TEXT NOT NULL, range_end TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 UNIQUE(calendar_id, source_uid, recurrence_id));
CREATE INDEX events_range ON events(range_start, range_end);
CREATE INDEX events_calendar ON events(calendar_id);
CREATE TABLE tombstones(id TEXT PRIMARY KEY, kind TEXT NOT NULL, deleted_at TEXT NOT NULL);
CREATE TABLE links(id TEXT PRIMARY KEY, event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
 target TEXT NOT NULL, relation TEXT NOT NULL, readers TEXT NOT NULL DEFAULT '[]',
 label TEXT NOT NULL DEFAULT '', remote_id TEXT, UNIQUE(event_id, target, relation));
CREATE TABLE outbox(id INTEGER PRIMARY KEY AUTOINCREMENT, method TEXT NOT NULL, path TEXT NOT NULL,
 body TEXT, link_id TEXT, attempts INTEGER NOT NULL DEFAULT 0, next_attempt REAL NOT NULL DEFAULT 0);
CREATE TABLE sources(provider TEXT PRIMARY KEY, enabled INTEGER NOT NULL, color TEXT NOT NULL,
 show_completed INTEGER NOT NULL DEFAULT 0, last_attempt_at TEXT, last_success_at TEXT,
 last_error TEXT, availability TEXT, item_count INTEGER NOT NULL DEFAULT 0,
 next_attempt REAL NOT NULL DEFAULT 0);
CREATE TABLE projected(provider TEXT NOT NULL, item_id TEXT NOT NULL, resource TEXT NOT NULL,
 kind TEXT NOT NULL, title TEXT NOT NULL, start TEXT NOT NULL, end TEXT, all_day INTEGER NOT NULL,
 time_zone TEXT, certainty TEXT NOT NULL, status TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '',
 context TEXT NOT NULL DEFAULT '', group_resource TEXT, group_label TEXT, updated_at TEXT,
 fetched_at TEXT NOT NULL, range_start TEXT NOT NULL, range_end TEXT NOT NULL,
 PRIMARY KEY(provider, item_id));
CREATE INDEX projected_range ON projected(range_start, range_end);
CREATE TABLE cursors(name TEXT PRIMARY KEY, value INTEGER NOT NULL);
""",
    # 0.4.0: an event returned by link-search may be labelled for the module that searched (ADR 0029).
    """
CREATE TABLE link_grants(event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
 requester TEXT NOT NULL, granted_at TEXT NOT NULL, PRIMARY KEY(event_id, requester));
""",
    # 0.6.0: Trash. Additive only: no existing row is rewritten, and every event stays active.
    # An event in Trash keeps its row (trashed_at set) and an occurrence in Trash stays in the
    # series' exdates, so `trash` only records what can be recovered. trash_audit holds ids and
    # times, never content, and outlives permanent deletion.
    """
ALTER TABLE calendars ADD COLUMN trashed_at TEXT;
ALTER TABLE events ADD COLUMN trashed_at TEXT;
CREATE INDEX events_trashed ON events(trashed_at) WHERE trashed_at IS NOT NULL;
CREATE TABLE trash(id TEXT PRIMARY KEY,
 kind TEXT NOT NULL CHECK(kind IN ('event','series','occurrence')),
 event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
 occurrence TEXT NOT NULL DEFAULT '', deleted_at TEXT NOT NULL, batch TEXT NOT NULL,
 cause TEXT NOT NULL DEFAULT 'user' CHECK(cause IN ('user','calendar')),
 snapshot TEXT NOT NULL, search TEXT NOT NULL DEFAULT '',
 UNIQUE(event_id, occurrence));
CREATE INDEX trash_batch ON trash(batch);
CREATE TABLE trash_audit(seq INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL,
 action TEXT NOT NULL CHECK(action IN ('trash','restore','purge')), kind TEXT NOT NULL,
 entry_id TEXT NOT NULL, event_id TEXT NOT NULL, occurrence TEXT NOT NULL DEFAULT '',
 batch TEXT NOT NULL DEFAULT '');
""",
    # 0.7.0: optimistic concurrency. Additive only; every existing record starts at revision 1.
    # A write must name the revision it was based on, so a stale client cannot overwrite newer data.
    """
ALTER TABLE events ADD COLUMN revision INTEGER NOT NULL DEFAULT 1;
ALTER TABLE calendars ADD COLUMN revision INTEGER NOT NULL DEFAULT 1;
ALTER TABLE categories ADD COLUMN revision INTEGER NOT NULL DEFAULT 1;
""",
]


class Database:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    def migrate(self):
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > len(MIGRATIONS):
                raise RuntimeError("Database is newer than this application")
            for i in range(version, len(MIGRATIONS)):
                db.executescript(
                    "BEGIN IMMEDIATE;\n" + MIGRATIONS[i] + f"\nPRAGMA user_version={i + 1}; COMMIT;"
                )

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()
