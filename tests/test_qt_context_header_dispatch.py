"""INC-QML-93: context-only headers preserve actual language dispatch and overlay admission."""
from __future__ import annotations

import importlib

import pytest

from graphify.extract import extract
from graphify.rcfile import set_language_overrides
from tests.test_qt_build_include_context import project


@pytest.fixture(autouse=True)
def clear_overrides():
    """Each real override declaration is scoped to its isolated fixture root."""
    set_language_overrides(None)
    yield
    set_language_overrides(None)


@pytest.mark.parametrize("language,header,admitted", [
    ("c", "struct Api{};\n", True),
    ("cpp", "class Api{};\n", True),
    ("objc", "@interface Api\n@end\n", False),
    ("python", "def api(): return 1\n", False),
])
def test_req_qml022_ac03_context_header_selection_preserves_actual_producers(tmp_path, monkeypatch, language, header, admitted):
    """Observe the real snapshot boundary, then run its actual parser/context implementation."""
    paths = project(tmp_path, header=header)
    if language == "python":
        (tmp_path / ".graphifyrc").write_text("language.h=python\n")
    facade = importlib.import_module("graphify.extract")
    context = importlib.import_module("graphify.extractors.qt_cpp_test_context")
    actual = context.build_qt_test_contexts
    observed = []

    def snapshot(native_paths, *, root, project_paths=()):
        native_paths, project_paths = tuple(native_paths), tuple(project_paths)
        observed.append((native_paths, project_paths))
        return actual(native_paths, root=root, project_paths=project_paths)

    monkeypatch.setattr(context, "build_qt_test_contexts", snapshot)
    result = extract(list(paths), root=tmp_path, cache_root=tmp_path, parallel=False)
    expected = {"c": facade.extract_c, "cpp": facade.extract_cpp,
                "objc": facade.extract_objc, "python": facade.extract_python}[language]
    assert facade._get_extractor(paths[1]) is expected
    assert len(observed) == 1 and (paths[1] in observed[0][0]) is admitted
    assert observed[0][1] == (paths[2],)
    members = [node for node in result["nodes"] if node.get("source_file") == "src/api.h"]
    assert any(node.get("metadata", {}).get("cpp_class") for node in members) is (language == "cpp")
    if admitted:
        assert not result.get("qml_failures")
    else:
        assert {"code": "QT_CPP_SYNTAX", "source_file": "tests/check.cpp"} in result["qml_failures"]
