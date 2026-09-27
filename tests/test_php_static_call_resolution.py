"""PHP `Class::method()` static calls must resolve to the actual method with
EXTRACTED confidence, not to a bare-name match on the class itself (#3872).

`scoped_call_expression` used the scope text (`Helper` in `Helper::format()`)
as the callee name instead of the method name, so the shared cross-file
bare-name pass bound every static call to whichever node happened to share
the class's label - almost always the class definition - and did so gated on
import evidence (INFERRED 0.85) even though the receiver class is named
explicitly in source. Same-namespace PHP classes never need a `use` import
for each other, so every same-namespace static call was stuck at INFERRED.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from graphify.extract import extract


def _extract(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    r = extract([tmp_path / n for n in files], cache_root=Path(tempfile.mkdtemp()),
                root=tmp_path, parallel=False)
    labels = {n["id"]: n["label"] for n in r["nodes"]}
    call_edges = [e for e in r["edges"] if e["relation"] == "calls"]
    calls = {(labels[e["source"]], labels[e["target"]]): e for e in call_edges}
    return calls, r


def test_same_namespace_static_call_is_extracted_not_inferred(tmp_path):
    """The exact shape from #3872: a same-namespace static call has no `use`
    import (none needed), so it must not be penalized as INFERRED."""
    calls, _ = _extract(tmp_path, {
        "Helper.php": (
            "<?php\nnamespace App;\nclass Helper {\n"
            "    public static function sanitize($x) { return $x; }\n}\n"),
        "Caller.php": (
            "<?php\nnamespace App;\nclass Caller {\n"
            "    public function run($x) { return Helper::sanitize($x); }\n}\n"),
    })
    edge = calls.get((".run()", ".sanitize()"))
    assert edge is not None
    assert edge["confidence"] == "EXTRACTED"
    assert edge["confidence_score"] == 1.0


def test_self_and_static_scope_resolve_to_enclosing_class(tmp_path):
    calls, _ = _extract(tmp_path, {"Widget.php": (
        "<?php\nnamespace App;\nclass Widget {\n"
        "    public static function build() { return self::helper(); }\n"
        "    public static function render() { return static::helper(); }\n"
        "    public static function helper() { return 1; }\n}\n")})
    assert (".build()", ".helper()") in calls
    assert (".render()", ".helper()") in calls
    assert calls[(".build()", ".helper()")]["confidence"] == "EXTRACTED"


def test_parent_scope_resolves_through_inheritance(tmp_path):
    calls, _ = _extract(tmp_path, {
        "Base.php": (
            "<?php\nnamespace App;\nclass Base {\n"
            "    public static function helper() { return 1; }\n}\n"),
        "Child.php": (
            "<?php\nnamespace App;\nclass Child extends Base {\n"
            "    public static function run() { return parent::helper(); }\n}\n"),
    })
    assert (".run()", ".helper()") in calls


def test_dynamic_scope_produces_no_phantom_edge(tmp_path):
    """`$cls::method()` has no declared-type table to resolve against - it
    must stay unresolved rather than guess and mint a wrong edge."""
    calls, r = _extract(tmp_path, {"Caller.php": (
        "<?php\nnamespace App;\nclass Caller {\n"
        "    public function run($cls) { return $cls::helper(); }\n}\n")})
    assert not any(s == ".run()" for s, _t in calls)


def test_instance_call_is_still_unresolved_no_regression(tmp_path):
    """`$obj->method()` was never resolved before this fix (no receiver-typed
    PHP resolver existed) and must remain so - this fix only targets scoped
    (`::`) calls, not instance (`->`) calls."""
    calls, _ = _extract(tmp_path, {
        "Helper.php": (
            "<?php\nnamespace App;\nclass Helper {\n"
            "    public function sanitize($x) { return $x; }\n}\n"),
        "Caller.php": (
            "<?php\nnamespace App;\nclass Caller {\n"
            "    public function run(Helper $h, $x) { return $h->sanitize($x); }\n}\n"),
    })
    assert not any(s == ".run()" for s, _t in calls)
