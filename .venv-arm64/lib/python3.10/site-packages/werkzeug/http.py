from __future__ import annotations

import email.utils
import re
import typing as t
import warnings
from datetime import date
from datetime import datetime
from datetime import time
from datetime import timedelta
from datetime import timezone
from enum import Enum
from hashlib import sha1
from time import mktime
from time import struct_time
from urllib.parse import quote
from urllib.parse import unquote

from ._internal import _dt_as_utc
from ._internal import _plain_int

if t.TYPE_CHECKING:
    from _typeshed.wsgi import WSGIEnvironment

_token_chars = frozenset(
    "!#$%&'*+-.0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ^_`abcdefghijklmnopqrstuvwxyz|~"
)
_etag_re = re.compile(r'([Ww]/)?(?:"(.*?)"|(.*?))(?:\s*,\s*|$)')
_entity_headers = frozenset(
    [
        "allow",
        "content-encoding",
        "content-language",
        "content-length",
        "content-location",
        "content-md5",
        "content-range",
        "content-type",
        "expires",
        "last-modified",
    ]
)
_hop_by_hop_headers = frozenset(
    [
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    ]
)
HTTP_STATUS_CODES = {
    100: "Continue",
    101: "Switching Protocols",
    102: "Processing",
    103: "Early Hints",  # see RFC 8297
    200: "OK",
    201: "Created",
    202: "Accepted",
    203: "Non Authoritative Information",
    204: "No Content",
    205: "Reset Content",
    206: "Partial Content",
    207: "Multi Status",
    208: "Already Reported",  # see RFC 5842
    226: "IM Used",  # see RFC 3229
    300: "Multiple Choices",
    301: "Moved Permanently",
    302: "Found",
    303: "See Other",
    304: "Not Modified",
    305: "Use Proxy",
    306: "Switch Proxy",  # unused
    307: "Temporary Redirect",
    308: "Permanent Redirect",
    400: "Bad Request",
    401: "Unauthorized",
    402: "Payment Required",  # unused
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    406: "Not Acceptable",
    407: "Proxy Authentication Required",
    408: "Request Timeout",
    409: "Conflict",
    410: "Gone",
    411: "Length Required",
    412: "Precondition Failed",
    413: "Request Entity Too Large",
    414: "Request URI Too Long",
    415: "Unsupported Media Type",
    416: "Requested Range Not Satisfiable",
    417: "Expectation Failed",
    418: "I'm a teapot",  # see RFC 2324
    421: "Misdirected Request",  # see RFC 7540
    422: "Unprocessable Entity",
    423: "Locked",
    424: "Failed Dependency",
    425: "Too Early",  # see RFC 8470
    426: "Upgrade Required",
    428: "Precondition Required",  # see RFC 6585
    429: "Too Many Requests",
    431: "Request Header Fields Too Large",
    449: "Retry With",  # proprietary MS extension
    451: "Unavailable For Legal Reasons",
    500: "Internal Server Error",
    501: "Not Implemented",
    502: "Bad Gateway",
    503: "Service Unavailable",
    504: "Gateway Timeout",
    505: "HTTP Version Not Supported",
    506: "Variant Also Negotiates",  # see RFC 2295
    507: "Insufficient Storage",
    508: "Loop Detected",  # see RFC 5842
    510: "Not Extended",
    511: "Network Authentication Failed",
}


class COEP(Enum):
    """Cross Origin Embedder Policies"""

    UNSAFE_NONE = "unsafe-none"
    REQUIRE_CORP = "require-corp"


class COOP(Enum):
    """Cross Origin Opener Policies"""

    UNSAFE_NONE = "unsafe-none"
    SAME_ORIGIN_ALLOW_POPUPS = "same-origin-allow-popups"
    SAME_ORIGIN = "same-origin"


def quote_header_value(value: t.Any, allow_token: bool = True) -> str:
    """Add double quotes around a header value. If the header contains only ASCII token
    characters, it will be returned unchanged. If the header contains ``"`` or ``\\``
    characters, they will be escaped with an additional ``\\`` character.

    This is the reverse of :func:`unquote_header_value`.

    :param value: The value to quote. Will be converted to a string.
    :param allow_token: Disable to quote the value even if it only has token characters.

    .. versionchanged:: 3.0
        Passing bytes is not supported.

    .. versionchanged:: 3.0
        The ``extra_chars`` parameter is removed.

    .. versionchanged:: 2.3
        The value is quoted if it is the empty string.

    .. versionadded:: 0.5
    """
    value_str = str(value)

    if not value_str:
        return '""'

    if allow_token:
        token_chars = _token_chars

        if token_chars.issuperset(value_str):
            return value_str

    value_str = value_str.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{value_str}"'


_unslash_re = re.compile(r"\\(.)", re.A)


def unquote_header_value(value: str) -> str:
    """Remove double quotes and backslash escapes from a header value.

    This is the reverse of :func:`quote_header_value`.

    :param value: The header value to unquote.

    .. versionchanged:: 3.2
        Removes escape preceding any character.

    .. versionchanged:: 3.0
        The ``is_filename`` parameter is removed.
    """
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return _unslash_re.sub(r"\g<1>", value[1:-1])

    return value


