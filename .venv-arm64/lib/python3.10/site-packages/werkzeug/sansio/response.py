from __future__ import annotations

import typing as t
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from http import HTTPStatus

from ..datastructures import CallbackDict
from ..datastructures import ContentRange
from ..datastructures import ContentSecurityPolicy
from ..datastructures import Headers
from ..datastructures import HeaderSet
from ..datastructures import ResponseCacheControl
from ..datastructures import WWWAuthenticate
from ..http import COEP
from ..http import COOP
from ..http import dump_age
from ..http import dump_cookie
from ..http import dump_header
from ..http import dump_options_header
from ..http import http_date
from ..http import HTTP_STATUS_CODES
from ..http import parse_age
from ..http import parse_cache_control_header
from ..http import parse_content_range_header
from ..http import parse_csp_header
from ..http import parse_date
from ..http import parse_options_header
from ..http import parse_set_header
from ..http import quote_etag
from ..http import unquote_etag
from ..utils import get_content_type
from ..utils import header_property

if t.TYPE_CHECKING:
    from ..datastructures.cache_control import _CacheControl


def _set_property(name: str, doc: str | None = None) -> property:
    def fget(self: Response) -> HeaderSet:
        def on_update(header_set: HeaderSet) -> None:
            if not header_set and name in self.headers:
                del self.headers[name]
            elif header_set:
                self.headers[name] = header_set.to_header()

        return parse_set_header(self.headers.get(name), on_update)

    def fset(
        self: Response,
        value: None | (str | dict[str, str | int] | t.Iterable[str]),
    ) -> None:
        if not value:
            del self.headers[name]
        elif isinstance(value, str):
            self.headers[name] = value
        else:
            self.headers[name] = dump_header(value)

    return property(fget, fset, doc=doc)


