"""Optimistic concurrency: a stale client can never silently overwrite newer data.

Real transactions on real SQLite files, with synthetic data only. Threaded tests start real
concurrent requests, so their exact winner is unknown but the outcome counts are not."""
# ruff: noqa: F811 (the shared `env` fixture is imported, then named as a test argument)

import hashlib
import json
import sqlite3
import threading

import pytest
from chronos.app import create_app
from chronos.db import MIGRATIONS, Database
from fastapi.testclient import TestClient
from test_chronos import (
    GW,
    ICS,
    KEY,
    FakeNexus,
    Feed,
    env,  # noqa: F401
    feed_version,
    native,
    occurrences,
    subscribe,
)
from test_trash import OCT26, WIDE, build_v2, single, weekly


def body_of(event, **changes):
    if event["all_day"]:
        start, end = event["start"], event["end"]
    else:
        start, end = event["start_local"], event["end_local"]
    return {
        "calendar_id": event["calendar_id"],
        "title": event["title"],
        "description": event["description"],
        "location": event["location"],
        "all_day": event["all_day"],
        "start": start,
        "end": end,
        "time_zone": event["time_zone"],
        "rrule": event["rrule"],
        "expected_revision": event["revision"],
        **changes,
    }


def stored(app, event_id):
    with app.state.db.connect() as conn:
        return dict(conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone())


def run_together(*jobs):
    """Start every job at the same moment and return their results."""
    gate, results = threading.Barrier(len(jobs)), [None] * len(jobs)

    def call(index, job):
        gate.wait()
        results[index] = job()

    threads = [threading.Thread(target=call, args=(i, job)) for i, job in enumerate(jobs)]
    [thread.start() for thread in threads]
    [thread.join() for thread in threads]
    return results


# ── Saving an event ──────────────────────────────────────────────────


def test_new_records_start_at_revision_one_and_each_save_adds_one(env):
    client = env[0]
    event = single(client)
    assert event["revision"] == 1
    saved = client.put(f"/api/events/{event['id']}", json=body_of(event, title="Second")).json()
    assert saved["revision"] == 2 and saved["title"] == "Second"
    assert client.get(f"/api/events/{event['id']}").json()["revision"] == 2


def test_first_save_wins_and_the_second_gets_409_and_changes_nothing(env):
    client, app, _, _ = env
    event = single(client)
    first_tab, second_tab = dict(event), dict(event)
    assert (
        client.put(
            f"/api/events/{event['id']}", json=body_of(first_tab, title="From A")
        ).status_code
        == 200
    )
    before = stored(app, event["id"])
    refused = client.put(
        f"/api/events/{event['id']}", json=body_of(second_tab, title="From B", location="Elsewhere")
    )
    assert refused.status_code == 409
    payload = refused.json()
    assert payload["code"] == "revision_conflict" and payload["current_revision"] == 2
    assert "changed elsewhere" in payload["detail"]
    assert stored(app, event["id"]) == before
    assert stored(app, event["id"])["title"] == "From A"


def test_a_save_without_a_revision_is_refused(env):
    client, app, _, _ = env
    event = single(client)
    body = body_of(event, title="Blind")
    del body["expected_revision"]
    refused = client.put(f"/api/events/{event['id']}", json=body)
    assert refused.status_code == 428 and refused.json()["code"] == "revision_required"
    assert stored(app, event["id"])["title"] == "Dentist"


def test_a_revision_from_the_future_is_refused(env):
    client = env[0]
    event = single(client)
    body = body_of(event, expected_revision=event["revision"] + 5)
    assert client.put(f"/api/events/{event['id']}", json=body).status_code == 409


def test_timestamps_play_no_part(env):
    """Two writes inside one second share updated_at; the revision still tells them apart."""
    client, app, _, _ = env
    event = single(client)
    with app.state.db.connect() as conn:
        conn.execute(
            "UPDATE events SET updated_at='2030-01-01T00:00:00Z' WHERE id=?", (event["id"],)
        )
    saved = client.put(f"/api/events/{event['id']}", json=body_of(event, title="ok"))
    assert saved.status_code == 200
    assert (
        client.put(f"/api/events/{event['id']}", json=body_of(event, title="x")).status_code == 409
    )


