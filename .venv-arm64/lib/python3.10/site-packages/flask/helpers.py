from __future__ import annotations

import importlib.util
import os
import sys
import typing as t
from datetime import datetime
from functools import cache
from functools import update_wrapper

import werkzeug.utils
from werkzeug.exceptions import abort as _wz_abort
from werkzeug.utils import redirect as _wz_redirect
from werkzeug.wrappers import Response as BaseResponse

from .globals import _cv_app
from .globals import _cv_request
from .globals import current_app
from .globals import request
from .globals import request_ctx
from .globals import session
from .signals import message_flashed

if t.TYPE_CHECKING:  # pragma: no cover
    from .wrappers import Response


def get_debug_flag() -> bool:
    """Get whether debug mode should be enabled for the app, indicated by the
    :envvar:`FLASK_DEBUG` environment variable. The default is ``False``.
    """
    val = os.environ.get("FLASK_DEBUG")
    return bool(val and val.lower() not in {"0", "false", "no"})


def get_load_dotenv(default: bool = True) -> bool:
    """Get whether the user has disabled loading default dotenv files by
    setting :envvar:`FLASK_SKIP_DOTENV`. The default is ``True``, load
    the files.

    :param default: What to return if the env var isn't set.
    """
    val = os.environ.get("FLASK_SKIP_DOTENV")

    if not val:
        return default

    return val.lower() in ("0", "false", "no")


@t.overload
def stream_with_context(
    generator_or_function: t.Iterator[t.AnyStr],
) -> t.Iterator[t.AnyStr]: ...


@t.overload
def stream_with_context(
    generator_or_function: t.Callable[..., t.Iterator[t.AnyStr]],
) -> t.Callable[[t.Iterator[t.AnyStr]], t.Iterator[t.AnyStr]]: ...


def stream_with_context(
    generator_or_function: t.Iterator[t.AnyStr] | t.Callable[..., t.Iterator[t.AnyStr]],
) -> t.Iterator[t.AnyStr] | t.Callable[[t.Iterator[t.AnyStr]], t.Iterator[t.AnyStr]]:
    """Wrap a response generator function so that it runs inside the current
    request context. This keeps :data:`request`, :data:`session`, and :data:`g`
    available, even though at the point the generator runs the request context
    will typically have ended.

    Use it as a decorator on a generator function:

    .. code-block:: python

        from flask import stream_with_context, request, Response

        @app.get("/stream")
        def streamed_response():
            @stream_with_context
            def generate():
                yield "Hello "
                yield request.args["name"]
                yield "!"

            return Response(generate())

    Or use it as a wrapper around a created generator:

    .. code-block:: python

        from flask import stream_with_context, request, Response

        @app.get("/stream")
        def streamed_response():
            def generate():
                yield "Hello "
                yield request.args["name"]
                yield "!"

            return Response(stream_with_context(generate()))

    .. versionadded:: 0.9
    """
    try:
        gen = iter(generator_or_function)  # type: ignore[arg-type]
    except TypeError:

        def decorator(*args: t.Any, **kwargs: t.Any) -> t.Any:
            gen = generator_or_function(*args, **kwargs)  # type: ignore[operator]
            return stream_with_context(gen)

        return update_wrapper(decorator, generator_or_function)  # type: ignore[arg-type]

    def generator() -> t.Iterator[t.AnyStr]:
        if (req_ctx := _cv_request.get(None)) is None:
            raise RuntimeError(
                "'stream_with_context' can only be used when a request"
                " context is active, such as in a view function."
            )

        app_ctx = _cv_app.get()
        # Setup code below will run the generator to this point, so that the
        # current contexts are recorded. The contexts must be pushed after,
        # otherwise their ContextVar will record the wrong event loop during
        # async view functions.
        yield None  # type: ignore[misc]

        # Push the app context first, so that the request context does not
        # automatically create and push a different app context.
        with app_ctx, req_ctx:
            try:
                yield from gen
            finally:
                # Clean up in case the user wrapped a WSGI iterator.
                if hasattr(gen, "close"):
                    gen.close()

    # Execute the generator to the sentinel value. This ensures the context is
    # preserved in the generator's state. Further iteration will push the
    # context and yield from the original iterator.
    wrapped_g = generator()
    next(wrapped_g)
    return wrapped_g


