from __future__ import annotations

from collections.abc import Iterator

from _pytest._io.saferepr import saferepr
from _pytest.assertion._typing import _AssertionTextDiffStyle
from _pytest.assertion._typing import _HighlightFunc
from _pytest.assertion.highlight import dummy_highlighter
from _pytest.compat import assert_never


def _compare_eq_text(
    left: str,
    right: str,
    highlighter: _HighlightFunc,
    verbose: int,
    assertion_text_diff_style: _AssertionTextDiffStyle,
) -> Iterator[str]:
    match assertion_text_diff_style:
        case "block":
            yield from _diff_text_block(left, right)
        case "ndiff":
            yield from _diff_text(left, right, highlighter, verbose)
        case unreachable:
            assert_never(unreachable)


def _diff_text_block(left: str, right: str) -> Iterator[str]:
    yield "Left:"
    yield from _format_text_block_lines(left)
    yield ""
    yield "Right:"
    yield from _format_text_block_lines(right)


def _format_text_block_lines(text: str) -> Iterator[str]:
    for line in text.split("\n"):
        yield f"  {line}"


def _diff_text(
    left: str, right: str, highlighter: _HighlightFunc, verbose: int = 0
) -> Iterator[str]:
    """Yield the explanation for the diff between text.

    Unless --verbose is used this will skip leading and trailing
    characters which are identical to keep the diff minimal.
    """
    from difflib import ndiff

    if verbose < 1:
        i = 0  # just in case left or right has zero length
        for i in range(min(len(left), len(right))):
            if left[i] != right[i]:
                break
        if i > 42:
            i -= 10  # Provide some context
            yield f"Skipping {i} identical leading characters in diff, use -v to show"
            left = left[i:]
            right = right[i:]
        if len(left) == len(right):
            for i in range(len(left)):
                if left[-i] != right[-i]:
                    break
            if i > 42:
                i -= 10  # Provide some context
                yield (
                    f"Skipping {i} identical trailing "
                    "characters in diff, use -v to show"
                )
                left = left[:-i]
                right = right[:-i]
    keepends = True
    if left.isspace() or right.isspace():
        left = repr(str(left))
        right = repr(str(right))
        yield "Strings contain only whitespace, escaping them using repr()"
    # "right" is the expected base against which we compare "left",
    # see https://github.com/pytest-dev/pytest/issues/3333
    yield from highlighter(
        "\n".join(
            line.strip("\n")
            for line in ndiff(right.splitlines(keepends), left.splitlines(keepends))
        ),
        lexer="diff",
    ).splitlines()


def _notin_text(term: str, text: str, verbose: int = 0) -> Iterator[str]:
    index = text.find(term)
    head = text[:index]
    tail = text[index + len(term) :]
    correct_text = head + tail
    diff = _diff_text(text, correct_text, dummy_highlighter, verbose)
    yield f"{saferepr(term, maxsize=42)} is contained here:"
    for line in diff:
        if line.startswith("Skipping"):
            continue
        if line.startswith("- "):
            continue
        if line.startswith("+ "):
            yield "  " + line[2:]
        else:
            yield line