def test_a_refused_save_leaves_links_untouched(env):
    client, app, _, _ = env
    event = single(client, "Lunch")
    person = "nexus:v1:meridian:person:0190f0e4-0000-7000-8000-000000000042"
    client.post(f"/api/events/{event['id']}/people", json={"resource": person, "label": "Vik"})
    client.put(f"/api/events/{event['id']}", json=body_of(event, title="Moved"))
    with app.state.db.connect() as conn:
        links = conn.execute("SELECT * FROM links").fetchall()
        before = [dict(r) for r in links]
    assert (
        client.put(f"/api/events/{event['id']}", json=body_of(event, title="x")).status_code == 409
    )
    with app.state.db.connect() as conn:
        assert [dict(r) for r in conn.execute("SELECT * FROM links")] == before


def test_linking_a_person_does_not_invalidate_an_open_editor(env):
    """Saving never touches links, so adding one cannot lose data and needs no conflict."""
    client = env[0]
    event = single(client, "Lunch")
    person = "nexus:v1:meridian:person:0190f0e4-0000-7000-8000-000000000042"
    client.post(f"/api/events/{event['id']}/people", json={"resource": person, "label": "Vik"})
    saved = client.put(f"/api/events/{event['id']}", json=body_of(event, title="Late lunch"))
    assert saved.status_code == 200
    assert [link["label"] for link in saved.json()["links"]] == ["Vik"]


def test_validation_still_applies_and_a_bad_save_does_not_use_up_the_revision(env):
    client, app, _, _ = env
    event = single(client)
    bad = client.put(f"/api/events/{event['id']}", json=body_of(event, end="2026-11-20T09:00"))
    assert bad.status_code == 422
    assert stored(app, event["id"])["revision"] == 1
    assert (
        client.put(f"/api/events/{event['id']}", json=body_of(event, title="ok")).status_code == 200
    )


def test_read_only_events_stay_read_only(env):
    client, app, _, _ = env
    event = single(client)
    with app.state.db.connect() as conn:
        conn.execute("UPDATE events SET origin='import' WHERE id=?", (event["id"],))
    response = client.put(f"/api/events/{event['id']}", json=body_of(event, title="x"))
    assert response.status_code == 409 and "read-only" in response.json()["detail"]


def test_rapid_repeated_saves_apply_once(env):
    client, app, _, _ = env
    event = single(client)
    codes = [
        client.put(f"/api/events/{event['id']}", json=body_of(event, title=f"Try {n}")).status_code
        for n in range(5)
    ]
    assert codes == [200, 409, 409, 409, 409]
    row = stored(app, event["id"])
    assert (row["title"], row["revision"]) == ("Try 0", 2)


def test_truly_concurrent_saves_have_exactly_one_winner(env):
    client, app, _, _ = env
    event = single(client)

    def save(n):
        return lambda: client.put(
            f"/api/events/{event['id']}", json=body_of(event, title=f"Writer {n}")
        )

    responses = run_together(*[save(n) for n in range(10)])
    codes = sorted(r.status_code for r in responses)
    assert codes == [200] + [409] * 9
    winner = next(r for r in responses if r.status_code == 200).json()["title"]
    row = stored(app, event["id"])
    assert (row["title"], row["revision"]) == (winner, 2)


# ── Trash ────────────────────────────────────────────────────────────


def test_saving_an_event_deleted_elsewhere_is_refused(env):
    client, app, _, _ = env
    event = single(client)
    client.delete(f"/api/events/{event['id']}")
    response = client.put(f"/api/events/{event['id']}", json=body_of(event, title="Late"))
    assert response.status_code == 410 and "in Trash" in response.json()["detail"]
    assert stored(app, event["id"])["title"] == "Dentist"


def test_a_restored_event_cannot_be_overwritten_by_an_editor_from_before(env):
    client, app, _, _ = env
    event = single(client)
    entry = client.delete(f"/api/events/{event['id']}").json()["trash"]
    client.post(f"/api/trash/{entry}/restore")
    refused = client.put(f"/api/events/{event['id']}", json=body_of(event, title="Stale"))
    assert refused.status_code == 409
    assert stored(app, event["id"])["revision"] == 3


