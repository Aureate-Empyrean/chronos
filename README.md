# Chronos

Calendars and events for Aureate Empyrean. Canonical architecture: `../architecture/modules/chronos.md`
(ADR 0010, 0011, 0012, 0013). Licensed AGPL-3.0-or-later.

## Included (0.1.0)

- Month, Week, Day and Agenda (upcoming and past) views; mini month; keyboard shortcuts
  (`T` today, `M`/`W`/`D`/`A` views, `←`/`→` move, `N` new event, `/` search, `Esc` close).
- Native events: create, edit, delete, all-day or timed with an explicit IANA time zone,
  recurrence (daily, weekly on chosen days, monthly, yearly; interval; until or count), skip a
  single occurrence, duplicate, categories (name + color), per-event color, status
  (confirmed, tentative, cancelled), location and description, search across all calendars.
- Several native calendars with colors and visibility; category filter.
- **One-time `.ics` import** with preview (counts, recurring/all-day/overrides, zones,
  duplicates already present, events in other calendars, per-event errors, warnings) into a
  new or existing import calendar. Re-importing updates changed events and never duplicates;
  it never deletes and never touches native calendars.
- **iCalendar subscriptions** (https, http, webcal) with name, color, refresh interval
  (15 min – 24 h), pause, sync now, last success, last error and warnings. Each successful
  refresh makes the calendar equal the feed: new, changed and removed events, stable IDs, no
  duplicates. ETag/Last-Modified and content hashing skip unchanged feeds. A feed that
  suddenly returns no events keeps the existing ones and warns.
- **Shared dates** (derived, read-only): Lyra release dates (on by default; what is shared is
  chosen in Lyra) and Mnemosyne Task deadlines (**off by default**, opt-in in Settings,
  completed tasks hidden unless chosen). "Plan in my calendar" creates a native event linked to
  the owner's resource (`chronos.about`), visible to that module as a backlink.
- Event provenance everywhere: native, imported (file and time), subscribed (feed and last
  sync) or shared by a module (with certainty: confirmed, may change, estimated).

Read-only by design: no two-way synchronization, no CalDAV, no reminders yet.

## Trash (0.6.0, in development, not deployed)

Deleting one of your own events, one occurrence or a whole series moves it to Trash, with Undo. Trash lists what was deleted and when, with search, restore, and a separately confirmed permanent delete. Nothing leaves Trash automatically. Deleted events disappear from calendars, search, other modules' links and link search, and come back with the same identifiers and relationships. Imported and subscribed events stay read-only and never enter Trash. Details, recurrence rules, integration behaviour, migration and rollback: [`docs/TRASH.md`](docs/TRASH.md).

## Concurrent edits (0.7.0, in development, not deployed)

A save based on an older version of an event, calendar or category is refused instead of overwriting newer data. The editor keeps your changes, shows what is stored now, and lets you decide. Nothing is merged automatically. Details: [`docs/CONCURRENCY.md`](docs/CONCURRENCY.md).

## Navigation (0.5.0 on aetest)

Calendar views, dates, native events, single occurrences and projected dates are browser history entries through the
Nexus navigation contract (`frontend/navigation.js`). Search and category filters are private per-entry state. An
unsaved event editor stays open while the address moves, and is kept as a draft when Chronos is left. Open on a
projected date uses the owner's resolved path where one exists. See `../empyrean-nexus/docs/navigation-history.md`.

## Added in 0.4.0 (production since 2026-11-09)

A names-only `link-search` projection, and a deep link to one event ([record](../VALIDATION_PHASE5_AETEST_2026-11-09.md)).

## Added in 0.3.0 (production since 2026-11-09)

Add a Place from Atlas to an event (`chronos.at`, shared with `atlas`), and a [Linked from other modules](../architecture/concepts/backlinks.md) section on event details. New reviewed scopes: resolve `atlas:place` and `meridian:interaction`; read Atlas's `place-directory`. No new capability. [Record](../VALIDATION_PHASE4_AETEST_2026-11-09.md).

## Added in 0.2.0 (in production since 2026-11-07 — see `../DEPLOYMENT_PHASE2_EXODUS_2026-11-07.md`)

- **Meridian birthdays and anniversaries** as a shared-date source, **off by default** (Settings → Dates
  shared by other modules), read through Meridian's `dated-items` projection and refreshed on
  `meridian.dated-items.changed`. Meridian stays the owner of the dates.
- **People on events:** a native event can link Meridian People, chosen by name through Meridian's
  `people-directory` projection (names only). The link is a `chronos.involves` reference that names
  `meridian` as a reader, so Meridian can list the event on the person's profile; the current name is
  shown through resolution, and a removed person shows as no longer in Meridian.
- Both need Meridian 0.6.0 or later; with an older Meridian the source reports its availability and the
  picker says why it is empty. Checked inside the real Nexus on aetest with Meridian 0.6.0
  ([record](../VALIDATION_PHASE2_AETEST_2026-11-07.md)).
- Manifest: reads `meridian`/`dated-items` and `meridian`/`people-directory`, resolves `meridian`/`person`,
  consumes `meridian.dated-items.changed`. No new capability.

## iCalendar details