def make_response(*args: t.Any) -> Response:
    """Sometimes it is necessary to set additional headers in a view.  Because
    views do not have to return response objects but can return a value that
    is converted into a response object by Flask itself, it becomes tricky to
    add headers to it.  This function can be called instead of using a return
    and you will get a response object which you can use to attach headers.

    If view looked like this and you want to add a new header::

        def index():
            return render_template('index.html', foo=42)

    You can now do something like this::

        def index():
            response = make_response(render_template('index.html', foo=42))
            response.headers['X-Parachutes'] = 'parachutes are cool'
            return response

    This function accepts the very same arguments you can return from a
    view function.  This for example creates a response with a 404 error
    code::

        response = make_response(render_template('not_found.html'), 404)

    The other use case of this function is to force the return value of a
    view function into a response which is helpful with view
    decorators::

        response = make_response(view_function())
        response.headers['X-Parachutes'] = 'parachutes are cool'

    Internally this function does the following things:

    -   if no arguments are passed, it creates a new response argument
    -   if one argument is passed, :meth:`flask.Flask.make_response`
        is invoked with it.
    -   if more than one argument is passed, the arguments are passed
        to the :meth:`flask.Flask.make_response` function as tuple.

    .. versionadded:: 0.6
    """
    if not args:
        return current_app.response_class()
    if len(args) == 1:
        args = args[0]
    return current_app.make_response(args)


def url_for(
    endpoint: str,
    *,
    _anchor: str | None = None,
    _method: str | None = None,
    _scheme: str | None = None,
    _external: bool | None = None,
    **values: t.Any,
) -> str:
    """Generate a URL to the given endpoint with the given values.

    This requires an active request or application context, and calls
    :meth:`current_app.url_for() <flask.Flask.url_for>`. See that method
    for full documentation.

    :param endpoint: The endpoint name associated with the URL to
        generate. If this starts with a ``.``, the current blueprint
        name (if any) will be used.
    :param _anchor: If given, append this as ``#anchor`` to the URL.
    :param _method: If given, generate the URL associated with this
        method for the endpoint.
    :param _scheme: If given, the URL will have this scheme if it is
        external.
    :param _external: If given, prefer the URL to be internal (False) or
        require it to be external (True). External URLs include the
        scheme and domain. When not in an active request, URLs are
        external by default.
    :param values: Values to use for the variable parts of the URL rule.
        Unknown keys are appended as query string arguments, like
        ``?a=b&c=d``.

    .. versionchanged:: 2.2
        Calls ``current_app.url_for``, allowing an app to override the
        behavior.

    .. versionchanged:: 0.10
       The ``_scheme`` parameter was added.

    .. versionchanged:: 0.9
       The ``_anchor`` and ``_method`` parameters were added.

    .. versionchanged:: 0.9
       Calls ``app.handle_url_build_error`` on build errors.
    """
    return current_app.url_for(
        endpoint,
        _anchor=_anchor,
        _method=_method,
        _scheme=_scheme,
        _external=_external,
        **values,
    )


def redirect(
    location: str, code: int = 302, Response: type[BaseResponse] | None = None
) -> BaseResponse:
    """Create a redirect response object.

    If :data:`~flask.current_app` is available, it will use its
    :meth:`~flask.Flask.redirect` method, otherwise it will use
    :func:`werkzeug.utils.redirect`.

    :param location: The URL to redirect to.
    :param code: The status code for the redirect.
    :param Response: The response class to use. Not used when
        ``current_app`` is active, which uses ``app.response_class``.

    .. versionadded:: 2.2
        Calls ``current_app.redirect`` if available instead of always
        using Werkzeug's default ``redirect``.
    """
    if current_app:
        return current_app.redirect(location, code=code)

    return _wz_redirect(location, code=code, Response=Response)