def test_saving_a_purged_event_cannot_recreate_it(env):
    client, app, _, _ = env
    event = single(client)
    entry = client.delete(f"/api/events/{event['id']}").json()["trash"]
    client.delete(f"/api/trash/{entry}?confirmed=true")
    assert client.put(f"/api/events/{event['id']}", json=body_of(event)).status_code == 404
    with app.state.db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM events").fetchone()[0] == 0


def test_save_and_delete_racing_cannot_lose_either_outcome(env):
    client, app, _, _ = env
    for attempt in range(8):
        event = single(client, f"Race {attempt}")
        saved, deleted = run_together(
            lambda: client.put(f"/api/events/{event['id']}", json=body_of(event, title="Saved")),
            lambda: client.delete(
                f"/api/events/{event['id']}", params={"expected_revision": event["revision"]}
            ),
        )
        row = stored(app, event["id"])
        assert sorted((saved.status_code, deleted.status_code)) in ([200, 409], [200, 410])
        if saved.status_code == 200:  # the save came first: the delete was stale and refused
            assert (
                row["title"] == "Saved" and row["trashed_at"] is None and deleted.status_code == 409
            )
        else:  # the delete came first: the save reached an event in Trash
            assert (
                row["title"] == f"Race {attempt}" and row["trashed_at"] and saved.status_code == 410
            )


def test_delete_with_a_stale_revision_is_refused_and_keeps_the_event(env):
    client, app, _, _ = env
    event = single(client)
    client.put(f"/api/events/{event['id']}", json=body_of(event, title="Newer"))
    refused = client.delete(f"/api/events/{event['id']}", params={"expected_revision": 1})
    assert refused.status_code == 409
    assert stored(app, event["id"])["trashed_at"] is None


def test_delete_without_a_revision_still_only_moves_to_trash(env):
    client, app, _, _ = env
    event = single(client)
    client.put(f"/api/events/{event['id']}", json=body_of(event, title="Newest"))
    entry = client.delete(f"/api/events/{event['id']}").json()["trash"]
    assert client.get(f"/api/trash/{entry}").json()["title"] == "Newest"


def test_undo_and_restore_ignore_revisions_because_the_entry_is_the_token(env):
    client = env[0]
    event = single(client)
    entry = client.delete(
        f"/api/events/{event['id']}", params={"expected_revision": event["revision"]}
    ).json()["trash"]
    assert client.post(f"/api/trash/{entry}/restore").status_code == 200
    # A later deletion is a new entry: acting on the old one cannot touch it.
    newer = client.delete(f"/api/events/{event['id']}").json()["trash"]
    assert newer != entry
    assert client.post(f"/api/trash/{entry}/restore").status_code == 404
    assert client.delete(f"/api/trash/{entry}?confirmed=true").status_code == 404
    assert client.get(f"/api/trash/{newer}").status_code == 200


def test_restore_and_purge_racing_have_one_outcome(env):
    client, app, _, _ = env
    for attempt in range(8):
        event = single(client, f"Contest {attempt}")
        entry = client.delete(f"/api/events/{event['id']}").json()["trash"]
        restored, purged = run_together(
            lambda: client.post(f"/api/trash/{entry}/restore"),
            lambda: client.delete(f"/api/trash/{entry}?confirmed=true"),
        )
        assert sorted((restored.status_code, purged.status_code)) == [200, 404]
        with app.state.db.connect() as conn:
            exists = conn.execute(
                "SELECT count(*) FROM events WHERE id=?", (event["id"],)
            ).fetchone()[0]
        assert exists == (1 if restored.status_code == 200 else 0)


def test_concurrent_restores_create_one_active_event(env):
    client, app, _, _ = env
    event = single(client)
    entry = client.delete(f"/api/events/{event['id']}").json()["trash"]
    responses = run_together(
        *[lambda: client.post(f"/api/trash/{entry}/restore") for _ in range(8)]
    )
    assert sorted(r.status_code for r in responses) == [200] + [404] * 7
    with app.state.db.connect() as conn:
        assert (
            conn.execute("SELECT count(*) FROM events WHERE trashed_at IS NULL").fetchone()[0] == 1
        )


