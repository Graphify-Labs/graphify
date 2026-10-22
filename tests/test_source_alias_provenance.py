"""REQ-QML-020: discovered source aliases remain distinct portable identities."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest

from graphify.build import build_from_json
from graphify.cache import file_hash
import graphify.extract as extraction
from graphify.export import to_json
from graphify.paths import load_node_link_graph
from graphify.watch import _rebuild_code
from tests.test_definition_file_portability import FOO_CPP, FOO_H
from tests.test_qt_final_incremental_parity import normalized, project, run
from tests.test_qt_product_publication import no_scratch, snapshot


PYTHON = b"def helper():\n    return 7\n\ndef caller():\n    return helper()\n"


@pytest.fixture
def directory_alias(request):
    """Own real directory links; Windows junctions need no elevated token."""
    if os.name != "nt":
        request.getfixturevalue("requires_symlinks")
    aliases = []

    def create(link, target):
        if os.name == "nt":
            result = subprocess.run(["cmd", "/d", "/c", "mklink", "/J", str(link), str(target)],
                                    capture_output=True, text=True, check=False)
            assert result.returncode == 0, "Temporary NTFS directory junction creation failed"
        else:
            link.symlink_to(target, target_is_directory=True)
        aliases.append(link)
        assert link.resolve() == target.resolve()
        return link

    yield create
    # Remove only owned link objects. Their target fixture tree stays intact.
    for link in reversed(aliases):
        if os.name == "nt":
            link.rmdir()
        else:
            link.unlink()


def extracted(paths, root, cache):
    result = extraction.extract(paths, root=root, cache_root=cache, parallel=False)
    assert not result["failed_sources"] and not result["qml_failures"]
    return result, build_from_json(result, root=root)


@pytest.mark.parametrize("aliased_root", [False, True])
def test_req_qml020_ac01_discovered_directory_sources_survive_cold_warm_and_reload(
        tmp_path, monkeypatch, directory_alias, aliased_root):
    """A followed directory and its target keep separate nodes, calls and cache keys."""
    root = tmp_path / "repo"
    (root / "real").mkdir(parents=True)
    (root / "real/member.py").write_bytes(PYTHON)
    directory_alias(root / "linked", root / "real")
    scan = directory_alias(tmp_path / "scan", root) if aliased_root else root
    paths = extraction.collect_files(scan, follow_symlinks=True, root=scan)
    assert {path.relative_to(scan).as_posix() for path in paths} == {
        "real/member.py", "linked/member.py"}
    assert file_hash(scan / "real/member.py", root) != file_hash(scan / "linked/member.py", root)
    cold, cold_graph = extracted(paths, scan, tmp_path / "cache")
    identities = {source: {node["id"] for node in cold["nodes"] if node.get("source_file") == source}
                  for source in ("real/member.py", "linked/member.py")}
    assert all(identities.values()) and identities["real/member.py"].isdisjoint(identities["linked/member.py"])
    for source, owned in identities.items():
        prefix = source.removesuffix(".py").replace("/", "_")
        assert owned == {prefix, f"{prefix}_helper", f"{prefix}_caller"}
        calls = [edge for edge in cold["edges"] if edge.get("source_file") == source
                 and edge.get("context") == "call"]
        assert calls and all(edge["source"] in owned and edge["target"] in owned for edge in calls)

    def uncached(*_args):
        pytest.fail("An unchanged source must use its own cached fragment")

    monkeypatch.setattr(extraction, "_safe_extract_with_xaml_root", uncached)
    warm, warm_graph = extracted(paths, scan, tmp_path / "cache")
    assert normalized(warm_graph) == normalized(cold_graph)
    for directed in (False, True):
        graph = build_from_json(warm, root=scan, directed=directed)
        if directed:
            assert all(graph.has_edge(f"{name}_member_caller", f"{name}_member_helper")
                       for name in ("real", "linked"))
        output = tmp_path / f"round-trip-{directed}.json"
        assert to_json(graph, {}, str(output), force=True)
        reloaded = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
        assert normalized(reloaded) == normalized(graph)


def test_req_qml020_ac01_leaf_alias_retains_its_source_below_an_aliased_root(
        tmp_path, requires_symlinks, directory_alias, monkeypatch):
    """A symlink file remains distinct when the entire scan root is also an alias."""
    root = tmp_path / "repo"
    (root / "sub").mkdir(parents=True)
    target = root / "real.py"
    target.write_bytes(PYTHON)
    (root / "sub/link.py").symlink_to(target)
    scan = directory_alias(tmp_path / "scan", root)
    paths = extraction.collect_files(scan)
    cold, before = extracted(paths, scan, tmp_path / "cache")
    assert {node.get("source_file") for node in cold["nodes"]} == {"real.py", "sub/link.py"}

    def uncached(*_args):
        pytest.fail("Leaf alias and target fragments must both survive warm replay")

    monkeypatch.setattr(extraction, "_safe_extract_with_xaml_root", uncached)
    _, after = extracted(paths, scan, tmp_path / "cache")
    assert normalized(after) == normalized(before)


@pytest.mark.parametrize("fault", [OSError, RuntimeError])
def test_req_qml020_ac02_failed_parent_anchor_keeps_only_accepted_physical_identity(
        tmp_path, directory_alias, monkeypatch, capsys, fault):
    """An inaccessible alias anchor falls back to a verified in-root source safely."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "member.py").write_bytes(PYTHON)
    scan = directory_alias(tmp_path / "scan", root)
    _, expected = extracted([root / "member.py"], root, tmp_path / "canonical-cache")
    realpath, observed = extraction._cached_realpath, []
    body = "private backend body must not become source context"

    def inaccessible_parent(path, cwd):
        if Path(path) == scan:
            observed.append(path)
            raise fault(body)
        return realpath(path, cwd)

    # Forward the real cache owner's invalidation; the adapter only injects
    # one ancestor lookup failure after accepted source facts are produced.
    setattr(inaccessible_parent, "cache_clear", realpath.cache_clear)
    monkeypatch.setattr(extraction, "_cached_realpath", inaccessible_parent)
    for _ in range(2):
        result, actual = extracted([scan / "member.py"], root, tmp_path / "alias-cache")
        assert normalized(actual) == normalized(expected)
        assert {node["source_file"] for node in result["nodes"]} == {"member.py"}
        assert body not in json.dumps(result)
    assert observed and body not in capsys.readouterr().out


