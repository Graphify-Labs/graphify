"""REQ-QML-020: real filesystem aliases preserve accepted membership identity."""
from __future__ import annotations

import copy
import ctypes
import os
from pathlib import Path

import pytest

from graphify.build import build_from_json
from graphify.extract import extract
from graphify.extractors.qml_facts import qml_metadata
from graphify.qml_resolution_types import source_path
from graphify.qt_project_index import QtProjectIndex
from graphify.qt_project_membership import resolve_project_memberships
from tests.qml_installed_smoke import native_module_smoke
from tests.test_qt_final_incremental_parity import clean, normalized, run


NAMES = ("backend.h", "Main.qml", "loader.cpp", "CMakeLists.txt", "resources.qrc")


@pytest.fixture(params=["windows_short", "symlink"])
def aliased_parent(tmp_path, request):
    """Exercise host path aliases without substituting a fake Path resolver."""
    parent = tmp_path / "parent directory with spaces"
    parent.mkdir()
    if request.param == "symlink":
        request.getfixturevalue("requires_symlinks")
        alias = tmp_path / "parent-alias"
        alias.symlink_to(parent, target_is_directory=True)
    else:
        if os.name != "nt":
            pytest.skip("Windows short-path API is not applicable on this host")
        api = ctypes.windll.kernel32.GetShortPathNameW
        api.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32)
        api.restype = ctypes.c_uint32
        buffer = ctypes.create_unicode_buffer(32768)
        length = api(str(parent), buffer, len(buffer))
        if not length or length >= len(buffer) or buffer.value == str(parent):
            pytest.skip("Filesystem does not supply a distinct Windows short-path alias")
        alias = Path(buffer.value)
    assert alias != parent and alias.resolve() == parent.resolve()
    return parent, alias


def extract_graph(root, anchor, cache, extra=()):
    """The actual facade publishes the mixed-language accepted graph."""
    result = extract([root / name for name in (*NAMES, *extra)], root=anchor,
                     cache_root=cache, parallel=False)
    assert not result["failed_sources"] and not result["qml_failures"]
    return build_from_json(result, root=anchor, directed=True), result


def memberships(graph):
    return {identity: qml_metadata(data) for identity, data in graph.nodes(data=True)
            if qml_metadata(data).get("kind") == "membership_resolution"}


def test_req_qml020_ac01_real_parent_alias_preserves_smoke_and_cold_warm_identity(
        aliased_parent, tmp_path, monkeypatch, request):
    """Unchanged smoke and a warm unrelated cache retain identical Qt endpoints."""
    parent, alias = aliased_parent
    canonical, supplied = parent / "native-profile", alias / "native-profile"
    native_module_smoke(supplied)
    (canonical / "keep.py").write_bytes(b"def retained(): return 7\n")
    names = (*NAMES, "keep.py")
    before = {name: (canonical / name).read_bytes() for name in names}
    expected, _ = extract_graph(canonical, canonical, tmp_path / "canonical-cache", ("keep.py",))
    cold, cold_result = extract_graph(supplied, supplied, tmp_path / "alias-cache", ("keep.py",))
    assert normalized(cold) == normalized(expected)
    sites = memberships(cold)
    assert len(sites) == 4 and all(md["status"] == "resolved" for md in sites.values())

    # Qt policy deliberately reparses native/QML/metadata facts. The unrelated
    # Python file must hit its actual cache while these fresh joins retain IDs.
    import graphify.extract as extraction
    observed, real = [], extraction._safe_extract_with_xaml_root

    def observe(extractor, path, root):
        observed.append(path)
        return real(extractor, path, root)

    monkeypatch.setattr(extraction, "_safe_extract_with_xaml_root", observe)
    warm, warm_result = extract_graph(supplied, supplied, tmp_path / "alias-cache", ("keep.py",))
    # Native alternate entry spellings expand before dispatch; a separately
    # discovered symlink keeps its exact lexical owner. Python still hits cache.
    parser_root = canonical if request.node.callspec.params["aliased_parent"] == "windows_short" else supplied
    assert set(observed) == {parser_root / name for name in NAMES}
    assert normalized(warm) == normalized(cold)
    assert memberships(warm) == sites
    assert {node["id"] for node in warm_result["nodes"]} == {
        node["id"] for node in cold_result["nodes"]}
    reanchored, _ = extract_graph(supplied, canonical, tmp_path / "reanchored-cache", ("keep.py",))
    assert normalized(reanchored) == normalized(expected) and memberships(reanchored) == sites
    assert before == {name: (canonical / name).read_bytes() for name in names}
    # Stored provenance is a lexical, read-free contract. Only accepted input
    # path identity at the membership boundary should resolve filesystem aliases.
    assert source_path({"source_file": str(supplied / "CMakeLists.txt")}, canonical) is None


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml020_ac03_alias_updates_remove_stale_membership_and_match_full_rebuild(
        aliased_parent, tmp_path, monkeypatch, operation):
    """Real update writers retire a removed build declaration through the supplied alias."""
    parent, alias = aliased_parent
    canonical, supplied = parent / "native-profile", alias / "native-profile"
    native_module_smoke(supplied)
    monkeypatch.chdir(canonical)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(supplied, monkeypatch, operation)
    assert normalized(initial) == normalized(clean(canonical, tmp_path / "initial-cache"))
    old = memberships(initial)
    assert len(old) == 4 and all(md["status"] == "resolved" for md in old.values())
    build = supplied / "CMakeLists.txt"
    build.write_bytes(build.read_bytes().replace(b"QML_FILES Main.qml", b"QML_FILES"))
    updated = run(supplied, monkeypatch, operation, [build])
    retired = set(old) - set(memberships(updated))
    assert len(retired) == 1 and not retired.intersection(updated)
    assert normalized(updated) == normalized(clean(canonical, tmp_path / "changed-cache"))
    assert normalized(run(supplied, monkeypatch, operation, [])) == normalized(updated)
    for source, target, data in updated.edges(data=True):
        if data.get("context") == "qt_membership_site":
            assert source not in retired and target not in retired


