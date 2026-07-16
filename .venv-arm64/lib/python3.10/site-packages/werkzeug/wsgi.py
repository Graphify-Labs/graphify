from __future__ import annotations

import io
import typing as t
from functools import partial
from functools import update_wrapper

from .exceptions import ClientDisconnected
from .exceptions import RequestEntityTooLarge
from .sansio import utils as _sansio_utils
from .sansio.utils import host_is_trusted  # noqa: F401 # Imported as part of API

if t.TYPE_CHECKING:
    from _typeshed.wsgi import WSGIApplication
    from _typeshed.wsgi import WSGIEnvironment


def responder(f: t.Callable[..., WSGIApplication]) -> WSGIApplication:
    """Marks a function as responder.  Decorate a function with it and it
    will automatically call the return value as WSGI application.

    Example::

        @responder
        def application(environ, start_response):
            return Response('Hello World!')
    """
    return update_wrapper(lambda *a: f(*a)(*a[-2:]), f)


def get_current_url(
    environ: WSGIEnvironment,
    root_only: bool = False,
    strip_querystring: bool = False,
    host_only: bool = False,
    trusted_hosts: t.Collection[str] | None = None,
) -> str:
    """Recreate the URL for a request from the parts in a WSGI
    environment.

    The URL is an IRI, not a URI, so it may contain Unicode characters.
    Use :func:`~werkzeug.urls.iri_to_uri` to convert it to ASCII.

    :param environ: The WSGI environment to get the URL parts from.
    :param root_only: Only build the root path, don't include the
        remaining path or query string.
    :param strip_querystring: Don't include the query string.
    :param host_only: Only build the scheme and host.
    :param trusted_hosts: A list of trusted host names to validate the
        host against.
    """
    parts = {
        "scheme": environ["wsgi.url_scheme"],
        "host": get_host(environ, trusted_hosts),
    }

    if not host_only:
        parts["root_path"] = environ.get("SCRIPT_NAME", "")

        if not root_only:
            parts["path"] = environ.get("PATH_INFO", "")

            if not strip_querystring:
                parts["query_string"] = environ.get("QUERY_STRING", "").encode("latin1")

    return _sansio_utils.get_current_url(**parts)


def _get_server(
    environ: WSGIEnvironment,
) -> tuple[str, int | None] | None:
    name = environ.get("SERVER_NAME")

    if name is None:
        return None

    try:
        port: int | None = int(environ.get("SERVER_PORT", None))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        # unix socket
        port = None

    return name, port


def get_host(
    environ: WSGIEnvironment, trusted_hosts: t.Collection[str] | None = None
) -> str:
    """Get and validate a request's ``host:port`` based on the values in the
    given WSGI environ.

    The ``Host`` header sent by the client is preferred. Otherwise, the server's
    configured address is used. If the server address is a Unix socket, it is
    ignored. The port is omitted if it matches the standard HTTP or HTTPS ports.

    The value is passed through :func:`host_is_trusted`. The host must be made
    up of valid characters, but this does not check validity beyond that. If a
    list of trusted domains is given, the domain must match one.

    :param environ: The WSGI environ.
    :param trusted_hosts: A list of trusted domains to match. These should
        already be IDNA encoded, but will be encoded if needed. The port is
        ignored for this check. If a name starts with a dot it will match as a
        suffix, accepting all subdomains. If empty or ``None``, all domains are
        allowed.

    :return: Host, with port if necessary.
    :raise .SecurityError: If the host is not trusted.

    .. versionchanged:: 3.2
        The characters of the host value are validated. The empty string is no
        longer allowed if no header value is available.

    .. versionchanged:: 3.2
        When using the server address, Unix sockets are ignored.

    .. versionchanged:: 3.1.3
        If ``SERVER_NAME`` is IPv6, it is wrapped in ``[]``.
    """
    return _sansio_utils.get_host(
        environ["wsgi.url_scheme"],
        environ.get("HTTP_HOST"),
        _get_server(environ),
        trusted_hosts,
    )


def get_content_length(environ: WSGIEnvironment) -> int | None:
    """Return the ``Content-Length`` header value as an int. If the header is not given
    or the ``Transfer-Encoding`` header is ``chunked``, ``None`` is returned to indicate
    a streaming request. If the value is not an integer, or negative, 0 is returned.

    :param environ: The WSGI environ to get the content length from.

    .. versionadded:: 0.9
    """
    return _sansio_utils.get_content_length(
        http_content_length=environ.get("CONTENT_LENGTH"),
        http_transfer_encoding=environ.get("HTTP_TRANSFER_ENCODING"),
    )


