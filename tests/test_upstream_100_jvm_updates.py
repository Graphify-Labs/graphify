"""REQ-CORE-005: actual manual/watch publication retains JVM package authority."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import graphify.extract as extraction
import graphify.watch as watch
from graphify.cache import load_cached, save_cached
from tests.test_qt_final_incremental_parity import clean, normalized, run
from tests.test_qt_product_publication import no_scratch, reject, snapshot


def project(root, provider_suffix="java"):
    """Same-named Java declarations require the Kotlin caller's written package."""
    providers = []
    for package in ("a", "b"):
        path = root / package / f"Logger.{provider_suffix}"
        path.parent.mkdir()
        text = (f"package {package};\npublic class Logger {{}}\n" if provider_suffix == "java"
                else f"package {package}\nopen class Logger\n")
        path.write_text(text, encoding="utf-8")
        providers.append(path)
    caller = root / "Use.kt"
    caller.write_text("package app\nimport a.Logger\nclass Use : Logger()\n", encoding="utf-8")
    (root / "keep.py").write_text("def retained(): return 7\n", encoding="utf-8")
    return providers, caller


def assert_target(graph, package):
    """Published source-backed package metadata and both dependency roles agree."""
    types = {data["source_file"]: identity for identity, data in graph.nodes(data=True)
             if data.get("label") == "Logger" and data.get("_callable_class") is True}
    assert set(types) == {"a/Logger.java", "b/Logger.java"}
    for name, identity in types.items():
        assert graph.nodes[identity]["metadata"]["jvm_package"] == name.split("/")[0]
    target = types[f"{package}/Logger.java"]
    unwanted = types[f"{'b' if package == 'a' else 'a'}/Logger.java"]
    edges = [(source, destination, data) for source, destination, data in graph.edges(data=True)
             if data.get("source_file") == "Use.kt" and data.get("relation") in {"imports", "inherits"}]
    assert {data["relation"] for source, destination, data in edges if target in (source, destination)} == {"imports", "inherits"}
    assert not any(unwanted in (source, destination) for source, destination, _ in edges)


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_core005_ac01_ac03_jvm_changed_caller_publication_retains_recovers_repeats(
        tmp_path_factory, monkeypatch, capsys, operation):
    """A late real manifest replacement failure preserves accepted files, then retries.

    Only the edited caller is parsed. The production CLI/watch context adapters
    must carry each unchanged Java declaration's package from persisted graph
    data; neither cache success nor in-memory resolution can publish acceptance.
    """
    root = tmp_path_factory.mktemp("jvmupdate")
    providers, caller = project(root)
    monkeypatch.chdir(root)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(root, monkeypatch, operation)
    assert_target(initial, "a")
    output = root / "graphify-out"
    accepted = snapshot(output)
    cache_root = output / "cache"
    old_cache = {path.relative_to(cache_root): path.read_bytes()
                 for path in cache_root.rglob("*.json")}
    caller.write_text(caller.read_text(encoding="utf-8").replace("import a.Logger", "import b.Logger"), encoding="utf-8")
    observed, real_extract = [], extraction._safe_extract_with_xaml_root

    def observe(extractor, path, *args, **kwargs):
        observed.append(path)
        return real_extract(extractor, path, *args, **kwargs)

    monkeypatch.setattr(extraction, "_safe_extract_with_xaml_root", observe)
    attempted, real_replace = [], watch.os_replace_with_fallback

    def fail_manifest(source, destination):
        if destination.name == "manifest.json":
            assert Path(source).is_file()
            assert isinstance(json.loads(Path(source).read_text(encoding="utf-8")), dict)
            attempted.append(destination)
            raise OSError("public JVM manifest replacement failure")
        return real_replace(source, destination)

    with monkeypatch.context() as failure:
        failure.setattr(watch, "os_replace_with_fallback", fail_manifest)
        reject(root, monkeypatch, operation, caller)
    assert attempted and snapshot(output) == accepted
    assert "GRAPH_PUBLICATION_FAILED" in capsys.readouterr().out
    assert all((cache_root / name).read_bytes() == content for name, content in old_cache.items())
    assert caller in observed and not any(path in observed for path in providers)
    no_scratch(output)
    recovered = run(root, monkeypatch, operation, [caller])
    assert_target(recovered, "b")
    assert normalized(recovered) == normalized(clean(root, root / ".comparison-cache"))
    settled = run(root, monkeypatch, operation, [])
    assert_target(settled, "b")
    durable = snapshot(output)
    assert normalized(run(root, monkeypatch, operation, [])) == normalized(settled)
    assert snapshot(output) == durable
    no_scratch(output)


def test_req_core005_ac02_unresolved_file_alias_identity_matches_full_partial_and_reorder(tmp_path_factory):
    """Missing raw-cache package authority keeps one deterministic sourceless type.

    Both runs use the same actual raw-cache boundary and supplied accepted
    provider cohort. Unknown-type identity must not depend on source order or
    confuse the independently retained file import with inheritance evidence.
    """
    root = tmp_path_factory.mktemp("jvmalias")
    providers, old_caller = project(root, "kt")
    caller = old_caller.with_suffix(".java")
    old_caller.unlink()
    caller.write_text("package app;\nimport b.Logger;\npublic class Use extends Logger {}\n", encoding="utf-8")
    paths = [*providers, caller]
    original = extraction.extract(paths, root=root, cache_root=root, parallel=False)
    context = [copy.deepcopy(node) for node in original["nodes"]
               if node.get("source_file") in {"a/Logger.kt", "b/Logger.kt"}]
    cached = load_cached(providers[1], root, cache_root=root)
    assert cached is not None
    for node in [*cached["nodes"], *context]:
        if node.get("label") == "Logger" and str(node.get("source_file", "")).replace("\\", "/").endswith("b/Logger.kt"):
            node["metadata"].pop("jvm_package")
    save_cached(providers[1], cached, root, cache_root=root)
    full = extraction.extract(paths, root=root, cache_root=root, parallel=False)
    partial = extraction.extract([caller], root=root, cache_root=root, parallel=False, resolution_context_nodes=context)
    reordered = extraction.extract(list(reversed(paths)), root=root, cache_root=root, parallel=False)
    identities = []
    for result in (full, partial, reordered):
        targets = {edge["target"] for edge in result["edges"] if edge.get("relation") == "inherits"}
        stubs = [node for node in result["nodes"] if node["id"] in targets]
        assert len(targets) == len(stubs) == 1
        assert stubs[0]["source_file"] == "" and stubs[0]["label"] == "b.Logger"
        assert targets != {"b_logger"}
        assert any(edge["target"] == "b_logger" and edge.get("relation") == "imports" for edge in result["edges"])
        identities.append(targets)
    assert identities[0] == identities[1] == identities[2]
