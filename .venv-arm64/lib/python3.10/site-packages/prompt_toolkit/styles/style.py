"""
Tool for creating styles from a dictionary.
"""

from __future__ import annotations

import itertools
import re
from enum import Enum
from typing import Hashable, TypeVar

from prompt_toolkit.cache import SimpleCache

from .base import (
    ANSI_COLOR_NAMES,
    ANSI_COLOR_NAMES_ALIASES,
    DEFAULT_ATTRS,
    Attrs,
    BaseStyle,
)
from .named_colors import NAMED_COLORS

__all__ = [
    "Style",
    "parse_color",
    "Priority",
    "merge_styles",
]

_named_colors_lowercase = {k.lower(): v.lstrip("#") for k, v in NAMED_COLORS.items()}


def parse_color(text: str) -> str:
    """
    Parse/validate color format.

    Like in Pygments, but also support the ANSI color names.
    (These will map to the colors of the 16 color palette.)
    """
    # ANSI color names.
    if text in ANSI_COLOR_NAMES:
        return text
    if text in ANSI_COLOR_NAMES_ALIASES:
        return ANSI_COLOR_NAMES_ALIASES[text]

    # 140 named colors.
    try:
        # Replace by 'hex' value.
        return _named_colors_lowercase[text.lower()]
    except KeyError:
        pass

    # Hex codes.
    if text[0:1] == "#":
        col = text[1:]

        # Keep this for backwards-compatibility (Pygments does it).
        # I don't like the '#' prefix for named colors.
        if col in ANSI_COLOR_NAMES:
            return col
        elif col in ANSI_COLOR_NAMES_ALIASES:
            return ANSI_COLOR_NAMES_ALIASES[col]

        # 6 digit hex color.
        elif len(col) == 6:
            return col

        # 3 digit hex color.
        elif len(col) == 3:
            return col[0] * 2 + col[1] * 2 + col[2] * 2

    # Default.
    elif text in ("", "default"):
        return text

    raise ValueError(f"Wrong color format {text!r}")


# Attributes, when they are not filled in by a style. None means that we take
# the value from the parent.
_EMPTY_ATTRS = Attrs(
    color=None,
    bgcolor=None,
    bold=None,
    underline=None,
    strike=None,
    italic=None,
    blink=None,
    reverse=None,
    hidden=None,
    dim=None,
)


def _expand_classname(classname: str) -> list[str]:
    """
    Split a single class name at the `.` operator, and build a list of classes.

    E.g. 'a.b.c' becomes ['a', 'a.b', 'a.b.c']
    """
    result = []
    parts = classname.split(".")

    for i in range(1, len(parts) + 1):
        result.append(".".join(parts[:i]).lower())

    return result


def _parse_style_str(style_str: str) -> Attrs:
    """
    Take a style string, e.g.  'bg:red #88ff00 class:title'
    and return a `Attrs` instance.
    """
    # Start from default Attrs.
    if "noinherit" in style_str:
        attrs = DEFAULT_ATTRS
    else:
        attrs = _EMPTY_ATTRS

    # Now update with the given attributes.
    for part in style_str.split():
        if part == "noinherit":
            pass
        elif part == "bold":
            attrs = attrs._replace(bold=True)
        elif part == "nobold":
            attrs = attrs._replace(bold=False)
        elif part == "italic":
            attrs = attrs._replace(italic=True)
        elif part == "noitalic":
            attrs = attrs._replace(italic=False)
        elif part == "underline":
            attrs = attrs._replace(underline=True)
        elif part == "nounderline":
            attrs = attrs._replace(underline=False)
        elif part == "strike":
            attrs = attrs._replace(strike=True)
        elif part == "nostrike":
            attrs = attrs._replace(strike=False)

        # prompt_toolkit extensions. Not in Pygments.
        elif part == "blink":
            attrs = attrs._replace(blink=True)
        elif part == "noblink":
            attrs = attrs._replace(blink=False)
        elif part == "reverse":
            attrs = attrs._replace(reverse=True)
        elif part == "noreverse":
            attrs = attrs._replace(reverse=False)
        elif part == "hidden":
            attrs = attrs._replace(hidden=True)
        elif part == "nohidden":
            attrs = attrs._replace(hidden=False)
        elif part == "dim":
            attrs = attrs._replace(dim=True)
        elif part == "nodim":
            attrs = attrs._replace(dim=False)

        # Pygments properties that we ignore.
        elif part in ("roman", "sans", "mono"):
            pass
        elif part.startswith("border:"):
            pass

        # Ignore pieces in between square brackets. This is internal stuff.
        # Like '[transparent]' or '[set-cursor-position]'.
        elif part.startswith("[") and part.endswith("]"):
            pass

        # Colors.
        elif part.startswith("bg:"):
            attrs = attrs._replace(bgcolor=parse_color(part[3:]))
        elif part.startswith("fg:"):  # The 'fg:' prefix is optional.
            attrs = attrs._replace(color=parse_color(part[3:]))
        else:
            attrs = attrs._replace(color=parse_color(part))

    return attrs


