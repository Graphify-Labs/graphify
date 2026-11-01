"""INC-QML-93: exact build ownership, lookup precedence and typed transport."""
from __future__ import annotations

from dataclasses import replace
import pickle

import pytest

from graphify.extractors.qt_cpp_syntax import QtCppError, read_cpp
from graphify.extractors.qt_cpp_test_context import QtTestContextError, build_qt_test_contexts, verify_test_contexts
from tests.test_qt_build_include_context import CMAKE, SOURCE, project, snapshot


@pytest.mark.parametrize("suffix", [
    "qt_add_executable(Other check.cpp)\n",
    "qt_add_executable(Other check.cpp)\ntarget_include_directories(Other SYSTEM PRIVATE ../src)\n",
    "target_include_directories(Check PRIVATE ../src)\n",
    "target_sources(Check PRIVATE $<TARGET_OBJECTS:Other>)\n",
    "target_include_directories(${WHICH} PRIVATE ../other)\n",
    "set_target_properties(${WHICH} PROPERTIES INCLUDE_DIRECTORIES ../other)\n",
    "set_property(TARGET ${WHICH} PROPERTY INCLUDE_DIRECTORIES ../other)\n",
])
def test_req_qml022_ac03_competing_unsupported_membership_or_roots_cannot_choose_target(tmp_path, suffix):
    """Rootless/unsupported owners still compete, and duplicate/dynamic root contracts fail closed."""
    paths = project(tmp_path, cmake=CMAKE + suffix)
    context = snapshot(tmp_path, paths).for_path(paths[0])
    with pytest.raises(QtCppError):
        read_cpp(paths[0], tmp_path, qt_test_context=context)


@pytest.mark.parametrize("literal", ["C:src", "C:/src", "//server/share", "\\\\?\\C:\\src", "/src", "../../escape"])
def test_req_qml022_ac03_foreign_or_escaping_build_roots_do_not_gain_authority(tmp_path, literal):
    """Foreign Windows/rooted/escaping spellings are rejected even on another host platform."""
    paths = project(tmp_path, cmake=CMAKE.replace("../src", literal))
    with pytest.raises(QtCppError):
        read_cpp(paths[0], tmp_path, qt_test_context=snapshot(tmp_path, paths).for_path(paths[0]))


def test_req_qml022_ac06_other_root_shadow_creation_invalidates_unique_lookup(tmp_path):
    """Fresh re-resolution checks negative candidates in every root, not just source-local absence."""
    paths = project(tmp_path, cmake=CMAKE.replace("../src", "../src ../other"))
    contexts = snapshot(tmp_path, paths)
    assert contexts.for_path(paths[0]).build_witnesses
    (tmp_path / "other").mkdir()
    (tmp_path / "other/api.h").write_bytes(b"#undef QFETCH\n")
    with pytest.raises(QtTestContextError):
        verify_test_contexts(contexts, root=tmp_path)


def test_req_qml022_ac06_transitive_root_context_and_worker_transport_preserve_origin(tmp_path):
    """An origin target follows provided forward headers; pickle cannot add mutable ambient state."""
    paths = project(tmp_path, source=SOURCE.replace('#include "api.h"\n#include <QtTest>', '#include "forward.h"'))
    forward = tmp_path / "src/forward.h"
    forward.write_bytes(b'#include "api.h"\n#include <QtTest>\n')
    contexts = build_qt_test_contexts([*paths[:2], forward], root=tmp_path, project_paths=paths[2:])
    recovered = pickle.loads(pickle.dumps(contexts))
    verify_test_contexts(recovered, root=tmp_path)
    unit = read_cpp(paths[0], tmp_path, qt_test_context=recovered.for_path(paths[0]))
    assert len(unit.qt_test_macros) == 2 and len(unit.test_launchers) == 1
    assert unit.qt_test_macros[0]["build_include_witnesses"][0]["source_file"] == "tests/check.cpp"


@pytest.mark.parametrize("field,value", [
    ("source_file", []), ("source_file", "\ud800"), ("build_file", None),
    ("target", []), ("target_span", [0, 1, 0, 0, 0, 1]),
    ("build_sha256", "bad"), ("source_span", (0, 0, 0, 0, 0, 0)),
])
def test_req_qml022_ac06_malformed_profile_transport_has_controlled_diagnostic(tmp_path, field, value):
    """Typed checks precede path/hash/index use and never echo corrupt source values."""
    paths = project(tmp_path)
    contexts = snapshot(tmp_path, paths)
    corrupted = replace(contexts, build_profiles=(replace(contexts.build_profiles[0], **{field: value}),))
    with pytest.raises(QtTestContextError) as caught:
        verify_test_contexts(corrupted, root=tmp_path)
    assert caught.value.code == "QT_CPP_CONTEXT" and str(value) not in str(caught.value)


