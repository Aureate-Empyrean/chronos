"""Outbound fetching of user-supplied calendar URLs with SSRF protection (ADR 0010).

Every hop: allowed scheme and port, no credentials, DNS resolution in-process, every
address must be globally routable, and the connection is pinned to the vetted address
(TLS still verifies the hostname). Redirects are followed manually and re-validated.
URLs are never logged or included in error messages."""

import ipaddress
import socket
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

ALLOWED_PORTS = {80, 443, 8080, 8443}
MAX_BYTES = 5 * 1024 * 1024
MAX_REDIRECTS = 3
TIMEOUT = httpx.Timeout(15.0, connect=8.0)
USER_AGENT = "Chronos/0.1 (Aureate Empyrean; calendar subscription)"


class FetchError(Exception):
    """A user-presentable failure that never contains the URL."""


def normalize(url: str) -> str:
    url = (url or "").strip()
    if len(url) > 2048:
        raise FetchError("The address is too long.")
    if url.lower().startswith("webcal://"):
        url = "https://" + url[9:]
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        raise FetchError("Use an https:// (or http://, webcal://) calendar address.")
    if parts.username or parts.password or "@" in parts.netloc:
        raise FetchError("Addresses with a user name or password are not supported.")
    if not parts.hostname:
        raise FetchError("The address has no host.")
    try:
        port = parts.port
    except ValueError as exc:
        raise FetchError("The address has an invalid port.") from exc
    if port is not None and port not in ALLOWED_PORTS:
        raise FetchError("Only ports 80, 443, 8080 and 8443 are allowed.")
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", parts.query, ""))


def display(url: str) -> str:
    """Masked form for the interface: scheme and host only."""
    try:
        parts = urlsplit(url)
        return f"{parts.scheme}://{parts.hostname}/…"
    except ValueError:
        return "…"


def public(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast and not ip.is_reserved


def default_resolver(host: str, port: int) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise FetchError("The calendar host could not be found.") from exc
    return list(dict.fromkeys(info[4][0] for info in infos))


def vet(url: str, resolver):
    parts = urlsplit(url)
    host = parts.hostname
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        literal = ipaddress.ip_address(host)
        addresses = [str(literal)]
    except ValueError:
        if host.endswith((".local", ".internal", ".localhost", ".lan", ".home.arpa")):
            raise FetchError("Local network addresses are not allowed.") from None
        addresses = resolver(host, port)
    if not addresses:
        raise FetchError("The calendar host could not be found.")
    if not all(public(a) for a in addresses):
        raise FetchError("Local, private and reserved network addresses are not allowed.")
    return parts, host, port, addresses[0]


def fetch(url, *, etag=None, last_modified=None, transport=None, resolver=default_resolver):
    """Fetch a feed. Returns (status, body, headers); status 304 means unchanged."""
    current = normalize(url)
    for _ in range(MAX_REDIRECTS + 1):
        parts, host, port, address = vet(current, resolver)
        pinned_host = f"[{address}]" if ":" in address else address
        default_port = 443 if parts.scheme == "https" else 80
        netloc = pinned_host + ("" if port == default_port else f":{port}")
        target = urlunsplit((parts.scheme, netloc, parts.path or "/", parts.query, ""))
        headers = {
            "Host": host + ("" if port == default_port else f":{port}"),
            "User-Agent": USER_AGENT,
            "Accept": "text/calendar, application/ics;q=0.9, text/plain;q=0.5, */*;q=0.1",
        }
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        extensions = {"sni_hostname": host} if parts.scheme == "https" else {}
        try:
            with httpx.Client(
                transport=transport, timeout=TIMEOUT, follow_redirects=False, trust_env=False
            ) as client:
                with client.stream(
                    "GET", target, headers=headers, extensions=extensions
                ) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location:
                            raise FetchError("The calendar server sent an invalid redirect.")
                        current = normalize(urljoin(current, location))
                        continue
                    if response.status_code == 304:
                        return 304, b"", dict(response.headers)
                    if response.status_code in {401, 403}:
                        raise FetchError("The calendar server refused access.")
                    if response.status_code == 404 or response.status_code == 410:
                        raise FetchError("The calendar was not found at this address.")
                    if response.status_code != 200:
                        raise FetchError(
                            f"The calendar server answered with HTTP {response.status_code}."
                        )
                    declared = response.headers.get("content-length")
                    if declared and declared.isdigit() and int(declared) > MAX_BYTES:
                        raise FetchError("The calendar is larger than 5 MiB.")
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_BYTES:
                            raise FetchError("The calendar is larger than 5 MiB.")
                    return 200, bytes(body), dict(response.headers)
        except httpx.TimeoutException as exc:
            raise FetchError("The calendar server did not respond in time.") from exc
        except httpx.HTTPError as exc:
            raise FetchError("The calendar server could not be reached.") from exc
    raise FetchError("The calendar address redirects too many times.")
