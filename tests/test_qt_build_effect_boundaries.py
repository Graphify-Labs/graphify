"""INC-QML-95: source-data joins cannot discard possible competing ownership."""
from __future__ import annotations

import pytest

from graphify.extractors.qt_cpp_syntax import QtCppError, read_cpp
from graphify.extractors.qt_cpp_test_context import build_qt_test_contexts, verify_test_contexts
from tests.test_qt_build_source_effects import REGISTRY, fixture, snapshot


@pytest.mark.parametrize("effect", [
    'set(owners "")\nforeach(name IN ITEMS Other Later)\nlist(APPEND owners ${name})\n'
    'target_sources(${owners} PRIVATE helper.cpp)\nendforeach()\n',
    'set(extra helper.cpp)\nforeach(name IN ITEMS Other Later)\n'
    'target_sources(Other PRIVATE ${extra})\nset(extra check.cpp)\nendforeach()\n',
    'function(message)\nset(extra check.cpp PARENT_SCOPE)\nendfunction()\n'
    'set(extra helper.cpp)\nmessage(STATUS ignored)\nforeach(target IN ITEMS Other)\n'
    'target_sources(${target} PRIVATE ${extra})\nendforeach()\n',
])
def test_req_qml022_ac03_carried_or_shadowed_bindings_cannot_be_a_finite_proof(tmp_path, effect):
    """Later iterations and overridden pure commands may change owner arity or source membership."""
    paths = fixture(tmp_path, effect)
    contexts = snapshot(tmp_path, paths)
    with pytest.raises(QtCppError):
        read_cpp(paths[0], tmp_path, qt_test_context=contexts.for_path(paths[0]))


@pytest.mark.parametrize("before,after", [
    ("set(extra helper.cpp)\nset(extra)\n", ""),
    ("if(FLAG)\nset(extra helper.cpp)\nendif()\n", ""),
    ("set(extra check.cpp)\nif(FLAG)\nset(extra helper.cpp)\nendif()\n", ""),
    ("set(extra helper.cpp)\nfind_package(Unknown CONFIG)\n", ""),
    ("set(extra helper.cpp)\nqt_add_resources(extra more.qrc)\n", ""),
    ("set(extra helper.cpp)\nlist(FILTER extra INCLUDE REGEX .*cpp)\n", ""),
    ("", "set(extra helper.cpp)\n"),
])
def test_req_qml022_ac03_unknown_or_later_binding_never_completes_earlier_source_effect(tmp_path, before, after):
    """Unsets, absent branches, output writers and source order keep prior or inherited payload uncertainty."""
    effect = before + REGISTRY + "foreach(target IN LISTS owned)\ntarget_sources(${target} PRIVATE ${extra})\nendforeach()\n" + after
    paths = fixture(tmp_path, effect)
    contexts = snapshot(tmp_path, paths)
    with pytest.raises(QtCppError):
        read_cpp(paths[0], tmp_path, qt_test_context=contexts.for_path(paths[0]))


def test_req_qml022_ac03_defined_empty_list_and_literal_append_have_complete_source_payload(tmp_path):
    """Explicit quoted empty shadows a cache entry; a no-argument set is tested separately as unknown."""
    effect = 'set(extra "")\nlist(APPEND extra helper.cpp)\n' + REGISTRY
    effect += "foreach(target IN LISTS owned)\ntarget_sources(${target} PRIVATE ${extra})\nendforeach()\n"
    paths = fixture(tmp_path, effect)
    contexts = snapshot(tmp_path, paths)
    unit = read_cpp(paths[0], tmp_path, qt_test_context=contexts.for_path(paths[0]))
    assert len(unit.qt_test_macros) == 2
    verify_test_contexts(contexts, root=tmp_path)


@pytest.mark.parametrize("prefix", [
    "set(extra " + " ".join(f"other{i}.cpp" for i in range(129)) + ")\n",
    "\n".join(f"set(binding{i} other{i}.cpp)" for i in range(257)) + "\nset(extra helper.cpp)\n",
])
def test_req_qml022_ac03_domain_and_binding_exhaustion_retains_unknown_effect_veto(tmp_path, prefix):
    """Bounds produce unavailable context rather than partial finite lists that exclude the current TU."""
    effect = prefix + REGISTRY + "foreach(target IN LISTS owned)\ntarget_sources(${target} PRIVATE ${extra})\nendforeach()\n"
    paths = fixture(tmp_path, effect)
    contexts = snapshot(tmp_path, paths)
    with pytest.raises(QtCppError):
        read_cpp(paths[0], tmp_path, qt_test_context=contexts.for_path(paths[0]))


@pytest.mark.parametrize("value", ["../tests/check.cpp", "${extra}"])
def test_req_qml022_ac03_effect_uses_own_source_directory_and_no_cross_file_variable_bindings(tmp_path, value):
    """Alias paths still name the TU, and normal variables do not leak between supplied metadata sources."""
    paths = fixture(tmp_path, "set(extra helper.cpp)\n")
    other = tmp_path / "nested/effects.cmake"
    other.parent.mkdir()
    other.write_text(REGISTRY + "foreach(target IN LISTS owned)\ntarget_sources(${target} PRIVATE " + value + ")\nendforeach()\n")
    contexts = build_qt_test_contexts([p for p in paths if p.suffix in {".cpp", ".h"}], root=tmp_path,
                                     project_paths=[paths[2], other])
    with pytest.raises(QtCppError):
        read_cpp(paths[0], tmp_path, qt_test_context=contexts.for_path(paths[0]))


def test_req_qml022_ac03_source_defined_trusted_command_shadow_is_cohort_owned(tmp_path):
    """A separately admitted command definition invalidates a pure-command assumption without importing variables."""
    effect = "set(extra helper.cpp)\nmessage(STATUS ignored)\nforeach(target IN ITEMS Other)\n"
    effect += "target_sources(${target} PRIVATE ${extra})\nendforeach()\n"
    paths = fixture(tmp_path, effect)
    other = tmp_path / "tests/shadow.cmake"
    other.write_text("function(message)\nset(extra check.cpp PARENT_SCOPE)\nendfunction()\n")
    contexts = build_qt_test_contexts([p for p in paths if p.suffix in {".cpp", ".h"}], root=tmp_path,
                                     project_paths=[paths[2], other])
    with pytest.raises(QtCppError):
        read_cpp(paths[0], tmp_path, qt_test_context=contexts.for_path(paths[0]))
