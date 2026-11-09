from pathlib import Path
from graphify.extract import extract_php
import pytest


def test_php_route_closure_gets_semantic_name(tmp_path):
    """A closure passed to a routing method gets a 'VERB /path' label."""
    src = b"""<?php
$app->get('/api/users', function() {
    return [];
});
$app->post('/api/users', function() {
    return 'created';
});
"""
    php_file = tmp_path / "routes.php"
    php_file.write_bytes(src)

    res = extract_php(php_file)
    if res.get("error"):
        if "No language parser" in res["error"]:
            pytest.skip("PHP grammar not installed")
        else:
            pytest.fail(res["error"])

    labels = {n["label"] for n in res["nodes"]}

    assert "GET /api/users()" in labels, "Expected route closure to have semantic label 'GET /api/users()'"
    assert "POST /api/users()" in labels, "Expected route closure to have semantic label 'POST /api/users()'"


def test_php_generic_closure_gets_ordinal_name(tmp_path):
    """Non-routing closures get stable ordinal names {closure#N}."""
    src = b"""<?php
$fn1 = fn($x) => $x + 1;
$fn2 = function() { return 'hello'; };
"""
    php_file = tmp_path / "closures.php"
    php_file.write_bytes(src)

    res = extract_php(php_file)
    if res.get("error"):
        if "No language parser" in res["error"]:
            pytest.skip("PHP grammar not installed")
        else:
            pytest.fail(res["error"])

    labels = {n["label"] for n in res["nodes"]}

    # Ordinals, not line numbers
    assert "{closure#1}()" in labels, "Expected first generic closure to be '{closure#1}()'"
    assert "{closure#2}()" in labels, "Expected second generic closure to be '{closure#2}()'"
    # Ensure no old line-based names leak through
    assert not any("closure@" in l for l in labels), "Line-based closure names should not appear"


def test_php_nested_route_closure_composes_prefix(tmp_path):
    """A closure passed to a routing method inside a group() composes the path."""
    src = b"""<?php
$app->group('/api/v1', function ($group) {
    $group->get('/users/{id}', function ($req, $res) { return 1; });
});
"""
    php_file = tmp_path / "nested_routes.php"
    php_file.write_bytes(src)

    res = extract_php(php_file)
    if res.get("error"):
        if "No language parser" in res["error"]:
            pytest.skip("PHP grammar not installed")
        else:
            pytest.fail(res["error"])

    labels = {n["label"] for n in res["nodes"]}
    assert "GET /api/v1/users/{id}()" in labels, "Expected nested route closure to compose prefix"
    assert "{closure#1}()" in labels, "Expected outer group closure to fallback to ordinal"


def test_php_cache_get_avoids_route_false_positive(tmp_path):
    """A get() call without a '/' path is treated as a generic closure, not a route."""
    src = b"""<?php
$value = $cache->get('user:42', function () { return 2; });
"""
    php_file = tmp_path / "cache.php"
    php_file.write_bytes(src)

    res = extract_php(php_file)
    if res.get("error"):
        if "No language parser" in res["error"]:
            pytest.skip("PHP grammar not installed")
        else:
            pytest.fail(res["error"])

    labels = {n["label"] for n in res["nodes"]}
    assert "{closure#1}()" in labels, "Expected non-routing get() to fallback to ordinal"
    assert not any(l.startswith("GET ") for l in labels), "Expected no route label for cache method"




def _php_grammar_available(tmp_path) -> bool:
    r = extract_php(tmp_path / "__probe.php")
    return not (r.get("error") and "No language parser" in (r.get("error") or ""))


def test_php_file_scope_arg_closure_call_resolves_to_the_closure(tmp_path):
    """#3409 reporter repro: a closure passed as an argument at FILE SCOPE must
    produce a node AND its inner call must attribute to that closure. Uses the
    full extract() pipeline so raw_calls resolve to a real defined target."""
    (tmp_path / "__probe.php").write_bytes(b"<?php\n")
    if not _php_grammar_available(tmp_path):
        pytest.skip("PHP grammar not installed")
    from graphify.extract import extract
    (tmp_path / "app.php").write_bytes(b"""<?php
function handler($x) { return $x; }
$assigned = function($x) { return handler($x); };
array_map(function($y){ return handler($y); }, $items);
""")
    r = extract([tmp_path / "app.php"], cache_root=tmp_path / ".cache")
    id2label = {n["id"]: n.get("label") for n in r["nodes"]}
    labels = set(id2label.values())
    # both the assigned and the argument-position closures exist as nodes
    closure_labels = {l for l in labels if l and l.startswith("{closure#")}
    assert len(closure_labels) >= 2, f"expected file-scope closures as nodes, got {sorted(labels)}"
    # each closure's inner call to handler() resolves and attributes to the closure
    call_pairs = {
        (id2label.get(e["source"]), id2label.get(e["target"]))
        for e in r["edges"] if e["relation"] == "calls"
    }
    handler_callers = {src for src, tgt in call_pairs if tgt == "handler()"}
    assert handler_callers, "closure inner call to handler() was not captured"
    assert all(c and c.startswith("{closure#") for c in handler_callers), (
        f"handler() call must attribute to a closure, not the file: {handler_callers}"
    )


def test_php_closures_produce_no_duplicate_nodes(tmp_path):
    """The walk partition must emit each closure exactly once (no double-walk)."""
    (tmp_path / "__probe.php").write_bytes(b"<?php\n")
    if not _php_grammar_available(tmp_path):
        pytest.skip("PHP grammar not installed")
    src = b"""<?php
$a = function() { return 1; };
$b = fn() => 2;
array_map(function() { return 3; }, []);
"""
    (tmp_path / "dup.php").write_bytes(src)
    res = extract_php(tmp_path / "dup.php")
    from collections import Counter
    counts = Counter(n["label"] for n in res["nodes"] if n.get("label", "").startswith("{closure#"))
    assert counts and all(c == 1 for c in counts.values()), f"duplicate closure nodes: {counts}"


def test_php_method_scope_closure_call_attributes_to_closure_not_method(tmp_path):
    """A closure inside a method: its inner call attributes to the closure node,
    not the enclosing method (closures are function_boundary_types) (#3409)."""
    (tmp_path / "__probe.php").write_bytes(b"<?php\n")
    if not _php_grammar_available(tmp_path):
        pytest.skip("PHP grammar not installed")
    from graphify.extract import extract
    (tmp_path / "svc.php").write_bytes(b"""<?php
function target($x) { return $x; }
class Service {
    public function run() {
        $cb = function($x) { return target($x); };
        return $cb;
    }
}
""")
    r = extract([tmp_path / "svc.php"], cache_root=tmp_path / ".cache")
    id2label = {n["id"]: n.get("label") for n in r["nodes"]}
    callers = {
        id2label.get(e["source"])
        for e in r["edges"] if e["relation"] == "calls" and id2label.get(e["target"]) == "target()"
    }
    assert callers, "call to target() inside the method-level closure was not captured"
    assert all(c and c.startswith("{closure#") for c in callers), (
        f"target() must attribute to the closure, not .run(): {callers}"
    )
    assert ".run()" not in callers
