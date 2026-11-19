"""#5207: one reference id (ADR-0007, RFC-1, REQ-42) cited from several files
must end up as one concept node, without loosening the other merge guards."""
import pytest

from graphify.dedup import deduplicate_entities
from graphify.ids import normalize_id

FILES = ("src/a.ts", "src/b.ts", "docs/c.md")


def _nodes(labels, file_type="concept"):
    return [{"id": f"{normalize_id(f.rsplit('.', 1)[0])}_{normalize_id(l)}",
             "label": l, "file_type": file_type, "source_file": f}
            for f, l in zip(FILES, labels)]


def _count(labels, file_type="concept", **kw):
    out, _ = deduplicate_entities(_nodes(labels, file_type), [], communities={}, **kw)
    return len(out)


@pytest.mark.parametrize("labels", [
    ["ADR-0007"] * 3,
    ["ADR 7", "ADR-0007", "ADR-007"],
    ["RFC-1", "rfc 1", "RFC1"],
    ["REQ-42", "REQ 42", "req-0042"],
])
def test_reference_id_mentions_merge_to_one_node(labels):
    assert _count(labels) == 1


def test_edges_rewired_to_survivor():
    nodes = _nodes(["ADR 7", "ADR-0007", "ADR-007"])
    code = {"id": "src_a_f", "label": "f", "file_type": "code", "source_file": "src/a.ts"}
    edges = [{"source": "src_a_f", "target": n["id"], "relation": "cites"} for n in nodes]
    out, out_edges = deduplicate_entities(nodes + [code], edges, communities={})
    targets = {e["target"] for e in out_edges}
    assert len(targets) == 1
    assert targets <= {n["id"] for n in out}


def test_different_numbers_stay_apart():
    assert _count(["ADR-7", "ADR-8", "ADR-0007"]) == 2


def test_different_kinds_stay_apart():
    assert _count(["ADR-7", "RFC-7", "REQ-7"]) == 3


def test_unknown_prefix_keeps_entropy_gate():
    assert _count(["XYZ-0007"] * 3) == 3


@pytest.mark.parametrize("file_type", ["document", "rationale"])
def test_file_anchored_types_still_blocked(file_type):
    assert _count(["ADR-0007"] * 3, file_type) == 3


def test_label_with_extra_words_is_not_a_reference_id():
    assert _count(["ADR-0007 context", "ADR-0007", "ADR-0007 consequences"]) == 3


def test_incremental_protected_nodes_not_collapsed():
    nodes = _nodes(["ADR-0007"] * 3)
    protected = {nodes[0]["id"], nodes[1]["id"]}
    out, _ = deduplicate_entities(nodes, [], communities={}, protected_ids=protected)
    assert len(out) == 2
