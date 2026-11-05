"""Event storage, occurrence expansion and serialization shared by routes and workers."""

import json
from collections import defaultdict
from datetime import date, timedelta

from chronos.recurrence import expand, series_end
from chronos.util import day_bounds, instant, iso_now, parse_instant, uuid7

EVENT_COLUMNS = (
    "title",
    "description",
    "location",
    "all_day",
    "start",
    "end",
    "time_zone",
    "rrule",
    "exdates",
    "recurrence_id",
    "status",
    "sequence",
    "content_hash",
)


def index_bounds(values: dict) -> tuple[str, str | None]:
    if values["all_day"]:
        start, _ = day_bounds(values["start"], values["end"])
    else:
        start = values["start"]
    try:
        end = series_end(values)
    except (ValueError, OverflowError):
        end = None
    return start, end


def queue(conn, method, path, body=None, link_id=None):
    conn.execute(
        "INSERT INTO outbox(method,path,body,link_id) VALUES(?,?,?,?)",
        (method, path, json.dumps(body) if body is not None else None, link_id),
    )


def delete_event(conn, event_id):
    """Delete an event, unpublish its Nexus edges and keep a tombstone for resolution."""
    for link in conn.execute("SELECT remote_id FROM links WHERE event_id=?", (event_id,)):
        if link["remote_id"]:
            queue(conn, "DELETE", f"/references/{link['remote_id']}")
    conn.execute("DELETE FROM events WHERE id=?", (event_id,))
    conn.execute(
        "INSERT OR REPLACE INTO tombstones(id,kind,deleted_at) VALUES(?,?,?)",
        (event_id, "event", iso_now()),
    )


def apply_records(conn, calendar_id, origin, records, delete_missing):
    """Make a calendar's external events match parsed records, keyed by (UID, RECURRENCE-ID).

    Unchanged content is skipped, so repeated imports and refreshes never duplicate;
    existing Chronos UUIDs are kept on update. Missing events are deleted only when the
    caller states the source is complete (subscriptions), never for one-time imports."""
    existing = {
        (row["source_uid"], row["recurrence_id"]): row
        for row in conn.execute(
            "SELECT id,source_uid,recurrence_id,content_hash,sequence FROM events "
            "WHERE calendar_id=?",
            (calendar_id,),
        )
    }
    counts = {"created": 0, "updated": 0, "unchanged": 0, "removed": 0}
    stamp = iso_now()
    for record in records:
        key = (record["uid"], record["recurrence_id"])
        values = {column: record[column] for column in EVENT_COLUMNS if column in record}
        values["all_day"] = int(record["all_day"])
        values["exdates"] = json.dumps(record["exdates"])
        values["range_start"], values["range_end"] = index_bounds({**values, **record})
        old = existing.pop(key, None)
        if old:
            if old["content_hash"] == record["content_hash"] or (
                not delete_missing and old["sequence"] > record["sequence"]
            ):
                counts["unchanged"] += 1
                continue
            assignments = ",".join(f"{column}=?" for column in values)
            conn.execute(
                f"UPDATE events SET {assignments},updated_at=? WHERE id=?",
                (*values.values(), stamp, old["id"]),
            )
            counts["updated"] += 1
        else:
            columns = [
                "id",
                "calendar_id",
                "origin",
                "source_uid",
                *values,
                "created_at",
                "updated_at",
            ]
            conn.execute(
                f"INSERT INTO events({','.join(columns)}) VALUES({','.join('?' * len(columns))})",
                (uuid7(), calendar_id, origin, record["uid"], *values.values(), stamp, stamp),
            )
            counts["created"] += 1
    if delete_missing:
        for old in existing.values():
            delete_event(conn, old["id"])
            counts["removed"] += 1
    return counts


def effective_color(row, categories):
    if row["color"]:
        return row["color"]
    category = categories.get(row["category_id"])
    return category["color"] if category else row["calendar_color"]