def abort(code: int | BaseResponse, *args: t.Any, **kwargs: t.Any) -> t.NoReturn:
    """Raise an :exc:`~werkzeug.exceptions.HTTPException` for the given
    status code.

    If :data:`~flask.current_app` is available, it will call its
    :attr:`~flask.Flask.aborter` object, otherwise it will use
    :func:`werkzeug.exceptions.abort`.

    :param code: The status code for the exception, which must be
        registered in ``app.aborter``.
    :param args: Passed to the exception.
    :param kwargs: Passed to the exception.

    .. versionadded:: 2.2
        Calls ``current_app.aborter`` if available instead of always
        using Werkzeug's default ``abort``.
    """
    if current_app:
        current_app.aborter(code, *args, **kwargs)

    _wz_abort(code, *args, **kwargs)


def get_template_attribute(template_name: str, attribute: str) -> t.Any:
    """Loads a macro (or variable) a template exports.  This can be used to
    invoke a macro from within Python code.  If you for example have a
    template named :file:`_cider.html` with the following contents:

    .. sourcecode:: html+jinja

       {% macro hello(name) %}Hello {{ name }}!{% endmacro %}

    You can access this from Python code like this::

        hello = get_template_attribute('_cider.html', 'hello')
        return hello('World')

    .. versionadded:: 0.2

    :param template_name: the name of the template
    :param attribute: the name of the variable of macro to access
    """
    return getattr(current_app.jinja_env.get_template(template_name).module, attribute)


def flash(message: str, category: str = "message") -> None:
    """Flashes a message to the next request.  In order to remove the
    flashed message from the session and to display it to the user,
    the template has to call :func:`get_flashed_messages`.

    .. versionchanged:: 0.3
       `category` parameter added.

    :param message: the message to be flashed.
    :param category: the category for the message.  The following values
                     are recommended: ``'message'`` for any kind of message,
                     ``'error'`` for errors, ``'info'`` for information
                     messages and ``'warning'`` for warnings.  However any
                     kind of string can be used as category.
    """
    # Original implementation:
    #
    #     session.setdefault('_flashes', []).append((category, message))
    #
    # This assumed that changes made to mutable structures in the session are
    # always in sync with the session object, which is not true for session
    # implementations that use external storage for keeping their keys/values.
    flashes = session.get("_flashes", [])
    flashes.append((category, message))
    session["_flashes"] = flashes
    app = current_app._get_current_object()  # type: ignore
    message_flashed.send(
        app,
        _async_wrapper=app.ensure_sync,
        message=message,
        category=category,
    )


def get_flashed_messages(
    with_categories: bool = False, category_filter: t.Iterable[str] = ()
) -> list[str] | list[tuple[str, str]]:
    """Pulls all flashed messages from the session and returns them.
    Further calls in the same request to the function will return
    the same messages.  By default just the messages are returned,
    but when `with_categories` is set to ``True``, the return value will
    be a list of tuples in the form ``(category, message)`` instead.

    Filter the flashed messages to one or more categories by providing those
    categories in `category_filter`.  This allows rendering categories in
    separate html blocks.  The `with_categories` and `category_filter`
    arguments are distinct:

    * `with_categories` controls whether categories are returned with message
      text (``True`` gives a tuple, where ``False`` gives just the message text).
    * `category_filter` filters the messages down to only those matching the
      provided categories.

    See :doc:`/patterns/flashing` for examples.

    .. versionchanged:: 0.3
       `with_categories` parameter added.

    .. versionchanged:: 0.9
        `category_filter` parameter added.

    :param with_categories: set to ``True`` to also receive categories.
    :param category_filter: filter of categories to limit return values.  Only
                            categories in the list will be returned.
    """
    flashes = request_ctx.flashes
    if flashes is None:
        flashes = session.pop("_flashes") if "_flashes" in session else []
        request_ctx.flashes = flashes
    if category_filter:
        flashes = list(filter(lambda f: f[0] in category_filter, flashes))
    if not with_categories:
        return [x[1] for x in flashes]
    return flashes


