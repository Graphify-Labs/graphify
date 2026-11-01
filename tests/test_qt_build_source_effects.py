"""INC-QML-95: bounded negative source effects never create build/compile facts."""
from __future__ import annotations

import pytest

from graphify.extract import extract
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.extractors.qt_cpp_syntax import QtCppError, read_cpp
from graphify.extractors.qt_cpp_test_context import build_qt_test_contexts
from tests.qt_analysis_helpers import sites
from tests.test_qt_build_include_context import CMAKE, project


REGISTRY = "get_property(owned DIRECTORY PROPERTY BUILDSYSTEM_TARGETS)\n"


def fixture(root, effect):
    """Every declared auxiliary source is explicit input data, never a build or discovery target."""
    paths = list(project(root, cmake=CMAKE + "qt_add_executable(Other other.cpp)\n" + effect))
    for name in ("other.cpp", "helper.cpp", "later.cpp", "tst_alpha.cpp", "tst_beta.cpp", "tst_view.cpp", "tst_edit.cpp"):
        path = root / "tests" / name
        path.write_text("void auxiliary(){}\n")
        paths.append(path)
    return paths


def snapshot(root, paths):
    return build_qt_test_contexts([path for path in paths if path.suffix in {".cpp", ".h"}],
                                 root=root, project_paths=[paths[2]])


SAFE = [
    REGISTRY + "foreach(target IN LISTS owned)\nif(FLAG)\n"
    "target_sources(${target} PRIVATE helper.cpp)\nendif()\nendforeach()\n",
    "foreach(target IN ITEMS Other Later)\ntarget_sources(${target} PRIVATE helper.cpp)\nendforeach()\n",
    "set(extra helper.cpp)\nif(FLAG)\nlist(APPEND extra later.cpp)\nendif()\n" + REGISTRY
    + "foreach(target IN LISTS owned)\ntarget_sources(${target} PRIVATE ${extra})\nendforeach()\n",
    "foreach(kind IN ITEMS Alpha Beta)\nstring(TOLOWER ${kind} stem)\n"
    "qt_add_executable(Tool${kind} tst_${stem}.cpp)\nendforeach()\n",
    "foreach(mode IN ITEMS view edit)\nif(FLAG)\nset(other ToolView)\nelse()\nset(other ToolEdit)\nendif()\n"
    "qt_add_executable(${other} tst_${mode}.cpp)\nendforeach()\n",
]


@pytest.mark.parametrize("effect", SAFE)
def test_req_qml022_ac03_finite_disjoint_source_effect_preserves_only_existing_literal_profile(tmp_path, effect):
    """Complete negative domains remove a veto without synthesizing a target, source membership or configured compiler."""
    paths = fixture(tmp_path, effect)
    contexts = snapshot(tmp_path, paths)
    context = contexts.for_path(paths[0])
    assert context is not None and context.build_witnesses
    assert {w.profile.target for c in contexts.contexts for w in c.build_witnesses} == {"Check"}
    unit = read_cpp(paths[0], tmp_path, qt_test_context=context)
    assert len(unit.qt_test_macros) == 2 and len(unit.test_launchers) == 1
    # Full facade propagation is distinct from CMake's existing QML-module
    # profile. Its unsupported diagnostic must not be erased by this feature.
    result = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not any(row.get("source_file") == "tests/check.cpp" for row in result.get("qml_failures", []))
    assert len(sites(result, "test_data")) == 1
    assert qt_metadata(sites(result, "test_data")[0]).get("build_include_witnesses")
    if "target_sources(" in effect:
        assert any(row.get("source_file") == "tests/CMakeLists.txt" and row.get("code") == "QML_PROJECT_UNSUPPORTED"
                   for row in result.get("qml_failures", []))


UNAVAILABLE = [
    REGISTRY + "foreach(target IN LISTS owned)\ntarget_sources(${target} PRIVATE check.cpp)\nendforeach()\n",
    REGISTRY + "foreach(target IN LISTS owned)\ntarget_sources(${target} PRIVATE ${external})\nendforeach()\n",
    "set(who Other;PRIVATE;check.cpp)\ntarget_sources(${who} PRIVATE helper.cpp)\n",
    "target_sources(${external} PRIVATE helper.cpp)\n",
    REGISTRY + "foreach(target IN LISTS owned)\n"
    "target_sources(${target} PRIVATE FILE_SET HEADERS BASE_DIRS ../src FILES ../src/api.h)\nendforeach()\n",
    REGISTRY + "foreach(target IN LISTS owned)\ntarget_include_directories(${target} PRIVATE ../src)\nendforeach()\n",
    "if(FLAG)\n" + REGISTRY + "endif()\nforeach(target IN LISTS owned)\n"
    "target_sources(${target} PRIVATE helper.cpp)\nendforeach()\n",
    REGISTRY + "set(owned ${external})\nforeach(target IN LISTS owned)\n"
    "target_sources(${target} PRIVATE helper.cpp)\nendforeach()\n",
    "foreach(mode IN ITEMS Alpha)\nset(other Check)\nqt_add_executable(${other} other.cpp)\nendforeach()\n",
    "foreach(mode IN ITEMS Alpha)\nqt_add_executable(Tool${mode} check.cpp)\nendforeach()\n",
    "foreach(mode IN ITEMS Alpha)\nqt_add_executable(${external}${mode} tst_${mode}.cpp)\nendforeach()\n",
]


@pytest.mark.parametrize("effect", UNAVAILABLE)
def test_req_qml022_ac03_unknown_overlapping_or_root_mutating_effect_cannot_lend_context(tmp_path, effect):
    """Owner/source collision, argument injection, unknown data and root changes stay explicit unavailable."""
    paths = fixture(tmp_path, effect)
    contexts = snapshot(tmp_path, paths)
    with pytest.raises(QtCppError, match="syntax|launcher"):
        read_cpp(paths[0], tmp_path, qt_test_context=contexts.for_path(paths[0]))


def test_req_qml022_ac03_unknown_foreign_manifest_source_claim_cannot_hide_behind_file_boundary(tmp_path):
    """A separate admitted CMake source can still assign the current TU to another unknown target."""
    paths = fixture(tmp_path, "")
    other = tmp_path / "tests/effects.cmake"
    other.write_text("target_sources(${external} PRIVATE check.cpp)\n")
    contexts = build_qt_test_contexts([path for path in paths if path.suffix in {".cpp", ".h"}],
                                     root=tmp_path, project_paths=[paths[2], other])
    with pytest.raises(QtCppError):
        read_cpp(paths[0], tmp_path, qt_test_context=contexts.for_path(paths[0]))
