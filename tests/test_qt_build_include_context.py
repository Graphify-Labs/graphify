"""INC-QML-93: only admitted target-owned roots resolve quoted include context."""
from __future__ import annotations

import copy

import pytest

from graphify.extract import extract
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.extractors.qt_cpp_syntax import QtCppError, read_cpp
from graphify.extractors.qt_cpp_test_context import build_qt_test_contexts, verify_test_contexts
from tests.qt_analysis_helpers import sites


SOURCE = ('#include "api.h"\n#include <QtTest>\n'
          'class Checks:public QObject{Q_OBJECT private slots:void run(){QFETCH(int,value);QTRY_COMPARE(value,1);}};\n'
          'QTEST_MAIN(Checks)\n')
CMAKE = 'qt_add_executable(Check check.cpp)\ntarget_include_directories(Check PRIVATE ../src)\n'


def project(root, *, cmake=CMAKE, header="struct Api{};\n", source=SOURCE):
    paths = []
    for name, text in {"tests/check.cpp": source, "src/api.h": header, "tests/CMakeLists.txt": cmake}.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode())
        paths.append(path)
    return paths[0], paths[1], paths[2]


def snapshot(root, paths):
    return build_qt_test_contexts(paths[:2], root=root, project_paths=paths[2:])


def test_req_qml022_ac03_no_build_metadata_keeps_existing_unknown_include_rejection(tmp_path):
    """The new path must not broaden an ordinary partial API that supplies no build ownership."""
    paths = project(tmp_path)
    contexts = build_qt_test_contexts(paths[:2], root=tmp_path)
    with pytest.raises(QtCppError):
        read_cpp(paths[0], tmp_path, qt_test_context=contexts.for_path(paths[0]))


def test_req_qml022_ac03_literal_owned_root_eliminates_unknown_header_without_discovery(tmp_path):
    """Exact target/source/root/hash/span witnesses admit source-only syntax through a provided header."""
    paths = project(tmp_path)
    contexts = snapshot(tmp_path, paths)
    before = copy.deepcopy(contexts)
    context = contexts.for_path(paths[0])
    assert context is not None and context.build_witnesses
    unit = read_cpp(paths[0], tmp_path, qt_test_context=context)
    assert len(unit.qt_test_macros) == 2 and len(unit.test_launchers) == 1
    verify_test_contexts(contexts, root=tmp_path)
    assert contexts == before


def test_req_qml022_ac06_facade_propagates_one_snapshot_and_keeps_build_provenance(tmp_path):
    """The actual production facade supplies admitted metadata to generic and Qt source producers."""
    paths = project(tmp_path)
    result = extract(list(paths), root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not result.get("qml_failures")
    assert len(sites(result, "test_data")) == len(sites(result, "test_assertion")) == len(sites(result, "test_launcher")) == 1
    for node in sites(result, "test_data") + sites(result, "test_assertion") + sites(result, "test_launcher"):
        assert qt_metadata(node).get("build_include_witnesses")


@pytest.mark.parametrize("cmake", [
    'qt_add_executable(Check check.cpp)\nqt_add_executable(Other other.cpp)\ntarget_include_directories(Other PRIVATE ../src)\n',
    CMAKE.replace("PRIVATE", "INTERFACE"),
    CMAKE.replace("PRIVATE", "SYSTEM PRIVATE"),
    CMAKE.replace("../src", "${SOURCE_ROOT}"),
    'qt_add_executable(Check check.cpp)\nif(FEATURE)\ntarget_include_directories(Check PRIVATE ../src)\nendif()\n',
    'qt_add_executable(Check check.cpp)\nqt_add_executable(Check other.cpp)\ntarget_include_directories(Check PRIVATE ../src)\n',
])
def test_req_qml022_ac03_foreign_dynamic_conditional_or_conflicting_targets_cannot_lend_roots(tmp_path, cmake):
    """Incomplete or another target's build metadata never becomes a convenient global include path."""
    paths = project(tmp_path, cmake=cmake)
    contexts = snapshot(tmp_path, paths)
    with pytest.raises(QtCppError):
        read_cpp(paths[0], tmp_path, qt_test_context=contexts.for_path(paths[0]))


def test_req_qml022_ac03_source_relative_header_has_precedence_over_owned_roots(tmp_path):
    """A provided local header wins even when a root header would interfere with the selected macros."""
    paths = project(tmp_path, header="#undef QFETCH\n")
    local = tmp_path / "tests/api.h"
    local.write_bytes(b"struct Local{};\n")
    contexts = build_qt_test_contexts([*paths[:2], local], root=tmp_path, project_paths=paths[2:])
    assert len(read_cpp(paths[0], tmp_path, qt_test_context=contexts.for_path(paths[0])).qt_test_macros) == 2


def test_req_qml022_ac03_existing_unprovided_local_shadow_is_rejection_only_and_never_opened(tmp_path, monkeypatch):
    """A positive root candidate cannot bypass an excluded source-relative file."""
    paths = project(tmp_path)
    local = tmp_path / "tests/api.h"
    local.write_bytes(b"#undef QFETCH\n")
    original = type(local).open

    def admitted_only(path, *args, **kwargs):
        assert path != local, "Unprovided header content must never be opened"
        return original(path, *args, **kwargs)

    with monkeypatch.context() as guard:
        guard.setattr(type(local), "open", admitted_only)
        contexts = snapshot(tmp_path, paths)
        with pytest.raises(QtCppError):
            read_cpp(paths[0], tmp_path, qt_test_context=contexts.for_path(paths[0]))


def test_req_qml022_ac06_new_local_shadow_invalidates_accepted_absence_witness(tmp_path):
    """A final coherent checkpoint detects a new shadow without reading or admitting that file."""
    paths = project(tmp_path)
    contexts = snapshot(tmp_path, paths)
    assert contexts.absences
    (tmp_path / "tests/api.h").write_bytes(b"struct Later{};\n")
    from graphify.extractors.qt_cpp_test_context import QtTestContextError
    with pytest.raises(QtTestContextError):
        verify_test_contexts(contexts, root=tmp_path)
