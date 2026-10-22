"""Accepted production extraction boundary for Qt source overlay regressions."""
from graphify.extract import extract
from graphify.extractors.qt_cpp_facts import qt_metadata


def analysis(root, sources):
    paths = []
    for name, source in sources.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8", newline="")
        paths.append(path)
    result = extract(paths, root=root, cache_root=root, parallel=False)
    assert not result.get("qml_failures"), result.get("qml_failures")
    return result


def sites(result, kind, operation=None):
    return [node for node in result["nodes"] if qt_metadata(node).get("kind") == kind
            and (operation is None or qt_metadata(node).get("operation") == operation)]
