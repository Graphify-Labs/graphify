from __future__ import annotations

import re
import typing as t
from urllib.parse import quote

from .._internal import _plain_int
from ..exceptions import SecurityError
from ..http import parse_set_header
from ..urls import uri_to_iri

_host_re = re.compile(
    r"""
    (
        [a-z0-9.-]+  # domain or ipv4
    |
        \[[a-f0-9]*:[a-f0-9.:]+]  # ipv6
    )
    (?::[0-9]+)?  # optional port
    """,
    flags=re.ASCII | re.IGNORECASE | re.VERBOSE,
)


def host_is_trusted(
    hostname: str | None, trusted_list: t.Collection[str] | None = None
) -> bool:
    """Perform some checks on a ``Host`` header ``host:port``. The host must be
    made up of valid characters, but this does not check validity beyond that.
    If a list of trusted domains is given, the domain must match one.

    :param hostname: The ``Host`` header ``host:port`` to check.
    :param trusted_list: A list of trusted domains to match. These should
        already be IDNA encoded, but will be encoded if needed. The port is
        ignored for this check. If a name starts with a dot it will match as a
        suffix, accepting all subdomains. If empty or ``None``, all domains are
        allowed.

    .. versionchanged:: 3.2
        The value's characters are validated.

    .. versionchanged:: 3.2
        ``trusted_list`` defaults to ``None``.

    .. versionadded:: 0.9
    """
    if not hostname:
        return False

    if _host_re.fullmatch(hostname) is None:
        return False

    hostname = hostname.partition(":")[0]

    if not trusted_list:
        return True

    if isinstance(trusted_list, str):
        trusted_list = [trusted_list]

    for ref in trusted_list:
        if ref.startswith("."):
            ref = ref[1:]
            suffix_match = True
        else:
            suffix_match = False

        try:
            ref = ref.partition(":")[0].encode("idna").decode("ascii")
        except UnicodeEncodeError:
            return False

        if ref == hostname or (suffix_match and hostname.endswith(f".{ref}")):
            return True

    return False


def get_host(
    scheme: str,
    host_header: str | None,
    server: tuple[str, int | None] | None = None,
    trusted_hosts: t.Collection[str] | None = None,
) -> str:
    """Get and validate a request's ``host:port`` based on the given values.

    The ``Host`` header sent by the client is preferred. Otherwise, the server's
    configured address is used. The port is omitted if it matches the standard
    HTTP or HTTPS ports.

    The value is passed through :func:`host_is_trusted`. The host must be made
    up of valid characters, but this does not check validity beyond that. If a
    list of trusted domains is given, the domain must match one.

    If the host header is not available, such as for HTTP/0.9 and 1.0, or it has
    invalid characters, the empty string is returned. Subdomain and host
    routing, and external URL building, will not work in these cases.

    :param scheme: The protocol of the request. Used to omit the standard ports
        80 and 443.
    :param host_header: The ``Host`` header value.
    :param server: The server's configured address ``(host, port)``. The server
        may be using a Unix socket and give ``(path, None)``; this is ignored as
        it would not produce a useful host value.
    :param trusted_hosts: A list of trusted domains to match. These should
        already be IDNA encoded, but will be encoded if needed. The port is
        ignored for this check. If a name starts with a dot it will match as a
        suffix, accepting all subdomains. If empty or ``None``, all domains are
        allowed.

    :return: Host, with port if necessary.
    :raise .SecurityError: If the host is not trusted.

    .. versionchanged:: 3.1.8
        The empty string is again returned if no host header value is available,
        or if the characters are invalid.

    .. versionchanged:: 3.1.7
        The characters of the host value are validated. The empty string is no
        longer allowed if no header value is available.

    .. versionchanged:: 3.2
        When using the server address, Unix sockets are ignored.

    .. versionchanged:: 3.1.3
        If ``SERVER_NAME`` is IPv6, it is wrapped in ``[]``.
    """
    if host_header is not None:
        host = host_header
    # The port server[1] will be None for a Unix socket. Ignore in that case.
    elif server is not None and server[1] is not None:
        host = server[0]

        # If SERVER_NAME is IPv6, wrap it in [] to match Host header.
        # Check for : because domain or IPv4 can't have that.
        if ":" in host and host[0] != "[":
            host = f"[{host}]"

        host = f"{host}:{server[1]}"
    else:
        # Pass through empty host from HTTP/0.9 and 1.0.
        return ""

    if scheme in {"http", "ws"}:
        host = host.removesuffix(":80")
    elif scheme in {"https", "wss"}:
        host = host.removesuffix(":443")

    if not host_is_trusted(host, trusted_hosts):
        if trusted_hosts:
            raise SecurityError(f"Host {host!r} is not trusted.")

        # Invalid characters, treat as empty.
        return ""

    return host


def get_current_url(
    scheme: str,
    host: str,
    root_path: str | None = None,
    path: str | None = None,
    query_string: bytes | None = None,
) -> str:
    """Recreate the URL for a request. If an optional part isn't
    provided, it and subsequent parts are not included in the URL.

    The URL is an IRI, not a URI, so it may contain Unicode characters.
    Use :func:`~werkzeug.urls.iri_to_uri` to convert it to ASCII.

    :param scheme: The protocol the request used, like ``"https"``.
    :param host: The host the request was made to. See :func:`get_host`.
    :param root_path: Prefix that the application is mounted under. This
        is prepended to ``path``.
    :param path: The path part of the URL after ``root_path``.
    :param query_string: The portion of the URL after the "?".
    """
    url = [scheme, "://", host]

    if root_path is None:
        url.append("/")
        return uri_to_iri("".join(url))

    # safe = https://url.spec.whatwg.org/#url-path-segment-string
    # as well as percent for things that are already quoted
    url.append(quote(root_path.rstrip("/"), safe="!$&'()*+,/:;=@%"))
    url.append("/")

    if path is None:
        return uri_to_iri("".join(url))

    url.append(quote(path.lstrip("/"), safe="!$&'()*+,/:;=@%"))

    if query_string:
        url.append("?")
        url.append(quote(query_string, safe="!$&'()*+,/:;=?@%"))

    return uri_to_iri("".join(url))


def get_content_length(
    http_content_length: str | None = None,
    http_transfer_encoding: str | None = None,
) -> int | None:
    """Return the ``Content-Length`` header value as an int. If the header is not given
    or the ``Transfer-Encoding`` header is ``chunked``, ``None`` is returned to indicate
    a streaming request. If the value is not an integer, or negative, 0 is returned.

    :param http_content_length: The Content-Length HTTP header.
    :param http_transfer_encoding: The Transfer-Encoding HTTP header.

    .. versionadded:: 2.2
    """
    if (
        http_transfer_encoding is not None
        and "chunked" in parse_set_header(http_transfer_encoding)
    ) or http_content_length is None:
        return None

    try:
        return max(0, _plain_int(http_content_length))
    except ValueError:
        return 0
