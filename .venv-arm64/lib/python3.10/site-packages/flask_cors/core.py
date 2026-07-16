from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, TypedDict, Union, cast

from flask import Blueprint, Flask, Response, current_app, request
from werkzeug.datastructures import Headers, MultiDict

LOG = logging.getLogger(__name__)

# A resource/origin/header pattern may either be a literal string or a
# pre-compiled regular expression.
ResourcePattern = Union[str, "re.Pattern[str]"]

# What a user may pass as ``resources``: a single pattern, a list of patterns,
# or a mapping of pattern -> per-resource (raw) options.
ResourceSpec = Union[
    str,
    "re.Pattern[str]",
    "list[ResourcePattern]",
    "dict[ResourcePattern, dict[str, Any]]",
]

# Input shapes accepted from users for individual options, before they are
# normalized by :func:`serialize_options`. These are deliberately broad: a
# scalar or an iterable of scalars are both accepted in most cases.
OriginsInput = Union[ResourcePattern, "Iterable[ResourcePattern]"]
HeadersInput = Union[ResourcePattern, "Iterable[ResourcePattern]"]
MethodsInput = Union[str, "Iterable[str]"]
ExposeHeadersInput = Union[str, "Iterable[str]", None]
MaxAgeInput = Union[timedelta, int, str, None]


@dataclass(frozen=True)
class _ComputedCorsOptions:
    """The fully-resolved CORS options for a single route.

    Private internal representation, built only by :func:`serialize_options`.
    Configure CORS via :class:`~flask_cors.CORS` / :func:`cross_origin` keyword
    arguments, not by constructing this directly.
    """

    # ``origins``/``allow_headers`` are normalized to a list of patterns: each
    # entry is either a compiled ``re.Pattern`` (regex) or a literal ``str``,
    # so request-time matching never has to guess which it is.
    origins: list[ResourcePattern]
    allow_headers: list[ResourcePattern]
    # Whether ``origins`` includes the catch-all ``.*`` wildcard. Computed once
    # here because the wildcard is otherwise indistinguishable from a regex
    # after the origins have been compiled.
    allow_all_origins: bool
    # ``methods``/``expose_headers`` join to a comma-separated string, or are
    # ``None`` when not configured.
    methods: str | None
    expose_headers: str | None
    # ``max_age`` is left as-is unless a timedelta is given, then stringified.
    max_age: str | int | None
    supports_credentials: bool
    send_wildcard: bool
    automatic_options: bool
    vary_header: bool
    intercept_exceptions: bool
    always_send: bool
    allow_private_network: bool


class CrossOriginOptionsInput(TypedDict, total=False):
    """The keyword options accepted by :func:`cross_origin`.

    Every key is optional (``total=False``): only the options a caller
    actually passes are forwarded, so app-level ``CORS_*`` configuration and
    the defaults still apply to anything left out. Used with PEP 692
    ``Unpack`` to type ``**kwargs`` precisely.
    """

    origins: OriginsInput
    methods: MethodsInput
    expose_headers: ExposeHeadersInput
    allow_headers: HeadersInput
    supports_credentials: bool
    max_age: MaxAgeInput
    send_wildcard: bool
    vary_header: bool
    automatic_options: bool
    always_send: bool
    allow_private_network: bool


class CorsOptionsInput(CrossOriginOptionsInput, total=False):
    """The keyword options accepted by :class:`CORS` / :meth:`CORS.init_app`.

    Extends :class:`CrossOriginOptionsInput` with the application-level options that
    only make sense for the extension.
    """

    resources: ResourceSpec
    intercept_exceptions: bool


# Response Headers
ACL_ORIGIN = "Access-Control-Allow-Origin"
ACL_METHODS = "Access-Control-Allow-Methods"
ACL_ALLOW_HEADERS = "Access-Control-Allow-Headers"
ACL_EXPOSE_HEADERS = "Access-Control-Expose-Headers"
ACL_CREDENTIALS = "Access-Control-Allow-Credentials"
ACL_MAX_AGE = "Access-Control-Max-Age"
ACL_RESPONSE_PRIVATE_NETWORK = "Access-Control-Allow-Private-Network"

# Request Header
ACL_REQUEST_METHOD = "Access-Control-Request-Method"
ACL_REQUEST_HEADERS = "Access-Control-Request-Headers"
ACL_REQUEST_HEADER_PRIVATE_NETWORK = "Access-Control-Request-Private-Network"

