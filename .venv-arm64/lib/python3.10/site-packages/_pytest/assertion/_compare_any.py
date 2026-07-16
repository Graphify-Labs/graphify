from __future__ import annotations

from collections.abc import Iterator
import dataclasses
import pprint

from _pytest.assertion._compare_mapping import _compare_eq_mapping
from _pytest.assertion._compare_sequence import _compare_eq_iterable
from _pytest.assertion._compare_sequence import _compare_eq_sequence
from _pytest.assertion._compare_set import _compare_eq_set
from _pytest.assertion._guards import has_default_eq
from _pytest.assertion._guards import isattrs
from _pytest.assertion._guards import isdatacls
from _pytest.assertion._guards import isiterable
from _pytest.assertion._guards import ismapping
from _pytest.assertion._guards import isnamedtuple
from _pytest.assertion._guards import issequence
from _pytest.assertion._guards import isset
from _pytest.assertion._guards import istext
from _pytest.assertion._typing import _AssertionTextDiffStyle
from _pytest.assertion._typing import _HighlightFunc
from _pytest.assertion.compare_text import _compare_eq_text


def _compare_eq_any(
    left: object,
    right: object,
    highlighter: _HighlightFunc,
    verbose: int,
    assertion_text_diff_style: _AssertionTextDiffStyle,
) -> Iterator[str]:
    """Yield the per-line explanation for ``left == right`` (without summary).

    Yields nothing when no specialised explanation applies, so consumers
    can stream the output and bail out early (e.g. for truncation) without
    materialising the entire diff first.
    """
    if istext(left) and istext(right):
        yield from _compare_eq_text(
            left,
            right,
            highlighter,
            verbose,
            assertion_text_diff_style,
        )
    else:
        from _pytest.python_api import ApproxBase

        # Although the common order should be obtained == approx(...), allow both ways.
        if isinstance(right, ApproxBase):
            yield from right._repr_compare(left)
        elif isinstance(left, ApproxBase):
            yield from left._repr_compare(right)
        elif type(left) is type(right) and (
            isdatacls(left) or isattrs(left) or isnamedtuple(left)
        ):
            # Note: unlike dataclasses/attrs, namedtuples compare only the
            # field values, not the type or field names. But this branch
            # intentionally only handles the same-type case, which was often
            # used in older code bases before dataclasses/attrs were available.
            yield from _compare_eq_cls(
                left,
                right,
                highlighter,
                verbose,
                assertion_text_diff_style,
            )
        elif issequence(left) and issequence(right):
            yield from _compare_eq_sequence(left, right, highlighter, verbose)
        elif isset(left) and isset(right):
            yield from _compare_eq_set(left, right, highlighter, verbose)
        elif ismapping(left) and ismapping(right):
            yield from _compare_eq_mapping(left, right, highlighter, verbose)

        if isiterable(left) and isiterable(right):
            yield from _compare_eq_iterable(left, right, highlighter, verbose)


def _compare_eq_cls(
    left: object,
    right: object,
    highlighter: _HighlightFunc,
    verbose: int,
    assertion_text_diff_style: _AssertionTextDiffStyle,
) -> Iterator[str]:
    if not has_default_eq(left):
        return
    if isdatacls(left):
        all_fields = dataclasses.fields(left)
        fields_to_check = [info.name for info in all_fields if info.compare]
    elif isattrs(left):
        all_fields = left.__attrs_attrs__  # type: ignore[attr-defined]
        fields_to_check = [field.name for field in all_fields if getattr(field, "eq")]
    elif isnamedtuple(left):
        fields_to_check = left._fields  # type: ignore[attr-defined]
    else:
        assert False

    indent = "  "
    same = []
    diff = []
    for field in fields_to_check:
        if getattr(left, field) == getattr(right, field):
            same.append(field)
        else:
            diff.append(field)

    if same or diff:
        yield ""
    if same and verbose < 2:
        yield f"Omitting {len(same)} identical items, use -vv to show"
    elif same:
        yield "Matching attributes:"
        yield from highlighter(pprint.pformat(same)).splitlines()
    if diff:
        yield "Differing attributes:"
        yield from highlighter(pprint.pformat(diff)).splitlines()
        for field in diff:
            field_left = getattr(left, field)
            field_right = getattr(right, field)
            yield ""
            yield f"Drill down into differing attribute {field}:"
            yield f"{indent}{field}: {highlighter(repr(field_left))} != {highlighter(repr(field_right))}"
            for line in _compare_eq_any(
                field_left,
                field_right,
                highlighter,
                verbose,
                assertion_text_diff_style,
            ):
                yield indent + line
