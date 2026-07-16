from __future__ import annotations

import collections.abc as cabc
import typing as t

from .structures import CallbackDict


def csp_property(key: str) -> t.Any:
    """Return a new property object for a content security policy header.
    Useful if you want to add support for a csp extension in a
    subclass.
    """
    return property(
        lambda x: x._get_value(key),
        lambda x, v: x._set_value(key, v),
        lambda x: x._del_value(key),
        f"accessor for {key!r}",
    )


class ContentSecurityPolicy(CallbackDict[str, str]):
    """Subclass of a dict that stores values for a Content Security Policy
    header. It has accessors for all the level 3 policies.

    Because the csp directives in the HTTP header use dashes the
    python descriptors use underscores for that.

    To get a header of the :class:`ContentSecurityPolicy` object again
    you can convert the object into a string or call the
    :meth:`to_header` method.  If you plan to subclass it and add your
    own items have a look at the sourcecode for that class.

    .. versionadded:: 1.0.0
       Support for Content Security Policy headers was added.

    """

    base_uri: str | None = csp_property("base-uri")
    child_src: str | None = csp_property("child-src")
    connect_src: str | None = csp_property("connect-src")
    default_src: str | None = csp_property("default-src")
    font_src: str | None = csp_property("font-src")
    form_action: str | None = csp_property("form-action")
    frame_ancestors: str | None = csp_property("frame-ancestors")
    frame_src: str | None = csp_property("frame-src")
    img_src: str | None = csp_property("img-src")
    manifest_src: str | None = csp_property("manifest-src")
    media_src: str | None = csp_property("media-src")
    navigate_to: str | None = csp_property("navigate-to")
    object_src: str | None = csp_property("object-src")
    prefetch_src: str | None = csp_property("prefetch-src")
    plugin_types: str | None = csp_property("plugin-types")
    report_to: str | None = csp_property("report-to")
    report_uri: str | None = csp_property("report-uri")
    sandbox: str | None = csp_property("sandbox")
    script_src: str | None = csp_property("script-src")
    script_src_attr: str | None = csp_property("script-src-attr")
    script_src_elem: str | None = csp_property("script-src-elem")
    style_src: str | None = csp_property("style-src")
    style_src_attr: str | None = csp_property("style-src-attr")
    style_src_elem: str | None = csp_property("style-src-elem")
    worker_src: str | None = csp_property("worker-src")

    def __init__(
        self,
        values: cabc.Mapping[str, str] | cabc.Iterable[tuple[str, str]] | None = (),
        on_update: cabc.Callable[[ContentSecurityPolicy], None] | None = None,
    ) -> None:
        super().__init__(values, on_update)
        self.provided = values is not None

    def _get_value(self, key: str) -> str | None:
        """Used internally by the accessor properties."""
        return self.get(key)

    def _set_value(self, key: str, value: str | None) -> None:
        """Used internally by the accessor properties."""
        if value is None:
            self.pop(key, None)
        else:
            self[key] = value

    def _del_value(self, key: str) -> None:
        """Used internally by the accessor properties."""
        if key in self:
            del self[key]

    def to_header(self) -> str:
        """Convert the stored values into a cache control header."""
        from ..http import dump_csp_header

        return dump_csp_header(self)

    def __str__(self) -> str:
        return self.to_header()

    def __repr__(self) -> str:
        kv_str = " ".join(f"{k}={v!r}" for k, v in sorted(self.items()))
        return f"<{type(self).__name__} {kv_str}>"