def dump_options_header(header: str | None, options: t.Mapping[str, t.Any]) -> str:
    """Produce a header value and ``key=value`` parameters separated by semicolons
    ``;``. For example, the ``Content-Type`` header.

    .. code-block:: python

        dump_options_header("text/html", {"charset": "UTF-8"})
        'text/html; charset=UTF-8'

    This is the reverse of :func:`parse_options_header`.

    If a value contains non-token characters, it will be quoted.

    If a value is ``None``, the parameter is skipped.

    In some keys for some headers, a UTF-8 value can be encoded using a special
    ``key*=UTF-8''value`` form, where ``value`` is percent encoded. This function will
    not produce that format automatically, but if a given key ends with an asterisk
    ``*``, the value is assumed to have that form and will not be quoted further.

    :param header: The primary header value.
    :param options: Parameters to encode as ``key=value`` pairs.

    .. versionchanged:: 2.3
        Keys with ``None`` values are skipped rather than treated as a bare key.

    .. versionchanged:: 2.2.3
        If a key ends with ``*``, its value will not be quoted.
    """
    segments = []

    if header is not None:
        segments.append(header)

    for key, value in options.items():
        if value is None:
            continue

        if key[-1] == "*":
            segments.append(f"{key}={value}")
        else:
            segments.append(f"{key}={quote_header_value(value)}")

    return "; ".join(segments)


def dump_header(iterable: dict[str, t.Any] | t.Iterable[t.Any]) -> str:
    """Produce a header value from a list of items or ``key=value`` pairs, separated by
    commas ``,``.

    This is the reverse of :func:`parse_list_header`, :func:`parse_dict_header`, and
    :func:`parse_set_header`.

    If a value contains non-token characters, it will be quoted.

    If a value is ``None``, the key is output alone.

    In some keys for some headers, a UTF-8 value can be encoded using a special
    ``key*=UTF-8''value`` form, where ``value`` is percent encoded. This function will
    not produce that format automatically, but if a given key ends with an asterisk
    ``*``, the value is assumed to have that form and will not be quoted further.

    .. code-block:: python

        dump_header(["foo", "bar baz"])
        'foo, "bar baz"'

        dump_header({"foo": "bar baz"})
        'foo="bar baz"'

    :param iterable: The items to create a header from.

    .. versionchanged:: 3.0
        The ``allow_token`` parameter is removed.

    .. versionchanged:: 2.2.3
        If a key ends with ``*``, its value will not be quoted.
    """
    if isinstance(iterable, dict):
        items = []

        for key, value in iterable.items():
            if value is None:
                items.append(key)
            elif key[-1] == "*":
                items.append(f"{key}={value}")
            else:
                items.append(f"{key}={quote_header_value(value)}")
    else:
        items = [quote_header_value(x) for x in iterable]

    return ", ".join(items)


def dump_csp_header(header: ds.ContentSecurityPolicy) -> str:
    """Dump a Content Security Policy header.

    These are structured into policies such as "default-src 'self';
    script-src 'self'".

    .. versionadded:: 1.0.0
       Support for Content Security Policy headers was added.

    """
    return "; ".join(f"{key} {value}" for key, value in header.items())


def parse_list_header(value: str) -> list[str]:
    """Parse a header value that consists of a list of comma separated items according
    to `RFC 9110 <https://httpwg.org/specs/rfc9110.html#abnf.extension>`__.

    Surrounding quotes are removed from items, but internal quotes are left for
    future parsing. Empty values are discarded.

    .. code-block:: python

        parse_list_header('token, "quoted value"')
        ['token', 'quoted value']

    This is the reverse of :func:`dump_header`.

    :param value: The header value to parse.

    .. versionchanged:: 3.2
        Quotes and escapes are kept if only part of an item is quoted. Empty
        values are omitted. An empty list is returned if the value contains an
        unclosed quoted string.
    """
    items = []
    item = ""
    escape = False
    quote = False

    for char in value:
        if escape:
            escape = False
            item += char
            continue

        if quote:
            if char == "\\":
                escape = True
            elif char == '"':
                quote = False

            item += char
            continue

        if char == ",":
            items.append(item)
            item = ""
            continue

        if char == '"':
            quote = True

        item += char

    if quote:
        # invalid, unclosed quoted string
        return []

    items.append(item)
    return [
        unquote_header_value(item) for item in (item.strip() for item in items) if item
    ]


def parse_dict_header(value: str) -> dict[str, str | None]:
    """Parse a list header using :func:`parse_list_header`, then parse each item as a
    ``key=value`` pair.

    .. code-block:: python

        parse_dict_header('a=b, c="d, e", f')
        {"a": "b", "c": "d, e", "f": None}

    This is the reverse of :func:`dump_header`.

    If a key does not have a value, it is ``None``.

    This handles charsets for values as described in
    `RFC 2231 <https://www.rfc-editor.org/rfc/rfc2231#section-3>`__. Only ASCII, UTF-8,
    and ISO-8859-1 charsets are accepted, otherwise the value remains quoted.

    :param value: The header value to parse.

    .. versionchanged:: 3.2
        An empty dict is returned if the value contains an unclosed quoted
        string.

    .. versionchanged:: 3.0
        Passing bytes is not supported.

    .. versionchanged:: 3.0
        The ``cls`` argument is removed.

    .. versionchanged:: 2.3
        Added support for ``key*=charset''value`` encoded items.

    .. versionchanged:: 0.9
       The ``cls`` argument was added.
    """
    result: dict[str, str | None] = {}

    for item in parse_list_header(value):
        key, has_value, value = item.partition("=")
        key = key.strip()

        if not key:
            # =value is not valid
            continue

        if not has_value:
            result[key] = None
            continue

        value = value.strip()
        encoding: str | None = None

        if key[-1] == "*":
            # key*=charset''value becomes key=value, where value is percent encoded
            # adapted from parse_options_header, without the continuation handling
            key = key[:-1]
            match = _charset_value_re.match(value)

            if match:
                # If there is a charset marker in the value, split it off.
                encoding, value = match.groups()
                encoding = encoding.lower()

            # A safe list of encodings. Modern clients should only send ASCII or UTF-8.
            # This list will not be extended further. An invalid encoding will leave the
            # value quoted.
            if encoding in {"ascii", "us-ascii", "utf-8", "iso-8859-1"}:
                # invalid bytes are replaced during unquoting
                value = unquote(value, encoding=encoding)

        result[key] = unquote_header_value(value)

    return result


