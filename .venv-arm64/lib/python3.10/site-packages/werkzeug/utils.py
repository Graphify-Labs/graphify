from __future__ import annotations

import io
import mimetypes
import os
import pkgutil
import re
import sys
import typing as t
import unicodedata
from datetime import datetime
from time import time
from urllib.parse import quote
from zlib import adler32

from markupsafe import escape

from ._internal import _DictAccessorProperty
from ._internal import _missing
from ._internal import _TAccessorValue
from .datastructures import Headers
from .exceptions import NotFound
from .exceptions import RequestedRangeNotSatisfiable
from .security import _windows_device_files
from .security import safe_join
from .wsgi import wrap_file

if t.TYPE_CHECKING:
    from _typeshed.wsgi import WSGIEnvironment

    from .wrappers.request import Request
    from .wrappers.response import Response

_T = t.TypeVar("_T")

_entity_re = re.compile(r"&([^;]+);")
_filename_ascii_strip_re = re.compile(r"[^A-Za-z0-9_.-]")


class cached_property(property, t.Generic[_T]):
    """A :func:`property` that is only evaluated once. Subsequent access
    returns the cached value. Setting the property sets the cached
    value. Deleting the property clears the cached value, accessing it
    again will evaluate it again.

    .. code-block:: python

        class Example:
            @cached_property
            def value(self):
                # calculate something important here
                return 42

        e = Example()
        e.value  # evaluates
        e.value  # uses cache
        e.value = 16  # sets cache
        del e.value  # clears cache

    If the class defines ``__slots__``, it must add ``_cache_{name}`` as
    a slot. Alternatively, it can add ``__dict__``, but that's usually
    not desirable.

    .. versionchanged:: 2.1
        Works with ``__slots__``.

    .. versionchanged:: 2.0
        ``del obj.name`` clears the cached value.
    """

    def __init__(
        self,
        fget: t.Callable[[t.Any], _T],
        name: str | None = None,
        doc: str | None = None,
    ) -> None:
        super().__init__(fget, doc=doc)
        self.__name__ = name or fget.__name__
        self.slot_name = f"_cache_{self.__name__}"
        self.__module__ = fget.__module__

    def __set__(self, obj: object, value: _T) -> None:
        if hasattr(obj, "__dict__"):
            obj.__dict__[self.__name__] = value
        else:
            setattr(obj, self.slot_name, value)

    def __get__(self, obj: object, type: type = None) -> _T:  # type: ignore
        if obj is None:
            return self  # type: ignore

        obj_dict = getattr(obj, "__dict__", None)

        if obj_dict is not None:
            value: _T = obj_dict.get(self.__name__, _missing)
        else:
            value = getattr(obj, self.slot_name, _missing)  # type: ignore[arg-type]

        if value is _missing:
            value = self.fget(obj)  # type: ignore

            if obj_dict is not None:
                obj.__dict__[self.__name__] = value
            else:
                setattr(obj, self.slot_name, value)

        return value

    def __delete__(self, obj: object) -> None:
        if hasattr(obj, "__dict__"):
            del obj.__dict__[self.__name__]
        else:
            setattr(obj, self.slot_name, _missing)


class environ_property(_DictAccessorProperty[_TAccessorValue]):
    """Maps request attributes to environment variables. This works not only
    for the Werkzeug request object, but also any other class with an
    environ attribute:

    >>> class Test(object):
    ...     environ = {'key': 'value'}
    ...     test = environ_property('key')
    >>> var = Test()
    >>> var.test
    'value'

    If you pass it a second value it's used as default if the key does not
    exist, the third one can be a converter that takes a value and converts
    it.  If it raises :exc:`ValueError` or :exc:`TypeError` the default value
    is used. If no default value is provided `None` is used.

    Per default the property is read only.  You have to explicitly enable it
    by passing ``read_only=False`` to the constructor.
    """

    read_only = True

    def lookup(self, obj: Request) -> WSGIEnvironment:
        return obj.environ


class header_property(_DictAccessorProperty[_TAccessorValue]):
    """Like `environ_property` but for headers."""

    def lookup(self, obj: Request | Response) -> Headers:  # type: ignore[override]
        return obj.headers