ALL_METHODS = ["GET", "HEAD", "POST", "OPTIONS", "PUT", "PATCH", "DELETE"]
CONFIG_OPTIONS = [
    "CORS_ORIGINS",
    "CORS_METHODS",
    "CORS_ALLOW_HEADERS",
    "CORS_EXPOSE_HEADERS",
    "CORS_SUPPORTS_CREDENTIALS",
    "CORS_MAX_AGE",
    "CORS_SEND_WILDCARD",
    "CORS_AUTOMATIC_OPTIONS",
    "CORS_VARY_HEADER",
    "CORS_RESOURCES",
    "CORS_INTERCEPT_EXCEPTIONS",
    "CORS_ALWAYS_SEND",
    "CORS_ALLOW_PRIVATE_NETWORK",
]
# Attribute added to request object by decorator to indicate that CORS
# was evaluated, in case the decorator and extension are both applied
# to a view.
FLASK_CORS_EVALUATED = "_FLASK_CORS_EVALUATED"

# The type of a compiled regular expression. Exposed publicly as
# ``re.Pattern`` since Python 3.8.
RegexObject = re.Pattern

# Characters commonly found in regular expressions. Their presence is used as
# a heuristic for whether a string is a regex rather than a literal value.
_REGEX_HINT_CHARS = frozenset("*\\]?$^[]()")

# The set of recognized option names, derived from the input schema (which
# lists exactly the keys a user may pass; the resolved dataclass additionally
# carries computed fields such as ``allow_all_origins``).
_KNOWN_OPTIONS = frozenset(CorsOptionsInput.__required_keys__) | frozenset(CorsOptionsInput.__optional_keys__)

# The raw, un-normalized option defaults. These are merged with app config and
# user kwargs before being handed to :func:`serialize_options`, which produces
# the strongly-typed :class:`_ComputedCorsOptions`. Typing this as ``CorsOptionsInput``
# lets mypy verify the defaults match the documented input schema.
DEFAULT_OPTIONS: CorsOptionsInput = {
    "origins": "*",
    "methods": ALL_METHODS,
    "allow_headers": "*",
    "expose_headers": None,
    "supports_credentials": False,
    "max_age": None,
    "send_wildcard": False,
    "automatic_options": True,
    "vary_header": True,
    "resources": r"/*",
    "intercept_exceptions": True,
    "always_send": True,
    "allow_private_network": False,
}


def parse_resources(resources: ResourceSpec) -> list[tuple[ResourcePattern, dict[str, Any]]]:
    if isinstance(resources, dict):
        # To make the API more consistent with the decorator, allow a
        # resource of '*', which is not actually a valid regexp.
        resource_pairs = [(re_fix(k), v) for k, v in resources.items()]

        # Sort patterns with static (literal) paths first, then by regex specificity
        def sort_key(pair: tuple[ResourcePattern, Any]) -> tuple[int, int, int, int]:
            pattern, _ = pair
            if isinstance(pattern, re.Pattern):
                return (1, 0, -pattern.pattern.count("/"), -len(pattern.pattern))
            elif probably_regex(pattern):
                return (1, 1, -pattern.count("/"), -len(pattern))
            else:
                return (0, 0, -pattern.count("/"), -len(pattern))

        resource_pairs.sort(key=sort_key)

    elif isinstance(resources, str):
        resource_pairs = [(re_fix(resources), {})]

    elif isinstance(resources, Iterable):
        resource_pairs = [(re_fix(r), {}) for r in resources]

    # Type of compiled regex is not part of the public API. Test for this
    # at runtime.
    elif isinstance(resources, re.Pattern):
        resource_pairs = [(re_fix(resources), {})]

    else:
        # ValueError (rather than the arguably more correct TypeError) is the
        # historical public contract here; callers may catch it.
        raise ValueError("Unexpected value for resources argument.")  # noqa: TRY004

    # Resolve each path pattern once (paths are matched case-sensitively), so
    # request handling never re-runs the regex heuristic. Patterns are sorted
    # above, before compilation, so specificity ordering is preserved.
    return [(_resolve_pattern(pattern, ignore_case=False), opts) for (pattern, opts) in resource_pairs]


def get_regexp_pattern(regexp: ResourcePattern) -> str:
    """
    Helper that returns regexp pattern from given value.

    :param regexp: regular expression to stringify
    :type regexp: re.Pattern or str
    :returns: string representation of given regexp pattern
    :rtype: str
    """
    if isinstance(regexp, re.Pattern):
        return regexp.pattern
    return str(regexp)


