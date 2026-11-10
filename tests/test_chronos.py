import json
from datetime import datetime, timezone

import httpx
import pytest
from chronos.app import create_app
from fastapi.testclient import TestClient

KEY = "k" * 40
GW = {"x-nexus-gateway-key": KEY}
RES = {"x-nexus-resolver-key": KEY}


class FakeNexus:
    def __init__(self):
        self.calls = []
        self.pages = {}
        self.fail = None
        self.directory = {"availability": "module_uninstalled"}

    def request(self, method, path, body=None):
        self.calls.append((method, path, body))
        if self.fail:
            raise self.fail
        if path == "/projections/query" and body["projection"] == "people-directory":
            return self.directory
        if path == "/projections/query":
            pages = self.pages.get(body["module"])
            if pages is None:
                return {"availability": "module_uninstalled"}
            index = int(body["cursor"] or 0)
            items, more = pages[index]
            return {
                "availability": "available",
                "items": items,
                "next_cursor": str(index + 1) if more else None,
            }
        if path == "/references":
            return {"reference": {"id": "remote-1"}}
        if path.startswith("/events"):
            return {"events": [], "next_cursor": 0}
        if path == "/resources/resolve":
            return {"availability": "available", "label": "Live label"}
        return {}


class Feed:
    """A fake upstream calendar server behind the SSRF-checked fetcher."""

    def __init__(self):
        self.body = b""
        self.status = 200
        self.headers = {"content-type": "text/calendar"}
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        return httpx.Response(self.status, content=self.body, headers=self.headers)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_RESOLVER_KEY", KEY)
    nexus, feed = FakeNexus(), Feed()
    addresses = {"feeds.example.com": ["93.184.215.14"], "evil.example.com": ["10.0.0.7"]}
    app = create_app(
        tmp_path,
        nexus=nexus,
        feed_transport=httpx.MockTransport(feed),
        resolver=lambda host, port: addresses.get(host, ["93.184.215.20"]),
        workers=False,
    )
    with TestClient(app, headers=GW) as client:
        client.put("/api/settings", json={"time_zone": "Europe/Bratislava"})
        yield client, app, nexus, feed


def native(client):
    return next(c for c in client.get("/api/state").json()["calendars"] if c["kind"] == "native")


def occurrences(client, start, end):
    return client.get(f"/api/occurrences?start={start}&end={end}").json()["occurrences"]


def test_gateway_key_is_required(env):
    client = env[0]
    assert client.get("/api/state", headers={"x-nexus-gateway-key": "wrong"}).status_code == 403
    assert client.get("/health", headers={}).json()["status"] == "ok"


def test_native_timed_event_keeps_zone_and_recurs_across_dst(env):
    client = env[0]
    cal = native(client)
    created = client.post(
        "/api/events",
        json={
            "calendar_id": cal["id"],
            "title": "Standup",
            "start": "2026-10-19T09:30",
            "end": "2026-10-19T10:00",
            "time_zone": "Europe/Bratislava",
            "rrule": "FREQ=WEEKLY;COUNT=4",
        },
    )
    assert created.status_code == 201, created.text
    event = created.json()
    assert event["start"] == "2026-10-19T07:30:00Z"  # CEST, UTC+2
    assert event["start_local"] == "2026-10-19T09:30"
    found = occurrences(client, "2026-10-01T00:00:00Z", "2026-11-30T00:00:00Z")
    assert [o["start"] for o in found] == [
        "2026-10-19T07:30:00Z",
        "2026-10-26T08:30:00Z",  # CET after 25 October: wall time stays 09:30
        "2026-11-02T08:30:00Z",
        "2026-11-09T08:30:00Z",
    ]
    skipped = client.delete(f"/api/events/{event['id']}?occurrence=2026-10-26T08:30:00Z")
    assert skipped.json()["deleted"] == "occurrence"
    found = occurrences(client, "2026-10-01T00:00:00Z", "2026-11-30T00:00:00Z")
    assert len(found) == 3 and "2026-10-26T08:30:00Z" not in [o["start"] for o in found]
    # Editing the title keeps the skipped occurrence.
    body = {
        "calendar_id": cal["id"],
        "title": "Daily standup",
        "start": "2026-10-19T09:30",
        "end": "2026-10-19T10:00",
        "time_zone": "Europe/Bratislava",
        "rrule": "FREQ=WEEKLY;COUNT=4",
    }
    assert client.put(f"/api/events/{event['id']}", json=body).json()["exdates"] == [
        "2026-10-26T08:30:00Z"
    ]


