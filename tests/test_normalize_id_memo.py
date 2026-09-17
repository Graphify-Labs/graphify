"""normalize_id is memoized without changing its result (#perf).

normalize_id is a pure, deterministic str->str transform (up to six
casefold+NFKC iterations plus two regex passes) that every node id flows
through via make_id, almost always on a repeating handful of stems and
identifiers. It is now lru_cached; the cache must not change any result and
must preserve the documented invariants (idempotent, caseless-stable,
\\w-only output).
"""

import re
import unicodedata

from graphify.ids import normalize_id


def _reference(s: str) -> str:
    """The pre-memo implementation, verbatim, as an equivalence oracle."""
    cur = s
    for _ in range(6):
        nxt = unicodedata.normalize("NFKC", cur.casefold())
        if nxt == cur:
            break
        cur = nxt
    cur = re.sub(r"[^\w]+", "_", cur, flags=re.UNICODE)
    cur = re.sub(r"_+", "_", cur)
    return cur.strip("_")


CASES = [
    "", "a", "MyClass", "handle_click", "handleClick", "src/module.py",
    "__dunder__", "a.b.c", "café", "résumé", "İstanbul", "ΐβγ",
    "A_b-c d", "___", "...", "1:/x", "Foo::Bar", "naïve", "straße",
    "  spaced  ", "tab\tsep", "mixedCASE_123",
]


def test_matches_the_unmemoized_reference():
    for s in CASES:
        assert normalize_id(s) == _reference(s), repr(s)


def test_documented_invariants_hold():
    for s in CASES:
        n = normalize_id(s)
        assert normalize_id(n) == n, f"not idempotent: {s!r}"
        assert normalize_id(s) == normalize_id(s.casefold()), f"not caseless-stable: {s!r}"
        assert re.fullmatch(r"[\w]*", n), f"non-word chars survived: {s!r} -> {n!r}"


def test_repeated_inputs_are_cached():
    normalize_id.cache_clear()
    for _ in range(100):
        normalize_id("MyRepeatedIdentifier")
    info = normalize_id.cache_info()
    assert info.misses == 1 and info.hits == 99, info


def test_distinct_inputs_map_distinctly_through_cache():
    normalize_id.cache_clear()
    a = normalize_id("Alpha")
    b = normalize_id("Beta")
    # Re-fetch from cache — must return each input's own result, not a shared one.
    assert normalize_id("Alpha") == a == "alpha"
    assert normalize_id("Beta") == b == "beta"
    assert a != b
