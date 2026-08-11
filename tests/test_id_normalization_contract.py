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
    # #2614: casefolding these EXPANDS them into a base letter plus a combining
    # mark. With casefold last, the mark landed in the id after the [^\w] filter
    # had already run, so the id carried a non-word character and a second pass
    # changed it. Turkish identifiers are the common real-world case.
    "İ",                     # İ  -> i + U+0307
    "İslemYap",              # İslemYap
    "fileİname",             # İ mid-identifier
    "İı_Mixed",         # İ with dotless ı
    "Große",                 # ß -> ss (length-changing casefold)
    "ẞ",                     # ẞ capital sharp s -> ss
]

# Characters whose casefold expands or recomposes — the exact class that broke
# the contract in #2614. Kept separate from CONTRACT_CASES because a few of them
# (e.g. U+01F0) legitimately normalize to a precomposed character that is not
# equal to its own casefold, which the lowercase assertion below would reject.
CASE_EXPANDING_CHARS = [
    "İ",  # İ  LATIN CAPITAL LETTER I WITH DOT ABOVE -> i + U+0307
    "ǰ",  # ǰ  casefold expands, NFKC then recomposes it
    "ͅ",  # ͅ   COMBINING GREEK YPOGEGRAMMENI -> ι
    "ͺ",  # ͺ   GREEK YPOGEGRAMMENI -> space + ι
    "ẞ",  # ẞ  -> ss
    "ῗ",  # ῗ   iota with dialytika and perispomeni
    "ὒ",  # ὒ   upsilon with psili and varia
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


@pytest.mark.parametrize("ch", CASE_EXPANDING_CHARS)
def test_case_expanding_chars_yield_word_only_ids(ch):
    """#2614: the postcondition the old recipe silently broke.

    ``normalize_id`` must emit only ``\\w`` characters and ``_``. Casefolding
    last let the combining mark that ``İ``.casefold() produces slip past the
    ``[^\\w]+`` filter, so ids carried U+0307 — invisible in most terminals, and
    a second normalization pass then rewrote it to ``_``.
    """
    out = normalize_id(f"a{ch}b")
    assert not re.search(r"[^\w]", out.replace("_", "")), (
        f"normalize_id({ch!r}) -> {out!r} contains a non-word character "
        f"({[hex(ord(c)) for c in out]})"
    )


@pytest.mark.parametrize("ch", CASE_EXPANDING_CHARS)
def test_case_expanding_chars_are_idempotent(ch):
    once = normalize_id(f"a{ch}b")
    assert normalize_id(once) == once, (
        f"normalize_id not idempotent for {ch!r}: {once!r} -> {normalize_id(once)!r}"
    )


@pytest.mark.parametrize("ch", CASE_EXPANDING_CHARS)
def test_case_expanding_chars_normalize_case_insensitively(ch):
    """The point of casefolding: upper and lower spellings must land on one id.

    Asserted instead of ``out == out.casefold()`` because casefold and NFKC do
    not commute — ``ǰ`` normalizes to the precomposed U+01F0, which is lowercase
    but is not equal to its own casefold. Case-insensitivity is the property the
    graph actually depends on.
    """
    assert normalize_id(f"a{ch.upper()}b") == normalize_id(f"a{ch.lower()}b")


def test_turkish_identifier_ids_match_between_extractor_and_builder():
    """#2614 end to end: the drift that split a Turkish symbol into ghost nodes.

    ``make_id`` minted ``islem_i̇slemyap`` (with U+0307) while the builder's
    re-normalization produced ``islem_i_slemyap``, so ``_semantic_id_remap``'s
    ``startswith(new_stem)`` check missed and the re-key silently no-opped.
    """
    stem, symbol = "islem", "İslemYap"
    minted = make_id(stem, symbol)
    assert _normalize_id(minted) == minted, "builder re-normalization drifts from make_id"
    assert minted.startswith(make_id(stem) + "_"), (
        "symbol id lost its file stem prefix, so the re-key cannot relate them"
    )
    assert minted == "islem_i_slemyap"


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


# The plain st.text() property above already existed when #2614 shipped, and did
# not catch it: the bug needs one specific codepoint (U+0130) out of ~1.1M, which
# a uniform draw essentially never produces. These strategies bias the search
# toward the characters that actually stress the recipe — case-expanding letters
# and combining marks — so the class stays covered rather than relying on luck.
_stress_alphabet = st.one_of(
    st.sampled_from(CASE_EXPANDING_CHARS),
    st.sampled_from("Iıİi_.-/aZ0"),        # Turkish dotted/dotless pairs + separators
    st.characters(categories=["Lu", "Ll", "Lt", "Mn", "Nd", "Pc"]),
)
_stress_text = st.text(alphabet=_stress_alphabet, max_size=12)


@given(_stress_text)
def test_property_normalize_id_idempotent_under_case_stress(s):
    once = normalize_id(s)
    assert normalize_id(once) == once, f"not idempotent for {s!r} -> {once!r}"


@given(_stress_text)
def test_property_normalize_id_emits_only_word_chars(s):
    """The postcondition #2614 violated: only \\w and _ may survive."""
    out = normalize_id(s)
    assert not re.search(r"[^\w]", out.replace("_", "")), (
        f"normalize_id({s!r}) -> {out!r} leaked a non-word character"
    )


@given(_stress_text)
def test_property_normalize_id_agrees_with_its_own_caseless_form(s):
    """Feeding an already-caseless string must not change the answer.

    Deliberately NOT ``normalize_id(s.upper()) == normalize_id(s.lower())``:
    ``str.upper()`` is locale-independent and lossy, so Turkish dotless ``ı``
    uppercases to ``I`` and then casefolds to ``i`` — the two spellings are
    genuinely different characters, not a normalization failure. Caseless
    equivalence via ``casefold`` is the invariant the graph relies on.
    """
    assert normalize_id(s) == normalize_id(s.casefold())
