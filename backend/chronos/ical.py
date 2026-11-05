"""iCalendar (RFC 5545) parsing into Chronos event records, using the `icalendar` library.

Read-only: Chronos never writes back to an imported file or subscribed feed. Each VEVENT
keeps its UID and RECURRENCE-ID as provenance; (UID, RECURRENCE-ID) is the identity used to
match repeated imports and refreshes against stable Chronos UUIDs."""

import hashlib
import json
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

import icalendar

from chronos.recurrence import build_rule
from chronos.util import UTC, instant

MAX_EVENTS = 20000
STATUSES = {"CONFIRMED": "confirmed", "TENTATIVE": "tentative", "CANCELLED": "cancelled"}
PREFERRED = ("Europe/", "America/", "Asia/", "Australia/", "Pacific/", "Africa/", "Atlantic/")


class FeedError(ValueError):
    """The content is not a usable iCalendar calendar."""


def valid_zone(name) -> bool:
    if not name or not isinstance(name, str) or len(name) > 64:
        return False
    try:
        ZoneInfo(name)
        return True
    except (ZoneInfoNotFoundError, ValueError):
        return False


@lru_cache(maxsize=64)
def _equivalent_zone(label: str, offsets: tuple) -> str | None:
    zones = sorted(
        (z for z in available_timezones() if "/" in z and not z.startswith(("Etc/", "SystemV/"))),
        key=lambda z: (next((i for i, p in enumerate(PREFERRED) if z.startswith(p)), 99), z),
    )
    for name in zones:
        zone = ZoneInfo(name)
        if all(zone.utcoffset(moment) == offset for moment, offset in offsets):
            return name
    return None


def zone_name(value: datetime, warnings: list) -> str | None:
    """IANA name for an aware datetime's zone, matching custom VTIMEZONEs by behaviour."""
    tz = value.tzinfo
    key = getattr(tz, "key", None)
    if key and valid_zone(key):
        return key
    if tz is UTC or str(tz) in {"UTC", "UTC+00:00"}:
        return "UTC"
    year = value.year
    samples = tuple(
        (moment, moment.replace(tzinfo=tz).utcoffset())
        for moment in (datetime(y, m, 15, 12) for y in (year, year + 1) for m in range(1, 13))
    )
    label = str(getattr(tz, "_s", None) or tz)
    match = _equivalent_zone(label, samples)
    if match:
        warnings.append(f"Time zone “{label}” was matched to {match}.")
        return match
    return None


def occurrence_key(value, fallback_zone: str) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=ZoneInfo(fallback_zone))
        return instant(value)
    return value.isoformat()


def _text(component, name, limit):
    value = component.get(name)
    if value is None:
        return ""
    if isinstance(value, list):
        value = value[0]
    return str(value).strip()[:limit]


def _dates(component, name):
    value = component.get(name)
    if value is None:
        return []
    lists = value if isinstance(value, list) else [value]
    return [item.dt for entry in lists for item in getattr(entry, "dts", [entry])]


