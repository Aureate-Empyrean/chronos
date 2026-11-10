"""Recoverable deletion of Chronos's own events.

An event in Trash keeps its row and id (`events.trashed_at` is set), so restoring cannot create
a second copy. One occurrence in Trash is a key in its series' `exdates`, as any skipped
occurrence is, plus a `trash` row saying that it can come back. Every recoverable thing has one
`trash` row; `UNIQUE(event_id, occurrence)` keeps it to one.

Only native events get here. Imported and subscribed events belong to their source and stay
read-only. Nothing is purged automatically: permanent deletion is always an explicit request.

Callers open a write transaction first (BEGIN IMMEDIATE), so each of these is atomic and
concurrent requests are serialized."""

import json

from chronos.recurrence import occurrence_at
from chronos.store import delete_event, index_bounds, publish_links, unpublish_links
from chronos.util import fold, iso_now, uuid7


class TrashError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


NOT_IN_TRASH = "This is no longer in Trash"


def _audit(conn, action, entry, stamp):
    conn.execute(
        "INSERT INTO trash_audit(at,action,kind,entry_id,event_id,occurrence,batch) "
        "VALUES(?,?,?,?,?,?,?)",
        (
            stamp,
            action,
            entry["kind"],
            entry["id"],
            entry["event_id"],
            entry["occurrence"],
            entry["batch"],
        ),
    )


def _snapshot(conn, row, start, end):
    """What was deleted, as it was then: the series may change while an occurrence is in Trash."""
    calendar = conn.execute(
        "SELECT name,color FROM calendars WHERE id=?", (row["calendar_id"],)
    ).fetchone()
    category = (
        conn.execute(
            "SELECT name,color FROM categories WHERE id=?", (row["category_id"],)
        ).fetchone()
        if row["category_id"]
        else None
    )
    return {
        "title": row["title"],
        "description": row["description"],
        "location": row["location"],
        "all_day": bool(row["all_day"]),
        "start": start,
        "end": end,
        "time_zone": row["time_zone"],
        "rrule": row["rrule"],
        "status": row["status"],
        "color": row["color"],
        "display_color": row["color"] or (category["color"] if category else calendar["color"]),
        "category_id": row["category_id"],
        "category_name": category["name"] if category else None,
        "calendar_id": row["calendar_id"],
        "calendar_name": calendar["name"],
    }


def _insert(conn, kind, row, occurrence, start, end, batch, cause):
    entry_id, stamp = uuid7(), iso_now()
    snapshot = _snapshot(conn, row, start, end)
    entry = {
        "id": entry_id,
        "kind": kind,
        "event_id": row["id"],
        "occurrence": occurrence,
        "batch": batch or entry_id,
    }
    words = (snapshot["title"], snapshot["location"], snapshot["description"])
    conn.execute(
        "INSERT INTO trash(id,kind,event_id,occurrence,deleted_at,batch,cause,snapshot,search) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (
            entry_id,
            kind,
            row["id"],
            occurrence,
            stamp,
            entry["batch"],
            cause,
            json.dumps(snapshot),
            fold(" ".join((*words, snapshot["calendar_name"]))),
        ),
    )
    _audit(conn, "trash", entry, stamp)
    return entry_id


def move_event(conn, row, batch=None, cause="user"):
    """Move a whole event or series to Trash. Its edges leave the Nexus index; the links stay."""
    kind = "series" if row["rrule"] else "event"
    entry = _insert(conn, kind, row, "", row["start"], row["end"], batch, cause)
    conn.execute(
        "UPDATE events SET trashed_at=?,revision=revision+1 WHERE id=?", (iso_now(), row["id"])
    )
    unpublish_links(conn, row["id"])
    return entry


def move_occurrence(conn, row, key):
    """Move one occurrence of a series to Trash. The series itself is not touched otherwise."""
    existing = conn.execute(
        "SELECT id FROM trash WHERE event_id=? AND occurrence=?", (row["id"], key)
    ).fetchone()
    if existing:
        return existing["id"]
    span = occurrence_at(row, key)
    if span is None:
        raise TrashError(422, "This occurrence is not part of the event")
    skipped = set(json.loads(row["exdates"]))
    if key in skipped:
        return None  # skipped before Trash existed: already gone, and there is nothing to recover
    entry = _insert(conn, "occurrence", row, key, span[0], span[1], None, "user")
    conn.execute(
        "UPDATE events SET exdates=?,updated_at=?,revision=revision+1 WHERE id=?",
        (json.dumps(sorted(skipped | {key})), iso_now(), row["id"]),
    )
    return entry


def _event(conn, entry):
    return conn.execute("SELECT * FROM events WHERE id=?", (entry["event_id"],)).fetchone()


def _blocked(conn, entry, event):
    """Why this entry cannot simply be restored right now, or None."""
    if entry["kind"] != "occurrence":
        return None
    if event["trashed_at"]:
        return "series_in_trash"
    if occurrence_at(event, entry["occurrence"]) is None:
        return "occurrence_gone"
    return None


