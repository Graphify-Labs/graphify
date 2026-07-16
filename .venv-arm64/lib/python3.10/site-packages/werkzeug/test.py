from __future__ import annotations

import dataclasses
import mimetypes
import sys
import typing as t
from collections import defaultdict
from datetime import datetime
from io import BytesIO
from itertools import chain
from random import random
from tempfile import TemporaryFile
from time import time
from urllib.parse import unquote
from urllib.parse import urlsplit
from urllib.parse import urlunsplit

from ._internal import _get_environ
from ._internal import _wsgi_decoding_dance
from ._internal import _wsgi_encoding_dance
from .datastructures import Authorization
from .datastructures import CallbackDict
from .datastructures import CombinedMultiDict
from .datastructures import EnvironHeaders
from .datastructures import FileMultiDict
from .datastructures import Headers
from .datastructures import MultiDict
from .http import dump_cookie
from .http import dump_options_header
from .http import parse_cookie
from .http import parse_date
from .http import parse_options_header
from .sansio.multipart import Data
from .sansio.multipart import Epilogue
from .sansio.multipart import Field
from .sansio.multipart import File
from .sansio.multipart import MultipartEncoder
from .sansio.multipart import Preamble
from .urls import _urlencode
from .urls import iri_to_uri
from .utils import cached_property
from .utils import get_content_type
from .wrappers.request import Request
from .wrappers.response import Response
from .wsgi import ClosingIterator
from .wsgi import get_current_url

if t.TYPE_CHECKING:
    import typing_extensions as te
    from _typeshed.wsgi import WSGIApplication
    from _typeshed.wsgi import WSGIEnvironment


def stream_encode_multipart(
    data: t.Mapping[str, t.Any],
    use_tempfile: bool = True,
    threshold: int = 1024 * 500,
    boundary: str | None = None,
) -> tuple[t.IO[bytes], int, str]:
    """Encode a dict of values (either strings or file descriptors or
    :class:`FileStorage` objects.) into a multipart encoded string stored
    in a file descriptor.

    .. versionchanged:: 3.0
        The ``charset`` parameter was removed.
    """
    if boundary is None:
        boundary = f"---------------WerkzeugFormPart_{time()}{random()}"

    stream: t.IO[bytes] = BytesIO()
    total_length = 0
    on_disk = False
    write_binary: t.Callable[[bytes], int]

    if use_tempfile:

        def write_binary(s: bytes) -> int:
            nonlocal stream, total_length, on_disk

            if on_disk:
                return stream.write(s)
            else:
                length = len(s)

                if length + total_length <= threshold:
                    stream.write(s)
                else:
                    new_stream = t.cast(t.IO[bytes], TemporaryFile("wb+"))
                    new_stream.write(stream.getvalue())  # type: ignore
                    new_stream.write(s)
                    stream = new_stream
                    on_disk = True

                total_length += length
                return length

    else:
        write_binary = stream.write

    encoder = MultipartEncoder(boundary.encode())
    write_binary(encoder.send_event(Preamble(data=b"")))
    for key, value in _iter_data(data):
        reader = getattr(value, "read", None)
        if reader is not None:
            filename = getattr(value, "filename", getattr(value, "name", None))
            content_type = getattr(value, "content_type", None)
            if content_type is None:
                content_type = (
                    filename
                    and mimetypes.guess_type(filename)[0]
                    or "application/octet-stream"
                )
            headers = value.headers
            headers.update([("Content-Type", content_type)])
            if filename is None:
                write_binary(encoder.send_event(Field(name=key, headers=headers)))
            else:
                write_binary(
                    encoder.send_event(
                        File(name=key, filename=filename, headers=headers)
                    )
                )
            while True:
                chunk = reader(16384)

                if not chunk:
                    write_binary(encoder.send_event(Data(data=chunk, more_data=False)))
                    break

                write_binary(encoder.send_event(Data(data=chunk, more_data=True)))
        else:
            if not isinstance(value, str):
                value = str(value)
            write_binary(encoder.send_event(Field(name=key, headers=Headers())))
            write_binary(encoder.send_event(Data(data=value.encode(), more_data=False)))

    write_binary(encoder.send_event(Epilogue(data=b"")))

    length = stream.tell()
    stream.seek(0)
    return stream, length, boundary


def encode_multipart(
    values: t.Mapping[str, t.Any], boundary: str | None = None
) -> tuple[str, bytes]:
    """Like `stream_encode_multipart` but returns a tuple in the form
    (``boundary``, ``data``) where data is bytes.

    .. versionchanged:: 3.0
        The ``charset`` parameter was removed.
    """
    stream, length, boundary = stream_encode_multipart(
        values, use_tempfile=False, boundary=boundary
    )
    return boundary, stream.read()


def _iter_data(data: t.Mapping[str, t.Any]) -> t.Iterator[tuple[str, t.Any]]:
    """Iterate over a mapping that might have a list of values, yielding
    all key, value pairs. Almost like iter_multi_items but only allows
    lists, not tuples, of values so tuples can be used for files.
    """
    if isinstance(data, MultiDict):
        yield from data.items(multi=True)
    else:
        for key, value in data.items():
            if isinstance(value, list):
                for v in value:
                    yield key, v
            else:
                yield key, value


_TAnyMultiDict = t.TypeVar("_TAnyMultiDict", bound="MultiDict[t.Any, t.Any]")


