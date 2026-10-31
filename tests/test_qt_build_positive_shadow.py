"""INC-QML-97: literal positive build calls need cohort-owned command identity."""
from __future__ import annotations

from dataclasses import replace
import hashlib

import pytest

import graphify.__main__ as entrypoint
from graphify.extract import extract
from graphify.extractors.qt_cpp_build_types import BuildInput
from graphify.extractors.qt_cpp_syntax import QtCppError, read_cpp
from graphify.extractors.qt_cpp_test_context import QtTestContextError, build_qt_test_contexts, verify_test_contexts
from graphify.watch import _rebuild_code
from tests.qt_analysis_helpers import sites
from tests.test_qt_build_include_context import project
from tests.test_qt_final_incremental_parity import clean, normalized, published, unrelated
from tests.test_qt_semantic_correction_updates import products

_POSITIVE = ("add_executable", "qt_add_executable", "qt6_add_executable", "target_sources", "target_include_directories")


def definition(name, kind="function"):
    return f"{kind}({name})\nend{kind}()\n"


def fixture(root, extra="", *, same_file=False):
    """The parent is explicit input; its function can precede the child's literal calls without execution here."""
    paths = list(project(root))
    parent = root / "CMakeLists.txt"
    parent.write_bytes((extra + "add_subdirectory(tests)\n").encode())
    if same_file:
        paths[2].write_bytes(paths[2].read_bytes() + extra.encode())
        parent.write_bytes(b"add_subdirectory(tests)\n")
    (root / "keep.py").write_bytes(b"def helper():return 1\n\ndef retained():return helper()\n")
    return [*paths, parent]


def snapshot(root, paths):
    return build_qt_test_contexts(paths[:2], root=root, project_paths=paths[2:])


@pytest.mark.parametrize("extra", ["", definition("helper"), definition("message"), definition("target_include_directories_helper")])
def test_req_qml022_ac03_literal_control_and_unrelated_definition_keep_positive_source_context(tmp_path, extra):
    """The census rejects ambiguous modeled command identity, not every unrelated function declaration."""
    paths = fixture(tmp_path, extra)
    contexts = snapshot(tmp_path, paths)
    context = contexts.for_path(paths[0])
    assert context is not None and len(context.build_witnesses) == 1
    assert len(read_cpp(paths[0], tmp_path, qt_test_context=context).qt_test_macros) == 2
    verify_test_contexts(contexts, root=tmp_path)
    result = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not result.get("qml_failures")
    assert len(sites(result, "test_data")) == len(sites(result, "test_assertion")) == len(sites(result, "test_launcher")) == 1


@pytest.mark.parametrize("name", _POSITIVE)
@pytest.mark.parametrize("kind", ["function", "macro"])
@pytest.mark.parametrize("same_file", [False, True])
def test_req_qml022_ac03_positive_command_shadow_is_rejected_in_every_admitted_manifest(tmp_path, name, kind, same_file):
    """A separate parent definition must veto the same identity that the existing same-file guard rejects."""
    paths = fixture(tmp_path, definition(name.upper(), kind), same_file=same_file)
    contexts = snapshot(tmp_path, paths)
    assert not contexts.build_profiles
    context = contexts.for_path(paths[0])
    assert context is not None and not context.build_witnesses
    with pytest.raises(QtCppError) as rejected:
        read_cpp(paths[0], tmp_path, qt_test_context=context)
    assert rejected.value.code == "QT_CPP_SYNTAX"
    verify_test_contexts(contexts, root=tmp_path)
    result = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    assert any(row["source_file"] == "tests/check.cpp" and row["code"] == "QT_CPP_SYNTAX"
               for row in result.get("qml_failures", []))
    assert not sites(result, "test_data") and not sites(result, "test_assertion") and not sites(result, "test_launcher")


@pytest.mark.parametrize("name", ["${api_name}", "", '""', '"bad;name"'])
def test_req_qml022_ac03_incomplete_definition_name_census_cannot_authorize_positive_calls(tmp_path, name):
    """Unknown/list-expanded/missing identities cannot be assumed unrelated to a positive command."""
    paths = fixture(tmp_path, definition(name))
    contexts = snapshot(tmp_path, paths)
    assert not contexts.build_profiles
    with pytest.raises(QtCppError):
        read_cpp(paths[0], tmp_path, qt_test_context=contexts.for_path(paths[0]))


