"""The JS/TS language family is decoupled from the AST-cache bypass set (#3326).

`_collect_js_symbol_resolution_facts` used to pick which files go through JS/TS
cross-file resolution by testing membership in `_JS_CACHE_BYPASS_SUFFIXES` — a
cache-policy constant. So a change made for caching reasons silently changed
which files produced INFERRED edges, invisible from either call site. The
resolution filter now keys on `_JS_FAMILY_SUFFIXES` (a language-membership
fact); the two are independent objects.
"""

import graphify.extractors.models as models
import graphify.extractors.resolution as resolution
from graphify.extract import extract


def test_family_and_cache_bypass_are_distinct_objects():
    fam = models._JS_FAMILY_SUFFIXES
    cache = models._JS_CACHE_BYPASS_SUFFIXES
    assert fam is not cache, "the two sets must be independent, not the same object"
    # They coincide in value today, but mutating one must not touch the other.
    probe = ".decoupling-probe"
    cache_copy = set(cache)
    try:
        cache.add(probe)
        assert probe not in fam, "mutating the cache set leaked into the family set"
    finally:
        cache.clear()
        cache.update(cache_copy)


def test_resolution_filter_uses_the_family_constant():
    # Read the source, not __code__.co_names: the constant is referenced inside
    # a list comprehension, whose names live in a separate code object on Python
    # 3.10/3.11 (they were only inlined into the enclosing function in 3.12,
    # PEP 709) — so a co_names check is Python-version-dependent. The source is
    # not.
    import inspect

    src = inspect.getsource(resolution._collect_js_symbol_resolution_facts)
    assert "_JS_FAMILY_SUFFIXES" in src, (
        "JS symbol resolution must select files by the language family"
    )
    assert "_JS_CACHE_BYPASS_SUFFIXES" not in src, (
        "resolution must not gate on the cache-bypass policy constant"
    )


def test_ts_cross_file_resolution_still_works(tmp_path, monkeypatch):
    """Behavior is unchanged: a .ts import call still resolves cross-file."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "m.ts").write_text(
        "export function foo() { return 1; }\n", encoding="utf-8")
    (tmp_path / "u.ts").write_text(
        "import { foo } from './m';\nexport function use() { return foo(); }\n",
        encoding="utf-8")
    r = extract(sorted(tmp_path.glob("*.ts")), cache_root=tmp_path)
    labels = {n["id"]: n.get("label", "") for n in r["nodes"]}
    calls = {(labels.get(e["source"], ""), labels.get(e["target"], ""))
             for e in r["edges"] if e["relation"] == "calls"}
    assert any("use" in s.lower() and t.rstrip("()") == "foo" for s, t in calls), calls


def test_family_contains_the_js_ts_suffixes():
    for suffix in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte"):
        assert suffix in models._JS_FAMILY_SUFFIXES
