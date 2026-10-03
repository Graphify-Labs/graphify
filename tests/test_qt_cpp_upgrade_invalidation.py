"""REQ-QML-018-AC02 same-version upgrades retire stale syntax and analysis epochs."""
from __future__ import annotations

import pytest

import graphify.__main__ as entrypoint
import graphify.cache as cache
import graphify.extract as extraction
import graphify.qt_incremental as policy
from graphify.qt_analysis_state import commit_qt_analysis, inspect_qt_analysis
from graphify.build import build_from_json
from graphify.detect import save_manifest
from graphify.export import to_json
from tests.test_qt_final_incremental_parity import clean, normalized, published


CPP = {
    "unused": "int helper(){return 1;}\nvoid use(){ Q_UNUSED(helper()); }\n",
    "default": "struct Value {};\nvoid use(const Value &value = {}) {}\n",
}


def source(root, syntax):
    path = root / "adapter.cpp"
    path.write_text(CPP[syntax], encoding="utf-8")
    return path


def old_syntax(path):
    # This is the real generic parser before the Qt-normalization adapter,
    # producing the historical accepted cache shape from the same source bytes.
    return extraction._extract_generic(path, extraction._CPP_CONFIG)


@pytest.mark.parametrize("syntax", CPP)
def test_req_qml018_ac02_schema_retires_real_same_package_syntax_cache(tmp_path, monkeypatch, syntax):
    """The fork upgrade changes extractor code without changing package version."""
    path = source(tmp_path, syntax)
    before = path.read_bytes(), cache._EXTRACTOR_VERSION
    old = old_syntax(path)
    with monkeypatch.context() as historical:
        historical.setattr(cache, "_AST_CACHE_SCHEMA", 5)
        cache.save_cached(path, old, root=tmp_path)
        old_dir = cache.cache_dir(tmp_path)
        assert cache.load_cached(path, root=tmp_path) is not None
    assert cache.load_cached(path, root=tmp_path) is None
    assert not old_dir.exists()
    assert before == (path.read_bytes(), cache._EXTRACTOR_VERSION)
    assert cache.cache_dir(tmp_path).name.endswith(f"-s{cache._AST_CACHE_SCHEMA}")


def test_req_qml018_ac02_policy_epoch_refreshes_same_package_unchanged_cpp(tmp_path, monkeypatch):
    """Only the analysis policy changes; source and installed package set do not."""
    path = source(tmp_path, "unused")
    out = tmp_path / "graphify-out"
    with monkeypatch.context() as historical:
        historical.setattr(policy, "QT_POLICY_VERSION", 1)
        old = inspect_qt_analysis(tmp_path, out, [path])
        commit_qt_analysis(out, old)
    current = inspect_qt_analysis(tmp_path, out, [path])
    assert current.changed and current.fingerprint != old.fingerprint
    assert current.has_qt and current.current_has_qt


@pytest.mark.parametrize("text", [CPP["unused"], CPP["default"],
                                  "void use(const T &value = { /* empty */ }) {}"])
def test_req_qml018_ac02_new_syntax_candidates_reparse_only_accepted_cpp(tmp_path, text):
    """Discovery remains caller-owned; no adjacent source or root is created."""
    path = tmp_path / "adapter.cpp"
    path.write_text(text, encoding="utf-8")
    before = set(tmp_path.iterdir())
    assert policy.requires_native_refresh([path])
    assert set(tmp_path.iterdir()) == before


def test_req_qml018_ac02_unrelated_plain_cpp_retains_actual_warm_cache(tmp_path, monkeypatch):
    """An ordinary call/nonempty initializer keeps the established AST fast path."""
    path = tmp_path / "ordinary.cpp"
    path.write_text("void helper(){} void use(){ int values[] = {1,2}; helper(); }", encoding="utf-8")
    assert not policy.requires_native_refresh([path])
    first = extraction.extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert cache.load_cached(path, root=tmp_path)
    observed, real = [], extraction._safe_extract_with_xaml_root

    def observe(extractor, input_path, root):
        observed.append(input_path)
        return real(extractor, input_path, root)

    monkeypatch.setattr(extraction, "_safe_extract_with_xaml_root", observe)
    warm = extraction.extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not observed and warm == first


def historical_publication(root, monkeypatch, syntax):
    """Publish actual pre-adapter parser output/cache with the former policy epoch.

    Generic builder/export and manifest/stamp APIs produce the historical accepted
    state; current update/extract functions are never replaced by fixture fakes.
    """
    path = source(root, syntax)
    keep = root / "keep.py"
    keep.write_text("def helper(): return 7\n\ndef retained(): return helper()\n", encoding="utf-8")
    paths, out = [path, keep], root / "graphify-out"
    with monkeypatch.context() as historical:
        historical.setattr(cache, "_AST_CACHE_SCHEMA", 5)
        historical.setattr(policy, "QT_POLICY_VERSION", 1)
        old = old_syntax(path)
        cache.save_cached(path, old, root=root)
        assert cache.load_cached(path, root=root)
        unchanged = extraction.extract([keep], root=root, cache_root=root, parallel=False)
        graph = build_from_json({"nodes": [*old["nodes"], *unchanged["nodes"]],
                                 "edges": [*old["edges"], *unchanged["edges"]]}, root=root)
        assert to_json(graph, {}, str(out / "graph.json"), force=True)
        save_manifest({"code": [str(item) for item in paths]}, manifest_path=str(out / "manifest.json"),
                      kind="ast", root=root, scan_corpus={str(item) for item in paths})
        state = inspect_qt_analysis(root, out, paths)
        commit_qt_analysis(out, state)
        assert not inspect_qt_analysis(root, out, paths).changed
        old_dir = cache.cache_dir(root)
    return paths, state.fingerprint, old_dir


