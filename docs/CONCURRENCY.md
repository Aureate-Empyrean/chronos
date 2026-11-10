# Concurrent edits

Applies from Chronos 0.7.0. A client that saves a version it no longer has is refused, so two tabs or devices cannot silently overwrite each other. Nothing is merged automatically.

## How it works

Events, calendars and categories have an integer `revision`, starting at 1. Reads return it. A write names the revision it was based on as `expected_revision`, in the body or the query string because the Nexus bridge does not carry custom request headers.

Each write runs in one `BEGIN IMMEDIATE` transaction: check the record, compare the revision, validate, write, add one to the revision. An event update also conditions its `UPDATE` on the revision. Timestamps play no part.

| Answer | Meaning |
| --- | --- |
| 409 `revision_conflict` | The stored revision is different. Nothing was written. The response includes `current_revision` |
| 428 `revision_required` | The write named no revision, for example from a page loaded before 0.7.0 |
| 410 | The event is in Trash |
| 404 | The record no longer exists |

## What is protected

| Record or action | Token | Notes |
| --- | --- | --- |
| Save an event or series (`PUT /api/events/{id}`) | event revision, required | |
| Delete an occurrence, event or series | event revision, enforced when sent | The interface always sends it |
| Rename or recolor a calendar | calendar revision, required | Showing or hiding is a separate switch and needs none |
| Delete a calendar | calendar revision, required | |
| Edit or delete a category | category revision, required | |
| Change a subscription's address | calendar revision, required | Refresh interval and pause are single controls and need none |
| Restore or permanently delete from Trash | the Trash entry ID | An entry is used once. Deleting again creates a new one, so an old action cannot reach it |
| Empty Trash | Trash generation | Changes with every move in or out of Trash, so a different Trash of the same size is refused |
| Import and subscription refresh | serialized write transaction | Changed records advance their revision. A feed fetched from an address that has since changed is discarded |

Occurrences have no record of their own in native calendars, so the series' revision is their token. Deleting or restoring an occurrence advances it. A series editor opened before that gets a conflict, and a save after review keeps the current exclusions, because saves never replace `exdates` with the client's copy.

Moving to Trash and restoring also advance the revision. An editor opened before a delete and undo gets a conflict when it saves.

Adding or removing a linked person or place does not advance the revision. Saves never touch links, so there is nothing to lose, and it would only interrupt an open editor.

Moving to Trash accepts a request with no revision because it destroys nothing and always keeps the newest version. The P1 navigation suite's cleanup relies on this. Requests with a stale revision are refused.

## In the interface

When a save conflicts, the editor stays open with every field intact and says nothing was saved.

- **Review stored version** shows what differs, stored against edited, and any change in deleted occurrences.
- **Save my version** saves against the exact revision just reviewed. If it changed again, the conflict comes back.
- **Discard my edits and use the stored version** reloads the form.

Calendar and category dialogs stay open and say what is stored now, and saving again is the deliberate retry. A delete refused as stale reloads the details so the current version can be read first.

A retained draft stays tied to the revision it was written against, through refresh, Back and Forward, and leaving Chronos. Drafts from before 0.7.0 have no revision and always go through review.

## Migration and rollback

Migration 4 adds three `NOT NULL DEFAULT 1` columns and rewrites no data. It runs in one transaction. `scripts/rehearse_migration.py` checks a copy, as for [Trash](TRASH.md).

Rollback follows the procedure in [`TRASH.md`](TRASH.md#rollback): swap the pre-update backup into the stopped module, then apply the previous manifest with `--allow-downgrade`. Chronos 0.6.0 refuses a schema 4 database, and a Nexus restore on 0.7.0 migrates forward again.

## Limits

- This is conflict detection, not device sync or merging.
- Settings, shared-date source switches and a subscription's interval and pause are last-write-wins. Each is a single independent control.
- A browser tab loaded before 0.7.0 is refused with 428 until it is reloaded. Nothing it sends can overwrite data.