def test_all_day_events_stay_dates(env):
    client = env[0]
    cal = native(client)
    event = client.post(
        "/api/events",
        json={
            "calendar_id": cal["id"],
            "title": "Trip",
            "all_day": True,
            "start": "2026-11-20",
            "end": "2026-11-23",
        },
    ).json()
    assert (event["start"], event["end"], event["time_zone"]) == ("2026-11-20", "2026-11-23", None)
    found = occurrences(client, "2026-11-21T23:00:00Z", "2026-11-22T23:00:00Z")
    assert [(o["start"], o["end"], o["all_day"]) for o in found] == [
        ("2026-11-20", "2026-11-23", True)
    ]
    bad = client.post(
        "/api/events",
        json={
            "calendar_id": cal["id"],
            "title": "x",
            "all_day": True,
            "start": "2026-11-20",
            "end": "2026-11-20",
        },
    )
    assert bad.status_code == 422


def test_native_validation(env):
    client = env[0]
    cal = native(client)
    base = {
        "calendar_id": cal["id"],
        "title": "x",
        "start": "2026-11-20T10:00",
        "end": "2026-11-20T11:00",
    }
    assert client.post("/api/events", json={**base, "time_zone": "Mars/Base"}).status_code == 422
    assert client.post("/api/events", json={**base, "rrule": "FREQ=SECONDLY"}).status_code == 422
    assert (
        client.post("/api/events", json={**base, "rrule": "FREQ=DAILY;BYSETPOS=1"}).status_code
        == 422
    )
    assert client.post("/api/events", json={**base, "end": "2026-11-20T09:00"}).status_code == 422
    assert client.post("/api/events", json={**base, "extra": 1}).status_code == 422


ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
X-WR-CALNAME:Racing 2026
X-WR-TIMEZONE:Europe/London
BEGIN:VEVENT
UID:race-1@example.com
DTSTART:20261108T130000Z
DTEND:20261108T150000Z
SUMMARY:Grand Prix
LOCATION:Interlagos
STATUS:CONFIRMED
END:VEVENT
BEGIN:VEVENT
UID:weekly@example.com
DTSTART;TZID=America/New_York:20261103T090000
DTEND;TZID=America/New_York:20261103T093000
RRULE:FREQ=WEEKLY;UNTIL=20261124T140000Z
EXDATE;TZID=America/New_York:20261110T090000
SUMMARY:Weekly sync
END:VEVENT
BEGIN:VEVENT
UID:weekly@example.com
RECURRENCE-ID;TZID=America/New_York:20261117T090000
DTSTART;TZID=America/New_York:20261117T110000
DTEND;TZID=America/New_York:20261117T113000
SUMMARY:Weekly sync (moved)
END:VEVENT
BEGIN:VEVENT
UID:weekly@example.com
RECURRENCE-ID;TZID=America/New_York:20261124T090000
DTSTART;TZID=America/New_York:20261124T090000
DTEND;TZID=America/New_York:20261124T093000
STATUS:CANCELLED
SUMMARY:Weekly sync
END:VEVENT
BEGIN:VEVENT
UID:holiday@example.com
DTSTART;VALUE=DATE:20261225
DTEND;VALUE=DATE:20261227
SUMMARY:Holidays
END:VEVENT
BEGIN:VEVENT
DTSTART:20261105T180000
SUMMARY:Floating dinner
END:VEVENT
BEGIN:VEVENT
UID:broken@example.com
SUMMARY:No start
END:VEVENT
BEGIN:VTODO
UID:todo
SUMMARY:Ignored task
END:VTODO
END:VCALENDAR
"""


def test_import_preview_commit_and_reimport(env):
    client = env[0]
    preview = client.post("/api/import/preview", json={"content": ICS, "filename": "f1.ics"}).json()
    assert preview["name"] == "Racing 2026"
    assert preview["total"] == 6 and preview["recurring"] == 1 and preview["overrides"] == 2
    assert preview["all_day"] == 1 and preview["error_count"] == 1
    assert preview["errors"][0]["title"] == "No start"
    assert preview["ignored"] == {"VTODO": 1}
    assert "America/New_York" in preview["zones"]

    result = client.post("/api/import", json={"content": ICS, "filename": "f1.ics"}).json()
    assert (result["created"], result["updated"], result["unchanged"]) == (6, 0, 0)
    cid = result["calendar"]["id"]
    assert result["calendar"]["kind"] == "import" and result["calendar"]["event_count"] == 6

    found = occurrences(client, "2026-11-01T00:00:00Z", "2026-12-31T00:00:00Z")
    weekly = sorted(o["start"] for o in found if o["title"].startswith("Weekly"))
    # 3 Nov (EST from 1 Nov) 14:00Z; 10 Nov excluded; 17 Nov moved to 11:00; 24 Nov cancelled.
    assert weekly == ["2026-11-03T14:00:00Z", "2026-11-17T16:00:00Z"]
    floating = next(o for o in found if o["title"] == "Floating dinner")
    assert floating["start"] == "2026-11-05T18:00:00Z"  # X-WR-TIMEZONE Europe/London (GMT)
    assert all(o["readonly"] and o["origin"] == "import" for o in found)

    again = client.post(
        "/api/import", json={"content": ICS, "filename": "f1.ics", "calendar_id": cid}
    ).json()
    assert (again["created"], again["updated"], again["unchanged"]) == (0, 0, 6)
    preview = client.post("/api/import/preview", json={"content": ICS, "calendar_id": cid}).json()
    assert preview["already_in_target"] == 6

    changed = ICS.replace("SUMMARY:Grand Prix", "SUMMARY:Grand Prix (Sprint)").replace(
        "BEGIN:VEVENT\nUID:holiday", "BEGIN:VEVENT\nUID:holiday-renamed"
    )
    updated = client.post("/api/import", json={"content": changed, "calendar_id": cid}).json()
    # One-time imports update and add, but never delete what a file no longer contains.
    assert (updated["created"], updated["updated"]) == (1, 1)
    assert updated["calendar"]["event_count"] == 7
    event_id = next(o["event_id"] for o in found if o["title"] == "Grand Prix")
    assert client.get(f"/api/events/{event_id}").json()["title"] == "Grand Prix (Sprint)"
    assert client.put(
        f"/api/events/{event_id}",
        json={
            "calendar_id": cid,
            "title": "x",
            "start": "2026-11-08T13:00",
            "end": "2026-11-08T14:00",
        },
    ).status_code in {409, 422}


def test_import_never_touches_native_calendars(env):
    client = env[0]
    cal = native(client)
    assert (
        client.post("/api/import", json={"content": ICS, "calendar_id": cal["id"]}).status_code
        == 409
    )
    assert client.post("/api/import/preview", json={"content": "hello"}).status_code == 422
    assert client.post(
        "/api/import/preview", json={"content": "BEGIN:VCALENDAR\nbroken"}
    ).status_code in {200, 422}


def test_custom_vtimezone_is_matched_to_iana(env):
    client = env[0]
    custom = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:x
BEGIN:VTIMEZONE
TZID:Office Time
BEGIN:STANDARD
DTSTART:19701025T030000
TZOFFSETFROM:+0200
TZOFFSETTO:+0100
RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:19700329T020000
TZOFFSETFROM:+0100
TZOFFSETTO:+0200
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU
END:DAYLIGHT
END:VTIMEZONE
BEGIN:VEVENT
UID:c1
DTSTART;TZID=Office Time:20261102T100000
DTEND;TZID=Office Time:20261102T110000
SUMMARY:Office
END:VEVENT
END:VCALENDAR
"""
    preview = client.post("/api/import/preview", json={"content": custom}).json()
    assert preview["zones"] and preview["zones"][0].startswith("Europe/")
    assert any("matched" in w for w in preview["warnings"])
    client.post("/api/import", json={"content": custom})
    found = occurrences(client, "2026-11-02T00:00:00Z", "2026-11-03T00:00:00Z")
    assert found[0]["start"] == "2026-11-02T09:00:00Z"