# https://cgit.freedesktop.org/xdg/shared-mime-info/tree/freedesktop.org.xml.in
# https://www.iana.org/assignments/media-types/media-types.xhtml
# Types listed in the XDG mime info that have a charset in the IANA registration.
_charset_mimetypes = {
    "application/ecmascript",
    "application/javascript",
    "application/sql",
    "application/xml",
    "application/xml-dtd",
    "application/xml-external-parsed-entity",
}


def get_content_type(mimetype: str, charset: str) -> str:
    """Returns the full content type string with charset for a mimetype.

    If the mimetype represents text, the charset parameter will be
    appended, otherwise the mimetype is returned unchanged.

    :param mimetype: The mimetype to be used as content type.
    :param charset: The charset to be appended for text mimetypes.
    :return: The content type.

    .. versionchanged:: 0.15
        Any type that ends with ``+xml`` gets a charset, not just those
        that start with ``application/``. Known text types such as
        ``application/javascript`` are also given charsets.
    """
    if (
        mimetype.startswith("text/")
        or mimetype in _charset_mimetypes
        or mimetype.endswith("+xml")
    ):
        mimetype += f"; charset={charset}"

    return mimetype


def secure_filename(filename: str) -> str:
    r"""Pass it a filename and it will return a secure version of it.  This
    filename can then safely be stored on a regular file system and passed
    to :func:`os.path.join`.  The filename returned is an ASCII only string
    for maximum portability.

    On windows systems the function also makes sure that the file is not
    named after one of the special device files.

    >>> secure_filename("My cool movie.mov")
    'My_cool_movie.mov'
    >>> secure_filename("../../../etc/passwd")
    'etc_passwd'
    >>> secure_filename('i contain cool \xfcml\xe4uts.txt')
    'i_contain_cool_umlauts.txt'

    The function might return an empty filename.  It's your responsibility
    to ensure that the filename is unique and that you abort or
    generate a random filename if the function returned an empty one.

    .. versionadded:: 0.5

    :param filename: the filename to secure
    """
    filename = unicodedata.normalize("NFKD", filename)
    filename = filename.encode("ascii", "ignore").decode("ascii")

    for sep in os.sep, os.path.altsep:
        if sep:
            filename = filename.replace(sep, " ")
    filename = str(_filename_ascii_strip_re.sub("", "_".join(filename.split()))).strip(
        "._"
    )

    # on nt a couple of special files are present in each folder.  We
    # have to ensure that the target file is not such a filename.  In
    # this case we prepend an underline
    if (
        os.name == "nt"
        and filename
        and filename.split(".")[0].upper() in _windows_device_files
    ):
        filename = f"_{filename}"

    return filename


def redirect(
    location: str, code: int = 302, Response: type[Response] | None = None
) -> Response:
    """Returns a response object (a WSGI application) that, if called,
    redirects the client to the target location. Supported codes are
    301, 302, 303, 305, 307, and 308. 300 is not supported because
    it's not a real redirect and 304 because it's the answer for a
    request with a request with defined If-Modified-Since headers.

    .. versionadded:: 0.6
       The location can now be a unicode string that is encoded using
       the :func:`iri_to_uri` function.

    .. versionadded:: 0.10
        The class used for the Response object can now be passed in.

    :param location: the location the response should redirect to.
    :param code: the redirect status code. defaults to 302.
    :param class Response: a Response class to use when instantiating a
        response. The default is :class:`werkzeug.wrappers.Response` if
        unspecified.
    """
    if Response is None:
        from .wrappers import Response

    html_location = escape(location)
    response = Response(  # type: ignore[misc]
        "<!doctype html>\n"
        "<html lang=en>\n"
        "<title>Redirecting...</title>\n"
        "<h1>Redirecting...</h1>\n"
        "<p>You should be redirected automatically to the target URL: "
        f'<a href="{html_location}">{html_location}</a>. If not, click the link.\n',
        code,
        mimetype="text/html",
    )
    response.headers["Location"] = location
    return response


def append_slash_redirect(environ: WSGIEnvironment, code: int = 308) -> Response:
    """Redirect to the current URL with a slash appended.

    If the current URL is ``/user/42``, the redirect URL will be
    ``42/``. When joined to the current URL during response
    processing or by the browser, this will produce ``/user/42/``.

    The behavior is undefined if the path ends with a slash already. If
    called unconditionally on a URL, it may produce a redirect loop.

    :param environ: Use the path and query from this WSGI environment
        to produce the redirect URL.
    :param code: the status code for the redirect.

    .. versionchanged:: 2.1
        Produce a relative URL that only modifies the last segment.
        Relevant when the current path has multiple segments.

    .. versionchanged:: 2.1
        The default status code is 308 instead of 301. This preserves
        the request method and body.
    """
    tail = environ["PATH_INFO"].rpartition("/")[2]

    if not tail:
        new_path = "./"
    else:
        new_path = f"{tail}/"

    query_string = environ.get("QUERY_STRING")

    if query_string:
        new_path = f"{new_path}?{query_string}"

    return redirect(new_path, code)


