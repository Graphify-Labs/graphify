"""is_absolute_any_platform: memoized, semantics byte-identical (#perf).

The pipeline asks this of the same few hundred stored paths tens of thousands
of times, and each uncached call built two pathlib objects (PurePosixPath +
PureWindowsPath) to read one flag. It is now memoized with a POSIX-first
shortcut; the answer is a pure function of the string, so the result must match
the prior `PurePosixPath(s).is_absolute() or PureWindowsPath(s).is_absolute()`
exactly.
"""

import random
from pathlib import PurePosixPath, PureWindowsPath

from graphify.paths import (
    _is_absolute_any_platform_str,
    is_absolute_any_platform,
)


def _reference(p):
    if not p:
        return False
    s = str(p)
    return PurePosixPath(s).is_absolute() or PureWindowsPath(s).is_absolute()


_SEGS = ["", "a", "b", "..", ".", "C:", "c:", "Z:", "1:", "server", "share",
         "x.py", "http:"]
_SEPS = ["/", "\\", "//", "\\\\", "///"]


def test_matches_reference_on_named_edge_cases():
    cases = [
        "", "a", "a/b", "src/module.py", "./rel", "../up",
        "/abs", "/", "//unc/share", "///t", "//server/share",
        r"C:\Users\x", "C:/Users/x", "C:rel", "C:", "c:/lower",
        r"\\server\share", r"\single", "/single", r"\\?\C:\long",
        "Z:\\", "1:/notdrive", "foo:bar", "http://x/y", None,
    ]
    for c in cases:
        assert is_absolute_any_platform(c) == _reference(c), repr(c)


def test_matches_reference_under_fuzz():
    cases = set()
    for a in _SEPS:
        for b in _SEGS:
            for c in _SEPS + [""]:
                for d in _SEGS:
                    cases.add(a + b + c + d)
    rng = random.Random(0)
    for _ in range(5000):
        n = rng.randint(0, 5)
        cases.add("".join(rng.choice(_SEPS + _SEGS) for _ in range(n)))
    for c in cases:
        assert is_absolute_any_platform(c) == _reference(c), repr(c)


def test_repeated_calls_are_memoized():
    _is_absolute_any_platform_str.cache_clear()
    for _ in range(100):
        is_absolute_any_platform("src/module.py")
    info = _is_absolute_any_platform_str.cache_info()
    assert info.misses == 1 and info.hits == 99, info


def test_none_and_empty_short_circuit_without_caching():
    _is_absolute_any_platform_str.cache_clear()
    assert is_absolute_any_platform(None) is False
    assert is_absolute_any_platform("") is False
    # The guard returns before the memoized core, so nothing was cached.
    assert _is_absolute_any_platform_str.cache_info().misses == 0


def test_posix_arm_is_exact_startswith_slash():
    """The shortcut must equal PurePosixPath(s).is_absolute() on the POSIX arm."""
    for s in ["/x", "/", "//x", "x", "C:/x", ""]:
        assert (s.startswith("/")) == PurePosixPath(s).is_absolute()
