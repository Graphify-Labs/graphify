from __future__ import annotations


class UserAgent:
    """Represents a parsed user agent header value.

    The default implementation does no parsing, only the :attr:`string`
    attribute is set. A subclass may parse the string to set the
    common attributes or expose other information. Set
    :attr:`werkzeug.wrappers.Request.user_agent_class` to use a
    subclass.

    :param string: The header value to parse.

    .. versionadded:: 2.0
        This replaces the previous ``useragents`` module, but does not
        provide a built-in parser.
    """

    platform: str | None = None
    """The OS name, if it could be parsed from the string."""

    browser: str | None = None
    """The browser name, if it could be parsed from the string."""

    version: str | None = None
    """The browser version, if it could be parsed from the string."""

    language: str | None = None
    """The browser language, if it could be parsed from the string."""

    def __init__(self, string: str) -> None:
        self.string: str = string
        """The original header value."""

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.browser}/{self.version}>"

    def __str__(self) -> str:
        return self.string

    def __bool__(self) -> bool:
        return bool(self.browser)

    def to_header(self) -> str:
        """Convert to a header value."""
        return self.string
