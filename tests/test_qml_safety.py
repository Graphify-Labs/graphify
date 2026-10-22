"""QML-001/002/011 integrity gates inspect source ownership, not graph counts."""
import pytest

from graphify.qml_safety import (
    QmlSafetyError, is_qml_path, qml_refresh_required, require_complete_qml,
    require_qml_watch_root,
)


@pytest.mark.parametrize("name", ["Main.qml", "MAIN.QML", "types.qmltypes", "qmldir"])
def test_qml_source_metadata_recognition(name):
    assert is_qml_path(name)


@pytest.mark.parametrize("name", ["qmldir.txt", "QMLDIR", "app.py", "qml"])
def test_qml_named_metadata_does_not_admit_unrelated_files(name):
    assert not is_qml_path(name)


@pytest.mark.parametrize("marker", ["error", "partial", "parse_errors", "failed_sources", "qml_failures"])
def test_guard_rejects_unsafe_qml_with_surviving_nodes(tmp_path, marker):
    """Recovered nodes cannot make a failed component scope authoritative."""
    path = tmp_path / "Main.qml"
    result = {"nodes": [{"id": "kept", "source_file": "Main.qml"}], "edges": []}
    value = True
    if marker == "failed_sources":
        value = [str(path)]
    elif marker == "qml_failures":
        value = [{"code": "QML_PARSE_PARTIAL", "source_file": str(path)}]
    result[marker] = value
    with pytest.raises(QmlSafetyError, match="QML_GRAPH_PRESERVED"):
        require_complete_qml(result, [path], operation="extract", root=tmp_path)


def test_omitted_qml_contribution_cannot_be_reported_complete(tmp_path):
    with pytest.raises(QmlSafetyError, match="Main.qml"):
        require_complete_qml({"nodes": []}, [tmp_path / "Main.qml"], operation="extract", root=tmp_path)


def test_clean_qml_and_unrelated_failure_keep_separate_contracts(tmp_path):
    """An existing Python error is outside the QML publication policy."""
    result = {"nodes": [{"source_file": "Main.qml"}], "failed_sources": ["bad.py"]}
    require_complete_qml(result, [tmp_path / "Main.qml"], operation="extract", root=tmp_path)
    require_complete_qml({"nodes": [], "error": "old behavior"}, ["bad.py"], operation="extract")


def test_diagnostic_escapes_delimiters_and_does_not_print_foreign_root(tmp_path):
    """Failure evidence contains a bounded escaped filename, never raw source."""
    source = tmp_path / 'hidden' / 'bad\n".qml'
    with pytest.raises(QmlSafetyError) as info:
        require_complete_qml({"nodes": [], "failed_sources": [str(source)]}, [source], operation="extract")
    message = str(info.value)
    assert str(tmp_path) not in message
    assert '\\n' in message and '\\"' in message
    assert "\n" not in message


@pytest.mark.parametrize("changed", [["Main.qml"], ["qmldir"], ["types.qmltypes"], ["helpers.js"]])
def test_qml_dependencies_widen_to_conservative_refresh(changed):
    assert qml_refresh_required(["Main.qml", "keep.py"], changed)


def test_non_qml_and_deleted_final_component_refresh_contracts():
    assert not qml_refresh_required(["keep.py"], ["helpers.js"])
    assert not qml_refresh_required(["Main.qml"], ["keep.py"])
    assert qml_refresh_required(["keep.py"], ["deleted.qml"])


def test_qml_subfolder_watch_rejects_before_rebasing(tmp_path):
    with pytest.raises(QmlSafetyError, match="QML_ROOT_MISMATCH"):
        require_qml_watch_root(["Main.qml"], project_root=tmp_path, watch_root=tmp_path / "ui")
    require_qml_watch_root(["keep.py"], project_root=tmp_path, watch_root=tmp_path / "src")
    require_qml_watch_root(["Main.qml"], project_root=tmp_path, watch_root=tmp_path)
