from __future__ import annotations

import collections.abc as cabc
import typing as t

if t.TYPE_CHECKING:  # pragma: no cover
    from _typeshed.wsgi import WSGIApplication  # noqa: F401
    from werkzeug.datastructures import Headers  # noqa: F401
    from werkzeug.sansio.response import Response  # noqa: F401

# The possible types that are directly convertible or are a Response object.
ResponseValue = t.Union[
    "Response",
    str,
    bytes,
    list[t.Any],
    # Only dict is actually accepted, but Mapping allows for TypedDict.
    t.Mapping[str, t.Any],
    t.Iterator[str],
    t.Iterator[bytes],
    cabc.AsyncIterable[str],  # for Quart, until App is generic.
    cabc.AsyncIterable[bytes],
]

# the possible types for an individual HTTP header
# This should be a Union, but mypy doesn't pass unless it's a TypeVar.
HeaderValue = t.Union[str, list[str], tuple[str, ...]]

# the possible types for HTTP headers
HeadersValue = t.Union[
    "Headers",
    t.Mapping[str, HeaderValue],
    t.Sequence[tuple[str, HeaderValue]],
]

# The possible types returned by a route function.
ResponseReturnValue = t.Union[
    ResponseValue,
    tuple[ResponseValue, HeadersValue],
    tuple[ResponseValue, int],
    tuple[ResponseValue, int, HeadersValue],
    "WSGIApplication",
]

# Allow any subclass of werkzeug.Response, such as the one from Flask,
# as a callback argument. Using werkzeug.Response directly makes a
# callback annotated with flask.Response fail type checking.
ResponseClass = t.TypeVar("ResponseClass", bound="Response")

AppOrBlueprintKey = t.Optional[str]  # The App key is None, whereas blueprints are named
AfterRequestCallable = t.Union[
    t.Callable[[ResponseClass], ResponseClass],
    t.Callable[[ResponseClass], t.Awaitable[ResponseClass]],
]
BeforeFirstRequestCallable = t.Union[
    t.Callable[[], None], t.Callable[[], t.Awaitable[None]]
]
BeforeRequestCallable = t.Union[
    t.Callable[[], t.Optional[ResponseReturnValue]],
    t.Callable[[], t.Awaitable[t.Optional[ResponseReturnValue]]],
]
ShellContextProcessorCallable = t.Callable[[], dict[str, t.Any]]
TeardownCallable = t.Union[
    t.Callable[[t.Optional[BaseException]], None],
    t.Callable[[t.Optional[BaseException]], t.Awaitable[None]],
]
TemplateContextProcessorCallable = t.Union[
    t.Callable[[], dict[str, t.Any]],
    t.Callable[[], t.Awaitable[dict[str, t.Any]]],
]
TemplateFilterCallable = t.Callable[..., t.Any]
TemplateGlobalCallable = t.Callable[..., t.Any]
TemplateTestCallable = t.Callable[..., bool]
URLDefaultCallable = t.Callable[[str, dict[str, t.Any]], None]
URLValuePreprocessorCallable = t.Callable[
    [t.Optional[str], t.Optional[dict[str, t.Any]]], None
]

# This should take Exception, but that either breaks typing the argument
# with a specific exception, or decorating multiple times with different
# exceptions (and using a union type on the argument).
# https://github.com/pallets/flask/issues/4095
# https://github.com/pallets/flask/issues/4295
# https://github.com/pallets/flask/issues/4297
ErrorHandlerCallable = t.Union[
    t.Callable[[t.Any], ResponseReturnValue],
    t.Callable[[t.Any], t.Awaitable[ResponseReturnValue]],
]

RouteCallable = t.Union[
    t.Callable[..., ResponseReturnValue],
    t.Callable[..., t.Awaitable[ResponseReturnValue]],
]