def feed_version(*events):
    body = "\n".join(
        f"BEGIN:VEVENT\nUID:{uid}\nDTSTART:{start}\nDTEND:{start[:9]}235900Z\nSUMMARY:{title}\nEND:VEVENT"
        for uid, start, title in events
    )
    return f"BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:x\n{body}\nEND:VCALENDAR\n".encode()


def subscribe(client, url="https://feeds.example.com/f1.ics?token=secret"):
    response = client.post(
        "/api/subscriptions",
        json={"name": "F1", "url": url, "color": "#E8956A", "refresh_minutes": 60},
    )
    return response


def test_subscription_sync_updates_and_removals(env):
    client, app, _, feed = env
    feed.body = feed_version(
        ("r1", "20261108T130000Z", "Brazil"), ("r2", "20261122T040000Z", "Las Vegas")
    )
    calendar = subscribe(client).json()
    assert calendar["subscription"]["url_display"] == "https://feeds.example.com/…"
    assert "secret" not in json.dumps(client.get("/api/state").json())
    worker = app.state.worker
    assert worker.due_subscriptions() == [calendar["id"]]
    assert worker.sync_subscription(calendar["id"])["counts"]["created"] == 2

    request = feed.requests[-1]
    assert request.url.host == "93.184.215.14"  # pinned to the vetted address
    assert request.headers["host"] == "feeds.example.com"
    assert request.extensions["sni_hostname"] == "feeds.example.com"
    assert request.url.query == b"token=secret"

    ids = {
        o["title"]: o["event_id"]
        for o in occurrences(client, "2026-11-01T00:00:00Z", "2026-12-01T00:00:00Z")
    }
    # Unchanged content: nothing is rewritten, nothing duplicated.
    assert worker.sync_subscription(calendar["id"])["counts"] is None
    feed.body = feed_version(
        ("r1", "20261108T140000Z", "Brazil (time changed)"), ("r3", "20261206T130000Z", "Abu Dhabi")
    )
    counts = worker.sync_subscription(calendar["id"])["counts"]
    assert counts == {"created": 1, "updated": 1, "unchanged": 0, "removed": 1}
    after = {
        o["title"]: o for o in occurrences(client, "2026-11-01T00:00:00Z", "2026-12-31T00:00:00Z")
    }
    assert after["Brazil (time changed)"]["event_id"] == ids["Brazil"]  # stable identity
    assert "Las Vegas" not in after
    gone = client.get(f"/api/events/{ids['Las Vegas']}")
    assert gone.status_code == 404

    feed.status, feed.body = 304, b""
    assert worker.sync_subscription(calendar["id"])["error"] is None

    feed.status, feed.body = 200, feed_version()
    result = worker.sync_subscription(calendar["id"])
    assert "kept" in result["warning"]
    assert client.get("/api/state").json()["calendars"][-1]["event_count"] == 2


