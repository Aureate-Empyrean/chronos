"""Background work: subscription refresh, projection reconciliation, Nexus outbox and hints.

Nothing here makes correctness depend on events. Subscriptions are refreshed on a schedule;
projected entries are replaced only after a complete successful fetch; events from Nexus
only bring the next reconciliation forward."""

import hashlib
import json
import os
import time
from datetime import timedelta

import httpx

from chronos import ical, net
from chronos.store import apply_records, normalize_item, queue
from chronos.util import iso_now

PROVIDERS = {"lyra": "#C98BE0", "mnemosyne": "#8B7CF6", "meridian": "#E3AE8E"}
# Mnemosyne deadlines and Meridian birthdays/anniversaries are opt-in (owner decision D4).
DEFAULT_ENABLED = {"lyra": 1, "mnemosyne": 0, "meridian": 0}
HINTS = {
    "lyra.dated-items.changed": "lyra",
    "mnemosyne.resource.changed": "mnemosyne",
    "meridian.dated-items.changed": "meridian",
}
RECONCILE_SECONDS = 15 * 60
WINDOW_PAST = 90
WINDOW_FUTURE = 400
MAX_PAGES = 40


class Nexus:
    """Module-side Nexus API client; credentials come from the broker environment."""

    def __init__(self, transport=None):
        self.transport = transport

    def request(self, method, path, body=None):
        with httpx.Client(transport=self.transport, timeout=8, trust_env=False) as client:
            response = client.request(
                method,
                os.environ["NEXUS_URL"] + "/api/v1/module" + path,
                headers={"Authorization": "Bearer " + os.environ["NEXUS_TOKEN"]},
                json=body,
            )
            response.raise_for_status()
            return response.json()