Parsing uses `icalendar` 7; recurrence expansion uses `python-dateutil`. Supported: VEVENT,
UID, DTSTART, DTEND, DURATION, SUMMARY, DESCRIPTION, LOCATION, STATUS, SEQUENCE, RRULE, EXDATE,
RECURRENCE-ID (moved and cancelled occurrences), VTIMEZONE/TZID (IANA names, Windows names,
custom zones matched to an equivalent IANA zone with a warning), X-WR-CALNAME, X-WR-TIMEZONE.
Timed events are stored as UTC instants plus their zone and expanded in that zone, so wall
times survive DST. All-day events stay dates. Floating times are pinned at import to the
feed's X-WR-TIMEZONE, or to your Chronos time zone. Not supported: RDATE (ignored with a
warning), RANGE=THISANDFUTURE, VTODO/VJOURNAL (counted, not imported), alarms, attendees.

## Subscription safety and troubleshooting

Subscriptions need the `network.egress` capability (Nexus ≥ 0.1.5). Before every request and
redirect Chronos resolves the host and refuses loopback, private, link-local, CGNAT, multicast,
reserved and unspecified addresses (including IPv4-mapped IPv6), `.local`/`.internal`/`.lan`
names, ports other than 80/443/8080/8443, and URLs with credentials. The connection is pinned
to the vetted address with TLS verified for the host name; at most 3 redirects, 15 s, 5 MiB.
URLs are never logged and are shown masked (`https://host/…`).

| Message | Meaning |
|---|---|
| Local, private and reserved network addresses are not allowed | The host resolves to a non-public address. Chronos cannot subscribe to feeds on your LAN. |
| The calendar server refused access / was not found | HTTP 401/403 or 404/410: the address is wrong or private. |
| This is not an iCalendar file | The server returned HTML or something else; use the feed's `.ics` address. |
| The calendar is larger than 5 MiB | Use a narrower feed. |
| The feed returned no events; the existing events were kept | Usually a temporary upstream problem; the next good refresh applies. |

Failures retry with backoff (5 min doubling, capped at the refresh interval). "Sync now" and
changing the address retry immediately.

## Design

Chronos uses token set 2.1 and foundation 1.1 (architecture ADR 0012, ADR 0014): a starfield atmosphere in celestial blue and violet, a floating liquid-glass rail and toolbar, the calendar on an elevated glass panel, luminous gradient event pills and blocks, display typography and accent-lit floating layers. Glass falls back to solid surfaces without `backdrop-filter` or with reduced transparency. Before/after screenshots (Playwright, 1440 px and 390 px, inside the Nexus sandbox): `docs/screenshots/`.

Its application icon (0.1.1) is a crescent moon and four-point star on the celestial-blue tile, served at `/icon.svg` for Nexus (manifest `icon`) and drawn as the same glyph in the header.

## Run through Nexus

Requires Nexus 0.1.8 or later within 0.1.x (0.1.1 declares an application icon). Port 15333 (registry: Nexus `docs/ports.md`).

```sh
docker compose build
python scripts/manifest.py
```

Review and install `manifest.local.json` in Nexus (Modules → Install module), grant the listed
capabilities and scopes, enable, open `/app/modules/chronos`. Requested permissions:
full-window application, private data volume, outbound network (subscriptions), event
subscription (`lyra.dated-items.changed`, `mnemosyne.resource.changed` and, since 0.2.0,
`meridian.dated-items.changed` as hints), references (create, read, resolve Lyra titles, Mnemosyne
tasks and, since 0.2.0, Meridian People), projection reads (`dated-items` from Lyra and Mnemosyne;
since 0.2.0 `dated-items` and `people-directory` from Meridian), backup v1. 0.2.0 adds no
capability. No environment variables or secrets are needed.

Module contract: resources `calendar` (not resolvable) and `event` (resolvable to modules an
event was shared with), Entity References v2 with enumeration, backup v1 (consistent SQLite
snapshot `chronos-sqlite` format 1; subscription refreshes are suspended between restore and
finalize).

## Development and tests

```sh
python -m venv .venv && .venv/bin/pip install -r requirements-dev.lock
.venv/bin/python -m pytest -q
.venv/bin/ruff check backend tests scripts && .venv/bin/ruff format --check backend tests scripts
node --check frontend/app.js
```

Browser journeys for Trash run in a real Nexus shell against a disposable stack: `tests/e2e/trash_e2e.cjs` and, for edit conflicts, `tests/e2e/conflict_e2e.cjs` (usage in their headers).

Tests cover DST-correct recurrence, all-day dates, validation, the import matrix (overrides,
cancelled occurrences, EXDATE, floating and custom zones, missing UIDs, broken components,
re-import), subscription updates/removals/304/empty-feed guard, SSRF refusals (private and
mapped addresses, metadata IPs, ports, credentials, `.local`, redirects to private hosts, size
and content checks), address pinning, projection reconciliation (paging, failures keep data,
invalid and foreign items rejected), Mnemosyne and Meridian opt-in/opt-out, the Meridian change hint,
people on events (picker, names only, duplicates, read-only events, enumeration, resolution for
Meridian), planning with references,
resolver policy, enumeration, backup round trip, the gateway key and the shared design files.

## Localization

Every interface string goes through the message catalog (`frontend/locales/en.json`, keys
are the English source text; `{placeholders}`; plural pairs). Dates, times, weekdays and
relative times use `Intl` with the Nexus locale and your time zone and week start. Additional
catalogs (for example `sk.json`) can be added to `frontend/locales` or to the data volume at
`/data/locales/<language-tag>.json`; missing keys fall back to English.