def get_input_stream(
    environ: WSGIEnvironment,
    safe_fallback: bool = True,
    max_content_length: int | None = None,
) -> t.IO[bytes]:
    """Return the WSGI input stream, wrapped so that it may be read safely without going
    past the ``Content-Length`` header value or ``max_content_length``.

    If ``Content-Length`` exceeds ``max_content_length``, a
    :exc:`RequestEntityTooLarge`` ``413 Content Too Large`` error is raised.

    If the WSGI server sets ``environ["wsgi.input_terminated"]``, it indicates that the
    server handles terminating the stream, so it is safe to read directly. For example,
    a server that knows how to handle chunked requests safely would set this.

    If ``max_content_length`` is set, it can be enforced on streams if
    ``wsgi.input_terminated`` is set. Otherwise, an empty stream is returned unless the
    user explicitly disables this safe fallback.

    If the limit is reached before the underlying stream is exhausted (such as a file
    that is too large, or an infinite stream), the remaining contents of the stream
    cannot be read safely. Depending on how the server handles this, clients may show a
    "connection reset" failure instead of seeing the 413 response.

    :param environ: The WSGI environ containing the stream.
    :param safe_fallback: Return an empty stream when ``Content-Length`` is not set.
        Disabling this allows infinite streams, which can be a denial-of-service risk.
    :param max_content_length: The maximum length that content-length or streaming
        requests may not exceed.

    .. versionchanged:: 2.3.2
        ``max_content_length`` is only applied to streaming requests if the server sets
        ``wsgi.input_terminated``.

    .. versionchanged:: 2.3
        Check ``max_content_length`` and raise an error if it is exceeded.

    .. versionadded:: 0.9
    """
    stream = t.cast(t.IO[bytes], environ["wsgi.input"])
    content_length = get_content_length(environ)

    if content_length is not None and max_content_length is not None:
        if content_length > max_content_length:
            raise RequestEntityTooLarge()

    # A WSGI server can set this to indicate that it terminates the input stream. In
    # that case the stream is safe without wrapping, or can enforce a max length.
    if "wsgi.input_terminated" in environ:
        if max_content_length is not None:
            # If this is moved above, it can cause the stream to hang if a read attempt
            # is made when the client sends no data. For example, the development server
            # does not handle buffering except for chunked encoding.
            return t.cast(
                t.IO[bytes], LimitedStream(stream, max_content_length, is_max=True)
            )

        return stream

    # No limit given, return an empty stream unless the user explicitly allows the
    # potentially infinite stream. An infinite stream is dangerous if it's not expected,
    # as it can tie up a worker indefinitely.
    if content_length is None:
        return io.BytesIO() if safe_fallback else stream

    return t.cast(t.IO[bytes], LimitedStream(stream, content_length))


def get_path_info(environ: WSGIEnvironment) -> str:
    """Return ``PATH_INFO`` from  the WSGI environment.

    :param environ: WSGI environment to get the path from.

    .. versionchanged:: 3.0
        The ``charset`` and ``errors`` parameters were removed.

    .. versionadded:: 0.9
    """
    path: bytes = environ.get("PATH_INFO", "").encode("latin1")
    return path.decode(errors="replace")


class ClosingIterator:
    """The WSGI specification requires that all middlewares and gateways
    respect the `close` callback of the iterable returned by the application.
    Because it is useful to add another close action to a returned iterable
    and adding a custom iterable is a boring task this class can be used for
    that::

        return ClosingIterator(app(environ, start_response), [cleanup_session,
                                                              cleanup_locals])

    If there is just one close function it can be passed instead of the list.

    A closing iterator is not needed if the application uses response objects
    and finishes the processing if the response is started::

        try:
            return response(environ, start_response)
        finally:
            cleanup_session()
            cleanup_locals()
    """

    def __init__(
        self,
        iterable: t.Iterable[bytes],
        callbacks: None
        | (t.Callable[[], None] | t.Iterable[t.Callable[[], None]]) = None,
    ) -> None:
        iterator = iter(iterable)
        self._next = t.cast(t.Callable[[], bytes], partial(next, iterator))
        if callbacks is None:
            callbacks = []
        elif callable(callbacks):
            callbacks = [callbacks]
        else:
            callbacks = list(callbacks)
        iterable_close = getattr(iterable, "close", None)
        if iterable_close:
            callbacks.insert(0, iterable_close)
        self._callbacks = callbacks

    def __iter__(self) -> ClosingIterator:
        return self

    def __next__(self) -> bytes:
        return self._next()

    def close(self) -> None:
        for callback in self._callbacks:
            callback()


