import os
import re
import time
import unicodedata
import uuid
from datetime import date, datetime, timedelta, timezone

UTC = timezone.utc
REF = re.compile(
    r"^nexus:v1:([a-z][a-z0-9-]{0,47}):([a-z][a-z0-9-]{0,47}):([a-zA-Z0-9][a-zA-Z0-9._~-]{0,127})$"
)
COLOR = r"^#[0-9a-fA-F]{6}$"


def uuid7() -> str:
    """RFC 9562 UUIDv7: 48-bit Unix milliseconds, version, 74 random bits."""
    ms = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10), "big")
    value = (ms & ((1 << 48) - 1)) << 80
    value |= 0x7 << 76
    value |= ((rand >> 62) & 0xFFF) << 64
    value |= 0b10 << 62
    value |= rand & ((1 << 62) - 1)
    return str(uuid.UUID(int=value))


def now() -> datetime:
    return datetime.now(UTC)


def iso_now() -> str:
    return instant(now())


def instant(value: datetime) -> str:
    """Canonical UTC instant text, second precision."""
    return value.astimezone(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_instant(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


def day_bounds(start: str, end: str) -> tuple[str, str]:
    """Index bounds for a floating date range: wide enough for any display zone."""
    a = datetime.combine(date.fromisoformat(start), datetime.min.time(), UTC) - timedelta(hours=15)
    b = datetime.combine(date.fromisoformat(end), datetime.min.time(), UTC) + timedelta(hours=15)
    return instant(a), instant(b)


def fold(value: str | None) -> str:
    """Case- and accent-insensitive form of a text, for searching."""
    decomposed = unicodedata.normalize("NFKD", value or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def reference(kind: str, rid: str) -> str:
    return f"nexus:v1:chronos:{kind}:{rid}"