def get(conn, entry_id):
    row = conn.execute("SELECT * FROM trash WHERE id=?", (entry_id,)).fetchone()
    if not row:
        raise TrashError(404, NOT_IN_TRASH)
    return row


def entry_json(conn, entry):
    snapshot = json.loads(entry["snapshot"])
    event = _event(conn, entry)
    calendar = conn.execute(
        "SELECT id,name,color,trashed_at FROM calendars WHERE id=?", (event["calendar_id"],)
    ).fetchone()
    return {
        "id": entry["id"],
        "kind": entry["kind"],
        "event_id": entry["event_id"],
        "occurrence": entry["occurrence"],
        "deleted_at": entry["deleted_at"],
        "batch": entry["batch"],
        "cause": entry["cause"],
        "title": snapshot["title"],
        "location": snapshot["location"],
        "all_day": snapshot["all_day"],
        "start": snapshot["start"],
        "end": snapshot["end"],
        "time_zone": snapshot["time_zone"],
        "rrule": snapshot["rrule"],
        "status": snapshot["status"],
        "color": snapshot["display_color"],
        "calendar": {
            "id": calendar["id"],
            "name": calendar["name"],
            "deleted": bool(calendar["trashed_at"]),
        },
        "blocked": _blocked(conn, entry, event),
    }


def detail(conn, entry):
    snapshot = json.loads(entry["snapshot"])
    event = _event(conn, entry)
    value = entry_json(conn, entry)
    value.update(
        description=snapshot["description"],
        category_name=snapshot["category_name"],
        created_at=event["created_at"],
        updated_at=event["updated_at"],
        links=[
            {"relation": link["relation"], "label": link["label"], "target": link["target"]}
            for link in conn.execute(
                "SELECT relation,label,target FROM links WHERE event_id=?", (event["id"],)
            )
        ]
        if entry["kind"] != "occurrence"
        else [],
        batch_size=conn.execute(
            "SELECT count(*) FROM trash WHERE batch=?", (entry["batch"],)
        ).fetchone()[0],
        occurrences_in_trash=conn.execute(
            "SELECT count(*) FROM trash WHERE event_id=? AND occurrence!=''", (event["id"],)
        ).fetchone()[0]
        if entry["kind"] == "series"
        else 0,
    )
    return value


def generation(conn):
    """Changes with every move in or out of Trash: the audit log only ever grows."""
    return conn.execute("SELECT coalesce(max(seq),0) FROM trash_audit").fetchone()[0]


def listing(conn, query, cursor, limit):
    """Newest first. Entry ids are time-ordered, so the id alone is a stable position."""
    clauses, params = [], []
    for token in fold(query).split()[:8]:
        escaped = token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        clauses.append("search LIKE ? ESCAPE '\\'")
        params.append(f"%{escaped}%")
    matching = " AND ".join(clauses) or "1"
    matched = conn.execute(f"SELECT count(*) FROM trash WHERE {matching}", params).fetchone()[0]
    position = "AND id<?" if cursor else ""
    rows = conn.execute(
        f"SELECT * FROM trash WHERE {matching} {position} ORDER BY id DESC LIMIT ?",
        (*params, *([cursor] if cursor else []), limit + 1),
    ).fetchall()
    page = rows[:limit]
    return {
        "items": [entry_json(conn, row) for row in page],
        "matched": matched,
        "total": conn.execute("SELECT count(*) FROM trash").fetchone()[0],
        "generation": generation(conn),
        "next_cursor": page[-1]["id"] if len(rows) > limit else None,
    }


def lookup(conn, event_id, occurrence):
    """The Trash entry behind a link to an event or occurrence that is gone, or None."""
    row = conn.execute(
        "SELECT * FROM trash WHERE event_id=? AND occurrence=?", (event_id, occurrence)
    ).fetchone()
    if row or not occurrence:
        return row
    # A link to one occurrence of a series that is itself in Trash.
    return conn.execute(
        "SELECT * FROM trash WHERE event_id=? AND occurrence=''", (event_id,)
    ).fetchone()


def _restored(entry, snapshot, **extra):
    return {
        "restored": entry["kind"],
        "event_id": entry["event_id"],
        "occurrence": entry["occurrence"],
        "start": snapshot["start"],
        "all_day": snapshot["all_day"],
        "calendar_restored": False,
        **extra,
    }


def _forget_key(conn, event, key):
    """Take one key out of the exclusions. The others stay exactly as they are now."""
    skipped = json.loads(event["exdates"])
    if key in skipped:
        conn.execute(
            "UPDATE events SET exdates=?,updated_at=?,revision=revision+1 WHERE id=?",
            (json.dumps([k for k in skipped if k != key]), iso_now(), event["id"]),
        )


