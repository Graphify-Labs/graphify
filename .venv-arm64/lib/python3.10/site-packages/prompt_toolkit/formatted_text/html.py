from __future__ import annotations

import xml.dom.minidom as minidom
from string import Formatter
from typing import Any

from .base import FormattedText, StyleAndTextTuples

__all__ = ["HTML"]


class HTML:
    """
    HTML formatted text.
    Take something HTML-like, for use as a formatted string.

    ::

        # Turn something into red.
        HTML('<style fg="ansired" bg="#00ff44">...</style>')

        # Italic, bold, underline and strike.
        HTML('<i>...</i>')
        HTML('<b>...</b>')
        HTML('<u>...</u>')
        HTML('<s>...</s>')

    All HTML elements become available as a "class" in the style sheet.
    E.g. ``<username>...</username>`` can be styled, by setting a style for
    ``username``.
    """

    def __init__(self, value: str) -> None:
        self.value = value
        document = minidom.parseString(f"<html-root>{value}</html-root>")

        result: StyleAndTextTuples = []
        name_stack: list[str] = []
        fg_stack: list[str] = []
        bg_stack: list[str] = []

        def get_current_style() -> str:
            "Build style string for current node."
            parts = []
            if name_stack:
                parts.append("class:" + ",".join(name_stack))

            if fg_stack:
                parts.append("fg:" + fg_stack[-1])
            if bg_stack:
                parts.append("bg:" + bg_stack[-1])
            return " ".join(parts)

        def process_node(node: Any) -> None:
            "Process node recursively."
            for child in node.childNodes:
                if child.nodeType == child.TEXT_NODE:
                    result.append((get_current_style(), child.data))
                else:
                    add_to_name_stack = child.nodeName not in (
                        "#document",
                        "html-root",
                        "style",
                    )
                    fg = bg = ""

                    for k, v in child.attributes.items():
                        if k == "fg":
                            fg = v
                        if k == "bg":
                            bg = v
                        if k == "color":
                            fg = v  # Alias for 'fg'.

                    # Check for spaces in attributes. This would result in
                    # invalid style strings otherwise.
                    if " " in fg:
                        raise ValueError('"fg" attribute contains a space.')
                    if " " in bg:
                        raise ValueError('"bg" attribute contains a space.')

                    if add_to_name_stack:
                        name_stack.append(child.nodeName)
                    if fg:
                        fg_stack.append(fg)
                    if bg:
                        bg_stack.append(bg)

                    process_node(child)

                    if add_to_name_stack:
                        name_stack.pop()
                    if fg:
                        fg_stack.pop()
                    if bg:
                        bg_stack.pop()

        process_node(document)

        self.formatted_text = FormattedText(result)

    def __repr__(self) -> str:
        return f"HTML({self.value!r})"

    def __pt_formatted_text__(self) -> StyleAndTextTuples:
        return self.formatted_text

    def format(self, *args: object, **kwargs: object) -> HTML:
        """
        Like `str.format`, but make sure that the arguments are properly
        escaped.
        """
        return HTML(FORMATTER.vformat(self.value, args, kwargs))

    def __mod__(self, value: object) -> HTML:
        """
        HTML('<b>%s</b>') % value
        """
        if not isinstance(value, tuple):
            value = (value,)

        value = tuple(html_escape(i) for i in value)
        return HTML(self.value % value)


class HTMLFormatter(Formatter):
    def format_field(self, value: object, format_spec: str) -> str:
        return html_escape(format(value, format_spec))


def html_escape(text: object) -> str:
    # The string interpolation functions also take integers and other types.
    # Convert to string first.
    if not isinstance(text, str):
        text = f"{text}"

    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


FORMATTER = HTMLFormatter()