class EnvironBuilder:
    """This class can be used to conveniently create a WSGI environment
    for testing purposes.  It can be used to quickly create WSGI environments
    or request objects from arbitrary data.

    The signature of this class is also used in some other places as of
    Werkzeug 0.5 (:func:`create_environ`, :meth:`Response.from_values`,
    :meth:`Client.open`).  Because of this most of the functionality is
    available through the constructor alone.

    Files and regular form data can be manipulated independently of each
    other with the :attr:`form` and :attr:`files` attributes, but are
    passed with the same argument to the constructor: `data`.

    `data` can be any of these values:

    -   a `str` or `bytes` object: The object is converted into an
        :attr:`input_stream`, the :attr:`content_length` is set and you have to
        provide a :attr:`content_type`.
    -   a `dict` or :class:`MultiDict`: The keys have to be strings. The values
        have to be either any of the following objects, or a list of any of the
        following objects:

        -   a :class:`file`-like object:  These are converted into
            :class:`FileStorage` objects automatically.
        -   a `tuple`:  The :meth:`~FileMultiDict.add_file` method is called
            with the key and the unpacked `tuple` items as positional
            arguments.
        -   a `str`:  The string is set as form data for the associated key.
    -   a file-like object: The object content is loaded in memory and then
        handled like a regular `str` or a `bytes`.

    :param path: the path of the request.  In the WSGI environment this will
                 end up as `PATH_INFO`.  If the `query_string` is not defined
                 and there is a question mark in the `path` everything after
                 it is used as query string.
    :param base_url: the base URL is a URL that is used to extract the WSGI
                     URL scheme, host (server name + server port) and the
                     script root (`SCRIPT_NAME`).
    :param query_string: an optional string or dict with URL parameters.
    :param method: the HTTP method to use, defaults to `GET`.
    :param input_stream: an optional input stream.  Do not specify this and
                         `data`.  As soon as an input stream is set you can't
                         modify :attr:`args` and :attr:`files` unless you
                         set the :attr:`input_stream` to `None` again.
    :param content_type: The content type for the request.  As of 0.5 you
                         don't have to provide this when specifying files
                         and form data via `data`.
    :param content_length: The content length for the request.  You don't
                           have to specify this when providing data via
                           `data`.
    :param errors_stream: an optional error stream that is used for
                          `wsgi.errors`.  Defaults to :data:`stderr`.
    :param multithread: controls `wsgi.multithread`.  Defaults to `False`.
    :param multiprocess: controls `wsgi.multiprocess`.  Defaults to `False`.
    :param run_once: controls `wsgi.run_once`.  Defaults to `False`.
    :param headers: an optional list or :class:`Headers` object of headers.
    :param data: a string or dict of form data or a file-object.
                 See explanation above.
    :param json: An object to be serialized and assigned to ``data``.
        Defaults the content type to ``"application/json"``.
        Serialized with the function assigned to :attr:`json_dumps`.
    :param environ_base: an optional dict of environment defaults.
    :param environ_overrides: an optional dict of environment overrides.
    :param auth: An authorization object to use for the
        ``Authorization`` header value. A ``(username, password)`` tuple
        is a shortcut for ``Basic`` authorization.

    .. versionchanged:: 3.0
        The ``charset`` parameter was removed.

    .. versionchanged:: 2.1
        ``CONTENT_TYPE`` and ``CONTENT_LENGTH`` are not duplicated as
        header keys in the environ.

    .. versionchanged:: 2.0
        ``REQUEST_URI`` and ``RAW_URI`` is the full raw URI including
        the query string, not only the path.

    .. versionchanged:: 2.0
        The default :attr:`request_class` is ``Request`` instead of
        ``BaseRequest``.

    .. versionadded:: 2.0
       Added the ``auth`` parameter.

    .. versionadded:: 0.15
        The ``json`` param and :meth:`json_dumps` method.

    .. versionadded:: 0.15
        The environ has keys ``REQUEST_URI`` and ``RAW_URI`` containing
        the path before percent-decoding. This is not part of the WSGI
        PEP, but many WSGI servers include it.

    .. versionchanged:: 0.6
       ``path`` and ``base_url`` can now be unicode strings that are
       encoded with :func:`iri_to_uri`.
    """

    #: the server protocol to use.  defaults to HTTP/1.1
    server_protocol = "HTTP/1.1"

    #: the wsgi version to use.  defaults to (1, 0)
    wsgi_version = (1, 0)

    #: The default request class used by :meth:`get_request`.
    request_class = Request

    import json

    #: The serialization function used when ``json`` is passed.
    json_dumps = staticmethod(json.dumps)
    del json

    _args: MultiDict[str, str] | None
    _query_string: str | None
    _input_stream: t.IO[bytes] | None
    _form: MultiDict[str, str] | None
    _files: FileMultiDict | None

    def __init__(
        self,
        path: str = "/",
        base_url: str | None = None,
        query_string: t.Mapping[str, str] | str | None = None,
        method: str = "GET",
        input_stream: t.IO[bytes] | None = None,
        content_type: str | None = None,
        content_length: int | None = None,
        errors_stream: t.IO[str] | None = None,
        multithread: bool = False,
        multiprocess: bool = False,
        run_once: bool = False,
        headers: Headers | t.Iterable[tuple[str, str]] | None = None,
        data: None | (t.IO[bytes] | str | bytes | t.Mapping[str, t.Any]) = None,
        environ_base: t.Mapping[str, t.Any] | None = None,
        environ_overrides: t.Mapping[str, t.Any] | None = None,
        mimetype: str | None = None,
        json: t.Mapping[str, t.Any] | None = None,
        auth: Authorization | tuple[str, str] | None = None,
    ) -> None:
        if query_string is not None and "?" in path:
            raise ValueError("Query string is defined in the path and as an argument")
        request_uri = urlsplit(path)
        if query_string is None and "?" in path:
            query_string = request_uri.query

        self.path = iri_to_uri(request_uri.path)
        self.request_uri = path
        if base_url is not None:
            base_url = iri_to_uri(base_url)
        self.base_url = base_url
        if isinstance(query_string, str):
            self.query_string = query_string
        else:
            if query_string is None:
                query_string = MultiDict()
            elif not isinstance(query_string, MultiDict):
                query_string = MultiDict(query_string)
            self.args = query_string
        self.method = method
        if headers is None:
            headers = Headers()
        elif not isinstance(headers, Headers):
            headers = Headers(headers)
        self.headers = headers
        if content_type is not None:
            self.content_type = content_type
        if errors_stream is None:
            errors_stream = sys.stderr
        self.errors_stream = errors_stream
        self.multithread = multithread
        self.multiprocess = multiprocess
        self.run_once = run_once
        self.environ_base = environ_base
        self.environ_overrides = environ_overrides
        self.input_stream = input_stream
        self.content_length = content_length
        self.closed = False

        if auth is not None:
            if isinstance(auth, tuple):
                auth = Authorization(
                    "basic", {"username": auth[0], "password": auth[1]}
                )

            self.headers.set("Authorization", auth.to_header())

        if json is not None:
            if data is not None:
                raise TypeError("can't provide both json and data")

            data = self.json_dumps(json)

            if self.content_type is None:
                self.content_type = "application/json"

        if data:
            if input_stream is not None:
                raise TypeError("can't provide input stream and data")
            if hasattr(data, "read"):
                data = data.read()
            if isinstance(data, str):
                data = data.encode()
            if isinstance(data, bytes):
                self.input_stream = BytesIO(data)
                if self.content_length is None:
                    self.content_length = len(data)
            else:
                for key, value in _iter_data(data):
                    if isinstance(value, (tuple, dict)) or hasattr(value, "read"):
                        self._add_file_from_data(key, value)
                    else:
                        self.form.setlistdefault(key).append(value)

        if mimetype is not None:
            self.mimetype = mimetype

    @classmethod
    def from_environ(cls, environ: WSGIEnvironment, **kwargs: t.Any) -> EnvironBuilder:
        """Turn an environ dict back into a builder. Any extra kwargs
        override the args extracted from the environ.

        .. versionchanged:: 2.0
            Path and query values are passed through the WSGI decoding
            dance to avoid double encoding.

        .. versionadded:: 0.15
        """
        headers = Headers(EnvironHeaders(environ))
        out = {
            "path": _wsgi_decoding_dance(environ["PATH_INFO"]),
            "base_url": cls._make_base_url(
                environ["wsgi.url_scheme"],
                headers.pop("Host"),
                _wsgi_decoding_dance(environ["SCRIPT_NAME"]),
            ),
            "query_string": _wsgi_decoding_dance(environ["QUERY_STRING"]),
            "method": environ["REQUEST_METHOD"],
            "input_stream": environ["wsgi.input"],
            "content_type": headers.pop("Content-Type", None),
            "content_length": headers.pop("Content-Length", None),
            "errors_stream": environ["wsgi.errors"],
            "multithread": environ["wsgi.multithread"],
            "multiprocess": environ["wsgi.multiprocess"],
            "run_once": environ["wsgi.run_once"],
            "headers": headers,
        }
        out.update(kwargs)
        return cls(**out)

    def _add_file_from_data(
        self,
        key: str,
        value: (t.IO[bytes] | tuple[t.IO[bytes], str] | tuple[t.IO[bytes], str, str]),
    ) -> None:
        """Called in the EnvironBuilder to add files from the data dict."""
        if isinstance(value, tuple):
            self.files.add_file(key, *value)
        else:
            self.files.add_file(key, value)

    @staticmethod
    def _make_base_url(scheme: str, host: str, script_root: str) -> str:
        return urlunsplit((scheme, host, script_root, "", "")).rstrip("/") + "/"

    @property
    def base_url(self) -> str:
        """The base URL is used to extract the URL scheme, host name,
        port, and root path.
        """
        return self._make_base_url(self.url_scheme, self.host, self.script_root)

    @base_url.setter
    def base_url(self, value: str | None) -> None:
        if value is None:
            scheme = "http"
            netloc = "localhost"
            script_root = ""
        else:
            scheme, netloc, script_root, qs, anchor = urlsplit(value)
            if qs or anchor:
                raise ValueError("base url must not contain a query string or fragment")
        self.script_root = script_root.rstrip("/")
        self.host = netloc
        self.url_scheme = scheme

    @property
    def content_type(self) -> str | None:
        """The content type for the request.  Reflected from and to
        the :attr:`headers`.  Do not set if you set :attr:`files` or
        :attr:`form` for auto detection.
        """
        ct = self.headers.get("Content-Type")
        if ct is None and not self._input_stream:
            if self._files:
                return "multipart/form-data"
            if self._form:
                return "application/x-www-form-urlencoded"
            return None
        return ct

    @content_type.setter
    def content_type(self, value: str | None) -> None:
        if value is None:
            self.headers.pop("Content-Type", None)
        else:
            self.headers["Content-Type"] = value

    @property
    def mimetype(self) -> str | None:
        """The mimetype (content type without charset etc.)

        .. versionadded:: 0.14
        """
        ct = self.content_type
        return ct.split(";")[0].strip() if ct else None

    @mimetype.setter
    def mimetype(self, value: str) -> None:
        self.content_type = get_content_type(value, "utf-8")

    @property
    def mimetype_params(self) -> t.Mapping[str, str]:
        """The mimetype parameters as dict.  For example if the
        content type is ``text/html; charset=utf-8`` the params would be
        ``{'charset': 'utf-8'}``.

        .. versionadded:: 0.14
        """

        def on_update(d: CallbackDict[str, str]) -> None:
            self.headers["Content-Type"] = dump_options_header(self.mimetype, d)

        d = parse_options_header(self.headers.get("content-type", ""))[1]
        return CallbackDict(d, on_update)

    @property
    def content_length(self) -> int | None:
        """The content length as integer.  Reflected from and to the
        :attr:`headers`.  Do not set if you set :attr:`files` or
        :attr:`form` for auto detection.
        """
        return self.headers.get("Content-Length", type=int)

    @content_length.setter
    def content_length(self, value: int | None) -> None:
        if value is None:
            self.headers.pop("Content-Length", None)
        else:
            self.headers["Content-Length"] = str(value)

    def _get_form(self, name: str, storage: type[_TAnyMultiDict]) -> _TAnyMultiDict:
        """Common behavior for getting the :attr:`form` and
        :attr:`files` properties.

        :param name: Name of the internal cached attribute.
        :param storage: Storage class used for the data.
        """
        if self.input_stream is not None:
            raise AttributeError("an input stream is defined")

        rv = getattr(self, name)

        if rv is None:
            rv = storage()
            setattr(self, name, rv)

        return rv  # type: ignore

    def _set_form(self, name: str, value: MultiDict[str, t.Any]) -> None:
        """Common behavior for setting the :attr:`form` and
        :attr:`files` properties.

        :param name: Name of the internal cached attribute.
        :param value: Value to assign to the attribute.
        """
        self._input_stream = None
        setattr(self, name, value)

    @property
    def form(self) -> MultiDict[str, str]:
        """A :class:`MultiDict` of form values."""
        return self._get_form("_form", MultiDict)

    @form.setter
    def form(self, value: MultiDict[str, str]) -> None:
        self._set_form("_form", value)

    @property
    def files(self) -> FileMultiDict:
        """A :class:`FileMultiDict` of uploaded files. Use
        :meth:`~FileMultiDict.add_file` to add new files.
        """
        return self._get_form("_files", FileMultiDict)

    @files.setter
    def files(self, value: FileMultiDict) -> None:
        self._set_form("_files", value)

    @property
    def input_stream(self) -> t.IO[bytes] | None:
        """An optional input stream. This is mutually exclusive with
        setting :attr:`form` and :attr:`files`, setting it will clear
        those. Do not provide this if the method is not ``POST`` or
        another method that has a body.
        """
        return self._input_stream

    @input_stream.setter
    def input_stream(self, value: t.IO[bytes] | None) -> None:
        self._input_stream = value
        self._form = None
        self._files = None

    @property
    def query_string(self) -> str:
        """The query string.  If you set this to a string
        :attr:`args` will no longer be available.
        """
        if self._query_string is None:
            if self._args is not None:
                return _urlencode(self._args)
            return ""
        return self._query_string

    @query_string.setter
    def query_string(self, value: str | None) -> None:
        self._query_string = value
        self._args = None

    @property
    def args(self) -> MultiDict[str, str]:
        """The URL arguments as :class:`MultiDict`."""
        if self._query_string is not None:
            raise AttributeError("a query string is defined")
        if self._args is None:
            self._args = MultiDict()
        return self._args

    @args.setter
    def args(self, value: MultiDict[str, str] | None) -> None:
        self._query_string = None
        self._args = value

    @property
    def server_name(self) -> str:
        """The server name (read-only, use :attr:`host` to set)"""
        return self.host.split(":", 1)[0]

    @property
    def server_port(self) -> int:
        """The server port as integer (read-only, use :attr:`host` to set)"""
        pieces = self.host.split(":", 1)

        if len(pieces) == 2:
            try:
                return int(pieces[1])
            except ValueError:
                pass

        if self.url_scheme == "https":
            return 443
        return 80

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def close(self) -> None:
        """Closes all files.  If you put real :class:`file` objects into the
        :attr:`files` dict you can call this method to automatically close
        them all in one go.
        """
        if self.closed:
            return
        try:
            files = self.files.values()
        except AttributeError:
            files = ()
        for f in files:
            try:
                f.close()
            except Exception:
                pass
        self.closed = True

    def get_environ(self) -> WSGIEnvironment:
        """Return the built environ.

        .. versionchanged:: 0.15
            The content type and length headers are set based on
            input stream detection. Previously this only set the WSGI
            keys.
        """
        input_stream = self.input_stream
        content_length = self.content_length

        mimetype = self.mimetype
        content_type = self.content_type

        if input_stream is not None:
            start_pos = input_stream.tell()
            input_stream.seek(0, 2)
            end_pos = input_stream.tell()
            input_stream.seek(start_pos)
            content_length = end_pos - start_pos
        elif mimetype == "multipart/form-data":
            input_stream, content_length, boundary = stream_encode_multipart(
                CombinedMultiDict([self.form, self.files])
            )
            content_type = f'{mimetype}; boundary="{boundary}"'
        elif mimetype == "application/x-www-form-urlencoded":
            form_encoded = _urlencode(self.form).encode("ascii")
            content_length = len(form_encoded)
            input_stream = BytesIO(form_encoded)
        else:
            input_stream = BytesIO()

        result: WSGIEnvironment = {}
        if self.environ_base:
            result.update(self.environ_base)

        def _path_encode(x: str) -> str:
            return _wsgi_encoding_dance(unquote(x))

        raw_uri = _wsgi_encoding_dance(self.request_uri)
        result.update(
            {
                "REQUEST_METHOD": self.method,
                "SCRIPT_NAME": _path_encode(self.script_root),
                "PATH_INFO": _path_encode(self.path),
                "QUERY_STRING": _wsgi_encoding_dance(self.query_string),
                # Non-standard, added by mod_wsgi, uWSGI
                "REQUEST_URI": raw_uri,
                # Non-standard, added by gunicorn
                "RAW_URI": raw_uri,
                "SERVER_NAME": self.server_name,
                "SERVER_PORT": str(self.server_port),
                "HTTP_HOST": self.host,
                "SERVER_PROTOCOL": self.server_protocol,
                "wsgi.version": self.wsgi_version,
                "wsgi.url_scheme": self.url_scheme,
                "wsgi.input": input_stream,
                "wsgi.errors": self.errors_stream,
                "wsgi.multithread": self.multithread,
                "wsgi.multiprocess": self.multiprocess,
                "wsgi.run_once": self.run_once,
            }
        )

        headers = self.headers.copy()
        # Don't send these as headers, they're part of the environ.
        headers.remove("Content-Type")
        headers.remove("Content-Length")

        if content_type is not None:
            result["CONTENT_TYPE"] = content_type

        if content_length is not None:
            result["CONTENT_LENGTH"] = str(content_length)

        combined_headers = defaultdict(list)

        for key, value in headers.to_wsgi_list():
            combined_headers[f"HTTP_{key.upper().replace('-', '_')}"].append(value)

        for key, values in combined_headers.items():
            result[key] = ", ".join(values)

        if self.environ_overrides:
            result.update(self.environ_overrides)

        return result

    def get_request(self, cls: type[Request] | None = None) -> Request:
        """Returns a request with the data.  If the request class is not
        specified :attr:`request_class` is used.

        :param cls: The request wrapper to use.
        """
        if cls is None:
            cls = self.request_class

        return cls(self.get_environ())