@pytest.mark.parametrize("failure", ["missing", "invalid_utf8", "malformed_scope"])
def test_req_qml022_ac03_incomplete_metadata_read_or_parse_cannot_supply_a_partial_census(tmp_path, failure):
    """A failed supplied census input never leaves the remaining literal calls as positive authority."""
    paths = fixture(tmp_path)
    extra = tmp_path / "extra.cmake"
    if failure != "missing":
        extra.write_bytes(b"\xff" if failure == "invalid_utf8" else b"if(FLAG)\n")
    contexts = build_qt_test_contexts(paths[:2], root=tmp_path, project_paths=[*paths[2:], extra])
    assert not contexts.build_profiles
    with pytest.raises(QtCppError):
        read_cpp(paths[0], tmp_path, qt_test_context=contexts.for_path(paths[0]))


@pytest.mark.parametrize("reverse", [False, True])
def test_req_qml022_ac03_scope_and_supplied_order_do_not_isolate_a_potential_builtin_shadow(tmp_path, reverse):
    """Unknown activation conditions and metadata enumeration cannot decide command identity for the cohort."""
    paths = fixture(tmp_path)
    paths[-1].write_bytes(b"add_subdirectory(tests)\nif(FLAG)\n" + definition("target_include_directories").encode() + b"endif()\n")
    metadata = list(reversed(paths[2:])) if reverse else paths[2:]
    contexts = build_qt_test_contexts(paths[:2], root=tmp_path, project_paths=metadata)
    assert not contexts.build_profiles
    with pytest.raises(QtCppError):
        read_cpp(paths[0], tmp_path, qt_test_context=contexts.for_path(paths[0]))


def test_req_qml022_ac06_fresh_hashes_cannot_repair_positive_profile_with_new_shadowed_owner(tmp_path):
    """Actual semantic replay rejects an otherwise well-typed self-consistent hash update to a stale profile."""
    paths = fixture(tmp_path)
    contexts = snapshot(tmp_path, paths)
    assert contexts.build_profiles
    parent = paths[-1]
    parent.write_bytes(b"\xef\xbb\xbf# caf\xc3\xa9 \xe9\x9b\xaa\r\n" +
                       (definition("target_include_directories") + "add_subdirectory(tests)\n").replace("\n", "\r\n").encode())
    inputs = tuple(BuildInput(item.source_file, hashlib.sha256(parent.read_bytes()).hexdigest())
                   if item.source_file == "CMakeLists.txt" else item for item in contexts.build_inputs)
    with pytest.raises(QtTestContextError) as rejected:
        verify_test_contexts(replace(contexts, build_inputs=inputs), root=tmp_path)
    assert rejected.value.code == "QT_CPP_CONTEXT"


def invoke(root, monkeypatch, operation, *, force=False, changes=None):
    """Only unrelated skill maintenance is suppressed; real CLI/watch admission and publication own the result."""
    if operation == "watch":
        return _rebuild_code(root, changed_paths=changes, no_cluster=True, force=force)
    monkeypatch.setattr(entrypoint, "_check_skill_version", lambda *_: None)
    monkeypatch.setattr(entrypoint, "_refresh_stale_skills", lambda: None)
    monkeypatch.setattr(entrypoint.sys, "argv", ["graphify", "update", str(root), "--no-cluster"] + (["--force"] if force else []))
    entrypoint.main()
    return True


def retained(root):
    return {**products(root), "report.md": (root / "graphify-out/report.md").read_bytes()}


@pytest.mark.parametrize("operation", ["manual", "watch"])
@pytest.mark.parametrize("force", [False, True])
def test_req_qml022_ac06_metadata_only_positive_shadow_rejects_retains_recovers_and_settles(tmp_path, monkeypatch, operation, force):
    """A warm metadata-only edit cannot publish stale root authority, including repeated forced updates."""
    paths = fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    assert invoke(tmp_path, monkeypatch, operation)
    initial = published(tmp_path)
    assert normalized(initial) == normalized(clean(tmp_path, tmp_path / ".cold"))
    (tmp_path / "graphify-out/report.md").write_bytes(b"Previously accepted positive root profile\n")
    before = retained(tmp_path)
    parent, original = paths[-1], paths[-1].read_bytes()
    parent.write_bytes(definition("target_include_directories").encode() + original)
    for _ in range(2):
        if operation == "manual":
            with pytest.raises(SystemExit) as rejected:
                invoke(tmp_path, monkeypatch, operation, force=force)
            assert rejected.value.code == 1
        else:
            assert not invoke(tmp_path, monkeypatch, operation, force=force, changes=[parent])
        assert retained(tmp_path) == before
    parent.write_bytes(original)
    assert invoke(tmp_path, monkeypatch, operation, changes=[parent])
    recovered = published(tmp_path)
    assert normalized(recovered) == normalized(initial)
    assert unrelated(recovered) == unrelated(initial)
    assert normalized(recovered) == normalized(clean(tmp_path, tmp_path / ".recovered"))
    accepted = retained(tmp_path)
    assert invoke(tmp_path, monkeypatch, operation, changes=[])
    assert retained(tmp_path) == accepted
