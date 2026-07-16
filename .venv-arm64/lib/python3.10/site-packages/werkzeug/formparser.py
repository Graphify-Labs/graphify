from __future__ import annotations

import typing as t
from io import BytesIO
from urllib.parse import parse_qsl

from ._internal import _plain_int
from .datastructures import FileStorage
from .datastructures import Headers
from .datastructures import MultiDict
from .exceptions import RequestEntityTooLarge
from .http import parse_options_header
from .sansio.multipart import Data
from .sansio.multipart import Epilogue
from .sansio.multipart import Field
from .sansio.multipart import File
from .sansio.multipart import MultipartDecoder
from .sansio.multipart import NeedData
from .wsgi import get_content_length
from .wsgi import get_input_stream

# there are some platforms where SpooledTemporaryFile is not available.
# In that case we need to provide a fallback.
try:
    from tempfile import SpooledTemporaryFile
except ImportError:
    from tempfile import TemporaryFile

    SpooledTemporaryFile = None  # type: ignore

if t.TYPE_CHECKING:
    import typing as te

    from _typeshed.wsgi import WSGIEnvironment

    t_parse_result = tuple[
        t.IO[bytes], MultiDict[str, str], MultiDict[str, FileStorage]
    ]

    class TStreamFactory(te.Protocol):
        def __call__(
            self,
            total_content_length: int | None,
            content_type: str | None,
            filename: str | None,
            content_length: int | None = None,
        ) -> t.IO[bytes]: ...


F = t.TypeVar("F", bound=t.Callable[..., t.Any])


def default_stream_factory(
    total_content_length: int | None,
    content_type: str | None,
    filename: str | None,
    content_length: int | None = None,
) -> t.IO[bytes]:
    max_size = 1024 * 500

    if SpooledTemporaryFile is not None:
        return t.cast(t.IO[bytes], SpooledTemporaryFile(max_size=max_size, mode="rb+"))
    elif total_content_length is None or total_content_length > max_size:
        return t.cast(t.IO[bytes], TemporaryFile("rb+"))

    return BytesIO()


def parse_form_data(
    environ: WSGIEnvironment,
    stream_factory: TStreamFactory | None = None,
    max_form_memory_size: int | None = None,
    max_content_length: int | None = None,
    cls: type[MultiDict[str, t.Any]] | None = None,
    silent: bool = True,
    *,
    max_form_parts: int | None = None,
) -> t_parse_result:
    """Parse the form data in the environ and return it as tuple in the form
    ``(stream, form, files)``.  You should only call this method if the
    transport method is `POST`, `PUT`, or `PATCH`.

    If the mimetype of the data transmitted is `multipart/form-data` the
    files multidict will be filled with `FileStorage` objects.  If the
    mimetype is unknown the input stream is wrapped and returned as first
    argument, else the stream is empty.

    This is a shortcut for the common usage of :class:`FormDataParser`.

    :param environ: the WSGI environment to be used for parsing.
    :param stream_factory: An optional callable that returns a new read and
                           writeable file descriptor.  This callable works
                           the same as :meth:`Response._get_file_stream`.
    :param max_form_memory_size: the maximum number of bytes to be accepted for
                           in-memory stored form data.  If the data
                           exceeds the value specified an
                           :exc:`~exceptions.RequestEntityTooLarge`
                           exception is raised.
    :param max_content_length: If this is provided and the transmitted data
                               is longer than this value an
                               :exc:`~exceptions.RequestEntityTooLarge`
                               exception is raised.
    :param cls: an optional dict class to use.  If this is not specified
                       or `None` the default :class:`MultiDict` is used.
    :param silent: If set to False parsing errors will not be caught.
    :param max_form_parts: The maximum number of multipart parts to be parsed. If this
        is exceeded, a :exc:`~exceptions.RequestEntityTooLarge` exception is raised.
    :return: A tuple in the form ``(stream, form, files)``.

    .. versionchanged:: 3.0
        The ``charset`` and ``errors`` parameters were removed.

    .. versionchanged:: 2.3
        Added the ``max_form_parts`` parameter.

    .. versionadded:: 0.5.1
       Added the ``silent`` parameter.

    .. versionadded:: 0.5
       Added the ``max_form_memory_size``, ``max_content_length``, and ``cls``
       parameters.
    """
    return FormDataParser(
        stream_factory=stream_factory,
        max_form_memory_size=max_form_memory_size,
        max_content_length=max_content_length,
        max_form_parts=max_form_parts,
        silent=silent,
        cls=cls,
    ).parse_from_environ(environ)