def parse_event(component, fallback_zone: str, warnings: list) -> dict:
    start_prop = component.get("DTSTART")
    if start_prop is None:
        raise ValueError("Event has no start (DTSTART)")
    start = start_prop.dt
    summary = _text(component, "SUMMARY", 500) or "Untitled"
    all_day = isinstance(start, date) and not isinstance(start, datetime)
    end = component.get("DTEND").dt if component.get("DTEND") is not None else None
    if end is None and component.get("DURATION") is not None:
        end = start + component.decoded("DURATION")
    if all_day:
        if isinstance(end, datetime):
            end = end.date()
        end = end if isinstance(end, date) and end > start else start + timedelta(days=1)
        zone = None
        start_text, end_text = start.isoformat(), end.isoformat()
    else:
        if end is None or not isinstance(end, datetime):
            end = start
        if start.tzinfo is None:
            zone = fallback_zone
            start = start.replace(tzinfo=ZoneInfo(zone))
        else:
            zone = zone_name(start, warnings)
            if zone is None:
                warnings.append(f"“{summary}”: unknown time zone, kept as UTC.")
                zone = "UTC"
        if end.tzinfo is None:
            end = end.replace(tzinfo=start.tzinfo)
        if end < start:
            end = start
        start_text, end_text = instant(start), instant(end)
    rrule = None
    rule_value = component.get("RRULE")
    if rule_value is not None:
        if isinstance(rule_value, list):
            warnings.append(f"“{summary}”: only the first of several RRULEs is used.")
            rule_value = rule_value[0]
        rrule = rule_value.to_ical().decode()
        anchor = datetime.combine(start, time()) if all_day else start.astimezone(ZoneInfo(zone))
        build_rule(rrule, anchor)  # raises on rules dateutil cannot evaluate
    if component.get("RDATE") is not None:
        warnings.append(f"“{summary}”: extra dates (RDATE) are not supported and were ignored.")
    exdates = sorted(
        {occurrence_key(v, zone or fallback_zone) for v in _dates(component, "EXDATE")}
    )
    if all_day:
        exdates = sorted({e[:10] for e in exdates})
    recurrence = component.get("RECURRENCE-ID")
    recurrence_id = ""
    if recurrence is not None:
        value = recurrence.dt
        recurrence_id = (
            value.isoformat()
            if not isinstance(value, datetime)
            else occurrence_key(value, zone or fallback_zone)
        )
    try:
        sequence = int(str(component.get("SEQUENCE", 0)))
    except ValueError:
        sequence = 0
    record = {
        "uid": _text(component, "UID", 255),
        "recurrence_id": recurrence_id,
        "title": summary,
        "description": _text(component, "DESCRIPTION", 20000),
        "location": _text(component, "LOCATION", 500),
        "all_day": all_day,
        "start": start_text,
        "end": end_text,
        "time_zone": zone,
        "rrule": rrule,
        "exdates": exdates,
        "status": STATUSES.get(_text(component, "STATUS", 20).upper(), "confirmed"),
        "sequence": sequence,
    }
    if not record["uid"]:
        digest = hashlib.sha256(f"{start_text}|{summary}|{recurrence_id}".encode()).hexdigest()
        record["uid"] = "chronos-derived-" + digest[:32]
        warnings.append(f"“{summary}”: no UID, a stable one was derived from its content.")
    record["content_hash"] = hashlib.sha256(
        json.dumps({k: v for k, v in record.items() if k != "sequence"}, sort_keys=True).encode()
    ).hexdigest()
    return record


def parse_calendar(content, default_zone: str) -> dict:
    """Parse iCalendar content. Raises FeedError when nothing usable is there."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    if b"BEGIN:VCALENDAR" not in content[:4096].upper():
        raise FeedError("This is not an iCalendar file (BEGIN:VCALENDAR is missing).")
    try:
        calendar = icalendar.Calendar.from_ical(content)
    except Exception as exc:  # the library raises several exception types for bad input
        raise FeedError("The calendar could not be read: it is not valid iCalendar.") from exc
    name = _text(calendar, "X-WR-CALNAME", 100)
    calendar_zone = _text(calendar, "X-WR-TIMEZONE", 64)
    fallback = calendar_zone if valid_zone(calendar_zone) else default_zone
    events, errors, warnings = {}, [], []
    duplicates = 0
    ignored = {
        "VTODO": len(calendar.walk("VTODO")),
        "VJOURNAL": len(calendar.walk("VJOURNAL")),
    }
    for component in calendar.walk("VEVENT"):
        if len(events) >= MAX_EVENTS:
            warnings.append(f"Only the first {MAX_EVENTS} events were read.")
            break
        try:
            record = parse_event(component, fallback, warnings)
        except Exception as exc:
            errors.append(
                {
                    "uid": _text(component, "UID", 255),
                    "title": _text(component, "SUMMARY", 200) or "Untitled",
                    "error": str(exc)[:200] or "Unreadable event",
                }
            )
            continue
        key = (record["uid"], record["recurrence_id"])
        if key in events:
            duplicates += 1
            if record["sequence"] < events[key]["sequence"]:
                continue
        events[key] = record
    return {
        "name": name,
        "time_zone": fallback,
        "events": list(events.values()),
        "errors": errors,
        "warnings": list(dict.fromkeys(warnings))[:50],
        "duplicates_in_file": duplicates,
        "ignored": {k: v for k, v in ignored.items() if v},
    }