class ClientRedirectError(Exception):
    """If a redirect loop is detected when using follow_redirects=True with
    the :cls:`Client`, then this exception is raised.
    """


class Client:
    """Simulate sending requests to a WSGI application without running a WSGI or HTTP
    server.

    :param application: The WSGI application to make requests to.
    :param response_wrapper: A :class:`.Response` class to wrap response data with.
        Defaults to :class:`.TestResponse`. If it's not a subclass of ``TestResponse``,
        one will be created.
    :param use_cookies: Persist cookies from ``Set-Cookie`` response headers to the
        ``Cookie`` header in subsequent requests. Domain and path matching is supported,
        but other cookie parameters are ignored.
    :param allow_subdomain_redirects: Allow requests to follow redirects to subdomains.
        Enable this if the application handles subdomains and redirects between them.

    .. versionchanged:: 2.3
        Simplify cookie implementation, support domain and path matching.

    .. versionchanged:: 2.1
        All data is available as properties on the returned response object. The
        response cannot be returned as a tuple.

    .. versionchanged:: 2.0
        ``response_wrapper`` is always a subclass of :class:``TestResponse``.

    .. versionchanged:: 0.5
        Added the ``use_cookies`` parameter.
    """

    def __init__(
        self,
        application: WSGIApplication,
        response_wrapper: type[Response] | None = None,
        use_cookies: bool = True,
        allow_subdomain_redirects: bool = False,
    ) -> None:
        self.application = application

        if response_wrapper in {None, Response}:
            response_wrapper = TestResponse
        elif response_wrapper is not None and not issubclass(
            response_wrapper, TestResponse
        ):
            response_wrapper = type(
                "WrapperTestResponse",
                (TestResponse, response_wrapper),
                {},
            )

        self.response_wrapper = t.cast(type["TestResponse"], response_wrapper)

        if use_cookies:
            self._cookies: dict[tuple[str, str, str], Cookie] | None = {}
        else:
            self._cookies = None

        self.allow_subdomain_redirects = allow_subdomain_redirects

    def get_cookie(
        self, key: str, domain: str = "localhost", path: str = "/"
    ) -> Cookie | None:
        """Return a :class:`.Cookie` if it exists. Cookies are uniquely identified by
        ``(domain, path, key)``.

        :param key: The decoded form of the key for the cookie.
        :param domain: The domain the cookie was set for.
        :param path: The path the cookie was set for.

        .. versionadded:: 2.3
        """
        if self._cookies is None:
            raise TypeError(
                "Cookies are disabled. Create a client with 'use_cookies=True'."
            )

        return self._cookies.get((domain, path, key))

    def set_cookie(
        self,
        key: str,
        value: str = "",
        *,
        domain: str = "localhost",
        origin_only: bool = True,
        path: str = "/",
        **kwargs: t.Any,
    ) -> None:
        """Set a cookie to be sent in subsequent requests.

        This is a convenience to skip making a test request to a route that would set
        the cookie. To test the cookie, make a test request to a route that uses the
        cookie value.

        The client uses ``domain``, ``origin_only``, and ``path`` to determine which
        cookies to send with a request. It does not use other cookie parameters that
        browsers use, since they're not applicable in tests.

        :param key: The key part of the cookie.
        :param value: The value part of the cookie.
        :param domain: Send this cookie with requests that match this domain. If
            ``origin_only`` is true, it must be an exact match, otherwise it may be a
            suffix match.
        :param origin_only: Whether the domain must be an exact match to the request.
        :param path: Send this cookie with requests that match this path either exactly
            or as a prefix.
        :param kwargs: Passed to :func:`.dump_cookie`.

        .. versionchanged:: 3.0
            The parameter ``server_name`` is removed. The first parameter is
            ``key``. Use the ``domain`` and ``origin_only`` parameters instead.

        .. versionchanged:: 2.3
            The ``origin_only`` parameter was added.

        .. versionchanged:: 2.3
            The ``domain`` parameter defaults to ``localhost``.
        """
        if self._cookies is None:
            raise TypeError(
                "Cookies are disabled. Create a client with 'use_cookies=True'."
            )

        cookie = Cookie._from_response_header(
            domain, "/", dump_cookie(key, value, domain=domain, path=path, **kwargs)
        )
        cookie.origin_only = origin_only

        if cookie._should_delete:
            self._cookies.pop(cookie._storage_key, None)
        else:
            self._cookies[cookie._storage_key] = cookie

    def delete_cookie(
        self,
        key: str,
        *,
        domain: str = "localhost",
        path: str = "/",
    ) -> None:
        """Delete a cookie if it exists. Cookies are uniquely identified by
        ``(domain, path, key)``.

        :param key: The decoded form of the key for the cookie.
        :param domain: The domain the cookie was set for.
        :param path: The path the cookie was set for.

        .. versionchanged:: 3.0
            The ``server_name`` parameter is removed. The first parameter is
            ``key``. Use the ``domain`` parameter instead.

        .. versionchanged:: 3.0
            The ``secure``, ``httponly`` and ``samesite`` parameters are removed.

        .. versionchanged:: 2.3
            The ``domain`` parameter defaults to ``localhost``.
        """
        if self._cookies is None:
            raise TypeError(
                "Cookies are disabled. Create a client with 'use_cookies=True'."
            )

        self._cookies.pop((domain, path, key), None)

    def _add_cookies_to_wsgi(self, environ: WSGIEnvironment) -> None:
        """If cookies are enabled, set the ``Cookie`` header in the environ to the
        cookies that are applicable to the request host and path.

        :meta private:

        .. versionadded:: 2.3
        """
        if self._cookies is None:
            return

        url = urlsplit(get_current_url(environ))
        server_name = url.hostname or "localhost"
        value = "; ".join(
            c._to_request_header()
            for c in self._cookies.values()
            if c._matches_request(server_name, url.path)
        )

        if value:
            environ["HTTP_COOKIE"] = value
        else:
            environ.pop("HTTP_COOKIE", None)

    def _update_cookies_from_response(
        self, server_name: str, path: str, headers: list[str]
    ) -> None:
        """If cookies are enabled, update the stored cookies from any ``Set-Cookie``
        headers in the response.

        :meta private:

        .. versionadded:: 2.3
        """
        if self._cookies is None:
            return

        for header in headers:
            cookie = Cookie._from_response_header(server_name, path, header)

            if cookie._should_delete:
                self._cookies.pop(cookie._storage_key, None)
            else:
                self._cookies[cookie._storage_key] = cookie

    def run_wsgi_app(
        self, environ: WSGIEnvironment, buffered: bool = False
    ) -> tuple[t.Iterable[bytes], str, Headers]:
        """Runs the wrapped WSGI app with the given environment.

        :meta private:
        """
        self._add_cookies_to_wsgi(environ)
        rv = run_wsgi_app(self.application, environ, buffered=buffered)
        url = urlsplit(get_current_url(environ))
        self._update_cookies_from_response(
            url.hostname or "localhost", url.path, rv[2].getlist("Set-Cookie")
        )
        return rv

    def resolve_redirect(
        self, response: TestResponse, buffered: bool = False
    ) -> TestResponse:
        """Perform a new request to the location given by the redirect
        response to the previous request.

        :meta private:
        """
        scheme, netloc, path, qs, anchor = urlsplit(response.location)
        builder = EnvironBuilder.from_environ(
            response.request.environ, path=path, query_string=qs
        )

        to_name_parts = netloc.split(":", 1)[0].split(".")
        from_name_parts = builder.server_name.split(".")

        if to_name_parts != [""]:
            # The new location has a host, use it for the base URL.
            builder.url_scheme = scheme
            builder.host = netloc
        else:
            # A local redirect with autocorrect_location_header=False
            # doesn't have a host, so use the request's host.
            to_name_parts = from_name_parts

        # Explain why a redirect to a different server name won't be followed.
        if to_name_parts != from_name_parts:
            if to_name_parts[-len(from_name_parts) :] == from_name_parts:
                if not self.allow_subdomain_redirects:
                    raise RuntimeError("Following subdomain redirects is not enabled.")
            else:
                raise RuntimeError("Following external redirects is not supported.")

        path_parts = path.split("/")
        root_parts = builder.script_root.split("/")

        if path_parts[: len(root_parts)] == root_parts:
            # Strip the script root from the path.
            builder.path = path[len(builder.script_root) :]
        else:
            # The new location is not under the script root, so use the
            # whole path and clear the previous root.
            builder.path = path
            builder.script_root = ""

        # Only 307 and 308 preserve all of the original request.
        if response.status_code not in {307, 308}:
            # HEAD is preserved, everything else becomes GET.
            if builder.method != "HEAD":
                builder.method = "GET"

            # Clear the body and the headers that describe it.

            if builder.input_stream is not None:
                builder.input_stream.close()
                builder.input_stream = None

            builder.content_type = None
            builder.content_length = None
            builder.headers.pop("Transfer-Encoding", None)

        return self.open(builder, buffered=buffered)

    def open(
        self,
        *args: t.Any,
        buffered: bool = False,
        follow_redirects: bool = False,
        **kwargs: t.Any,
    ) -> TestResponse:
        """Generate an environ dict from the given arguments, make a
        request to the application using it, and return the response.

        :param args: Passed to :class:`EnvironBuilder` to create the
            environ for the request. If a single arg is passed, it can
            be an existing :class:`EnvironBuilder` or an environ dict.
        :param buffered: Convert the iterator returned by the app into
            a list. If the iterator has a ``close()`` method, it is
            called automatically.
        :param follow_redirects: Make additional requests to follow HTTP
            redirects until a non-redirect status is returned.
            :attr:`TestResponse.history` lists the intermediate
            responses.

        .. versionchanged:: 2.1
            Removed the ``as_tuple`` parameter.

        .. versionchanged:: 2.0
            The request input stream is closed when calling
            ``response.close()``. Input streams for redirects are
            automatically closed.

        .. versionchanged:: 0.5
            If a dict is provided as file in the dict for the ``data``
            parameter the content type has to be called ``content_type``
            instead of ``mimetype``. This change was made for
            consistency with :class:`werkzeug.FileWrapper`.

        .. versionchanged:: 0.5
            Added the ``follow_redirects`` parameter.
        """
        request: Request | None = None

        if not kwargs and len(args) == 1:
            arg = args[0]

            if isinstance(arg, EnvironBuilder):
                request = arg.get_request()
            elif isinstance(arg, dict):
                request = EnvironBuilder.from_environ(arg).get_request()
            elif isinstance(arg, Request):
                request = arg

        if request is None:
            builder = EnvironBuilder(*args, **kwargs)

            try:
                request = builder.get_request()
            finally:
                builder.close()

        response_parts = self.run_wsgi_app(request.environ, buffered=buffered)
        response = self.response_wrapper(*response_parts, request=request)

        redirects = set()
        history: list[TestResponse] = []

        if not follow_redirects:
            return response

        while response.status_code in {
            301,
            302,
            303,
            305,
            307,
            308,
        }:
            # Exhaust intermediate response bodies to ensure middleware
            # that returns an iterator runs any cleanup code.
            if not buffered:
                response.make_sequence()
                response.close()

            new_redirect_entry = (response.location, response.status_code)

            if new_redirect_entry in redirects:
                raise ClientRedirectError(
                    f"Loop detected: A {response.status_code} redirect"
                    f" to {response.location} was already made."
                )

            redirects.add(new_redirect_entry)
            response.history = tuple(history)
            history.append(response)
            response = self.resolve_redirect(response, buffered=buffered)
        else:
            # This is the final request after redirects.
            response.history = tuple(history)
            # Close the input stream when closing the response, in case
            # the input is an open temporary file.
            response.call_on_close(request.input_stream.close)
            return response

    def get(self, *args: t.Any, **kw: t.Any) -> TestResponse:
        """Call :meth:`open` with ``method`` set to ``GET``."""
        kw["method"] = "GET"
        return self.open(*args, **kw)

    def post(self, *args: t.Any, **kw: t.Any) -> TestResponse:
        """Call :meth:`open` with ``method`` set to ``POST``."""
        kw["method"] = "POST"
        return self.open(*args, **kw)

    def put(self, *args: t.Any, **kw: t.Any) -> TestResponse:
        """Call :meth:`open` with ``method`` set to ``PUT``."""
        kw["method"] = "PUT"
        return self.open(*args, **kw)

    def delete(self, *args: t.Any, **kw: t.Any) -> TestResponse:
        """Call :meth:`open` with ``method`` set to ``DELETE``."""
        kw["method"] = "DELETE"
        return self.open(*args, **kw)

    def patch(self, *args: t.Any, **kw: t.Any) -> TestResponse:
        """Call :meth:`open` with ``method`` set to ``PATCH``."""
        kw["method"] = "PATCH"
        return self.open(*args, **kw)

    def options(self, *args: t.Any, **kw: t.Any) -> TestResponse:
        """Call :meth:`open` with ``method`` set to ``OPTIONS``."""
        kw["method"] = "OPTIONS"
        return self.open(*args, **kw)

    def head(self, *args: t.Any, **kw: t.Any) -> TestResponse:
        """Call :meth:`open` with ``method`` set to ``HEAD``."""
        kw["method"] = "HEAD"
        return self.open(*args, **kw)

    def trace(self, *args: t.Any, **kw: t.Any) -> TestResponse:
        """Call :meth:`open` with ``method`` set to ``TRACE``."""
        kw["method"] = "TRACE"
        return self.open(*args, **kw)

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.application!r}>"