def test_empty_trash_refuses_a_different_trash_with_the_same_count(env):
    client = env[0]
    a, b = single(client, "A"), single(client, "B")
    entry = client.delete(f"/api/events/{a['id']}").json()["trash"]
    generation = client.get("/api/trash").json()["generation"]
    # Another client swaps what is in Trash; the number of items stays one.
    client.post(f"/api/trash/{entry}/restore")
    client.delete(f"/api/events/{b['id']}")
    assert client.get("/api/trash").json()["total"] == 1
    refused = client.post(
        "/api/trash/empty", json={"confirmed": True, "expected_generation": generation}
    )
    assert refused.status_code == 409
    assert [i["title"] for i in client.get("/api/trash").json()["items"]] == ["B"]


# ── Recurring series and occurrences ─────────────────────────────────


def test_editing_a_series_conflicts_with_an_occurrence_deleted_elsewhere(env):
    client, _, _, _ = env
    series = weekly(client)
    client.delete(f"/api/events/{series['id']}", params={"occurrence": OCT26})
    refused = client.put(f"/api/events/{series['id']}", json=body_of(series, title="Renamed"))
    assert refused.status_code == 409
    after = client.get(f"/api/events/{series['id']}").json()
    assert after["exdates"] == [OCT26] and after["title"] == "Standup"


def test_after_review_a_series_save_keeps_the_exclusion_made_elsewhere(env):
    client, _, _, _ = env
    series = weekly(client)
    client.delete(f"/api/events/{series['id']}", params={"occurrence": OCT26})
    current = client.get(f"/api/events/{series['id']}").json()
    saved = client.put(
        f"/api/events/{series['id']}",
        json=body_of(series, title="Renamed", expected_revision=current["revision"]),
    ).json()
    assert saved["title"] == "Renamed" and saved["exdates"] == [OCT26]


def test_a_stale_occurrence_delete_is_refused_and_excludes_nothing(env):
    client, _, _, _ = env
    series = weekly(client)
    client.put(f"/api/events/{series['id']}", json=body_of(series, title="Renamed"))
    refused = client.delete(
        f"/api/events/{series['id']}",
        params={"occurrence": OCT26, "expected_revision": series["revision"]},
    )
    assert refused.status_code == 409
    assert client.get(f"/api/events/{series['id']}").json()["exdates"] == []
    assert client.get("/api/trash").json()["total"] == 0


def test_a_stale_series_delete_is_refused(env):
    client, app, _, _ = env
    series = weekly(client)
    client.delete(f"/api/events/{series['id']}", params={"occurrence": OCT26})
    refused = client.delete(
        f"/api/events/{series['id']}",
        params={"scope": "series", "expected_revision": series["revision"]},
    )
    assert refused.status_code == 409 and stored(app, series["id"])["trashed_at"] is None


def test_restoring_an_occurrence_makes_open_series_editors_stale(env):
    client, _, _, _ = env
    series = weekly(client)
    entry = client.delete(f"/api/events/{series['id']}", params={"occurrence": OCT26}).json()[
        "trash"
    ]
    current = client.get(f"/api/events/{series['id']}").json()
    client.post(f"/api/trash/{entry}/restore")
    refused = client.put(f"/api/events/{series['id']}", json=body_of(current, title="Stale"))
    assert refused.status_code == 409
    assert client.get(f"/api/events/{series['id']}").json()["exdates"] == []


def test_concurrent_deletes_of_different_occurrences_lose_nothing(env):
    client, _, _, _ = env
    series = weekly(client, rrule="FREQ=DAILY;COUNT=20")
    keys = [o["occurrence"] for o in occurrences(client, *WIDE)][:10]
    responses = run_together(
        *[
            (
                lambda key: (
                    lambda: client.delete(f"/api/events/{series['id']}", params={"occurrence": key})
                )
            )(k)
            for k in keys
        ]
    )
    assert {r.status_code for r in responses} == {200}
    assert sorted(client.get(f"/api/events/{series['id']}").json()["exdates"]) == sorted(keys)