class Worker:
    def __init__(self, db, nexus, settings, clock, feed_transport=None, resolver=None):
        self.db = db
        self.nexus = nexus
        self.settings = settings
        self.clock = clock
        self.feed_transport = feed_transport
        self.resolver = resolver or net.default_resolver
        self.suspended = db.path.parent / "sync-suspended"
        self.last_poll = 0.0

    # ── Subscriptions ────────────────────────────────────────────────

    def due_subscriptions(self):
        with self.db.connect() as conn:
            return [
                r["calendar_id"]
                for r in conn.execute(
                    "SELECT calendar_id FROM subscriptions WHERE enabled=1 AND next_attempt<=?",
                    (time.time(),),
                )
            ]

    def sync_subscription(self, calendar_id):
        with self.db.connect() as conn:
            sub = conn.execute(
                "SELECT * FROM subscriptions WHERE calendar_id=?", (calendar_id,)
            ).fetchone()
            if not sub:
                return None
            conn.execute(
                "UPDATE subscriptions SET running=1,last_attempt_at=? WHERE calendar_id=?",
                (iso_now(), calendar_id),
            )
        result = {"error": None, "warning": None, "counts": None}
        try:
            status, body, headers = net.fetch(
                sub["url"],
                etag=sub["etag"],
                last_modified=sub["last_modified"],
                transport=self.feed_transport,
                resolver=self.resolver,
            )
            digest = hashlib.sha256(body).hexdigest() if status == 200 else sub["content_hash"]
            with self.db.connect() as conn:
                if status == 200 and digest != sub["content_hash"]:
                    parsed = ical.parse_calendar(body, self.settings()["time_zone"])
                    existing = conn.execute(
                        "SELECT count(*) FROM events WHERE calendar_id=?", (calendar_id,)
                    ).fetchone()[0]
                    if not parsed["events"] and existing:
                        # A feed that suddenly has no events is more often broken than empty.
                        result["warning"] = (
                            "The feed returned no events; the existing events were kept."
                        )
                        digest = sub["content_hash"]
                    else:
                        result["counts"] = apply_records(
                            conn, calendar_id, "subscription", parsed["events"], True
                        )
                        issues = len(parsed["errors"])
                        if issues:
                            result["warning"] = f"{issues} events in the feed could not be read."
                        elif parsed["warnings"]:
                            result["warning"] = parsed["warnings"][0]
                conn.execute(
                    "UPDATE subscriptions SET last_success_at=?,last_error=NULL,last_warning=?,"
                    "etag=?,last_modified=?,content_hash=?,failures=0,next_attempt=? "
                    "WHERE calendar_id=?",
                    (
                        iso_now(),
                        result["warning"]
                        if result["counts"] is not None or result["warning"]
                        else sub["last_warning"],
                        headers.get("etag") or sub["etag"],
                        headers.get("last-modified") or sub["last_modified"],
                        digest,
                        time.time() + sub["refresh_minutes"] * 60,
                        calendar_id,
                    ),
                )
        except (net.FetchError, ical.FeedError) as exc:
            result["error"] = str(exc)
        except Exception as exc:  # never leak details (they may contain the URL)
            print(f"Subscription sync failed: {type(exc).__name__}", flush=True)
            result["error"] = "The calendar could not be synchronized."
        if result["error"]:
            with self.db.connect() as conn:
                failures = sub["failures"] + 1
                delay = min(sub["refresh_minutes"] * 60, 300 * 2 ** min(failures - 1, 6))
                conn.execute(
                    "UPDATE subscriptions SET last_error=?,failures=?,next_attempt=? "
                    "WHERE calendar_id=?",
                    (result["error"], failures, time.time() + delay, calendar_id),
                )
        with self.db.connect() as conn:
            conn.execute("UPDATE subscriptions SET running=0 WHERE calendar_id=?", (calendar_id,))
        return result

    # ── Projections ──────────────────────────────────────────────────

    def ensure_sources(self, conn):
        for provider, color in PROVIDERS.items():
            conn.execute(
                "INSERT OR IGNORE INTO sources(provider,enabled,color) VALUES(?,?,?)",
                (provider, DEFAULT_ENABLED[provider], color),
            )

    def due_sources(self):
        with self.db.connect() as conn:
            return [
                r["provider"]
                for r in conn.execute(
                    "SELECT provider FROM sources WHERE enabled=1 AND next_attempt<=?",
                    (time.time(),),
                )
            ]

    def reconcile(self, provider):
        """Replace derived entries for a provider only after a complete, valid fetch."""
        today = self.clock().date()
        window = {
            "from": (today - timedelta(days=WINDOW_PAST)).isoformat(),
            "to": (today + timedelta(days=WINDOW_FUTURE)).isoformat(),
        }
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE sources SET last_attempt_at=?,next_attempt=? WHERE provider=?",
                (iso_now(), time.time() + RECONCILE_SECONDS, provider),
            )
        items, cursor, error, availability = [], None, None, None
        try:
            for _ in range(MAX_PAGES):
                page = self.nexus.request(
                    "POST",
                    "/projections/query",
                    {
                        "module": provider,
                        "projection": "dated-items",
                        "query": window,
                        "cursor": cursor,
                    },
                )
                availability = page.get("availability")
                if availability != "available":
                    error = availability or "temporarily_unavailable"
                    break
                items.extend(page.get("items") or [])
                cursor = page.get("next_cursor")
                if not cursor:
                    break
            else:
                error = "too_many_pages"
        except httpx.HTTPStatusError as exc:
            error = "not_granted" if exc.response.status_code == 403 else "nexus_error"
        except (httpx.HTTPError, KeyError, ValueError):
            error = "nexus_unreachable"
        with self.db.connect() as conn:
            if error:
                # Failure is never "zero items": keep what we have and mark it stale.
                conn.execute(
                    "UPDATE sources SET last_error=?,availability=? WHERE provider=?",
                    (error, availability or error, provider),
                )
                return {"ok": False, "error": error}
            fetched = iso_now()
            rows, invalid = {}, 0
            for item in items:
                row = normalize_item(provider, item, fetched) if isinstance(item, dict) else None
                if row is None:
                    invalid += 1
                    continue
                rows[row["item_id"]] = row
            conn.execute("BEGIN IMMEDIATE")
            if not conn.execute(
                "SELECT enabled FROM sources WHERE provider=?", (provider,)
            ).fetchone()[0]:
                return {"ok": False, "error": "disabled"}
            conn.execute("DELETE FROM projected WHERE provider=?", (provider,))
            for row in rows.values():
                conn.execute(
                    f"INSERT INTO projected({','.join(row)}) VALUES({','.join('?' * len(row))})",
                    tuple(row.values()),
                )
            conn.execute(
                "UPDATE sources SET last_success_at=?,last_error=?,availability='available',"
                "item_count=? WHERE provider=?",
                (fetched, f"invalid_items:{invalid}" if invalid else None, len(rows), provider),
            )
        return {"ok": True, "items": len(rows), "invalid": invalid}

    def poll_hints(self):
        """Bring reconciliation forward when a provider announces a change."""
        with self.db.connect() as conn:
            row = conn.execute("SELECT value FROM cursors WHERE name='events'").fetchone()
        cursor = row["value"] if row else 0
        touched = set()
        for _ in range(10):
            page = self.nexus.request("GET", f"/events?after={cursor}")
            for entry in page.get("events", []):
                provider = HINTS.get(entry.get("event", {}).get("type"))
                if provider:
                    touched.add(provider)
            advanced = page.get("next_cursor", cursor)
            if advanced == cursor:
                break
            cursor = advanced
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO cursors(name,value) VALUES('events',?) "
                "ON CONFLICT(name) DO UPDATE SET value=excluded.value",
                (cursor,),
            )
            for provider in touched:
                conn.execute(
                    "UPDATE sources SET next_attempt=min(next_attempt,?) WHERE provider=? "
                    "AND enabled=1",
                    (time.time() + 5, provider),
                )
        return touched

    # ── Nexus reference outbox ───────────────────────────────────────

    def flush(self, force=False):
        with self.db.connect() as conn:
            entries = conn.execute(
                "SELECT * FROM outbox WHERE next_attempt<=? ORDER BY id LIMIT 40",
                (float("inf") if force else time.time(),),
            ).fetchall()
        for entry in entries:
            try:
                result = self.nexus.request(
                    entry["method"],
                    entry["path"],
                    json.loads(entry["body"]) if entry["body"] else None,
                )
            except httpx.HTTPStatusError as exc:
                code = exc.response.status_code
                # 404 on DELETE: already gone. 422: refused as invalid; enumeration
                # publishes the edge once owner reconciliation can accept it.
                if not ((entry["method"] == "DELETE" and code == 404) or code == 422):
                    self._retry(entry)
                    continue
                result = {}
            except (httpx.HTTPError, KeyError, OSError):
                self._retry(entry)
                continue
            with self.db.connect() as conn:
                if entry["link_id"] and result.get("reference"):
                    remote = result["reference"]["id"]
                    owner = conn.execute(
                        "SELECT e.trashed_at FROM links l JOIN events e ON e.id=l.event_id "
                        "WHERE l.id=?",
                        (entry["link_id"],),
                    ).fetchone()
                    if owner and owner["trashed_at"]:
                        # Trashed while this was in flight: an event in Trash publishes nothing.
                        queue(conn, "DELETE", f"/references/{remote}")
                    else:
                        conn.execute(
                            "UPDATE links SET remote_id=? WHERE id=?", (remote, entry["link_id"])
                        )
                conn.execute("DELETE FROM outbox WHERE id=?", (entry["id"],))

    def _retry(self, entry):
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE outbox SET attempts=attempts+1,next_attempt=? WHERE id=?",
                (time.time() + min(300, 2 ** min(entry["attempts"] + 1, 8)), entry["id"]),
            )

    # ── Loop ─────────────────────────────────────────────────────────

    def tick(self):
        if self.suspended.exists():
            return
        for calendar_id in self.due_subscriptions():
            self.sync_subscription(calendar_id)
        if "NEXUS_TOKEN" not in os.environ:
            return
        try:
            if time.monotonic() - self.last_poll >= 30:
                self.last_poll = time.monotonic()
                self.poll_hints()
        except (httpx.HTTPError, KeyError, ValueError):
            pass
        for provider in self.due_sources():
            self.reconcile(provider)
        self.flush()