CLASS_NAMES_RE = re.compile(r"^[a-z0-9.\s_-]*$")  # This one can't contain a comma!


class Priority(Enum):
    """
    The priority of the rules, when a style is created from a dictionary.

    In a `Style`, rules that are defined later will always override previous
    defined rules, however in a dictionary, the key order was arbitrary before
    Python 3.6. This means that the style could change at random between rules.

    We have two options:

    - `DICT_KEY_ORDER`: This means, iterate through the dictionary, and take
       the key/value pairs in order as they come. This is a good option if you
       have Python >3.6. Rules at the end will override rules at the beginning.
    - `MOST_PRECISE`: keys that are defined with most precision will get higher
      priority. (More precise means: more elements.)
    """

    DICT_KEY_ORDER = "KEY_ORDER"
    MOST_PRECISE = "MOST_PRECISE"


# We don't support Python versions older than 3.6 anymore, so we can always
# depend on dictionary ordering. This is the default.
default_priority = Priority.DICT_KEY_ORDER


class Style(BaseStyle):
    """
    Create a ``Style`` instance from a list of style rules.

    The `style_rules` is supposed to be a list of ('classnames', 'style') tuples.
    The classnames are a whitespace separated string of class names and the
    style string is just like a Pygments style definition, but with a few
    additions: it supports 'reverse' and 'blink'.

    Later rules always override previous rules.

    Usage::

        Style([
            ('title', '#ff0000 bold underline'),
            ('something-else', 'reverse'),
            ('class1 class2', 'reverse'),
        ])

    The ``from_dict`` classmethod is similar, but takes a dictionary as input.
    """

    def __init__(self, style_rules: list[tuple[str, str]]) -> None:
        class_names_and_attrs = []

        # Loop through the rules in the order they were defined.
        # Rules that are defined later get priority.
        for class_names, style_str in style_rules:
            assert CLASS_NAMES_RE.match(class_names), repr(class_names)

            # The order of the class names doesn't matter.
            # (But the order of rules does matter.)
            class_names_set = frozenset(class_names.lower().split())
            attrs = _parse_style_str(style_str)

            class_names_and_attrs.append((class_names_set, attrs))

        self._style_rules = style_rules
        self.class_names_and_attrs = class_names_and_attrs

    @property
    def style_rules(self) -> list[tuple[str, str]]:
        return self._style_rules

    @classmethod
    def from_dict(
        cls, style_dict: dict[str, str], priority: Priority = default_priority
    ) -> Style:
        """
        :param style_dict: Style dictionary.
        :param priority: `Priority` value.
        """
        if priority == Priority.MOST_PRECISE:

            def key(item: tuple[str, str]) -> int:
                # Split on '.' and whitespace. Count elements.
                return sum(len(i.split(".")) for i in item[0].split())

            return cls(sorted(style_dict.items(), key=key))
        else:
            return cls(list(style_dict.items()))

    def get_attrs_for_style_str(
        self, style_str: str, default: Attrs = DEFAULT_ATTRS
    ) -> Attrs:
        """
        Get `Attrs` for the given style string.
        """
        list_of_attrs = [default]
        class_names: set[str] = set()

        # Apply default styling.
        for names, attr in self.class_names_and_attrs:
            if not names:
                list_of_attrs.append(attr)

        # Go from left to right through the style string. Things on the right
        # take precedence.
        for part in style_str.split():
            # This part represents a class.
            # Do lookup of this class name in the style definition, as well
            # as all class combinations that we have so far.
            if part.startswith("class:"):
                # Expand all class names (comma separated list).
                new_class_names = []
                for p in part[6:].lower().split(","):
                    new_class_names.extend(_expand_classname(p))

                for new_name in new_class_names:
                    # Build a set of all possible class combinations to be applied.
                    combos = set()
                    combos.add(frozenset([new_name]))

                    for count in range(1, len(class_names) + 1):
                        for c2 in itertools.combinations(class_names, count):
                            combos.add(frozenset(c2 + (new_name,)))

                    # Apply the styles that match these class names.
                    for names, attr in self.class_names_and_attrs:
                        if names in combos:
                            list_of_attrs.append(attr)

                    class_names.add(new_name)

            # Process inline style.
            else:
                inline_attrs = _parse_style_str(part)
                list_of_attrs.append(inline_attrs)

        return _merge_attrs(list_of_attrs)

    def invalidation_hash(self) -> Hashable:
        return id(self.class_names_and_attrs)