@pytest.mark.parametrize("change", ["omit", "root", "header", "span", "source"])
def test_req_qml022_ac06_forged_or_removed_build_proof_rejects_actual_snapshot(tmp_path, change):
    """A stale denial-free context cannot survive removed or relocated ownership proof."""
    paths = project(tmp_path)
    contexts = snapshot(tmp_path, paths)
    index = contexts.paths.index(str(paths[0].resolve()))
    context, proof = contexts.contexts[index], contexts.contexts[index].build_witnesses[0]
    changes = {"root": {"root": replace(proof.root, directory="tests")},
               "header": {"header_file": "tests/check.cpp"},
               "span": {"include_span": (1, 2, 0, 0, 1, 2)},
               "source": {"importer_file": "src/api.h"}}
    witnesses = () if change == "omit" else (replace(proof, **changes[change]),)
    rows = list(contexts.contexts)
    rows[index] = replace(context, build_witnesses=witnesses)
    with pytest.raises(QtTestContextError):
        verify_test_contexts(replace(contexts, contexts=tuple(rows)), root=tmp_path)


def test_req_qml022_ac03_shared_header_does_not_borrow_another_targets_root_domain(tmp_path):
    """The same admitted header is re-evaluated for each explicit owning translation unit."""
    paths = project(tmp_path, source=SOURCE.replace('"api.h"', '"../shared/forward.h"'))
    shared = tmp_path / "shared/forward.h"
    shared.parent.mkdir()
    shared.write_bytes(b'#include "api.h"\n')
    other = tmp_path / "tests/other.cpp"
    other.write_bytes(SOURCE.replace('"api.h"', '"../shared/forward.h"').encode())
    paths[2].write_bytes((CMAKE + 'qt_add_executable(Other other.cpp)\n').encode())
    contexts = build_qt_test_contexts([*paths[:2], shared, other], root=tmp_path, project_paths=paths[2:])
    assert len(read_cpp(paths[0], tmp_path, qt_test_context=contexts.for_path(paths[0])).qt_test_macros) == 2
    with pytest.raises(QtCppError):
        read_cpp(other, tmp_path, qt_test_context=contexts.for_path(other))


def test_req_qml022_ac03_target_sources_public_ownership_keeps_exact_command_bytes(tmp_path):
    """A literal later source addition belongs to the same target and retains UTF-8/BOM/CRLF offsets."""
    cmake = '\ufeff# café 雪\r\nqt_add_executable(Check)\r\ntarget_sources(Check PUBLIC check.cpp)\r\n'
    cmake += 'target_include_directories(Check PUBLIC ../src)\r\n'
    paths = project(tmp_path, cmake=cmake)
    contexts = snapshot(tmp_path, paths)
    context = contexts.for_path(paths[0])
    assert len(read_cpp(paths[0], tmp_path, qt_test_context=context).qt_test_macros) == 2
    proof = context.build_witnesses[0]
    raw = paths[2].read_bytes()
    assert raw[slice(*proof.profile.source_span[:2])] == b"check.cpp"
    assert raw[slice(*proof.root.token_span[:2])] == b"../src"
    assert proof.root.visibility == "PUBLIC"
    verify_test_contexts(contexts, root=tmp_path)


def test_req_qml022_ac03_symlink_root_escape_or_dangling_local_shadow_cannot_lend_authority(tmp_path):
    """A symlink may not escape the admitted root, and a dangling local link remains present."""
    paths = project(tmp_path)
    local = tmp_path / "tests/api.h"
    try:
        local.symlink_to(tmp_path / "missing.h")
    except OSError:
        pytest.skip("Host does not permit creating a symlink")
    with pytest.raises(QtCppError):
        read_cpp(paths[0], tmp_path, qt_test_context=snapshot(tmp_path, paths).for_path(paths[0]))
    local.unlink()
    outside = tmp_path.parent / (tmp_path.name + "-outside")
    outside.mkdir()
    link = tmp_path / "linked"
    link.symlink_to(outside, target_is_directory=True)
    paths[2].write_bytes(CMAKE.replace("../src", "../linked").encode())
    try:
        with pytest.raises(QtCppError):
            read_cpp(paths[0], tmp_path, qt_test_context=snapshot(tmp_path, paths).for_path(paths[0]))
    finally:
        link.unlink()
        outside.rmdir()


