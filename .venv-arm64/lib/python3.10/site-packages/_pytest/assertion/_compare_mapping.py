from __future__ import annotations

from collections.abc import Iterator
from collections.abc import Mapping
import pprint

from _pytest._io.saferepr import saferepr
from _pytest.assertion._typing import _HighlightFunc


def _compare_eq_mapping(
    left: Mapping[object, object],
    right: Mapping[object, object],
    highlighter: _HighlightFunc,
    verbose: int = 0,
) -> Iterator[str]:
    set_left = set(left)
    set_right = set(right)
    common = set_left.intersection(set_right)
    same = {k: left[k] for k in common if left[k] == right[k]}
    if same and verbose < 2:
        yield f"Omitting {len(same)} identical items, use -vv to show"
    elif same:
        yield "Common items:"
        yield from highlighter(pprint.pformat(same)).splitlines()
    diff = {k for k in common if left[k] != right[k]}
    if diff:
        yield "Differing items:"
        for k in diff:
            yield (
                highlighter(saferepr({k: left[k]}))
                + " != "
                + highlighter(saferepr({k: right[k]}))
            )
    extra_left = set_left - set_right
    len_extra_left = len(extra_left)
    if len_extra_left:
        yield f"Left contains {len_extra_left} more item{'' if len_extra_left == 1 else 's'}:"
        yield from highlighter(
            pprint.pformat({k: left[k] for k in extra_left})
        ).splitlines()
    extra_right = set_right - set_left
    len_extra_right = len(extra_right)
    if len_extra_right:
        yield f"Right contains {len_extra_right} more item{'' if len_extra_right == 1 else 's'}:"
        yield from highlighter(
            pprint.pformat({k: right[k] for k in extra_right})
        ).splitlines()
