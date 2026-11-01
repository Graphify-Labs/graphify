"""INC-QML-15: exact overload identity across durable cold/manual/watch updates."""
from __future__ import annotations

import os
import stat

import pytest

from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.watch import _rebuild_code
import graphify.watch as watch
from graphify.cache import cache_dir
import graphify.cache as cache
import graphify.qt_incremental as qt_incremental
import graphify.extractors.cpp_constructor_signature as constructor_signatures
from graphify.extractors.base import _make_id
from tests.test_qt_final_incremental_parity import clean, normalized, run, unrelated
from tests.test_qt_overload_consumers import fixture


def project(root):
    """Real Qt constructor bodies and unrelated Python exercise the shared production pipeline."""
    fixture(root)
    (root / "keep.py").write_bytes(b"def helper(): return 7\n\ndef retained(): return helper()\n")
    return [root / "backend.hpp", root / "backend.cpp"]


def identities(graph):
    return {data["metadata"]["cpp_constructor"]["signature"]: identity
            for identity, data in graph.nodes(data=True) if data.get("metadata", {}).get("cpp_constructor")}


def assert_owners(graph):
    """Each constructor body owns four native mechanisms with its distinct canonical ID."""
    accepted = set(identities(graph).values())
    owned = [qt_metadata(data) for _, data in graph.nodes(data=True)
             if qt_metadata(data).get("kind") in {"emission", "qml_access", "qml_load", "qml_root"}]
    assert len(accepted) == 2 and len(owned) == 8
    assert all(md["status"] == "resolved" and md["owner_id"] in accepted for md in owned)
    assert {md["owner_id"] for md in owned} == accepted


def replace_types(paths, old, new):
    for path in paths:
        path.write_bytes(path.read_bytes().replace(old, new))


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml011_ac01_ac04_overload_signature_edit_removal_and_repeat_parity(tmp_path, monkeypatch, operation):
    """Cold/warm/manual/watch retain exact IDs and erase retired signatures and locations."""
    paths = project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    cold = clean(tmp_path, tmp_path / ".cold-cache")
    assert normalized(clean(tmp_path, tmp_path / ".cold-cache")) == normalized(cold)
    initial = run(tmp_path, monkeypatch, operation)
    assert normalized(initial) == normalized(cold)
    assert_owners(initial)
    accepted, kept = identities(initial), unrelated(initial)
    replace_types(paths, b"int ", b"double ")
    changed = run(tmp_path, monkeypatch, operation, paths)
    assert_owners(changed)
    assert len(set(identities(changed).values()).intersection(accepted.values())) == 1
    assert not set(accepted.values()).difference(identities(changed).values()).intersection(changed)
    assert normalized(changed) == normalized(clean(tmp_path, tmp_path / ".changed-cache"))
    assert unrelated(changed) == kept

    # Parameter renaming changes occurrence bytes/spans, never the accepted
    # signature ID; cached and rebuilt facts must carry the new original ranges.
    before_rename = identities(changed)
    replace_types(paths, b"value", b"renamedValue")
    renamed = run(tmp_path, monkeypatch, operation, paths)
    assert identities(renamed) == before_rename
    assert normalized(renamed) == normalized(clean(tmp_path, tmp_path / ".rename-cache"))

    # Remove one declaration and definition rather than hiding it by a filter.
    header = paths[0].read_bytes().replace(b" Backend(double renamedValue);", b"")
    paths[0].write_bytes(header)
    lines = paths[1].read_bytes().splitlines(keepends=True)
    paths[1].write_bytes(b"".join(line for line in lines if b"Backend::Backend(double" not in line))
    removed = run(tmp_path, monkeypatch, operation, paths)
    assert len(identities(removed)) == 1
    assert len([1 for _, data in removed.nodes(data=True) if qt_metadata(data).get("kind") == "emission"]) == 1
    assert normalized(removed) == normalized(clean(tmp_path, tmp_path / ".removed-cache"))
    assert unrelated(removed) == kept
    before = (tmp_path / "graphify-out/graph.json").read_bytes()
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(removed)
    assert (tmp_path / "graphify-out/graph.json").read_bytes() == before