def test_req_qml020_ac01_native_definition_keeps_discovered_directory_provenance(
        tmp_path, directory_alias):
    """Actual C++ declaration/definition merging keeps the walked source fields."""
    root = tmp_path / "repo"
    (root / "real").mkdir(parents=True)
    (root / "real/Foo.h").write_text(FOO_H, encoding="utf-8")
    (root / "real/Foo.cpp").write_text(FOO_CPP, encoding="utf-8")
    directory_alias(root / "linked", root / "real")
    paths = [root / "linked/Foo.h", root / "linked/Foo.cpp"]
    graphs = []
    for _ in range(2):
        result, graph = extracted(paths, root, tmp_path / "cache")
        definitions = [node for node in result["nodes"] if node.get("definition_file")]
        assert definitions and all(node["source_file"] == "linked/Foo.h"
                                   and node["definition_file"] == "linked/Foo.cpp" for node in definitions)
        assert all(item["source_file"].startswith("linked/")
                   for item in result["nodes"] + result["edges"] if item.get("source_file"))
        graphs.append(graph)
    assert normalized(graphs[0]) == normalized(graphs[1])


def test_req_qml020_ac02_foreign_alias_cannot_acquire_native_root_authority(
        tmp_path, directory_alias):
    """A lexically local link to a foreign QObject remains excluded and diagnostic."""
    root, foreign = tmp_path / "repo", tmp_path / "foreign"
    root.mkdir()
    foreign.mkdir()
    target = foreign / "Foreign.h"
    target.write_bytes(b"class Foreign : public QObject { Q_OBJECT public: Q_INVOKABLE void run(); };\n")
    directory_alias(root / "linked", foreign)
    assert extraction.collect_files(root, follow_symlinks=True, root=root) == []
    before = target.read_bytes()
    result = extraction.extract([root / "linked/Foreign.h"], root=root,
                                cache_root=tmp_path / "cache", parallel=False)
    assert result["failed_sources"] == [str(root / "linked/Foreign.h")]
    assert result["qml_failures"] == [{"code": "QT_CPP_ROOT", "source_file": ""}]
    assert not [node for node in result["nodes"] if node.get("metadata", {}).get("qt")]
    assert target.read_bytes() == before


