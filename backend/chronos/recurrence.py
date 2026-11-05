"""RFC 5545 recurrence expansion with python-dateutil.

Timed series expand in their own IANA zone so wall-clock times survive DST changes;
all-day series expand over naive dates. Occurrence keys are the canonical start text
(UTC instant or ISO date) and match iCalendar RECURRENCE-ID and EXDATE values."""

import json
from datetime import date, datetime, time, timedelta
from itertools import islice
from zoneinfo import ZoneInfo

from dateutil.rrule import rrulestr

from chronos.util import UTC, instant, parse_instant

MAX_OCCURRENCES = 2000
MAX_BOUNDED = 10000
FREQUENCIES = {"DAILY", "WEEKLY", "MONTHLY", "YEARLY"}


def rule_parts(text: str) -> dict:
    text = text.strip()
    if text.upper().startswith("RRULE:"):
        text = text[6:]
    parts = {}
    for part in text.split(";"):
        if "=" in part:
            key, value = part.split("=", 1)
            parts[key.strip().upper()] = value.strip()
    return parts


def build_rule(text: str, dtstart: datetime):
    """Parse an RRULE for dtstart, normalizing UNTIL to what dateutil requires."""
    parts = rule_parts(text)
    if parts.get("FREQ") not in FREQUENCIES | {"HOURLY", "MINUTELY", "SECONDLY"}:
        raise ValueError("Unsupported recurrence frequency")
    until = parts.get("UNTIL")
    if until:
        if dtstart.tzinfo is not None and not until.endswith("Z"):
            # RFC 5545 requires UTC UNTIL with a zoned DTSTART; real feeds often omit it.
            if len(until) == 8:
                local = datetime.strptime(until, "%Y%m%d").replace(hour=23, minute=59, second=59)
            else:
                local = datetime.strptime(until[:15], "%Y%m%dT%H%M%S")
            parts["UNTIL"] = (
                local.replace(tzinfo=dtstart.tzinfo).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
            )
        elif dtstart.tzinfo is None and until.endswith("Z"):
            parts["UNTIL"] = until[:-1]
    normalized = ";".join(f"{key}={value}" for key, value in parts.items())
    return rrulestr(normalized, dtstart=dtstart)


def validate_native_rule(text: str) -> str:
    """Native events: daily or slower, a bounded grammar, normalized text."""
    if len(text) > 300:
        raise ValueError("Recurrence rule is too long")
    parts = rule_parts(text)
    if parts.get("FREQ") not in FREQUENCIES:
        raise ValueError("Repeat daily, weekly, monthly or yearly")
    allowed = {"FREQ", "INTERVAL", "COUNT", "UNTIL", "BYDAY", "BYMONTHDAY", "BYMONTH", "WKST"}
    if set(parts) - allowed:
        raise ValueError("Unsupported recurrence option")
    if "COUNT" in parts and "UNTIL" in parts:
        raise ValueError("Use either an end date or a number of occurrences")
    if "COUNT" in parts and not (parts["COUNT"].isdigit() and 1 <= int(parts["COUNT"]) <= 1000):
        raise ValueError("Occurrences must be between 1 and 1000")
    if "INTERVAL" in parts and not (
        parts["INTERVAL"].isdigit() and 1 <= int(parts["INTERVAL"]) <= 99
    ):
        raise ValueError("Repeat interval must be between 1 and 99")
    build_rule(text, datetime(2000, 1, 1))
    return ";".join(f"{key}={value}" for key, value in parts.items())


def _start(row):
    if row["all_day"]:
        return datetime.combine(date.fromisoformat(row["start"]), time())
    zone = ZoneInfo(row["time_zone"]) if row["time_zone"] else UTC
    return parse_instant(row["start"]).astimezone(zone)


def _duration(row) -> timedelta:
    if row["all_day"]:
        return date.fromisoformat(row["end"]) - date.fromisoformat(row["start"])
    return parse_instant(row["end"]) - parse_instant(row["start"])


def series_end(row) -> str | None:
    """Upper index bound of a series, or None when it is unbounded (or very long)."""
    duration = _duration(row)
    if not row["rrule"]:
        last = _start(row)
    else:
        parts = rule_parts(row["rrule"])
        if "COUNT" not in parts and "UNTIL" not in parts:
            return None
        occurrences = list(islice(build_rule(row["rrule"], _start(row)), MAX_BOUNDED + 1))
        if not occurrences or len(occurrences) > MAX_BOUNDED:
            return None
        last = occurrences[-1]
    if row["all_day"]:
        end_day = (last + duration).date()
        bound = datetime.combine(end_day, time(), UTC) + timedelta(hours=15)
        return instant(bound)
    return instant(last + duration)


def expand(row, window_start: datetime, window_end: datetime, skip=frozenset()):
    """Yield (key, start, end) occurrences overlapping the UTC window.

    All-day occurrences yield ISO dates (end exclusive); timed ones yield UTC datetimes."""
    duration = _duration(row)
    excluded = set(skip)
    if row["exdates"]:
        excluded.update(json.loads(row["exdates"]))
    dtstart = _start(row)
    if row["all_day"]:
        lo = datetime.combine(window_start.date(), time()) - duration - timedelta(days=1)
        hi = datetime.combine(window_end.date(), time()) + timedelta(days=1)
        if row["rrule"]:
            starts = islice(build_rule(row["rrule"], dtstart).xafter(lo, inc=True), MAX_OCCURRENCES)
        else:
            starts = [dtstart]
        for start in starts:
            if start > hi:
                break
            end = start + duration
            key = start.date().isoformat()
            if key in excluded or end <= lo:
                continue
            yield key, start.date().isoformat(), end.date().isoformat()
        return
    if row["rrule"]:
        lo = window_start - duration
        starts = islice(
            build_rule(row["rrule"], dtstart).xafter(lo.astimezone(dtstart.tzinfo), inc=True),
            MAX_OCCURRENCES,
        )
    else:
        starts = [dtstart]
    for start in starts:
        start_utc = start.astimezone(UTC)
        if start_utc >= window_end:
            break
        end_utc = start_utc + duration
        key = instant(start_utc)
        # Ends before the window; a zero-length event exactly at its start still counts.
        if key in excluded or end_utc < window_start or (duration and end_utc == window_start):
            continue
        yield key, start_utc, end_utc


def describe_parts(text: str | None) -> dict | None:
    return rule_parts(text) if text else None