def _restore_as_separate(conn, entry, event, snapshot):
    """A one-off event from what was deleted, for an occurrence its series no longer has.

    The entry's own id becomes the event's id, so this can happen only once."""
    category = snapshot["category_id"]
    if category and not conn.execute("SELECT 1 FROM categories WHERE id=?", (category,)).fetchone():
        category = None
    values = {
        "id": entry["id"],
        "calendar_id": event["calendar_id"],
        "origin": "native",
        "title": snapshot["title"],
        "description": snapshot["description"],
        "location": snapshot["location"],
        "all_day": int(snapshot["all_day"]),
        "start": snapshot["start"],
        "end": snapshot["end"],
        "time_zone": snapshot["time_zone"],
        "rrule": None,
        "exdates": "[]",
        "status": snapshot["status"],
        "category_id": category,
        "color": snapshot["color"],
    }
    values["range_start"], values["range_end"] = index_bounds(values)
    stamp = iso_now()
    columns = [*values, "created_at", "updated_at"]
    conn.execute(
        f"INSERT INTO events({','.join(columns)}) VALUES({','.join('?' * len(columns))})",
        (*values.values(), stamp, stamp),
    )


def _restore_occurrence(conn, entry, event, snapshot, separate):
    blocked = _blocked(conn, entry, event)
    if blocked == "series_in_trash":
        raise TrashError(409, "Restore the series first. This occurrence belongs to it.")
    if blocked == "occurrence_gone" and not separate:
        raise TrashError(
            409,
            "The series was rescheduled, so this occurrence is no longer part of it. "
            "You can restore it as a separate event.",
        )
    if blocked == "occurrence_gone":
        _restore_as_separate(conn, entry, event, snapshot)
        _forget_key(conn, event, entry["occurrence"])
        return _restored(entry, snapshot, event_id=entry["id"], occurrence="", separate=True)
    _forget_key(conn, event, entry["occurrence"])
    return _restored(entry, snapshot, separate=False)


def restore(conn, entry, separate=False):
    event = _event(conn, entry)
    snapshot = json.loads(entry["snapshot"])
    stamp = iso_now()
    if entry["kind"] == "occurrence":
        result = _restore_occurrence(conn, entry, event, snapshot, separate)
    else:
        conn.execute(
            "UPDATE events SET trashed_at=NULL,revision=revision+1 WHERE id=?", (event["id"],)
        )
        came_back = conn.execute(
            "UPDATE calendars SET trashed_at=NULL,revision=revision+1 "
            "WHERE id=? AND trashed_at IS NOT NULL",
            (event["calendar_id"],),
        ).rowcount
        publish_links(conn, event["id"])
        result = _restored(entry, snapshot, calendar_restored=bool(came_back))
    conn.execute("DELETE FROM trash WHERE id=?", (entry["id"],))
    _audit(conn, "restore", entry, stamp)
    return result


def restore_batch(conn, batch):
    """Everything deleted together, such as the events of a deleted calendar."""
    entries = conn.execute(
        "SELECT * FROM trash WHERE batch=? AND occurrence=''", (batch,)
    ).fetchall()
    if not entries:
        raise TrashError(404, NOT_IN_TRASH)
    results = [restore(conn, entry) for entry in entries]
    return {
        "restored": len(results),
        "calendar_restored": any(r["calendar_restored"] for r in results),
    }


def _drop_empty_calendars(conn):
    """A deleted calendar goes for good once nothing recoverable is left in it."""
    for row in conn.execute(
        "SELECT id FROM calendars WHERE trashed_at IS NOT NULL AND NOT EXISTS "
        "(SELECT 1 FROM events e WHERE e.calendar_id=calendars.id)"
    ).fetchall():
        conn.execute("DELETE FROM calendars WHERE id=?", (row["id"],))
        conn.execute(
            "INSERT OR REPLACE INTO tombstones(id,kind,deleted_at) VALUES(?,?,?)",
            (row["id"], "calendar", iso_now()),
        )


def _purge_one(conn, entry, stamp):
    _audit(conn, "purge", entry, stamp)
    if entry["kind"] == "occurrence":
        # The key stays in exdates: deleted for good means it does not come back.
        conn.execute("DELETE FROM trash WHERE id=?", (entry["id"],))
    else:
        delete_event(conn, entry["event_id"])  # its occurrence entries go with it


def purge(conn, entry):
    stamp = iso_now()
    for occurrence in conn.execute(
        "SELECT * FROM trash WHERE event_id=? AND occurrence!='' AND ?!='occurrence'",
        (entry["event_id"], entry["kind"]),
    ).fetchall():
        _audit(conn, "purge", occurrence, stamp)
    _purge_one(conn, entry, stamp)
    _drop_empty_calendars(conn)
    return {"purged": entry["kind"]}


def empty(conn, expected_generation):
    """Delete everything in Trash for good, if it is still exactly what the owner was shown."""
    if generation(conn) != expected_generation:
        raise TrashError(409, "Trash has changed. Review it and try again.")
    entries = conn.execute("SELECT * FROM trash ORDER BY occurrence='' ").fetchall()
    stamp = iso_now()
    for entry in entries:
        _purge_one(conn, entry, stamp)
    _drop_empty_calendars(conn)
    return {"purged": len(entries)}
