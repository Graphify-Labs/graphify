"""INC-QML-79: inclusion guards are source admission, not feature branches."""
from __future__ import annotations

import pytest

from graphify.extractors.qt_cpp_facts import qt_metadata
from tests.qt_analysis_helpers import analysis
from tests.qt_metaobject_helpers import member_edges, member_sites, sources


@pytest.mark.parametrize("definition", ["#define BACKEND_HPP", "#define BACKEND_HPP 1"])
def test_whole_file_guard_preserves_actual_metaobject_and_qml_member_authority(tmp_path, definition):
    """A conventional matched guard cannot erase the class's own source Q_OBJECT."""
    files = sources(crlf=True)
    files["backend.hpp"] = "\ufeff#ifndef BACKEND_HPP\r\n" + definition + "\r\n" + files["backend.hpp"].removeprefix("\ufeff") + "#endif\r\n"
    result = analysis(tmp_path, files)
    assert len(member_edges(result)) == 3
    assert {node["metadata"]["qml"]["status"] for node in member_sites(result)} == {"resolved"}
    marker = next(qt_metadata(n) for n in result["nodes"] if qt_metadata(n).get("kind") == "metaobject")
    cls = next(qt_metadata(n) for n in result["nodes"] if qt_metadata(n).get("kind") == "class")
    assert marker["conditional"] is False and cls["api_declaration_conditional"] is False
    assert cls["metaobject_status"] == "resolved"
    span = marker["span"]
    assert files["backend.hpp"].encode()[span["start_byte"]:span["end_byte"]] == b"Q_OBJECT"


@pytest.mark.parametrize("before,after", [
    ("#ifdef BACKEND_HPP\n#define BACKEND_HPP\n", "#endif\n"),
    ("#ifndef BACKEND_HPP\n", "#endif\n"),
    ("#ifndef BACKEND_HPP\n#define OTHER_HPP\n", "#endif\n"),
    ("class Outside {};\n#ifndef BACKEND_HPP\n#define BACKEND_HPP\n", "#endif\n"),
    ("#ifndef BACKEND_HPP\n#define BACKEND_HPP\n", "#else\nclass Alternative {};\n#endif\n"),
    ("#if !defined(BACKEND_HPP)\n#define BACKEND_HPP\n", "#endif\n"),
    ("#ifndef BACKEND_HPP\n#define BACKEND_HPP\n#undef BACKEND_HPP\n", "#endif\n"),
    ("#ifndef BACKEND_HPP\n#define BACKEND_HPP\n#  undef BACKEND_HPP\n", "#endif\n"),
    ("#ifndef BACKEND_HPP\n#define BACKEND_HPP\n#define BACKEND_HPP 1\n", "#endif\n"),
    ("#ifndef BACKEND_HPP\n#define BACKEND_HPP\n#if FEATURE\n#undef BACKEND_HPP\n#endif\n", "#endif\n"),
])
def test_feature_or_unproved_guard_remains_uncertain(tmp_path, before, after):
    """Guard-shaped text cannot lend unconditional authority to a feature alternative."""
    files = sources()
    files["backend.hpp"] = before + files["backend.hpp"] + after
    result = analysis(tmp_path, files)
    assert not member_edges(result)
    assert all(node["metadata"]["qml"]["status"] != "resolved" for node in member_sites(result))


def test_nested_feature_condition_inside_valid_guard_stays_dynamic(tmp_path):
    """Only the outer inclusion idiom is transparent; real marker conditions remain unknown."""
    files = sources("#if FEATURE\nQ_OBJECT\n#endif")
    files["backend.hpp"] = "#ifndef BACKEND_HPP\n#define BACKEND_HPP\n" + files["backend.hpp"] + "#endif\n"
    result = analysis(tmp_path, files)
    assert not member_edges(result)
    cls = next(qt_metadata(n) for n in result["nodes"] if qt_metadata(n).get("kind") == "class")
    assert cls["api_declaration_conditional"] is False
    assert cls["metaobject_status"] == "dynamic"


def test_guarded_sdk_alias_and_engine_declaration_keep_exact_load_identity(tmp_path):
    """Alias, engine and observed call consumers share the same inclusion predicate."""
    files = sources()
    files["loader.hpp"] = ("#ifndef LOADER_HPP\n#define LOADER_HPP\n"
        "using Engine = QQmlApplicationEngine;\nvoid boot(){ Engine engine; "
        'engine.loadFromModule("Public.Probe", "Main"); }\n#endif\n')
    result = analysis(tmp_path, files)
    loads = [qt_metadata(n) for n in result["nodes"] if qt_metadata(n).get("kind") == "qml_load"]
    assert len(loads) == 1 and loads[0]["status"] == "resolved"
    assert loads[0]["receiver_identity_status"] == "resolved"


def test_incomplete_guard_cannot_supply_transparent_context():
    """A parser-inserted missing delimiter is not an actual closing source token."""
    from tree_sitter import Language, Parser
    import tree_sitter_cpp
    from graphify.extractors.cpp_include_guards import is_include_guard

    parser = Parser(Language(tree_sitter_cpp.language()))
    tree = parser.parse(b"#ifndef BACKEND_HPP\n#define BACKEND_HPP\nclass Backend {};\n")
    guard = tree.root_node.named_children[0]
    assert guard.type == "preproc_ifdef" and guard.children[-1].is_missing
    assert not is_include_guard(guard)


def test_other_definitions_and_literal_guard_text_do_not_invalidate_guard(tmp_path):
    """Only actual writes to this guard identity defeat its conventional ownership."""
    files = sources()
    files["backend.hpp"] = ("#ifndef BACKEND_HPP\n#define BACKEND_HPP\n#define FEATURE 1\n"
        'const char *description = "#undef BACKEND_HPP";\n' + files["backend.hpp"] + "#endif\n")
    assert len(member_edges(analysis(tmp_path, files))) == 3
