"""SSRF guard for user-supplied web URLs."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

from advp.ingest.files import IngestError


class BlockedUrlError(ValueError, IngestError):
    """Rejected URL that is unsupported or points at a local/private host."""

    code = "web_url_blocked"
    status_code = 400

    def __init__(self, message: str, hint: str | None = None) -> None:
        IngestError.__init__(self, message, hint)


def validate_public_url(url: str, *, allow_private: bool = False) -> str:
    """Return the URL when it is a public HTTP(S) target, else raise."""
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        raise BlockedUrlError(
            "only http and https URLs are supported",
            hint="use an HTTP(S) page URL",
        )
    host = parsed.hostname or ""
    if not host:
        raise BlockedUrlError("URL has no host", hint="include a host name in the URL")
    if allow_private:
        return url
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise BlockedUrlError(
            "host could not be resolved",
            hint="check the host name and network access",
        ) from exc
    for info in infos:
        validate_public_address(str(info[4][0]))
    return url


def validate_public_address(address: str) -> str:
    """Return a peer IP address when it is public, else raise."""
    ip = ipaddress.ip_address(address)
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    ):
        raise BlockedUrlError(
            "private or local network addresses are not allowed",
            hint="use a public HTTP(S) URL",
        )
    return address
