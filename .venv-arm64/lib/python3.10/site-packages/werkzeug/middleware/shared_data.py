"""
Serve Shared Static Files
=========================

.. autoclass:: SharedDataMiddleware
    :members: is_allowed

:copyright: 2007 Pallets
:license: BSD-3-Clause
"""

from __future__ import annotations

import collections.abc as cabc
import importlib.util
import mimetypes
import os
import posixpath
import typing as t
from datetime import datetime
from datetime import timezone
from io import BytesIO
from time import time
from zlib import adler32

from ..http import http_date
from ..http import is_resource_modified
from ..security import safe_join
from ..utils import get_content_type
from ..wsgi import get_path_info
from ..wsgi import wrap_file

_TOpener = t.Callable[[], tuple[t.IO[bytes], datetime, int]]
_TLoader = t.Callable[[t.Optional[str]], tuple[t.Optional[str], t.Optional[_TOpener]]]

if t.TYPE_CHECKING:
    from _typeshed.wsgi import StartResponse
    from _typeshed.wsgi import WSGIApplication
    from _typeshed.wsgi import WSGIEnvironment


class SharedDataMiddleware:
    """A WSGI middleware which provides static content for development
    environments or simple server setups. Its usage is quite simple::

        import os
        from werkzeug.middleware.shared_data import SharedDataMiddleware

        app = SharedDataMiddleware(app, {
            '/shared': os.path.join(os.path.dirname(__file__), 'shared')
        })

    The contents of the folder ``./shared`` will now be available on
    ``http://example.com/shared/``.  This is pretty useful during development
    because a standalone media server is not required. Files can also be
    mounted on the root folder and still continue to use the application because
    the shared data middleware forwards all unhandled requests to the
    application, even if the requests are below one of the shared folders.

    If `pkg_resources` is available you can also tell the middleware to serve
    files from package data::

        app = SharedDataMiddleware(app, {
            '/static': ('myapplication', 'static')
        })

    This will then serve the ``static`` folder in the `myapplication`
    Python package.

    The optional `disallow` parameter can be a list of :func:`~fnmatch.fnmatch`
    rules for files that are not accessible from the web.  If `cache` is set to
    `False` no caching headers are sent.

    Currently the middleware does not support non-ASCII filenames. If the
    encoding on the file system happens to match the encoding of the URI it may
    work but this could also be by accident. We strongly suggest using ASCII
    only file names for static files.

    The middleware will guess the mimetype using the Python `mimetype`
    module.  If it's unable to figure out the charset it will fall back
    to `fallback_mimetype`.

    :param app: the application to wrap.  If you don't want to wrap an
                application you can pass it :exc:`NotFound`.
    :param exports: a list or dict of exported files and folders.
    :param disallow: a list of :func:`~fnmatch.fnmatch` rules.
    :param cache: enable or disable caching headers.
    :param cache_timeout: the cache timeout in seconds for the headers.
    :param fallback_mimetype: The fallback mimetype for unknown files.

    .. versionchanged:: 1.0
        The default ``fallback_mimetype`` is
        ``application/octet-stream``. If a filename looks like a text
        mimetype, the ``utf-8`` charset is added to it.

    .. versionadded:: 0.6
        Added ``fallback_mimetype``.

    .. versionchanged:: 0.5
        Added ``cache_timeout``.
    """

    def __init__(
        self,
        app: WSGIApplication,
        exports: (
            cabc.Mapping[str, str | tuple[str, str]]
            | t.Iterable[tuple[str, str | tuple[str, str]]]
        ),
        disallow: None = None,
        cache: bool = True,
        cache_timeout: int = 60 * 60 * 12,
        fallback_mimetype: str = "application/octet-stream",
    ) -> None:
        self.app = app
        self.exports: list[tuple[str, _TLoader]] = []
        self.cache = cache
        self.cache_timeout = cache_timeout

        if isinstance(exports, cabc.Mapping):
            exports = exports.items()

        for key, value in exports:
            if isinstance(value, tuple):
                loader = self.get_package_loader(*value)
            elif isinstance(value, str):
                if os.path.isfile(value):
                    loader = self.get_file_loader(value)
                else:
                    loader = self.get_directory_loader(value)
            else:
                raise TypeError(f"unknown def {value!r}")

            self.exports.append((key, loader))

        if disallow is not None:
            from fnmatch import fnmatch

            self.is_allowed = lambda x: not fnmatch(x, disallow)

        self.fallback_mimetype = fallback_mimetype

    def is_allowed(self, filename: str) -> bool:
        """Subclasses can override this method to disallow the access to
        certain files.  However by providing `disallow` in the constructor
        this method is overwritten.
        """
        return True

    def _opener(self, filename: str) -> _TOpener:
        return lambda: (
            open(filename, "rb"),
            datetime.fromtimestamp(os.path.getmtime(filename), tz=timezone.utc),
            int(os.path.getsize(filename)),
        )

    def get_file_loader(self, filename: str) -> _TLoader:
        return lambda x: (os.path.basename(filename), self._opener(filename))

    def get_package_loader(self, package: str, package_path: str) -> _TLoader:
        load_time = datetime.now(timezone.utc)
        spec = importlib.util.find_spec(package)
        reader = spec.loader.get_resource_reader(package)  # type: ignore[union-attr]

        def loader(
            path: str | None,
        ) -> tuple[str | None, _TOpener | None]:
            if path is None:
                return None, None

            path = safe_join(package_path, path)

            if path is None:
                return None, None

            basename = posixpath.basename(path)

            try:
                resource = reader.open_resource(path)
            except OSError:
                return None, None

            if isinstance(resource, BytesIO):
                return (
                    basename,
                    lambda: (resource, load_time, len(resource.getvalue())),
                )

            return (
                basename,
                lambda: (
                    resource,
                    datetime.fromtimestamp(
                        os.path.getmtime(resource.name), tz=timezone.utc
                    ),
                    os.path.getsize(resource.name),
                ),
            )

        return loader

    def get_directory_loader(self, directory: str) -> _TLoader:
        def loader(
            path: str | None,
        ) -> tuple[str | None, _TOpener | None]:
            if path is not None:
                path = safe_join(directory, path)

                if path is None:
                    return None, None
            else:
                path = directory

            if os.path.isfile(path):
                return os.path.basename(path), self._opener(path)

            return None, None

        return loader

    def generate_etag(self, mtime: datetime, file_size: int, real_filename: str) -> str:
        fn_str = os.fsencode(real_filename)
        timestamp = mtime.timestamp()
        checksum = adler32(fn_str) & 0xFFFFFFFF
        return f"wzsdm-{timestamp}-{file_size}-{checksum}"

    def __call__(
        self, environ: WSGIEnvironment, start_response: StartResponse
    ) -> t.Iterable[bytes]:
        path = get_path_info(environ)
        file_loader = None

        for search_path, loader in self.exports:
            if search_path == path:
                real_filename, file_loader = loader(None)

                if file_loader is not None:
                    break

            if not search_path.endswith("/"):
                search_path += "/"

            if path.startswith(search_path):
                real_filename, file_loader = loader(path[len(search_path) :])

                if file_loader is not None:
                    break

        if file_loader is None or not self.is_allowed(real_filename):  # type: ignore
            return self.app(environ, start_response)

        guessed_type = mimetypes.guess_type(real_filename)  # type: ignore
        mime_type = get_content_type(guessed_type[0] or self.fallback_mimetype, "utf-8")
        f, mtime, file_size = file_loader()

        headers = [("Date", http_date())]

        if self.cache:
            timeout = self.cache_timeout
            etag = self.generate_etag(mtime, file_size, real_filename)  # type: ignore
            headers += [
                ("Etag", f'"{etag}"'),
                ("Cache-Control", f"max-age={timeout}, public"),
            ]

            if not is_resource_modified(environ, etag, last_modified=mtime):
                f.close()
                start_response("304 Not Modified", headers)
                return []

            headers.append(("Expires", http_date(time() + timeout)))
        else:
            headers.append(("Cache-Control", "public"))

        headers.extend(
            (
                ("Content-Type", mime_type),
                ("Content-Length", str(file_size)),
                ("Last-Modified", http_date(mtime)),
            )
        )
        start_response("200 OK", headers)
        return wrap_file(environ, f)
