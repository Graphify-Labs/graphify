from __future__ import annotations

import typing as t
from datetime import datetime
from urllib.parse import parse_qsl

from ..datastructures import Accept
from ..datastructures import Authorization
from ..datastructures import CharsetAccept
from ..datastructures import ETags
from ..datastructures import Headers
from ..datastructures import HeaderSet
from ..datastructures import IfRange
from ..datastructures import ImmutableList
from ..datastructures import ImmutableMultiDict
from ..datastructures import LanguageAccept
from ..datastructures import MIMEAccept
from ..datastructures import MultiDict
from ..datastructures import Range
from ..datastructures import RequestCacheControl
from ..http import parse_accept_header
from ..http import parse_cache_control_header
from ..http import parse_date
from ..http import parse_etags
from ..http import parse_if_range_header
from ..http import parse_list_header
from ..http import parse_options_header
from ..http import parse_range_header
from ..http import parse_set_header
from ..user_agent import UserAgent
from ..utils import cached_property
from ..utils import header_property
from .http import parse_cookie
from .utils import get_content_length
from .utils import get_current_url
from .utils import get_host


class Request:
    """Represents the non-IO parts of a HTTP request, including the
    method, URL info, and headers.

    This class is not meant for general use. It should only be used when
    implementing WSGI, ASGI, or another HTTP application spec. Werkzeug
    provides a WSGI implementation at :cls:`werkzeug.wrappers.Request`.

    :param method: The method the request was made with, such as
        ``GET``.
    :param scheme: The URL scheme of the protocol the request used, such
        as ``https`` or ``wss``.
    :param server: The address of the server. ``(host, port)``,
        ``(path, None)`` for unix sockets, or ``None`` if not known.
    :param root_path: The prefix that the application is mounted under.
        This is prepended to generated URLs, but is not part of route
        matching.
    :param path: The path part of the URL after ``root_path``.
    :param query_string: The part of the URL after the "?".
    :param headers: The headers received with the request.
    :param remote_addr: The address of the client sending the request.

    .. versionchanged:: 3.0
        The ``charset``, ``url_charset``, and ``encoding_errors`` attributes
        were removed.

    .. versionadded:: 2.0
    """

    #: the class to use for `args` and `form`.  The default is an
    #: :class:`~werkzeug.datastructures.ImmutableMultiDict` which supports
    #: multiple values per key. A :class:`~werkzeug.datastructures.ImmutableDict`
    #: is faster but only remembers the last key. It is also
    #: possible to use mutable structures, but this is not recommended.
    #:
    #: .. versionadded:: 0.6
    parameter_storage_class: type[MultiDict[str, t.Any]] = ImmutableMultiDict

    #: The type to be used for dict values from the incoming WSGI
    #: environment. (For example for :attr:`cookies`.) By default an
    #: :class:`~werkzeug.datastructures.ImmutableMultiDict` is used.
    #:
    #: .. versionchanged:: 1.0.0
    #:     Changed to ``ImmutableMultiDict`` to support multiple values.
    #:
    #: .. versionadded:: 0.6
    dict_storage_class: type[MultiDict[str, t.Any]] = ImmutableMultiDict

    #: the type to be used for list values from the incoming WSGI environment.
    #: By default an :class:`~werkzeug.datastructures.ImmutableList` is used
    #: (for example for :attr:`access_list`).
    #:
    #: .. versionadded:: 0.6
    list_storage_class: type[list[t.Any]] = ImmutableList

    user_agent_class: type[UserAgent] = UserAgent
    """The class used and returned by the :attr:`user_agent` property to
    parse the header. Defaults to
    :class:`~werkzeug.user_agent.UserAgent`, which does no parsing. An
    extension can provide a subclass that uses a parser to provide other
    data.

    .. versionadded:: 2.0
    """

    #: Valid host names when handling requests. By default all hosts are
    #: trusted, which means that whatever the client says the host is
    #: will be accepted.
    #:
    #: Because ``Host`` and ``X-Forwarded-Host`` headers can be set to
    #: any value by a malicious client, it is recommended to either set
    #: this property or implement similar validation in the proxy (if
    #: the application is being run behind one).
    #:
    #: .. versionadded:: 0.9
    trusted_hosts: list[str] | None = None

    def __init__(
        self,
        method: str,
        scheme: str,
        server: tuple[str, int | None] | None,
        root_path: str,
        path: str,
        query_string: bytes,
        headers: Headers,
        remote_addr: str | None,
    ) -> None:
        #: The method the request was made with, such as ``GET``.
        self.method = method.upper()
        #: The URL scheme of the protocol the request used, such as
        #: ``https`` or ``wss``.
        self.scheme = scheme
        #: The address of the server. ``(host, port)``, ``(path, None)``
        #: for unix sockets, or ``None`` if not known.
        self.server = server
        #: The prefix that the application is mounted under, without a
        #: trailing slash. :attr:`path` comes after this.
        self.root_path = root_path.rstrip("/")
        #: The path part of the URL after :attr:`root_path`. This is the
        #: path used for routing within the application.
        self.path = "/" + path.lstrip("/")
        #: The part of the URL after the "?". This is the raw value, use
        #: :attr:`args` for the parsed values.
        self.query_string = query_string
        #: The headers received with the request.
        self.headers = headers
        #: The address of the client sending the request.
        self.remote_addr = remote_addr

    def __repr__(self) -> str:
        try:
            url = self.url
        except Exception as e:
            url = f"(invalid URL: {e})"

        return f"<{type(self).__name__} {url!r} [{self.method}]>"

    @cached_property
    def args(self) -> MultiDict[str, str]:
        """The parsed URL parameters (the part in the URL after the question
        mark).

        By default an
        :class:`~werkzeug.datastructures.ImmutableMultiDict`
        is returned from this function.  This can be changed by setting
        :attr:`parameter_storage_class` to a different type.  This might
        be necessary if the order of the form data is important.

        .. versionchanged:: 2.3
            Invalid bytes remain percent encoded.
        """
        return self.parameter_storage_class(
            parse_qsl(
                self.query_string.decode(),
                keep_blank_values=True,
                errors="werkzeug.url_quote",
            )
        )

    @cached_property
    def access_route(self) -> list[str]:
        """If a forwarded header exists this is a list of all ip addresses
        from the client ip to the last proxy server.
        """
        if "X-Forwarded-For" in self.headers:
            return self.list_storage_class(
                parse_list_header(self.headers["X-Forwarded-For"])
            )
        elif self.remote_addr is not None:
            return self.list_storage_class([self.remote_addr])
        return self.list_storage_class()

    @cached_property
    def full_path(self) -> str:
        """Requested path, including the query string."""
        return f"{self.path}?{self.query_string.decode()}"

    @property
    def is_secure(self) -> bool:
        """``True`` if the request was made with a secure protocol
        (HTTPS or WSS).
        """
        return self.scheme in {"https", "wss"}

    @cached_property
    def url(self) -> str:
        """The full request URL with the scheme, host, root path, path,
        and query string."""
        return get_current_url(
            self.scheme, self.host, self.root_path, self.path, self.query_string
        )

    @cached_property
    def base_url(self) -> str:
        """Like :attr:`url` but without the query string."""
        return get_current_url(self.scheme, self.host, self.root_path, self.path)

    @cached_property
    def root_url(self) -> str:
        """The request URL scheme, host, and root path. This is the root
        that the application is accessed from.
        """
        return get_current_url(self.scheme, self.host, self.root_path)

    @cached_property
    def host_url(self) -> str:
        """The request URL scheme and host only."""
        return get_current_url(self.scheme, self.host)

    @cached_property
    def host(self) -> str:
        """The host name the request was made to, including the port if
        it's non-standard. Validated with :attr:`trusted_hosts`.

        See :func:`.get_host` for a detailed explanation.
        """
        return get_host(
            self.scheme, self.headers.get("host"), self.server, self.trusted_hosts
        )

    @cached_property
    def cookies(self) -> ImmutableMultiDict[str, str]:
        """A :class:`dict` with the contents of all cookies transmitted with
        the request."""
        wsgi_combined_cookie = ";".join(self.headers.getlist("Cookie"))
        return parse_cookie(  # type: ignore
            wsgi_combined_cookie, cls=self.dict_storage_class
        )

    # Common Descriptors

    content_type = header_property[str](
        "Content-Type",
        doc="""The Content-Type entity-header field indicates the media
        type of the entity-body sent to the recipient or, in the case of
        the HEAD method, the media type that would have been sent had
        the request been a GET.""",
        read_only=True,
    )

    @cached_property
    def content_length(self) -> int | None:
        """The Content-Length entity-header field indicates the size of the
        entity-body in bytes or, in the case of the HEAD method, the size of
        the entity-body that would have been sent had the request been a
        GET.
        """
        return get_content_length(
            http_content_length=self.headers.get("Content-Length"),
            http_transfer_encoding=self.headers.get("Transfer-Encoding"),
        )

    content_encoding = header_property[str](
        "Content-Encoding",
        doc="""The Content-Encoding entity-header field is used as a
        modifier to the media-type. When present, its value indicates
        what additional content codings have been applied to the
        entity-body, and thus what decoding mechanisms must be applied
        in order to obtain the media-type referenced by the Content-Type
        header field.

        .. versionadded:: 0.9""",
        read_only=True,
    )
    content_md5 = header_property[str](
        "Content-MD5",
        doc="""The Content-MD5 entity-header field, as defined in
        RFC 1864, is an MD5 digest of the entity-body for the purpose of
        providing an end-to-end message integrity check (MIC) of the
        entity-body. (Note: a MIC is good for detecting accidental
        modification of the entity-body in transit, but is not proof
        against malicious attacks.)

        .. versionadded:: 0.9""",
        read_only=True,
    )
    referrer = header_property[str](
        "Referer",
        doc="""The Referer[sic] request-header field allows the client
        to specify, for the server's benefit, the address (URI) of the
        resource from which the Request-URI was obtained (the
        "referrer", although the header field is misspelled).""",
        read_only=True,
    )
    date = header_property(
        "Date",
        None,
        parse_date,
        doc="""The Date general-header field represents the date and
        time at which the message was originated, having the same
        semantics as orig-date in RFC 822.

        .. versionchanged:: 2.0
            The datetime object is timezone-aware.
        """,
        read_only=True,
    )
    max_forwards = header_property(
        "Max-Forwards",
        None,
        int,
        doc="""The Max-Forwards request-header field provides a
        mechanism with the TRACE and OPTIONS methods to limit the number
        of proxies or gateways that can forward the request to the next
        inbound server.""",
        read_only=True,
    )

    def _parse_content_type(self) -> None:
        if not hasattr(self, "_parsed_content_type"):
            self._parsed_content_type = parse_options_header(
                self.headers.get("Content-Type", "")
            )

    @property
    def mimetype(self) -> str:
        """Like :attr:`content_type`, but without parameters (eg, without
        charset, type etc.) and always lowercase.  For example if the content
        type is ``text/HTML; charset=utf-8`` the mimetype would be
        ``'text/html'``.
        """
        self._parse_content_type()
        return self._parsed_content_type[0].lower()

    @property
    def mimetype_params(self) -> dict[str, str]:
        """The mimetype parameters as dict.  For example if the content
        type is ``text/html; charset=utf-8`` the params would be
        ``{'charset': 'utf-8'}``.
        """
        self._parse_content_type()
        return self._parsed_content_type[1]

    @cached_property
    def pragma(self) -> HeaderSet:
        """The Pragma general-header field is used to include
        implementation-specific directives that might apply to any recipient
        along the request/response chain.  All pragma directives specify
        optional behavior from the viewpoint of the protocol; however, some
        systems MAY require that behavior be consistent with the directives.
        """
        return parse_set_header(self.headers.get("Pragma", ""))

    # Accept

    @cached_property
    def accept_mimetypes(self) -> MIMEAccept:
        """List of mimetypes this client supports as
        :class:`~werkzeug.datastructures.MIMEAccept` object.
        """
        return parse_accept_header(self.headers.get("Accept"), MIMEAccept)

    @cached_property
    def accept_charsets(self) -> CharsetAccept:
        """List of charsets this client supports as
        :class:`~werkzeug.datastructures.CharsetAccept` object.
        """
        return parse_accept_header(self.headers.get("Accept-Charset"), CharsetAccept)

    @cached_property
    def accept_encodings(self) -> Accept:
        """List of encodings this client accepts.  Encodings in a HTTP term
        are compression encodings such as gzip.  For charsets have a look at
        :attr:`accept_charset`.
        """
        return parse_accept_header(self.headers.get("Accept-Encoding"))

    @cached_property
    def accept_languages(self) -> LanguageAccept:
        """List of languages this client accepts as
        :class:`~werkzeug.datastructures.LanguageAccept` object.

        .. versionchanged 0.5
           In previous versions this was a regular
           :class:`~werkzeug.datastructures.Accept` object.
        """
        return parse_accept_header(self.headers.get("Accept-Language"), LanguageAccept)

    # ETag

    @cached_property
    def cache_control(self) -> RequestCacheControl:
        """A :class:`~werkzeug.datastructures.RequestCacheControl` object
        for the incoming cache control headers.
        """
        cache_control = self.headers.get("Cache-Control")
        return parse_cache_control_header(cache_control, None, RequestCacheControl)

    @cached_property
    def if_match(self) -> ETags:
        """An object containing all the etags in the `If-Match` header.

        :rtype: :class:`~werkzeug.datastructures.ETags`
        """
        return parse_etags(self.headers.get("If-Match"))

    @cached_property
    def if_none_match(self) -> ETags:
        """An object containing all the etags in the `If-None-Match` header.

        :rtype: :class:`~werkzeug.datastructures.ETags`
        """
        return parse_etags(self.headers.get("If-None-Match"))

    @cached_property
    def if_modified_since(self) -> datetime | None:
        """The parsed `If-Modified-Since` header as a datetime object.

        .. versionchanged:: 2.0
            The datetime object is timezone-aware.
        """
        return parse_date(self.headers.get("If-Modified-Since"))

    @cached_property
    def if_unmodified_since(self) -> datetime | None:
        """The parsed `If-Unmodified-Since` header as a datetime object.

        .. versionchanged:: 2.0
            The datetime object is timezone-aware.
        """
        return parse_date(self.headers.get("If-Unmodified-Since"))

    @cached_property
    def if_range(self) -> IfRange:
        """The parsed ``If-Range`` header.

        .. versionchanged:: 2.0
            ``IfRange.date`` is timezone-aware.

        .. versionadded:: 0.7
        """
        return parse_if_range_header(self.headers.get("If-Range"))

    @cached_property
    def range(self) -> Range | None:
        """The parsed `Range` header.

        .. versionadded:: 0.7

        :rtype: :class:`~werkzeug.datastructures.Range`
        """
        return parse_range_header(self.headers.get("Range"))

    # User Agent

    @cached_property
    def user_agent(self) -> UserAgent:
        """The user agent. Use ``user_agent.string`` to get the header
        value. Set :attr:`user_agent_class` to a subclass of
        :class:`~werkzeug.user_agent.UserAgent` to provide parsing for
        the other properties or other extended data.

        .. versionchanged:: 2.1
            The built-in parser was removed. Set ``user_agent_class`` to a ``UserAgent``
            subclass to parse data from the string.
        """
        return self.user_agent_class(self.headers.get("User-Agent", ""))

    # Authorization

    @cached_property
    def authorization(self) -> Authorization | None:
        """The ``Authorization`` header parsed into an :class:`.Authorization` object.
        ``None`` if the header is not present.

        .. versionchanged:: 2.3
            :class:`Authorization` is no longer a ``dict``. The ``token`` attribute
            was added for auth schemes that use a token instead of parameters.
        """
        return Authorization.from_header(self.headers.get("Authorization"))

    # CORS

    origin = header_property[str](
        "Origin",
        doc=(
            "The host that the request originated from. Set"
            " :attr:`~CORSResponseMixin.access_control_allow_origin` on"
            " the response to indicate which origins are allowed."
        ),
        read_only=True,
    )

    access_control_request_headers = header_property(
        "Access-Control-Request-Headers",
        load_func=parse_set_header,
        doc=(
            "Sent with a preflight request to indicate which headers"
            " will be sent with the cross origin request. Set"
            " :attr:`~CORSResponseMixin.access_control_allow_headers`"
            " on the response to indicate which headers are allowed."
        ),
        read_only=True,
    )

    access_control_request_method = header_property[str](
        "Access-Control-Request-Method",
        doc=(
            "Sent with a preflight request to indicate which method"
            " will be used for the cross origin request. Set"
            " :attr:`~CORSResponseMixin.access_control_allow_methods`"
            " on the response to indicate which methods are allowed."
        ),
        read_only=True,
    )

    @property
    def is_json(self) -> bool:
        """Check if the mimetype indicates JSON data, either
        :mimetype:`application/json` or :mimetype:`application/*+json`.
        """
        mt = self.mimetype
        return (
            mt == "application/json"
            or mt.startswith("application/")
            and mt.endswith("+json")
        )