# https://httpwg.org/specs/rfc9110.html#parameter
_parameter_key_re = re.compile(r"([\w!#$%&'*+\-.^`|~]+)=", flags=re.ASCII)
_parameter_token_value_re = re.compile(r"[\w!#$%&'*+\-.^`|~]+", flags=re.ASCII)
# https://www.rfc-editor.org/rfc/rfc2231#section-4
_charset_value_re = re.compile(
    r"""
    ([\w!#$%&*+\-.^`|~]*)'  # charset part, could be empty
    [\w!#$%&*+\-.^`|~]*'  # don't care about language part, usually empty
    ([\w!#$%&'*+\-.^`|~]+)  # one or more token chars with percent encoding
    """,
    re.ASCII | re.VERBOSE,
)
# https://www.rfc-editor.org/rfc/rfc2231#section-3
_continuation_re = re.compile(r"\*(\d+)$", re.ASCII)


def parse_options_header(value: str | None) -> tuple[str, dict[str, str]]:
    """Parse a header that consists of a value with ``key=value`` parameters separated
    by semicolons ``;``. For example, the ``Content-Type`` header.

    .. code-block:: python

        parse_options_header("text/html; charset=UTF-8")
        ('text/html', {'charset': 'UTF-8'})

        parse_options_header("")
        ("", {})

    This is the reverse of :func:`dump_options_header`.

    This parses valid parameter parts as described in
    `RFC 9110 <https://httpwg.org/specs/rfc9110.html#parameter>`__. Invalid parts are
    skipped.

    This handles continuations and charsets as described in
    `RFC 2231 <https://www.rfc-editor.org/rfc/rfc2231#section-3>`__, although not as
    strictly as the RFC. Only ASCII, UTF-8, and ISO-8859-1 charsets are accepted,
    otherwise the value remains quoted.

    Clients may not be consistent in how they handle a quote character within a quoted
    value. The `HTML Standard <https://html.spec.whatwg.org/#multipart-form-data>`__
    replaces it with ``%22`` in multipart form data.
    `RFC 9110 <https://httpwg.org/specs/rfc9110.html#quoted.strings>`__ uses backslash
    escapes in HTTP headers. Both are decoded to the ``"`` character.

    Clients may not be consistent in how they handle non-ASCII characters. HTML
    documents must declare ``<meta charset=UTF-8>``, otherwise browsers may replace with
    HTML character references, which can be decoded using :func:`html.unescape`.

    :param value: The header value to parse.
    :return: ``(value, options)``, where ``options`` is a dict

    .. versionchanged:: 2.3
        Invalid parts, such as keys with no value, quoted keys, and incorrectly quoted
        values, are discarded instead of treating as ``None``.

    .. versionchanged:: 2.3
        Only ASCII, UTF-8, and ISO-8859-1 are accepted for charset values.

    .. versionchanged:: 2.3
        Escaped quotes in quoted values, like ``%22`` and ``\\"``, are handled.

    .. versionchanged:: 2.2
        Option names are always converted to lowercase.

    .. versionchanged:: 2.2
        The ``multiple`` parameter was removed.

    .. versionchanged:: 0.15
        :rfc:`2231` parameter continuations are handled.

    .. versionadded:: 0.5
    """
    if value is None:
        return "", {}

    value, _, rest = value.partition(";")
    value = value.strip()
    rest = rest.strip()

    if not value or not rest:
        # empty (invalid) value, or value without options
        return value, {}

    # Collect all valid key=value parts without processing the value.
    parts: list[tuple[str, str]] = []

    while True:
        if (m := _parameter_key_re.match(rest)) is not None:
            pk = m.group(1).lower()
            rest = rest[m.end() :]

            # Value may be a token.
            if (m := _parameter_token_value_re.match(rest)) is not None:
                parts.append((pk, m.group()))

            # Value may be a quoted string, find the closing quote.
            elif rest[:1] == '"':
                pos = 1
                length = len(rest)

                while pos < length:
                    if rest[pos : pos + 2] in {"\\\\", '\\"'}:
                        # Consume escaped slashes and quotes.
                        pos += 2
                    elif rest[pos] == '"':
                        # Stop at an unescaped quote.
                        parts.append((pk, rest[: pos + 1]))
                        rest = rest[pos + 1 :]
                        break
                    else:
                        # Consume any other character.
                        pos += 1

        # Find the next section delimited by `;`, if any.
        if (end := rest.find(";")) == -1:
            break

        rest = rest[end + 1 :].lstrip()

    options: dict[str, str] = {}
    encoding: str | None = None
    continued_encoding: str | None = None

    # For each collected part, process optional charset and continuation,
    # unquote quoted values.
    for pk, pv in parts:
        if pk[-1] == "*":
            # key*=charset''value becomes key=value, where value is percent encoded
            pk = pk[:-1]
            match = _charset_value_re.match(pv)

            if match:
                # If there is a valid charset marker in the value, split it off.
                encoding, pv = match.groups()
                # This might be the empty string, handled next.
                encoding = encoding.lower()

            # No charset marker, or marker with empty charset value.
            if not encoding:
                encoding = continued_encoding

            # A safe list of encodings. Modern clients should only send ASCII or UTF-8.
            # This list will not be extended further. An invalid encoding will leave the
            # value quoted.
            if encoding in {"ascii", "us-ascii", "utf-8", "iso-8859-1"}:
                # Continuation parts don't require their own charset marker. This is
                # looser than the RFC, it will persist across different keys and allows
                # changing the charset during a continuation. But this implementation is
                # much simpler than tracking the full state.
                continued_encoding = encoding
                # invalid bytes are replaced during unquoting
                pv = unquote(pv, encoding=encoding)

        # Remove quotes. At this point the value cannot be empty or a single quote.
        if pv[0] == pv[-1] == '"':
            # HTTP headers use slash, multipart form data uses percent
            pv = pv[1:-1].replace("\\\\", "\\").replace('\\"', '"').replace("%22", '"')

        match = _continuation_re.search(pk)

        if match:
            # key*0=a; key*1=b becomes key=ab
            pk = pk[: match.start()]
            options[pk] = options.get(pk, "") + pv
        else:
            options[pk] = pv

    return value, options