def create_environ(*args: t.Any, **kwargs: t.Any) -> WSGIEnvironment:
    """Create a new WSGI environ dict based on the values passed.  The first
    parameter should be the path of the request which defaults to '/'.  The
    second one can either be an absolute path (in that case the host is
    localhost:80) or a full path to the request with scheme, netloc port and
    the path to the script.

    This accepts the same arguments as the :class:`EnvironBuilder`
    constructor.

    .. versionchanged:: 0.5
       This function is now a thin wrapper over :class:`EnvironBuilder` which
       was added in 0.5.  The `headers`, `environ_base`, `environ_overrides`
       and `charset` parameters were added.
    """
    builder = EnvironBuilder(*args, **kwargs)

    try:
        return builder.get_environ()
    finally:
        builder.close()


def run_wsgi_app(
    app: WSGIApplication, environ: WSGIEnvironment, buffered: bool = False
) -> tuple[t.Iterable[bytes], str, Headers]:
    """Return a tuple in the form (app_iter, status, headers) of the
    application output.  This works best if you pass it an application that
    returns an iterator all the time.

    Sometimes applications may use the `write()` callable returned
    by the `start_response` function.  This tries to resolve such edge
    cases automatically.  But if you don't get the expected output you
    should set `buffered` to `True` which enforces buffering.

    If passed an invalid WSGI application the behavior of this function is
    undefined.  Never pass non-conforming WSGI applications to this function.

    :param app: the application to execute.
    :param buffered: set to `True` to enforce buffering.
    :return: tuple in the form ``(app_iter, status, headers)``
    """
    # Copy environ to ensure any mutations by the app (ProxyFix, for
    # example) don't affect subsequent requests (such as redirects).
    environ = _get_environ(environ).copy()
    status: str
    response: tuple[str, list[tuple[str, str]]] | None = None
    buffer: list[bytes] = []

    def start_response(status, headers, exc_info=None):  # type: ignore
        nonlocal response

        if exc_info:
            try:
                raise exc_info[1].with_traceback(exc_info[2])
            finally:
                exc_info = None

        response = (status, headers)
        return buffer.append

    app_rv = app(environ, start_response)
    close_func = getattr(app_rv, "close", None)
    app_iter: t.Iterable[bytes] = iter(app_rv)

    # when buffering we emit the close call early and convert the
    # application iterator into a regular list
    if buffered:
        try:
            app_iter = list(app_iter)
        finally:
            if close_func is not None:
                close_func()

    # otherwise we iterate the application iter until we have a response, chain
    # the already received data with the already collected data and wrap it in
    # a new `ClosingIterator` if we need to restore a `close` callable from the
    # original return value.
    else:
        for item in app_iter:
            buffer.append(item)

            if response is not None:
                break

        if buffer:
            app_iter = chain(buffer, app_iter)

        if close_func is not None and app_iter is not app_rv:
            app_iter = ClosingIterator(app_iter, close_func)

    status, headers = response  # type: ignore
    return app_iter, status, Headers(headers)