def occurrences(conn, window_start, window_end, settings, query=None):
    """Every visible occurrence and projected entry overlapping the UTC window."""
    categories = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM categories")}
    overrides = defaultdict(set)
    for row in conn.execute(
        "SELECT calendar_id,source_uid,recurrence_id FROM events WHERE recurrence_id!=''"
    ):
        overrides[(row["calendar_id"], row["source_uid"])].add(row["recurrence_id"])
    rows = conn.execute(
        "SELECT e.*,c.color AS calendar_color,c.name AS calendar_name,c.kind AS calendar_kind "
        "FROM events e JOIN calendars c ON c.id=e.calendar_id "
        "WHERE c.visible=1 AND e.range_start<? AND (e.range_end IS NULL OR e.range_end>?)",
        (instant(window_end), instant(window_start)),
    ).fetchall()
    result = []
    for row in rows:
        if row["recurrence_id"] and row["status"] == "cancelled":
            continue
        skip = (
            ()
            if row["recurrence_id"]
            else overrides.get((row["calendar_id"], row["source_uid"]), ())
        )
        try:
            found = list(expand(row, window_start, window_end, skip))
        except (ValueError, OverflowError, KeyError):
            continue
        for key, start, end in found:
            result.append(
                {
                    "key": f"{row['id']}/{key}",
                    "event_id": row["id"],
                    "occurrence": key,
                    "calendar_id": row["calendar_id"],
                    "calendar_name": row["calendar_name"],
                    "origin": row["origin"],
                    "title": row["title"],
                    "location": row["location"],
                    "all_day": bool(row["all_day"]),
                    "start": start if row["all_day"] else instant(start),
                    "end": end if row["all_day"] else instant(end),
                    "time_zone": row["time_zone"],
                    "status": row["status"],
                    "color": effective_color(row, categories),
                    "category_id": row["category_id"],
                    "recurring": bool(row["rrule"]) or bool(row["recurrence_id"]),
                    "readonly": row["origin"] != "native",
                }
            )
    for row in conn.execute(
        "SELECT p.*,s.color AS source_color,s.show_completed FROM projected p "
        "JOIN sources s ON s.provider=p.provider "
        "WHERE s.enabled=1 AND p.range_start<? AND p.range_end>?",
        (instant(window_end), instant(window_start)),
    ):
        if row["status"] == "completed" and not row["show_completed"]:
            continue
        result.append(projected_json(row))
    if query:
        needle = query.casefold()
        result = [
            o
            for o in result
            if needle in o["title"].casefold() or needle in (o.get("location") or "").casefold()
        ]
    return result


def projected_json(row):
    return {
        "key": f"{row['provider']}:{row['item_id']}",
        "provider": row["provider"],
        "item_id": row["item_id"],
        "resource": row["resource"],
        "kind": row["kind"],
        "origin": "projection",
        "title": row["title"],
        "summary": row["summary"],
        "context": row["context"],
        "group_label": row["group_label"],
        "all_day": bool(row["all_day"]),
        "start": row["start"],
        "end": row["end"],
        "time_zone": row["time_zone"],
        "certainty": row["certainty"],
        "status": row["status"],
        "color": row["source_color"],
        "recurring": False,
        "readonly": True,
        "fetched_at": row["fetched_at"],
    }


def normalize_item(provider: str, item: dict, fetched_at: str):
    """Validate one dated-items v1 item; returns a stored row or None if it is unusable."""
    from chronos.util import REF

    try:
        item_id, resource, kind, title = item["id"], item["resource"], item["kind"], item["title"]
        if not all(isinstance(v, str) for v in (item_id, resource, kind, title)):
            return None
        match = REF.fullmatch(resource)
        if not (0 < len(item_id) <= 160 and match and match[1] == provider):
            return None
        if not kind.startswith(provider + ".") or len(kind) > 80 or not title.strip():
            return None
        all_day = item["all_day"]
        if not isinstance(all_day, bool):
            return None
        if all_day:
            start = date.fromisoformat(item["start"])
            end = date.fromisoformat(item["end"]) if item.get("end") else start + timedelta(days=1)
            if end <= start or (end - start).days > 366:
                return None
            start_text, end_text = start.isoformat(), end.isoformat()
            low, high = day_bounds(start_text, end_text)
        else:
            if len(item["start"]) <= 10:
                return None
            start = parse_instant(item["start"])
            end = parse_instant(item["end"]) if item.get("end") else start
            if end < start:
                return None
            start_text, end_text = instant(start), instant(end)
            low, high = start_text, instant(end + timedelta(seconds=1))
        certainty = item.get("certainty")
        status = item.get("status")
        if certainty not in {"confirmed", "tentative", "estimated"}:
            return None
        if status not in {"scheduled", "postponed", "cancelled", "open", "completed"}:
            return None
        group = item.get("group") if isinstance(item.get("group"), dict) else {}
        return {
            "provider": provider,
            "item_id": item_id,
            "resource": resource,
            "kind": kind,
            "title": title.strip()[:200],
            "start": start_text,
            "end": end_text,
            "all_day": int(all_day),
            "time_zone": item.get("time_zone") if isinstance(item.get("time_zone"), str) else None,
            "certainty": certainty,
            "status": status,
            "summary": str(item.get("summary") or "")[:300],
            "context": str(item.get("context") or "")[:80],
            "group_resource": str(group.get("resource") or "")[:240] or None,
            "group_label": str(group.get("label") or "")[:200] or None,
            "updated_at": str(item.get("updated_at") or "")[:40] or None,
            "fetched_at": fetched_at,
            "range_start": low,
            "range_end": high,
        }
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
