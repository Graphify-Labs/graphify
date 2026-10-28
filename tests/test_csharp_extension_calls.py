"""Decision record: A/B comparison of candidate C# extension binders (#4828).

The production pass is chosen by measuring candidates against fixtures whose
ground truth is decidable from the C# spec. This module keeps the comparison
executable: it is what tells a future change that removing the scope check, the
unresolved-base poison, or the deny-list costs a false edge.

Candidates are applied to the graph as the *nominal* pipeline builds it
(``production_extension=False`` in the harness), so the numbers stay comparable
no matter which stage of the production fix has landed. The production behaviour
itself is covered by ``test_csharp_extension_resolution.py``.

Fixtures: ``expect`` must bind, ``forbid``/``forbid_pairs`` must not, ``optional``
is unknowable without a BCL symbol table and is never scored.
"""
from __future__ import annotations

import pytest

from tests.csharp_extension_harness import (
    FIXTURES,
    STRATEGY_IDS,
    STRATEGIES,
    expected_pairs,
    line_of,
    strategy_bindings,
)

FIXTURE_IDS = list(FIXTURES)

# Strategies that claim "no false edge anywhere". The others are deliberately
# imprecise (that is the property being measured) and are scored by the matrix.
PRECISE_STRATEGIES = [
    "S3_typed_assignable",
    "S5_roc_guarded",
    "S7_all_rungs",
    "S9_signature_parse",
]

# Per strategy, the fixtures it must get fully right. Everything else may
# under-bind (scored by the matrix) but may still not over-bind.
STRATEGY_RECALL: dict[str, set[str]] = {
    "S1_typed_exact": {"domain_cross_file", "same_file", "arity", "type_param_vs_class"},
    "S2_typed_exact_scope": {"domain_cross_file", "same_file", "arity", "type_param_vs_class"},
    "S3_typed_assignable": {
        "domain_cross_file", "same_file", "arity", "type_param_vs_class",
        "base_and_interface", "inner_scope_wins", "instance_wins",
    },
    "S4_roc_naive": {
        "domain_cross_file", "same_file", "arity", "type_param_vs_class",
        "base_and_interface", "inner_scope_wins", "instance_wins",
        "primitive_and_thirdparty", "generic_wildcard",
    },
    "S5_roc_guarded": {
        "domain_cross_file", "same_file", "arity", "type_param_vs_class",
        "base_and_interface", "inner_scope_wins", "instance_wins",
        "primitive_and_thirdparty", "generic_wildcard",
    },
    "S6_reporter_patch": {
        "domain_cross_file", "same_file", "arity", "type_param_vs_class",
        "instance_wins", "primitive_and_thirdparty", "generic_wildcard",
        "issue_repro",
    },
    "S7_all_rungs": {
        "domain_cross_file", "same_file", "arity", "type_param_vs_class",
        "base_and_interface", "inner_scope_wins", "instance_wins",
        "primitive_and_thirdparty", "generic_wildcard", "issue_repro",
    },
    "S9_signature_parse": {
        "domain_cross_file", "same_file", "arity", "base_and_interface",
        "inner_scope_wins", "instance_wins",
    },
}


# --------------------------------------------------------------------------- #
# fixture sanity
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("name", FIXTURE_IDS)
def test_fixture_markers_are_unambiguous(name):
    fixture = FIXTURES[name]
    bodies = "\n".join(fixture.files.values())
    import re as _re
    markers = _re.findall(r"//\s*[A-Z]\d+", bodies)
    for marker in set(markers):
        assert markers.count(marker) == 1, (name, marker, markers.count(marker))

    def source_of(marker):
        hits = [b for b in fixture.files.values() if marker in b]
        assert len(hits) == 1, (name, marker, len(hits))
        return hits[0]

    for call_marker, (t_file, t_marker) in fixture.expect.items():
        assert line_of(source_of(call_marker), call_marker)
        assert line_of(fixture.files[t_file], t_marker)
        assert call_marker not in fixture.forbid, (name, call_marker)

    for call_marker in fixture.forbid:
        assert line_of(source_of(call_marker), call_marker)

    for call_marker, (t_file, t_marker) in fixture.forbid_pairs.items():
        assert line_of(source_of(call_marker), call_marker)
        assert line_of(fixture.files[t_file], t_marker)
        assert fixture.expect.get(call_marker) != (t_file, t_marker)

    for call_marker in fixture.optional:
        assert line_of(source_of(call_marker), call_marker)


