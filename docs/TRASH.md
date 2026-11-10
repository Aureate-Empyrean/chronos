# Trash: recoverable deletion

Applies to Chronos's own events (0.6.0). Imported and subscribed events are read-only copies owned by their source and never enter Trash.

## What deleting does

| Action | Effect | Recovery |
| --- | --- | --- |
| Delete an event | Moves to Trash, keeps its row and ID | Restore, or Undo in the toast |
| Delete one occurrence | The occurrence leaves the series; the series is otherwise untouched | Restore, or Undo |
| Delete a series | Every occurrence leaves the calendar together, with the rule intact | Restore |
| Delete a native calendar | Its events move to Trash together, and the calendar stays hidden as their container | Restore all, or restore one, which also brings the calendar back |
| Delete for good | Removes the row; a tombstone remains so links resolve as deleted | None. A separate confirmation is required |
| Empty Trash | Deletes everything for good | None. Needs a ticked confirmation and refuses if Trash changed since it was shown |

Nothing is removed from Trash automatically. A repeating event needs an explicit target: `?occurrence=<key>` or `?scope=series`. Without one the request is refused, so a lost occurrence key can never widen into deleting the series.

## Data model (schema 3)

- `events.trashed_at` is set while an event is in Trash. The row, its ID, its links and its timestamps are unchanged, so a restore cannot create a second copy.
- An occurrence in Trash stays in its series' `exdates`, like any skipped occurrence, so expansion needs no special case. A `trash` row records that it can come back.
- `trash` has one row per recoverable thing (`UNIQUE(event_id, occurrence)`), with a snapshot of what was deleted and folded text for search.
- `calendars.trashed_at` marks a deleted native calendar that still holds recoverable events. It is removed when the last of them is deleted for good.
- `trash_audit` records trash, restore and purge with IDs and times only. It holds no titles and survives permanent deletion.

Every lifecycle operation runs in one `BEGIN IMMEDIATE` transaction, so concurrent requests are serialized.

## Recurrence

Occurrence keys are the canonical start: a UTC instant, or an ISO date for all-day series. Native events have no per-occurrence edits, so a native occurrence has no content of its own. Modified occurrences (`RECURRENCE-ID`) exist only in imported and subscribed calendars, which are read-only.

| Situation | Result |
| --- | --- |
| Restore an occurrence | Removes only its own key from `exdates`. Other skips stay as they are now |
| Series renamed or its rule changed while an occurrence is in Trash (same start) | The occurrence stays deleted. On restore it takes the series' current details. Trash keeps showing what was deleted |
| Series rescheduled (start changed) | Occurrences in Trash stay deleted. If the new schedule no longer produces the key, restore is refused and "Restore as separate event" is offered. It creates a one-off event whose ID is the Trash entry's ID, so it can happen only once |
| Occurrence in Trash whose series is also in Trash | Restore the series first; the occurrence is then restorable |
| Series deleted for good | Its occurrence entries go with it |
| Occurrence deleted for good | The key stays in `exdates`, so later edits cannot bring it back |
| Occurrences skipped before 0.6.0 | Stay skipped. They are not added to Trash, because nothing records when or why they were skipped |

## Integrations

| Surface | While in Trash | After restore | After permanent deletion |
| --- | --- | --- | --- |
| Occurrences, search, event counts | Excluded | Included | Gone |
| `GET /api/events/{id}` and all writes | 410, "in Trash" | Normal | 404 |
| Resolver (`/empyrean/v1/resources/resolve`) | 404, the same "unavailable" answer Atlas gives | Available again; earlier grants still hold | 410 |
| `link-search` | Excluded | Included | Gone |
| Outgoing references | Excluded, and the Nexus edges are unpublished | Republished through the outbox | Gone |
| Backup | Trash is included: a Nexus backup is the explicit recovery export | | |

Incoming links from other modules stay in Nexus while an event is in Trash and resolve as unavailable. "Delete for good" warns when it finds any, and says so when it could not check.

Restoring a backup reinstates Trash exactly as it was in that backup and republishes only active events' edges.

## Import, export and subscriptions

- Import only ever writes to import calendars, and subscription refresh only to subscription calendars. Neither can reach a native event.
- `apply_records` leaves any row in Trash untouched: no update, no resurrection, no duplicate, and a feed that drops it does not remove it.
- Chronos has **no ICS export** today, so there is no export that could include Trash. When one is added it must select `trashed_at IS NULL`.
- Limits for external calendars:
  - Chronos publishes no feed and has no CalDAV, so nothing outside Chronos learns about a deletion.
  - A subscribed calendar follows its feed. An event removed upstream is removed from Chronos directly, not through Trash.
  - Deleting a subscribed or imported calendar is immediate and permanent, as before. Subscribing or importing again recreates the events with new IDs.
  - A copy made with "Copy to my calendar" is an independent native event.

## Migration and rollback

Migration 3 is additive: two nullable columns, a partial index and two new tables. No existing row is rewritten, every event stays active, and it runs in one transaction, so a failure leaves schema 2 intact.

Before applying it to real data, rehearse on a copy:

```sh
PYTHONPATH=backend python scripts/rehearse_migration.py <copy of chronos.sqlite3>
```

The script migrates its own temporary copy, compares every pre-existing column of every table, checks integrity and foreign keys, and prints counts only.

### Rollback

Rollback means the pre-update snapshot plus the previous image. `nexus.manage --update --approve --backup-first` takes that snapshot, and it is a plain schema 2 SQLite file. Do not remove the columns or regenerate IDs in place.

Order matters. Chronos 0.5.0 refuses to start on a schema 3 database, and restoring through Nexus while 0.6.0 is installed migrates the backup forward again. So replace the file while the module is stopped:

1. Disable the module (`POST /api/v1/modules/chronos/disable`).
2. Copy `/data/backups/modules/chronos/<backup id>/artifact` from the Nexus data volume over `chronos.sqlite3` in the module's data volume. Delete `chronos.sqlite3-wal` and `chronos.sqlite3-shm`, and keep the file owned by uid 10001.
3. Apply the previous manifest with `nexus.manage --update --approve --allow-downgrade`, adding `--backup-override "<reason>"` because a stopped module cannot be backed up.
4. Enable the module and check its health.

This sequence was rehearsed on a disposable stack. Anything created or deleted after the update is lost, because the snapshot predates it.