def get_cors_origins(options: _ComputedCorsOptions, request_origin: str | None) -> list[str] | None:
    origins = options.origins
    wildcard = options.allow_all_origins

    # If the Origin header is not present terminate this set of steps.
    # The request is outside the scope of this specification.-- W3Spec
    if request_origin:
        LOG.debug("CORS request received with 'Origin' %s", request_origin)

        # If the allowed origins is an asterisk or 'wildcard', always match
        if wildcard and options.send_wildcard:
            LOG.debug("Allowed origins are set to '*'. Sending wildcard CORS header.")
            return ["*"]
        # If the value of the Origin header is a case-insensitive match
        # for any of the values in list of origins.
        # NOTE: Per RFC 1035 and RFC 4343 schemes and hostnames are case insensitive.
        elif try_match_any_pattern(request_origin, origins, caseSensitive=False):
            LOG.debug(
                "The request's Origin header matches. Sending CORS headers.",
            )
            # Add a single Access-Control-Allow-Origin header, with either
            # the value of the Origin header or the string "*" as value.
            # -- W3Spec
            return [request_origin]
        else:
            LOG.debug("The request's Origin header does not match any of allowed origins.")
            return None

    elif options.always_send:
        if wildcard:
            # If wildcard is in the origins, even if 'send_wildcard' is False,
            # simply send the wildcard. Unless supports_credentials is True,
            # since that is forbidden by the spec..
            # It is the most-likely to be correct thing to do (the only other
            # option is to return nothing, which  almost certainly not what
            # the developer wants if the '*' origin was specified.
            if options.supports_credentials:
                return None
            else:
                return ["*"]
        else:
            # Return all literal (non-regex) origins. After resolution a plain
            # ``str`` entry is always a literal; regexes are compiled patterns.
            return sorted(o for o in origins if isinstance(o, str))

    # Terminate these steps, return the original request untouched.
    else:
        LOG.debug(
            "The request did not contain an 'Origin' header. This means the browser or client did not request CORS, ensure the Origin Header is set."
        )
        return None


def get_allow_headers(options: _ComputedCorsOptions, acl_request_headers: str | None) -> str | None:
    if acl_request_headers:
        allow_headers = options.allow_headers
        request_headers = [h.strip() for h in acl_request_headers.split(",")]

        # any header that matches in the allow_headers
        matching_headers = filter(
            lambda h: try_match_any_pattern(h, allow_headers, caseSensitive=False),
            request_headers,
        )

        return ", ".join(sorted(matching_headers))

    return None


def get_cors_headers(
    options: _ComputedCorsOptions, request_headers: Headers, request_method: str
) -> MultiDict[str, str | int | None]:
    origins_to_set = get_cors_origins(options, request_headers.get("Origin"))
    # Values are header values (str), with ``max_age`` allowing int and a few
    # options allowing None; the trailing comprehension drops the None/empty
    # entries before the result is returned.
    headers: MultiDict[str, str | int | None] = MultiDict()

    if not origins_to_set:  # CORS is not enabled for this route
        return headers

    headers.setlist(ACL_ORIGIN, origins_to_set)

    headers[ACL_EXPOSE_HEADERS] = options.expose_headers

    if options.supports_credentials:
        headers[ACL_CREDENTIALS] = "true"  # case sensitive

    if (
        ACL_REQUEST_HEADER_PRIVATE_NETWORK in request_headers
        and request_headers.get(ACL_REQUEST_HEADER_PRIVATE_NETWORK) == "true"
    ):
        allow_private_network = "true" if options.allow_private_network else "false"
        headers[ACL_RESPONSE_PRIVATE_NETWORK] = allow_private_network

    # This is a preflight request
    # http://www.w3.org/TR/cors/#resource-preflight-requests
    if request_method == "OPTIONS":
        acl_request_method = request_headers.get(ACL_REQUEST_METHOD, "").upper()

        # If there is no Access-Control-Request-Method header or if parsing
        # failed, do not set any additional headers
        methods = options.methods
        if acl_request_method and methods and acl_request_method in methods:
            # If method is not a case-sensitive match for any of the values in
            # list of methods do not set any additional headers and terminate
            # this set of steps.
            headers[ACL_ALLOW_HEADERS] = get_allow_headers(options, request_headers.get(ACL_REQUEST_HEADERS))
            headers[ACL_MAX_AGE] = options.max_age
            headers[ACL_METHODS] = methods
        else:
            LOG.info(
                "The request's Access-Control-Request-Method header does not match allowed methods. CORS headers will not be applied."
            )

    # http://www.w3.org/TR/cors/#resource-implementation
    if options.vary_header:
        # Only set the header if the resolved origin can vary dynamically:
        # i.e. we are not returning a wildcard, and more than one origin (or a
        # regex) could have matched.
        origins = options.origins
        returns_wildcard = headers[ACL_ORIGIN] == "*"
        if not returns_wildcard and (
            len(origins) > 1 or len(origins_to_set) > 1 or any(isinstance(o, re.Pattern) for o in origins)
        ):
            headers.add("Vary", "Origin")

    return MultiDict((k, v) for k, v in headers.items() if v)


