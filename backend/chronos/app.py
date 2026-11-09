import base64
import json
import os
import re
import secrets
import sqlite3
import threading
import time
import unicodedata
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, available_timezones

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from chronos import VERSION, ical, net
from chronos.db import MIGRATIONS, Database
from chronos.recurrence import validate_native_rule
from chronos.store import (
    apply_records,
    delete_event,
    index_bounds,
    occurrences,
    projected_json,
    queue,
)
from chronos.sync import PROVIDERS, Nexus, Worker
from chronos.util import COLOR, REF, instant, iso_now, now, parse_instant, reference, uuid7

ROOT = Path(__file__).resolve().parents[2]
BACKUP_FORMAT = "chronos-sqlite"
BACKUP_FORMAT_VERSION = 1
BACKUP_HEADER = "X-Empyrean-Backup-"
MAX_ARTIFACT = 256 * 1024 * 1024
MAX_WINDOW_DAYS = 120
DEFAULT_SETTINGS = {
    "time_zone": "UTC",
    "time_zone_set": False,
    "week_start": 1,
    "time_format": "auto",
}
REFRESH_CHOICES = {15, 60, 180, 360, 720, 1440}
ZONES = sorted(
    z for z in available_timezones() if "/" in z and not z.startswith(("Etc/", "SystemV/"))
)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Settings(Strict):
    time_zone: str | None = None
    week_start: int | None = Field(default=None, ge=0, le=6)
    time_format: str | None = Field(default=None, pattern=r"^(auto|12|24)$")


class CalendarBody(Strict):
    name: str = Field(min_length=1, max_length=100)
    color: str = Field(pattern=COLOR)
    visible: bool = True


class CalendarPatch(Strict):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    color: str | None = Field(default=None, pattern=COLOR)
    visible: bool | None = None


class CategoryBody(Strict):
    name: str = Field(min_length=1, max_length=60)
    color: str = Field(pattern=COLOR)


class EventBody(Strict):
    calendar_id: str
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=20000)
    location: str = Field(default="", max_length=500)
    all_day: bool = False
    # All-day: ISO dates, end exclusive. Timed: local wall time "YYYY-MM-DDTHH:MM" in time_zone.
    start: str = Field(max_length=25)
    end: str = Field(max_length=25)
    time_zone: str | None = None
    rrule: str | None = Field(default=None, max_length=300)
    status: str = Field(default="confirmed", pattern=r"^(confirmed|tentative|cancelled)$")
    category_id: str | None = None
    color: str = Field(default="", pattern=r"^(#[0-9a-fA-F]{6})?$")


class ImportBody(Strict):
    content: str = Field(min_length=1, max_length=2_000_000)
    filename: str = Field(default="calendar.ics", max_length=200)
    calendar_id: str | None = None
    name: str | None = Field(default=None, max_length=100)
    color: str | None = Field(default=None, pattern=COLOR)


class SubscriptionBody(Strict):
    name: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=8, max_length=2048)
    color: str = Field(pattern=COLOR)
    refresh_minutes: int = 360


class SubscriptionPatch(Strict):
    url: str | None = Field(default=None, min_length=8, max_length=2048)
    enabled: bool | None = None
    refresh_minutes: int | None = None


class SourcePatch(Strict):
    enabled: bool | None = None
    color: str | None = Field(default=None, pattern=COLOR)
    show_completed: bool | None = None


class PersonBody(Strict):
    """A Meridian Person chosen in the people picker (people-directory projection)."""

    resource: str = Field(max_length=240)
    label: str = Field(default="", max_length=200)


class PlanBody(Strict):
    provider: str = Field(pattern=r"^[a-z][a-z0-9-]{0,47}$")
    item_id: str = Field(min_length=1, max_length=160)
    calendar_id: str


class CopyBody(Strict):
    calendar_id: str


def styles():
    """Shared tokens, the shared foundation, the bundled Roboto face (inline: the sandbox
    has no network), then Chronos's own styles."""
    font = base64.b64encode((ROOT / "frontend/fonts/Roboto.woff2").read_bytes()).decode()
    face = (
        '@font-face{font-family:"Roboto";src:url(data:font/woff2;base64,'
        + font
        + ') format("woff2");font-weight:100 900;font-stretch:75% 100%;font-display:swap}'
    )
    return "\n".join(
        [
            (ROOT / "frontend/aureate-tokens.css").read_text(encoding="utf-8"),
            (ROOT / "frontend/aureate-foundation.css").read_text(encoding="utf-8"),
            face,
            (ROOT / "frontend/style.css").read_text(encoding="utf-8"),
        ]
    )


