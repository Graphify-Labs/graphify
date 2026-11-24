"""PHP member calls that `_resolve_php_member_calls` dropped although the target is
plain from the source.

- A file mapped to PHP through `.graphifyrc` (`language.inc=php`) got no static-call
  edges: the resolver checked the literal `.php` suffix.
- `$this->m()` was never bound to the enclosing class, and no scope looked a method
  up the `inherits` chain, so an inherited `$this->m()` and a two-hop `parent::m()`
  produced no edge.
- A second call to the same method from the same caller lost its line: the resolver
  kept one edge per caller and callee, and `_merge_decl_def_classes` deduped every
  edge in the corpus by caller and callee once a C++ header member merged.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from graphify.build import build_from_json
from graphify.extract import _resolve_php_member_calls, extract
from graphify.rcfile import set_language_overrides


@pytest.fixture(autouse=True)
def reset_overrides():
    set_language_overrides(None)
    yield
    set_language_overrides(None)


def _extract(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    paths = [tmp_path / n for n in files if not n.startswith(".")]
    return extract(paths, cache_root=Path(tempfile.mkdtemp()), root=tmp_path, parallel=False)


def _calls(result) -> dict[tuple[str, str], list[dict]]:
    labels = {n["id"]: n["label"] for n in result["nodes"]}
    found: dict[tuple[str, str], list[dict]] = {}
    for e in result["edges"]:
        if e["relation"] == "calls":
            found.setdefault((labels[e["source"]], labels[e["target"]]), []).append(e)
    return found


def _owner_of(result, method_nid: str) -> str:
    labels = {n["id"]: n["label"] for n in result["nodes"]}
    owners = [labels[e["source"]] for e in result["edges"]
              if e["relation"] == "method" and e["target"] == method_nid]
    assert len(owners) == 1, owners
    return owners[0]


# ---------------------------------------------------------------------------
# A remapped extension is PHP too
# ---------------------------------------------------------------------------

def test_static_calls_resolve_in_a_file_mapped_to_php(tmp_path):
    result = _extract(tmp_path, {
        ".graphifyrc": "language.inc=php\n",
        "Base.inc": (
            "<?php\nclass Base {\n"
            "    public static function setup() { return 0; }\n}\n"),
        "Helper.inc": (
            "<?php\nclass Helper {\n"
            "    public static function format($x) { return $x; }\n}\n"),
        "Child.inc": (
            "<?php\nclass Child extends Base {\n"
            "    public function run($x) { return Helper::format($x); }\n"
            "    public function again() { return self::run(1); }\n"
            "    public function boot() { return parent::setup(); }\n}\n"),
    })
    calls = _calls(result)
    assert (".run()", ".format()") in calls
    assert (".again()", ".run()") in calls
    assert (".boot()", ".setup()") in calls
    assert all(e["confidence"] == "EXTRACTED" for edges in calls.values() for e in edges)


# ---------------------------------------------------------------------------
# $this and the inherits chain
# ---------------------------------------------------------------------------

def test_this_call_to_an_inherited_method_binds_the_parent_method(tmp_path):
    result = _extract(tmp_path, {
        "Base.php": (
            "<?php\nclass Base {\n"
            "    public function helper() { return 1; }\n}\n"),
        "Child.php": (
            "<?php\nclass Child extends Base {\n"
            "    public function run() { return $this->helper(); }\n}\n"),
        "Decoy.php": (
            "<?php\nclass Decoy {\n"
            "    public function helper() { return 2; }\n}\n"),
    })
    edges = _calls(result).get((".run()", ".helper()"), [])
    assert len(edges) == 1
    assert _owner_of(result, edges[0]["target"]) == "Base"
    assert edges[0]["confidence"] == "EXTRACTED"


def test_parent_call_two_levels_up_binds_the_grandparent_method(tmp_path):
    result = _extract(tmp_path, {
        "Base.php": (
            "<?php\nclass Base {\n"
            "    public function setup() { return 1; }\n}\n"),
        "Middle.php": "<?php\nclass Middle extends Base {\n}\n",
        "Leaf.php": (
            "<?php\nclass Leaf extends Middle {\n"
            "    public function boot() { return parent::setup(); }\n}\n"),
    })
    edges = _calls(result).get((".boot()", ".setup()"), [])
    assert len(edges) == 1
    assert _owner_of(result, edges[0]["target"]) == "Base"


def test_nearest_declaring_class_wins(tmp_path):
    result = _extract(tmp_path, {
        "Base.php": (
            "<?php\nclass Base {\n"
            "    public function helper() { return 1; }\n}\n"),
        "Middle.php": (
            "<?php\nclass Middle extends Base {\n"
            "    public function helper() { return 2; }\n}\n"),
        "Leaf.php": (
            "<?php\nclass Leaf extends Middle {\n"
            "    public function run() { return $this->helper(); }\n}\n"),
    })
    edges = _calls(result).get((".run()", ".helper()"), [])
    assert len(edges) == 1
    assert _owner_of(result, edges[0]["target"]) == "Middle"


def test_this_call_with_no_declaring_class_in_the_chain_binds_nothing(tmp_path):
    result = _extract(tmp_path, {
        "Base.php": "<?php\nclass Base {\n}\n",
        "Child.php": (
            "<?php\nclass Child extends Base {\n"
            "    public function run() { return $this->helper(); }\n}\n"),
        "Decoy.php": (
            "<?php\nclass Decoy {\n"
            "    public function helper() { return 2; }\n}\n"),
    })
    assert (".run()", ".helper()") not in _calls(result)


_TRAIT_AND_PARENT = {
    "Base.php": (
        "<?php\nclass Base {\n"
        "    public function helper() { return 1; }\n}\n"),
    "Mixin.php": (
        "<?php\ntrait Mixin {\n"
        "    public function helper() { return 2; }\n}\n"),
}


def test_a_trait_method_wins_over_the_inherited_one(tmp_path):
    """PHP runs the used trait's method, not the parent's."""
    result = _extract(tmp_path, {**_TRAIT_AND_PARENT, "Child.php": (
        "<?php\nclass Child extends Base {\n"
        "    use Mixin;\n"
        "    public function run() { return $this->helper(); }\n}\n")})
    edges = _calls(result).get((".run()", ".helper()"), [])
    assert len(edges) == 1
    assert _owner_of(result, edges[0]["target"]) == "Mixin"


def test_the_class_own_method_wins_over_its_trait(tmp_path):
    result = _extract(tmp_path, {**_TRAIT_AND_PARENT, "Child.php": (
        "<?php\nclass Child extends Base {\n"
        "    use Mixin;\n"
        "    public function helper() { return 3; }\n"
        "    public function run() { return $this->helper(); }\n}\n")})
    edges = _calls(result).get((".run()", ".helper()"), [])
    assert len(edges) == 1
    assert _owner_of(result, edges[0]["target"]) == "Child"


def test_a_method_from_a_trait_used_by_a_trait_is_found(tmp_path):
    result = _extract(tmp_path, {
        "Inner.php": (
            "<?php\ntrait Inner {\n"
            "    public function helper() { return 1; }\n}\n"),
        "Outer.php": "<?php\ntrait Outer {\n    use Inner;\n}\n",
        "Child.php": (
            "<?php\nclass Child {\n"
            "    use Outer;\n"
            "    public function run() { return $this->helper(); }\n}\n"),
    })
    edges = _calls(result).get((".run()", ".helper()"), [])
    assert len(edges) == 1
    assert _owner_of(result, edges[0]["target"]) == "Inner"


def _node(nid, label, source_file="a.php"):
    return {"id": nid, "label": label, "source_file": source_file}


def _resolve(edges, raw_overrides=None, source_file="a.php"):
    nodes = [_node("f", source_file, source_file), _node("child", "Child", source_file),
             _node("run", ".run()", source_file),
             _node("b1", "BaseOne", source_file), _node("b1_h", ".helper()", source_file),
             _node("b2", "BaseTwo", source_file), _node("b2_h", ".helper()", source_file)]
    edges = [{"source": "f", "target": t, "relation": "contains"} for t in ("child", "b1", "b2")] + [
        {"source": "child", "target": "run", "relation": "method"}] + edges
    raw = {"caller_nid": "run", "receiver": "this", "callee": "helper",
           "is_member_call": True, "source_file": source_file, "source_location": "L3",
           **(raw_overrides or {})}
    _resolve_php_member_calls([{"raw_calls": [raw]}], nodes, edges)
    return [e for e in edges if e["relation"] == "calls"]


_TWO_BASES = [
    {"source": "b1", "target": "b1_h", "relation": "method"},
    {"source": "b2", "target": "b2_h", "relation": "method"},
    {"source": "child", "target": "b1", "relation": "inherits"},
    {"source": "child", "target": "b2", "relation": "inherits"},
]


def test_a_tie_on_the_nearest_level_binds_nothing():
    """Two bases on one level both declare the method: no edge, as the Java
    resolver does."""
    assert _resolve(list(_TWO_BASES)) == []


def test_an_inherits_cycle_ends_without_an_edge():
    """`Child -> BaseOne -> Child` with no declaration: the walk stops."""
    assert _resolve([
        {"source": "child", "target": "b1", "relation": "inherits"},
        {"source": "b1", "target": "child", "relation": "inherits"},
    ]) == []


def test_a_member_call_outside_php_is_left_alone():
    one_base = [{"source": "b1", "target": "b1_h", "relation": "method"},
                {"source": "child", "target": "b1", "relation": "inherits"}]
    assert [e["target"] for e in _resolve(list(one_base))] == ["b1_h"]
    assert _resolve(list(one_base), source_file="a.py") == []


def test_this_with_a_scope_operator_stays_unresolved():
    """`$this::m()` is a dynamic scope, not `$this->m()`."""
    one_base = [{"source": "b1", "target": "b1_h", "relation": "method"},
                {"source": "child", "target": "b1", "relation": "inherits"}]
    assert _resolve(one_base, {"php_scoped": True}) == []


# ---------------------------------------------------------------------------
# Every call site keeps its line
# ---------------------------------------------------------------------------

_REPEAT = {
    "Helper.php": (
        "<?php\nclass Helper {\n"
        "    public static function format($x) { return $x; }\n}\n"),
    "Caller.php": (
        "<?php\nclass Caller {\n"
        "    public function run($x) {\n"
        "        $a = Helper::format($x);\n"
        "        $b = Helper::format($a);\n"
        "        return $b;\n"
        "    }\n}\n"),
}

# One C++ member declared in a header and defined in its `.cc` merges, which is
# what makes `_merge_decl_def_classes` run its corpus-wide edge dedup.
_HEADER_PAIR = {
    "store.h": "class Store {\npublic:\n    int size();\n};\n",
    "store.cc": '#include "store.h"\nint Store::size() { return 0; }\n',
}


def _repeat_sites(result) -> list[str]:
    return sorted(e["source_location"] for e in _calls(result).get((".run()", ".format()"), []))


@pytest.mark.parametrize("files", [_REPEAT, {**_REPEAT, **_HEADER_PAIR}],
                         ids=["php-only", "with-cpp-header-merge"])
def test_a_repeat_call_keeps_both_lines(tmp_path, files):
    result = _extract(tmp_path, files)
    assert _repeat_sites(result) == ["L4", "L5"]


def test_the_build_folds_the_repeat_call_into_also_seen(tmp_path):
    result = _extract(tmp_path, _REPEAT)
    graph = build_from_json(result, directed=True)
    (u, v), = [(u, v) for u, v, d in graph.edges(data=True)
               if d.get("relation") == "calls"
               and graph.nodes[u].get("label") == ".run()"
               and graph.nodes[v].get("label") == ".format()"]
    data = graph.edges[u, v]
    lines = {data.get("source_location")} | {s.get("source_location") for s in data.get("also_seen", [])}
    assert lines == {"L4", "L5"}


def test_the_header_merge_still_drops_its_own_twins(tmp_path):
    """The merge still removes the duplicate `contains`/`method` edges it creates."""
    result = _extract(tmp_path, _HEADER_PAIR)
    keys = [(e["source"], e["target"], e["relation"]) for e in result["edges"]
            if e["relation"] in ("contains", "method")]
    assert len(keys) == len(set(keys))