# --------------------------------------------------------------------------- #
# per-candidate sweep
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("strategy_id", PRECISE_STRATEGIES)
@pytest.mark.parametrize("name", FIXTURE_IDS)
def test_precise_strategy_emits_no_forbidden_edge(name, strategy_id):
    result = strategy_bindings(name, strategy_id)
    assert result["violations"] == set(), f"{strategy_id} on {name}"


@pytest.mark.parametrize("strategy_id", STRATEGY_IDS)
@pytest.mark.parametrize("name", FIXTURE_IDS)
def test_strategy_to_upholds_the_ground_truth(name, strategy_id):
    if strategy_id == "S0_baseline":
        assert strategy_bindings(name, strategy_id)["added"] == []
        return
    required = STRATEGY_RECALL.get(strategy_id, set())
    if name not in required:
        pytest.skip("under-binding is scored by the matrix test")
    result = strategy_bindings(name, strategy_id)
    assert expected_pairs(name) <= result["bindings"], (
        f"{strategy_id} on {name}: missing "
        f"{sorted(expected_pairs(name) - result['bindings'])}"
    )


# --------------------------------------------------------------------------- #
# the matrix
# --------------------------------------------------------------------------- #


def _score(strategy_id: str) -> dict:
    expected_total = 0
    correct = 0
    wrong: list = []
    for name in FIXTURE_IDS:
        fixture = FIXTURES[name]
        expected = expected_pairs(name)
        expected_total += len(expected)
        result = strategy_bindings(name, strategy_id)
        correct += len(expected & result["bindings"])
        for binding in result["bindings"] - expected:
            if binding[0] in fixture.optional:
                continue
            wrong.append((name, *binding))
        for edge in result["phantoms"]:
            wrong.append((name, "phantom", str(edge.get("target"))))
    return {
        "expected": expected_total,
        "correct": correct,
        "wrong": wrong,
        "recall": correct / expected_total if expected_total else 0.0,
        "precision": correct / (correct + len(wrong)) if (correct + len(wrong)) else 1.0,
    }


def test_strategy_matrix(capsys):
    scores = {sid: _score(sid) for sid in STRATEGY_IDS}
    lines = [
        f"{'strategy':26} {'hits':>5} {'expected':>9} {'wrong':>6} "
        f"{'recall':>7} {'precision':>10}"
    ]
    for sid in STRATEGY_IDS:
        s = scores[sid]
        lines.append(
            f"{sid:26} {s['correct']:5d} {s['expected']:9d} {len(s['wrong']):6d} "
            f"{s['recall']:7.3f} {s['precision']:10.3f}"
        )
    with capsys.disabled():
        print("\n" + "\n".join(lines))

    # Baseline proves the fixtures are not already passing: it can satisfy only
    # the ordinary static/instance calls, never an extension call.
    assert scores["S0_baseline"]["wrong"] == []
    assert scores["S0_baseline"]["correct"] < scores["S3_typed_assignable"]["correct"]

    # Each added rung is weakly better on recall.
    assert scores["S2_typed_exact_scope"]["recall"] >= scores["S1_typed_exact"]["recall"]
    assert scores["S3_typed_assignable"]["recall"] >= scores["S2_typed_exact_scope"]["recall"]
    assert scores["S5_roc_guarded"]["recall"] >= scores["S3_typed_assignable"]["recall"]
    assert scores["S7_all_rungs"]["recall"] >= scores["S5_roc_guarded"]["recall"]

    # The provable-only rung has no false edge anywhere in the corpus.
    for sid in PRECISE_STRATEGIES:
        assert scores[sid]["wrong"] == [], sid

    # Relaxing a rule costs precision: each of these is a documented trade.
    assert scores["S1_typed_exact"]["wrong"], "no-scope must bind an unimported extension"
    assert scores["S2_typed_exact_scope"]["wrong"], "no-poison must bind through an unknown base"
    assert scores["S4_roc_naive"]["wrong"], "no-deny-list must bind a BCL instance member"
    assert scores["S6_reporter_patch"]["wrong"], "reporter patch must bind out of scope / through a base"
    assert scores["S4_roc_naive"]["recall"] > scores["S5_roc_guarded"]["recall"]
    assert scores["S5_roc_guarded"]["recall"] > scores["S3_typed_assignable"]["recall"]