def set_cors_headers(resp: Response, options: _ComputedCorsOptions) -> Response:
    """
    Performs the actual evaluation of Flask-CORS options and actually
    modifies the response object.

    This function is used both in the decorator and the after_request
    callback
    """

    # If CORS has already been evaluated via the decorator, skip
    if hasattr(resp, FLASK_CORS_EVALUATED):
        LOG.debug("CORS have been already evaluated, skipping")
        return resp

    # Some libraries, like OAuthlib, set resp.headers to non Multidict
    # objects (Werkzeug Headers work as well). This is a problem because
    # headers allow repeated values.
    if not isinstance(resp.headers, Headers) and not isinstance(resp.headers, MultiDict):
        # The non-standard header container is replaced with a MultiDict so
        # repeated headers behave consistently.
        resp.headers = MultiDict(resp.headers)

    headers_to_set = get_cors_headers(options, request.headers, request.method)

    LOG.debug("Settings CORS headers: %s", str(headers_to_set))

    for k, v in headers_to_set.items():
        resp.headers.add(k, v)

    return resp


def probably_regex(maybe_regex: ResourcePattern) -> bool:
    if isinstance(maybe_regex, re.Pattern):
        return True

    # Use characters common in regular expressions as a proxy for whether
    # this string is in fact a regex.
    return not _REGEX_HINT_CHARS.isdisjoint(maybe_regex)


def re_fix(reg: ResourcePattern) -> ResourcePattern:
    """
    Replace the invalid regex r'*' with the valid, wildcard regex r'/.*' to
    enable the CORS app extension to have a more user friendly api.
    """
    return r".*" if reg == r"*" else reg


def try_match_any_pattern(inst: str, patterns: Iterable[ResourcePattern], caseSensitive: bool = True) -> bool:
    return any(try_match_pattern(inst, pattern, caseSensitive) for pattern in patterns)


def try_match_pattern(value: Any, pattern: ResourcePattern, caseSensitive: bool = True) -> bool:
    """
    Match a value against a *resolved* pattern: a compiled ``re.Pattern``
    (whose case-sensitivity is already baked in) or a literal string. Used to
    match request origins, headers, or paths; ``caseSensitive`` only affects
    the literal comparison (origins and headers are case insensitive, paths are
    case sensitive).
    """
    if isinstance(pattern, re.Pattern):
        return bool(pattern.match(value))
    try:
        v = str(value)
        p = str(pattern)
    except Exception:
        return bool(value == pattern)
    return v == p if caseSensitive else v.casefold() == p.casefold()


def merge_options(appInstance: Flask | Blueprint | None, *dicts: Mapping[str, Any]) -> dict[str, Any]:
    """
    Merge the DEFAULT_OPTIONS, the app's configuration-specified options and any
    dictionaries passed into a single raw options mapping. The last specified
    option wins.
    """
    options: dict[str, Any] = dict(DEFAULT_OPTIONS)
    options.update(get_app_kwarg_dict(appInstance))
    for d in dicts:
        options.update(d)
    return options


def get_cors_options(appInstance: Flask | Blueprint | None, *dicts: Mapping[str, Any]) -> _ComputedCorsOptions:
    """Compute the resolved CORS options for an application (see merge_options)."""
    return serialize_options(merge_options(appInstance, *dicts))


def get_app_kwarg_dict(appInstance: Flask | Blueprint | None = None) -> dict[str, Any]:
    """Returns the dictionary of CORS specific app configurations."""
    app = appInstance or current_app

    # In order to support blueprints which do not have a config attribute
    app_config = getattr(app, "config", {})

    return {k.lower().replace("cors_", ""): value for k in CONFIG_OPTIONS if (value := app_config.get(k)) is not None}


