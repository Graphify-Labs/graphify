"""Production extractor fixtures for scoped QML/JS expression acceptance."""

from graphify.extract import extract
from graphify.extractors.qml_facts import qml_metadata


def extraction(root, sources):
    paths = []
    for name, source in sources.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        paths.append(path)
    result = extract(paths, root=root, cache_root=root, parallel=False)
    assert not result.get("qml_failures"), result.get("qml_failures")
    return result


def nodes(result, kind, name=None, file=None):
    return [node for node in result["nodes"] if qml_metadata(node).get("kind") == kind
            and (name is None or qml_metadata(node).get("raw_name") == name)
            and (file is None or node["source_file"] == file)]


def single(result, kind, name=None, file=None):
    found = nodes(result, kind, name, file)
    assert len(found) == 1, (kind, name, file, found)
    return found[0]


def target_edges(result, site, context=None):
    return [edge for edge in result["edges"] if edge["source"] == site["id"]
            and edge["relation"] != "contains" and (context is None or edge.get("context") == context)]