_q_value_re = re.compile(r"-?\d+(\.\d+)?", re.ASCII)
_TAnyAccept = t.TypeVar("_TAnyAccept", bound="ds.Accept")


@t.overload
def parse_accept_header(value: str | None) -> ds.Accept: ...


@t.overload
def parse_accept_header(value: str | None, cls: type[_TAnyAccept]) -> _TAnyAccept: ...


def parse_accept_header(
    value: str | None, cls: type[_TAnyAccept] | None = None
) -> _TAnyAccept:
    """Parse an ``Accept`` header according to
    `RFC 9110 <https://httpwg.org/specs/rfc9110.html#field.accept>`__.

    Returns an :class:`.Accept` instance, which can sort and inspect items based on
    their quality parameter. When parsing ``Accept-Charset``, ``Accept-Encoding``, or
    ``Accept-Language``, pass the appropriate :class:`.Accept` subclass.

    :param value: The header value to parse.
    :param cls: The :class:`.Accept` class to wrap the result in.
    :return: An instance of ``cls``.

    .. versionchanged:: 2.3
        Parse according to RFC 9110. Items with invalid ``q`` values are skipped.
    """
    if cls is None:
        cls = t.cast(type[_TAnyAccept], ds.Accept)

    if not value:
        return cls(None)

    result = []

    for item in parse_list_header(value):
        item, options = parse_options_header(item)

        if "q" in options:
            # pop q, remaining options are reconstructed
            q_str = options.pop("q").strip()

            if _q_value_re.fullmatch(q_str) is None:
                # ignore an invalid q
                continue

            q = float(q_str)

            if q < 0 or q > 1:
                # ignore an invalid q
                continue
        else:
            q = 1

        if options:
            # reconstruct the media type with any options
            item = dump_options_header(item, options)

        result.append((item, q))

    return cls(result)


_TAnyCC = t.TypeVar("_TAnyCC", bound="ds.cache_control._CacheControl")


@t.overload
def parse_cache_control_header(
    value: str | None,
    on_update: t.Callable[[ds.cache_control._CacheControl], None] | None = None,
) -> ds.RequestCacheControl: ...


@t.overload
def parse_cache_control_header(
    value: str | None,
    on_update: t.Callable[[ds.cache_control._CacheControl], None] | None = None,
    cls: type[_TAnyCC] = ...,
) -> _TAnyCC: ...


def parse_cache_control_header(
    value: str | None,
    on_update: t.Callable[[ds.cache_control._CacheControl], None] | None = None,
    cls: type[_TAnyCC] | None = None,
) -> _TAnyCC:
    """Parse a cache control header.  The RFC differs between response and
    request cache control, this method does not.  It's your responsibility
    to not use the wrong control statements.

    .. versionadded:: 0.5
       The `cls` was added.  If not specified an immutable
       :class:`~werkzeug.datastructures.RequestCacheControl` is returned.

    :param value: a cache control header to be parsed.
    :param on_update: an optional callable that is called every time a value
                      on the :class:`~werkzeug.datastructures.CacheControl`
                      object is changed.
    :param cls: the class for the returned object.  By default
                :class:`~werkzeug.datastructures.RequestCacheControl` is used.
    :return: a `cls` object.
    """
    if cls is None:
        cls = t.cast("type[_TAnyCC]", ds.RequestCacheControl)

    if not value:
        return cls((), on_update)

    return cls(parse_dict_header(value), on_update)


_TAnyCSP = t.TypeVar("_TAnyCSP", bound="ds.ContentSecurityPolicy")


