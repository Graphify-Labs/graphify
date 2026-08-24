"""Every INFERRED edge the AST extractor emits must carry a rubric score.

`references/extraction-spec.md` is explicit:

    confidence_score is REQUIRED on every edge - never omit it, never use 0.5
    as a default
    - INFERRED edges: pick exactly ONE value from this set — never 0.5:
        0.95 / 0.85 / 0.75 / 0.65 / 0.55

The AST extractor honoured neither half. Some sites emitted no
`confidence_score` at all, which fell through to `_CONFIDENCE_SCORE_DEFAULTS`
and landed on exactly the 0.5 the rubric rules out; others hardcoded 0.8, which
is not in the discrete set. On graphify's own package that was 128 of 128
INFERRED edges — 54 missing a score and 74 at 0.8 (#2813).

The tiers are deliberately NOT changed here. The reporter's other option was to
promote AST `uses` edges to EXTRACTED/1.0, which is a semantic judgement about
what the extractor knows; snapping the scores onto the documented scale fixes
the stated violation without making that call.
"""
from pathlib import Path

import pytest

from graphify.export import _CONFIDENCE_SCORE_DEFAULTS

# The discrete INFERRED set from references/extraction-spec.md.
RUBRIC = {0.55, 0.65, 0.75, 0.85, 0.95}

SRC = Path(__file__).resolve().parent.parent / "graphify"


def _extract(tmp_path, name, body):
    from graphify.extract import extract
    f = tmp_path / name
    f.write_text(body, encoding="utf-8")
    return extract([f], root=tmp_path)


def _inferred(res):
    return [e for e in res.get("edges", []) if e.get("confidence") == "INFERRED"]


# ---------------------------------------------------------------------------
# The default
# ---------------------------------------------------------------------------

def test_the_inferred_default_is_not_the_forbidden_value():
    assert _CONFIDENCE_SCORE_DEFAULTS["INFERRED"] != 0.5


def test_every_default_that_can_apply_to_an_inferred_edge_is_on_the_rubric():
    assert _CONFIDENCE_SCORE_DEFAULTS["INFERRED"] in RUBRIC


def test_extracted_and_ambiguous_defaults_are_unchanged():
    """The fix is scoped to INFERRED; the other two tiers keep their values."""
    assert _CONFIDENCE_SCORE_DEFAULTS["EXTRACTED"] == 1.0
    assert _CONFIDENCE_SCORE_DEFAULTS["AMBIGUOUS"] == 0.2


# ---------------------------------------------------------------------------
# No emission site ships an off-rubric literal
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rel_path", [
    "extract.py",
    "symbol_resolution.py",
    "extractors/engine.py",
    "extractors/resolution.py",
])
def test_no_module_hardcodes_an_off_rubric_inferred_score(rel_path):
    """0.8 was the value in the tree and is not on the scale. Catch it and the
    forbidden 0.5 as literals, so a future edit cannot reintroduce either."""
    text = (SRC / rel_path).read_text(encoding="utf-8")
    for forbidden in ('"confidence_score": 0.8,', '"confidence_score": 0.5,',
                      "confidence_score = 0.8\n", "confidence_score = 0.5\n"):
        assert forbidden not in text, f"{rel_path} still emits {forbidden.strip()}"


# ---------------------------------------------------------------------------
# End to end
# ---------------------------------------------------------------------------

def test_python_indirect_call_edges_carry_a_rubric_score(tmp_path):
    """A function passed by name as an argument — the indirect_call path."""
    res = _extract(tmp_path, "m.py", (
        "def handler():\n    return 1\n\n"
        "def register(cb):\n    return cb\n\n"
        "def wire():\n    return register(handler)\n"
    ))
    inferred = _inferred(res)
    if not inferred:
        pytest.skip("this build produced no INFERRED edges for the fixture")
    for e in inferred:
        assert e.get("confidence_score") in RUBRIC, e


def test_no_inferred_edge_is_left_without_a_score(tmp_path):
    res = _extract(tmp_path, "m.py", (
        "def handler():\n    return 1\n\n"
        "def register(cb):\n    return cb\n\n"
        "def wire():\n    return register(handler)\n"
    ))
    for e in _inferred(res):
        assert e.get("confidence_score") is not None, (
            f"edge would inherit the default instead of stating a score: {e}")


def test_extracted_edges_still_score_one(tmp_path):
    """The other half of the rubric must not drift while fixing this one."""
    res = _extract(tmp_path, "m.py", "def a():\n    return 1\n\ndef b():\n    return a()\n")
    for e in res.get("edges", []):
        if e.get("confidence") == "EXTRACTED" and "confidence_score" in e:
            assert e["confidence_score"] == 1.0, e