def test_req_qml020_ac03_watch_rename_deletion_and_repeat_preserve_discovered_source(
        tmp_path, directory_alias):
    """Real graph publication tracks two renames, deletion and no-change replay."""
    root = tmp_path / "repo"
    (root / "real").mkdir(parents=True)
    (root / ".graphifyignore").write_text("real/\n", encoding="utf-8")
    current = root / "real/old.py"
    current.write_bytes(PYTHON)
    directory_alias(root / "linked", root / "real")
    output = root / "graphify-out/graph.json"
    assert _rebuild_code(root, follow_symlinks=True, no_cluster=True, acquire_lock=False)
    for name in ("first.py", "second.py"):
        destination = current.with_name(name)
        current.rename(destination)
        current = destination
        assert _rebuild_code(root, changed_paths=[Path("linked") / name], follow_symlinks=True,
                             no_cluster=True, acquire_lock=False)
        actual = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
        assert {data.get("source_file") for _, data in actual.nodes(data=True)} == {f"linked/{name}"}
        paths = extraction.collect_files(root, follow_symlinks=True, root=root)
        _, full = extracted(paths, root, tmp_path / f"full-{name}")
        assert normalized(actual) == normalized(full)
    accepted = output.read_bytes()
    assert _rebuild_code(root, changed_paths=[], follow_symlinks=True, no_cluster=True, acquire_lock=False)
    assert output.read_bytes() == accepted
    current.unlink()
    assert _rebuild_code(root, changed_paths=[Path("linked/second.py")], follow_symlinks=True,
                         no_cluster=True, acquire_lock=False)
    retired = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
    assert retired.number_of_nodes() == retired.number_of_edges() == 0


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml020_ac03_policy19_products_refresh_retain_and_recover(
        tmp_path, directory_alias, monkeypatch, operation):
    """An unchanged Qt cohort refreshes aliases, with real failed publication retention."""
    import graphify.qt_analysis_state as state
    import graphify.qt_incremental as policy

    root = tmp_path / "repo"
    root.mkdir()
    project(root)
    (root / "real").mkdir()
    (root / "real/member.py").write_bytes(PYTHON)
    directory_alias(root / "linked", root / "real")
    (root / ".graphifyignore").write_text("real/\n", encoding="utf-8")
    monkeypatch.chdir(root)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    with monkeypatch.context() as prior:
        prior.setattr(policy, "QT_POLICY_VERSION", 19)
        run(root, prior, operation, follow_symlinks=True)
    output = root / "graphify-out"
    before, old_stamp = snapshot(output), state.read_qt_fingerprint(output)
    observed, real_extract = [], extraction.extract

    def record_inputs(paths, *args, **kwargs):
        paths = list(paths)
        observed.append({path.relative_to(root).as_posix() for path in paths})
        return real_extract(paths, *args, **kwargs)

    monkeypatch.setattr(extraction, "extract", record_inputs)
    real_commit = state.commit_qt_analysis

    def fail_after_staging(*args, **kwargs):
        real_commit(*args, **kwargs)
        raise OSError("public source identity refresh publication failure")

    with monkeypatch.context() as failed:
        failed.setattr(state, "commit_qt_analysis", fail_after_staging)
        if operation == "manual":
            with pytest.raises(SystemExit) as rejection:
                run(root, failed, operation, [], follow_symlinks=True)
            assert rejection.value.code == 1
        else:
            assert not _rebuild_code(root, changed_paths=[], no_cluster=True, follow_symlinks=True)
    assert snapshot(output) == before and state.read_qt_fingerprint(output) == old_stamp
    no_scratch(output)
    repaired = run(root, monkeypatch, operation, [], follow_symlinks=True)
    assert state.read_qt_fingerprint(output) != old_stamp
    assert observed and {"Main.qml", "backend.h", "loader.cpp"} <= set.union(*observed)
    assert "linked/member.py" in {data.get("source_file") for _, data in repaired.nodes(data=True)}
    paths = extraction.collect_files(root, root=root, follow_symlinks=True)
    _, full = extracted(paths, root, tmp_path / "full")
    assert normalized(repaired) == normalized(full)
    accepted = snapshot(output)
    assert normalized(run(root, monkeypatch, operation, [], follow_symlinks=True)) == normalized(repaired)
    assert snapshot(output) == accepted
    no_scratch(output)


@pytest.mark.skipif(os.name == "nt", reason="POSIX directory-symlink discovery profile")
def test_req_qml020_ac03_directory_symlink_requires_explicit_discovery_profile(tmp_path, directory_alias):
    """A real alias remains absent by default; only supported opt-in admits it."""
    root = tmp_path.resolve()
    real = root / "real"
    real.mkdir()
    (real / "member.py").write_bytes(PYTHON)
    directory_alias(root / "linked", real)
    (root / ".graphifyignore").write_text("real/\n", encoding="utf-8")
    assert extraction.collect_files(root, root=root) == []
    assert extraction.collect_files(root, root=root, follow_symlinks=True) == [root / "linked/member.py"]