@t.overload
def parse_csp_header(
    value: str | None,
    on_update: t.Callable[[ds.ContentSecurityPolicy], None] | None = None,
) -> ds.ContentSecurityPolicy: ...


@t.overload
def parse_csp_header(
    value: str | None,
    on_update: t.Callable[[ds.ContentSecurityPolicy], None] | None = None,
    cls: type[_TAnyCSP] = ...,
) -> _TAnyCSP: ...


def parse_csp_header(
    value: str | None,
    on_update: t.Callable[[ds.ContentSecurityPolicy], None] | None = None,
    cls: type[_TAnyCSP] | None = None,
) -> _TAnyCSP:
    """Parse a Content Security Policy header.

    .. versionadded:: 1.0.0
       Support for Content Security Policy headers was added.

    :param value: a csp header to be parsed.
    :param on_update: an optional callable that is called every time a value
                      on the object is changed.
    :param cls: the class for the returned object.  By default
                :class:`~werkzeug.datastructures.ContentSecurityPolicy` is used.
    :return: a `cls` object.
    """
    if cls is None:
        cls = t.cast("type[_TAnyCSP]", ds.ContentSecurityPolicy)

    if value is None:
        return cls((), on_update)

    items = []

    for policy in value.split(";"):
        policy = policy.strip()

        # Ignore badly formatted policies (no space)
        if " " in policy:
            directive, value = policy.strip().split(" ", 1)
            items.append((directive.strip(), value.strip()))

    return cls(items, on_update)


def parse_set_header(
    value: str | None,
    on_update: t.Callable[[ds.HeaderSet], None] | None = None,
) -> ds.HeaderSet:
    """Parse a set-like header and return a
    :class:`~werkzeug.datastructures.HeaderSet` object:

    >>> hs = parse_set_header('token, "quoted value"')

    The return value is an object that treats the items case-insensitively
    and keeps the order of the items:

    >>> 'TOKEN' in hs
    True
    >>> hs.index('quoted value')
    1
    >>> hs
    HeaderSet(['token', 'quoted value'])

    To create a header from the :class:`HeaderSet` again, use the
    :func:`dump_header` function.

    :param value: a set header to be parsed.
    :param on_update: an optional callable that is called every time a
                      value on the :class:`~werkzeug.datastructures.HeaderSet`
                      object is changed.
    :return: a :class:`~werkzeug.datastructures.HeaderSet`
    """
    if not value:
        return ds.HeaderSet(None, on_update)
    return ds.HeaderSet(parse_list_header(value), on_update)


def parse_if_range_header(value: str | None) -> ds.IfRange:
    """Parses an if-range header which can be an etag or a date.  Returns
    a :class:`~werkzeug.datastructures.IfRange` object.

    .. versionchanged:: 2.0
        If the value represents a datetime, it is timezone-aware.

    .. versionadded:: 0.7
    """
    if not value:
        return ds.IfRange()
    date = parse_date(value)
    if date is not None:
        return ds.IfRange(date=date)
    # drop weakness information
    return ds.IfRange(unquote_etag(value)[0])


def parse_range_header(
    value: str | None, make_inclusive: bool = True
) -> ds.Range | None:
    """Parses a range header into a :class:`~werkzeug.datastructures.Range`
    object.  If the header is missing or malformed `None` is returned.
    `ranges` is a list of ``(start, stop)`` tuples where the ranges are
    non-inclusive.

    .. versionadded:: 0.7
    """
    if not value or "=" not in value:
        return None

    ranges = []
    last_end = 0
    units, rng = value.split("=", 1)
    units = units.strip().lower()

    for item in rng.split(","):
        item = item.strip()
        if "-" not in item:
            return None
        if item.startswith("-"):
            if last_end < 0:
                return None
            try:
                begin = _plain_int(item)
            except ValueError:
                return None
            end = None
            last_end = -1
        elif "-" in item:
            begin_str, end_str = item.split("-", 1)
            begin_str = begin_str.strip()
            end_str = end_str.strip()

            try:
                begin = _plain_int(begin_str)
            except ValueError:
                return None

            if begin < last_end or last_end < 0:
                return None
            if end_str:
                try:
                    end = _plain_int(end_str) + 1
                except ValueError:
                    return None

                if begin >= end:
                    return None
            else:
                end = None
            last_end = end if end is not None else -1
        ranges.append((begin, end))

    return ds.Range(units, ranges)


def parse_content_range_header(
    value: str | None,
    on_update: t.Callable[[ds.ContentRange], None] | None = None,
) -> ds.ContentRange | None:
    """Parses a range header into a
    :class:`~werkzeug.datastructures.ContentRange` object or `None` if
    parsing is not possible.

    .. versionadded:: 0.7

    :param value: a content range header to be parsed.
    :param on_update: an optional callable that is called every time a value
                      on the :class:`~werkzeug.datastructures.ContentRange`
                      object is changed.
    """
    if value is None:
        return None
    try:
        units, rangedef = (value or "").strip().split(None, 1)
    except ValueError:
        return None

    if "/" not in rangedef:
        return None
    rng, length_str = rangedef.split("/", 1)
    if length_str == "*":
        length = None
    else:
        try:
            length = _plain_int(length_str)
        except ValueError:
            return None

    if rng == "*":
        if not is_byte_range_valid(None, None, length):
            return None

        return ds.ContentRange(units, None, None, length, on_update=on_update)
    elif "-" not in rng:
        return None

    start_str, stop_str = rng.split("-", 1)
    try:
        start = _plain_int(start_str)
        stop = _plain_int(stop_str) + 1
    except ValueError:
        return None

    if is_byte_range_valid(start, stop, length):
        return ds.ContentRange(units, start, stop, length, on_update=on_update)

    return None