# --------------------------------------------------------------------------- #
# explicit discriminators: each proves the flag it names is what changed
# --------------------------------------------------------------------------- #


def _has(name: str, strategy_id: str, call_marker: str, target: tuple[str, str]) -> bool:
    return (call_marker, target) in strategy_bindings(name, strategy_id)["bindings"]


def test_scope_flag_is_what_excludes_an_unimported_extension():
    target = ("Other.cs", "// D1")
    assert _has("out_of_scope", "S1_typed_exact", "// E1", target)
    for sid in ("S2_typed_exact_scope", "S3_typed_assignable",
                "S5_roc_guarded", "S7_all_rungs"):
        assert not _has("out_of_scope", sid, "// E1", target), sid


def test_scope_level_is_what_picks_the_inner_extension():
    inner = ("Inner.cs", "// D2")
    outer = ("Outer.cs", "// D1")
    assert not _has("inner_scope_wins", "S1_typed_exact", "// E1", inner)
    assert _has("inner_scope_wins", "S3_typed_assignable", "// E1", inner)
    assert not _has("inner_scope_wins", "S3_typed_assignable", "// E1", outer)


def test_assignability_is_what_reaches_base_and_interface_extensions():
    base = ("Domain.cs", "// D1")
    iface = ("Domain.cs", "// D2")
    assert not _has("base_and_interface", "S2_typed_exact_scope", "// E1", base)
    assert not _has("base_and_interface", "S2_typed_exact_scope", "// E2", iface)
    assert _has("base_and_interface", "S3_typed_assignable", "// E1", base)
    assert _has("base_and_interface", "S3_typed_assignable", "// E2", iface)


def test_poison_flag_is_what_refuses_an_unknown_base():
    target = ("W.cs", "// D1")
    assert _has("unresolved_base_poison", "S2_typed_exact_scope", "// E1", target)
    assert not _has("unresolved_base_poison", "S3_typed_assignable", "// E1", target)


def test_out_of_corpus_rung_is_what_reaches_string_and_thirdparty():
    targets = {
        "// E1": ("Ext.cs", "// D1"),
        "// E2": ("Ext.cs", "// D2"),
        "// E3": ("Ext.cs", "// D3"),
    }
    for marker, target in targets.items():
        assert not _has("primitive_and_thirdparty", "S3_typed_assignable", marker, target), marker
        assert _has("primitive_and_thirdparty", "S5_roc_guarded", marker, target), marker


def test_deny_list_is_what_prevents_a_bcl_false_positive():
    """`PropertyInfo.GetValue(obj)`: the 2-arg extension fits the arity, so only
    the deny-list stands between the naive rung and a false edge."""
    target = ("E.cs", "// D2")
    assert _has("bcl_name_cost", "S4_roc_naive", "// E1", target)
    assert not _has("bcl_name_cost", "S5_roc_guarded", "// E1", target)


def test_untyped_rung_is_what_reaches_a_chained_receiver():
    target = ("Ext.cs", "// D1")
    assert not _has("issue_repro", "S5_roc_guarded", "// E2", target)
    assert _has("issue_repro", "S7_all_rungs", "// E2", target)
    # ... while the typed (primitive) receiver needs no untyped rung at all.
    assert _has("issue_repro", "S5_roc_guarded", "// E1", target)


def test_metadata_beats_signature_parsing_on_this_T():
    """Both `this T` declarations look identical in the signature text."""
    concrete = ("T.cs", "// D1")
    assert _has("type_param_vs_class", "S3_typed_assignable", "// E1", concrete)
    assert not _has("type_param_vs_class", "S9_signature_parse", "// E1", concrete)
    # The generic `this T` is the wildcard rung, reachable only with the
    # `extended_is_type_param` fact that the signature text cannot carry.
    wildcard = ("Gen.cs", "// D1")
    assert _has("generic_wildcard", "S5_roc_guarded", "// E1", wildcard)
    assert not _has("generic_wildcard", "S9_signature_parse", "// E1", wildcard)


def test_control_bare_name_reintroduces_the_god_node_edge():
    """The anti-pattern is real on this corpus, which is why it is rejected."""
    control = strategy_bindings("god_node_control", "S8_bare_name_control")
    assert ("// F1", ("Cache.cs", "// D1")) in control["bindings"]
    for sid in STRATEGY_IDS:
        if sid == "S8_bare_name_control":
            continue
        assert not _has("god_node_control", sid, "// F1", ("Cache.cs", "// D1")), sid
