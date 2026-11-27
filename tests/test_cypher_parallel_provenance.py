import networkx as nx

from graphify.export import to_cypher


def test_cypher_exports_distinct_call_sites_with_provenance(tmp_path):
    graph = nx.MultiGraph()
    graph.add_node("caller", label="Caller", source_file="src/a.py", source_location="L10")
    graph.add_node("callee", label="Callee", source_file="src/b.py", source_location="L20")
    for location in ("L42", "L77", "L77"):
        graph.add_edge("callee", "caller", _src="caller", _tgt="callee",
                       relation="calls", confidence="EXTRACTED",
                       source_file="src/a.py", source_location=location, context="call")
    output = tmp_path / "graph.cypher"
    to_cypher(graph, str(output))
    before = output.read_text(encoding="utf-8")
    statements = [line for line in before.splitlines() if line.startswith("MATCH (a")]
    assert len(statements) == 3
    assert len({line.split(" SET ")[0] for line in statements}) == 3
    assert all("MATCH (a {id: 'caller'}), (b {id: 'callee'})" in line for line in statements)
    assert all("source_file = 'src/a.py'" in line and "context = 'call'" in line
               for line in statements)
    assert "'L42'" in statements[0]
    assert all("'L77'" in line for line in statements[1:])
    assert "n.source_file = 'src/b.py'" in before
    assert "n.source_location = 'L20'" in before
    to_cypher(graph, str(output))
    assert output.read_text(encoding="utf-8") == before