def quote_etag(etag: str, weak: bool = False) -> str:
    """Quote an etag.

    :param etag: the etag to quote.
    :param weak: set to `True` to tag it "weak".
    """
    if '"' in etag:
        raise ValueError("invalid etag")
    etag = f'"{etag}"'
    if weak:
        etag = f"W/{etag}"
    return etag


@t.overload
def unquote_etag(etag: str) -> tuple[str, bool]: ...
@t.overload
def unquote_etag(etag: None) -> tuple[None, None]: ...
def unquote_etag(
    etag: str | None,
) -> tuple[str, bool] | tuple[None, None]:
    """Unquote a single etag:

    >>> unquote_etag('W/"bar"')
    ('bar', True)
    >>> unquote_etag('"bar"')
    ('bar', False)

    :param etag: the etag identifier to unquote.
    :return: a ``(etag, weak)`` tuple.
    """
    if not etag:
        return None, None
    etag = etag.strip()
    weak = False
    if etag.startswith(("W/", "w/")):
        weak = True
        etag = etag[2:]
    if etag[:1] == etag[-1:] == '"':
        etag = etag[1:-1]
    return etag, weak


def parse_etags(value: str | None) -> ds.ETags:
    """Parse an etag header.

    :param value: the tag header to parse
    :return: an :class:`~werkzeug.datastructures.ETags` object.
    """
    if not value:
        return ds.ETags()
    strong = []
    weak = []
    end = len(value)
    pos = 0
    while pos < end:
        match = _etag_re.match(value, pos)
        if match is None:
            break
        is_weak, quoted, raw = match.groups()
        if raw == "*":
            return ds.ETags(star_tag=True)
        elif quoted:
            raw = quoted
        if is_weak:
            weak.append(raw)
        else:
            strong.append(raw)
        pos = match.end()
    return ds.ETags(strong, weak)


def generate_etag(data: bytes) -> str:
    """Generate an etag for some data.

    .. versionchanged:: 2.0
        Use SHA-1. MD5 may not be available in some environments.
    """
    return sha1(data).hexdigest()


def parse_date(value: str | None) -> datetime | None:
    """Parse an :rfc:`2822` date into a timezone-aware
    :class:`datetime.datetime` object, or ``None`` if parsing fails.

    This is a wrapper for :func:`email.utils.parsedate_to_datetime`. It
    returns ``None`` if parsing fails instead of raising an exception,
    and always returns a timezone-aware datetime object. If the string
    doesn't have timezone information, it is assumed to be UTC.

    :param value: A string with a supported date format.

    .. versionchanged:: 2.0
        Return a timezone-aware datetime object. Use
        ``email.utils.parsedate_to_datetime``.
    """
    if value is None:
        return None

    try:
        dt = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)

    return dt


def http_date(
    timestamp: datetime | date | int | float | struct_time | None = None,
) -> str:
    """Format a datetime object or timestamp into an :rfc:`2822` date
    string.

    This is a wrapper for :func:`email.utils.format_datetime`. It
    assumes naive datetime objects are in UTC instead of raising an
    exception.

    :param timestamp: The datetime or timestamp to format. Defaults to
        the current time.

    .. versionchanged:: 2.0
        Use ``email.utils.format_datetime``. Accept ``date`` objects.
    """
    if isinstance(timestamp, date):
        if not isinstance(timestamp, datetime):
            # Assume plain date is midnight UTC.
            timestamp = datetime.combine(timestamp, time(), tzinfo=timezone.utc)
        else:
            # Ensure datetime is timezone-aware.
            timestamp = _dt_as_utc(timestamp)

        return email.utils.format_datetime(timestamp, usegmt=True)

    if isinstance(timestamp, struct_time):
        timestamp = mktime(timestamp)

    return email.utils.formatdate(timestamp, usegmt=True)


def parse_age(value: str | None = None) -> timedelta | None:
    """Parses a base-10 integer count of seconds into a timedelta.

    If parsing fails, the return value is `None`.

    :param value: a string consisting of an integer represented in base-10
    :return: a :class:`datetime.timedelta` object or `None`.
    """
    if not value:
        return None
    try:
        seconds = int(value)
    except ValueError:
        return None
    if seconds < 0:
        return None
    try:
        return timedelta(seconds=seconds)
    except OverflowError:
        return None


def dump_age(age: timedelta | int | None = None) -> str | None:
    """Formats the duration as a base-10 integer.

    :param age: should be an integer number of seconds,
                a :class:`datetime.timedelta` object, or,
                if the age is unknown, `None` (default).
    """
    if age is None:
        return None
    if isinstance(age, timedelta):
        age = int(age.total_seconds())
    else:
        age = int(age)

    if age < 0:
        raise ValueError("age cannot be negative")

    return str(age)


