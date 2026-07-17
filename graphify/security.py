# Security helpers - URL validation, safe fetch, path guards, label sanitisation
from __future__ import annotations

import html
import http.client
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import ipaddress
import socket

from graphify.paths import GRAPHIFY_OUT, GRAPHIFY_OUT_NAME

_ALLOWED_SCHEMES = {"http", "https"}
_MAX_FETCH_BYTES = 52_428_800   # 50 MB hard cap for binary downloads
_MAX_TEXT_BYTES  = 10_485_760   # 10 MB hard cap for HTML / text

# AWS metadata, link-local, and common cloud metadata endpoints
_BLOCKED_HOSTS = {"metadata.google.internal", "metadata.google.com"}

# RFC 6598 Shared Address Space (CGN) -- is_private misses this on Python <3.11
_CGN_NETWORK = ipaddress.ip_network("100.64.0.0/10")

# RFC 6052 NAT64 Well-Known Prefix -- is_reserved=True in Python but these embed
# public IPv4 addresses and are legitimate public internet traffic, not SSRF vectors.
_NAT64_WKP = ipaddress.ip_network("64:ff9b::/96")


# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------

def _ip_is_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True if *ip* falls in a private/reserved/internal range.

    Shared by validate_url (pre-flight DNS check) and the SSRF-guarded
    connection classes (connect-time check) so both use identical logic.
    NAT64 well-known-prefix addresses are unwrapped to their embedded IPv4
    before the check, since those carry legitimate public traffic.
    """
    # For NAT64 addresses, check the embedded IPv4 instead of the wrapper
    if isinstance(ip, ipaddress.IPv6Address) and ip in _NAT64_WKP:
        ip = ipaddress.ip_address(int(ip) & 0xFFFFFFFF)
    return (
        ip.is_private
        or ip.is_reserved
        or ip.is_loopback
        or ip.is_link_local
        or ip in _CGN_NETWORK
    )


def validate_url(url: str) -> str:
    """Raise ValueError if *url* is not http or https, or targets a private/internal IP.

    Blocks file://, ftp://, data:, and any other scheme that could be used
    for SSRF or local file access. Also blocks requests to private/reserved
    IP ranges (127.x, 10.x, 169.254.x, etc.) and cloud metadata endpoints
    to prevent SSRF in cloud environments.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise ValueError(
            f"Blocked URL scheme '{parsed.scheme}' - only http and https are allowed. "
            f"Got: {url!r}"
        )

    hostname = parsed.hostname
    if hostname:
        # Block known cloud metadata hostnames
        if hostname.lower() in _BLOCKED_HOSTS:
            raise ValueError(
                f"Blocked cloud metadata endpoint '{hostname}'. "
                f"Got: {url!r}"
            )

        # Resolve hostname and block private/reserved IP ranges
        try:
            infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
            for info in infos:
                addr = info[4][0]
                ip = ipaddress.ip_address(addr)
                if _ip_is_blocked(ip):
                    raise ValueError(
                        f"Blocked private/internal IP {addr} (resolved from '{hostname}'). "
                        f"Got: {url!r}"
                    )
        except socket.gaierror as exc:
            raise ValueError(
                f"DNS resolution failed for '{hostname}': {exc}. Got: {url!r}"
            ) from exc

    return url


# ---------------------------------------------------------------------------
# SSRF-guarded connections
#
# Instead of monkey-patching the process-global socket.getaddrinfo (a
# non-thread-safe TOCTOU hazard when multiple fetches run concurrently),
# we subclass the HTTP(S) connection so each connection resolves DNS exactly
# once, validates the resulting IP, and then connects to that exact IP. There
# is no second resolution, so a DNS-rebind attack cannot swap in a private
# address (e.g. 169.254.169.254) between validation and connection.
# ---------------------------------------------------------------------------


