"""INC-QML-53: RC compilation prerequisites cannot lend runtime provider authority."""
from __future__ import annotations

from pathlib import Path

import pytest

from graphify.build import build_from_json
from graphify.extract import collect_files, extract
from graphify.extractors.qml_cmake import parse_cmake
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.qml_resolution_types import qml_metadata
from graphify.qt_project_index import QtProjectIndex
from tests.test_qt_cmake_mutation_updates import normalized


MODULE = "qt_add_qml_module(app URI Public.Tools VERSION 1.0 QML_FILES Main.qml SOURCES backend.h)\n"
RC_PREFIX = ('if(WIN32)\n'
             'set_source_files_properties(app.rc PROPERTIES '
             'INCLUDE_DIRECTORIES "${CMAKE_CURRENT_SOURCE_DIR}" '
             'OBJECT_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/icon_1.ico")\nendif()\n')
PROPERTY_SETS = [
    ("INCLUDE_DIRECTORIES",), ("OBJECT_DEPENDS",),
    ("INCLUDE_DIRECTORIES", "OBJECT_DEPENDS"), ("OBJECT_DEPENDS", "INCLUDE_DIRECTORIES"),
    ("INCLUDE_DIRECTORIES", "INCLUDE_DIRECTORIES"), ("OBJECT_DEPENDS", "OBJECT_DEPENDS"),
    ("OBJECT_DEPENDS", "INCLUDE_DIRECTORIES", "OBJECT_DEPENDS"),
]


@pytest.mark.parametrize("names", PROPERTY_SETS)
@pytest.mark.parametrize("computed", [False, True])
@pytest.mark.parametrize("scoped", [False, True])
@pytest.mark.parametrize("multiple", [False, True])
@pytest.mark.parametrize("bom,newline", [(b"", b"\n"), (b"\xef\xbb\xbf", b"\r\n")])
def test_req_qml009_ac04_rc_compile_properties_remain_opaque_with_original_spans(
    names, computed, scoped, multiple, bom, newline
):
    """Accept only proven RC source identities, never evaluate prerequisite values.

    Both property orders and repeated compile-only assignments are harmless:
    none establishes QML/C++ membership, resources, or a persistent property fact.
    """
    paths = '"rüň.rc" extra.RC' if multiple else '"rüň.rc"'
    value = '"${CMAKE_CURRENT_SOURCE_DIR}/icon.ico;${generated}"' if computed else '"icon.ico"'
    pairs = " ".join(f"{name} {value}" for name in names)
    command = f"set_source_files_properties({paths} PROPERTIES {pairs})\n"
    if scoped:
        command = "if(WIN32)\n" + command + "endif()\n"
    text = "# café ☃\n" + command + MODULE
    raw = bom + text.encode().replace(b"\n", newline)
    result = parse_cmake(raw)
    assert not result.get("error") and not result.get("qml_failures")
    assert not any(qml_metadata(node).get("kind") in {"qt_source_property", "qt_tooling_source", "resource_alias"}
                   for node in result["nodes"])
    sources = [node for node in result["nodes"] if qml_metadata(node).get("kind") == "qt_source"]
    assert [qml_metadata(node)["value"] for node in sources] == ["Main.qml", "backend.h"]
    for node in sources:
        metadata = qml_metadata(node)
        span = metadata["span"]
        assert raw[span["start_byte"]:span["end_byte"]].decode() == metadata["value"]
        for side in ("start", "end"):
            prefix = raw[:span[side + "_byte"]]
            assert span[side + "_row"] == prefix.count(b"\n")
            assert span[side + "_column"] == len(prefix) - prefix.rfind(b"\n") - 1


@pytest.mark.parametrize("command", [
    "set_source_files_properties(${rc} PROPERTIES OBJECT_DEPENDS icon.ico)",
    "set_source_files_properties(app.rc PROPERTIES ${property} icon.ico)",
    "set_source_files_properties(app.rc backend.h PROPERTIES OBJECT_DEPENDS icon.ico)",
    "set_source_files_properties(app.rc Main.qml PROPERTIES OBJECT_DEPENDS icon.ico)",
    "set_source_files_properties(app.rc resources.qrc PROPERTIES OBJECT_DEPENDS icon.ico)",
    'set_source_files_properties("backend.h;app.rc" PROPERTIES OBJECT_DEPENDS icon.ico)',
    "set_source_files_properties(backend.h;app.rc PROPERTIES OBJECT_DEPENDS icon.ico)",
    'set_source_files_properties("app.rc;backend.h" PROPERTIES OBJECT_DEPENDS icon.ico)',
    'set_source_files_properties(app.rc PROPERTIES "INCLUDE_DIRECTORIES;OBJECT_DEPENDS" icon.ico)',
    "set_source_files_properties(app.rc DIRECTORY other PROPERTIES OBJECT_DEPENDS icon.ico)",
    'set_source_files_properties(app.rc "DIRECTORY" other PROPERTIES OBJECT_DEPENDS icon.ico)',
    "set_source_files_properties(app.rc TARGET_DIRECTORY other PROPERTIES OBJECT_DEPENDS icon.ico)",
    'set_source_files_properties(app.rc "TARGET_DIRECTORY" other PROPERTIES OBJECT_DEPENDS icon.ico)',
    "set_source_files_properties(app.rc PROPERTIES OBJECT_DEPENDS)",
    "set_source_files_properties(app.rc PROPERTIES OBJECT_DEPENDS icon.ico OBJECT_DEPENDS)",
    "set_source_files_properties(app.rc PROPERTIES)",
    "set_source_files_properties(app.rc PROPERTIES OBJECT_DEPENDS icon.ico UNKNOWN_PROPERTY value)",
    "set_source_files_properties(app.rc PROPERTIES OBJECT_DEPENDS icon.ico QT_RESOURCE_ALIAS Wrong.qml)",
    "set_source_files_properties(app.rc PROPERTIES OBJECT_DEPENDS icon.ico QT_QML_SINGLETON_TYPE TRUE)",
    "set_source_files_properties(app.rc PROPERTIES OBJECT_DEPENDS icon.ico HEADER_FILE_ONLY TRUE)",
    "set_source_files_properties(backend.h PROPERTIES OBJECT_DEPENDS icon.ico)",
    "set_source_files_properties(resources.qrc PROPERTIES OBJECT_DEPENDS icon.ico)",
])
def test_req_qml012_ac01_rc_exemption_rejects_unproven_source_scope_or_property(command):
    """Computed values never authorize computed names, source identities or mixed kinds."""
    result = parse_cmake(command + "\n" + MODULE)
    assert result.get("qml_failures") and result["partial"]
    assert all(entry["code"] == "QML_PROJECT_UNSUPPORTED" and entry["severity"] == "error"
               for entry in result["diagnostics"])
    if "DIRECTORY" in command:
        assert result["diagnostics"][0]["reason"] == "unsupported_source_property_scope"
    assert not any(qml_metadata(node).get("kind") == "qt_source_property" for node in result["nodes"])