@pytest.mark.parametrize(
    "url,message",
    [
        ("https://evil.example.com/x.ics", "private"),
        ("http://127.0.0.1/x.ics", "private"),
        ("http://[::ffff:10.0.0.1]/x.ics", "private"),
        ("http://169.254.169.254/latest", "private"),
        ("https://feeds.example.com:22/x.ics", "ports"),
        ("https://user:pw@feeds.example.com/x.ics", "password"),
        ("ftp://feeds.example.com/x.ics", "https"),
        ("https://printer.local/x.ics", "Local"),
    ],
)
def test_subscription_ssrf_protection(env, url, message):
    client, app, _, feed = env
    response = subscribe(client, url)
    if response.status_code == 422:
        assert message.lower() in response.json()["detail"].lower()
        return
    result = app.state.worker.sync_subscription(response.json()["id"])
    assert message.lower() in result["error"].lower()
    assert feed.requests == []


def test_subscription_redirect_size_and_content_errors(env):
    client, app, _, feed = env
    calendar = subscribe(client).json()
    worker = app.state.worker
    feed.status, feed.headers = 302, {"location": "https://evil.example.com/next"}
    assert "private" in worker.sync_subscription(calendar["id"])["error"].lower()
    feed.status, feed.headers = 200, {"content-type": "text/html"}
    feed.body = b"<html>not a calendar</html>"
    error = worker.sync_subscription(calendar["id"])["error"]
    assert "not an icalendar" in error.lower()
    feed.body = b"BEGIN:VCALENDAR\n" + b"X" * (5 * 1024 * 1024 + 10)
    assert "5 MiB" in worker.sync_subscription(calendar["id"])["error"]
    state = next(
        c for c in client.get("/api/state").json()["calendars"] if c["id"] == calendar["id"]
    )
    assert (
        state["subscription"]["last_error"]
        and "feeds.example.com" not in state["subscription"]["last_error"]
    )


def item(item_id, start, **extra):
    return {
        "id": item_id,
        "resource": f"nexus:v1:lyra:episode:0190f0e4-0000-7000-8000-{item_id.zfill(12)}",
        "kind": "lyra.episode-air",
        "title": f"Dexter · S1E{item_id}",
        "start": start,
        "all_day": True,
        "certainty": "tentative",
        "status": "scheduled",
        **extra,
    }


def test_projection_reconcile_replace_and_failure_keeps(env):
    client, app, nexus, _ = env
    nexus.pages["lyra"] = [
        ([item("1", "2026-11-14"), item("2", "2026-11-21")], True),
        ([item("3", "2026-11-28"), {"id": "bad"}], False),
    ]
    result = app.state.worker.reconcile("lyra")
    assert result == {"ok": True, "items": 3, "invalid": 1}
    query = next(c for c in nexus.calls if c[1] == "/projections/query")[2]
    assert query["module"] == "lyra" and query["projection"] == "dated-items"
    found = [
        o
        for o in occurrences(client, "2026-11-01T00:00:00Z", "2026-12-01T00:00:00Z")
        if o["origin"] == "projection"
    ]
    assert [(o["title"], o["start"], o["all_day"], o["certainty"]) for o in found][0] == (
        "Dexter · S1E1",
        "2026-11-14",
        True,
        "tentative",
    )
    # The air date of episode 2 changes upstream: same identity, no duplicate.
    nexus.pages["lyra"] = [([item("1", "2026-11-14"), item("2", "2026-11-22")], False)]
    app.state.worker.reconcile("lyra")
    found = [
        o
        for o in occurrences(client, "2026-11-01T00:00:00Z", "2026-12-01T00:00:00Z")
        if o["origin"] == "projection"
    ]
    assert [(o["item_id"], o["start"]) for o in found] == [("1", "2026-11-14"), ("2", "2026-11-22")]
    # The provider becomes unavailable: entries survive, the source is marked stale.
    nexus.pages.pop("lyra")
    assert app.state.worker.reconcile("lyra")["ok"] is False
    assert (
        len(
            [
                o
                for o in occurrences(client, "2026-11-01T00:00:00Z", "2026-12-01T00:00:00Z")
                if o["origin"] == "projection"
            ]
        )
        == 2
    )
    source = next(s for s in client.get("/api/state").json()["sources"] if s["provider"] == "lyra")
    assert source["availability"] == "module_uninstalled" and source["item_count"] == 2
    nexus.fail = httpx.ConnectError("down")
    assert app.state.worker.reconcile("lyra")["error"] == "nexus_unreachable"