def test_concurrent_stale_occurrence_deletes_allow_one(env):
    client, _, _, _ = env
    series = weekly(client, rrule="FREQ=DAILY;COUNT=20")
    keys = [o["occurrence"] for o in occurrences(client, *WIDE)][:6]
    params = lambda key: {"occurrence": key, "expected_revision": series["revision"]}  # noqa: E731
    responses = run_together(
        *[
            (lambda key: lambda: client.delete(f"/api/events/{series['id']}", params=params(key)))(
                k
            )
            for k in keys
        ]
    )
    assert sorted(r.status_code for r in responses) == [200] + [409] * 5
    assert len(client.get(f"/api/events/{series['id']}").json()["exdates"]) == 1


def test_all_day_series_uses_the_same_protection(env):
    client, _, _, _ = env
    series = client.post("/api/events", json={
        "calendar_id": native(client)["id"], "title": "Bins", "all_day": True,
        "start": "2026-11-02", "end": "2026-11-03", "rrule": "FREQ=WEEKLY;COUNT=3",
    }).json()  # fmt: skip
    client.delete(f"/api/events/{series['id']}", params={"occurrence": "2026-11-09"})
    assert (
        client.put(f"/api/events/{series['id']}", json=body_of(series, title="x")).status_code
        == 409
    )


# ── Calendars and categories ─────────────────────────────────────────


def calendar_by_id(client, calendar_id):
    return next(c for c in client.get("/api/state").json()["calendars"] if c["id"] == calendar_id)


def test_stale_calendar_rename_is_refused(env):
    client = env[0]
    cal = native(client)
    first = client.put(
        f"/api/calendars/{cal['id']}",
        json={"name": "A", "color": "#7AA7EB", "expected_revision": cal["revision"]},
    )
    assert first.status_code == 200 and first.json()["revision"] == cal["revision"] + 1
    refused = client.put(
        f"/api/calendars/{cal['id']}",
        json={"name": "B", "color": "#7AA7EB", "expected_revision": cal["revision"]},
    )
    assert refused.status_code == 409 and "calendar changed elsewhere" in refused.json()["detail"]
    assert calendar_by_id(client, cal["id"])["name"] == "A"
    assert client.put(f"/api/calendars/{cal['id']}", json={"name": "C"}).status_code == 428


def test_showing_or_hiding_a_calendar_is_not_a_form_edit(env):
    client = env[0]
    cal = native(client)
    assert client.put(f"/api/calendars/{cal['id']}", json={"visible": False}).status_code == 200
    # An open rename dialog is not invalidated by the switch.
    assert calendar_by_id(client, cal["id"])["revision"] == cal["revision"]
    saved = client.put(
        f"/api/calendars/{cal['id']}", json={"name": "New", "expected_revision": cal["revision"]}
    )
    assert saved.status_code == 200 and saved.json()["visible"] is False


def test_stale_calendar_delete_is_refused(env):
    client = env[0]
    work = client.post("/api/calendars", json={"name": "Work", "color": "#7AA7EB"}).json()
    client.put(
        f"/api/calendars/{work['id']}", json={"name": "Job", "expected_revision": work["revision"]}
    )
    refused = client.delete(
        f"/api/calendars/{work['id']}",
        params={"confirmed": True, "expected_revision": work["revision"]},
    )
    assert refused.status_code == 409
    assert (
        client.delete(f"/api/calendars/{work['id']}", params={"confirmed": True}).status_code == 428
    )
    assert calendar_by_id(client, work["id"])["name"] == "Job"


def test_stale_category_edit_and_delete_are_refused(env):
    client = env[0]
    category = client.post("/api/categories", json={"name": "Health", "color": "#8FC2A9"}).json()
    assert category["revision"] == 1
    body = {"name": "Care", "color": "#8FC2A9", "expected_revision": 1}
    assert client.put(f"/api/categories/{category['id']}", json=body).json()["revision"] == 2
    assert (
        client.put(f"/api/categories/{category['id']}", json={**body, "name": "Old"}).status_code
        == 409
    )
    assert (
        client.delete(
            f"/api/categories/{category['id']}", params={"expected_revision": 1}
        ).status_code
        == 409
    )
    assert client.delete(f"/api/categories/{category['id']}").status_code == 428
    names = [c["name"] for c in client.get("/api/state").json()["categories"]]
    assert names == ["Care"]
    assert (
        client.delete(
            f"/api/categories/{category['id']}", params={"expected_revision": 2}
        ).status_code
        == 200
    )