class TestResponse(Response):
    """:class:`~werkzeug.wrappers.Response` subclass that provides extra
    information about requests made with the test :class:`Client`.

    Test client requests will always return an instance of this class.
    If a custom response class is passed to the client, it is
    subclassed along with this to support test information.

    If the test request included large files, or if the application is
    serving a file, call :meth:`close` to close any open files and
    prevent Python showing a ``ResourceWarning``.

    .. versionchanged:: 2.2
        Set the ``default_mimetype`` to None to prevent a mimetype being
        assumed if missing.

    .. versionchanged:: 2.1
        Response instances cannot be treated as tuples.

    .. versionadded:: 2.0
        Test client methods always return instances of this class.
    """

    default_mimetype = None
    # Don't assume a mimetype, instead use whatever the response provides

    request: Request
    """A request object with the environ used to make the request that
    resulted in this response.
    """

    history: tuple[TestResponse, ...]
    """A list of intermediate responses. Populated when the test request
    is made with ``follow_redirects`` enabled.
    """

    # Tell Pytest to ignore this, it's not a test class.
    __test__ = False

    def __init__(
        self,
        response: t.Iterable[bytes],
        status: str,
        headers: Headers,
        request: Request,
        history: tuple[TestResponse] = (),  # type: ignore
        **kwargs: t.Any,
    ) -> None:
        super().__init__(response, status, headers, **kwargs)
        self.request = request
        self.history = history
        self._compat_tuple = response, status, headers

    @cached_property
    def text(self) -> str:
        """The response data as text. A shortcut for
        ``response.get_data(as_text=True)``.

        .. versionadded:: 2.1
        """
        return self.get_data(as_text=True)


