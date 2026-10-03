"""QML-011: accepted-input refresh, provider removal and cache/config invariants."""
import pytest

from graphify.qt_incremental import (
    is_qt_metadata, plan_qt_refresh, qt_analysis_fingerprint, qt_syntax_cache_bypass,
)


@pytest.mark.parametrize("path", ["qmldir", "nested/CMakeLists.txt", "module.cmake",
                                 "tools.pro", "settings.pri", "types.qmltypes", "ui.QRC"])
def test_every_declared_qt_metadata_form_invalidates_unchanged_consumers(path):
    plan = plan_qt_refresh(["Main.qml", "backend.h", path], [path])
    assert plan.required
    assert plan.accepted_inputs == tuple(sorted(["Main.qml", "backend.h", path]))
    assert qt_syntax_cache_bypass(path)
    assert is_qt_metadata(path)


@pytest.mark.parametrize("path", ["qmldir.txt", "QMLDIR", "cmakelists.txt", "script.py", "notes.txt"])
def test_unrelated_files_do_not_become_qt_metadata_or_force_scope_rebuilds(path):
    assert not is_qt_metadata(path)
    assert not qt_syntax_cache_bypass(path)
    assert not plan_qt_refresh(["Main.qml", path], [path]).required


@pytest.mark.parametrize("path", ["backend.cpp", "backend.h", "backend.hpp", "backend.cxx"])
def test_native_provider_only_updates_include_unchanged_qml_and_cpp_consumers(path):
    plan = plan_qt_refresh(["Main.qml", "consumer.cpp", path], [path])
    assert plan.required
    assert "Main.qml" in plan.accepted_inputs
    assert "qt_native_provider_changed" in plan.reasons
    assert not qt_syntax_cache_bypass(path)
    assert qt_syntax_cache_bypass(path, native=True)


def test_last_provider_deletion_and_rename_never_read_removed_or_ignored_sources():
    prior = ["Main.qml", "backend.h", "resources.qrc"]
    plan = plan_qt_refresh(["consumer.cpp", "new.h"], ["backend.h", "Main.qml", "resources.qrc", "new.h"],
                           prior_paths=prior)
    assert plan.required
    assert plan.accepted_inputs == ("consumer.cpp", "new.h")
    assert "backend.h" not in plan.accepted_inputs
    assert "resources.qrc" not in plan.accepted_inputs
    assert plan_qt_refresh(["consumer.py"], ["last_native.h"]).required


def test_ignore_and_analysis_config_changes_refresh_only_new_accepted_corpus():
    plan = plan_qt_refresh(["Main.qml"], [".graphifyignore"], prior_paths=["backend.h", "Main.qml"])
    assert plan.required and plan.accepted_inputs == ("Main.qml",)
    assert "qt_corpus_policy_changed" in plan.reasons
    assert plan_qt_refresh(["Main.qml"], [], configuration_changed=True).required
    assert not plan_qt_refresh(["app.py"], [], configuration_changed=True).required


def test_new_native_qt_events_are_not_hidden_by_an_ordinary_cpp_context():
    plan = plan_qt_refresh(["ordinary.cpp", "consumer.cpp"], ["ordinary.cpp"])
    assert plan.required
    assert plan.accepted_inputs == ("consumer.cpp", "ordinary.cpp")


def test_shared_js_refreshes_qt_consumers_only_when_a_qt_context_exists():
    assert plan_qt_refresh(["Main.qml", "utils.mjs"], ["utils.mjs"]).required
    assert not plan_qt_refresh(["app.js"], ["app.js"]).required
    assert plan_qt_refresh(["utils.js"], ["utils.js"], qt_facts_present=True).required


def test_configuration_fingerprint_covers_parser_contract_import_order_and_ignores():
    base = {"parser_version": "qmljs-test-1", "fact_version": 1,
            "import_roots": ["imports", "."], "ignore_patterns": ["build/", "generated/"]}
    original = qt_analysis_fingerprint(**base)
    assert qt_analysis_fingerprint(**base) == original
    for changed in ({"parser_version": "qmljs-test-2"}, {"fact_version": 2},
                    {"import_roots": [".", "imports"]}, {"ignore_patterns": ["build/"]},
                    {"ignore_patterns": list(reversed(base["ignore_patterns"]))},
                    {"profile": "qt6-reviewed-next"}):
        assert qt_analysis_fingerprint(**{**base, **changed}) != original
    with pytest.raises(ValueError, match="QT_CONFIG"):
        qt_analysis_fingerprint(parser_version="test", fact_version=0)
