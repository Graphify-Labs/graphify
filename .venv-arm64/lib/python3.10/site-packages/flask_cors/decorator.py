from __future__ import annotations

import logging
from collections.abc import Callable
from functools import update_wrapper
from typing import TYPE_CHECKING, Any, TypeVar, cast

from flask import Response, current_app, make_response, request

from .core import FLASK_CORS_EVALUATED, CrossOriginOptionsInput, get_cors_options, set_cors_headers

if TYPE_CHECKING:
    from typing_extensions import Unpack

LOG = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def cross_origin(*args: Any, **kwargs: Unpack[CrossOriginOptionsInput]) -> Callable[[F], F]:
    """
    This function is the decorator which is used to wrap a Flask route with.
    In the simplest case, simply use the default parameters to allow all
    origins in what is the most permissive configuration. If this method
    modifies state or performs authentication which may be brute-forced, you
    should add some degree of protection, such as Cross Site Request Forgery
    protection.

    :param origins:
        The origin, or list of origins to allow requests from.
        The origin(s) may be regular expressions, case-sensitive strings,
        or else an asterisk

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

    :param automatic_options:
        Only applies to the `cross_origin` decorator. If True, Flask-CORS will
        override Flask's default OPTIONS handling to return CORS headers for
        OPTIONS requests.

        Default : True
    :type automatic_options: bool

    """
    _options = kwargs

    def decorator(f: F) -> F:
        LOG.debug("Enabling %s for cross_origin using options:%s", f, _options)

        # If True, intercept OPTIONS requests by modifying the view function,
        # replicating Flask's default behavior, and wrapping the response with
        # CORS headers.
        #
        # If f.provide_automatic_options is unset or True, Flask's route
        # decorator (which is actually wraps the function object we return)
        # intercepts OPTIONS handling, and requests will not have CORS headers
        if _options.get("automatic_options", True):
            # ``f`` is a plain view function; these attributes are read by
            # Flask's routing. Use an ``Any`` alias so the dynamic attribute
            # assignment type-checks.
            view_func: Any = f
            required_methods = set(getattr(f, "required_methods", set()))
            required_methods.add("OPTIONS")
            view_func.required_methods = required_methods
            view_func.provide_automatic_options = False

        def wrapped_function(*args: Any, **kwargs: Any) -> Response:
            # Handle setting of Flask-Cors parameters
            options = get_cors_options(current_app, _options)

            if options.automatic_options and request.method == "OPTIONS":
                resp = current_app.make_default_options_response()
            else:
                resp = make_response(f(*args, **kwargs))

            set_cors_headers(resp, options)
            setattr(resp, FLASK_CORS_EVALUATED, True)
            return resp

        return cast(F, update_wrapper(wrapped_function, f))

    return decorator