_T = TypeVar("_T")


def _merge_attrs(list_of_attrs: list[Attrs]) -> Attrs:
    """
    Take a list of :class:`.Attrs` instances and merge them into one.
    Every `Attr` in the list can override the styling of the previous one. So,
    the last one has highest priority.
    """

    def _or(*values: _T) -> _T:
        "Take first not-None value, starting at the end."
        for v in values[::-1]:
            if v is not None:
                return v
        raise ValueError  # Should not happen, there's always one non-null value.

    return Attrs(
        color=_or("", *[a.color for a in list_of_attrs]),
        bgcolor=_or("", *[a.bgcolor for a in list_of_attrs]),
        bold=_or(False, *[a.bold for a in list_of_attrs]),
        underline=_or(False, *[a.underline for a in list_of_attrs]),
        strike=_or(False, *[a.strike for a in list_of_attrs]),
        italic=_or(False, *[a.italic for a in list_of_attrs]),
        blink=_or(False, *[a.blink for a in list_of_attrs]),
        reverse=_or(False, *[a.reverse for a in list_of_attrs]),
        hidden=_or(False, *[a.hidden for a in list_of_attrs]),
        dim=_or(False, *[a.dim for a in list_of_attrs]),
    )


def merge_styles(styles: list[BaseStyle]) -> _MergedStyle:
    """
    Merge multiple `Style` objects.
    """
    styles = [s for s in styles if s is not None]
    return _MergedStyle(styles)


class _MergedStyle(BaseStyle):
    """
    Merge multiple `Style` objects into one.
    This is supposed to ensure consistency: if any of the given styles changes,
    then this style will be updated.
    """

    # NOTE: previously, we used an algorithm where we did not generate the
    #       combined style. Instead this was a proxy that called one style
    #       after the other, passing the outcome of the previous style as the
    #       default for the next one. This did not work, because that way, the
    #       priorities like described in the `Style` class don't work.
    #       'class:aborted' was for instance never displayed in gray, because
    #       the next style specified a default color for any text. (The
    #       explicit styling of class:aborted should have taken priority,
    #       because it was more precise.)
    def __init__(self, styles: list[BaseStyle]) -> None:
        self.styles = styles
        self._style: SimpleCache[Hashable, Style] = SimpleCache(maxsize=1)

    @property
    def _merged_style(self) -> Style:
        "The `Style` object that has the other styles merged together."

        def get() -> Style:
            return Style(self.style_rules)

        return self._style.get(self.invalidation_hash(), get)

    @property
    def style_rules(self) -> list[tuple[str, str]]:
        style_rules = []
        for s in self.styles:
            style_rules.extend(s.style_rules)
        return style_rules

    def get_attrs_for_style_str(
        self, style_str: str, default: Attrs = DEFAULT_ATTRS
    ) -> Attrs:
        return self._merged_style.get_attrs_for_style_str(style_str, default)

    def invalidation_hash(self) -> Hashable:
        return tuple(s.invalidation_hash() for s in self.styles)
