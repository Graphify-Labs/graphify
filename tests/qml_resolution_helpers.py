"""Hand-authored public module fixtures through the actual source extractors."""

from graphify.extractors.qml import extract_qml
from graphify.extractors.qml_facts import qml_metadata
from graphify.extractors.qml_metadata import extract_qmldir
from graphify.qml_resolution import build_qml_index


def corpus(root, sources):
    """Only supplied sources enter the index; its resolver cannot widen discovery."""
    per_file = {}
    for relative, text in sources.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        if path.suffix in {".js", ".mjs"}:
            from graphify.extract import extract_js
            result = extract_js(path)
        else:
            result = (extract_qmldir(path, root=root) if path.name == "qmldir" else
                      extract_qml(path, root=root))
        assert not result.get("error"), result
        per_file[path] = result
    nodes = [node for result in per_file.values() for node in result["nodes"]]
    edges = [edge for result in per_file.values() for edge in result["edges"]]
    return per_file, nodes, edges


def named(nodes, file, kind, name=None):
    selected = [node for node in nodes if node["source_file"] == file and
                qml_metadata(node).get("kind") == kind and
                (name is None or qml_metadata(node).get("raw_name") == name)]
    assert len(selected) == 1, (file, kind, name, selected)
    return selected[0]


def index_for(root, sources, *, import_roots=None):
    per_file, nodes, edges = corpus(root, sources)
    return build_qml_index(nodes, edges, root=root, import_roots=import_roots), per_file, nodes, edges


def component_key(nodes, file="Main.qml", name=None):
    return qml_metadata(named(nodes, file, "component", name)).get("component_key")


def module(uri, filename="Button.qml", *, extra=""):
    return {f'{uri.replace(".", "/")}/qmldir': f"module {uri}\nButton 1.0 {filename}\n{extra}",
            f'{uri.replace(".", "/")}/{filename}': "QtObject { property int value: 1 }"}