def is_resource_modified(
    environ: WSGIEnvironment,
    etag: str | None = None,
    data: bytes | None = None,
    last_modified: datetime | str | None = None,
    ignore_if_range: bool = True,
) -> bool:
    """Convenience method for conditional requests.

    :param environ: the WSGI environment of the request to be checked.
    :param etag: the etag for the response for comparison.
    :param data: or alternatively the data of the response to automatically
                 generate an etag using :func:`generate_etag`.
    :param last_modified: an optional date of the last modification.
    :param ignore_if_range: If `False`, `If-Range` header will be taken into
                            account.
    :return: `True` if the resource was modified, otherwise `False`.

    .. versionchanged:: 2.0
        SHA-1 is used to generate an etag value for the data. MD5 may
        not be available in some environments.

    .. versionchanged:: 1.0.0
        The check is run for methods other than ``GET`` and ``HEAD``.
    """
    return _sansio_http.is_resource_modified(
        http_range=environ.get("HTTP_RANGE"),
        http_if_range=environ.get("HTTP_IF_RANGE"),
        http_if_modified_since=environ.get("HTTP_IF_MODIFIED_SINCE"),
        http_if_none_match=environ.get("HTTP_IF_NONE_MATCH"),
        http_if_match=environ.get("HTTP_IF_MATCH"),
        etag=etag,
        data=data,
        last_modified=last_modified,
        ignore_if_range=ignore_if_range,
    )


def remove_entity_headers(
    headers: ds.Headers | list[tuple[str, str]],
    allowed: t.Iterable[str] = ("expires", "content-location"),
) -> None:
    """Remove all entity headers from a list or :class:`Headers` object.  This
    operation works in-place.  `Expires` and `Content-Location` headers are
    by default not removed.  The reason for this is :rfc:`2616` section
    10.3.5 which specifies some entity headers that should be sent.

    .. versionchanged:: 0.5
       added `allowed` parameter.

    :param headers: a list or :class:`Headers` object.
    :param allowed: a list of headers that should still be allowed even though
                    they are entity headers.
    """
    allowed = {x.lower() for x in allowed}
    headers[:] = [
        (key, value)
        for key, value in headers
        if not is_entity_header(key) or key.lower() in allowed
    ]


def remove_hop_by_hop_headers(headers: ds.Headers | list[tuple[str, str]]) -> None:
    """Remove all HTTP/1.1 "Hop-by-Hop" headers from a list or
    :class:`Headers` object.  This operation works in-place.

    .. versionadded:: 0.5

    :param headers: a list or :class:`Headers` object.
    """
    headers[:] = [
        (key, value) for key, value in headers if not is_hop_by_hop_header(key)
    ]


def is_entity_header(header: str) -> bool:
    """Check if a header is an entity header.

    .. versionadded:: 0.5

    :param header: the header to test.
    :return: `True` if it's an entity header, `False` otherwise.
    """
    return header.lower() in _entity_headers


def is_hop_by_hop_header(header: str) -> bool:
    """Check if a header is an HTTP/1.1 "Hop-by-Hop" header.

    .. versionadded:: 0.5

    :param header: the header to test.
    :return: `True` if it's an HTTP/1.1 "Hop-by-Hop" header, `False` otherwise.
    """
    return header.lower() in _hop_by_hop_headers


def parse_cookie(
    header: WSGIEnvironment | str | None,
    cls: type[ds.MultiDict[str, str]] | None = None,
) -> ds.MultiDict[str, str]:
    """Parse a cookie from a string or WSGI environ.

    The same key can be provided multiple times, the values are stored
    in-order. The default :class:`MultiDict` will have the first value
    first, and all values can be retrieved with
    :meth:`MultiDict.getlist`.

    :param header: The cookie header as a string, or a WSGI environ dict
        with a ``HTTP_COOKIE`` key.
    :param cls: A dict-like class to store the parsed cookies in.
        Defaults to :class:`MultiDict`.

    .. versionchanged:: 3.0
        Passing bytes, and the ``charset`` and ``errors`` parameters, were removed.

    .. versionchanged:: 1.0
        Returns a :class:`MultiDict` instead of a ``TypeConversionDict``.

    .. versionchanged:: 0.5
        Returns a :class:`TypeConversionDict` instead of a regular dict. The ``cls``
        parameter was added.
    """
    if isinstance(header, dict):
        cookie = header.get("HTTP_COOKIE")
    else:
        cookie = header

    if cookie:
        cookie = cookie.encode("latin1").decode()

    return _sansio_http.parse_cookie(cookie=cookie, cls=cls)


_cookie_no_quote_re = re.compile(r"[\w!#$%&'()*+\-./:<=>?@\[\]^`{|}~]*", re.A)
_cookie_slash_re = re.compile(rb"[\x00-\x19\",;\\\x7f-\xff]", re.A)
_cookie_slash_map = {b'"': b'\\"', b"\\": b"\\\\"}
_cookie_slash_map.update(
    (v.to_bytes(1, "big"), b"\\%03o" % v)
    for v in [*range(0x20), *b",;", *range(0x7F, 256)]
)