def _prepare_send_file_kwargs(**kwargs: t.Any) -> dict[str, t.Any]:
    if kwargs.get("max_age") is None:
        kwargs["max_age"] = current_app.get_send_file_max_age

    kwargs.update(
        environ=request.environ,
        use_x_sendfile=current_app.config["USE_X_SENDFILE"],
        response_class=current_app.response_class,
        _root_path=current_app.root_path,
    )
    return kwargs


def send_file(
    path_or_file: os.PathLike[t.AnyStr] | str | t.IO[bytes],
    mimetype: str | None = None,
    as_attachment: bool = False,
    download_name: str | None = None,
    conditional: bool = True,
    etag: bool | str = True,
    last_modified: datetime | int | float | None = None,
    max_age: None | (int | t.Callable[[str | None], int | None]) = None,
) -> Response:
    """Send the contents of a file to the client.

    The first argument can be a file path or a file-like object. Paths
    are preferred in most cases because Werkzeug can manage the file and
    get extra information from the path. Passing a file-like object
    requires that the file is opened in binary mode, and is mostly
    useful when building a file in memory with :class:`io.BytesIO`.

    Never pass file paths provided by a user. The path is assumed to be
    trusted, so a user could craft a path to access a file you didn't
    intend. Use :func:`send_from_directory` to safely serve
    user-requested paths from within a directory.

    If the WSGI server sets a ``file_wrapper`` in ``environ``, it is
    used, otherwise Werkzeug's built-in wrapper is used. Alternatively,
    if the HTTP server supports ``X-Sendfile``, configuring Flask with
    ``USE_X_SENDFILE = True`` will tell the server to send the given
    path, which is much more efficient than reading it in Python.

    :param path_or_file: The path to the file to send, relative to the
        current working directory if a relative path is given.
        Alternatively, a file-like object opened in binary mode. Make
        sure the file pointer is seeked to the start of the data.
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

    .. versionchanged:: 2.0
        ``download_name`` replaces the ``attachment_filename``
        parameter. If ``as_attachment=False``, it is passed with
        ``Content-Disposition: inline`` instead.

    .. versionchanged:: 2.0
        ``max_age`` replaces the ``cache_timeout`` parameter.
        ``conditional`` is enabled and ``max_age`` is not set by
        default.

    .. versionchanged:: 2.0
        ``etag`` replaces the ``add_etags`` parameter. It can be a
        string to use instead of generating one.

    .. versionchanged:: 2.0
        Passing a file-like object that inherits from
        :class:`~io.TextIOBase` will raise a :exc:`ValueError` rather
        than sending an empty file.

    .. versionadded:: 2.0
        Moved the implementation to Werkzeug. This is now a wrapper to
        pass some Flask-specific arguments.

    .. versionchanged:: 1.1
        ``filename`` may be a :class:`~os.PathLike` object.

    .. versionchanged:: 1.1
        Passing a :class:`~io.BytesIO` object supports range requests.

    .. versionchanged:: 1.0.3
        Filenames are encoded with ASCII instead of Latin-1 for broader
        compatibility with WSGI servers.

    .. versionchanged:: 1.0
        UTF-8 filenames as specified in :rfc:`2231` are supported.

    .. versionchanged:: 0.12
        The filename is no longer automatically inferred from file
        objects. If you want to use automatic MIME and etag support,
        pass a filename via ``filename_or_fp`` or
        ``attachment_filename``.

    .. versionchanged:: 0.12
        ``attachment_filename`` is preferred over ``filename`` for MIME
        detection.

    .. versionchanged:: 0.9
        ``cache_timeout`` defaults to
        :meth:`Flask.get_send_file_max_age`.

    .. versionchanged:: 0.7
        MIME guessing and etag support for file-like objects was
        removed because it was unreliable. Pass a filename if you are
        able to, otherwise attach an etag yourself.

    .. versionchanged:: 0.5
        The ``add_etags``, ``cache_timeout`` and ``conditional``
        parameters were added. The default behavior is to add etags.

    .. versionadded:: 0.2
    """
    return werkzeug.utils.send_file(  # type: ignore[return-value]
        **_prepare_send_file_kwargs(
            path_or_file=path_or_file,
            environ=request.environ,
            mimetype=mimetype,
            as_attachment=as_attachment,
            download_name=download_name,
            conditional=conditional,
            etag=etag,
            last_modified=last_modified,
            max_age=max_age,
        )
    )


