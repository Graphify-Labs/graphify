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
        pytest.skip(res["error"])

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
        pytest.skip(res["error"])

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
        pytest.skip(res["error"])

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
        pytest.skip(res["error"])

    labels = {n["label"] for n in res["nodes"]}
    assert "{closure#1}()" in labels, "Expected non-routing get() to fallback to ordinal"
    assert not any(l.startswith("GET ") for l in labels), "Expected no route label for cache method"