def wrap_file(
    environ: WSGIEnvironment, file: t.IO[bytes], buffer_size: int = 8192
) -> t.Iterable[bytes]:
    """Wraps a file.  This uses the WSGI server's file wrapper if available
    or otherwise the generic :class:`FileWrapper`.

    .. versionadded:: 0.5

    If the file wrapper from the WSGI server is used it's important to not
    iterate over it from inside the application but to pass it through
    unchanged.  If you want to pass out a file wrapper inside a response
    object you have to set :attr:`Response.direct_passthrough` to `True`.

    More information about file wrappers are available in :pep:`333`.

    :param file: a :class:`file`-like object with a :meth:`~file.read` method.
    :param buffer_size: number of bytes for one iteration.
    """
    return environ.get("wsgi.file_wrapper", FileWrapper)(  # type: ignore
        file, buffer_size
    )


class FileWrapper:
    """This class can be used to convert a :class:`file`-like object into
    an iterable.  It yields `buffer_size` blocks until the file is fully
    read.

    You should not use this class directly but rather use the
    :func:`wrap_file` function that uses the WSGI server's file wrapper
    support if it's available.

    .. versionadded:: 0.5

    If you're using this object together with a :class:`Response` you have
    to use the `direct_passthrough` mode.

    :param file: a :class:`file`-like object with a :meth:`~file.read` method.
    :param buffer_size: number of bytes for one iteration.
    """

    def __init__(self, file: t.IO[bytes], buffer_size: int = 8192) -> None:
        self.file = file
        self.buffer_size = buffer_size

    def close(self) -> None:
        if hasattr(self.file, "close"):
            self.file.close()

    def seekable(self) -> bool:
        if hasattr(self.file, "seekable"):
            return self.file.seekable()
        if hasattr(self.file, "seek"):
            return True
        return False

    def seek(self, *args: t.Any) -> None:
        if hasattr(self.file, "seek"):
            self.file.seek(*args)

    def tell(self) -> int | None:
        if hasattr(self.file, "tell"):
            return self.file.tell()
        return None

    def __iter__(self) -> FileWrapper:
        return self

    def __next__(self) -> bytes:
        data = self.file.read(self.buffer_size)
        if data:
            return data
        raise StopIteration()


class _RangeWrapper:
    # private for now, but should we make it public in the future ?

    """This class can be used to convert an iterable object into
    an iterable that will only yield a piece of the underlying content.
    It yields blocks until the underlying stream range is fully read.
    The yielded blocks will have a size that can't exceed the original
    iterator defined block size, but that can be smaller.

    If you're using this object together with a :class:`Response` you have
    to use the `direct_passthrough` mode.

    :param iterable: an iterable object with a :meth:`__next__` method.
    :param start_byte: byte from which read will start.
    :param byte_range: how many bytes to read.
    """

    def __init__(
        self,
        iterable: t.Iterable[bytes] | t.IO[bytes],
        start_byte: int = 0,
        byte_range: int | None = None,
    ):
        self.iterable = iter(iterable)
        self.byte_range = byte_range
        self.start_byte = start_byte
        self.end_byte = None

        if byte_range is not None:
            self.end_byte = start_byte + byte_range

        self.read_length = 0
        self.seekable = hasattr(iterable, "seekable") and iterable.seekable()
        self.end_reached = False

    def __iter__(self) -> _RangeWrapper:
        return self

    def _next_chunk(self) -> bytes:
        try:
            chunk = next(self.iterable)
            self.read_length += len(chunk)
            return chunk
        except StopIteration:
            self.end_reached = True
            raise

    def _first_iteration(self) -> tuple[bytes | None, int]:
        chunk = None
        if self.seekable:
            self.iterable.seek(self.start_byte)  # type: ignore
            self.read_length = self.iterable.tell()  # type: ignore
            contextual_read_length = self.read_length
        else:
            while self.read_length <= self.start_byte:
                chunk = self._next_chunk()
            if chunk is not None:
                chunk = chunk[self.start_byte - self.read_length :]
            contextual_read_length = self.start_byte
        return chunk, contextual_read_length

    def _next(self) -> bytes:
        if self.end_reached:
            raise StopIteration()
        chunk = None
        contextual_read_length = self.read_length
        if self.read_length == 0:
            chunk, contextual_read_length = self._first_iteration()
        if chunk is None:
            chunk = self._next_chunk()
        if self.end_byte is not None and self.read_length >= self.end_byte:
            self.end_reached = True
            return chunk[: self.end_byte - contextual_read_length]
        return chunk

    def __next__(self) -> bytes:
        chunk = self._next()
        if chunk:
            return chunk
        self.end_reached = True
        raise StopIteration()

    def close(self) -> None:
        if hasattr(self.iterable, "close"):
            self.iterable.close()