def send_file(
    path_or_file: os.PathLike[str] | str | t.IO[bytes],
    environ: WSGIEnvironment,
    mimetype: str | None = None,
    as_attachment: bool = False,
    download_name: str | None = None,
    conditional: bool = True,
    etag: bool | str = True,
    last_modified: datetime | int | float | None = None,
    max_age: None | (int | t.Callable[[str | None], int | None]) = None,
    use_x_sendfile: bool = False,
    response_class: type[Response] | None = None,
    _root_path: os.PathLike[str] | str | None = None,
) -> Response:
    """Send the contents of a file to the client.

    The first argument can be a file path or a file-like object. Paths
    are preferred in most cases because Werkzeug can manage the file and
    get extra information from the path. Passing a file-like object
    requires that the file is opened in binary mode, and is mostly
    useful when building a file in memory with :class:`io.BytesIO`.

    Never pass file paths provided by a user. The path is assumed to be
    trusted, so a user could craft a path to access a file you didn't
    intend. Use :func:`send_from_directory` to safely serve user-provided paths.

    If the WSGI server sets a ``file_wrapper`` in ``environ``, it is
    used, otherwise Werkzeug's built-in wrapper is used. Alternatively,
    if the HTTP server supports ``X-Sendfile``, ``use_x_sendfile=True``
    will tell the server to send the given path, which is much more
    efficient than reading it in Python.

    :param path_or_file: The path to the file to send, relative to the
        current working directory if a relative path is given.
        Alternatively, a file-like object opened in binary mode. Make
        sure the file pointer is seeked to the start of the data.
    :param environ: The WSGI environ for the current request.
    :param mimetype: The MIME type to send for the file. If not
        provided, it will try to detect it from the file name.
    :param as_attachment: Indicate to a browser that it should offer to
        save the file instead of displaying it.
    :param download_name: The default name browsers will use when saving
        the file. Defaults to the passed file name.
    :param conditional: Enable conditional and range responses based on
        request headers. Requires passing a file path and ``environ``.
    :param etag: Calculate an ETag for the file, which requires passing
        a file path. Can also be a string to use instead.
    :param last_modified: The last modified time to send for the file,
        in seconds. If not provided, it will try to detect it from the
        file path.
    :param max_age: How long the client should cache the file, in
        seconds. If set, ``Cache-Control`` will be ``public``, otherwise
        it will be ``no-cache`` to prefer conditional caching.
    :param use_x_sendfile: Set the ``X-Sendfile`` header to let the
        server to efficiently send the file. Requires support from the
        HTTP server. Requires passing a file path.
    :param response_class: Build the response using this class. Defaults
        to :class:`~werkzeug.wrappers.Response`.
    :param _root_path: Do not use. For internal use only. Use
        :func:`send_from_directory` to safely send files under a path.

    .. versionchanged:: 2.0.2
        ``send_file`` only sets a detected ``Content-Encoding`` if
        ``as_attachment`` is disabled.

    .. versionadded:: 2.0
        Adapted from Flask's implementation.

    .. versionchanged:: 2.0
        ``download_name`` replaces Flask's ``attachment_filename``
         parameter. If ``as_attachment=False``, it is passed with
         ``Content-Disposition: inline`` instead.

    .. versionchanged:: 2.0
        ``max_age`` replaces Flask's ``cache_timeout`` parameter.
        ``conditional`` is enabled and ``max_age`` is not set by
        default.

    .. versionchanged:: 2.0
        ``etag`` replaces Flask's ``add_etags`` parameter. It can be a
        string to use instead of generating one.

    .. versionchanged:: 2.0
        If an encoding is returned when guessing ``mimetype`` from
        ``download_name``, set the ``Content-Encoding`` header.
    """
    if response_class is None:
        from .wrappers import Response

        response_class = Response

    path: str | None = None
    file: t.IO[bytes] | None = None
    size: int | None = None
    mtime: float | None = None
    headers = Headers()

    if isinstance(path_or_file, (os.PathLike, str)) or hasattr(
        path_or_file, "__fspath__"
    ):
        path_or_file = t.cast("os.PathLike[str] | str", path_or_file)

        # Flask will pass app.root_path, allowing its send_file wrapper
        # to not have to deal with paths.
        if _root_path is not None:
            path = os.path.join(_root_path, path_or_file)
        else:
            path = os.path.abspath(path_or_file)

        stat = os.stat(path)
        size = stat.st_size
        mtime = stat.st_mtime
    else:
        file = path_or_file

    if download_name is None and path is not None:
        download_name = os.path.basename(path)

    if mimetype is None:
        if download_name is None:
            raise TypeError(
                "Unable to detect the MIME type because a file name is"
                " not available. Either set 'download_name', pass a"
                " path instead of a file, or set 'mimetype'."
            )

        mimetype, encoding = mimetypes.guess_type(download_name)

        if mimetype is None:
            mimetype = "application/octet-stream"

        # Don't send encoding for attachments, it causes browsers to
        # save decompress tar.gz files.
        if encoding is not None and not as_attachment:
            headers.set("Content-Encoding", encoding)

    if download_name is not None:
        try:
            download_name.encode("ascii")
        except UnicodeEncodeError:
            simple = unicodedata.normalize("NFKD", download_name)
            simple = simple.encode("ascii", "ignore").decode("ascii")
            # safe = RFC 5987 attr-char
            quoted = quote(download_name, safe="!#$&+-.^_`|~")
            names = {"filename": simple, "filename*": f"UTF-8''{quoted}"}
        else:
            names = {"filename": download_name}

        value = "attachment" if as_attachment else "inline"
        headers.set("Content-Disposition", value, **names)
    elif as_attachment:
        raise TypeError(
            "No name provided for attachment. Either set"
            " 'download_name' or pass a path instead of a file."
        )

    if use_x_sendfile and path is not None:
        headers["X-Sendfile"] = path
        data = None
    else:
        if file is None:
            file = open(path, "rb")  # type: ignore
        elif isinstance(file, io.BytesIO):
            size = file.getbuffer().nbytes
        elif isinstance(file, io.TextIOBase):
            raise ValueError("Files must be opened in binary mode or use BytesIO.")

        data = wrap_file(environ, file)

    rv = response_class(
        data, mimetype=mimetype, headers=headers, direct_passthrough=True
    )

    if size is not None:
        rv.content_length = size

    if last_modified is not None:
        rv.last_modified = last_modified  # type: ignore
    elif mtime is not None:
        rv.last_modified = mtime  # type: ignore

    rv.cache_control.no_cache = True

    # Flask will pass app.get_send_file_max_age, allowing its send_file
    # wrapper to not have to deal with paths.
    if callable(max_age):
        max_age = max_age(path)

    if max_age is not None:
        if max_age > 0:
            rv.cache_control.no_cache = None
            rv.cache_control.public = True

        rv.cache_control.max_age = max_age
        rv.expires = int(time() + max_age)  # type: ignore

    if isinstance(etag, str):
        rv.set_etag(etag)
    elif etag and path is not None:
        check = adler32(path.encode()) & 0xFFFFFFFF
        rv.set_etag(f"{mtime}-{size}-{check}")

    if conditional:
        try:
            rv = rv.make_conditional(environ, accept_ranges=True, complete_length=size)
        except RequestedRangeNotSatisfiable:
            if file is not None:
                file.close()

            raise

        # Some x-sendfile implementations incorrectly ignore the 304
        # status code and send the file anyway.
        if rv.status_code == 304:
            rv.headers.pop("x-sendfile", None)

    return rv