class FormDataParser:
    """This class implements parsing of form data for Werkzeug.  By itself
    it can parse multipart and url encoded form data.  It can be subclassed
    and extended but for most mimetypes it is a better idea to use the
    untouched stream and expose it as separate attributes on a request
    object.

    :param stream_factory: An optional callable that returns a new read and
                           writeable file descriptor.  This callable works
                           the same as :meth:`Response._get_file_stream`.
    :param max_form_memory_size: the maximum number of bytes to be accepted for
                           in-memory stored form data.  If the data
                           exceeds the value specified an
                           :exc:`~exceptions.RequestEntityTooLarge`
                           exception is raised.
    :param max_content_length: If this is provided and the transmitted data
                               is longer than this value an
                               :exc:`~exceptions.RequestEntityTooLarge`
                               exception is raised.
    :param cls: an optional dict class to use.  If this is not specified
                       or `None` the default :class:`MultiDict` is used.
    :param silent: If set to False parsing errors will not be caught.
    :param max_form_parts: The maximum number of multipart parts to be parsed. If this
        is exceeded, a :exc:`~exceptions.RequestEntityTooLarge` exception is raised.

    .. versionchanged:: 3.0
        The ``charset`` and ``errors`` parameters were removed.

    .. versionchanged:: 3.0
        The ``parse_functions`` attribute and ``get_parse_func`` methods were removed.

    .. versionchanged:: 2.2.3
        Added the ``max_form_parts`` parameter.

    .. versionadded:: 0.8
    """

    def __init__(
        self,
        stream_factory: TStreamFactory | None = None,
        max_form_memory_size: int | None = None,
        max_content_length: int | None = None,
        cls: type[MultiDict[str, t.Any]] | None = None,
        silent: bool = True,
        *,
        max_form_parts: int | None = None,
    ) -> None:
        if stream_factory is None:
            stream_factory = default_stream_factory

        self.stream_factory = stream_factory
        self.max_form_memory_size = max_form_memory_size
        self.max_content_length = max_content_length
        self.max_form_parts = max_form_parts

        if cls is None:
            cls = t.cast("type[MultiDict[str, t.Any]]", MultiDict)

        self.cls = cls
        self.silent = silent

    def parse_from_environ(self, environ: WSGIEnvironment) -> t_parse_result:
        """Parses the information from the environment as form data.

        :param environ: the WSGI environment to be used for parsing.
        :return: A tuple in the form ``(stream, form, files)``.
        """
        stream = get_input_stream(environ, max_content_length=self.max_content_length)
        content_length = get_content_length(environ)
        mimetype, options = parse_options_header(environ.get("CONTENT_TYPE"))
        return self.parse(
            stream,
            content_length=content_length,
            mimetype=mimetype,
            options=options,
        )

    def parse(
        self,
        stream: t.IO[bytes],
        mimetype: str,
        content_length: int | None,
        options: dict[str, str] | None = None,
    ) -> t_parse_result:
        """Parses the information from the given stream, mimetype,
        content length and mimetype parameters.

        :param stream: an input stream
        :param mimetype: the mimetype of the data
        :param content_length: the content length of the incoming data
        :param options: optional mimetype parameters (used for
                        the multipart boundary for instance)
        :return: A tuple in the form ``(stream, form, files)``.

        .. versionchanged:: 3.0
            The invalid ``application/x-url-encoded`` content type is not
            treated as ``application/x-www-form-urlencoded``.
        """
        if mimetype == "multipart/form-data":
            parse_func = self._parse_multipart
        elif mimetype == "application/x-www-form-urlencoded":
            parse_func = self._parse_urlencoded
        else:
            return stream, self.cls(), self.cls()

        if options is None:
            options = {}

        try:
            return parse_func(stream, mimetype, content_length, options)
        except ValueError:
            if not self.silent:
                raise

        return stream, self.cls(), self.cls()

    def _parse_multipart(
        self,
        stream: t.IO[bytes],
        mimetype: str,
        content_length: int | None,
        options: dict[str, str],
    ) -> t_parse_result:
        parser = MultiPartParser(
            stream_factory=self.stream_factory,
            max_form_memory_size=self.max_form_memory_size,
            max_form_parts=self.max_form_parts,
            cls=self.cls,
        )
        boundary = options.get("boundary", "").encode("ascii")

        if not boundary:
            raise ValueError("Missing boundary")

        form, files = parser.parse(stream, boundary, content_length)
        return stream, form, files

    def _parse_urlencoded(
        self,
        stream: t.IO[bytes],
        mimetype: str,
        content_length: int | None,
        options: dict[str, str],
    ) -> t_parse_result:
        if (
            self.max_form_memory_size is not None
            and content_length is not None
            and content_length > self.max_form_memory_size
        ):
            raise RequestEntityTooLarge()

        items = parse_qsl(
            stream.read().decode(),
            keep_blank_values=True,
            errors="werkzeug.url_quote",
        )
        return stream, self.cls(items), self.cls()


