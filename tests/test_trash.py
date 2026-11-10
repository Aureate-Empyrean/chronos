"""Recoverable deletion (Trash): behaviour, recurrence, integrations and migration.

All data is synthetic. Occurrence keys are the canonical UTC instant or ISO date."""
# ruff: noqa: F811 (the shared `env` fixture is imported, then named as a test argument)

import hashlib
import json
import sqlite3
import threading

import httpx
import pytest
from chronos import trash as trash_module
from chronos.app import create_app
from chronos.db import MIGRATIONS, Database
from fastapi.testclient import TestClient
from test_chronos import (
    GW,
    ICS,
    KEY,
    PERSON,
    PLACE,
    RES,
    FakeNexus,
    env,  # noqa: F401
    feed_version,
    native,
    occurrences,
    subscribe,
)

WIDE = ("2026-10-01T00:00:00Z", "2026-12-31T00:00:00Z")
OCT26 = "2026-10-26T08:30:00Z"  # the second occurrence of the weekly series, after the DST change
NOV02 = "2026-11-02T08:30:00Z"


def weekly(client, **extra):
    """Mondays 09:30 in Bratislava: 19 and 26 Oct, 2 and 9 Nov 2026."""
    body = {
        "calendar_id": native(client)["id"],
        "title": "Standup",
        "description": "Bring notes",
        "location": "Room 4",
        "start": "2026-10-19T09:30",
        "end": "2026-10-19T10:00",
        "time_zone": "Europe/Bratislava",
        "rrule": "FREQ=WEEKLY;COUNT=4",
        **extra,
    }
    response = client.post("/api/events", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def single(client, title="Dentist", **extra):
    response = client.post(
        "/api/events",
        json={
            "calendar_id": native(client)["id"],
            "title": title,
            "description": "Check-up",
            "location": "Old town 5",
            "start": "2026-11-20T10:00",
            "end": "2026-11-20T11:00",
            "time_zone": "Europe/Bratislava",
            **extra,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def starts(client):
    return sorted(o["start"] for o in occurrences(client, *WIDE) if o["title"] != "x")


def trash_items(client, q=""):
    return client.get("/api/trash", params={"q": q}).json()["items"]


def edit(client, event, **changes):
    body = {
        "calendar_id": event["calendar_id"],
        "title": event["title"],
        "start": event["start_local"],
        "end": event["end_local"],
        "time_zone": event["time_zone"],
        "rrule": event["rrule"],
        **changes,
    }
    response = client.put(f"/api/events/{event['id']}", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def rows(app, sql, *params):
    with app.state.db.connect() as conn:
        return conn.execute(sql, params).fetchall()


# ── Deleting and restoring ───────────────────────────────────────────


def test_deleted_event_leaves_every_view_and_comes_back_identical(env):
    client, app, _, _ = env
    category = client.post("/api/categories", json={"name": "Health", "color": "#8FC2A9"}).json()
    event = single(client, category_id=category["id"])
    assert native(client)["event_count"] == 1
    assert client.get("/api/state").json()["trash_count"] == 0

    deleted = client.delete(f"/api/events/{event['id']}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] == "event"

    assert occurrences(client, *WIDE) == []
    assert client.get("/api/search?q=dentist").json()["events"] == []
    assert client.get(f"/api/events/{event['id']}").status_code == 410
    assert native(client)["event_count"] == 0
    assert client.get("/api/state").json()["trash_count"] == 1

    items = trash_items(client)
    assert len(items) == 1
    item = items[0]
    assert item["id"] == deleted.json()["trash"]
    assert (item["kind"], item["event_id"], item["title"]) == ("event", event["id"], "Dentist")
    assert item["deleted_at"].endswith("Z") and item["blocked"] is None
    detail = client.get(f"/api/trash/{item['id']}").json()
    assert detail["description"] == "Check-up"
    assert detail["category_name"] == "Health"
    assert detail["created_at"] == event["created_at"]

    restored = client.post(f"/api/trash/{item['id']}/restore")
    assert restored.status_code == 200 and restored.json()["restored"] == "event"
    again = client.get(f"/api/events/{event['id']}").json()
    assert {k: v for k, v in again.items() if k != "links"} == {
        k: v for k, v in event.items() if k != "links"
    }
    assert [o["event_id"] for o in occurrences(client, *WIDE)] == [event["id"]]
    assert trash_items(client) == []


def test_undo_uses_the_id_returned_by_delete(env):
    client, _, _, _ = env
    event = single(client)
    entry = client.delete(f"/api/events/{event['id']}").json()["trash"]
    assert client.post(f"/api/trash/{entry}/restore").status_code == 200
    assert [o["event_id"] for o in occurrences(client, *WIDE)] == [event["id"]]


def test_restoring_twice_cannot_create_a_second_event(env):
    client, app, _, _ = env
    event = single(client)
    entry = client.delete(f"/api/events/{event['id']}").json()["trash"]
    assert client.post(f"/api/trash/{entry}/restore").status_code == 200
    assert client.post(f"/api/trash/{entry}/restore").status_code == 404
    assert rows(app, "SELECT count(*) FROM events")[0][0] == 1
    assert len(occurrences(client, *WIDE)) == 1


def test_concurrent_restores_of_one_entry_succeed_exactly_once(env):
    client, app, _, _ = env
    event = single(client)
    entry = client.delete(f"/api/events/{event['id']}").json()["trash"]
    outcomes = []

    def attempt():
        try:
            with app.state.db.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                trash_module.restore(conn, trash_module.get(conn, entry))
            outcomes.append("restored")
        except trash_module.TrashError:
            outcomes.append("refused")

    threads = [threading.Thread(target=attempt) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert outcomes.count("restored") == 1 and outcomes.count("refused") == 7
    assert rows(app, "SELECT count(*) FROM events WHERE trashed_at IS NULL")[0][0] == 1


def test_an_event_in_trash_cannot_be_changed(env):
    client, _, _, _ = env
    event = single(client)
    client.delete(f"/api/events/{event['id']}")
    eid = event["id"]
    assert client.put(f"/api/events/{eid}", json={
        "calendar_id": event["calendar_id"], "title": "x",
        "start": "2026-11-20T10:00", "end": "2026-11-20T11:00",
    }).status_code == 410  # fmt: skip
    assert client.delete(f"/api/events/{eid}").status_code == 410
    assert (
        client.post(
            f"/api/events/{eid}/copy", json={"calendar_id": event["calendar_id"]}
        ).status_code
        == 410
    )
    assert client.post(f"/api/events/{eid}/people", json={"resource": PERSON}).status_code == 410
    assert client.post(f"/api/events/{eid}/places", json={"resource": PLACE}).status_code == 410
    assert client.get(f"/api/events/{eid}/links").status_code == 410


def test_delete_is_refused_for_events_chronos_does_not_own(env):
    client, app, _, _ = env
    event = single(client)
    with app.state.db.connect() as conn:
        conn.execute("UPDATE events SET origin='subscription' WHERE id=?", (event["id"],))
    assert client.delete(f"/api/events/{event['id']}").status_code == 409
    assert trash_items(client) == []


def test_lookup_answers_for_deep_links(env):
    client, _, _, _ = env
    event, series = single(client), weekly(client)
    entry = client.delete(f"/api/events/{event['id']}").json()["trash"]
    ask = lambda eid, o="": client.get(  # noqa: E731
        "/api/trash/lookup", params={"event_id": eid, "occurrence": o}
    )  # noqa: E731
    assert ask(event["id"]).json()["id"] == entry
    assert ask(series["id"], OCT26).status_code == 404  # active series, active occurrence
    occurrence = client.delete(f"/api/events/{series['id']}", params={"occurrence": OCT26}).json()
    assert ask(series["id"], OCT26).json()["id"] == occurrence["trash"]
    whole = client.delete(f"/api/events/{series['id']}", params={"scope": "series"}).json()
    assert ask(series["id"], NOV02).json()["id"] == whole["trash"]  # the series is in Trash
    missing = "0190f0e4-0000-7000-8000-0000000000bb"
    assert ask(missing).status_code == 404


# ── Permanent deletion ───────────────────────────────────────────────


def test_permanent_delete_needs_trash_and_confirmation(env):
    client, app, _, _ = env
    event = single(client)
    assert client.delete(f"/api/trash/{event['id']}?confirmed=true").status_code == 404  # active
    entry = client.delete(f"/api/events/{event['id']}").json()["trash"]
    assert client.delete(f"/api/trash/{entry}").status_code == 422
    assert client.get(f"/api/trash/{entry}").status_code == 200
    assert client.delete(f"/api/trash/{entry}?confirmed=true").json() == {"purged": "event"}
    assert client.get(f"/api/events/{event['id']}").status_code == 404
    assert client.get(f"/api/trash/{entry}").status_code == 404
    assert rows(app, "SELECT kind FROM tombstones WHERE id=?", event["id"])[0]["kind"] == "event"
    audit = [dict(r) for r in rows(app, "SELECT * FROM trash_audit ORDER BY seq")]
    assert [a["action"] for a in audit] == ["trash", "purge"]
    assert "Dentist" not in json.dumps(audit)  # ids and times only, never content


def test_empty_trash_has_safeguards_and_keeps_active_events(env):
    client, app, _, _ = env
    keep, gone = single(client, "Keep"), single(client, "Gone")
    series = weekly(client)
    client.delete(f"/api/events/{gone['id']}")
    client.delete(f"/api/events/{series['id']}", params={"occurrence": OCT26})
    client.delete(f"/api/events/{series['id']}", params={"scope": "series"})
    assert len(trash_items(client)) == 3
    assert (
        client.post("/api/trash/empty", json={"confirmed": False, "expected": 3}).status_code == 422
    )
    assert client.post("/api/trash/empty", json={"expected": 3}).status_code == 422
    assert (
        client.post("/api/trash/empty", json={"confirmed": True, "expected": 2}).status_code == 409
    )
    assert len(trash_items(client)) == 3
    assert client.post("/api/trash/empty", json={"confirmed": True, "expected": 3}).json() == {
        "purged": 3
    }
    assert trash_items(client) == []
    assert [o["event_id"] for o in occurrences(client, *WIDE)] == [keep["id"]]
    assert rows(app, "SELECT count(*) FROM events")[0][0] == 1
    # Each permanently deleted event still resolves as deleted.
    assert rows(app, "SELECT count(*) FROM tombstones WHERE kind='event'")[0][0] == 2


def test_nothing_is_purged_automatically(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_RESOLVER_KEY", KEY)
    first = create_app(tmp_path, nexus=FakeNexus(), workers=False)
    with TestClient(first, headers=GW) as client:
        event = single(client)
        client.delete(f"/api/events/{event['id']}")
        with first.state.db.connect() as conn:
            conn.execute("UPDATE trash SET deleted_at='2001-01-01T00:00:00Z'")
    second = create_app(tmp_path, nexus=FakeNexus(), workers=False)
    with TestClient(second, headers=GW) as client:
        second.state.worker.tick()
        assert [i["event_id"] for i in trash_items(client)] == [event["id"]]


# ── Recurrence ───────────────────────────────────────────────────────


def test_one_occurrence_never_deletes_the_series(env):
    client, app, _, _ = env
    series = weekly(client)
    # A repeating event needs an explicit target.
    assert client.delete(f"/api/events/{series['id']}").status_code == 422
    assert (
        client.delete(f"/api/events/{series['id']}", params={"occurrence": ""}).status_code == 422
    )
    assert len(occurrences(client, *WIDE)) == 4

    result = client.delete(f"/api/events/{series['id']}", params={"occurrence": OCT26})
    assert result.json()["deleted"] == "occurrence"
    assert OCT26 not in starts(client) and len(starts(client)) == 3
    item = trash_items(client)[0]
    assert (item["kind"], item["occurrence"], item["start"]) == ("occurrence", OCT26, OCT26)
    assert client.get(f"/api/events/{series['id']}").json()["exdates"] == [OCT26]


def test_occurrence_delete_rejects_keys_the_series_does_not_produce(env):
    client, _, _, _ = env
    series, plain = weekly(client), single(client)
    for bad in ("2026-10-27T08:30:00Z", "garbage", "2026-10-26"):
        assert (
            client.delete(f"/api/events/{series['id']}", params={"occurrence": bad}).status_code
            == 422
        )
    assert (
        client.delete(f"/api/events/{plain['id']}", params={"occurrence": OCT26}).status_code == 422
    )
    assert trash_items(client) == []


def test_repeating_a_delete_makes_one_entry(env):
    client, app, _, _ = env
    series = weekly(client)
    first = client.delete(f"/api/events/{series['id']}", params={"occurrence": OCT26}).json()
    second = client.delete(f"/api/events/{series['id']}", params={"occurrence": OCT26}).json()
    assert first["trash"] == second["trash"]
    assert rows(app, "SELECT count(*) FROM trash")[0][0] == 1


def test_restoring_an_occurrence_removes_only_its_own_exclusion(env):
    client, _, _, _ = env
    series = weekly(client)
    one = client.delete(f"/api/events/{series['id']}", params={"occurrence": OCT26}).json()
    client.delete(f"/api/events/{series['id']}", params={"occurrence": NOV02})
    assert client.post(f"/api/trash/{one['trash']}/restore").json()["restored"] == "occurrence"
    assert OCT26 in starts(client) and NOV02 not in starts(client)
    assert client.get(f"/api/events/{series['id']}").json()["exdates"] == [NOV02]
    assert [i["occurrence"] for i in trash_items(client)] == [NOV02]


def test_concurrent_occurrence_deletes_are_all_kept(env):
    client, app, _, _ = env
    series = weekly(client, rrule="FREQ=DAILY;COUNT=30")
    keys = [o["occurrence"] for o in occurrences(client, *WIDE)][:12]

    def remove(key):
        with app.state.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM events WHERE id=?", (series["id"],)).fetchone()
            trash_module.move_occurrence(conn, row, key)

    threads = [threading.Thread(target=remove, args=(k,)) for k in keys]
    [t.start() for t in threads]
    [t.join() for t in threads]
    event = client.get(f"/api/events/{series['id']}").json()
    assert sorted(event["exdates"]) == sorted(keys)
    assert len(trash_items(client)) == 12


def test_all_day_occurrences_use_date_keys(env):
    client, _, _, _ = env
    series = client.post("/api/events", json={
        "calendar_id": native(client)["id"], "title": "Bins", "all_day": True,
        "start": "2026-11-02", "end": "2026-11-03", "rrule": "FREQ=WEEKLY;COUNT=3",
    }).json()  # fmt: skip
    entry = client.delete(f"/api/events/{series['id']}", params={"occurrence": "2026-11-09"}).json()
    assert [o["start"] for o in occurrences(client, *WIDE)] == ["2026-11-02", "2026-11-16"]
    assert trash_items(client)[0]["all_day"] is True
    client.post(f"/api/trash/{entry['trash']}/restore")
    assert len(occurrences(client, *WIDE)) == 3


def test_series_goes_and_returns_whole_with_rule_and_exclusions(env):
    client, _, _, _ = env
    series = weekly(client)
    occurrence = client.delete(f"/api/events/{series['id']}", params={"occurrence": OCT26}).json()
    entry = client.delete(f"/api/events/{series['id']}", params={"scope": "series"}).json()["trash"]
    assert occurrences(client, *WIDE) == []
    kinds = {i["id"]: i for i in trash_items(client)}
    assert kinds[entry]["kind"] == "series" and kinds[entry]["rrule"] == "FREQ=WEEKLY;COUNT=4"
    assert kinds[occurrence["trash"]]["blocked"] == "series_in_trash"
    refused = client.post(f"/api/trash/{occurrence['trash']}/restore")
    assert refused.status_code == 409 and "series first" in refused.json()["detail"]

    assert client.post(f"/api/trash/{entry}/restore").json()["restored"] == "series"
    after = client.get(f"/api/events/{series['id']}").json()
    assert after["rrule"] == "FREQ=WEEKLY;COUNT=4" and after["exdates"] == [OCT26]
    assert OCT26 not in starts(client) and len(starts(client)) == 3
    # The occurrence is still in Trash, and now it can come back too.
    assert client.post(f"/api/trash/{occurrence['trash']}/restore").status_code == 200
    assert OCT26 in starts(client)


def test_purging_an_occurrence_keeps_it_deleted_after_later_edits(env):
    client, _, _, _ = env
    series = weekly(client)
    entry = client.delete(f"/api/events/{series['id']}", params={"occurrence": OCT26}).json()[
        "trash"
    ]
    assert client.delete(f"/api/trash/{entry}?confirmed=true").json() == {"purged": "occurrence"}
    assert OCT26 not in starts(client)
    edited = edit(client, series, rrule="FREQ=WEEKLY;COUNT=6")
    assert OCT26 in edited["exdates"] and OCT26 not in starts(client)


def test_purging_a_series_takes_its_occurrence_entries_with_it(env):
    client, app, _, _ = env
    series = weekly(client)
    client.delete(f"/api/events/{series['id']}", params={"occurrence": OCT26})
    entry = client.delete(f"/api/events/{series['id']}", params={"scope": "series"}).json()["trash"]
    client.delete(f"/api/trash/{entry}?confirmed=true")
    assert trash_items(client) == []
    audit = [r["action"] for r in rows(app, "SELECT action FROM trash_audit ORDER BY seq")]
    assert audit == ["trash", "trash", "purge", "purge"]


def test_trashed_occurrence_stays_deleted_through_edits_and_restores_after_them(env):
    client, _, _, _ = env
    series = weekly(client)
    entry = client.delete(f"/api/events/{series['id']}", params={"occurrence": OCT26}).json()[
        "trash"
    ]
    # A new title: the occurrence stays deleted, and returns with the series' current title.
    renamed = edit(client, series, title="Daily standup")
    assert renamed["exdates"] == [OCT26]
    # A new rule with the same start: it still stays deleted.
    longer = edit(client, series, title="Daily standup", rrule="FREQ=WEEKLY;COUNT=8")
    assert longer["exdates"] == [OCT26] and OCT26 not in starts(client)
    # What Trash shows is what was deleted.
    assert trash_items(client)[0]["title"] == "Standup"
    assert client.post(f"/api/trash/{entry}/restore").json()["separate"] is False
    found = {o["start"]: o["title"] for o in occurrences(client, *WIDE)}
    assert found[OCT26] == "Daily standup"


def test_rescheduled_series_offers_a_separate_event_once(env):
    client, app, _, _ = env
    series = weekly(client)
    entry = client.delete(f"/api/events/{series['id']}", params={"occurrence": OCT26}).json()[
        "trash"
    ]
    moved = edit(client, series, start="2026-10-19T11:00", end="2026-10-19T11:30")
    assert moved["exdates"] == [OCT26]  # the reschedule did not bring anything back
    assert all(s[11:13] in {"09", "10"} for s in starts(client))  # 11:00 local, UTC+2 or +1

    item = next(i for i in trash_items(client) if i["id"] == entry)
    assert item["blocked"] == "occurrence_gone"
    refused = client.post(f"/api/trash/{entry}/restore")
    assert refused.status_code == 409 and "separate event" in refused.json()["detail"]
    assert len(trash_items(client)) == 1

    series_before = dict(rows(app, "SELECT rrule,start FROM events WHERE id=?", series["id"])[0])
    result = client.post(f"/api/trash/{entry}/restore", json={"as_separate": True})
    assert result.status_code == 200 and result.json()["separate"] is True
    assert result.json()["event_id"] == entry
    separate = client.get(f"/api/events/{entry}").json()
    assert (separate["title"], separate["rrule"], separate["start"]) == ("Standup", None, OCT26)
    assert separate["location"] == "Room 4"
    assert client.post(f"/api/trash/{entry}/restore", json={"as_separate": True}).status_code == 404
    assert rows(app, "SELECT count(*) FROM events WHERE id=?", entry)[0][0] == 1
    assert (
        dict(rows(app, "SELECT rrule,start FROM events WHERE id=?", series["id"])[0])
        == series_before
    )


def test_series_turned_into_a_single_event_does_not_vanish(env):
    client, _, _, _ = env
    series = weekly(client)
    first = "2026-10-19T07:30:00Z"
    entry = client.delete(f"/api/events/{series['id']}", params={"occurrence": first}).json()[
        "trash"
    ]
    assert first not in starts(client)
    single_now = edit(client, series, rrule=None)
    assert single_now["exdates"] == [] and starts(client) == [first]
    # Its key is the event's own start, so restoring has nothing to change and nothing to add.
    assert client.post(f"/api/trash/{entry}/restore").json()["separate"] is False
    assert starts(client) == [first]


def test_occurrence_keys_survive_dst_on_restore(env):
    client, _, _, _ = env
    series = weekly(client)
    # 19 Oct is CEST (07:30Z), 26 Oct is already CET (08:30Z): the keys differ by an hour.
    summer = "2026-10-19T07:30:00Z"
    a = client.delete(f"/api/events/{series['id']}", params={"occurrence": summer}).json()["trash"]
    b = client.delete(f"/api/events/{series['id']}", params={"occurrence": OCT26}).json()["trash"]
    client.post(f"/api/trash/{a}/restore")
    client.post(f"/api/trash/{b}/restore")
    assert starts(client) == [summer, OCT26, NOV02, "2026-11-09T08:30:00Z"]


# ── Import, subscriptions and integrations ───────────────────────────


def test_imported_events_stay_read_only_and_out_of_trash(env):
    client = env[0]
    result = client.post("/api/import", json={"content": ICS, "filename": "f.ics"}).json()
    found = next(o for o in occurrences(client, *WIDE) if o["title"] == "Grand Prix")
    assert client.delete(f"/api/events/{found['event_id']}").status_code == 409
    assert trash_items(client) == []
    again = client.post(
        "/api/import", json={"content": ICS, "calendar_id": result["calendar"]["id"]}
    )
    assert (again.json()["created"], again.json()["updated"]) == (0, 0)


def as_if_trashed(app, event_id):
    """Trash is native-only today: this states directly what the sources must respect."""
    with app.state.db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        return trash_module.move_event(conn, row)


def test_import_cannot_resurrect_or_duplicate_a_trashed_record(env):
    client, app, _, _ = env
    result = client.post("/api/import", json={"content": ICS, "filename": "f.ics"}).json()
    cid = result["calendar"]["id"]
    found = next(o for o in occurrences(client, *WIDE) if o["title"] == "Grand Prix")
    as_if_trashed(app, found["event_id"])
    preview = client.post("/api/import/preview", json={"content": ICS, "calendar_id": cid}).json()
    assert preview["already_in_target"] == 5
    changed = ICS.replace("SUMMARY:Grand Prix", "SUMMARY:Grand Prix (changed)")
    again = client.post("/api/import", json={"content": changed, "calendar_id": cid}).json()
    assert (again["created"], again["updated"], again["unchanged"]) == (0, 0, 6)
    titles = [o["title"] for o in occurrences(client, *WIDE)]
    assert "Grand Prix" not in titles and "Grand Prix (changed)" not in titles
    assert rows(app, "SELECT title FROM events WHERE id=?", found["event_id"])[0][0] == "Grand Prix"
    assert (
        rows(app, "SELECT count(*) FROM events WHERE calendar_id=? AND source_uid=?", cid,
             "race-1@example.com")[0][0] == 1
    )  # fmt: skip


def test_subscription_refresh_leaves_a_trashed_record_alone(env):
    client, app, _, feed = env
    feed.body = feed_version(
        ("r1", "20261108T130000Z", "Brazil"), ("r2", "20261122T040000Z", "Vegas")
    )
    calendar = subscribe(client).json()
    worker = app.state.worker
    worker.sync_subscription(calendar["id"])
    vegas = next(o for o in occurrences(client, *WIDE) if o["title"] == "Vegas")
    as_if_trashed(app, vegas["event_id"])
    # Changed in the feed, then dropped from it: neither brings it back or destroys it.
    feed.body = feed_version(
        ("r1", "20261108T130000Z", "Brazil"), ("r2", "20261122T050000Z", "Vegas 2")
    )
    assert worker.sync_subscription(calendar["id"])["counts"]["created"] == 0
    assert "Vegas 2" not in [o["title"] for o in occurrences(client, *WIDE)]
    feed.body = feed_version(("r1", "20261108T140000Z", "Brazil moved"))
    assert worker.sync_subscription(calendar["id"])["counts"]["removed"] == 0
    assert rows(app, "SELECT trashed_at FROM events WHERE id=?", vegas["event_id"])[0][0]


def test_resolver_and_link_search_stop_seeing_trash_and_links_return(env):
    client, app, nexus, _ = env
    event = single(client, "Lunch")
    client.post(f"/api/events/{event['id']}/people", json={"resource": PERSON, "label": "Vik"})
    ref = event["reference"]
    resolve = lambda who="meridian": client.post(  # noqa: E731
        "/empyrean/v1/resources/resolve", headers=RES, json={"resource": ref, "requester": who}
    )
    search = lambda: client.post(  # noqa: E731
        "/empyrean/v1/projections/link-search", headers=RES,
        json={"requester": "atlas", "query": {"q": "lun"}},
    ).json()["items"]  # fmt: skip
    outgoing = lambda: client.get(  # noqa: E731
        "/empyrean/v1/references/outgoing", headers=RES
    ).json()["references"]
    assert resolve().status_code == 200 and len(search()) == 1 and len(outgoing()) == 1
    app.state.worker.flush(force=True)
    nexus.calls.clear()

    entry = client.delete(f"/api/events/{event['id']}").json()["trash"]
    assert resolve().status_code == 404 and search() == [] and outgoing() == []
    app.state.worker.flush(force=True)
    assert ("DELETE", "/references/remote-1", None) in nexus.calls
    detail = client.get(f"/api/trash/{entry}").json()
    assert [link["label"] for link in detail["links"]] == ["Vik"]  # the relationship is kept

    nexus.calls.clear()
    client.post(f"/api/trash/{entry}/restore")
    assert resolve().status_code == 200 and len(outgoing()) == 1
    app.state.worker.flush(force=True)
    posted = [c for c in nexus.calls if c[1] == "/references"]
    assert posted[0][2]["source"] == ref and posted[0][2]["target"] == PERSON
    assert resolve("atlas").status_code == 200  # an earlier link-search grant still holds
    links = client.get(f"/api/events/{event['id']}").json()["links"]
    assert links[0]["label"] == "Vik" and links[0]["id"]
    assert rows(app, "SELECT remote_id FROM links")[0][0] == "remote-1"


def test_purged_event_resolves_as_deleted(env):
    client, _, _, _ = env
    event = single(client)
    entry = client.delete(f"/api/events/{event['id']}").json()["trash"]
    client.delete(f"/api/trash/{entry}?confirmed=true")
    gone = client.post(
        "/empyrean/v1/resources/resolve", headers=RES,
        json={"resource": event["reference"], "requester": "lyra"},
    )  # fmt: skip
    assert gone.status_code == 410


def test_edge_published_while_trashing_is_taken_back_down(env):
    client, app, nexus, _ = env
    event = single(client, "Lunch")
    client.post(f"/api/events/{event['id']}/people", json={"resource": PERSON, "label": "Vik"})
    original = nexus.request

    def trashed_mid_flight(method, path, body=None):
        result = original(method, path, body)
        if method == "POST" and path == "/references":
            client.delete(f"/api/events/{event['id']}")
        return result

    nexus.request = trashed_mid_flight
    app.state.worker.flush(force=True)
    nexus.request = original
    app.state.worker.flush(force=True)
    assert ("DELETE", "/references/remote-1", None) in nexus.calls
    assert rows(app, "SELECT remote_id FROM links")[0][0] is None
    assert rows(app, "SELECT count(*) FROM outbox")[0][0] == 0


def test_trashing_cancels_an_unsent_publication(env):
    client, app, nexus, _ = env
    event = single(client, "Lunch")
    client.post(f"/api/events/{event['id']}/people", json={"resource": PERSON, "label": "Vik"})
    client.delete(f"/api/events/{event['id']}")
    app.state.worker.flush(force=True)
    assert [c for c in nexus.calls if c[1] == "/references"] == []


def test_linked_from_still_answers_in_trash_for_the_purge_warning(env):
    client, _, nexus, _ = env
    event = single(client, "Lunch")
    client.delete(f"/api/events/{event['id']}")
    response = client.get(f"/api/events/{event['id']}/linked-from")
    assert response.status_code == 200 and response.json()["availability"] == "available"
    nexus.fail = httpx.ConnectError("down")
    assert client.get(f"/api/events/{event['id']}/linked-from").json()["availability"] == (
        "nexus_unreachable"
    )


# ── Calendars ────────────────────────────────────────────────────────


def second_calendar(client):
    return client.post("/api/calendars", json={"name": "Work", "color": "#7AA7EB"}).json()


def test_deleting_a_calendar_keeps_its_events_recoverable(env):
    client, app, _, _ = env
    work = second_calendar(client)
    a = single(client, "A", calendar_id=work["id"])
    series = weekly(client, calendar_id=work["id"])
    earlier = single(client, "Earlier", calendar_id=work["id"])
    client.delete(f"/api/events/{earlier['id']}")
    assert client.delete(f"/api/calendars/{work['id']}").status_code == 422  # needs confirmation
    result = client.delete(f"/api/calendars/{work['id']}?confirmed=true").json()
    assert result["trash"]["count"] == 2
    state = client.get("/api/state").json()
    assert [c["name"] for c in state["calendars"]] == ["Personal"]
    assert occurrences(client, *WIDE) == []
    assert client.post("/api/events", json={
        "calendar_id": work["id"], "title": "x", "start": "2026-11-20T10:00", "end": "2026-11-20T11:00",
    }).status_code == 404  # fmt: skip
    items = trash_items(client)
    assert len(items) == 3 and sum(i["calendar"]["deleted"] for i in items) == 3

    restored = client.post(f"/api/trash/batches/{result['trash']['batch']}/restore").json()
    assert restored == {"restored": 2, "calendar_restored": True}
    assert {c["name"] for c in client.get("/api/state").json()["calendars"]} == {"Personal", "Work"}
    assert {o["event_id"] for o in occurrences(client, *WIDE)} == {a["id"], series["id"]}
    # What was deleted separately before stays in Trash.
    assert [i["event_id"] for i in trash_items(client)] == [earlier["id"]]


def test_restoring_one_event_brings_its_calendar_back(env):
    client, _, _, _ = env
    work = second_calendar(client)
    a = single(client, "A", calendar_id=work["id"])
    b = single(client, "B", calendar_id=work["id"])
    client.delete(f"/api/calendars/{work['id']}?confirmed=true")
    entry = next(i for i in trash_items(client) if i["event_id"] == a["id"])
    assert client.post(f"/api/trash/{entry['id']}/restore").json()["calendar_restored"] is True
    assert {c["name"] for c in client.get("/api/state").json()["calendars"]} == {"Personal", "Work"}
    assert [o["event_id"] for o in occurrences(client, *WIDE)] == [a["id"]]
    assert [i["event_id"] for i in trash_items(client)] == [b["id"]]


def test_a_deleted_calendar_goes_for_good_with_its_last_event(env):
    client, app, _, _ = env
    work = second_calendar(client)
    single(client, "A", calendar_id=work["id"])
    client.delete(f"/api/calendars/{work['id']}?confirmed=true")
    assert rows(app, "SELECT count(*) FROM calendars WHERE id=?", work["id"])[0][0] == 1
    client.post("/api/trash/empty", json={"confirmed": True, "expected": 1})
    assert rows(app, "SELECT count(*) FROM calendars WHERE id=?", work["id"])[0][0] == 0
    assert rows(app, "SELECT kind FROM tombstones WHERE id=?", work["id"])[0][0] == "calendar"


def test_calendar_rules_stay(env):
    client, _, _, _ = env
    assert client.delete(f"/api/calendars/{native(client)['id']}?confirmed=true").status_code == 409
    empty = second_calendar(client)
    assert client.delete(f"/api/calendars/{empty['id']}?confirmed=true").json() == {"deleted": True}
    imported = client.post("/api/import", json={"content": ICS, "filename": "f.ics"}).json()
    cid = imported["calendar"]["id"]
    assert client.delete(f"/api/calendars/{cid}?confirmed=true").json() == {"deleted": True}
    assert trash_items(client) == []


# ── Listing and search ───────────────────────────────────────────────


def test_trash_search_is_accent_and_case_insensitive_and_literal(env):
    client, _, _, _ = env
    single(client, "Kaviareň s Táňou", location="Nám. SNP")
    single(client, "100% done")
    for event in occurrences(client, *WIDE):
        client.delete(f"/api/events/{event['event_id']}")
    assert [i["title"] for i in trash_items(client, "kaviaren tanou")] == ["Kaviareň s Táňou"]
    assert [i["title"] for i in trash_items(client, "nam snp")] == ["Kaviareň s Táňou"]
    assert [i["title"] for i in trash_items(client, "100%")] == ["100% done"]
    assert trash_items(client, "%") == [next(i for i in trash_items(client) if "%" in i["title"])]
    assert trash_items(client, "nothing here") == []
    found = client.get("/api/trash", params={"q": "personal"}).json()  # the calendar's name
    assert found["matched"] == 2 and found["total"] == 2


def test_trash_pages_are_complete_and_stable(env):
    client, _, _, _ = env
    for n in range(7):
        event = single(client, f"Item {n}")
        client.delete(f"/api/events/{event['id']}")
    seen, cursor = [], ""
    while True:
        page = client.get("/api/trash", params={"limit": 3, "cursor": cursor}).json()
        seen += [i["title"] for i in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert seen == [f"Item {n}" for n in range(6, -1, -1)]  # newest first, no gaps or repeats


# ── Authorization ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/trash"),
        ("GET", "/api/trash/lookup?event_id=x"),
        ("GET", "/api/trash/x"),
        ("POST", "/api/trash/x/restore"),
        ("POST", "/api/trash/batches/x/restore"),
        ("POST", "/api/trash/empty"),
        ("DELETE", "/api/trash/x?confirmed=true"),
    ],
)
def test_trash_requires_the_gateway_key(env, method, path):
    client = env[0]
    assert client.request(method, path, headers={"x-nexus-gateway-key": "wrong"}).status_code == 403
    assert client.request(method, path, headers={"x-nexus-gateway-key": ""}).status_code == 403


def test_the_resolver_key_does_not_open_the_owner_api(env):
    client = env[0]
    response = client.get("/api/trash", headers={**RES, "x-nexus-gateway-key": "wrong"})
    assert response.status_code == 403


# ── Migration and backup ─────────────────────────────────────────────

OLD_COLUMNS = (
    "id,calendar_id,origin,title,description,location,all_day,start,end,time_zone,rrule,exdates,"
    "recurrence_id,status,category_id,color,source_uid,sequence,content_hash,range_start,"
    "range_end,created_at,updated_at"
)
STAMP = "2026-11-01T10:00:00Z"
CAL = "0190f0e4-0000-7000-8000-00000000c001"
SUB = "0190f0e4-0000-7000-8000-00000000c002"
EVT = "0190f0e4-0000-7000-8000-00000000e00{}"


def build_v2(path):
    """A database as Chronos 0.5.0 left it: two migrations applied, synthetic content."""
    db = sqlite3.connect(path)
    db.execute("PRAGMA foreign_keys=ON")
    for index, script in enumerate(MIGRATIONS[:2]):
        db.executescript("BEGIN;\n" + script + f"\nPRAGMA user_version={index + 1}; COMMIT;")
    db.execute(
        "INSERT INTO calendars(id,kind,name,color,created_at,updated_at) VALUES(?,?,?,?,?,?)",
        (CAL, "native", "Personal", "#7AA7EB", STAMP, STAMP),
    )
    db.execute(
        "INSERT INTO calendars(id,kind,name,color,created_at,updated_at) VALUES(?,?,?,?,?,?)",
        (SUB, "import", "Imported", "#8FC2A9", STAMP, STAMP),
    )
    db.execute(
        "INSERT INTO categories(id,name,color,created_at) VALUES('cat','Work','#8FC2A9',?)",
        (STAMP,),
    )
    insert = (
        "INSERT INTO events(id,calendar_id,origin,title,description,location,all_day,start,end,"
        "time_zone,rrule,exdates,recurrence_id,status,category_id,source_uid,range_start,range_end,"
        "created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
    )
    weekly_row = (EVT.format(1), CAL, "native", "Skipped before Trash", "d", "l", 0,
                  "2026-10-19T07:30:00Z", "2026-10-19T08:00:00Z", "Europe/Bratislava",
                  "FREQ=WEEKLY;COUNT=4", json.dumps([OCT26]), "", "confirmed", "cat", None,
                  "2026-10-19T07:30:00Z", "2026-11-09T09:00:00Z", STAMP, STAMP)  # fmt: skip
    plain_row = (EVT.format(2), CAL, "native", "Plain", "", "", 1, "2026-11-20", "2026-11-21", None,
                 None, "[]", "", "tentative", None, None, "2026-11-19T09:00:00Z",
                 "2026-11-21T15:00:00Z", STAMP, STAMP)  # fmt: skip
    imported_row = (EVT.format(3), SUB, "import", "Feed", "", "", 0, "2026-11-21T10:00:00Z",
                    "2026-11-21T11:00:00Z", "UTC", None, "[]", "", "confirmed", None, "uid-1",
                    "2026-11-21T10:00:00Z", "2026-11-21T11:00:00Z", STAMP, STAMP)  # fmt: skip
    for row in (weekly_row, plain_row, imported_row):
        db.execute(insert, row)
    db.execute(
        "INSERT INTO links(id,event_id,target,relation,readers,label,remote_id) VALUES(?,?,?,?,?,?,?)",
        ("link-1", EVT.format(2), PERSON, "chronos.involves", '["meridian"]', "Vik", "remote-9"),
    )
    db.execute("INSERT INTO link_grants VALUES(?,?,?)", (EVT.format(2), "atlas", STAMP))
    db.execute("INSERT INTO tombstones VALUES('old-gone','event',?)", (STAMP,))
    db.commit()
    return db


def digest(conn):
    h = hashlib.sha256()
    for table, order in (
        ("calendars", "id"), ("categories", "id"), ("links", "id"),
        ("link_grants", "event_id,requester"), ("tombstones", "id"),
    ):  # fmt: skip
        columns = {"calendars": "id,kind,name,color,visible,position,created_at,updated_at"}.get(
            table, "*"
        )
        h.update(
            repr(
                list(map(tuple, conn.execute(f"SELECT {columns} FROM {table} ORDER BY {order}")))
            ).encode()
        )
    h.update(
        repr(
            list(map(tuple, conn.execute(f"SELECT {OLD_COLUMNS} FROM events ORDER BY id")))
        ).encode()
    )
    return h.hexdigest()


def test_migration_keeps_every_event_active_and_unchanged(tmp_path):
    old = build_v2(tmp_path / "chronos.sqlite3")
    before = digest(old)
    old.close()

    db = Database(tmp_path / "chronos.sqlite3")
    with db.connect() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS) == 3
        assert digest(conn) == before
        assert (
            conn.execute("SELECT count(*) FROM events WHERE trashed_at IS NULL").fetchone()[0] == 3
        )
        assert (
            conn.execute("SELECT count(*) FROM calendars WHERE trashed_at IS NOT NULL").fetchone()[
                0
            ]
            == 0
        )
        assert conn.execute("SELECT count(*) FROM trash").fetchone()[0] == 0
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    Database(tmp_path / "chronos.sqlite3")  # running it again changes nothing
    with db.connect() as conn:
        assert digest(conn) == before


def test_old_skips_stay_skipped_and_new_lifecycle_works_on_migrated_data(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_RESOLVER_KEY", KEY)
    build_v2(tmp_path / "chronos.sqlite3").close()
    app = create_app(tmp_path, nexus=FakeNexus(), workers=False)
    with TestClient(app, headers=GW) as client:
        client.put("/api/settings", json={"time_zone": "Europe/Bratislava"})
        found = occurrences(client, *WIDE)
        assert OCT26 not in [o["start"] for o in found] and len(found) == 5
        assert trash_items(client) == []  # an old skip is not invented into Trash
        repeated = client.delete(f"/api/events/{EVT.format(1)}", params={"occurrence": OCT26})
        assert repeated.status_code == 200 and repeated.json()["trash"] is None
        entry = client.delete(f"/api/events/{EVT.format(2)}").json()["trash"]
        assert client.post(f"/api/trash/{entry}/restore").status_code == 200
        assert client.get(f"/api/events/{EVT.format(2)}").json()["links"][0]["label"] == "Vik"


def test_a_failed_migration_leaves_the_old_schema_intact(tmp_path):
    old = build_v2(tmp_path / "chronos.sqlite3")
    before = digest(old)
    old.execute("CREATE TABLE trash(blocking INTEGER)")  # makes the migration fail midway
    old.commit()
    old.close()
    with pytest.raises(sqlite3.OperationalError):
        Database(tmp_path / "chronos.sqlite3")
    check = sqlite3.connect(tmp_path / "chronos.sqlite3")
    assert check.execute("PRAGMA user_version").fetchone()[0] == 2
    columns = [r[1] for r in check.execute("PRAGMA table_info(events)")]
    assert "trashed_at" not in columns
    assert digest(check) == before


def test_newer_database_is_refused(tmp_path):
    (tmp_path / "x").mkdir()
    db = Database(tmp_path / "x" / "chronos.sqlite3")
    with db.connect() as conn:
        conn.execute(f"PRAGMA user_version={len(MIGRATIONS) + 1}")
    with pytest.raises(RuntimeError, match="newer"):
        Database(tmp_path / "x" / "chronos.sqlite3")


def _export_headers(exported):
    return {k: v for k, v in exported.headers.items() if k.lower().startswith("x-empyrean-backup-")}


def test_backup_carries_trash_and_restore_republishes_only_active_links(env):
    client, app, nexus, _ = env
    kept, gone = single(client, "Kept"), single(client, "Gone")
    for event in (kept, gone):
        client.post(f"/api/events/{event['id']}/people", json={"resource": PERSON, "label": "Vik"})
    client.delete(f"/api/events/{gone['id']}")
    exported = client.post("/empyrean/v1/backup/export", headers=RES)
    client.post("/api/trash/empty", json={"confirmed": True, "expected": 1})
    headers = _export_headers(exported)
    assert client.post("/empyrean/v1/backup/validate", headers={**RES, **headers},
                       content=exported.content).json() == {"valid": True}  # fmt: skip
    nexus.calls.clear()
    assert client.post("/empyrean/v1/backup/restore", headers={**RES, **headers},
                       content=exported.content).json() == {"restored": True}  # fmt: skip
    assert [i["event_id"] for i in trash_items(client)] == [gone["id"]]
    assert [o["event_id"] for o in occurrences(client, *WIDE)] == [kept["id"]]
    app.state.worker.flush(force=True)
    sources = [c[2]["source"] for c in nexus.calls if c[1] == "/references"]
    assert sources == [kept["reference"]]
    client.post("/empyrean/v1/backup/finalize", headers=RES)


def test_backup_from_the_previous_version_restores_and_migrates(env, tmp_path):
    client, app, _, _ = env
    build_v2(tmp_path / "old.sqlite3").close()
    artifact = (tmp_path / "old.sqlite3").read_bytes()
    headers = {
        "x-empyrean-backup-module": "chronos",
        "x-empyrean-backup-format": "chronos-sqlite",
        "x-empyrean-backup-format-version": "1",
    }
    assert client.post(
        "/empyrean/v1/backup/restore", headers={**RES, **headers}, content=artifact
    ).json() == {"restored": True}
    client.post("/empyrean/v1/backup/finalize", headers=RES)
    assert rows(app, "PRAGMA user_version")[0][0] == len(MIGRATIONS)
    assert len(occurrences(client, *WIDE)) == 5
    entry = client.delete(f"/api/events/{EVT.format(2)}").json()["trash"]
    assert client.post(f"/api/trash/{entry}/restore").status_code == 200
    assert rows(app, "SELECT count(*) FROM events WHERE id=?", EVT.format(2))[0][0] == 1
