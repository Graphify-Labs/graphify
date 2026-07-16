from __future__ import annotations

import difflib
import typing as t

from ..exceptions import BadRequest
from ..exceptions import HTTPException
from ..utils import cached_property
from ..utils import redirect

if t.TYPE_CHECKING:
    from _typeshed.wsgi import WSGIEnvironment

    from ..wrappers.request import Request
    from ..wrappers.response import Response
    from .map import MapAdapter
    from .rules import Rule


class RoutingException(Exception):
    """Special exceptions that require the application to redirect, notifying
    about missing urls, etc.

    :internal:
    """


class RequestRedirect(HTTPException, RoutingException):
    """Raise if the map requests a redirect. This is for example the case if
    `strict_slashes` are activated and an url that requires a trailing slash.

    The attribute `new_url` contains the absolute destination url.
    """

    code = 308

    def __init__(self, new_url: str) -> None:
        super().__init__(new_url)
        self.new_url = new_url

    def get_response(
        self,
        environ: WSGIEnvironment | Request | None = None,
        scope: dict[str, t.Any] | None = None,
    ) -> Response:
        return redirect(self.new_url, self.code)


class RequestPath(RoutingException):
    """Internal exception."""

    __slots__ = ("path_info",)

    def __init__(self, path_info: str) -> None:
        super().__init__()
        self.path_info = path_info


class RequestAliasRedirect(RoutingException):  # noqa: B903
    """This rule is an alias and wants to redirect to the canonical URL."""

    def __init__(self, matched_values: t.Mapping[str, t.Any], endpoint: t.Any) -> None:
        super().__init__()
        self.matched_values = matched_values
        self.endpoint = endpoint


class BuildError(RoutingException, LookupError):
    """Raised if the build system cannot find a URL for an endpoint with the
    values provided.
    """

    def __init__(
        self,
        endpoint: t.Any,
        values: t.Mapping[str, t.Any],
        method: str | None,
        adapter: MapAdapter | None = None,
    ) -> None:
        super().__init__(endpoint, values, method)
        self.endpoint = endpoint
        self.values = values
        self.method = method
        self.adapter = adapter

    @cached_property
    def suggested(self) -> Rule | None:
        return self.closest_rule(self.adapter)

    def closest_rule(self, adapter: MapAdapter | None) -> Rule | None:
        def _score_rule(rule: Rule) -> float:
            return sum(
                [
                    0.98
                    * difflib.SequenceMatcher(
                        # endpoints can be any type, compare as strings
                        None,
                        str(rule.endpoint),
                        str(self.endpoint),
                    ).ratio(),
                    0.01 * bool(set(self.values or ()).issubset(rule.arguments)),
                    0.01 * bool(rule.methods and self.method in rule.methods),
                ]
            )

        if adapter and adapter.map._rules:
            return max(adapter.map._rules, key=_score_rule)

        return None

    def __str__(self) -> str:
        message = [f"Could not build url for endpoint {self.endpoint!r}"]
        if self.method:
            message.append(f" ({self.method!r})")
        if self.values:
            message.append(f" with values {sorted(self.values)!r}")
        message.append(".")
        if self.suggested:
            if self.endpoint == self.suggested.endpoint:
                if (
                    self.method
                    and self.suggested.methods is not None
                    and self.method not in self.suggested.methods
                ):
                    message.append(
                        " Did you mean to use methods"
                        f" {sorted(self.suggested.methods)!r}?"
                    )
                missing_values = self.suggested.arguments.union(
                    set(self.suggested.defaults or ())
                ) - set(self.values.keys())
                if missing_values:
                    message.append(
                        f" Did you forget to specify values {sorted(missing_values)!r}?"
                    )
            else:
                message.append(f" Did you mean {self.suggested.endpoint!r} instead?")
        return "".join(message)


class WebsocketMismatch(BadRequest):
    """The only matched rule is either a WebSocket and the request is
    HTTP, or the rule is HTTP and the request is a WebSocket.
    """


class NoMatch(Exception):
    __slots__ = ("have_match_for", "websocket_mismatch")

    def __init__(self, have_match_for: set[str], websocket_mismatch: bool) -> None:
        self.have_match_for = have_match_for
        self.websocket_mismatch = websocket_mismatch