def _resolve_and_validate(host: str, port: int) -> tuple[int, str]:
    """Resolve *host* once and return (family, validated_ip) for the first
    address that is not in a blocked range.

    Raises OSError if every resolved address is private/reserved/internal,
    matching the failure mode urllib/http.client expect from connect().
    """
    infos = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
    for family, _type, _proto, _canon, sockaddr in infos:
        addr = sockaddr[0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if _ip_is_blocked(ip):
            raise OSError(
                f"SSRF blocked: IP {addr} resolved from '{host}' is private/reserved"
            )
        return family, addr
    raise OSError(f"SSRF blocked: no usable address resolved from '{host}'")


class _SSRFGuardedHTTPConnection(http.client.HTTPConnection):
    """HTTPConnection that resolves + validates DNS once, then connects to the
    exact validated IP (no second resolution = no DNS-rebind TOCTOU)."""

    def connect(self) -> None:
        family, ip = _resolve_and_validate(self.host, self.port)
        self.sock = socket.create_connection(
            (ip, self.port),
            self.timeout,
            self.source_address,
        )
        if self._tunnel_host:
            self._tunnel()


class _SSRFGuardedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPSConnection variant of _SSRFGuardedHTTPConnection.

    Connects to the validated IP but performs the TLS handshake with
    server_hostname set to the original hostname so SNI / certificate
    validation work correctly (validating against the IP would break TLS).
    """

    def connect(self) -> None:
        family, ip = _resolve_and_validate(self.host, self.port)
        sock = socket.create_connection(
            (ip, self.port),
            self.timeout,
            self.source_address,
        )
        if self._tunnel_host:
            self.sock = sock
            self._tunnel()
            sock = self.sock
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class _SSRFGuardedHTTPHandler(urllib.request.HTTPHandler):
    """urllib handler that routes http:// through _SSRFGuardedHTTPConnection."""

    def http_open(self, req):
        return self.do_open(_SSRFGuardedHTTPConnection, req)


class _SSRFGuardedHTTPSHandler(urllib.request.HTTPSHandler):
    """urllib handler that routes https:// through _SSRFGuardedHTTPSConnection."""

    def https_open(self, req):
        return self.do_open(_SSRFGuardedHTTPSConnection, req)


class _NoFileRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Redirect handler that re-validates every redirect target.

    Prevents open-redirect SSRF attacks where an http:// URL redirects
    to file:// or an internal address.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)          # raises ValueError if scheme is wrong
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _build_opener() -> urllib.request.OpenerDirector:
    # build_opener replaces the default HTTP(S)Handlers with our SSRF-guarded
    # subclasses, so every connection resolves+validates DNS once and connects
    # to that exact IP. Thread-safe: no process-global state is mutated.
    return urllib.request.build_opener(
        _SSRFGuardedHTTPHandler,
        _SSRFGuardedHTTPSHandler,
        _NoFileRedirectHandler,
    )


# ---------------------------------------------------------------------------
# Safe fetch
# ---------------------------------------------------------------------------

def safe_fetch(url: str, max_bytes: int = _MAX_FETCH_BYTES, timeout: int = 30) -> bytes:
    """Fetch *url* and return raw bytes.

    Protections applied:
    - URL scheme validated (http / https only)
    - Redirects re-validated via _NoFileRedirectHandler
    - Response body capped at *max_bytes* (streaming read)
    - Non-2xx status raises urllib.error.HTTPError
    - Network errors propagate as urllib.error.URLError / OSError

    Raises:
        ValueError        - disallowed scheme or redirect target
        urllib.error.HTTPError  - non-2xx HTTP status
        urllib.error.URLError   - DNS / connection failure
        OSError               - size cap exceeded
    """
    validate_url(url)
    opener = _build_opener()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 graphify/1.0"})

    with opener.open(req, timeout=timeout) as resp:
        # urllib raises HTTPError for non-2xx when using urlopen directly;
        # with a custom opener we check manually to be safe.
        status = getattr(resp, "status", None) or getattr(resp, "code", None)
        if status is not None and not (200 <= status < 300):
            raise urllib.error.HTTPError(url, status, f"HTTP {status}", {}, None)

        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = resp.read(65_536)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise OSError(
                    f"Response from {url!r} exceeds size limit "
                    f"({max_bytes // 1_048_576} MB). Aborting download."
                )
            chunks.append(chunk)

    return b"".join(chunks)


def safe_fetch_text(url: str, max_bytes: int = _MAX_TEXT_BYTES, timeout: int = 15) -> str:
    """Fetch *url* and return decoded text (UTF-8, replacing bad bytes).

    Wraps safe_fetch with tighter defaults for HTML / text content.
    """
    raw = safe_fetch(url, max_bytes=max_bytes, timeout=timeout)
    return raw.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Label sanitisation (mirrors code-review-graph's _sanitize_name pattern)
# ---------------------------------------------------------------------------

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")
_MAX_LABEL_LEN = 256


def sanitize_label(text: str | None) -> str:
    """Strip control characters and cap length.

    Safe for embedding in JSON data (inside <script> tags) and plain text.
    For direct HTML injection, wrap the result with html.escape().
    """
    if text is None:
        return ""
    text = _CONTROL_CHAR_RE.sub("", str(text))
    if len(text) > _MAX_LABEL_LEN:
        text = text[:_MAX_LABEL_LEN]
    return text


def validate_store_path(path: str | Path) -> Path:
    """Resolve and validate an embedded Helix store directory."""
    resolved = Path(path).expanduser().resolve()
    if resolved.suffix.lower() == ".json" or resolved.is_file():
        raise ValueError(
            "legacy JSON graphs are obsolete; pass a graph.helix store and rebuild from source"
        )
    if not resolved.is_dir():
        raise FileNotFoundError(f"Helix store not found: {resolved}")
    return resolved


# ---------------------------------------------------------------------------
# Metadata sanitisation (recursive, bounded, HTML-safe)
# ---------------------------------------------------------------------------

_METADATA_MAX_VALUE_LEN = 512
_METADATA_MAX_LIST_ITEMS = 50


def _sanitize_metadata_string(value: object) -> str:
    """Return a control-character-free, HTML-escaped, bounded string."""
    text = _CONTROL_CHAR_RE.sub("", str(value))
    text = html.escape(text, quote=True)
    if len(text) > _METADATA_MAX_VALUE_LEN:
        text = text[:_METADATA_MAX_VALUE_LEN]
    return text  # html is imported at module level (line 5)


def _sanitize_metadata_value(value: object) -> object:
    """Sanitize a metadata value while preserving simple JSON-compatible types."""
    if isinstance(value, bool):
        # bool is a subclass of int — must be checked first to avoid coercion.
        return value
    if isinstance(value, str):
        return _sanitize_metadata_string(value)
    if isinstance(value, dict):
        return sanitize_metadata(value)
    if isinstance(value, (list, tuple)):
        return [_sanitize_metadata_value(item) for item in value[:_METADATA_MAX_LIST_ITEMS]]
    if isinstance(value, (int, float)) or value is None:
        return value
    return _sanitize_metadata_string(value)


def sanitize_metadata(metadata: Mapping[str, Any] | None) -> dict[str, object]:
    """Sanitize metadata keys and values before graph export.

    Metadata is less constrained than node labels: it can contain nested
    dicts, lists, source snippets, external index symbols, and docstring
    text. This helper keeps the data JSON-compatible, strips control
    characters, escapes HTML-sensitive characters in strings, caps long
    strings/lists, and drops entries whose key becomes empty after
    sanitization.
    """
    if metadata is None:
        return {}

    result: dict[str, object] = {}
    for key, value in metadata.items():
        clean_key = _sanitize_metadata_string(key)
        if not clean_key:
            continue
        result[clean_key] = _sanitize_metadata_value(value)
    return result
