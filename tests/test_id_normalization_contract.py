"""Drift guard for the node-ID normalization contract.

Three independent producers must agree on node IDs or the graph splits one entity
into disconnected ghost nodes: the AST extractor (``extract._make_id``), the
semantic subagents (the skill prompt's node-ID spec), and the graph builder
(``build._normalize_id``, which reconciles edge endpoints). The recipe used to be
copy-pasted into ``_make_id`` and ``_normalize_id`` and kept in sync only by
mirrored docstrings — exactly how the recurring ID-drift bug class crept in
(#811 Unicode collapse, #550 same-filename collisions, #1033 AST-vs-LLM file-node
mismatch, #1104).

Both callers now delegate to :mod:`graphify.ids`, so they share one
implementation and cannot diverge. These tests lock that contract: if a future
change re-forks the normalization (a new local helper, an inlined regex, a
dropped ``casefold``), they fail.
"""
import re

import pytest

from graphify.build import _normalize_id
from graphify.extract import _make_id
from graphify.ids import make_id, normalize_id

# Inputs that previously diverged or are easy to get wrong. The single-part form
# of `_make_id` must equal `_normalize_id` for every one of these.
CONTRACT_CASES = [
    "Session_ValidateToken",      # casing
    "session.validate-token",     # punctuation -> underscore
    "foo__bar..baz",              # repeated separators collapse
    "  Leading_Trailing__  ",     # strip stray underscores/space
    "A/B\\C",                     # path separators both directions
    "MixedCASE",                  # #811: casefold
    "café",                       # composed accented Latin (NFKC)
    "café",                 # decomposed e + combining acute -> same as 'café'
    "日本語クラス",                  # #811: CJK letters survive, not collapsed
    "Кириллица",                  # Cyrillic survives
    "naïve_Über",                 # mixed accented Latin
    "x_c1",                       # must NOT be treated as a chunk suffix here
    "__dunder__",                 # leading/trailing underscores stripped
    "tab\tnewline\nspace ",       # whitespace runs -> single underscore
]


@pytest.mark.parametrize("raw", CONTRACT_CASES)
def test_make_id_matches_normalize_id(raw):
    """The AST id-maker and the builder's reconciler must agree, char for char."""
    assert _make_id(raw) == _normalize_id(raw), (
        f"ID drift for {raw!r}: extract._make_id -> {_make_id(raw)!r} but "
        f"build._normalize_id -> {_normalize_id(raw)!r}"
    )


@pytest.mark.parametrize("raw", CONTRACT_CASES)
def test_normalize_id_is_idempotent(raw):
    once = normalize_id(raw)
    assert normalize_id(once) == once, f"normalize_id not idempotent for {raw!r}"


def test_make_id_joins_then_normalizes():
    """Multi-part make_id == normalize_id of the joined parts (the builder only
    ever sees the joined string, so these must coincide)."""
    parts = ("auth", "session.py", "ValidateToken")
    assert make_id(*parts) == normalize_id("_".join(parts))
    # Documented spec example.
    assert make_id("src/auth/session.py".split("/")[-2], "session", "ValidateToken") == \
        "auth_session_validatetoken"


def test_unicode_identifiers_do_not_collapse_to_empty():
    """#811: non-ASCII identifiers must yield distinct, non-empty IDs rather than
    collapsing to a single per-file node."""
    a = _make_id("クラスА")
    b = _make_id("クラスB")
    assert a and b and a != b


def test_normalized_ids_are_safe_node_ids():
    """Output is lowercase and contains no path/punctuation separators."""
    for raw in CONTRACT_CASES:
        out = normalize_id(raw)
        assert out == out.casefold()
        assert not re.search(r"[./\\\s]", out), f"unsafe char in id {out!r}"
        assert not out.startswith("_") and not out.endswith("_")


def test_both_callers_share_one_implementation():
    """Guard against re-forking: the two public callers must resolve to the same
    underlying function object as graphify.ids.normalize_id."""
    # build._normalize_id is imported directly from graphify.ids.
    assert _normalize_id is normalize_id
    # extract._make_id wraps make_id; prove it round-trips through the shared core.
    assert _make_id("Foo.Bar") == normalize_id("Foo.Bar")
    # The other two live ID producers — MCP config ingestion and bash symbol
    # resolution — must also resolve to the shared recipe, or the "single source
    # of truth" leaks back into copy-pasted forks (#1378).
    from graphify.mcp_ingest import _make_id as _mcp_make_id
    from graphify.symbol_resolution import _bash_make_id
    for fn in (_make_id, _mcp_make_id, _bash_make_id):
        assert fn("Foo.Bar", "baz") == make_id("Foo.Bar", "baz")
        assert fn("Ångström", "Ⅳ") == make_id("Ångström", "Ⅳ")


# Optional property-based fuzzing — hypothesis is a dev dependency. Skip cleanly
# if it is unavailable so the deterministic cases above still run everywhere.
hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given  # noqa: E402
from hypothesis import strategies as st  # noqa: E402


@given(st.text())
def test_property_make_id_equals_normalize_id(s):
    assert _make_id(s) == _normalize_id(s)


@given(st.text())
def test_property_normalize_id_idempotent(s):
    once = normalize_id(s)
    assert normalize_id(once) == once
