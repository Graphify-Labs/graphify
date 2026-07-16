from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote

from flask import Blueprint, Flask, Response, request

from .core import (
    ACL_ORIGIN,
    CorsOptionsInput,
    ResourcePattern,
    _ComputedCorsOptions,
    get_cors_options,
    get_regexp_pattern,
    merge_options,
    parse_resources,
    serialize_options,
    set_cors_headers,
    try_match_pattern,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from typing_extensions import Unpack

LOG = logging.getLogger(__name__)


class CORS:
    """
    Initializes Cross Origin Resource sharing for the application. The
    arguments are identical to `cross_origin`, with the addition of a
    `resources` parameter. The resources parameter defines a series of regular
    expressions for resource paths to match and optionally, the associated
    options to be applied to the particular resource. These options are
    identical to the arguments to `cross_origin`.

    The settings for CORS are determined in the following order

    1. Resource level settings (e.g when passed as a dictionary)
    2. Keyword argument settings
    3. App level configuration settings (e.g. CORS_*)
    4. Default settings

    Note: as it is possible for multiple regular expressions to match a
    resource path, the regular expressions are first sorted by length,
    from longest to shortest, in order to attempt to match the most
    specific regular expression. This allows the definition of a
    number of specific resource options, with a wildcard fallback
    for all other resources.

    :param resources:
        The series of regular expression and (optionally) associated CORS
        options to be applied to the given resource path.

        If the argument is a dictionary, it's keys must be regular expressions,
        and the values must be a dictionary of kwargs, identical to the kwargs
        of this function.

        If the argument is a list, it is expected to be a list of regular
        expressions, for which the app-wide configured options are applied.

        If the argument is a string, it is expected to be a regular expression
        for which the app-wide configured options are applied.

        Default : Match all and apply app-level configuration

    :type resources: dict, iterable or string

    :param origins:
        The origin, or list of origins to allow requests from.
        The origin(s) may be regular expressions, case-sensitive strings,
        or else an asterisk.

        ..  note::

            origins must include the schema and the port (if not port 80),
            e.g.,
            `CORS(app, origins=["http://localhost:8000", "https://example.com"])`.

        Default : '*'
    :type origins: list, string or regex

    :param methods:
        The method or list of methods which the allowed origins are allowed to
        access for non-simple requests.

        Default : [GET, HEAD, POST, OPTIONS, PUT, PATCH, DELETE]
    :type methods: list or string

    :param expose_headers:
        The header or list which are safe to expose to the API of a CORS API
        specification.

        Default : None
    :type expose_headers: list or string

    :param allow_headers:
        The header or list of header field names which can be used when this
        resource is accessed by allowed origins. The header(s) may be regular
        expressions, case-sensitive strings, or else an asterisk.

        Default : '*', allow all headers
    :type allow_headers: list, string or regex

    :param supports_credentials:
        Allows users to make authenticated requests. If true, injects the
        `Access-Control-Allow-Credentials` header in responses. This allows
        cookies and credentials to be submitted across domains.

        :note: This option cannot be used in conjunction with a '*' origin

        Default : False
    :type supports_credentials: bool

    :param max_age:
        The maximum time for which this CORS request maybe cached. This value
        is set as the `Access-Control-Max-Age` header.

        Default : None
    :type max_age: timedelta, integer, string or None

    :param send_wildcard: If True, and the origins parameter is `*`, a wildcard
        `Access-Control-Allow-Origin` header is sent, rather than the
        request's `Origin` header.

        Default : False
    :type send_wildcard: bool

    :param vary_header:
        If True, the header Vary: Origin will be returned as per the W3
        implementation guidelines.

        Setting this header when the `Access-Control-Allow-Origin` is
        dynamically generated (e.g. when there is more than one allowed
        origin, and an Origin than '*' is returned) informs CDNs and other
        caches that the CORS headers are dynamic, and cannot be cached.

        If False, the Vary header will never be injected or altered.

        Default : True
    :type vary_header: bool

    :param allow_private_network:
        If True, the response header `Access-Control-Allow-Private-Network`
        will be set with the value 'true' whenever the request header
        `Access-Control-Request-Private-Network` has a value 'true'.

        If False, the response header `Access-Control-Allow-Private-Network`
        will be set with the value 'false' whenever the request header
        `Access-Control-Request-Private-Network` has a value of 'true'.

        If the request header `Access-Control-Request-Private-Network` is
        not present or has a value other than 'true', the response header
        `Access-Control-Allow-Private-Network` will not be set.

        Default : True
    :type allow_private_network: bool
    """

    def __init__(self, app: Flask | Blueprint | None = None, **kwargs: Unpack[CorsOptionsInput]) -> None:
        self._options = kwargs
        if app is not None:
            self.init_app(app, **kwargs)

    def init_app(self, app: Flask | Blueprint, **kwargs: Unpack[CorsOptionsInput]) -> None:
        # The resources and options may be specified in the App Config, the CORS constructor
        # or the kwargs to the call to init_app.
        merged = merge_options(app, self._options, kwargs)
        options = serialize_options(merged)

        # Flatten our resources into a list of the form
        # (pattern_or_regexp, dictionary_of_raw_options). ``resources`` is a raw
        # spec consumed only here, so it is read from the merged mapping rather
        # than carried on the resolved options.
        resources = parse_resources(merged.get("resources", r"/*"))

        # Compute the options for each resource from the raw inputs (defaults,
        # app config, constructor kwargs, init_app kwargs) plus the per-resource
        # overrides. Re-merging the raw inputs rather than the already-resolved
        # ``options`` avoids re-normalizing compiled regexes.
        resolved_resources: list[tuple[ResourcePattern, _ComputedCorsOptions]] = [
            (pattern, get_cors_options(app, self._options, kwargs, opts)) for (pattern, opts) in resources
        ]

        # Create a human-readable form of these resources by converting the compiled
        # regular expressions into strings.
        resources_human = {get_regexp_pattern(pattern): opts for (pattern, opts) in resolved_resources}
        LOG.debug("Configuring CORS with resources: %s", resources_human)

        cors_after_request = make_after_request_function(resolved_resources)
        app.after_request(cors_after_request)

        # Wrap exception handlers with cross_origin so error responses also
        # receive CORS headers. Blueprints have no ``handle_exception`` /
        # ``make_response``, so the ``hasattr`` guard skips them; the ``Any``
        # alias lets us read and reassign those Flask-only methods without
        # tripping mypy's attr-defined / method-assign checks for ``Blueprint``.
        if options.intercept_exceptions and hasattr(app, "handle_exception"):
            app_any: Any = app

            def _after_request_decorator(f: Callable[..., Any]) -> Callable[..., Response]:
                def wrapped_function(*args: Any, **kwargs: Any) -> Response:
                    return cors_after_request(app_any.make_response(f(*args, **kwargs)))

                return wrapped_function

            app_any.handle_exception = _after_request_decorator(app_any.handle_exception)
            app_any.handle_user_exception = _after_request_decorator(app_any.handle_user_exception)


def make_after_request_function(
    resources: list[tuple[ResourcePattern, _ComputedCorsOptions]],
) -> Callable[[Response], Response]:
    def cors_after_request(resp: Response) -> Response:
        # If CORS headers are set in a view decorator, pass
        if resp.headers is not None and resp.headers.get(ACL_ORIGIN):
            LOG.debug("CORS have been already evaluated, skipping")
            return resp
        normalized_path = unquote(request.path)
        for res_regex, res_options in resources:
            if try_match_pattern(normalized_path, res_regex, caseSensitive=True):
                LOG.debug(
                    "Request to '%r' matches CORS resource '%s'. Using options: %s",
                    request.path,
                    get_regexp_pattern(res_regex),
                    res_options,
                )
                set_cors_headers(resp, res_options)
                break
        else:
            LOG.debug("No CORS rule matches")
        return resp

    return cors_after_request