def test_req_qml009_ac04_rc_dependencies_and_authoring_targets_never_expand_accepted_corpus(tmp_path, monkeypatch):
    """Outside prerequisites/executables/native headers stay unread and unbound.

    A supported header-only native addition inside the root retains its actual
    provider. A separately listed outside header/executable cannot borrow that
    ownership or admit source simply through a CMake reference.
    """
    root, tools = tmp_path / "app", tmp_path / "tools"
    root.mkdir()
    tools.mkdir()
    outside = {tools / "foreign.h": b"class Foreign : public QObject { Q_OBJECT QML_ELEMENT };\n",
               tools / "author.cpp": b"int authoring_only() { return 1; }\n",
               tools / "icon.ico": b"opaque native icon"}
    for path, content in outside.items():
        path.write_bytes(content)
    sources = {
        "CMakeLists.txt": RC_PREFIX +
            "set_source_files_properties(backend.h ../tools/foreign.h PROPERTIES HEADER_FILE_ONLY TRUE)\n"
            "qt_add_qml_module(app URI Public.Tools VERSION 1.0 QML_FILES Main.qml)\n"
            "target_sources(app PRIVATE backend.h ../tools/foreign.h)\n"
            "qt_add_executable(authoring ../tools/author.cpp ../tools/foreign.h)\n",
        "Main.qml": "import Public.Tools 1.0\nService { property int shown: status }\n",
        "backend.h": "class Backend : public QObject { Q_OBJECT QML_NAMED_ELEMENT(Service) "
                     "Q_PROPERTY(int status READ status) public: int status() { return 1; } };\n",
    }
    sources["CMakeLists.txt"] = sources["CMakeLists.txt"].replace("/icon_1.ico", "/../tools/icon.ico")
    for name, text in sources.items():
        (root / name).write_bytes(text.encode())
    reads, original_open = [], Path.open
    def guarded_open(path, *args, **kwargs):
        if path.resolve() in outside:
            reads.append(path)
            raise AssertionError("Outside CMake prerequisite/source must not be read")
        return original_open(path, *args, **kwargs)
    with monkeypatch.context() as guard:
        guard.setattr(Path, "open", guarded_open)
        paths = collect_files(root, root=root)
        cold = extract(paths, root=root, cache_root=root / ".cache", parallel=False)
        warm = extract(paths, root=root, cache_root=root / ".cache", parallel=False)
    assert not reads
    for result in (cold, warm):
        assert not result.get("qml_failures") and not result.get("qt_failures") and not result.get("failed_sources")
        assert all(node["source_file"] in sources for node in result["nodes"] if node.get("source_file"))
        # The generic C++ owner deliberately retains an unresolved SDK base
        # reference. It is not a source declaration or a Qt native endpoint.
        external = [node for node in result["nodes"] if not node.get("source_file")]
        assert len(external) == 1 and external[0]["id"] == "qobject" and external[0]["label"] == "QObject"
        assert external[0]["source_file"] == external[0]["source_location"] == ""
        assert not qt_metadata(external[0]) and not qml_metadata(external[0])
        assert not external[0].get("_callable") and not external[0].get("_callable_class")
        assert not any(qt_metadata(node).get("class_name") == "Foreign" for node in result["nodes"])
        reads = [edge for edge in result["edges"] if edge.get("context") == "qml_binding_read"
                 and qt_metadata(edge).get("native_endpoint")]
        assert len(reads) == 1
        assert reads[0]["target"] != external[0]["id"]
        index = QtProjectIndex(result["nodes"], result["edges"], root=root)
        assert external[0]["id"] not in index.nodes
        backend = next(node for node in result["nodes"] if node.get("_callable_class") and node["label"] == "Backend")
        assert any(edge["source"] == backend["id"] and edge["target"] == external[0]["id"]
                   and edge.get("relation") == "inherits" for edge in result["edges"])
        assert index.module_context("backend.h").status == "resolved"
        assert index.module_context("../tools/foreign.h").target_id is None
        outside_sites = [qml_metadata(node) for node in result["nodes"]
                         if qml_metadata(node).get("kind") == "membership_resolution"
                         and qml_metadata(node).get("reason") == "membership_path_outside_root"]
        assert len(outside_sites) == 1 and not outside_sites[0]["target_id"]
    assert normalized(build_from_json(cold, root=root)) == normalized(build_from_json(warm, root=root))
    assert all(path.read_bytes() == content for path, content in outside.items())
    assert all((root / name).read_bytes() == text.encode() for name, text in sources.items())
