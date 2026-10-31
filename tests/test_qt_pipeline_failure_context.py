"""REQ-QML-012/020: join failures remain bounded after input identity breaks."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import graphify.extract as extraction
import graphify.qt_project_membership as membership
from graphify.extractors.qml_facts import qml_metadata
from graphify.qt_qml_pipeline import resolve_qt_qml
from graphify.watch import _rebuild_code
from tests.qml_installed_smoke import native_module_smoke
from tests.test_qt_final_incremental_parity import normalized, run
from tests.test_qt_project_membership_aliases import aliased_parent  # noqa: F401 - shared real host fixture


NAMES = ("backend.h", "Main.qml", "loader.cpp", "CMakeLists.txt", "resources.qrc")
PRIVATE_BODY = "private-filesystem-backend-body"


def raw_project(root, *, metadata_path=None):
    """Produce actual parser facts before the owning join creates its per-run index."""
    paths = [metadata_path if name == "CMakeLists.txt" and metadata_path is not None
             else root / name for name in (*NAMES, "keep.py")]
    per_file = [extraction._safe_extract_with_xaml_root(
        extraction._get_extractor(path), path, root) for path in paths]
    assert all(not result.get("error") for result in per_file)
    nodes = [node for result in per_file for node in result["nodes"]]
    edges = [edge for result in per_file for edge in result["edges"]]
    return paths, per_file, nodes, edges


def project(root):
    native_module_smoke(root)
    (root / "keep.py").write_bytes(b"def retained(): return 7\n")


def arm_failure(monkeypatch, build, error_type):
    """Fail only the accepted input after real parsing, collection, and indexing."""
    real_membership, real_resolve = membership.resolve_project_memberships, Path.resolve
    reached = []

    def fail_input(path, *args, **kwargs):
        if path == build:
            raise error_type(PRIVATE_BODY)
        return real_resolve(path, *args, **kwargs)

    def arm(results, *args, **kwargs):
        assert build in results and kwargs["project_index"].nodes
        assert any(qml_metadata(node).get("kind") == "qt_source"
                   for node in results[build]["nodes"])
        reached.append("accepted_join")
        if error_type is None:
            raise ValueError(PRIVATE_BODY)
        # The patch survives the membership exception, so the real diagnostic
        # path must withstand the same persistent OSError or alias-loop failure.
        monkeypatch.setattr(Path, "resolve", fail_input)
        return real_membership(results, *args, **kwargs)

    monkeypatch.setattr(membership, "resolve_project_memberships", arm)
    return reached


def assert_failure_context(paths, per_file, failed, expected_build):
    """Every affected source has bounded context; unrelated Python stays unaffected."""
    assert set(failed) == {str(path) for path in paths if path.name != "keep.py"}
    for path, result in zip(paths, per_file):
        if path.name == "keep.py":
            assert not result.get("qml_failures") and not result.get("diagnostics")
            continue
        source = expected_build if path.name == "CMakeLists.txt" else path.name
        assert result["qml_failures"] == [{"code": "QML_RESOLUTION_FAILED", "source_file": source}]
        assert result["diagnostics"] == [{
            "code": "QML_RESOLUTION_FAILED", "severity": "error", "owner": "qt_qml_resolution",
            "source_file": source, "message": "Qt/QML project join failed",
            "recovery": "Correct the join failure and retry; prior graph is preserved.",
        }]
    assert PRIVATE_BODY not in json.dumps(per_file)


@pytest.mark.parametrize("error_type", [None, OSError, RuntimeError])
def test_req_qml012_ac01_all_sources_keep_safe_context_after_join_failure(
        tmp_path, monkeypatch, error_type):
    """Ordinary and persistent failures return complete diagnostics, never backend exceptions."""
    root = tmp_path / "native-profile"
    project(root)
    paths, per_file, nodes, edges = raw_project(root)
    reached = arm_failure(monkeypatch, root / "CMakeLists.txt", error_type)
    failed = resolve_qt_qml(paths, per_file, nodes, edges, root=root)
    assert reached == ["accepted_join"]
    assert_failure_context(paths, per_file, failed, "CMakeLists.txt")


@pytest.mark.parametrize("error_type", [None, OSError, RuntimeError])
def test_req_qml012_ac01_real_alias_uses_canonical_or_explicit_unavailable_context(
        aliased_parent, monkeypatch, error_type):
    """Real parent aliases retain canonical context, or an empty label when identity is inaccessible."""
    parent, alias = aliased_parent
    root = parent / "native-profile"
    project(root)
    build = alias / "native-profile/CMakeLists.txt"
    assert build.resolve() == root / "CMakeLists.txt"
    paths, per_file, nodes, edges = raw_project(root, metadata_path=build)
    reached = arm_failure(monkeypatch, build, error_type)
    failed = resolve_qt_qml(paths, per_file, nodes, edges, root=root)
    assert reached == ["accepted_join"]
    assert_failure_context(paths, per_file, failed, "CMakeLists.txt" if error_type is None else "")
    assert all(not qml_metadata(node).get("kind") == "membership_resolution" for node in nodes)


def test_req_qml020_ac02_foreign_transport_cannot_gain_authority_from_diagnostic_context(tmp_path):
    """A rejected outside-root owner has no private path label and publishes no fallback target."""
    root = tmp_path / "native-profile"
    project(root)
    paths, per_file, nodes, edges = raw_project(root)
    paths[NAMES.index("CMakeLists.txt")] = tmp_path / "private-external-input/CMakeLists.txt"
    failed = resolve_qt_qml(paths, per_file, nodes, edges, root=root)
    assert_failure_context(paths, per_file, failed, "")
    assert "private-external-input" not in json.dumps(per_file)
    assert not any(qml_metadata(node).get("kind") == "membership_resolution" for node in nodes)
    assert not any(edge.get("context") in {"qt_project_source", "qt_resource_membership"} for edge in edges)


@pytest.mark.parametrize("delimiter", ["\n", "\r", "\t", "\x00", "\x1b", "\x7f", "\x85", "\u2028", "\u2029"])
def test_req_qml012_ac01_injected_context_delimiters_are_explicitly_unavailable(tmp_path, delimiter):
    """Untrusted transported labels cannot inject control characters into join diagnostics."""
    root = tmp_path / "native-profile"
    project(root)
    paths, per_file, nodes, edges = raw_project(root)
    paths[NAMES.index("CMakeLists.txt")] = root / ("injected" + delimiter + "label/CMakeLists.txt")
    failed = resolve_qt_qml(paths, per_file, nodes, edges, root=root)
    assert_failure_context(paths, per_file, failed, "")
    assert delimiter not in "".join(diagnostic["source_file"] for result in per_file
                                    for diagnostic in result.get("diagnostics", []))


@pytest.mark.parametrize("length", [160, 161])
def test_req_qml012_ac01_context_ceiling_preserves_or_rejects_complete_relative_label(tmp_path, length):
    """The diagnostic-only 160-character ceiling never truncates a source into another identity."""
    root = tmp_path / "native-profile"
    project(root)
    paths, per_file, nodes, edges = raw_project(root)
    relative = "a" * (length - len("/CMakeLists.txt")) + "/CMakeLists.txt"
    assert len(relative) == length
    paths[NAMES.index("CMakeLists.txt")] = root / relative
    failed = resolve_qt_qml(paths, per_file, nodes, edges, root=root)
    assert_failure_context(paths, per_file, failed, relative if length == 160 else "")
    assert not any(qml_metadata(node).get("kind") == "membership_resolution" for node in nodes)


@pytest.mark.parametrize("operation", ["manual", "watch"])
@pytest.mark.parametrize("error_type", [OSError, RuntimeError])
def test_req_qml012_ac02_persistent_failure_retains_products_and_repairs_without_leaking(
        tmp_path, monkeypatch, capsys, operation, error_type):
    """Actual update writers reject safely, keep four durable products, repair, then repeat."""
    root = tmp_path / "native-profile"
    project(root)
    monkeypatch.chdir(root)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(root, monkeypatch, operation)
    output = root / "graphify-out"
    names = ("graph.json", "manifest.json", ".qt_analysis.json", ".graphify_root")
    before = {name: (output / name).read_bytes() for name in names}
    build = root / "CMakeLists.txt"
    original = build.read_bytes()
    build.write_bytes(original + b"\n# trigger accepted-source refresh\n")
    capsys.readouterr()
    with monkeypatch.context() as failure:
        reached = arm_failure(failure, build, error_type)
        if operation == "manual":
            with pytest.raises(SystemExit) as rejected:
                run(root, failure, operation, [build])
            assert rejected.value.code == 1
        else:
            assert not _rebuild_code(root, changed_paths=[build], no_cluster=True)
        assert reached == ["accepted_join"]
    captured = capsys.readouterr()
    assert PRIVATE_BODY not in captured.out + captured.err
    # The join's per-source code is asserted above. The actual writer retains
    # its separate documented publication-rejection diagnostic at this boundary.
    assert "QML_GRAPH_PRESERVED" in captured.out + captured.err
    assert before == {name: (output / name).read_bytes() for name in names}
    build.write_bytes(original)
    repaired = run(root, monkeypatch, operation, [build])
    assert normalized(repaired) == normalized(initial)
    repaired_products = {name: (output / name).read_bytes() for name in names}
    assert normalized(run(root, monkeypatch, operation, [])) == normalized(initial)
    assert repaired_products == {name: (output / name).read_bytes() for name in names}
