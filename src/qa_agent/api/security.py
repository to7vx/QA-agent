"""SSRF protection for user-submitted target URLs.

Users submit arbitrary URLs that the server's headless browser will fetch. We
must refuse to fetch anything that could reach internal infrastructure: the
cloud metadata endpoint, loopback, link-local, and private RFC1918 ranges, plus
non-http(s) schemes.

This is a best-effort guard at submit time. The browser also runs in a
locked-down container with no host-network access as the real boundary.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeURLError(ValueError):
    """Raised when a target URL is rejected by the SSRF guard."""


_ALLOWED_SCHEMES = {"http", "https"}


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        # 169.254.169.254 (cloud metadata) is link-local, already covered, but
        # be explicit for IPv6 ULA too.
        or (ip.version == 6 and ip.is_site_local)  # type: ignore[union-attr]
    )


def validate_target_url(url: str, *, resolve_dns: bool = True) -> str:
    """Return the URL if safe to fetch, else raise :class:`UnsafeURLError`.

    When ``resolve_dns`` is True (production), the hostname is resolved and every
    resolved address is checked — this defeats DNS-rebinding to internal IPs.
    Tests pass ``resolve_dns=False`` to stay offline.
    """
    if not url or not isinstance(url, str):
        raise UnsafeURLError("Empty URL.")

    parsed = urlparse(url)
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise UnsafeURLError(f"Unsupported scheme: {parsed.scheme!r} (only http/https).")

    host = parsed.hostname
    if not host:
        raise UnsafeURLError("URL has no host.")

    lowered = host.lower()
    if lowered == "localhost" or lowered.endswith(".localhost"):
        raise UnsafeURLError("Refusing to fetch localhost.")

    # If the host is already a literal IP, check it directly. (Parse separately
    # so we don't accidentally catch our own UnsafeURLError, which subclasses
    # ValueError, in the except below.)
    literal_ip: ipaddress.IPv4Address | ipaddress.IPv6Address | None
    try:
        literal_ip = ipaddress.ip_address(host)
    except ValueError:
        literal_ip = None  # not a literal IP — it's a hostname
    if literal_ip is not None:
        if _is_blocked_ip(literal_ip):
            raise UnsafeURLError(f"Refusing to fetch internal address: {host}")
        return url

    if resolve_dns:
        try:
            infos = socket.getaddrinfo(host, parsed.port or None, proto=socket.IPPROTO_TCP)
        except socket.gaierror as exc:
            raise UnsafeURLError(f"Could not resolve host {host!r}: {exc}") from exc
        for info in infos:
            addr = info[4][0]
            try:
                ip = ipaddress.ip_address(addr)
            except ValueError:
                continue
            if _is_blocked_ip(ip):
                raise UnsafeURLError(f"Host {host!r} resolves to an internal address ({addr}).")

    return url