@pytest.mark.parametrize("corruption", ["outside_root", "conflicting_source"])
def test_req_qml020_ac02_path_alias_cannot_authorize_foreign_source(
        aliased_parent, tmp_path, corruption):
    """A real outside/other source path still raises the established integrity diagnostic."""
    parent, alias = aliased_parent
    canonical, supplied = parent / "native-profile", alias / "native-profile"
    native_module_smoke(canonical)
    _, result = extract_graph(canonical, canonical, tmp_path / "accepted-cache")
    nodes, edges = copy.deepcopy((result["nodes"], result["edges"]))
    declaration = next(node for node in nodes if qml_metadata(node).get("kind") == "qt_source")
    if corruption == "outside_root":
        foreign = parent / "foreign/CMakeLists.txt"
        foreign.parent.mkdir()
        foreign.write_bytes((canonical / "CMakeLists.txt").read_bytes())
        path = alias / "foreign/CMakeLists.txt"
    else:
        path = supplied / "other.cmake"
        path.write_bytes((canonical / "CMakeLists.txt").read_bytes())
    active = {path: {"nodes": [declaration], "edges": []}}
    index = QtProjectIndex(nodes, edges, root=canonical)
    before = copy.deepcopy((nodes, edges, active))
    with pytest.raises(ValueError, match="QML_METADATA: membership declaration source is not accepted"):
        resolve_project_memberships(active, nodes, edges, root=canonical, project_index=index)
    assert (nodes, edges, active) == before


@pytest.mark.parametrize("error_type", [OSError, RuntimeError])
def test_req_qml020_ac02_input_resolution_failure_is_bounded_and_preserves_facts(
        tmp_path, monkeypatch, error_type):
    """Filesystem failure/alias loops cannot leak backend bodies or partially publish."""
    canonical = tmp_path / "native-profile"
    native_module_smoke(canonical)
    _, result = extract_graph(canonical, canonical, tmp_path / "accepted-cache")
    nodes, edges = copy.deepcopy((result["nodes"], result["edges"]))
    declaration = next(node for node in nodes if qml_metadata(node).get("kind") == "qt_source")
    build = canonical / "CMakeLists.txt"
    active = {build: {"nodes": [declaration], "edges": []}}
    index = QtProjectIndex(nodes, edges, root=canonical)
    before = copy.deepcopy((nodes, edges, active))
    real, observed = Path.resolve, []
    private_body = "private-filesystem-backend-body"

    def fail_input_only(path, *args, **kwargs):
        # Accepted parsing/indexing is complete. Fail only this supplied input
        # identity operation; root and all other real path behavior stay intact.
        if path == build:
            observed.append(path)
            raise error_type(private_body)
        return real(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", fail_input_only)
    with pytest.raises(ValueError) as failure:
        resolve_project_memberships(active, nodes, edges, root=canonical, project_index=index)
    assert str(failure.value) == "QML_METADATA: membership declaration source is not accepted"
    assert private_body not in repr(failure.value) and failure.value.__cause__ is None
    assert observed == [build] and (nodes, edges, active) == before


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml020_ac02_conflicting_transport_retains_durable_products_and_recovers(
        aliased_parent, tmp_path, monkeypatch, operation):
    """Rejected accepted-input transport preserves saved graph/manifest/stamp/root products."""
    import graphify.qt_project_membership as membership
    from graphify.watch import _rebuild_code

    parent, alias = aliased_parent
    canonical, supplied = parent / "native-profile", alias / "native-profile"
    native_module_smoke(supplied)
    monkeypatch.chdir(canonical)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(supplied, monkeypatch, operation)
    output = canonical / "graphify-out"
    products = ("graph.json", "manifest.json", ".qt_analysis.json", ".graphify_root")
    before = {name: (output / name).read_bytes() for name in products}
    build = supplied / "CMakeLists.txt"
    source = build.read_bytes()
    build.write_bytes(source + b"\n# trigger accepted-source refresh\n")
    real = membership.resolve_project_memberships

    def conflict(results, *args, **kwargs):
        # Corrupt only the transported input owner. Real parsing, source facts,
        # per-run indexes, diagnostic handling, and durable writers still run.
        wrong = {Path(path).with_name("other.cmake"): value for path, value in results.items()}
        return real(wrong, *args, **kwargs)

    with monkeypatch.context() as rejected:
        rejected.setattr(membership, "resolve_project_memberships", conflict)
        if operation == "manual":
            with pytest.raises(SystemExit) as failure:
                run(supplied, rejected, operation, [build])
            assert failure.value.code == 1
        else:
            assert not _rebuild_code(supplied, changed_paths=[build], no_cluster=True)
    assert before == {name: (output / name).read_bytes() for name in products}
    build.write_bytes(source)
    repaired = run(supplied, monkeypatch, operation, [build])
    assert normalized(repaired) == normalized(initial)
    assert normalized(run(supplied, monkeypatch, operation, [])) == normalized(initial)
