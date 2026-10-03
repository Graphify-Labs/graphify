"""QML-016-AC04 canonical C++ header/implementation ownership in affected results."""
import pytest

from graphify.affected import affected_nodes
from graphify.build import build_from_json
from graphify.extractors.qt_cpp_facts import qt_metadata, update_qt
from tests.qt_analysis_helpers import analysis, sites

HEADER = '''class Emitter: public QObject { Q_OBJECT
public: void wire(Emitter *other); void accept();
signals: void changed();
};'''
SOURCE = '''void Emitter::wire(Emitter *other) {
 QObject::connect(other, &Emitter::changed, this, &Emitter::accept);
}
void Emitter::accept() {}
'''


def fixture(tmp_path):
    result = analysis(tmp_path, {"emitter.h": HEADER, "emitter.cpp": SOURCE})
    graph = build_from_json(result, root=tmp_path, directed=True)
    site = sites(result, "connect")[0]
    metadata = qt_metadata(site)
    assert metadata["status"] == "resolved"
    owner = graph.nodes[metadata["owner_id"]]
    assert owner["source_file"] == "emitter.h" and owner["definition_file"] == "emitter.cpp"
    return graph, site, metadata


def test_qml016_ac04_signal_change_reports_canonical_out_of_line_function_owner(tmp_path):
    """A real implementation site promotes its canonical header-owned method."""
    graph, site, metadata = fixture(tmp_path)
    hits = affected_nodes(graph, metadata["signal_target_id"], relations=["references"], depth=2)
    by_id = {hit.node_id: hit for hit in hits}
    assert site["id"] in by_id and metadata["owner_id"] in by_id
    assert by_id[metadata["owner_id"]].via_file == "emitter.cpp"
    assert by_id[metadata["owner_id"]].via_location == site["source_location"]
    assert metadata["owner_id"] not in {hit.node_id for hit in affected_nodes(graph, metadata["signal_target_id"], relations=["calls"], depth=2)}


@pytest.mark.parametrize("invalid", ["definition", "callable", "owner", "span"])
def test_qml016_ac04_foreign_or_unproven_definition_cannot_promote_owner(tmp_path, invalid):
    """Borrowed source fields alone cannot authorize unrelated function ownership."""
    graph, site, metadata = fixture(tmp_path)
    owner = graph.nodes[metadata["owner_id"]]
    if invalid == "definition":
        owner["definition_file"] = "other.cpp"
    elif invalid == "callable":
        owner.pop("_callable")
    elif invalid == "owner":
        update_qt(graph.nodes[site["id"]], owner_id="foreign_owner")
    else:
        update_qt(graph.nodes[site["id"]], span={**metadata["span"], "end_byte": metadata["span"]["end_byte"] + 1})
    hits = {hit.node_id for hit in affected_nodes(graph, metadata["signal_target_id"], relations=["references"], depth=2)}
    assert site["id"] in hits and metadata["owner_id"] not in hits