class Response:
    """Represents the non-IO parts of an HTTP response, specifically the
    status and headers but not the body.

    This class is not meant for general use. It should only be used when
    implementing WSGI, ASGI, or another HTTP application spec. Werkzeug
    provides a WSGI implementation at :cls:`werkzeug.wrappers.Response`.

    :param status: The status code for the response. Either an int, in
        which case the default status message is added, or a string in
        the form ``{code} {message}``, like ``404 Not Found``. Defaults
        to 200.
    :param headers: A :class:`~werkzeug.datastructures.Headers` object,
        or a list of ``(key, value)`` tuples that will be converted to a
        ``Headers`` object.
    :param mimetype: The mime type (content type without charset or
        other parameters) of the response. If the value starts with
        ``text/`` (or matches some other special cases), the charset
        will be added to create the ``content_type``.
    :param content_type: The full content type of the response.
        Overrides building the value from ``mimetype``.

    .. versionchanged:: 3.0
        The ``charset`` attribute was removed.

    .. versionadded:: 2.0
    """

    #: the default status if none is provided.
    default_status = 200

    #: the default mimetype if none is provided.
    default_mimetype: str | None = "text/plain"

    #: Warn if a cookie header exceeds this size. The default, 4093, should be
    #: safely `supported by most browsers <cookie_>`_. A cookie larger than
    #: this size will still be sent, but it may be ignored or handled
    #: incorrectly by some browsers. Set to 0 to disable this check.
    #:
    #: .. versionadded:: 0.13
    #:
    #: .. _`cookie`: http://browsercookielimits.squawky.net/
    max_cookie_size = 4093

    # A :class:`Headers` object representing the response headers.
    headers: Headers

    def __init__(
        self,
        status: int | str | HTTPStatus | None = None,
        headers: t.Mapping[str, str | t.Iterable[str]]
        | t.Iterable[tuple[str, str]]
        | None = None,
        mimetype: str | None = None,
        content_type: str | None = None,
    ) -> None:
        if isinstance(headers, Headers):
            self.headers = headers
        elif not headers:
            self.headers = Headers()
        else:
            self.headers = Headers(headers)

        if content_type is None:
            if mimetype is None and "content-type" not in self.headers:
                mimetype = self.default_mimetype
            if mimetype is not None:
                mimetype = get_content_type(mimetype, "utf-8")
            content_type = mimetype
        if content_type is not None:
            self.headers["Content-Type"] = content_type
        if status is None:
            status = self.default_status
        self.status = status

    def __repr__(self) -> str:
        return f"<{type(self).__name__} [{self.status}]>"

    @property
    def status_code(self) -> int:
        """The HTTP status code as a number."""
        return self._status_code

    @status_code.setter
    def status_code(self, code: int) -> None:
        self.status = code

    @property
    def status(self) -> str:
        """The HTTP status code as a string."""
        return self._status

    @status.setter
    def status(self, value: str | int | HTTPStatus) -> None:
        self._status, self._status_code = self._clean_status(value)

    def _clean_status(self, value: str | int | HTTPStatus) -> tuple[str, int]:
        if isinstance(value, (int, HTTPStatus)):
            status_code = int(value)
        else:
            value = value.strip()

            if not value:
                raise ValueError("Empty status argument")

            code_str, sep, _ = value.partition(" ")

            try:
                status_code = int(code_str)
            except ValueError:
                # only message
                return f"0 {value}", 0

            if sep:
                # code and message
                return value, status_code

        # only code, look up message
        try:
            status = f"{status_code} {HTTP_STATUS_CODES[status_code].upper()}"
        except KeyError:
            status = f"{status_code} UNKNOWN"

        return status, status_code

    def set_cookie(
        self,
        key: str,
        value: str = "",
        max_age: timedelta | int | None = None,
        expires: str | datetime | int | float | None = None,
        path: str | None = "/",
        domain: str | None = None,
        secure: bool = False,
        httponly: bool = False,
        samesite: str | None = None,
        partitioned: bool = False,
    ) -> None:
        """Sets a cookie.

        A warning is raised if the size of the cookie header exceeds
        :attr:`max_cookie_size`, but the header will still be set.

        :param key: the key (name) of the cookie to be set.
        :param value: the value of the cookie.
        :param max_age: should be a number of seconds, or `None` (default) if
                        the cookie should last only as long as the client's
                        browser session.
        :param expires: should be a `datetime` object or UNIX timestamp.
        :param path: limits the cookie to a given path, per default it will
                     span the whole domain.
        :param domain: if you want to set a cross-domain cookie.  For example,
                       ``domain="example.com"`` will set a cookie that is
                       readable by the domain ``www.example.com``,
                       ``foo.example.com`` etc.  Otherwise, a cookie will only
                       be readable by the domain that set it.
        :param secure: If ``True``, the cookie will only be available
            via HTTPS.
        :param httponly: Disallow JavaScript access to the cookie.
        :param samesite: Limit the scope of the cookie to only be
            attached to requests that are "same-site".
        :param partitioned: If ``True``, the cookie will be partitioned.

        .. versionchanged:: 3.1
            The ``partitioned`` parameter was added.
        """
        self.headers.add(
            "Set-Cookie",
            dump_cookie(
                key,
                value=value,
                max_age=max_age,
                expires=expires,
                path=path,
                domain=domain,
                secure=secure,
                httponly=httponly,
                max_size=self.max_cookie_size,
                samesite=samesite,
                partitioned=partitioned,
            ),
        )

    def delete_cookie(
        self,
        key: str,
        path: str | None = "/",
        domain: str | None = None,
        secure: bool = False,
        httponly: bool = False,
        samesite: str | None = None,
        partitioned: bool = False,
    ) -> None:
        """Delete a cookie.  Fails silently if key doesn't exist.

        :param key: the key (name) of the cookie to be deleted.
        :param path: if the cookie that should be deleted was limited to a
                     path, the path has to be defined here.
        :param domain: if the cookie that should be deleted was limited to a
                       domain, that domain has to be defined here.
        :param secure: If ``True``, the cookie will only be available
            via HTTPS.
        :param httponly: Disallow JavaScript access to the cookie.
        :param samesite: Limit the scope of the cookie to only be
            attached to requests that are "same-site".
        :param partitioned: If ``True``, the cookie will be partitioned.
        """
        self.set_cookie(
            key,
            expires=0,
            max_age=0,
            path=path,
            domain=domain,
            secure=secure,
            httponly=httponly,
            samesite=samesite,
            partitioned=partitioned,
        )

    @property
    def is_json(self) -> bool:
        """Check if the mimetype indicates JSON data, either
        :mimetype:`application/json` or :mimetype:`application/*+json`.
        """
        mt = self.mimetype
        return mt is not None and (
            mt == "application/json"
            or mt.startswith("application/")
            and mt.endswith("+json")
        )

    # Common Descriptors

    @property
    def mimetype(self) -> str | None:
        """The mimetype (content type without charset etc.)"""
        ct = self.headers.get("content-type")

        if ct:
            return ct.split(";")[0].strip()
        else:
            return None

    @mimetype.setter
    def mimetype(self, value: str) -> None:
        self.headers["Content-Type"] = get_content_type(value, "utf-8")

    @property
    def mimetype_params(self) -> dict[str, str]:
        """The mimetype parameters as dict. For example if the
        content type is ``text/html; charset=utf-8`` the params would be
        ``{'charset': 'utf-8'}``.

        .. versionadded:: 0.5
        """

        def on_update(d: CallbackDict[str, str]) -> None:
            self.headers["Content-Type"] = dump_options_header(self.mimetype, d)

        d = parse_options_header(self.headers.get("content-type", ""))[1]
        return CallbackDict(d, on_update)

    location = header_property[str](
        "Location",
        doc="""The Location response-header field is used to redirect
        the recipient to a location other than the Request-URI for
        completion of the request or identification of a new
        resource.""",
    )
    age = header_property(
        "Age",
        None,
        parse_age,
        dump_age,  # type: ignore
        doc="""The Age response-header field conveys the sender's
        estimate of the amount of time since the response (or its
        revalidation) was generated at the origin server.

        Age values are non-negative decimal integers, representing time
        in seconds.""",
    )
    content_type = header_property[str](
        "Content-Type",
        doc="""The Content-Type entity-header field indicates the media
        type of the entity-body sent to the recipient or, in the case of
        the HEAD method, the media type that would have been sent had
        the request been a GET.""",
    )
    content_length = header_property(
        "Content-Length",
        None,
        int,
        str,
        doc="""The Content-Length entity-header field indicates the size
        of the entity-body, in decimal number of OCTETs, sent to the
        recipient or, in the case of the HEAD method, the size of the
        entity-body that would have been sent had the request been a
        GET.""",
    )
    content_location = header_property[str](
        "Content-Location",
        doc="""The Content-Location entity-header field MAY be used to
        supply the resource location for the entity enclosed in the
        message when that entity is accessible from a location separate
        from the requested resource's URI.""",
    )
    content_encoding = header_property[str](
        "Content-Encoding",
        doc="""The Content-Encoding entity-header field is used as a
        modifier to the media-type. When present, its value indicates
        what additional content codings have been applied to the
        entity-body, and thus what decoding mechanisms must be applied
        in order to obtain the media-type referenced by the Content-Type
        header field.""",
    )
    content_md5 = header_property[str](
        "Content-MD5",
        doc="""The Content-MD5 entity-header field, as defined in
        RFC 1864, is an MD5 digest of the entity-body for the purpose of
        providing an end-to-end message integrity check (MIC) of the
        entity-body. (Note: a MIC is good for detecting accidental
        modification of the entity-body in transit, but is not proof
        against malicious attacks.)""",
    )
    date = header_property(
        "Date",
        None,
        parse_date,
        http_date,
        doc="""The Date general-header field represents the date and
        time at which the message was originated, having the same
        semantics as orig-date in RFC 822.

        .. versionchanged:: 2.0
            The datetime object is timezone-aware.
        """,
    )
    expires = header_property(
        "Expires",
        None,
        parse_date,
        http_date,
        doc="""The Expires entity-header field gives the date/time after
        which the response is considered stale. A stale cache entry may
        not normally be returned by a cache.

        .. versionchanged:: 2.0
            The datetime object is timezone-aware.
        """,
    )
    last_modified = header_property(
        "Last-Modified",
        None,
        parse_date,
        http_date,
        doc="""The Last-Modified entity-header field indicates the date
        and time at which the origin server believes the variant was
        last modified.

        .. versionchanged:: 2.0
            The datetime object is timezone-aware.
        """,
    )

    @property
    def retry_after(self) -> datetime | None:
        """The Retry-After response-header field can be used with a
        503 (Service Unavailable) response to indicate how long the
        service is expected to be unavailable to the requesting client.

        Time in seconds until expiration or date.

        .. versionchanged:: 2.0
            The datetime object is timezone-aware.
        """
        value = self.headers.get("retry-after")
        if value is None:
            return None

        try:
            seconds = int(value)
        except ValueError:
            return parse_date(value)

        return datetime.now(timezone.utc) + timedelta(seconds=seconds)

    @retry_after.setter
    def retry_after(self, value: datetime | int | str | None) -> None:
        if value is None:
            if "retry-after" in self.headers:
                del self.headers["retry-after"]
            return
        elif isinstance(value, datetime):
            value = http_date(value)
        else:
            value = str(value)
        self.headers["Retry-After"] = value

    vary = _set_property(
        "Vary",
        doc="""The Vary field value indicates the set of request-header
        fields that fully determines, while the response is fresh,
        whether a cache is permitted to use the response to reply to a
        subsequent request without revalidation.""",
    )
    content_language = _set_property(
        "Content-Language",
        doc="""The Content-Language entity-header field describes the
        natural language(s) of the intended audience for the enclosed
        entity. Note that this might not be equivalent to all the
        languages used within the entity-body.""",
    )
    allow = _set_property(
        "Allow",
        doc="""The Allow entity-header field lists the set of methods
        supported by the resource identified by the Request-URI. The
        purpose of this field is strictly to inform the recipient of
        valid methods associated with the resource. An Allow header
        field MUST be present in a 405 (Method Not Allowed)
        response.""",
    )

    # ETag

    @property
    def cache_control(self) -> ResponseCacheControl:
        """The Cache-Control general-header field is used to specify
        directives that MUST be obeyed by all caching mechanisms along the
        request/response chain.
        """

        def on_update(cache_control: _CacheControl) -> None:
            if not cache_control and "cache-control" in self.headers:
                del self.headers["cache-control"]
            elif cache_control:
                self.headers["Cache-Control"] = cache_control.to_header()

        return parse_cache_control_header(
            self.headers.get("cache-control"), on_update, ResponseCacheControl
        )

    def set_etag(self, etag: str, weak: bool = False) -> None:
        """Set the etag, and override the old one if there was one."""
        self.headers["ETag"] = quote_etag(etag, weak)

    def get_etag(self) -> tuple[str, bool] | tuple[None, None]:
        """Return a tuple in the form ``(etag, is_weak)``.  If there is no
        ETag the return value is ``(None, None)``.
        """
        return unquote_etag(self.headers.get("ETag"))

    accept_ranges = header_property[str](
        "Accept-Ranges",
        doc="""The `Accept-Ranges` header. Even though the name would
        indicate that multiple values are supported, it must be one
        string token only.

        The values ``'bytes'`` and ``'none'`` are common.

        .. versionadded:: 0.7""",
    )

    @property
    def content_range(self) -> ContentRange:
        """The ``Content-Range`` header as a
        :class:`~werkzeug.datastructures.ContentRange` object. Available
        even if the header is not set.

        .. versionadded:: 0.7
        """

        def on_update(rng: ContentRange) -> None:
            if not rng:
                del self.headers["content-range"]
            else:
                self.headers["Content-Range"] = rng.to_header()

        rv = parse_content_range_header(self.headers.get("content-range"), on_update)
        # always provide a content range object to make the descriptor
        # more user friendly.  It provides an unset() method that can be
        # used to remove the header quickly.
        if rv is None:
            rv = ContentRange(None, None, None, on_update=on_update)
        return rv

    @content_range.setter
    def content_range(self, value: ContentRange | str | None) -> None:
        if not value:
            del self.headers["content-range"]
        elif isinstance(value, str):
            self.headers["Content-Range"] = value
        else:
            self.headers["Content-Range"] = value.to_header()

    # Authorization

    @property
    def www_authenticate(self) -> WWWAuthenticate:
        """The ``WWW-Authenticate`` header parsed into a :class:`.WWWAuthenticate`
        object. Modifying the object will modify the header value.

        This header is not set by default. To set this header, assign an instance of
        :class:`.WWWAuthenticate` to this attribute.

        .. code-block:: python

            response.www_authenticate = WWWAuthenticate(
                "basic", {"realm": "Authentication Required"}
            )

        Multiple values for this header can be sent to give the client multiple options.
        Assign a list to set multiple headers. However, modifying the items in the list
        will not automatically update the header values, and accessing this attribute
        will only ever return the first value.

        To unset this header, assign ``None`` or use ``del``.

        .. versionchanged:: 2.3
            This attribute can be assigned to set the header. A list can be assigned
            to set multiple header values. Use ``del`` to unset the header.

        .. versionchanged:: 2.3
            :class:`WWWAuthenticate` is no longer a ``dict``. The ``token`` attribute
            was added for auth challenges that use a token instead of parameters.
        """
        value = WWWAuthenticate.from_header(self.headers.get("WWW-Authenticate"))

        if value is None:
            value = WWWAuthenticate("basic")

        def on_update(value: WWWAuthenticate) -> None:
            self.www_authenticate = value

        value._on_update = on_update
        return value

    @www_authenticate.setter
    def www_authenticate(
        self, value: WWWAuthenticate | list[WWWAuthenticate] | None
    ) -> None:
        if not value:  # None or empty list
            del self.www_authenticate
        elif isinstance(value, list):
            # Clear any existing header by setting the first item.
            self.headers.set("WWW-Authenticate", value[0].to_header())

            for item in value[1:]:
                # Add additional header lines for additional items.
                self.headers.add("WWW-Authenticate", item.to_header())
        else:
            self.headers.set("WWW-Authenticate", value.to_header())

            def on_update(value: WWWAuthenticate) -> None:
                self.www_authenticate = value

            # When setting a single value, allow updating it directly.
            value._on_update = on_update

    @www_authenticate.deleter
    def www_authenticate(self) -> None:
        if "WWW-Authenticate" in self.headers:
            del self.headers["WWW-Authenticate"]

    # CSP

    @property
    def content_security_policy(self) -> ContentSecurityPolicy:
        """The ``Content-Security-Policy`` header as a
        :class:`~werkzeug.datastructures.ContentSecurityPolicy` object. Available
        even if the header is not set.

        The Content-Security-Policy header adds an additional layer of
        security to help detect and mitigate certain types of attacks.
        """

        def on_update(csp: ContentSecurityPolicy) -> None:
            if not csp:
                del self.headers["content-security-policy"]
            else:
                self.headers["Content-Security-Policy"] = csp.to_header()

        rv = parse_csp_header(self.headers.get("content-security-policy"), on_update)
        if rv is None:
            rv = ContentSecurityPolicy(None, on_update=on_update)
        return rv

    @content_security_policy.setter
    def content_security_policy(
        self, value: ContentSecurityPolicy | str | None
    ) -> None:
        if not value:
            del self.headers["content-security-policy"]
        elif isinstance(value, str):
            self.headers["Content-Security-Policy"] = value
        else:
            self.headers["Content-Security-Policy"] = value.to_header()

    @property
    def content_security_policy_report_only(self) -> ContentSecurityPolicy:
        """The ``Content-Security-policy-report-only`` header as a
        :class:`~werkzeug.datastructures.ContentSecurityPolicy` object. Available
        even if the header is not set.

        The Content-Security-Policy-Report-Only header adds a csp policy
        that is not enforced but is reported thereby helping detect
        certain types of attacks.
        """

        def on_update(csp: ContentSecurityPolicy) -> None:
            if not csp:
                del self.headers["content-security-policy-report-only"]
            else:
                self.headers["Content-Security-policy-report-only"] = csp.to_header()

        rv = parse_csp_header(
            self.headers.get("content-security-policy-report-only"), on_update
        )
        if rv is None:
            rv = ContentSecurityPolicy(None, on_update=on_update)
        return rv

    @content_security_policy_report_only.setter
    def content_security_policy_report_only(
        self, value: ContentSecurityPolicy | str | None
    ) -> None:
        if not value:
            del self.headers["content-security-policy-report-only"]
        elif isinstance(value, str):
            self.headers["Content-Security-policy-report-only"] = value
        else:
            self.headers["Content-Security-policy-report-only"] = value.to_header()

    # CORS

    @property
    def access_control_allow_credentials(self) -> bool:
        """Whether credentials can be shared by the browser to
        JavaScript code. As part of the preflight request it indicates
        whether credentials can be used on the cross origin request.
        """
        return "Access-Control-Allow-Credentials" in self.headers

    @access_control_allow_credentials.setter
    def access_control_allow_credentials(self, value: bool | None) -> None:
        if value is True:
            self.headers["Access-Control-Allow-Credentials"] = "true"
        else:
            self.headers.pop("Access-Control-Allow-Credentials", None)

    access_control_allow_headers = header_property(
        "Access-Control-Allow-Headers",
        load_func=parse_set_header,
        dump_func=dump_header,
        doc="Which headers can be sent with the cross origin request.",
    )

    access_control_allow_methods = header_property(
        "Access-Control-Allow-Methods",
        load_func=parse_set_header,
        dump_func=dump_header,
        doc="Which methods can be used for the cross origin request.",
    )

    access_control_allow_origin = header_property[str](
        "Access-Control-Allow-Origin",
        doc="The origin or '*' for any origin that may make cross origin requests.",
    )

    access_control_expose_headers = header_property(
        "Access-Control-Expose-Headers",
        load_func=parse_set_header,
        dump_func=dump_header,
        doc="Which headers can be shared by the browser to JavaScript code.",
    )

    access_control_max_age = header_property(
        "Access-Control-Max-Age",
        load_func=int,
        dump_func=str,
        doc="The maximum age in seconds the access control settings can be cached for.",
    )

    cross_origin_opener_policy = header_property[COOP](
        "Cross-Origin-Opener-Policy",
        load_func=lambda value: COOP(value),
        dump_func=lambda value: value.value,
        default=COOP.UNSAFE_NONE,
        doc="""Allows control over sharing of browsing context group with cross-origin
        documents. Values must be a member of the :class:`werkzeug.http.COOP` enum.""",
    )

    cross_origin_embedder_policy = header_property[COEP](
        "Cross-Origin-Embedder-Policy",
        load_func=lambda value: COEP(value),
        dump_func=lambda value: value.value,
        default=COEP.UNSAFE_NONE,
        doc="""Prevents a document from loading any cross-origin resources that do not
        explicitly grant the document permission. Values must be a member of the
        :class:`werkzeug.http.COEP` enum.""",
    )