@pytest.mark.parametrize("operation", ["manual", "watch"])
@pytest.mark.parametrize("failure_kind", ["readonly", "late_os_error"])
def test_req_qml011_ac04_overload_publication_failure_retains_cohort_and_retries(tmp_path, monkeypatch, operation, failure_kind):
    """A real readonly manifest must retain prior graph/identity/checkpoint bytes before recovery."""
    paths = project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    assert_owners(initial)
    output = tmp_path / "graphify-out"
    products = ("graph.json", "manifest.json", ".qt_analysis.json", ".graphify_root")
    retained = {name: (output / name).read_bytes() for name in products}
    ast_cache = cache_dir(tmp_path)
    old_cache = {path: path.read_bytes() for path in ast_cache.rglob("*.json")}
    assert old_cache  # The actual versioned AST cache, not an empty historical filename pattern.
    replace_types(paths, b"int ", b"double ")
    manifest = output / "manifest.json"
    original_mode = manifest.stat().st_mode
    if failure_kind == "readonly" and os.name != "nt":
        pytest.skip("Windows readonly destination contract; POSIX late real replacement failure runs separately")
    actual_replace = os.replace
    product_replace = watch.os_replace_with_fallback
    blocker = tmp_path / ".replace-blocker"
    blocker.mkdir()

    def reject_manifest(source, destination):
        if destination.name == "manifest.json":
            return actual_replace(source, blocker)  # Actual OS rejection of file-to-directory replacement.
        return product_replace(source, destination)

    if failure_kind == "readonly":
        os.chmod(manifest, stat.S_IREAD)
    else:
        monkeypatch.setattr(watch, "os_replace_with_fallback", reject_manifest)
    try:
        if operation == "manual":
            with pytest.raises(SystemExit) as failure:
                run(tmp_path, monkeypatch, operation, paths)
            assert failure.value.code == 1
        else:
            assert not _rebuild_code(tmp_path, changed_paths=paths, no_cluster=True)
        assert retained == {name: (output / name).read_bytes() for name in products}
        assert all(path.read_bytes() == content for path, content in old_cache.items())
    finally:
        os.chmod(manifest, original_mode | stat.S_IWRITE)
        monkeypatch.setattr(watch, "os_replace_with_fallback", product_replace)
    repaired = run(tmp_path, monkeypatch, operation, paths)
    assert_owners(repaired)
    assert normalized(repaired) == normalized(clean(tmp_path, tmp_path / ".repaired-cache"))
    assert normalized(repaired) != normalized(initial)
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(repaired)


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml011_ac04_cpp_only_overload_mismatch_rejects_native_owner_then_header_repair(tmp_path, monkeypatch, operation):
    """Unchanged header prototypes cannot become owners of a newly incompatible constructor body."""
    paths = project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    assert_owners(initial)
    paths[1].write_bytes(paths[1].read_bytes().replace(b"int renamed", b"double renamed"))
    mismatch = run(tmp_path, monkeypatch, operation, [paths[1]])
    emissions = [qt_metadata(data) for _, data in mismatch.nodes(data=True) if qt_metadata(data).get("kind") == "emission"]
    assert len(emissions) == 2 and sum(md["status"] == "resolved" for md in emissions) == 1
    assert normalized(mismatch) == normalized(clean(tmp_path, tmp_path / ".mismatch-cache"))
    paths[0].write_bytes(paths[0].read_bytes().replace(b"int value", b"double value"))
    repaired = run(tmp_path, monkeypatch, operation, [paths[0]])
    assert_owners(repaired)
    assert normalized(repaired) == normalized(clean(tmp_path, tmp_path / ".header-repair-cache"))


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml011_ac04_partial_constructor_parse_retains_accepted_identity_and_recovery(tmp_path, monkeypatch, operation):
    """An actual malformed overloaded C++ file cannot publish a partial new constructor set."""
    paths = project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    output = tmp_path / "graphify-out"
    retained = {name: (output / name).read_bytes() for name in ("graph.json", "manifest.json", ".qt_analysis.json")}
    original = paths[1].read_bytes()
    paths[1].write_bytes(original + b"\nBackend::Backend(double invalid {\n")
    if operation == "manual":
        with pytest.raises(SystemExit) as failure:
            run(tmp_path, monkeypatch, operation, paths)
        assert failure.value.code == 1
    else:
        assert not _rebuild_code(tmp_path, changed_paths=paths, no_cluster=True)
    assert retained == {name: (output / name).read_bytes() for name in retained}
    paths[1].write_bytes(original)
    restored = run(tmp_path, monkeypatch, operation, paths)
    assert normalized(restored) == normalized(initial)
    assert_owners(restored)


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml011_ac04_schema9_name_id_fixture_migrates_unchanged_sources_to_exact_signatures(tmp_path, monkeypatch, operation):
    """A same-package prior-ID producer seam supplies historical identity, not fabricated current graph data."""
    paths = project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    current_schema, current_policy = cache._AST_CACHE_SCHEMA, qt_incremental.QT_POLICY_VERSION
    assert current_schema >= 10 and current_policy >= 14
    original = {path: path.read_bytes() for path in paths}

    def prior_name_id(class_id, name, *_args):
        return _make_id(class_id, name)

    # Only historical producer ID and epoch seams differ. Current declaration
    # authority guards intentionally refuse these old identity contracts; this
    # proves migration/retirement, not a replay of prior release semantics.
    with monkeypatch.context() as legacy:
        legacy.setattr(cache, "_AST_CACHE_SCHEMA", 9)
        legacy.setattr(qt_incremental, "QT_POLICY_VERSION", 13)
        legacy.setattr(constructor_signatures, "constructor_id", prior_name_id)
        legacy.setattr("graphify.extractors.cpp_constructors.constructor_id", prior_name_id)
        prior = run(tmp_path, monkeypatch, operation)
        prior_ids = set(identities(prior).values())
        assert prior_ids and all("_cppctor_" not in identity for identity in prior_ids)
        prior_cache = cache_dir(tmp_path)
        assert "-s9" in prior_cache.name and list(prior_cache.rglob("*.json"))
    migrated = run(tmp_path, monkeypatch, operation, [])
    assert not prior_ids.intersection(migrated)
    assert_owners(migrated)
    assert all("_cppctor_" in identity for identity in identities(migrated).values())
    assert original == {path: path.read_bytes() for path in paths}
    assert cache_dir(tmp_path) != prior_cache
    assert normalized(migrated) == normalized(clean(tmp_path, tmp_path / ".migration-cache"))
    before = (tmp_path / "graphify-out/graph.json").read_bytes()
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(migrated)
    assert before == (tmp_path / "graphify-out/graph.json").read_bytes()