def test_mnemosyne_projection_is_opt_in_and_opt_out_removes_copies(env):
    client, app, nexus, _ = env
    sources = {s["provider"]: s for s in client.get("/api/state").json()["sources"]}
    assert sources["mnemosyne"]["enabled"] is False and sources["lyra"]["enabled"] is True
    assert "mnemosyne" not in app.state.worker.due_sources()
    task = {
        **item("9", "2026-11-18"),
        "resource": "nexus:v1:mnemosyne:task:0190f0e4-0000-7000-8000-000000000009",
        "kind": "mnemosyne.task-deadline",
        "title": "Submit report",
        "certainty": "confirmed",
        "status": "open",
        "context": "Work",
    }
    done = {**task, "id": "10", "title": "Done task", "status": "completed"}
    nexus.pages["mnemosyne"] = [([task, done], False)]
    client.put("/api/sources/mnemosyne", json={"enabled": True})
    assert "mnemosyne" in app.state.worker.due_sources()
    app.state.worker.reconcile("mnemosyne")
    titles = [
        o["title"] for o in occurrences(client, "2026-11-01T00:00:00Z", "2026-12-01T00:00:00Z")
    ]
    assert "Submit report" in titles and "Done task" not in titles
    client.put("/api/sources/mnemosyne", json={"show_completed": True})
    titles = [
        o["title"] for o in occurrences(client, "2026-11-01T00:00:00Z", "2026-12-01T00:00:00Z")
    ]
    assert "Done task" in titles
    client.put("/api/sources/mnemosyne", json={"enabled": False})
    with app.state.db.connect() as conn:
        assert (
            conn.execute("SELECT count(*) FROM projected WHERE provider='mnemosyne'").fetchone()[0]
            == 0
        )
    # A provider cannot inject items for another module's resources.
    nexus.pages["lyra"] = [([{**task, "kind": "lyra.episode-air"}], False)]
    assert app.state.worker.reconcile("lyra")["invalid"] == 1


def test_plan_links_event_resolves_and_enumerates(env):
    client, app, nexus, _ = env
    nexus.pages["lyra"] = [([item("1", "2026-11-14")], False)]
    app.state.worker.reconcile("lyra")
    cal = native(client)
    event = client.post(
        "/api/projected/plan", json={"provider": "lyra", "item_id": "1", "calendar_id": cal["id"]}
    ).json()
    assert event["origin"] == "native" and event["all_day"] and event["start"] == "2026-11-14"
    assert event["links"][0]["relation"] == "chronos.about"
    app.state.worker.flush(force=True)
    posted = next(c for c in nexus.calls if c[1] == "/references")[2]
    assert posted["source"] == f"nexus:v1:chronos:event:{event['id']}"
    assert posted["readers"] == ["lyra"]
    assert (
        client.get(f"/api/events/{event['id']}/links").json()["links"][0]["label"] == "Live label"
    )

    resolve = lambda who: client.post(  # noqa: E731
        "/empyrean/v1/resources/resolve",
        headers=RES,
        json={"resource": event["reference"], "requester": who},
    )
    assert resolve("lyra").json()["label"] == "Dexter · S1E1"
    assert resolve("mnemosyne").status_code == 403
    assert (
        client.post(
            "/empyrean/v1/resources/resolve",
            json={"resource": event["reference"], "requester": "lyra"},
        ).status_code
        == 403
    )  # resolver key required

    edges = client.get("/empyrean/v1/references/outgoing", headers=RES).json()
    assert edges["references"] == [
        {
            "source": event["reference"],
            "target": event["links"][0]["target"],
            "relation": "chronos.about",
            "metadata": {},
            "readers": ["lyra"],
        }
    ]
    entry = client.delete(f"/api/events/{event['id']}").json()["trash"]
    assert resolve("lyra").status_code == 404  # in Trash: unavailable, and it may come back
    app.state.worker.flush(force=True)
    assert ("DELETE", "/references/remote-1", None) in nexus.calls
    assert client.get("/empyrean/v1/references/outgoing", headers=RES).json()["references"] == []
    client.delete(f"/api/trash/{entry}?confirmed=true")
    assert resolve("lyra").status_code == 410  # deleted for good


