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
    """A same-named decoy method on an unrelated class proves `self::`/
    `static::` bind to the ENCLOSING class, not to any node sharing the bare
    method name (review finding on PR #3874: without a decoy, a bare-name
    coincidence would pass this test even if self/static were never scoped)."""
    calls, _ = _extract(tmp_path, {
        "Widget.php": (
            "<?php\nnamespace App;\nclass Widget {\n"
            "    public static function build() { return self::helper(); }\n"
            "    public static function render() { return static::helper(); }\n"
            "    public static function helper() { return 1; }\n}\n"),
        "Decoy.php": (
            "<?php\nnamespace App;\nclass Decoy {\n"
            "    public static function helper() { return 2; }\n}\n"),
    })
    assert (".build()", ".helper()") in calls
    assert (".render()", ".helper()") in calls
    assert calls[(".build()", ".helper()")]["confidence"] == "EXTRACTED"


def test_self_scope_does_not_resolve_to_other_class(tmp_path):
    """`self::helper()` must NOT bind to another class's `helper()` even when
    the enclosing class has no method of that name - `self::` names the
    enclosing class, not a bare method-name match anywhere in the corpus."""
    calls, _ = _extract(tmp_path, {
        "A.php": (
            "<?php\nnamespace App;\nclass A {\n"
            "    public function build() { return self::helper(); }\n}\n"),
        "B.php": (
            "<?php\nnamespace App;\nclass B {\n"
            "    public function helper() { return 1; }\n}\n"),
    })
    assert not any(s == ".build()" for s, _t in calls)


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
    must stay unresolved rather than guess and mint a wrong edge. A same-file,
    same-named decoy method proves the resolver actually ran and declined to
    bind, rather than the guard never being exercised (review finding on PR
    #3874: without the decoy, the old bare-name path would silently produce
    the same "no edge to a DIFFERENT-labeled node" result for the wrong
    reason)."""
    calls, r = _extract(tmp_path, {"Caller.php": (
        "<?php\nnamespace App;\nclass Caller {\n"
        "    public function run($cls) { return $cls::helper(); }\n"
        "    public function helper() { return 1; }\n}\n")})
    assert not any(s == ".run()" for s, _t in calls)


def test_lowercase_class_name_still_resolves(tmp_path):
    """PHP class names are conventionally StudlyCase but the language does not
    enforce it - a lowercase-first class is still a class, not a variable, and
    must resolve the same way (review finding on PR #3874)."""
    calls, _ = _extract(tmp_path, {
        "helper.php": (
            "<?php\nnamespace App;\nclass helper {\n"
            "    public static function sanitize($x) { return $x; }\n}\n"),
        "Caller.php": (
            "<?php\nnamespace App;\nclass Caller {\n"
            "    public function run($x) { return helper::sanitize($x); }\n}\n"),
    })
    edge = calls.get((".run()", ".sanitize()"))
    assert edge is not None
    assert edge["confidence"] == "EXTRACTED"


def test_fully_qualified_scope_resolves_by_last_segment(tmp_path):
    """A fully-qualified scope (`\\App\\Helper::method()` or
    `App\\Helper::method()`) must match the class's own unqualified label,
    not be left parked as unresolved (review finding on PR #3874)."""
    calls, _ = _extract(tmp_path, {
        "Helper.php": (
            "<?php\nnamespace App;\nclass Helper {\n"
            "    public static function sanitize($x) { return $x; }\n}\n"),
        "Caller.php": (
            "<?php\nnamespace Other;\nclass Caller {\n"
            "    public function run($x) { return \\App\\Helper::sanitize($x); }\n}\n"),
    })
    edge = calls.get((".run()", ".sanitize()"))
    assert edge is not None
    assert edge["confidence"] == "EXTRACTED"


def test_method_name_case_insensitivity(tmp_path):
    """PHP method names are case-insensitive at the call site - a call spelled
    with different case than the declaration must still resolve (review
    finding on PR #3874)."""
    calls, _ = _extract(tmp_path, {
        "Helper.php": (
            "<?php\nnamespace App;\nclass Helper {\n"
            "    public static function Sanitize($x) { return $x; }\n}\n"),
        "Caller.php": (
            "<?php\nnamespace App;\nclass Caller {\n"
            "    public function run($x) { return Helper::sanitize($x); }\n}\n"),
    })
    assert any(s == ".run()" and t.lower() == ".sanitize()" for s, t in calls)


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