class LimitedStream(io.RawIOBase):
    """Wrap a stream so that it doesn't read more than a given limit. This is used to
    limit ``wsgi.input`` to the ``Content-Length`` header value or
    :attr:`.Request.max_content_length`.

    When attempting to read after the limit has been reached, :meth:`on_exhausted` is
    called. When the limit is a maximum, this raises :exc:`.RequestEntityTooLarge`.

    If reading from the stream returns zero bytes or raises an error,
    :meth:`on_disconnect` is called, which raises :exc:`.ClientDisconnected`. When the
    limit is a maximum and zero bytes were read, no error is raised, since it may be the
    end of the stream.

    If the limit is reached before the underlying stream is exhausted (such as a file
    that is too large, or an infinite stream), the remaining contents of the stream
    cannot be read safely. Depending on how the server handles this, clients may show a
    "connection reset" failure instead of seeing the 413 response.

    :param stream: The stream to read from. Must be a readable binary IO object.
    :param limit: The limit in bytes to not read past. Should be either the
        ``Content-Length`` header value or ``request.max_content_length``.
    :param is_max: Whether the given ``limit`` is ``request.max_content_length`` instead
        of the ``Content-Length`` header value. This changes how exhausted and
        disconnect events are handled.

    .. versionchanged:: 2.3
        Handle ``max_content_length`` differently than ``Content-Length``.

    .. versionchanged:: 2.3
        Implements ``io.RawIOBase`` rather than ``io.IOBase``.
    """

    def __init__(self, stream: t.IO[bytes], limit: int, is_max: bool = False) -> None:
        self._stream = stream
        self._pos = 0
        self.limit = limit
        self._limit_is_max = is_max

    @property
    def is_exhausted(self) -> bool:
        """Whether the current stream position has reached the limit."""
        return self._pos >= self.limit

    def on_exhausted(self) -> None:
        """Called when attempting to read after the limit has been reached.

        The default behavior is to do nothing, unless the limit is a maximum, in which
        case it raises :exc:`.RequestEntityTooLarge`.

        .. versionchanged:: 2.3
            Raises ``RequestEntityTooLarge`` if the limit is a maximum.

        .. versionchanged:: 2.3
            Any return value is ignored.
        """
        if self._limit_is_max:
            raise RequestEntityTooLarge()

    def on_disconnect(self, error: Exception | None = None) -> None:
        """Called when an attempted read receives zero bytes before the limit was
        reached. This indicates that the client disconnected before sending the full
        request body.

        The default behavior is to raise :exc:`.ClientDisconnected`, unless the limit is
        a maximum and no error was raised.

        .. versionchanged:: 2.3
            Added the ``error`` parameter. Do nothing if the limit is a maximum and no
            error was raised.

        .. versionchanged:: 2.3
            Any return value is ignored.
        """
        if not self._limit_is_max or error is not None:
            raise ClientDisconnected()

        # If the limit is a maximum, then we may have read zero bytes because the
        # streaming body is complete. There's no way to distinguish that from the
        # client disconnecting early.

    def exhaust(self) -> bytes:
        """Exhaust the stream by reading until the limit is reached or the client
        disconnects, returning the remaining data.

        .. versionchanged:: 2.3
            Return the remaining data.

        .. versionchanged:: 2.2.3
            Handle case where wrapped stream returns fewer bytes than requested.
        """
        if not self.is_exhausted:
            return self.readall()

        return b""

    def readinto(self, b: bytearray) -> int | None:  # type: ignore[override]
        size = len(b)
        remaining = self.limit - self._pos

        if remaining <= 0:
            self.on_exhausted()
            return 0

        if hasattr(self._stream, "readinto"):
            # Use stream.readinto if it's available.
            if size <= remaining:
                # The size fits in the remaining limit, use the buffer directly.
                try:
                    out_size: int | None = self._stream.readinto(b)
                except (OSError, ValueError) as e:
                    self.on_disconnect(error=e)
                    return 0
            else:
                # Use a temp buffer with the remaining limit as the size.
                temp_b = bytearray(remaining)

                try:
                    out_size = self._stream.readinto(temp_b)
                except (OSError, ValueError) as e:
                    self.on_disconnect(error=e)
                    return 0

                if out_size:
                    b[:out_size] = temp_b
        else:
            # WSGI requires that stream.read is available.
            try:
                data = self._stream.read(min(size, remaining))
            except (OSError, ValueError) as e:
                self.on_disconnect(error=e)
                return 0

            out_size = len(data)
            b[:out_size] = data

        if not out_size:
            # Read zero bytes from the stream.
            self.on_disconnect()
            return 0

        self._pos += out_size
        return out_size

    def readall(self) -> bytes:
        if self.is_exhausted:
            self.on_exhausted()
            return b""

        out = bytearray()

        # The parent implementation uses "while True", which results in an extra read.
        while not self.is_exhausted:
            data = self.read(1024 * 64)

            # Stream may return empty before a max limit is reached.
            if not data:
                break

            out.extend(data)

        return bytes(out)

    def tell(self) -> int:
        """Return the current stream position.

        .. versionadded:: 0.9
        """
        return self._pos

    def readable(self) -> bool:
        return True