def test_backup_roundtrip_and_suspends_sync(env):
    client, app, _, feed = env
    cal = native(client)
    client.post(
        "/api/events",
        json={
            "calendar_id": cal["id"],
            "title": "Keep me",
            "all_day": True,
            "start": "2026-12-01",
            "end": "2026-12-02",
        },
    )
    exported = client.post("/empyrean/v1/backup/export", headers=RES)
    assert exported.status_code == 200
    headers = {
        k: v for k, v in exported.headers.items() if k.lower().startswith("x-empyrean-backup-")
    }
    assert headers["x-empyrean-backup-module"] == "chronos"
    artifact = exported.content
    client.delete(
        f"/api/events/{occurrences(client, '2026-11-30T00:00:00Z', '2026-12-03T00:00:00Z')[0]['event_id']}"
    )
    assert client.post(
        "/empyrean/v1/backup/validate", headers={**RES, **headers}, content=artifact
    ).json() == {"valid": True}
    assert (
        client.post(
            "/empyrean/v1/backup/validate", headers={**RES, **headers}, content=b"junk"
        ).status_code
        == 422
    )
    assert client.post(
        "/empyrean/v1/backup/restore", headers={**RES, **headers}, content=artifact
    ).json() == {"restored": True}
    assert app.state.worker.suspended.exists()
    restored = occurrences(client, "2026-11-30T00:00:00Z", "2026-12-03T00:00:00Z")
    assert [o["title"] for o in restored] == ["Keep me"]
    assert client.post("/empyrean/v1/backup/finalize", headers=RES).json() == {"finalized": True}
    assert not app.state.worker.suspended.exists()


def test_search_and_categories(env):
    client = env[0]
    cal = native(client)
    category = client.post("/api/categories", json={"name": "Health", "color": "#8FC2A9"}).json()
    assert (
        client.post("/api/categories", json={"name": "health", "color": "#8FC2A9"}).status_code
        == 409
    )
    client.post(
        "/api/events",
        json={
            "calendar_id": cal["id"],
            "title": "Dentist",
            "location": "Old town 5",
            "start": "2026-11-20T10:00",
            "end": "2026-11-20T11:00",
            "category_id": category["id"],
        },
    )
    found = client.get("/api/search?q=old to").json()["events"]
    assert [e["title"] for e in found] == ["Dentist"]
    occurrence = occurrences(client, "2026-11-20T00:00:00Z", "2026-11-21T00:00:00Z")[0]
    assert occurrence["color"] == "#8FC2A9"
    assert client.get("/api/search?q=%25").json()["events"] == []


def test_interface_uses_shared_design_files(env):
    page = env[0].get("/").text
    assert "Aureate Empyrean shared design tokens — version 2" in page
    assert "Aureate Empyrean foundation stylesheet" in page
    assert "data:font/woff2;base64," in page
    assert "--accent: #7aa7eb" in page.lower()


def test_time_is_utc_and_uuid7(env):
    from chronos.util import uuid7

    value = uuid7()
    assert value[14] == "7" and value[19] in "89ab"
    assert datetime.now(timezone.utc).year >= 2026


def test_serves_its_application_icon(env):
    """The manifest `icon` Nexus loads through its gateway: an SVG tile, not the UI page."""
    response = env[0].get("/icon.svg")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert response.text.lstrip().startswith("<svg") and "<script" not in response.text


# ── 0.2.0: Meridian dates and people ─────────────────────────────────

PERSON = "nexus:v1:meridian:person:0190f0e4-0000-7000-8000-000000000042"


def birthday(item_id, start, **extra):
    return {
        "id": item_id,
        "resource": PERSON,
        "kind": "meridian.birthday",
        "title": "Birthday · Vzorko Kvázimenný",
        "start": start,
        "all_day": True,
        "certainty": "confirmed",
        "status": "scheduled",
        "summary": "Turns 39",
        **extra,
    }


def test_meridian_dates_are_opt_in_and_reconciled(env):
    client, app, nexus, _ = env
    sources = {s["provider"]: s for s in client.get("/api/state").json()["sources"]}
    assert sources["meridian"]["enabled"] is False  # owner decision D4: off by default
    assert "meridian" not in app.state.worker.due_sources()
    nexus.pages["meridian"] = [([birthday("d1:2026", "2026-08-23")], False)]
    client.put("/api/sources/meridian", json={"enabled": True})
    assert "meridian" in app.state.worker.due_sources()
    assert app.state.worker.reconcile("meridian") == {"ok": True, "items": 1, "invalid": 0}
    found = [
        o
        for o in occurrences(client, "2026-08-01T00:00:00Z", "2026-08-31T00:00:00Z")
        if o["origin"] == "projection"
    ]
    assert [(o["title"], o["start"], o["all_day"], o["provider"]) for o in found] == [
        ("Birthday · Vzorko Kvázimenný", "2026-08-23", True, "meridian")
    ]
    # Meridian may only provide dates about its own resources.
    foreign = birthday(
        "x:2026", "2026-08-24", resource="nexus:v1:lyra:movie:0190f0e4-0000-7000-8000-000000000001"
    )
    nexus.pages["meridian"] = [([foreign], False)]
    assert app.state.worker.reconcile("meridian")["invalid"] == 1
    client.put("/api/sources/meridian", json={"enabled": False})
    with app.state.db.connect() as conn:
        assert (
            conn.execute("SELECT count(*) FROM projected WHERE provider='meridian'").fetchone()[0]
            == 0
        )


