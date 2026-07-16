from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Iterable, List, Tuple, Union, cast

from prompt_toolkit.mouse_events import MouseEvent

if TYPE_CHECKING:
    from typing_extensions import Protocol

    from prompt_toolkit.key_binding.key_bindings import NotImplementedOrNone

__all__ = [
    "OneStyleAndTextTuple",
    "StyleAndTextTuples",
    "MagicFormattedText",
    "AnyFormattedText",
    "to_formatted_text",
    "is_formatted_text",
    "Template",
    "merge_formatted_text",
    "FormattedText",
]

OneStyleAndTextTuple = Union[
    Tuple[str, str], Tuple[str, str, Callable[[MouseEvent], "NotImplementedOrNone"]]
]

# List of (style, text) tuples.
StyleAndTextTuples = List[OneStyleAndTextTuple]


if TYPE_CHECKING:
    from typing_extensions import TypeGuard

    class MagicFormattedText(Protocol):
        """
        Any object that implements ``__pt_formatted_text__`` represents formatted
        text.
        """

        def __pt_formatted_text__(self) -> StyleAndTextTuples: ...


AnyFormattedText = Union[
    str,
    "MagicFormattedText",
    StyleAndTextTuples,
    # Callable[[], 'AnyFormattedText']  # Recursive definition not supported by mypy.
    Callable[[], Any],
    None,
]


def to_formatted_text(
    value: AnyFormattedText, style: str = "", auto_convert: bool = False
) -> FormattedText:
    """
    Convert the given value (which can be formatted text) into a list of text
    fragments. (Which is the canonical form of formatted text.) The outcome is
    always a `FormattedText` instance, which is a list of (style, text) tuples.

    It can take a plain text string, an `HTML` or `ANSI` object, anything that
    implements `__pt_formatted_text__` or a callable that takes no arguments and
    returns one of those.

    :param style: An additional style string which is applied to all text
        fragments.
    :param auto_convert: If `True`, also accept other types, and convert them
        to a string first.
    """
    result: FormattedText | StyleAndTextTuples

    if value is None:
        result = []
    elif isinstance(value, str):
        result = [("", value)]
    elif isinstance(value, list):
        result = value  # StyleAndTextTuples
    elif hasattr(value, "__pt_formatted_text__"):
        result = cast("MagicFormattedText", value).__pt_formatted_text__()
    elif callable(value):
        return to_formatted_text(value(), style=style)
    elif auto_convert:
        result = [("", f"{value}")]
    else:
        raise ValueError(
            "No formatted text. Expecting a unicode object, "
            f"HTML, ANSI or a FormattedText instance. Got {value!r}"
        )

    # Apply extra style.
    if style:
        result = cast(
            StyleAndTextTuples,
            [(style + " " + item_style, *rest) for item_style, *rest in result],
        )

    # Make sure the result is wrapped in a `FormattedText`. Among other
    # reasons, this is important for `print_formatted_text` to work correctly
    # and distinguish between lists and formatted text.
    if isinstance(result, FormattedText):
        return result
    else:
        return FormattedText(result)


def is_formatted_text(value: object) -> TypeGuard[AnyFormattedText]:
    """
    Check whether the input is valid formatted text (for use in assert
    statements).
    In case of a callable, it doesn't check the return type.
    """
    if callable(value):
        return True
    if isinstance(value, (str, list)):
        return True
    if hasattr(value, "__pt_formatted_text__"):
        return True
    return False


class FormattedText(StyleAndTextTuples):
    """
    A list of ``(style, text)`` tuples.

    (In some situations, this can also be ``(style, text, mouse_handler)``
    tuples.)
    """

    def __pt_formatted_text__(self) -> StyleAndTextTuples:
        return self

    def __repr__(self) -> str:
        return f"FormattedText({super().__repr__()})"


class Template:
    """
    Template for string interpolation with formatted text.

    Example::

        Template(' ... {} ... ').format(HTML(...))

    :param text: Plain text.
    """

    def __init__(self, text: str) -> None:
        assert "{0}" not in text
        self.text = text

    def format(self, *values: AnyFormattedText) -> AnyFormattedText:
        def get_result() -> AnyFormattedText:
            # Split the template in parts.
            parts = self.text.split("{}")
            assert len(parts) - 1 == len(values)

            result = FormattedText()
            for part, val in zip(parts, values):
                result.append(("", part))
                result.extend(to_formatted_text(val))
            result.append(("", parts[-1]))
            return result

        return get_result


def merge_formatted_text(items: Iterable[AnyFormattedText]) -> AnyFormattedText:
    """
    Merge (Concatenate) several pieces of formatted text together.
    """

    def _merge_formatted_text() -> AnyFormattedText:
        result = FormattedText()
        for i in items:
            result.extend(to_formatted_text(i))
        return result

    return _merge_formatted_text