def create_app(
    data_dir=None, nexus=None, feed_transport=None, resolver=None, clock=None, workers=True
):
    clock = clock or now
    db = Database(Path(data_dir or os.getenv("CHRONOS_DATA", "/data")) / "chronos.sqlite3")
    nexus = nexus or Nexus()
    stop = threading.Event()
    style = styles()

    def settings():
        with db.connect() as conn:
            stored = {
                r["key"]: json.loads(r["value"]) for r in conn.execute("SELECT * FROM settings")
            }
        return {**DEFAULT_SETTINGS, **stored}

    worker = Worker(db, nexus, settings, clock, feed_transport, resolver)

    with db.connect() as conn:
        worker.ensure_sources(conn)
        if not conn.execute("SELECT 1 FROM calendars WHERE kind='native'").fetchone():
            stamp = iso_now()
            conn.execute(
                "INSERT INTO calendars(id,kind,name,color,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?)",
                (uuid7(), "native", "Personal", "#7AA7EB", stamp, stamp),
            )
        # A sync interrupted by a restart is not running any more.
        conn.execute("UPDATE subscriptions SET running=0")

    def loop():
        while not stop.wait(2):
            try:
                worker.tick()
            except Exception as exc:
                print(f"Background work failed: {type(exc).__name__}", flush=True)

    @asynccontextmanager
    async def lifespan(app):
        thread = threading.Thread(target=loop, daemon=True) if workers else None
        if thread:
            thread.start()
        yield
        stop.set()
        if thread:
            thread.join(timeout=5)

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.db = db
    app.state.worker = worker

    @app.middleware("http")
    async def trusted_gateway(request: Request, call_next):
        if request.url.path.startswith("/api/"):
            key = os.getenv("NEXUS_RESOLVER_KEY", "")
            if not key or not secrets.compare_digest(
                request.headers.get("x-nexus-gateway-key", ""), key
            ):
                return JSONResponse({"detail": "Nexus gateway required"}, status_code=403)
        return await call_next(request)

    # ── Helpers ──────────────────────────────────────────────────────

    def calendar(conn, cid, kinds=None):
        row = conn.execute("SELECT * FROM calendars WHERE id=?", (cid,)).fetchone()
        if not row:
            raise HTTPException(404, "Calendar not found")
        if kinds and row["kind"] not in kinds:
            raise HTTPException(409, "This calendar cannot be changed here")
        return row

    def event_row(conn, eid):
        row = conn.execute("SELECT * FROM events WHERE id=?", (eid,)).fetchone()
        if not row:
            raise HTTPException(404, "Event not found")
        return row

    def calendar_json(conn, row):
        value = dict(row)
        value["visible"] = bool(value["visible"])
        value["event_count"] = conn.execute(
            "SELECT count(*) FROM events WHERE calendar_id=?", (row["id"],)
        ).fetchone()[0]
        if row["kind"] == "subscription":
            sub = conn.execute(
                "SELECT * FROM subscriptions WHERE calendar_id=?", (row["id"],)
            ).fetchone()
            value["subscription"] = {
                "url_display": net.display(sub["url"]),
                "enabled": bool(sub["enabled"]),
                "refresh_minutes": sub["refresh_minutes"],
                "last_attempt_at": sub["last_attempt_at"],
                "last_success_at": sub["last_success_at"],
                "last_error": sub["last_error"],
                "last_warning": sub["last_warning"],
                "running": bool(sub["running"]) or (sub["enabled"] and sub["next_attempt"] == 0),
            }
        if row["kind"] == "import":
            last = conn.execute(
                "SELECT * FROM imports WHERE calendar_id=? ORDER BY imported_at DESC LIMIT 1",
                (row["id"],),
            ).fetchone()
            value["last_import"] = dict(last) if last else None
        return value

    def sources_json(conn):
        return [
            {
                **dict(r),
                "enabled": bool(r["enabled"]),
                "show_completed": bool(r["show_completed"]),
            }
            for r in conn.execute("SELECT * FROM sources ORDER BY provider")
        ]

    def local_to_utc(text, zone_name):
        try:
            local = datetime.fromisoformat(text)
            zone = ZoneInfo(zone_name)
        except (ValueError, KeyError) as exc:
            raise HTTPException(422, "Invalid date, time or time zone") from exc
        if local.tzinfo is not None:
            raise HTTPException(422, "Send local wall time without an offset")
        return local.replace(tzinfo=zone)

    def event_values(conn, body: EventBody):
        calendar(conn, body.calendar_id, {"native"})
        if (
            body.category_id
            and not conn.execute(
                "SELECT 1 FROM categories WHERE id=?", (body.category_id,)
            ).fetchone()
        ):
            raise HTTPException(422, "Unknown category")
        values = {
            "calendar_id": body.calendar_id,
            "title": body.title.strip(),
            "description": body.description,
            "location": body.location.strip(),
            "all_day": int(body.all_day),
            "status": body.status,
            "category_id": body.category_id,
            "color": body.color,
            "rrule": None,
            "exdates": "[]",
        }
        if body.all_day:
            try:
                start, end = date.fromisoformat(body.start[:10]), date.fromisoformat(body.end[:10])
            except ValueError as exc:
                raise HTTPException(422, "Invalid date") from exc
            if end <= start:
                raise HTTPException(422, "The end must be after the start")
            values.update(start=start.isoformat(), end=end.isoformat(), time_zone=None)
        else:
            zone = body.time_zone or settings()["time_zone"]
            start, end = local_to_utc(body.start, zone), local_to_utc(body.end, zone)
            if end < start:
                raise HTTPException(422, "The end must not be before the start")
            values.update(start=instant(start), end=instant(end), time_zone=zone)
        if body.rrule:
            try:
                values["rrule"] = validate_native_rule(body.rrule)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
        values["range_start"], values["range_end"] = index_bounds(values)
        return values

    def event_json(conn, row):
        value = dict(row)
        value["all_day"] = bool(value["all_day"])
        value["exdates"] = json.loads(value["exdates"])
        value["readonly"] = row["origin"] != "native"
        value["reference"] = reference("event", row["id"])
        if not row["all_day"]:
            zone = ZoneInfo(row["time_zone"] or "UTC")
            value["start_local"] = (
                parse_instant(row["start"]).astimezone(zone).strftime("%Y-%m-%dT%H:%M")
            )
            value["end_local"] = (
                parse_instant(row["end"]).astimezone(zone).strftime("%Y-%m-%dT%H:%M")
            )
        cal = conn.execute("SELECT * FROM calendars WHERE id=?", (row["calendar_id"],)).fetchone()
        value["calendar"] = {
            "id": cal["id"],
            "name": cal["name"],
            "kind": cal["kind"],
            "color": cal["color"],
        }
        value["links"] = [
            {
                "id": link["id"],
                "target": link["target"],
                "relation": link["relation"],
                "label": link["label"],
            }
            for link in conn.execute("SELECT * FROM links WHERE event_id=?", (row["id"],))
        ]
        if row["origin"] == "subscription":
            sub = conn.execute(
                "SELECT last_success_at FROM subscriptions WHERE calendar_id=?", (cal["id"],)
            ).fetchone()
            value["provenance"] = {
                "kind": "subscription",
                "name": cal["name"],
                "synced_at": sub["last_success_at"] if sub else None,
            }
        elif row["origin"] == "import":
            last = conn.execute(
                "SELECT filename,imported_at FROM imports WHERE calendar_id=? ORDER BY imported_at DESC LIMIT 1",
                (cal["id"],),
            ).fetchone()
            value["provenance"] = {
                "kind": "import",
                "name": cal["name"],
                "filename": last["filename"] if last else None,
                "imported_at": last["imported_at"] if last else None,
            }
        else:
            value["provenance"] = {"kind": "native", "name": cal["name"]}
        return value

    def window(start, end):
        try:
            a, b = parse_instant(start), parse_instant(end)
        except ValueError as exc:
            raise HTTPException(422, "Invalid range") from exc
        if b <= a or b - a > timedelta(days=MAX_WINDOW_DAYS):
            raise HTTPException(422, f"Ranges are limited to {MAX_WINDOW_DAYS} days")
        return a, b

    # ── Application API ──────────────────────────────────────────────

    @app.get("/health")
    def health():
        with db.connect() as conn:
            conn.execute("SELECT 1")
        return {"status": "ok", "version": VERSION}

    @app.get("/api/state")
    def state():
        with db.connect() as conn:
            return {
                "version": VERSION,
                "settings": settings(),
                "calendars": [
                    calendar_json(conn, r)
                    for r in conn.execute(
                        "SELECT * FROM calendars ORDER BY kind!='native',position,created_at"
                    )
                ],
                "categories": [
                    dict(r) for r in conn.execute("SELECT * FROM categories ORDER BY name")
                ],
                "sources": sources_json(conn),
                "pending_sync": conn.execute("SELECT count(*) FROM outbox").fetchone()[0],
            }

    @app.get("/api/timezones")
    def timezones():
        return {"zones": ZONES}

    @app.put("/api/settings")
    def put_settings(body: Settings):
        changes = body.model_dump(exclude_none=True)
        if "time_zone" in changes:
            if changes["time_zone"] not in ZONES and changes["time_zone"] != "UTC":
                raise HTTPException(422, "Unknown time zone")
            changes["time_zone_set"] = True
        with db.connect() as conn:
            for key, value in changes.items():
                conn.execute(
                    "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, json.dumps(value)),
                )
        return settings()

    @app.post("/api/calendars", status_code=201)
    def create_calendar(body: CalendarBody):
        stamp = iso_now()
        cid = uuid7()
        with db.connect() as conn:
            conn.execute(
                "INSERT INTO calendars(id,kind,name,color,visible,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                (cid, "native", body.name.strip(), body.color, int(body.visible), stamp, stamp),
            )
            return calendar_json(conn, calendar(conn, cid))

    @app.put("/api/calendars/{cid}")
    def update_calendar(cid: str, body: CalendarPatch):
        changes = body.model_dump(exclude_none=True)
        with db.connect() as conn:
            calendar(conn, cid)
            if "visible" in changes:
                changes["visible"] = int(changes["visible"])
            for key, value in changes.items():
                conn.execute(
                    f"UPDATE calendars SET {key}=?,updated_at=? WHERE id=?", (value, iso_now(), cid)
                )
            return calendar_json(conn, calendar(conn, cid))

    @app.delete("/api/calendars/{cid}")
    def delete_calendar(cid: str, confirmed: bool = False):
        if not confirmed:
            raise HTTPException(422, "Deleting a calendar requires confirmation")
        with db.connect() as conn:
            row = calendar(conn, cid)
            if (
                row["kind"] == "native"
                and conn.execute("SELECT count(*) FROM calendars WHERE kind='native'").fetchone()[0]
                == 1
            ):
                raise HTTPException(409, "Keep at least one of your own calendars")
            for event in conn.execute(
                "SELECT id FROM events WHERE calendar_id=?", (cid,)
            ).fetchall():
                delete_event(conn, event["id"])
            conn.execute("DELETE FROM calendars WHERE id=?", (cid,))
            conn.execute(
                "INSERT OR REPLACE INTO tombstones(id,kind,deleted_at) VALUES(?,?,?)",
                (cid, "calendar", iso_now()),
            )
        return {"deleted": True}

    @app.post("/api/categories", status_code=201)
    def create_category(body: CategoryBody):
        with db.connect() as conn:
            if conn.execute(
                "SELECT 1 FROM categories WHERE name=?", (body.name.strip(),)
            ).fetchone():
                raise HTTPException(409, "A category with this name exists")
            cid = uuid7()
            conn.execute(
                "INSERT INTO categories(id,name,color,created_at) VALUES(?,?,?,?)",
                (cid, body.name.strip(), body.color, iso_now()),
            )
            return dict(conn.execute("SELECT * FROM categories WHERE id=?", (cid,)).fetchone())

    @app.put("/api/categories/{cid}")
    def update_category(cid: str, body: CategoryBody):
        with db.connect() as conn:
            if not conn.execute("SELECT 1 FROM categories WHERE id=?", (cid,)).fetchone():
                raise HTTPException(404, "Category not found")
            try:
                conn.execute(
                    "UPDATE categories SET name=?,color=? WHERE id=?",
                    (body.name.strip(), body.color, cid),
                )
            except sqlite3.IntegrityError as exc:
                raise HTTPException(409, "A category with this name exists") from exc
            return dict(conn.execute("SELECT * FROM categories WHERE id=?", (cid,)).fetchone())

    @app.delete("/api/categories/{cid}")
    def delete_category(cid: str):
        with db.connect() as conn:
            conn.execute("DELETE FROM categories WHERE id=?", (cid,))
        return {"deleted": True}

    @app.get("/api/occurrences")
    def list_occurrences(start: str, end: str, q: str = ""):
        a, b = window(start, end)
        with db.connect() as conn:
            items = occurrences(conn, a, b, settings(), q.strip()[:100] or None)
        items.sort(
            key=lambda o: (o["start"][:10], not o["all_day"], o["start"], o["title"].casefold())
        )
        return {"occurrences": items}

    @app.get("/api/search")
    def search(q: str):
        needle = q.strip()[:100]
        if len(needle) < 2:
            return {"events": [], "projected": []}
        pattern = "%" + needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT e.*,c.name AS calendar_name,c.color AS calendar_color FROM events e "
                "JOIN calendars c ON c.id=e.calendar_id WHERE e.recurrence_id='' AND "
                "(e.title LIKE ? ESCAPE '\\' OR e.location LIKE ? ESCAPE '\\' OR e.description LIKE ? ESCAPE '\\') "
                "ORDER BY e.start DESC LIMIT 60",
                (pattern, pattern, pattern),
            ).fetchall()
            projected = conn.execute(
                "SELECT p.*,s.color AS source_color,s.show_completed FROM projected p JOIN sources s "
                "ON s.provider=p.provider WHERE s.enabled=1 AND p.title LIKE ? ESCAPE '\\' ORDER BY p.start LIMIT 30",
                (pattern,),
            ).fetchall()
        return {
            "events": [
                {
                    "id": r["id"],
                    "title": r["title"],
                    "location": r["location"],
                    "all_day": bool(r["all_day"]),
                    "start": r["start"],
                    "end": r["end"],
                    "time_zone": r["time_zone"],
                    "recurring": bool(r["rrule"]),
                    "origin": r["origin"],
                    "calendar_name": r["calendar_name"],
                    "color": r["color"] or r["calendar_color"],
                }
                for r in rows
            ],
            "projected": [projected_json(r) for r in projected],
        }

    @app.get("/api/events/{eid}")
    def read_event(eid: str):
        with db.connect() as conn:
            return event_json(conn, event_row(conn, eid))

    @app.post("/api/events", status_code=201)
    def create_event(body: EventBody):
        with db.connect() as conn:
            values = event_values(conn, body)
            eid, stamp = uuid7(), iso_now()
            columns = ["id", "origin", *values, "created_at", "updated_at"]
            conn.execute(
                f"INSERT INTO events({','.join(columns)}) VALUES({','.join('?' * len(columns))})",
                (eid, "native", *values.values(), stamp, stamp),
            )
            return event_json(conn, event_row(conn, eid))

    @app.put("/api/events/{eid}")
    def update_event(eid: str, body: EventBody):
        with db.connect() as conn:
            old = event_row(conn, eid)
            if old["origin"] != "native":
                raise HTTPException(
                    409, "Events from imported or subscribed calendars are read-only"
                )
            values = event_values(conn, body)
            if (
                values["rrule"]
                and values["rrule"] == old["rrule"]
                and values["start"] == old["start"]
            ):
                values["exdates"] = old["exdates"]  # skipped occurrences survive unrelated edits
            assignments = ",".join(f"{column}=?" for column in values)
            conn.execute(
                f"UPDATE events SET {assignments},updated_at=? WHERE id=?",
                (*values.values(), iso_now(), eid),
            )
            return event_json(conn, event_row(conn, eid))

    @app.delete("/api/events/{eid}")
    def remove_event(eid: str, occurrence: str = ""):
        with db.connect() as conn:
            row = event_row(conn, eid)
            if row["origin"] != "native":
                raise HTTPException(
                    409, "Events from imported or subscribed calendars are read-only"
                )
            if occurrence:
                if not row["rrule"]:
                    raise HTTPException(422, "Only repeating events have occurrences")
                skipped = sorted(set(json.loads(row["exdates"])) | {occurrence[:20]})
                conn.execute(
                    "UPDATE events SET exdates=?,updated_at=? WHERE id=?",
                    (json.dumps(skipped), iso_now(), eid),
                )
                return {"deleted": "occurrence"}
            delete_event(conn, eid)
        return {"deleted": "event"}

    @app.post("/api/events/{eid}/copy", status_code=201)
    def copy_event(eid: str, body: CopyBody):
        with db.connect() as conn:
            row = event_row(conn, eid)
            calendar(conn, body.calendar_id, {"native"})
            stamp, new = iso_now(), uuid7()
            conn.execute(
                "INSERT INTO events(id,calendar_id,origin,title,description,location,all_day,start,end,"
                "time_zone,rrule,exdates,recurrence_id,status,range_start,range_end,created_at,updated_at) "
                "VALUES(?,?,'native',?,?,?,?,?,?,?,?,?,'',?,?,?,?,?)",
                (
                    new,
                    body.calendar_id,
                    row["title"],
                    row["description"],
                    row["location"],
                    row["all_day"],
                    row["start"],
                    row["end"],
                    row["time_zone"],
                    row["rrule"] if not row["recurrence_id"] else None,
                    row["exdates"] if not row["recurrence_id"] else "[]",
                    row["status"],
                    row["range_start"],
                    row["range_end"],
                    stamp,
                    stamp,
                ),
            )
            return event_json(conn, event_row(conn, new))

    @app.delete("/api/events/{eid}/links/{lid}")
    def unlink(eid: str, lid: str):
        with db.connect() as conn:
            link = conn.execute(
                "SELECT * FROM links WHERE id=? AND event_id=?", (lid, eid)
            ).fetchone()
            if not link:
                raise HTTPException(404, "Link not found")
            if link["remote_id"]:
                queue(conn, "DELETE", f"/references/{link['remote_id']}")
            conn.execute("DELETE FROM links WHERE id=?", (lid,))
        return {"deleted": True}

    # ── People (Meridian) ────────────────────────────────────────────
    # A Person is linked to an event by reference (`chronos.involves`); Meridian stays the
    # owner of the Person, and is listed as a reader so it can show the event on the profile.

    @app.get("/api/people")
    def people(q: str = "", limit: int = 10):
        """Meridian's people-directory projection through Nexus: names only, for the picker."""
        try:
            page = nexus.request(
                "POST",
                "/projections/query",
                {
                    "module": "meridian",
                    "projection": "people-directory",
                    "query": {"q": q[:100], "limit": max(1, min(limit, 20))},
                    "cursor": None,
                },
            )
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            return {"availability": "not_granted" if status == 403 else "nexus_error", "items": []}
        except (httpx.HTTPError, KeyError, ValueError):
            return {"availability": "nexus_unreachable", "items": []}
        if page.get("availability") != "available":
            return {"availability": page.get("availability") or "unavailable", "items": []}
        items = []
        for item in page.get("items") or []:
            match = REF.fullmatch(str(item.get("resource", "")))
            if match and match[1] == "meridian" and match[2] == "person":
                items.append({"resource": item["resource"], "label": str(item.get("label") or "")[:200],
                              "self": bool(item.get("self"))})  # fmt: skip
        return {"availability": "available", "items": items}

    @app.get("/api/events/{eid}/linked-from")
    def linked_from(eid: str):
        """Backlinks standard (concepts/backlinks.md): items in other modules that link to this
        event and share it with Chronos, labelled by their owners. Never raises."""
        with db.connect() as conn:
            event_row(conn, eid)
        try:
            page = nexus.request("GET", f"/references?resource={reference('event', eid)}&direction=incoming&limit=100")
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            return {"availability": "not_granted" if status == 403 else "nexus_error", "items": []}
        except (httpx.HTTPError, KeyError, ValueError):
            return {"availability": "nexus_unreachable", "items": []}
        items = []
        for edge in page.get("references") or []:
            source = edge.get("source", "")
            match = REF.fullmatch(source)
            if not match or match[1] == "chronos":
                continue
            entry = {"source": source, "module": match[1], "type": match[2], "label": "", "availability": "unknown"}
            try:
                out = nexus.request("POST", "/resources/resolve", {"resource": source})
                entry["availability"] = out.get("availability") or "unknown"
                if entry["availability"] == "available":
                    entry["label"] = str(out.get("label") or "")[:200]
                    entry["open_path"] = (out.get("open") or {}).get("module_path")
            except Exception:
                entry["availability"] = "temporarily_unavailable"
            items.append(entry)
        return {"availability": "available", "items": items}

    @app.get("/api/places")
    def places(q: str = "", limit: int = 10):
        """Atlas's place-directory projection through Nexus: names only, for the picker."""
        try:
            page = nexus.request(
                "POST",
                "/projections/query",
                {"module": "atlas", "projection": "place-directory",
                 "query": {"q": q[:100], "limit": max(1, min(limit, 20))}, "cursor": None},
            )
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            return {"availability": "not_granted" if status == 403 else "nexus_error", "items": []}
        except (httpx.HTTPError, KeyError, ValueError):
            return {"availability": "nexus_unreachable", "items": []}
        if page.get("availability") != "available":
            return {"availability": page.get("availability") or "unavailable", "items": []}
        items = []
        for item in page.get("items") or []:
            match = REF.fullmatch(str(item.get("resource", "")))
            if match and match[1] == "atlas" and match[2] == "place":
                items.append({"resource": item["resource"], "label": str(item.get("label") or "")[:200]})
        return {"availability": "available", "items": items}

    @app.post("/api/events/{eid}/places", status_code=201)
    def add_place(eid: str, body: PersonBody):
        match = REF.fullmatch(body.resource)
        if not match or match[1] != "atlas" or match[2] != "place":
            raise HTTPException(422, "Choose a place from Atlas")
        with db.connect() as conn:
            row = event_row(conn, eid)
            if row["origin"] != "native":
                raise HTTPException(409, "This event is read-only here")
            if conn.execute(
                "SELECT 1 FROM links WHERE event_id=? AND target=? AND relation='chronos.at'",
                (eid, body.resource),
            ).fetchone():
                raise HTTPException(409, "This place is already linked")
            lid = uuid7()
            readers = ["atlas"]
            conn.execute(
                "INSERT INTO links(id,event_id,target,relation,readers,label) VALUES(?,?,?,?,?,?)",
                (lid, eid, body.resource, "chronos.at", json.dumps(readers), body.label),
            )
            queue(
                conn,
                "POST",
                "/references",
                {"source": reference("event", eid), "target": body.resource, "relation": "chronos.at",
                 "metadata": {}, "readers": readers},
                lid,
            )
            return event_json(conn, event_row(conn, eid))

    @app.post("/api/events/{eid}/people", status_code=201)
    def add_person(eid: str, body: PersonBody):
        match = REF.fullmatch(body.resource)
        if not match or match[1] != "meridian" or match[2] != "person":
            raise HTTPException(422, "Choose a person from Meridian")
        with db.connect() as conn:
            row = event_row(conn, eid)
            if row["origin"] != "native":
                raise HTTPException(409, "This event is read-only here")
            if conn.execute(
                "SELECT 1 FROM links WHERE event_id=? AND target=? AND relation='chronos.involves'",
                (eid, body.resource),
            ).fetchone():
                raise HTTPException(409, "This person is already linked")
            lid = uuid7()
            readers = ["meridian"]
            conn.execute(
                "INSERT INTO links(id,event_id,target,relation,readers,label) VALUES(?,?,?,?,?,?)",
                (lid, eid, body.resource, "chronos.involves", json.dumps(readers), body.label),
            )
            queue(
                conn,
                "POST",
                "/references",
                {
                    "source": reference("event", eid),
                    "target": body.resource,
                    "relation": "chronos.involves",
                    "metadata": {},
                    "readers": readers,
                },
                lid,
            )
            return event_json(conn, event_row(conn, eid))

    @app.get("/api/events/{eid}/links")
    def resolve_links(eid: str):
        """Live owner-provided labels and availability for this event's references."""
        with db.connect() as conn:
            event_row(conn, eid)
            links = conn.execute("SELECT * FROM links WHERE event_id=?", (eid,)).fetchall()
        results = []
        for link in links:
            entry = {
                "id": link["id"],
                "target": link["target"],
                "label": link["label"],
                "relation": link["relation"],
            }
            try:
                resolved = nexus.request("POST", "/resources/resolve", {"resource": link["target"]})
                entry["availability"] = resolved.get("availability")
                if resolved.get("availability") == "available":
                    entry["label"] = resolved.get("label") or link["label"]
            except Exception:
                entry["availability"] = "temporarily_unavailable"
            results.append(entry)
        return {"links": results}

    # ── iCalendar import ─────────────────────────────────────────────

    def parse_upload(body: ImportBody):
        try:
            return ical.parse_calendar(body.content, settings()["time_zone"])
        except ical.FeedError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/api/import/preview")
    def import_preview(body: ImportBody):
        parsed = parse_upload(body)
        with db.connect() as conn:
            existing = set()
            if body.calendar_id:
                calendar(conn, body.calendar_id, {"import"})
                existing = {
                    (r["source_uid"], r["recurrence_id"])
                    for r in conn.execute(
                        "SELECT source_uid,recurrence_id FROM events WHERE calendar_id=?",
                        (body.calendar_id,),
                    )
                }
            uids = {e["uid"] for e in parsed["events"]}
            elsewhere = {}
            for r in conn.execute(
                "SELECT DISTINCT e.source_uid,c.name FROM events e JOIN calendars c ON c.id=e.calendar_id "
                "WHERE e.source_uid IS NOT NULL AND c.id IS NOT ?",
                (body.calendar_id,),
            ):
                if r["source_uid"] in uids:
                    elsewhere[r["name"]] = elsewhere.get(r["name"], 0) + 1
        events = parsed["events"]
        return {
            "name": parsed["name"] or Path(body.filename).stem[:100] or "Imported calendar",
            "time_zone": parsed["time_zone"],
            "total": len(events),
            "recurring": sum(1 for e in events if e["rrule"]),
            "all_day": sum(1 for e in events if e["all_day"]),
            "overrides": sum(1 for e in events if e["recurrence_id"]),
            "zones": sorted({e["time_zone"] for e in events if e["time_zone"]}),
            "already_in_target": sum(
                1 for e in events if (e["uid"], e["recurrence_id"]) in existing
            ),
            "in_other_calendars": [{"name": k, "count": v} for k, v in sorted(elsewhere.items())],
            "duplicates_in_file": parsed["duplicates_in_file"],
            "errors": parsed["errors"][:50],
            "error_count": len(parsed["errors"]),
            "warnings": parsed["warnings"],
            "ignored": parsed["ignored"],
            "sample": [
                {
                    k: e[k]
                    for k in ("title", "start", "end", "all_day", "time_zone", "rrule", "location")
                }
                for e in sorted(events, key=lambda e: e["start"])[:12]
            ],
        }

    @app.post("/api/import", status_code=201)
    def import_commit(body: ImportBody):
        parsed = parse_upload(body)
        with db.connect() as conn:
            stamp = iso_now()
            if body.calendar_id:
                cid = calendar(conn, body.calendar_id, {"import"})["id"]
            else:
                cid = uuid7()
                conn.execute(
                    "INSERT INTO calendars(id,kind,name,color,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                    (
                        cid,
                        "import",
                        (
                            body.name
                            or parsed["name"]
                            or Path(body.filename).stem
                            or "Imported calendar"
                        )[:100],
                        body.color or "#8FC2A9",
                        stamp,
                        stamp,
                    ),
                )
            counts = apply_records(conn, cid, "import", parsed["events"], False)
            conn.execute(
                "INSERT INTO imports(id,calendar_id,filename,imported_at,created,updated,unchanged,skipped) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (
                    uuid7(),
                    cid,
                    body.filename[:200],
                    stamp,
                    counts["created"],
                    counts["updated"],
                    counts["unchanged"],
                    len(parsed["errors"]),
                ),
            )
            return {
                "calendar": calendar_json(conn, calendar(conn, cid)),
                **counts,
                "skipped": len(parsed["errors"]),
                "warnings": parsed["warnings"],
            }

    # ── Subscriptions ────────────────────────────────────────────────

    def checked_url(url):
        try:
            return net.normalize(url)
        except net.FetchError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/api/subscriptions", status_code=201)
    def subscribe(body: SubscriptionBody):
        if body.refresh_minutes not in REFRESH_CHOICES:
            raise HTTPException(422, "Unsupported refresh interval")
        url = checked_url(body.url)
        with db.connect() as conn:
            cid, stamp = uuid7(), iso_now()
            conn.execute(
                "INSERT INTO calendars(id,kind,name,color,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (cid, "subscription", body.name.strip(), body.color, stamp, stamp),
            )
            conn.execute(
                "INSERT INTO subscriptions(calendar_id,url,refresh_minutes,next_attempt) VALUES(?,?,?,0)",
                (cid, url, body.refresh_minutes),
            )
            return calendar_json(conn, calendar(conn, cid))

    @app.put("/api/subscriptions/{cid}")
    def update_subscription(cid: str, body: SubscriptionPatch):
        with db.connect() as conn:
            calendar(conn, cid, {"subscription"})
            if body.url is not None:
                conn.execute(
                    "UPDATE subscriptions SET url=?,etag=NULL,last_modified=NULL,content_hash=NULL,"
                    "failures=0,last_error=NULL,next_attempt=0 WHERE calendar_id=?",
                    (checked_url(body.url), cid),
                )
            if body.enabled is not None:
                conn.execute(
                    "UPDATE subscriptions SET enabled=?,next_attempt=? WHERE calendar_id=?",
                    (int(body.enabled), 0 if body.enabled else time.time() + 10**9, cid),
                )
            if body.refresh_minutes is not None:
                if body.refresh_minutes not in REFRESH_CHOICES:
                    raise HTTPException(422, "Unsupported refresh interval")
                conn.execute(
                    "UPDATE subscriptions SET refresh_minutes=? WHERE calendar_id=?",
                    (body.refresh_minutes, cid),
                )
            return calendar_json(conn, calendar(conn, cid))

    @app.post("/api/subscriptions/{cid}/sync", status_code=202)
    def request_sync(cid: str):
        with db.connect() as conn:
            calendar(conn, cid, {"subscription"})
            conn.execute(
                "UPDATE subscriptions SET next_attempt=0,enabled=1 WHERE calendar_id=?", (cid,)
            )
            return calendar_json(conn, calendar(conn, cid))

    # ── Projection sources ───────────────────────────────────────────

    @app.put("/api/sources/{provider}")
    def update_source(provider: str, body: SourcePatch):
        if provider not in PROVIDERS:
            raise HTTPException(404, "Unknown source")
        with db.connect() as conn:
            if body.enabled is not None:
                conn.execute(
                    "UPDATE sources SET enabled=?,next_attempt=0,last_error=NULL WHERE provider=?",
                    (int(body.enabled), provider),
                )
                if not body.enabled:
                    # Derived copies are rebuildable; opting out removes them.
                    conn.execute("DELETE FROM projected WHERE provider=?", (provider,))
                    conn.execute(
                        "UPDATE sources SET item_count=0,availability=NULL WHERE provider=?",
                        (provider,),
                    )
            if body.color is not None:
                conn.execute("UPDATE sources SET color=? WHERE provider=?", (body.color, provider))
            if body.show_completed is not None:
                conn.execute(
                    "UPDATE sources SET show_completed=? WHERE provider=?",
                    (int(body.show_completed), provider),
                )
            return {"sources": sources_json(conn)}

    @app.post("/api/sources/{provider}/refresh", status_code=202)
    def refresh_source(provider: str):
        if provider not in PROVIDERS:
            raise HTTPException(404, "Unknown source")
        with db.connect() as conn:
            conn.execute(
                "UPDATE sources SET next_attempt=0 WHERE provider=? AND enabled=1", (provider,)
            )
            return {"sources": sources_json(conn)}

    @app.get("/api/projected/open")
    def projected_open(provider: str, item_id: str):
        """Where a projected date lives in its owner module, per the owner's own resolver.

        No path is ever derived from a label or an item id: without an available, resolved
        target the answer is simply no path, and Chronos opens the provider itself."""
        with db.connect() as conn:
            row = conn.execute(
                "SELECT resource FROM projected WHERE provider=? AND item_id=?",
                (provider, item_id),
            ).fetchone()
        if not row:
            raise HTTPException(404, "Not found")
        try:
            out = nexus.request("POST", "/resources/resolve", {"resource": row["resource"]})
        except Exception:
            return {"availability": "temporarily_unavailable", "open_path": None}
        availability = out.get("availability") or "unknown"
        path = (out.get("open") or {}).get("module_path") if availability == "available" else None
        return {"availability": availability, "open_path": path}

    @app.post("/api/projected/plan", status_code=201)
    def plan(body: PlanBody):
        """Create a native Event about a projected item, linked to the owner's resource."""
        with db.connect() as conn:
            item = conn.execute(
                "SELECT * FROM projected WHERE provider=? AND item_id=?",
                (body.provider, body.item_id),
            ).fetchone()
            if not item:
                raise HTTPException(404, "This entry is no longer provided")
            calendar(conn, body.calendar_id, {"native"})
            eid, stamp = uuid7(), iso_now()
            values = {
                "calendar_id": body.calendar_id,
                "title": item["title"],
                "description": item["summary"],
                "location": "",
                "all_day": item["all_day"],
                "start": item["start"],
                "end": item["end"] or item["start"],
                "time_zone": item["time_zone"] if not item["all_day"] else None,
                "rrule": None,
                "exdates": "[]",
                "status": "confirmed",
            }
            if not item["all_day"] and not values["time_zone"]:
                values["time_zone"] = settings()["time_zone"]
            values["range_start"], values["range_end"] = index_bounds(values)
            columns = ["id", "origin", *values, "created_at", "updated_at"]
            conn.execute(
                f"INSERT INTO events({','.join(columns)}) VALUES({','.join('?' * len(columns))})",
                (eid, "native", *values.values(), stamp, stamp),
            )
            lid = uuid7()
            readers = [body.provider]
            conn.execute(
                "INSERT INTO links(id,event_id,target,relation,readers,label) VALUES(?,?,?,?,?,?)",
                (lid, eid, item["resource"], "chronos.about", json.dumps(readers), item["title"]),
            )
            queue(
                conn,
                "POST",
                "/references",
                {
                    "source": reference("event", eid),
                    "target": item["resource"],
                    "relation": "chronos.about",
                    "metadata": {},
                    "readers": readers,
                },
                lid,
            )
            return event_json(conn, event_row(conn, eid))

    # ── Module protocol (Nexus private network) ──────────────────────

    def require_resolver(request):
        key = os.getenv("NEXUS_RESOLVER_KEY", "")
        if not key or not secrets.compare_digest(
            request.headers.get("x-nexus-resolver-key", ""), key
        ):
            raise HTTPException(403, "Resolver authentication required")

    @app.post("/empyrean/v1/resources/resolve")
    def protocol_resolve(body: dict, request: Request):
        require_resolver(request)
        match = REF.fullmatch(str(body.get("resource", "")))
        if not match or match[1] != "chronos" or match[2] != "event":
            raise HTTPException(404, "Not found")
        with db.connect() as conn:
            row = conn.execute("SELECT * FROM events WHERE id=?", (match[3],)).fetchone()
            if not row:
                gone = conn.execute("SELECT 1 FROM tombstones WHERE id=?", (match[3],)).fetchone()
                raise HTTPException(410 if gone else 404, "Unavailable")
            # Events disclose metadata only to modules they were explicitly shared with.
            shared = any(
                body.get("requester") in json.loads(link["readers"])
                for link in conn.execute("SELECT readers FROM links WHERE event_id=?", (row["id"],))
            ) or conn.execute(
                "SELECT 1 FROM link_grants WHERE event_id=? AND requester=?", (row["id"], body.get("requester"))
            ).fetchone()
            if not shared:
                raise HTTPException(403, "Event has not been shared with requester")
            return {
                "resource": body["resource"],
                "label": row["title"][:200],
                "open_path": f"/events/{row['id']}",
                "representation": {"start": row["start"], "all_day": bool(row["all_day"])},
            }

    @app.post("/empyrean/v1/projections/link-search")
    def link_search(body: dict, request: Request):
        """Events a module may link (ADR 0029): a reference and a label, nothing else. Nexus
        allows only modules whose manifest scope the owner reviewed. A result may later be
        labelled for that module, because this already showed it the same label."""
        require_resolver(request)
        query = body.get("query") if isinstance(body.get("query"), dict) else {}
        limit = max(1, min(int(query.get("limit") or 10) if str(query.get("limit") or 10).isdigit() else 10, 20))
        folded = lambda v: "".join(c for c in unicodedata.normalize("NFKD", v or "") if not unicodedata.combining(c)).lower()  # noqa: E731
        tokens = [t for t in folded(str(query.get("q") or "")[:100]).split() if t][:8]
        requester = str(body.get("requester") or "")
        with db.connect() as conn:
            rows = conn.execute("SELECT id, title, start FROM events WHERE status<>'cancelled' ORDER BY start DESC LIMIT 2000").fetchall()
            found = [r for r in rows if all(t in folded(r["title"]) for t in tokens)][:limit]
            for r in found:
                conn.execute("INSERT OR IGNORE INTO link_grants(event_id, requester, granted_at) VALUES(?,?,?)", (r["id"], requester, iso_now()))
        return {
            "items": [{"resource": reference("event", r["id"]), "label": f"{r['title']} · {str(r['start'])[:10]}"[:200]} for r in found],
            "next_cursor": None,
        }

    @app.get("/empyrean/v1/references/outgoing")
    def outgoing(request: Request, limit: int = 200, cursor: str = ""):
        """Complete authoritative set of edges Chronos publishes to the Nexus index."""
        require_resolver(request)
        limit = max(1, min(limit, 200))
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM links WHERE id>? ORDER BY id LIMIT ?", (cursor, limit + 1)
            ).fetchall()
        page = rows[:limit]
        return {
            "references": [
                {
                    "source": reference("event", r["event_id"]),
                    "target": r["target"],
                    "relation": r["relation"],
                    "metadata": {},
                    "readers": json.loads(r["readers"]),
                }
                for r in page
            ],
            "next_cursor": page[-1]["id"] if len(rows) > limit else None,
        }

    async def receive_artifact(request):
        path = db.path.parent / f"restore-{uuid7()}.part"
        size = 0
        try:
            with open(path, "wb") as out:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > MAX_ARTIFACT:
                        raise HTTPException(413, "Backup artifact exceeds 256 MiB")
                    out.write(chunk)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return path

    def check_artifact(request, path):
        headers = {
            k[len(BACKUP_HEADER) :].lower(): v
            for k, v in request.headers.items()
            if k.lower().startswith(BACKUP_HEADER.lower())
        }
        if headers.get("module") != "chronos" or headers.get("format") != BACKUP_FORMAT:
            raise ValueError("Not a Chronos backup")
        if headers.get("format-version") != str(BACKUP_FORMAT_VERSION):
            raise ValueError("Unsupported backup format version")
        try:
            snapshot = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        except sqlite3.Error as exc:
            raise ValueError("Backup is not a readable database") from exc
        try:
            if snapshot.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Backup database is damaged")
            schema = snapshot.execute("PRAGMA user_version").fetchone()[0]
            if not 1 <= schema <= len(MIGRATIONS):
                raise ValueError("Backup schema is not supported by this version")
            tables = {
                r[0] for r in snapshot.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            if not {"calendars", "events", "links"} <= tables:
                raise ValueError("Backup is missing Chronos data")
        except sqlite3.Error as exc:
            raise ValueError("Backup is not a readable database") from exc
        finally:
            snapshot.close()

    @app.post("/empyrean/v1/backup/export")
    def backup_export(request: Request):
        require_resolver(request)
        path = db.path.parent / f"export-{uuid7()}.part"
        try:
            target = sqlite3.connect(path)
            with db.connect() as conn:
                conn.backup(target)
            target.execute("PRAGMA journal_mode=DELETE")
            target.close()
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return FileResponse(
            path,
            media_type="application/octet-stream",
            background=BackgroundTask(path.unlink, missing_ok=True),
            headers={
                BACKUP_HEADER + "Module": "chronos",
                BACKUP_HEADER + "Module-Version": VERSION,
                BACKUP_HEADER + "Format": BACKUP_FORMAT,
                BACKUP_HEADER + "Format-Version": str(BACKUP_FORMAT_VERSION),
                BACKUP_HEADER + "Created-At": clock().isoformat(),
                BACKUP_HEADER + "Restorable-By": f">={VERSION},<1",
            },
        )

    @app.post("/empyrean/v1/backup/validate")
    async def backup_validate(request: Request):
        require_resolver(request)
        path = await receive_artifact(request)
        try:
            await run_in_threadpool(check_artifact, request, path)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        finally:
            path.unlink(missing_ok=True)
        return {"valid": True}

    def replace_data(path):
        # Subscription refreshes delete events missing from feeds: suspend them durably
        # until Nexus finalizes the restore.
        worker.suspended.write_text(clock().isoformat())
        snapshot = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            with db.connect() as conn:
                snapshot.backup(conn)
        finally:
            snapshot.close()
        db.migrate()
        with db.connect() as conn:
            conn.execute("DELETE FROM outbox")
            conn.execute("UPDATE subscriptions SET running=0")
            for link in conn.execute("SELECT * FROM links").fetchall():
                queue(
                    conn,
                    "POST",
                    "/references",
                    {
                        "source": reference("event", link["event_id"]),
                        "target": link["target"],
                        "relation": link["relation"],
                        "metadata": {},
                        "readers": json.loads(link["readers"]),
                    },
                    link["id"],
                )

    @app.post("/empyrean/v1/backup/restore")
    async def backup_restore(request: Request):
        require_resolver(request)
        path = await receive_artifact(request)
        try:
            try:
                await run_in_threadpool(check_artifact, request, path)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            await run_in_threadpool(replace_data, path)
        finally:
            path.unlink(missing_ok=True)
        return {"restored": True}

    @app.post("/empyrean/v1/backup/finalize")
    def backup_finalize(request: Request):
        require_resolver(request)
        worker.suspended.unlink(missing_ok=True)
        return {"finalized": True}

    # ── Interface ────────────────────────────────────────────────────

    def catalogs():
        result = {}
        for directory in (ROOT / "frontend/locales", db.path.parent / "locales"):
            if not directory.exists():
                continue
            for file in directory.glob("*.json"):
                if not re.fullmatch(r"[a-z]{2,3}(-[A-Za-z0-9]{2,8})?", file.stem):
                    continue
                try:
                    messages = json.loads(file.read_text(encoding="utf-8"))
                except (ValueError, OSError):
                    continue
                if isinstance(messages, dict) and all(
                    isinstance(v, str) for v in messages.values()
                ):
                    result[file.stem] = {**result.get(file.stem, {}), **messages}
        return result

    @app.get("/icon.svg", include_in_schema=False)
    def app_icon():
        """The application icon Nexus shows in its switcher and module list (manifest `icon`)."""
        return FileResponse(ROOT / "frontend/icon.svg", media_type="image/svg+xml")

    @app.get("/{path:path}", response_class=HTMLResponse)
    def ui(path: str):
        script = (
            (ROOT / "frontend/app.js")
            .read_text(encoding="utf-8")
            .replace("/*CATALOGS*/ {}", json.dumps(catalogs()).replace("<", "\\u003c"))
        )
        # Nexus navigation contract: the shared SDK, then Chronos's adapter.
        script = "\n".join(
            [
                script,
                (ROOT / "frontend/vendor/nexus-navigation.js").read_text(encoding="utf-8"),
                (ROOT / "frontend/navigation.js").read_text(encoding="utf-8"),
            ]
        )
        html = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
        return html.replace("/*STYLE*/", style).replace("/*SCRIPT*/", script)

    return app