def test_meridian_change_hint_brings_reconciliation_forward(env):
    client, app, nexus, _ = env
    client.put("/api/sources/meridian", json={"enabled": True})
    with app.state.db.connect() as conn:
        conn.execute("UPDATE sources SET next_attempt=9e12 WHERE provider='meridian'")
    original = nexus.request

    def request(method, path, body=None):
        if path.startswith("/events"):
            nexus.calls.append((method, path, body))
            return {
                "events": [{"event": {"type": "meridian.dated-items.changed"}}],
                "next_cursor": 1,
            }
        return original(method, path, body)

    nexus.request = request
    assert app.state.worker.poll_hints() == {"meridian"}


def test_people_on_events_link_resolve_and_enumerate(env):
    client, app, nexus, _ = env
    cal = native(client)
    event = client.post(
        "/api/events",
        json={
            "calendar_id": cal["id"],
            "title": "Lunch",
            "start": "2026-11-20T12:00",
            "end": "2026-11-20T13:00",
            "time_zone": "Europe/Bratislava",
        },
    ).json()
    # The picker reads Meridian's people-directory through Nexus; names only.
    nexus.directory = {
        "availability": "available",
        "items": [
            {"id": "x", "resource": PERSON, "label": "Vzorko Kvázimenný", "self": False},
            {
                "id": "y",
                "resource": "nexus:v1:meridian:group:0190f0e4-0000-7000-8000-000000000043",
                "label": "A group",
            },
        ],
        "next_cursor": None,
    }
    found = client.get("/api/people?q=vik").json()
    assert found == {
        "availability": "available",
        "items": [{"resource": PERSON, "label": "Vzorko Kvázimenný", "self": False}],
    }
    query = [c for c in nexus.calls if c[1] == "/projections/query"][-1][2]
    assert query == {
        "module": "meridian",
        "projection": "people-directory",
        "query": {"q": "vik", "limit": 10},
        "cursor": None,
    }
    added = client.post(
        f"/api/events/{event['id']}/people", json={"resource": PERSON, "label": "Vzorko Kvázimenný"}
    )
    assert added.status_code == 201, added.text
    link = next(x for x in added.json()["links"] if x["relation"] == "chronos.involves")
    assert link["target"] == PERSON and link["label"] == "Vzorko Kvázimenný"
    assert (
        client.post(f"/api/events/{event['id']}/people", json={"resource": PERSON}).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/events/{event['id']}/people",
            json={"resource": "nexus:v1:meridian:group:0190f0e4-0000-7000-8000-000000000043"},
        ).status_code
        == 422
    )
    app.state.worker.flush(force=True)
    posted = [c[2] for c in nexus.calls if c[1] == "/references"][-1]
    assert posted == {
        "source": event["reference"],
        "target": PERSON,
        "relation": "chronos.involves",
        "metadata": {},
        "readers": ["meridian"],
    }
    links = client.get(f"/api/events/{event['id']}/links").json()["links"]
    assert links[0]["relation"] == "chronos.involves" and links[0]["label"] == "Live label"
    # Meridian, as a reader, may resolve the event title for the person's profile.
    resolved = client.post(
        "/empyrean/v1/resources/resolve",
        headers=RES,
        json={"resource": event["reference"], "requester": "meridian"},
    )
    assert resolved.status_code == 200 and resolved.json()["label"] == "Lunch"
    edges = client.get("/empyrean/v1/references/outgoing", headers=RES).json()["references"]
    assert [e["relation"] for e in edges] == ["chronos.involves"]
    client.delete(f"/api/events/{event['id']}/links/{link['id']}")
    assert client.get(f"/api/events/{event['id']}").json()["links"] == []


def test_people_picker_reports_why_it_is_empty(env):
    client, _, nexus, _ = env
    assert client.get("/api/people?q=a").json() == {
        "availability": "module_uninstalled",
        "items": [],
    }
    nexus.directory = {"availability": "not_provided"}
    assert client.get("/api/people").json()["availability"] == "not_provided"
    nexus.fail = httpx.ConnectError("down")
    assert client.get("/api/people").json()["availability"] == "nexus_unreachable"