def test_stale_subscription_address_change_is_refused(env):
    client, _, _, _ = env
    calendar = subscribe(client).json()
    url = "https://feeds.example.com/new.ics"
    assert client.put(f"/api/subscriptions/{calendar['id']}", json={"url": url}).status_code == 428
    assert (
        client.put(
            f"/api/subscriptions/{calendar['id']}",
            json={"url": url, "expected_revision": calendar["revision"]},
        ).status_code
        == 200
    )
    assert (
        client.put(
            f"/api/subscriptions/{calendar['id']}",
            json={"url": url + "x", "expected_revision": calendar["revision"]},
        ).status_code
        == 409
    )
    # The refresh interval is one setting from one control and needs no revision.
    assert (
        client.put(f"/api/subscriptions/{calendar['id']}", json={"refresh_minutes": 60}).status_code
        == 200
    )


# ── Imports and subscriptions ────────────────────────────────────────


def test_reimport_that_changes_a_record_advances_its_revision(env):
    client, app, _, _ = env
    result = client.post("/api/import", json={"content": ICS, "filename": "f.ics"}).json()
    cid = result["calendar"]["id"]
    found = next(o for o in occurrences(client, *WIDE) if o["title"] == "Grand Prix")
    assert stored(app, found["event_id"])["revision"] == 1
    client.post("/api/import", json={"content": ICS, "calendar_id": cid})  # identical
    assert stored(app, found["event_id"])["revision"] == 1
    changed = ICS.replace("SUMMARY:Grand Prix", "SUMMARY:Grand Prix 2")
    client.post("/api/import", json={"content": changed, "calendar_id": cid})
    assert stored(app, found["event_id"])["revision"] == 2


def test_concurrent_imports_of_one_file_never_duplicate(env):
    client, app, _, _ = env
    cid = client.post("/api/import", json={"content": ICS, "filename": "f.ics"}).json()["calendar"][
        "id"
    ]
    with app.state.db.connect() as conn:
        conn.execute("DELETE FROM events WHERE calendar_id=?", (cid,))
    responses = run_together(
        *[
            lambda: client.post("/api/import", json={"content": ICS, "calendar_id": cid})
            for _ in range(6)
        ]
    )
    assert {r.status_code for r in responses} == {201}
    assert sorted(r.json()["created"] for r in responses) == [0, 0, 0, 0, 0, 6]
    with app.state.db.connect() as conn:
        assert (
            conn.execute("SELECT count(*) FROM events WHERE calendar_id=?", (cid,)).fetchone()[0]
            == 6
        )


def test_subscription_sync_ignores_a_feed_whose_address_changed_during_the_fetch(env, monkeypatch):
    client, app, _, feed = env
    calendar = subscribe(client).json()
    feed.body = feed_version(("old-1", "20261108T130000Z", "From the old address"))
    original = Feed.__call__

    def owner_changes_the_address_mid_fetch(self, request):
        with app.state.db.connect() as conn:
            conn.execute(
                "UPDATE subscriptions SET url='https://feeds.example.com/new.ics' WHERE calendar_id=?",
                (calendar["id"],),
            )
        return original(self, request)

    monkeypatch.setattr(Feed, "__call__", owner_changes_the_address_mid_fetch)
    result = app.state.worker.sync_subscription(calendar["id"])
    assert result["counts"] is None and result["error"] is None
    with app.state.db.connect() as conn:
        count = conn.execute("SELECT count(*) FROM events WHERE calendar_id=?", (calendar["id"],))
        assert count.fetchone()[0] == 0
        row = conn.execute(
            "SELECT running,content_hash FROM subscriptions WHERE calendar_id=?", (calendar["id"],)
        ).fetchone()
    assert row["running"] == 0 and row["content_hash"] is None


def test_subscription_refresh_cannot_change_a_native_event(env):
    client, app, _, feed = env
    event = single(client)
    feed.body = feed_version(("r1", "20261108T130000Z", "Brazil"))
    calendar = subscribe(client).json()
    app.state.worker.sync_subscription(calendar["id"])
    assert stored(app, event["id"])["revision"] == 1


# ── Migration and backups ────────────────────────────────────────────