@dataclasses.dataclass
class Cookie:
    """A cookie key, value, and parameters.

    The class itself is not a public API. Its attributes are documented for inspection
    with :meth:`.Client.get_cookie` only.

    .. versionadded:: 2.3
    """

    key: str
    """The cookie key, encoded as a client would see it."""

    value: str
    """The cookie key, encoded as a client would see it."""

    decoded_key: str
    """The cookie key, decoded as the application would set and see it."""

    decoded_value: str
    """The cookie value, decoded as the application would set and see it."""

    expires: datetime | None
    """The time at which the cookie is no longer valid."""

    max_age: int | None
    """The number of seconds from when the cookie was set at which it is
    no longer valid.
    """

    domain: str
    """The domain that the cookie was set for, or the request domain if not set."""

    origin_only: bool
    """Whether the cookie will be sent for exact domain matches only. This is ``True``
    if the ``Domain`` parameter was not present.
    """

    path: str
    """The path that the cookie was set for."""

    secure: bool | None
    """The ``Secure`` parameter."""

    http_only: bool | None
    """The ``HttpOnly`` parameter."""

    same_site: str | None
    """The ``SameSite`` parameter."""

    def _matches_request(self, server_name: str, path: str) -> bool:
        return (
            server_name == self.domain
            or (
                not self.origin_only
                and server_name.endswith(self.domain)
                and server_name[: -len(self.domain)].endswith(".")
            )
        ) and (
            path == self.path
            or (
                path.startswith(self.path)
                and path[len(self.path) - self.path.endswith("/") :].startswith("/")
            )
        )

    def _to_request_header(self) -> str:
        return f"{self.key}={self.value}"

    @classmethod
    def _from_response_header(cls, server_name: str, path: str, header: str) -> te.Self:
        header, _, parameters_str = header.partition(";")
        key, _, value = header.partition("=")
        decoded_key, decoded_value = next(parse_cookie(header).items())  # type: ignore[call-overload]
        params = {}

        for item in parameters_str.split(";"):
            k, sep, v = item.partition("=")
            params[k.strip().lower()] = v.strip() if sep else None

        return cls(
            key=key.strip(),
            value=value.strip(),
            decoded_key=decoded_key,
            decoded_value=decoded_value,
            expires=parse_date(params.get("expires")),
            max_age=int(params["max-age"] or 0) if "max-age" in params else None,
            domain=params.get("domain") or server_name,
            origin_only="domain" not in params,
            path=params.get("path") or path.rpartition("/")[0] or "/",
            secure="secure" in params,
            http_only="httponly" in params,
            same_site=params.get("samesite"),
        )

    @property
    def _storage_key(self) -> tuple[str, str, str]:
        return self.domain, self.path, self.decoded_key

    @property
    def _should_delete(self) -> bool:
        return self.max_age == 0 or (
            self.expires is not None and self.expires.timestamp() == 0
        )