def send_from_directory(
    directory: os.PathLike[str] | str,
    path: os.PathLike[str] | str,
    **kwargs: t.Any,
) -> Response:
    """Send a file from within a directory using :func:`send_file`.

    .. code-block:: python

        @app.route("/uploads/<path:name>")
        def download_file(name):
            return send_from_directory(
                app.config['UPLOAD_FOLDER'], name, as_attachment=True
            )

    This is a secure way to serve files from a folder, such as static
    files or uploads. Uses :func:`~werkzeug.security.safe_join` to
    ensure the path coming from the client is not maliciously crafted to
    point outside the specified directory.

    If the final path does not point to an existing regular file,
    raises a 404 :exc:`~werkzeug.exceptions.NotFound` error.

    :param directory: The directory that ``path`` must be located under,
        relative to the current application's root path. This *must not*
        be a value provided by the client, otherwise it becomes insecure.
    :param path: The path to the file to send, relative to
        ``directory``.
    :param kwargs: Arguments to pass to :func:`send_file`.

    .. versionchanged:: 2.0
        ``path`` replaces the ``filename`` parameter.

    .. versionadded:: 2.0
        Moved the implementation to Werkzeug. This is now a wrapper to
        pass some Flask-specific arguments.

    .. versionadded:: 0.5
    """
    return werkzeug.utils.send_from_directory(  # type: ignore[return-value]
        directory, path, **_prepare_send_file_kwargs(**kwargs)
    )


def get_root_path(import_name: str) -> str:
    """Find the root path of a package, or the path that contains a
    module. If it cannot be found, returns the current working
    directory.

    Not to be confused with the value returned by :func:`find_package`.

    :meta private:
    """
    # Module already imported and has a file attribute. Use that first.
    mod = sys.modules.get(import_name)

    if mod is not None and hasattr(mod, "__file__") and mod.__file__ is not None:
        return os.path.dirname(os.path.abspath(mod.__file__))

    # Next attempt: check the loader.
    try:
        spec = importlib.util.find_spec(import_name)

        if spec is None:
            raise ValueError
    except (ImportError, ValueError):
        loader = None
    else:
        loader = spec.loader

    # Loader does not exist or we're referring to an unloaded main
    # module or a main module without path (interactive sessions), go
    # with the current working directory.
    if loader is None:
        return os.getcwd()

    if hasattr(loader, "get_filename"):
        filepath = loader.get_filename(import_name)  # pyright: ignore
    else:
        # Fall back to imports.
        __import__(import_name)
        mod = sys.modules[import_name]
        filepath = getattr(mod, "__file__", None)

        # If we don't have a file path it might be because it is a
        # namespace package. In this case pick the root path from the
        # first module that is contained in the package.
        if filepath is None:
            raise RuntimeError(
                "No root path can be found for the provided module"
                f" {import_name!r}. This can happen because the module"
                " came from an import hook that does not provide file"
                " name information or because it's a namespace package."
                " In this case the root path needs to be explicitly"
                " provided."
            )

    # filepath is import_name.py for a module, or __init__.py for a package.
    return os.path.dirname(os.path.abspath(filepath))  # type: ignore[no-any-return]


@cache
def _split_blueprint_path(name: str) -> list[str]:
    out: list[str] = [name]

    if "." in name:
        out.extend(_split_blueprint_path(name.rpartition(".")[0]))

    return out