def test_req_qml022_ac06_metadata_removed_after_snapshot_is_controlled_integrity_failure(tmp_path):
    """A disappearing admitted build witness does not silently downgrade proof to an ordinary include."""
    paths = project(tmp_path)
    contexts = snapshot(tmp_path, paths)
    paths[2].unlink()
    with pytest.raises(QtTestContextError):
        verify_test_contexts(contexts, root=tmp_path)


def test_req_qml022_ac06_omitting_every_build_field_cannot_erase_unknown_header_effect(tmp_path):
    """Actual source, not a caller-controlled flag, still requires unknown-header denial without build proof."""
    paths = project(tmp_path)
    contexts = snapshot(tmp_path, paths)
    corrupted = replace(contexts, build_inputs=(), build_profiles=(), absences=(),
                        contexts=tuple(replace(item, build_witnesses=()) for item in contexts.contexts))
    with pytest.raises(QtTestContextError):
        verify_test_contexts(corrupted, root=tmp_path)
    baseline = build_qt_test_contexts(paths[:2], root=tmp_path)
    verify_test_contexts(baseline, root=tmp_path)
    with pytest.raises(QtCppError):
        read_cpp(paths[0], tmp_path, qt_test_context=baseline.for_path(paths[0]))


def test_req_qml022_ac03_buildless_direct_sdk_and_late_unknown_header_preserve_forward_order(tmp_path):
    """Unknown includes after a real macro do not retroactively revoke its earlier literal SDK context."""
    source = '#include <QtTest>\nvoid run(){QFETCH(int,value);}\n#include "late-unknown.h"\n'
    path = tmp_path / "checks.cpp"
    path.write_bytes(source.encode())
    contexts = build_qt_test_contexts([path], root=tmp_path)
    verify_test_contexts(contexts, root=tmp_path)
    unit = read_cpp(path, tmp_path, qt_test_context=contexts.for_path(path))
    assert unit.qt_test_macros[0]["variable"] == "value"
    assert not unit.qt_test_macros[0].get("build_include_witnesses")


@pytest.mark.parametrize("writer", [
    "set_target_properties(Other PROPERTIES INCLUDE_DIRECTORIES ../other)",
    "set_property(TARGET Other APPEND PROPERTY INCLUDE_DIRECTORIES ../other)",
])
def test_req_qml022_ac03_literal_other_target_root_setters_do_not_poison_known_owner(tmp_path, writer):
    """Rejection is narrowed only by an actual literal target owner, never a guessed dynamic spelling."""
    paths = project(tmp_path, cmake=CMAKE + "qt_add_executable(Other other.cpp)\n" + writer + "\n")
    contexts = snapshot(tmp_path, paths)
    assert len(read_cpp(paths[0], tmp_path, qt_test_context=contexts.for_path(paths[0])).qt_test_macros) == 2
    verify_test_contexts(contexts, root=tmp_path)


def test_req_qml022_ac03_unknown_root_writer_in_another_admitted_file_is_not_ignored(tmp_path):
    """An unbound writer may affect any source-local target; its missing local definition lends no isolation."""
    paths = project(tmp_path)
    other = tmp_path / "other.cmake"
    other.write_bytes(b"target_include_directories(${WHICH} PRIVATE other)\n")
    contexts = build_qt_test_contexts(paths[:2], root=tmp_path, project_paths=[paths[2], other])
    with pytest.raises(QtCppError):
        read_cpp(paths[0], tmp_path, qt_test_context=contexts.for_path(paths[0]))


def test_req_qml022_ac03_set_target_properties_keeps_literal_append_named_target(tmp_path):
    """APPEND is a set_property option, but remains an ordinary target name in the separate setter grammar."""
    cmake = CMAKE.replace("Check", "APPEND") + "qt_add_executable(Other other.cpp)\n"
    cmake += "set_target_properties(APPEND Other PROPERTIES INCLUDE_DIRECTORIES ../other)\n"
    paths = project(tmp_path, cmake=cmake)
    with pytest.raises(QtCppError):
        read_cpp(paths[0], tmp_path, qt_test_context=snapshot(tmp_path, paths).for_path(paths[0]))
