from __future__ import annotations

import json
import typing as t
from http import HTTPStatus
from urllib.parse import urljoin

from .._internal import _get_environ
from ..datastructures import Headers
from ..http import generate_etag
from ..http import http_date
from ..http import is_resource_modified
from ..http import parse_etags
from ..http import parse_range_header
from ..http import remove_entity_headers
from ..sansio.response import Response as _SansIOResponse
from ..urls import iri_to_uri
from ..utils import cached_property
from ..wsgi import _RangeWrapper
from ..wsgi import ClosingIterator
from ..wsgi import get_current_url

if t.TYPE_CHECKING:
    from _typeshed.wsgi import StartResponse
    from _typeshed.wsgi import WSGIApplication
    from _typeshed.wsgi import WSGIEnvironment

    from .request import Request


def _iter_encoded(iterable: t.Iterable[str | bytes]) -> t.Iterator[bytes]:
    for item in iterable:
        if isinstance(item, str):
            yield item.encode()
        else:
            yield item


class Response(_SansIOResponse):
    """Represents an outgoing WSGI HTTP response with body, status, and
    headers. Has properties and methods for using the functionality
    defined by various HTTP specs.

    The response body is flexible to support different use cases. The
    simple form is passing bytes, or a string which will be encoded as
    UTF-8. Passing an iterable of bytes or strings makes this a
    streaming response. A generator is particularly useful for building
    a CSV file in memory or using SSE (Server Sent Events). A file-like
    object is also iterable, although the
    :func:`~werkzeug.utils.send_file` helper should be used in that
    case.

    The response object is itself a WSGI application callable. When
    called (:meth:`__call__`) with ``environ`` and ``start_response``,
    it will pass its status and headers to ``start_response`` then
    return its body as an iterable.

    .. code-block:: python

        from werkzeug.wrappers.response import Response

        def index():
            return Response("Hello, World!")

        def application(environ, start_response):
            path = environ.get("PATH_INFO") or "/"

            if path == "/":
                response = index()
            else:
                response = Response("Not Found", status=404)

            return response(environ, start_response)

    :param response: The data for the body of the response. A string or
        bytes, or tuple or list of strings or bytes, for a fixed-length
        response, or any other iterable of strings or bytes for a
        streaming response. Defaults to an empty body.
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
    :param direct_passthrough: Pass the response body directly through
        as the WSGI iterable. This can be used when the body is a binary
        file or other iterator of bytes, to skip some unnecessary
        checks. Use :func:`~werkzeug.utils.send_file` instead of setting
        this manually.

    .. versionchanged:: 2.1
        Old ``BaseResponse`` and mixin classes were removed.

    .. versionchanged:: 2.0
        Combine ``BaseResponse`` and mixins into a single ``Response``
        class.

    .. versionchanged:: 0.5
        The ``direct_passthrough`` parameter was added.
    """

    #: if set to `False` accessing properties on the response object will
    #: not try to consume the response iterator and convert it into a list.
    #:
    #: .. versionadded:: 0.6.2
    #:
    #:    That attribute was previously called `implicit_seqence_conversion`.
    #:    (Notice the typo).  If you did use this feature, you have to adapt
    #:    your code to the name change.
    implicit_sequence_conversion = True

    #: If a redirect ``Location`` header is a relative URL, make it an
    #: absolute URL, including scheme and domain.
    #:
    #: .. versionchanged:: 2.1
    #:     This is disabled by default, so responses will send relative
    #:     redirects.
    #:
    #: .. versionadded:: 0.8
    autocorrect_location_header = False

    #: Should this response object automatically set the content-length
    #: header if possible?  This is true by default.
    #:
    #: .. versionadded:: 0.8
    automatically_set_content_length = True

    #: The response body to send as the WSGI iterable. A list of strings
    #: or bytes represents a fixed-length response, any other iterable
    #: is a streaming response. Strings are encoded to bytes as UTF-8.
    #:
    #: Do not set to a plain string or bytes, that will cause sending
    #: the response to be very inefficient as it will iterate one byte
    #: at a time.
    response: t.Iterable[str] | t.Iterable[bytes]

    def __init__(
        self,
        response: t.Iterable[bytes] | bytes | t.Iterable[str] | str | None = None,
        status: int | str | HTTPStatus | None = None,
        headers: t.Mapping[str, str | t.Iterable[str]]
        | t.Iterable[tuple[str, str]]
        | None = None,
        mimetype: str | None = None,
        content_type: str | None = None,
        direct_passthrough: bool = False,
    ) -> None:
        super().__init__(
            status=status,
            headers=headers,
            mimetype=mimetype,
            content_type=content_type,
        )

        #: Pass the response body directly through as the WSGI iterable.
        #: This can be used when the body is a binary file or other
        #: iterator of bytes, to skip some unnecessary checks. Use
        #: :func:`~werkzeug.utils.send_file` instead of setting this
        #: manually.
        self.direct_passthrough = direct_passthrough
        self._on_close: list[t.Callable[[], t.Any]] = []

        # we set the response after the headers so that if a class changes
        # the charset attribute, the data is set in the correct charset.
        if response is None:
            self.response = []
        elif isinstance(response, (str, bytes, bytearray)):
            self.set_data(response)
        else:
            self.response = response

    def call_on_close(self, func: t.Callable[[], t.Any]) -> t.Callable[[], t.Any]:
        """Adds a function to the internal list of functions that should
        be called as part of closing down the response.  Since 0.7 this
        function also returns the function that was passed so that this
        can be used as a decorator.

        .. versionadded:: 0.6
        """
        self._on_close.append(func)
        return func

    def __repr__(self) -> str:
        if self.is_sequence:
            body_info = f"{sum(map(len, self.iter_encoded()))} bytes"
        else:
            body_info = "streamed" if self.is_streamed else "likely-streamed"
        return f"<{type(self).__name__} {body_info} [{self.status}]>"

    @classmethod
    def force_type(
        cls, response: Response, environ: WSGIEnvironment | None = None
    ) -> Response:
        """Enforce that the WSGI response is a response object of the current
        type.  Werkzeug will use the :class:`Response` internally in many
        situations like the exceptions.  If you call :meth:`get_response` on an
        exception you will get back a regular :class:`Response` object, even
        if you are using a custom subclass.

        This method can enforce a given response type, and it will also
        convert arbitrary WSGI callables into response objects if an environ
        is provided::

            # convert a Werkzeug response object into an instance of the
            # MyResponseClass subclass.
            response = MyResponseClass.force_type(response)

            # convert any WSGI application into a response object
            response = MyResponseClass.force_type(response, environ)

        This is especially useful if you want to post-process responses in
        the main dispatcher and use functionality provided by your subclass.

        Keep in mind that this will modify response objects in place if
        possible!

        :param response: a response object or wsgi application.
        :param environ: a WSGI environment object.
        :return: a response object.
        """
        if not isinstance(response, Response):
            if environ is None:
                raise TypeError(
                    "cannot convert WSGI application into response"
                    " objects without an environ"
                )

            from ..test import run_wsgi_app

            response = Response(*run_wsgi_app(response, environ))

        response.__class__ = cls
        return response

    @classmethod
    def from_app(
        cls, app: WSGIApplication, environ: WSGIEnvironment, buffered: bool = False
    ) -> Response:
        """Create a new response object from an application output.  This
        works best if you pass it an application that returns a generator all
        the time.  Sometimes applications may use the `write()` callable
        returned by the `start_response` function.  This tries to resolve such
        edge cases automatically.  But if you don't get the expected output
        you should set `buffered` to `True` which enforces buffering.

        :param app: the WSGI application to execute.
        :param environ: the WSGI environment to execute against.
        :param buffered: set to `True` to enforce buffering.
        :return: a response object.
        """
        from ..test import run_wsgi_app

        return cls(*run_wsgi_app(app, environ, buffered))

    @t.overload
    def get_data(self, as_text: t.Literal[False] = False) -> bytes: ...

    @t.overload
    def get_data(self, as_text: t.Literal[True]) -> str: ...

    def get_data(self, as_text: bool = False) -> bytes | str:
        """The string representation of the response body.  Whenever you call
        this property the response iterable is encoded and flattened.  This
        can lead to unwanted behavior if you stream big data.

        This behavior can be disabled by setting
        :attr:`implicit_sequence_conversion` to `False`.

        If `as_text` is set to `True` the return value will be a decoded
        string.

        .. versionadded:: 0.9
        """
        self._ensure_sequence()
        rv = b"".join(self.iter_encoded())

        if as_text:
            return rv.decode()

        return rv

    def set_data(self, value: bytes | str) -> None:
        """Sets a new string as response.  The value must be a string or
        bytes. If a string is set it's encoded to the charset of the
        response (utf-8 by default).

        .. versionadded:: 0.9
        """
        if isinstance(value, str):
            value = value.encode()
        self.response = [value]
        if self.automatically_set_content_length:
            self.headers["Content-Length"] = str(len(value))

    data = property(
        get_data,
        set_data,
        doc="A descriptor that calls :meth:`get_data` and :meth:`set_data`.",
    )

    def calculate_content_length(self) -> int | None:
        """Returns the content length if available or `None` otherwise."""
        try:
            self._ensure_sequence()
        except RuntimeError:
            return None
        return sum(len(x) for x in self.iter_encoded())

    def _ensure_sequence(self, mutable: bool = False) -> None:
        """This method can be called by methods that need a sequence.  If
        `mutable` is true, it will also ensure that the response sequence
        is a standard Python list.

        .. versionadded:: 0.6
        """
        if self.is_sequence:
            # if we need a mutable object, we ensure it's a list.
            if mutable and not isinstance(self.response, list):
                self.response = list(self.response)  # type: ignore
            return
        if self.direct_passthrough:
            raise RuntimeError(
                "Attempted implicit sequence conversion but the"
                " response object is in direct passthrough mode."
            )
        if not self.implicit_sequence_conversion:
            raise RuntimeError(
                "The response object required the iterable to be a"
                " sequence, but the implicit conversion was disabled."
                " Call make_sequence() yourself."
            )
        self.make_sequence()

    def make_sequence(self) -> None:
        """Converts the response iterator in a list.  By default this happens
        automatically if required.  If `implicit_sequence_conversion` is
        disabled, this method is not automatically called and some properties
        might raise exceptions.  This also encodes all the items.

        .. versionadded:: 0.6
        """
        if not self.is_sequence:
            # if we consume an iterable we have to ensure that the close
            # method of the iterable is called if available when we tear
            # down the response
            close = getattr(self.response, "close", None)
            self.response = list(self.iter_encoded())
            if close is not None:
                self.call_on_close(close)

    def iter_encoded(self) -> t.Iterator[bytes]:
        """Iter the response encoded with the encoding of the response.
        If the response object is invoked as WSGI application the return
        value of this method is used as application iterator unless
        :attr:`direct_passthrough` was activated.
        """
        # Encode in a separate function so that self.response is fetched
        # early.  This allows us to wrap the response with the return
        # value from get_app_iter or iter_encoded.
        return _iter_encoded(self.response)

    @property
    def is_streamed(self) -> bool:
        """If the response is streamed (the response is not an iterable with
        a length information) this property is `True`.  In this case streamed
        means that there is no information about the number of iterations.
        This is usually `True` if a generator is passed to the response object.

        This is useful for checking before applying some sort of post
        filtering that should not take place for streamed responses.
        """
        try:
            len(self.response)  # type: ignore
        except (TypeError, AttributeError):
            return True
        return False

    @property
    def is_sequence(self) -> bool:
        """If the iterator is buffered, this property will be `True`.  A
        response object will consider an iterator to be buffered if the
        response attribute is a list or tuple.

        .. versionadded:: 0.6
        """
        return isinstance(self.response, (tuple, list))

    def close(self) -> None:
        """Close the wrapped response if possible.  You can also use the object
        in a with statement which will automatically close it.

        .. versionadded:: 0.9
           Can now be used in a with statement.
        """
        if hasattr(self.response, "close"):
            self.response.close()
        for func in self._on_close:
            func()

    def __enter__(self) -> Response:
        return self

    def __exit__(self, exc_type, exc_value, tb):  # type: ignore
        self.close()

    def freeze(self) -> None:
        """Make the response object ready to be pickled. Does the
        following:

        *   Buffer the response into a list, ignoring
            :attr:`implicity_sequence_conversion` and
            :attr:`direct_passthrough`.
        *   Set the ``Content-Length`` header.
        *   Generate an ``ETag`` header if one is not already set.

        .. versionchanged:: 2.1
            Removed the ``no_etag`` parameter.

        .. versionchanged:: 2.0
            An ``ETag`` header is always added.

        .. versionchanged:: 0.6
            The ``Content-Length`` header is set.
        """
        # Always freeze the encoded response body, ignore
        # implicit_sequence_conversion and direct_passthrough.
        self.response = list(self.iter_encoded())
        self.headers["Content-Length"] = str(sum(map(len, self.response)))
        self.add_etag()

    def get_wsgi_headers(self, environ: WSGIEnvironment) -> Headers:
        """This is automatically called right before the response is started
        and returns headers modified for the given environment.  It returns a
        copy of the headers from the response with some modifications applied
        if necessary.

        For example the location header (if present) is joined with the root
        URL of the environment.  Also the content length is automatically set
        to zero here for certain status codes.

        .. versionchanged:: 0.6
           Previously that function was called `fix_headers` and modified
           the response object in place.  Also since 0.6, IRIs in location
           and content-location headers are handled properly.

           Also starting with 0.6, Werkzeug will attempt to set the content
           length if it is able to figure it out on its own.  This is the
           case if all the strings in the response iterable are already
           encoded and the iterable is buffered.

        :param environ: the WSGI environment of the request.
        :return: returns a new :class:`~werkzeug.datastructures.Headers`
                 object.
        """
        headers = Headers(self.headers)
        location: str | None = None
        content_location: str | None = None
        content_length: str | int | None = None
        status = self.status_code

        # iterate over the headers to find all values in one go.  Because
        # get_wsgi_headers is used each response that gives us a tiny
        # speedup.
        for key, value in headers:
            ikey = key.lower()
            if ikey == "location":
                location = value
            elif ikey == "content-location":
                content_location = value
            elif ikey == "content-length":
                content_length = value

        if location is not None:
            location = iri_to_uri(location)

            if self.autocorrect_location_header:
                # Make the location header an absolute URL.
                current_url = get_current_url(environ, strip_querystring=True)
                current_url = iri_to_uri(current_url)
                location = urljoin(current_url, location)

            headers["Location"] = location

        # make sure the content location is a URL
        if content_location is not None:
            headers["Content-Location"] = iri_to_uri(content_location)

        if 100 <= status < 200 or status == 204:
            # Per section 3.3.2 of RFC 7230, "a server MUST NOT send a
            # Content-Length header field in any response with a status
            # code of 1xx (Informational) or 204 (No Content)."
            headers.remove("Content-Length")
        elif status == 304:
            remove_entity_headers(headers)

        # if we can determine the content length automatically, we
        # should try to do that.  But only if this does not involve
        # flattening the iterator or encoding of strings in the
        # response. We however should not do that if we have a 304
        # response.
        if (
            self.automatically_set_content_length
            and self.is_sequence
            and content_length is None
            and status not in (204, 304)
            and not (100 <= status < 200)
        ):
            content_length = sum(len(x) for x in self.iter_encoded())
            headers["Content-Length"] = str(content_length)

        return headers

    def get_app_iter(self, environ: WSGIEnvironment) -> t.Iterable[bytes]:
        """Returns the application iterator for the given environ.  Depending
        on the request method and the current status code the return value
        might be an empty response rather than the one from the response.

        If the request method is `HEAD` or the status code is in a range
        where the HTTP specification requires an empty response, an empty
        iterable is returned.

        .. versionadded:: 0.6

        :param environ: the WSGI environment of the request.
        :return: a response iterable.
        """
        status = self.status_code
        if (
            environ["REQUEST_METHOD"] == "HEAD"
            or 100 <= status < 200
            or status in (204, 304)
        ):
            iterable: t.Iterable[bytes] = ()
        elif self.direct_passthrough:
            return self.response  # type: ignore
        else:
            iterable = self.iter_encoded()
        return ClosingIterator(iterable, self.close)

    def get_wsgi_response(
        self, environ: WSGIEnvironment
    ) -> tuple[t.Iterable[bytes], str, list[tuple[str, str]]]:
        """Returns the final WSGI response as tuple.  The first item in
        the tuple is the application iterator, the second the status and
        the third the list of headers.  The response returned is created
        specially for the given environment.  For example if the request
        method in the WSGI environment is ``'HEAD'`` the response will
        be empty and only the headers and status code will be present.

        .. versionadded:: 0.6

        :param environ: the WSGI environment of the request.
        :return: an ``(app_iter, status, headers)`` tuple.
        """
        headers = self.get_wsgi_headers(environ)
        app_iter = self.get_app_iter(environ)
        return app_iter, self.status, headers.to_wsgi_list()

    def __call__(
        self, environ: WSGIEnvironment, start_response: StartResponse
    ) -> t.Iterable[bytes]:
        """Process this response as WSGI application.

        :param environ: the WSGI environment.
        :param start_response: the response callable provided by the WSGI
                               server.
        :return: an application iterator
        """
        app_iter, status, headers = self.get_wsgi_response(environ)
        start_response(status, headers)
        return app_iter

    # JSON

    #: A module or other object that has ``dumps`` and ``loads``
    #: functions that match the API of the built-in :mod:`json` module.
    json_module = json

    @property
    def json(self) -> t.Any | None:
        """The parsed JSON data if :attr:`mimetype` indicates JSON
        (:mimetype:`application/json`, see :attr:`is_json`).

        Calls :meth:`get_json` with default arguments.
        """
        return self.get_json()

    @t.overload
    def get_json(self, force: bool = ..., silent: t.Literal[False] = ...) -> t.Any: ...

    @t.overload
    def get_json(self, force: bool = ..., silent: bool = ...) -> t.Any | None: ...

    def get_json(self, force: bool = False, silent: bool = False) -> t.Any | None:
        """Parse :attr:`data` as JSON. Useful during testing.

        If the mimetype does not indicate JSON
        (:mimetype:`application/json`, see :attr:`is_json`), this
        returns ``None``.

        Unlike :meth:`Request.get_json`, the result is not cached.

        :param force: Ignore the mimetype and always try to parse JSON.
        :param silent: Silence parsing errors and return ``None``
            instead.
        """
        if not (force or self.is_json):
            return None

        data = self.get_data()

        try:
            return self.json_module.loads(data)
        except ValueError:
            if not silent:
                raise

            return None

    # Stream

    @cached_property
    def stream(self) -> ResponseStream:
        """The response iterable as write-only stream."""
        return ResponseStream(self)

    def _wrap_range_response(self, start: int, length: int) -> None:
        """Wrap existing Response in case of Range Request context."""
        if self.status_code == 206:
            self.response = _RangeWrapper(self.response, start, length)  # type: ignore

    def _is_range_request_processable(self, environ: WSGIEnvironment) -> bool:
        """Return ``True`` if `Range` header is present and if underlying
        resource is considered unchanged when compared with `If-Range` header.
        """
        return (
            "HTTP_IF_RANGE" not in environ
            or not is_resource_modified(
                environ,
                self.headers.get("etag"),
                None,
                self.headers.get("last-modified"),
                ignore_if_range=False,
            )
        ) and "HTTP_RANGE" in environ

    def _process_range_request(
        self,
        environ: WSGIEnvironment,
        complete_length: int | None,
        accept_ranges: bool | str,
    ) -> bool:
        """Handle Range Request related headers (RFC7233).  If `Accept-Ranges`
        header is valid, and Range Request is processable, we set the headers
        as described by the RFC, and wrap the underlying response in a
        RangeWrapper.

        Returns ``True`` if Range Request can be fulfilled, ``False`` otherwise.

        :raises: :class:`~werkzeug.exceptions.RequestedRangeNotSatisfiable`
                 if `Range` header could not be parsed or satisfied.

        .. versionchanged:: 3.2
            Adds the ``Accept-Ranges`` header if ``accept_ranges`` is passed,
            even if this is not a satisfiable range request.

        .. versionchanged:: 2.0
            Returns ``False`` if the length is 0.
        """
        from ..exceptions import RequestedRangeNotSatisfiable

        if not accept_ranges:
            return False

        if accept_ranges is True:
            accept_ranges = "bytes"

        self.accept_ranges = accept_ranges

        if not (complete_length and self._is_range_request_processable(environ)):
            return False

        parsed_range = parse_range_header(environ.get("HTTP_RANGE"))

        if parsed_range is None:
            raise RequestedRangeNotSatisfiable(complete_length)

        range_tuple = parsed_range.range_for_length(complete_length)
        content_range_header = parsed_range.to_content_range_header(complete_length)

        if range_tuple is None or content_range_header is None:
            raise RequestedRangeNotSatisfiable(complete_length)

        content_length = range_tuple[1] - range_tuple[0]
        self.content_length = content_length
        self.content_range = content_range_header
        self.status_code = 206
        self._wrap_range_response(range_tuple[0], content_length)
        return True

    def make_conditional(
        self,
        request_or_environ: WSGIEnvironment | Request,
        accept_ranges: bool | str = False,
        complete_length: int | None = None,
    ) -> Response:
        """Make the response conditional to the request.  This method works
        best if an etag was defined for the response already.  The `add_etag`
        method can be used to do that.  If called without etag just the date
        header is set.

        This does nothing if the request method in the request or environ is
        anything but GET or HEAD.

        For optimal performance when handling range requests, it's recommended
        that your response data object implements `seekable`, `seek` and `tell`
        methods as described by :py:class:`io.IOBase`.  Objects returned by
        :meth:`~werkzeug.wsgi.wrap_file` automatically implement those methods.

        It does not remove the body of the response because that's something
        the :meth:`__call__` function does for us automatically.

        Returns self so that you can do ``return resp.make_conditional(req)``
        but modifies the object in-place.

        :param request_or_environ: a request object or WSGI environment to be
                                   used to make the response conditional
                                   against.
        :param accept_ranges: This parameter dictates the value of
                              `Accept-Ranges` header. If ``False`` (default),
                              the header is not set. If ``True``, it will be set
                              to ``"bytes"``. If it's a string, it will use this
                              value.
        :param complete_length: Will be used only in valid Range Requests.
                                It will set `Content-Range` complete length
                                value and compute `Content-Length` real value.
                                This parameter is mandatory for successful
                                Range Requests completion.
        :raises: :class:`~werkzeug.exceptions.RequestedRangeNotSatisfiable`
                 if `Range` header could not be parsed or satisfied.

        .. versionchangedd: 3.2
            Adds the ``Accept-Ranges`` header if ``accept_ranges`` is passed,
            even if this is not a satisfiable range request.

        .. versionchanged:: 2.0
            Range processing is skipped if length is 0 instead of
            raising a 416 Range Not Satisfiable error.
        """
        environ = _get_environ(request_or_environ)
        if environ["REQUEST_METHOD"] in ("GET", "HEAD"):
            # if the date is not in the headers, add it now.  We however
            # will not override an already existing header.  Unfortunately
            # this header will be overridden by many WSGI servers including
            # wsgiref.
            if "date" not in self.headers:
                self.headers["Date"] = http_date()
            is206 = self._process_range_request(environ, complete_length, accept_ranges)
            if not is206 and not is_resource_modified(
                environ,
                self.headers.get("etag"),
                None,
                self.headers.get("last-modified"),
            ):
                if parse_etags(environ.get("HTTP_IF_MATCH")):
                    self.status_code = 412
                else:
                    self.status_code = 304
            if (
                self.automatically_set_content_length
                and "content-length" not in self.headers
            ):
                length = self.calculate_content_length()
                if length is not None:
                    self.headers["Content-Length"] = str(length)
        return self

    def add_etag(self, overwrite: bool = False, weak: bool = False) -> None:
        """Add an etag for the current response if there is none yet.

        .. versionchanged:: 2.0
            SHA-1 is used to generate the value. MD5 may not be
            available in some environments.
        """
        if overwrite or "etag" not in self.headers:
            self.set_etag(generate_etag(self.get_data()), weak)


class ResponseStream:
    """A file descriptor like object used by :meth:`Response.stream` to
    represent the body of the stream. It directly pushes into the
    response iterable of the response object.
    """

    mode = "wb+"

    def __init__(self, response: Response):
        self.response = response
        self.closed = False

    def write(self, value: bytes) -> int:
        if self.closed:
            raise ValueError("I/O operation on closed file")
        self.response._ensure_sequence(mutable=True)
        self.response.response.append(value)  # type: ignore
        self.response.headers.pop("Content-Length", None)
        return len(value)

    def writelines(self, seq: t.Iterable[bytes]) -> None:
        for item in seq:
            self.write(item)

    def close(self) -> None:
        self.closed = True

    def flush(self) -> None:
        if self.closed:
            raise ValueError("I/O operation on closed file")

    def isatty(self) -> bool:
        if self.closed:
            raise ValueError("I/O operation on closed file")
        return False

    def tell(self) -> int:
        self.response._ensure_sequence()
        return sum(map(len, self.response.response))

    @property
    def encoding(self) -> str:
        return "utf-8"