def cli(root, monkeypatch, operation, *, force=False):
    # These documented production options isolate skill maintenance and tips;
    # the real console parser, locking, update/extract and persistence all run.
    monkeypatch.setenv("GRAPHIFY_NO_AUTO_REFRESH", "1")
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    args = ["graphify", operation, str(root), "--no-cluster"]
    if operation == "extract":
        args += ["--update", "--code-only"]
    if force:
        args.append("--force")
    monkeypatch.setattr(entrypoint.sys, "argv", args)
    try:
        entrypoint.main()
    except SystemExit as result:
        if result.code not in (None, 0):
            raise
    return published(root)


def unchanged_python(graph):
    nodes, edges = normalized(graph)
    ids = {identity for identity, data in graph.nodes(data=True) if data.get("source_file") == "keep.py"}
    return {identity: nodes[identity] for identity in ids}, {edge for edge in edges if edge[0] in ids and edge[1] in ids}


@pytest.mark.parametrize("operation", ["update", "extract"])
@pytest.mark.parametrize("syntax", CPP)
def test_req_qml018_ac02_actual_cli_refreshes_old_epoch_without_source_or_package_change(
    tmp_path, monkeypatch, operation, syntax
):
    """Upgrade success: stale accepted graph/cache cannot survive unchanged inputs."""
    monkeypatch.chdir(tmp_path)
    paths, old_fingerprint, old_dir = historical_publication(tmp_path, monkeypatch, syntax)
    before = {item.name: item.read_bytes() for item in paths}, cache._EXTRACTOR_VERSION
    initial = published(tmp_path)
    untouched = unchanged_python(initial)
    observed, real = [], extraction._safe_extract_with_xaml_root

    def observe(extractor, input_path, root):
        observed.append(input_path)
        return real(extractor, input_path, root)

    # Observe the genuine parser dispatch, rather than infer it from a graph
    # that could already retain some nested known calls under the old adapter.
    monkeypatch.setattr(extraction, "_safe_extract_with_xaml_root", observe)
    current = cli(tmp_path, monkeypatch, operation)
    assert paths[0] in observed
    assert not old_dir.exists() and cache.cache_dir(tmp_path).name.endswith(f"-s{cache._AST_CACHE_SCHEMA}")
    assert cache.load_cached(paths[0], root=tmp_path) is None
    assert cache.load_cached(paths[1], root=tmp_path) is not None
    state = inspect_qt_analysis(tmp_path, tmp_path / "graphify-out", paths)
    assert not state.changed and state.fingerprint != old_fingerprint
    assert before == ({item.name: item.read_bytes() for item in paths}, cache._EXTRACTOR_VERSION)
    assert unchanged_python(current) == untouched
    if syntax == "unused":
        nodes = {data.get("label"): identity for identity, data in current.nodes(data=True)
                 if data.get("source_file") == "adapter.cpp"}
        pairs = {nodes["use()"], nodes["helper()"]}
        assert any({source, target} == pairs and data.get("relation") == "calls"
                   for source, target, data in current.edges(data=True))
        assert any(call["callee"] == "Q_UNUSED" for call in old_syntax(paths[0])["raw_calls"])
    direct = extraction.extract_cpp(paths[0])
    assert not direct.get("parse_errors")
    assert not any(call["callee"] == "Q_UNUSED" for call in direct.get("raw_calls", []))
    assert normalized(current) == normalized(clean(tmp_path, tmp_path / ".cold-cache"))
    assert normalized(current) == normalized(clean(tmp_path, tmp_path / ".cold-cache"))
    graph_bytes = (tmp_path / "graphify-out/graph.json").read_bytes()
    repeated = cli(tmp_path, monkeypatch, operation)
    assert normalized(repeated) == normalized(current)
    assert (tmp_path / "graphify-out/graph.json").read_bytes() == graph_bytes


def products(root):
    out = root / "graphify-out"
    return {name: (out / name).read_bytes() for name in ("graph.json", "manifest.json", ".qt_analysis.json")}


def ast_entries(root):
    base = root / "graphify-out/cache/ast"
    return {path.relative_to(base).as_posix(): path.read_bytes() for path in base.rglob("*.json")}


@pytest.mark.parametrize("force", [False, True])
def test_req_qml018_ac02_current_epoch_failure_keeps_real_cache_and_products(tmp_path, monkeypatch, force):
    """Malformed new input cannot poison current syntax cache or published state."""
    monkeypatch.chdir(tmp_path)
    path = source(tmp_path, "unused")
    valid = path.read_bytes()
    accepted = cli(tmp_path, monkeypatch, "update")
    cache.save_cached(path, extraction.extract_cpp(path), root=tmp_path)
    before, cached = products(tmp_path), ast_entries(tmp_path)
    assert cached and all(f"-s{cache._AST_CACHE_SCHEMA}/" in name for name in cached)
    path.write_text("void use(){ Q_UNUSED(helper()) broken( }", encoding="utf-8")
    with pytest.raises(SystemExit) as failure:
        cli(tmp_path, monkeypatch, "update", force=force)
    assert failure.value.code == 1
    assert products(tmp_path) == before and ast_entries(tmp_path) == cached
    path.write_bytes(valid)
    assert normalized(cli(tmp_path, monkeypatch, "update")) == normalized(accepted)
    assert ast_entries(tmp_path) == cached