def send_from_directory(
    directory: os.PathLike[str] | str,
    path: os.PathLike[str] | str,
    environ: WSGIEnvironment,
    **kwargs: t.Any,
) -> Response:
    """Send a file from within a directory using :func:`send_file`.

    This is a secure way to serve files from a folder, such as static
    files or uploads. Uses :func:`~werkzeug.security.safe_join` to
    ensure the path coming from the client is not maliciously crafted to
    point outside the specified directory.

    If the final path does not point to an existing regular file,
    returns a 404 :exc:`~werkzeug.exceptions.NotFound` error.

    :param directory: The directory that ``path`` must be located under. This *must not*
        be a value provided by the client, otherwise it becomes insecure.
    :param path: The path to the file to send, relative to ``directory``. This is the
        part of the path provided by the client, which is checked for security.
    :param environ: The WSGI environ for the current request.
    :param kwargs: Arguments to pass to :func:`send_file`.

    .. versionadded:: 2.0
        Adapted from Flask's implementation.
    """
    path_str = safe_join(os.fspath(directory), os.fspath(path))

    if path_str is None:
        raise NotFound()

    # Flask will pass app.root_path, allowing its send_from_directory
    # wrapper to not have to deal with paths.
    if "_root_path" in kwargs:
        path_str = os.path.join(kwargs["_root_path"], path_str)

    if not os.path.isfile(path_str):
        raise NotFound()

    return send_file(path_str, environ, **kwargs)