def table_digest(conn, table, columns):
    selected = ",".join(columns)
    rows = conn.execute(f"SELECT {selected} FROM {table} ORDER BY id").fetchall()
    return hashlib.sha256(repr([tuple(r) for r in rows]).encode()).hexdigest()


def columns_of(conn, table):
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


def test_migration_starts_every_record_at_revision_one_and_changes_nothing_else(tmp_path):
    path = tmp_path / "chronos.sqlite3"
    build_v2(path).close()
    db3 = sqlite3.connect(path)
    db3.executescript("BEGIN;\n" + MIGRATIONS[2] + "\nPRAGMA user_version=3; COMMIT;")
    columns = {
        t: columns_of(db3, t) for t in ("events", "calendars", "categories", "links", "trash")
    }
    before = {t: table_digest(db3, t, c) for t, c in columns.items()}
    db3.close()

    db = Database(path)
    with db.connect() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
        for table, cols in columns.items():
            assert table_digest(conn, table, cols) == before[table], table
        for table in ("events", "calendars", "categories"):
            assert {r[0] for r in conn.execute(f"SELECT DISTINCT revision FROM {table}")} == {1}
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_upgraded_data_is_protected_at_once(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_RESOLVER_KEY", KEY)
    build_v2(tmp_path / "chronos.sqlite3").close()
    app = create_app(tmp_path, nexus=FakeNexus(), workers=False)
    event_id = "0190f0e4-0000-7000-8000-00000000e002"
    with TestClient(app, headers=GW) as client:
        event = client.get(f"/api/events/{event_id}").json()
        assert event["revision"] == 1
        body = {
            "calendar_id": event["calendar_id"],
            "title": "x",
            "all_day": True,
            "start": event["start"],
            "end": event["end"],
        }
        assert client.put(f"/api/events/{event_id}", json=body).status_code == 428
        assert (
            client.put(f"/api/events/{event_id}", json={**body, "expected_revision": 1}).status_code
            == 200
        )
        assert (
            client.put(f"/api/events/{event_id}", json={**body, "expected_revision": 1}).status_code
            == 409
        )


def test_a_failed_migration_leaves_the_previous_schema(tmp_path):
    path = tmp_path / "chronos.sqlite3"
    build_v2(path).close()
    conn = sqlite3.connect(path)
    conn.executescript("BEGIN;\n" + MIGRATIONS[2] + "\nPRAGMA user_version=3; COMMIT;")
    conn.execute("ALTER TABLE categories ADD COLUMN revision INTEGER")  # blocks the last statement
    conn.commit()
    conn.close()
    with pytest.raises(sqlite3.OperationalError):
        Database(path)
    conn = sqlite3.connect(path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
    assert "revision" not in columns_of(conn, "events")  # rolled back with the failing statement


def test_backup_round_trip_keeps_revisions(env):
    client, app, _, _ = env
    event = single(client)
    client.put(f"/api/events/{event['id']}", json=body_of(event, title="Second"))
    exported = client.post("/empyrean/v1/backup/export", headers={"x-nexus-resolver-key": KEY})
    headers = {
        k: v for k, v in exported.headers.items() if k.lower().startswith("x-empyrean-backup-")
    }
    current = client.get(f"/api/events/{event['id']}").json()
    client.put(f"/api/events/{event['id']}", json=body_of(current, title="Third"))
    assert client.post(
        "/empyrean/v1/backup/restore", headers={"x-nexus-resolver-key": KEY, **headers}, content=exported.content
    ).status_code == 200  # fmt: skip
    restored = client.get(f"/api/events/{event['id']}").json()
    assert (restored["title"], restored["revision"]) == ("Second", 2)
    client.post("/empyrean/v1/backup/finalize", headers={"x-nexus-resolver-key": KEY})


def test_a_revision_never_leaks_into_exports_or_resolver_labels(env):
    client = env[0]
    event = single(client)
    resolved = client.post(
        "/empyrean/v1/resources/resolve",
        headers={"x-nexus-resolver-key": KEY},
        json={"resource": event["reference"], "requester": "lyra"},
    )
    assert resolved.status_code == 403
    assert "revision" not in json.dumps(occurrences(client, *WIDE))