class MultiPartParser:
    def __init__(
        self,
        stream_factory: TStreamFactory | None = None,
        max_form_memory_size: int | None = None,
        cls: type[MultiDict[str, t.Any]] | None = None,
        buffer_size: int = 64 * 1024,
        max_form_parts: int | None = None,
    ) -> None:
        self.max_form_memory_size = max_form_memory_size
        self.max_form_parts = max_form_parts

        if stream_factory is None:
            stream_factory = default_stream_factory

        self.stream_factory = stream_factory

        if cls is None:
            cls = t.cast("type[MultiDict[str, t.Any]]", MultiDict)

        self.cls = cls
        self.buffer_size = buffer_size

    def fail(self, message: str) -> te.NoReturn:
        raise ValueError(message)

    def get_part_charset(self, headers: Headers) -> str:
        # Figure out input charset for current part
        content_type = headers.get("content-type")

        if content_type:
            parameters = parse_options_header(content_type)[1]
            ct_charset = parameters.get("charset", "").lower()

            # A safe list of encodings. Modern clients should only send ASCII or UTF-8.
            # This list will not be extended further.
            if ct_charset in {"ascii", "us-ascii", "utf-8", "iso-8859-1"}:
                return ct_charset

        return "utf-8"

    def start_file_streaming(
        self, event: File, total_content_length: int | None
    ) -> t.IO[bytes]:
        content_type = event.headers.get("content-type")

        try:
            content_length = _plain_int(event.headers["content-length"])
        except (KeyError, ValueError):
            content_length = 0

        container = self.stream_factory(
            total_content_length=total_content_length,
            filename=event.filename,
            content_type=content_type,
            content_length=content_length,
        )
        return container

    def parse(
        self, stream: t.IO[bytes], boundary: bytes, content_length: int | None
    ) -> tuple[MultiDict[str, str], MultiDict[str, FileStorage]]:
        current_part: Field | File
        field_size: int | None = None
        container: t.IO[bytes] | list[bytes]
        _write: t.Callable[[bytes], t.Any]

        parser = MultipartDecoder(
            boundary,
            max_form_memory_size=self.max_form_memory_size,
            max_parts=self.max_form_parts,
        )

        fields = []
        files = []

        for data in _chunk_iter(stream.read, self.buffer_size):
            parser.receive_data(data)
            event = parser.next_event()
            while not isinstance(event, (Epilogue, NeedData)):
                if isinstance(event, Field):
                    current_part = event
                    field_size = 0
                    container = []
                    _write = container.append
                elif isinstance(event, File):
                    current_part = event
                    field_size = None
                    container = self.start_file_streaming(event, content_length)
                    _write = container.write
                elif isinstance(event, Data):
                    if self.max_form_memory_size is not None and field_size is not None:
                        # Ensure that accumulated data events do not exceed limit.
                        # Also checked within single event in MultipartDecoder.
                        field_size += len(event.data)

                        if field_size > self.max_form_memory_size:
                            raise RequestEntityTooLarge()

                    _write(event.data)
                    if not event.more_data:
                        if isinstance(current_part, Field):
                            value = b"".join(container).decode(
                                self.get_part_charset(current_part.headers), "replace"
                            )
                            fields.append((current_part.name, value))
                        else:
                            container = t.cast(t.IO[bytes], container)
                            container.seek(0)
                            files.append(
                                (
                                    current_part.name,
                                    FileStorage(
                                        container,
                                        current_part.filename,
                                        current_part.name,
                                        headers=current_part.headers,
                                    ),
                                )
                            )

                event = parser.next_event()

        return self.cls(fields), self.cls(files)


def _chunk_iter(read: t.Callable[[int], bytes], size: int) -> t.Iterator[bytes | None]:
    """Read data in chunks for multipart/form-data parsing. Stop if no data is read.
    Yield ``None`` at the end to signal end of parsing.
    """
    while True:
        data = read(size)

        if not data:
            break

        yield data

    yield None
