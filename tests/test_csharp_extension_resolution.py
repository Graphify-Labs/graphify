"""Production behaviour for C# extension-call binding (#4828).

Ground truth lives in ``tests/csharp_extension_harness.py``: ``expect`` edges must
exist in the real pipeline output, ``forbid`` edges must not. ``STAGE_FIXTURES``
names the fixtures the pass is required to satisfy *at this stage* of the fix;
the forbidden-edge tests run against every fixture from the first stage, so a
later stage can only add recall, never a false edge.
"""
from __future__ import annotations

import pytest

from tests.csharp_extension_harness import (
    FIXTURES,
    expected_pairs,
    graph_bindings,
)

FIXTURE_IDS = list(FIXTURES)

# Stage 1: in-corpus receivers, scope, assignability, poison, arity.
# Stage 2: out-of-corpus receivers guarded by the BCL/regular-name rules.
# Stage 3: untyped/chained receivers.
STAGE_FIXTURES = {
    "domain_cross_file",
    "same_file",
    "arity",
    "type_param_vs_class",
    "base_and_interface",
    "inner_scope_wins",
    "instance_wins",
    # stage 2: out-of-corpus receivers (primitives, third-party types, `this T`)
    "primitive_and_thirdparty",
    "generic_wildcard",
    # stage 3: untyped/chained receivers
    "issue_repro",
}


@pytest.mark.parametrize("name", FIXTURE_IDS)
def test_production_never_emits_a_forbidden_edge(name):
    result = graph_bindings(name)
    assert result["violations"] == set(), sorted(result["violations"])


@pytest.mark.parametrize("name", FIXTURE_IDS)
def test_production_invents_no_call_site(name):
    assert graph_bindings(name)["phantoms"] == []


@pytest.mark.parametrize("name", sorted(STAGE_FIXTURES))
def test_production_binds_the_decidable_extension_calls(name):
    result = graph_bindings(name)
    missing = expected_pairs(name) - result["bindings"]
    assert not missing, f"{name}: missing {sorted(missing)}"


def test_extension_edge_is_inferred_at_the_call_site():
    from tests.csharp_extension_harness import corpus

    data = corpus("domain_cross_file")
    by_id = {n["id"]: n for n in data["nodes"]}
    paint_calls = [
        e for e in data["edges"]
        if e.get("relation") == "calls"
        and by_id.get(e.get("target"), {}).get("label") == ".Paint()"
    ]
    assert len(paint_calls) == 2
    assert {e["source_location"] for e in paint_calls} == {"L5", "L6"}
    for edge in paint_calls:
        assert edge["confidence"] == "INFERRED"
        assert edge["confidence_score"] == 0.85
        assert edge["context"] == "call"


def test_instance_member_wins_over_a_same_named_extension():
    """`Cache.GetValue()` is nominal; the extension of the same name must not win."""
    result = graph_bindings("instance_wins")
    assert ("// E1", ("Cache.cs", "// D1")) in result["bindings"]
    assert ("// E1", ("Cache.cs", "// D2")) not in result["bindings"]


def test_static_form_is_never_rebound_to_the_extension():
    """`Conv.ToInt32(x)` names its type in source and is bound by the nominal pass."""
    result = graph_bindings("static_class_receiver")
    assert ("// B1", ("E.cs", "// D1")) in result["bindings"]
    assert ("// B1", ("E.cs", "// D2")) not in result["bindings"]


def test_ambiguity_binds_nothing():
    result = graph_bindings("ambiguous_same_scope")
    assert not any(marker == "// E1" for marker, _target in result["bindings"])


def test_out_of_scope_extension_binds_nothing():
    result = graph_bindings("out_of_scope")
    assert not any(marker == "// E1" for marker, _target in result["bindings"])


def test_unresolved_base_poisons_the_lookup():
    result = graph_bindings("unresolved_base_poison")
    assert not any(marker == "// E1" for marker, _target in result["bindings"])


def test_out_of_corpus_receiver_binds_through_the_guarded_rung():
    """`string.Mask()`, `int.Twice()` and a third-party receiver all bind."""
    result = graph_bindings("primitive_and_thirdparty")
    for marker, target in (
        ("// E1", ("Ext.cs", "// D1")),
        ("// E2", ("Ext.cs", "// D2")),
        ("// E3", ("Ext.cs", "// D3")),
    ):
        assert (marker, target) in result["bindings"], marker


def test_out_of_corpus_extension_edge_is_scored_lower():
    from tests.csharp_extension_harness import corpus

    data = corpus("primitive_and_thirdparty")
    by_id = {n["id"]: n for n in data["nodes"]}
    scores = {
        by_id[e["target"]]["label"]: e["confidence_score"]
        for e in data["edges"]
        if e.get("relation") == "calls"
        and by_id.get(e["target"], {}).get("metadata", {}).get("extension")
    }
    assert scores[".Mask()"] == 0.75
    assert scores[".Twice()"] == 0.75


def test_bcl_member_name_on_an_undeclared_type_is_not_bound():
    """`PropertyInfo.GetValue(obj)` is an instance call; the corpus cannot prove
    otherwise, so the deny-list refuses the same-named extension."""
    result = graph_bindings("bcl_name_cost")
    assert not any(marker == "// E1" for marker, _target in result["bindings"])


def test_open_generic_extension_applies_only_as_a_wildcard():
    result = graph_bindings("generic_wildcard")
    assert ("// E1", ("Gen.cs", "// D1")) in result["bindings"]
    # The concrete class T keeps winning over the generic `this T` declaration.
    concrete = graph_bindings("type_param_vs_class")
    assert ("// E1", ("T.cs", "// D1")) in concrete["bindings"]
    assert ("// E1", ("T.cs", "// D2")) not in concrete["bindings"]


def test_chained_receiver_binds_when_the_name_is_unique():
    """The issue's `v.ToString().Mask()` line: no receiver type to check, so the
    guarded untyped rung is the only possible proof."""
    result = graph_bindings("issue_repro")
    assert ("// E1", ("Ext.cs", "// D1")) in result["bindings"]
    assert ("// E2", ("Ext.cs", "// D1")) in result["bindings"]


def test_untyped_rung_refuses_a_name_a_regular_method_uses():
    result = graph_bindings("untyped_regular_name")
    assert not any(marker == "// F1" for marker, _target in result["bindings"])


def test_untyped_rung_refuses_a_capitalized_type_receiver():
    """`Conv.ToInt32(x)` names a type; the extension must not be considered."""
    result = graph_bindings("static_class_receiver")
    assert ("// B1", ("E.cs", "// D2")) not in result["bindings"]