def import_string(import_name: str, silent: bool = False) -> t.Any:
    """Imports an object based on a string.  This is useful if you want to
    use import paths as endpoints or something similar.  An import path can
    be specified either in dotted notation (``xml.sax.saxutils.escape``)
    or with a colon as object delimiter (``xml.sax.saxutils:escape``).

    If `silent` is True the return value will be `None` if the import fails.

    :param import_name: the dotted name for the object to import.
    :param silent: if set to `True` import errors are ignored and
                   `None` is returned instead.
    :return: imported object
    """
    import_name = import_name.replace(":", ".")
    try:
        try:
            __import__(import_name)
        except ImportError:
            if "." not in import_name:
                raise
        else:
            return sys.modules[import_name]

        module_name, obj_name = import_name.rsplit(".", 1)
        module = __import__(module_name, globals(), locals(), [obj_name])
        try:
            return getattr(module, obj_name)
        except AttributeError as e:
            raise ImportError(e) from None

    except ImportError as e:
        if not silent:
            raise ImportStringError(import_name, e).with_traceback(
                sys.exc_info()[2]
            ) from None

    return None


def find_modules(
    import_path: str, include_packages: bool = False, recursive: bool = False
) -> t.Iterator[str]:
    """Finds all the modules below a package.  This can be useful to
    automatically import all views / controllers so that their metaclasses /
    function decorators have a chance to register themselves on the
    application.

    Packages are not returned unless `include_packages` is `True`.  This can
    also recursively list modules but in that case it will import all the
    packages to get the correct load path of that module.

    :param import_path: the dotted name for the package to find child modules.
    :param include_packages: set to `True` if packages should be returned, too.
    :param recursive: set to `True` if recursion should happen.
    :return: generator
    """
    module = import_string(import_path)
    path = getattr(module, "__path__", None)
    if path is None:
        raise ValueError(f"{import_path!r} is not a package")
    basename = f"{module.__name__}."
    for _importer, modname, ispkg in pkgutil.iter_modules(path):
        modname = basename + modname
        if ispkg:
            if include_packages:
                yield modname
            if recursive:
                yield from find_modules(modname, include_packages, True)
        else:
            yield modname


class ImportStringError(ImportError):
    """Provides information about a failed :func:`import_string` attempt."""

    #: String in dotted notation that failed to be imported.
    import_name: str
    #: Wrapped exception.
    exception: BaseException

    def __init__(self, import_name: str, exception: BaseException) -> None:
        self.import_name = import_name
        self.exception = exception
        msg = import_name
        name = ""
        tracked = []
        for part in import_name.replace(":", ".").split("."):
            name = f"{name}.{part}" if name else part
            imported = import_string(name, silent=True)
            if imported:
                tracked.append((name, getattr(imported, "__file__", None)))
            else:
                track = [f"- {n!r} found in {i!r}." for n, i in tracked]
                track.append(f"- {name!r} not found.")
                track_str = "\n".join(track)
                msg = (
                    f"import_string() failed for {import_name!r}. Possible reasons"
                    f" are:\n\n"
                    "- missing __init__.py in a package;\n"
                    "- package or module path not included in sys.path;\n"
                    "- duplicated package or module name taking precedence in"
                    " sys.path;\n"
                    "- missing module, class, function or variable;\n\n"
                    f"Debugged import:\n\n{track_str}\n\n"
                    f"Original exception:\n\n{type(exception).__name__}: {exception}"
                )
                break

        super().__init__(msg)

    def __repr__(self) -> str:
        return f"<{type(self).__name__}({self.import_name!r}, {self.exception!r})>"