def dump_cookie(
    key: str,
    value: str = "",
    max_age: timedelta | int | None = None,
    expires: str | datetime | int | float | None = None,
    path: str | None = "/",
    domain: str | None = None,
    secure: bool = False,
    httponly: bool = False,
    sync_expires: bool = True,
    max_size: int = 4093,
    samesite: str | None = None,
    partitioned: bool = False,
) -> str:
    """Create a Set-Cookie header without the ``Set-Cookie`` prefix.

    The return value is usually restricted to ascii as the vast majority
    of values are properly escaped, but that is no guarantee. It's
    tunneled through latin1 as required by :pep:`3333`.

    The return value is not ASCII safe if the key contains unicode
    characters.  This is technically against the specification but
    happens in the wild.  It's strongly recommended to not use
    non-ASCII values for the keys.

    :param max_age: should be a number of seconds, or `None` (default) if
                    the cookie should last only as long as the client's
                    browser session.  Additionally `timedelta` objects
                    are accepted, too.
    :param expires: should be a `datetime` object or unix timestamp.
    :param path: limits the cookie to a given path, per default it will
                 span the whole domain.
    :param domain: Use this if you want to set a cross-domain cookie. For
                   example, ``domain="example.com"`` will set a cookie
                   that is readable by the domain ``www.example.com``,
                   ``foo.example.com`` etc. Otherwise, a cookie will only
                   be readable by the domain that set it.
    :param secure: The cookie will only be available via HTTPS
    :param httponly: disallow JavaScript to access the cookie.  This is an
                     extension to the cookie standard and probably not
                     supported by all browsers.
    :param charset: the encoding for string values.
    :param sync_expires: automatically set expires if max_age is defined
                         but expires not.
    :param max_size: Warn if the final header value exceeds this size. The
        default, 4093, should be safely `supported by most browsers
        <cookie_>`_. Set to 0 to disable this check.
    :param samesite: Limits the scope of the cookie such that it will
        only be attached to requests if those requests are same-site.
    :param partitioned: Opts the cookie into partitioned storage. This
        will also set secure to True

    .. _`cookie`: http://browsercookielimits.squawky.net/

    .. versionchanged:: 3.1
        The ``partitioned`` parameter was added.

    .. versionchanged:: 3.0
        Passing bytes, and the ``charset`` parameter, were removed.

    .. versionchanged:: 2.3.3
        The ``path`` parameter is ``/`` by default.

    .. versionchanged:: 2.3.1
        The value allows more characters without quoting.

    .. versionchanged:: 2.3
        ``localhost`` and other names without a dot are allowed for the domain. A
        leading dot is ignored.

    .. versionchanged:: 2.3
        The ``path`` parameter is ``None`` by default.

    .. versionchanged:: 1.0.0
        The string ``'None'`` is accepted for ``samesite``.
    """
    if path is not None:
        # safe = https://url.spec.whatwg.org/#url-path-segment-string
        # as well as percent for things that are already quoted
        # excluding semicolon since it's part of the header syntax
        path = quote(path, safe="%!$&'()*+,/:=@")

    if domain:
        domain = domain.partition(":")[0].lstrip(".").encode("idna").decode("ascii")

    if isinstance(max_age, timedelta):
        max_age = int(max_age.total_seconds())

    if expires is not None:
        if not isinstance(expires, str):
            expires = http_date(expires)
    elif max_age is not None and sync_expires:
        expires = http_date(datetime.now(tz=timezone.utc).timestamp() + max_age)

    if samesite is not None:
        samesite = samesite.title()

        if samesite not in {"Strict", "Lax", "None"}:
            raise ValueError("SameSite must be 'Strict', 'Lax', or 'None'.")

    if partitioned:
        secure = True

    # Quote value if it contains characters not allowed by RFC 6265. Slash-escape with
    # three octal digits, which matches http.cookies, although the RFC suggests base64.
    if not _cookie_no_quote_re.fullmatch(value):
        # Work with bytes here, since a UTF-8 character could be multiple bytes.
        value = _cookie_slash_re.sub(
            lambda m: _cookie_slash_map[m.group()], value.encode()
        ).decode("ascii")
        value = f'"{value}"'

    # Send a non-ASCII key as mojibake. Everything else should already be ASCII.
    # TODO Remove encoding dance, it seems like clients accept UTF-8 keys
    buf = [f"{key.encode().decode('latin1')}={value}"]

    for k, v in (
        ("Domain", domain),
        ("Expires", expires),
        ("Max-Age", max_age),
        ("Secure", secure),
        ("HttpOnly", httponly),
        ("Path", path),
        ("SameSite", samesite),
        ("Partitioned", partitioned),
    ):
        if v is None or v is False:
            continue

        if v is True:
            buf.append(k)
            continue

        buf.append(f"{k}={v}")

    rv = "; ".join(buf)

    # Warn if the final value of the cookie is larger than the limit. If the cookie is
    # too large, then it may be silently ignored by the browser, which can be quite hard
    # to debug.
    cookie_size = len(rv)

    if max_size and cookie_size > max_size:
        value_size = len(value)
        warnings.warn(
            f"The '{key}' cookie is too large: the value was {value_size} bytes but the"
            f" header required {cookie_size - value_size} extra bytes. The final size"
            f" was {cookie_size} bytes but the limit is {max_size} bytes. Browsers may"
            " silently ignore cookies larger than this.",
            stacklevel=2,
        )

    return rv


def is_byte_range_valid(
    start: int | None, stop: int | None, length: int | None
) -> bool:
    """Checks if a given byte content range is valid for the given length.

    .. versionadded:: 0.7
    """
    if (start is None) != (stop is None):
        return False
    elif start is None:
        return length is None or length >= 0
    elif length is None:
        return 0 <= start < stop  # type: ignore
    elif start >= stop:  # type: ignore
        return False
    return 0 <= start < length


# circular dependencies
from . import datastructures as ds  # noqa: E402
from .sansio import http as _sansio_http  # noqa: E402