def test_people_cannot_be_added_to_read_only_events(env):
    client, app, _, _ = env
    cal = native(client)
    event = client.post(
        "/api/events",
        json={
            "calendar_id": cal["id"],
            "title": "Feed copy",
            "start": "2026-11-20T12:00",
            "end": "2026-11-20T13:00",
            "time_zone": "Europe/Bratislava",
        },
    ).json()
    with app.state.db.connect() as conn:  # as if it came from an imported or subscribed calendar
        conn.execute("UPDATE events SET origin='import' WHERE id=?", (event["id"],))
    assert (
        client.post(f"/api/events/{event['id']}/people", json={"resource": PERSON}).status_code
        == 409
    )
    missing = "0190f0e4-0000-7000-8000-0000000000aa"
    assert (
        client.post(f"/api/events/{missing}/people", json={"resource": PERSON}).status_code == 404
    )


# ── 0.3.0: backlinks standard and Places from Atlas ────────────────────
PLACE = "nexus:v1:atlas:place:0190f0e4-0000-7000-8000-00000000000c"
INTERACTION = "nexus:v1:meridian:interaction:0190f0e4-0000-7000-8000-00000000000d"
GONE = "nexus:v1:meridian:interaction:0190f0e4-0000-7000-8000-00000000000e"


def _lunch(client):
    return client.post(
        "/api/events",
        json={
            "calendar_id": native(client)["id"],
            "title": "Lunch",
            "start": "2026-12-01T12:00",
            "end": "2026-12-01T13:00",
            "time_zone": "Europe/Bratislava",
        },
    ).json()


def test_backlinks_follow_the_standard(env):
    client, _, nexus, _ = env
    event = _lunch(client)
    original = nexus.request

    def request(method, path, body=None):
        if path.startswith("/references?"):
            assert "direction=incoming" in path
            return {
                "references": [
                    {"source": INTERACTION, "relation": "meridian.interaction-about"},
                    {"source": GONE, "relation": "meridian.interaction-about"},
                    {"source": f"nexus:v1:chronos:event:{event['id']}", "relation": "chronos.self"},
                ]
            }
        if path == "/resources/resolve" and body["resource"] == GONE:
            return {"availability": "deleted"}
        return original(method, path, body)

    nexus.request = request
    got = client.get(f"/api/events/{event['id']}/linked-from").json()
    assert got["availability"] == "available"
    assert [(x["module"], x["type"], x["label"], x["availability"]) for x in got["items"]] == [
        ("meridian", "interaction", "Live label", "available"),
        ("meridian", "interaction", "", "deleted"),
    ]
    nexus.request = original
    nexus.fail = httpx.ConnectError("down")
    assert client.get(f"/api/events/{event['id']}/linked-from").json() == {
        "availability": "nexus_unreachable",
        "items": [],
    }


def test_a_place_from_atlas_is_linked_and_shared_with_atlas(env):
    client, app, nexus, _ = env
    event = _lunch(client)
    assert client.post(
        f"/api/events/{event['id']}/places", json={"resource": "nexus:v1:lyra:movie:x", "label": "No"}
    ).status_code == 422  # fmt: skip
    added = client.post(f"/api/events/{event['id']}/places", json={"resource": PLACE, "label": "Bistro"})
    assert added.status_code == 201, added.text
    link = next(x for x in added.json()["links"] if x["relation"] == "chronos.at")
    assert link["target"] == PLACE
    assert client.post(f"/api/events/{event['id']}/places", json={"resource": PLACE, "label": "Bistro"}).status_code == 409
    out = client.get("/empyrean/v1/references/outgoing", headers=RES).json()["references"]
    assert [x["readers"] for x in out if x["target"] == PLACE] == [["atlas"]]
    # Atlas may now read the event's label, because the link is shared with it.
    resolved = client.post("/empyrean/v1/resources/resolve", headers=RES,
                           json={"resource": f"nexus:v1:chronos:event:{event['id']}", "requester": "atlas"})  # fmt: skip
    assert resolved.status_code == 200 and resolved.json()["label"] == "Lunch"


def test_link_search_returns_labels_and_grants_only_that_module(env):
    client, _, _, _ = env
    event = _lunch(client)
    ask = lambda q: client.post("/empyrean/v1/projections/link-search", headers=RES, json={"requester": "meridian", "query": {"q": q}})  # noqa: E731
    assert client.post("/empyrean/v1/projections/link-search", json={"requester": "meridian", "query": {}}).status_code == 403
    ref = f"nexus:v1:chronos:event:{event['id']}"
    resolve = lambda who: client.post("/empyrean/v1/resources/resolve", headers=RES, json={"resource": ref, "requester": who})  # noqa: E731
    assert resolve("meridian").status_code == 403  # nothing shared yet
    found = ask("lun").json()["items"]
    assert found == [{"resource": ref, "label": "Lunch · 2026-12-01"}]
    assert ask("nothing").json()["items"] == []
    assert resolve("meridian").status_code == 200
    assert resolve("lyra").status_code == 403
