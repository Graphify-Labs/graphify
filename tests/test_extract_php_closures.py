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