def flexible_str(obj: Any) -> str | None:
    """
    A more flexible str function which intelligently handles stringifying
    strings, lists and other iterables. The results are lexographically sorted
    to ensure generated responses are consistent when iterables such as Set
    are used.
    """
    if obj is None:
        return None
    elif not isinstance(obj, str) and isinstance(obj, Iterable):
        return ", ".join(str(item) for item in sorted(obj))
    else:
        return str(obj)


def ensure_iterable(inst: Any) -> Iterable[Any]:
    """
    Wraps scalars or string types as a list, or returns the iterable instance.
    """
    if isinstance(inst, str) or not isinstance(inst, Iterable):
        return [inst]
    else:
        return cast("Iterable[Any]", inst)


def sanitize_regex_param(param: Any) -> list[ResourcePattern]:
    return [re_fix(x) for x in ensure_iterable(param)]


def _resolve_pattern(pattern: ResourcePattern, *, ignore_case: bool) -> ResourcePattern:
    """Resolve a single raw pattern once, at configuration time.

    A regex-like string is compiled to a ``re.Pattern`` (with the correct
    case-sensitivity baked in); a literal string and an already-compiled
    pattern are returned unchanged. An invalid regular expression raises a
    ``ValueError`` so the misconfiguration fails fast at setup time rather than
    silently never matching.
    """
    if isinstance(pattern, str) and probably_regex(pattern):
        try:
            return re.compile(pattern, re.IGNORECASE if ignore_case else 0)
        except re.error as exc:
            raise ValueError(f"Invalid regular expression in Flask-CORS configuration: {pattern!r}") from exc
    return pattern


def _resolve_patterns(patterns: Iterable[ResourcePattern], *, ignore_case: bool) -> list[ResourcePattern]:
    """Resolve a list of patterns (see :func:`_resolve_pattern`).

    After this, the request path can simply test ``isinstance(p, re.Pattern)``
    instead of re-running the :func:`probably_regex` heuristic on every request.
    """
    return [_resolve_pattern(p, ignore_case=ignore_case) for p in patterns]


def serialize_options(opts: Mapping[str, Any]) -> _ComputedCorsOptions:
    """
    Normalize a raw options mapping into a strongly-typed :class:`_ComputedCorsOptions`.

    This is the single boundary where loosely-typed user input (arbitrary
    keyword arguments, app config, resource dictionaries) is parsed into the
    concrete, per-field types the rest of the package relies on.
    """
    for key in opts:
        if key not in _KNOWN_OPTIONS:
            LOG.warning("Unknown option passed to Flask-CORS: %s", key)

    # Ensure origins is a list of allowed origins with at least one entry. The
    # wildcard is detected before the patterns are compiled (afterwards ``.*``
    # is just another compiled regex, indistinguishable from a real one).
    sanitized_origins = sanitize_regex_param(opts.get("origins"))
    allow_all_origins = r".*" in sanitized_origins
    supports_credentials = bool(opts.get("supports_credentials"))
    send_wildcard = bool(opts.get("send_wildcard"))

    # This is expressly forbidden by the spec. Raise a value error so people
    # don't get burned in production.
    if allow_all_origins and supports_credentials and send_wildcard:
        raise ValueError(
            "Cannot use supports_credentials in conjunction with"
            "an origin string of '*'. See: "
            "http://www.w3.org/TR/cors/#resource-requests"
        )

    origins = _resolve_patterns(sanitized_origins, ignore_case=True)
    allow_headers = _resolve_patterns(sanitize_regex_param(opts.get("allow_headers")), ignore_case=True)

    methods = flexible_str(opts.get("methods"))
    if methods is not None:
        methods = methods.upper()

    max_age = opts.get("max_age")
    if isinstance(max_age, timedelta):
        max_age = str(int(max_age.total_seconds()))

    return _ComputedCorsOptions(
        origins=origins,
        allow_headers=allow_headers,
        allow_all_origins=allow_all_origins,
        methods=methods,
        expose_headers=flexible_str(opts.get("expose_headers")),
        max_age=max_age,
        supports_credentials=supports_credentials,
        send_wildcard=send_wildcard,
        automatic_options=bool(opts.get("automatic_options")),
        vary_header=bool(opts.get("vary_header")),
        intercept_exceptions=bool(opts.get("intercept_exceptions")),
        always_send=bool(opts.get("always_send")),
        allow_private_network=bool(opts.get("allow_private_network")),
    )
