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
subscription (`lyra.dated-items.changed`, `mnemosyne.resource.changed` as hints), references
(create, read, resolve Lyra titles and Mnemosyne tasks), projection reads (`dated-items` from
Lyra and Mnemosyne), backup v1. No environment variables or secrets are needed.

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

Tests cover DST-correct recurrence, all-day dates, validation, the import matrix (overrides,
cancelled occurrences, EXDATE, floating and custom zones, missing UIDs, broken components,
re-import), subscription updates/removals/304/empty-feed guard, SSRF refusals (private and
mapped addresses, metadata IPs, ports, credentials, `.local`, redirects to private hosts, size
and content checks), address pinning, projection reconciliation (paging, failures keep data,
invalid and foreign items rejected), Mnemosyne opt-in/opt-out, planning with references,
resolver policy, enumeration, backup round trip, the gateway key and the shared design files.

## Localization

Every interface string goes through the message catalog (`frontend/locales/en.json`, keys
are the English source text; `{placeholders}`; plural pairs). Dates, times, weekdays and
relative times use `Intl` with the Nexus locale and your time zone and week start. Additional
catalogs (for example `sk.json`) can be added to `frontend/locales` or to the data volume at
`/data/locales/<language-tag>.json`; missing keys fall back to English.
