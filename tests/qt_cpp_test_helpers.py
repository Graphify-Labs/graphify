"""Public synthetic Qt inputs using Graphify's actual canonical C++ extractor."""
from __future__ import annotations

import copy
from pathlib import Path

from graphify.extract import extract
from graphify.extractors.qt_cpp_exposure import enrich_qt_cpp
from graphify.extractors.qt_cpp_facts import qt_metadata

HEADER = '''class Backend : public QObject {
    Q_OBJECT
    QML_NAMED_ELEMENT(Backend)
    Q_PROPERTY(int value READ value WRITE setValue NOTIFY valueChanged)
public:
    int value() const;
    Q_INVOKABLE int next(int amount);
    void ordinary(int value);
signals:
    void valueChanged(int value);
public slots:
    void setValue(int value);
private:
    Q_INVOKABLE void hidden();
};
'''


def write(root, name, source):
    path = Path(root) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(source.encode())
    return path


def collect(root, files):
    paths = [write(root, name, source) for name, source in files.items()]
    accepted = extract(paths, root=Path(root), cache_root=Path(root) / ".probe-cache", parallel=False)
    # A production integration may already have run overlays. This independent
    # collector boundary borrows only existing generic declarations unchanged.
    nodes = [node for node in accepted["nodes"] if not qt_metadata(node)]
    ids = {node["id"] for node in nodes}
    edges = [edge for edge in accepted["edges"] if edge["source"] in ids and edge["target"] in ids]
    snapshot = copy.deepcopy((nodes, edges))
    results = [{"nodes": [], "edges": []} for _ in paths]
    enrich_qt_cpp(paths, results, root=root, accepted_nodes=nodes, accepted_edges=edges)
    assert (nodes, edges) == snapshot
    return {"nodes": nodes + [node for result in results for node in result["nodes"]],
            "edges": edges + [edge for result in results for edge in result["edges"]], "per_file": results}


def facts(result, kind, name=None):
    return [node for node in result["nodes"] if (md := qt_metadata(node)).get("kind") == kind
            and (name is None or md.get("raw_name") == name)]
