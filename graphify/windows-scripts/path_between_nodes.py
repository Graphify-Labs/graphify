import sys, json
import networkx as nx
from networkx.readwrite import json_graph
from pathlib import Path

a_term = sys.argv[1] if len(sys.argv) > 1 else ''
b_term = sys.argv[2] if len(sys.argv) > 2 else ''

data = json.loads(Path('graphify-out/graph.json').read_text())
G = json_graph.node_link_graph(data, edges='links')

def find_node(term):
    term = term.lower()
    scored = sorted(
        [(sum(1 for w in term.split() if w in G.nodes[n].get('label', '').lower()), n)
         for n in G.nodes()],
        reverse=True
    )
    return scored[0][1] if scored and scored[0][0] > 0 else None

src = find_node(a_term)
tgt = find_node(b_term)

if not src or not tgt:
    print(f'Could not find nodes matching: {a_term!r} or {b_term!r}')
    sys.exit(0)

try:
    path = nx.shortest_path(G, src, tgt)
    print(f'Shortest path ({len(path)-1} hops):')
    for i, nid in enumerate(path):
        label = G.nodes[nid].get('label', nid)
        if i < len(path) - 1:
            edge = G.edges[nid, path[i+1]]
            rel = edge.get('relation', '')
            conf = edge.get('confidence', '')
            print(f'  {label} --{rel}--> [{conf}]')
        else:
            print(f'  {label}')
except nx.NetworkXNoPath:
    print(f'No path found between {a_term!r} and {b_term!r}')
except nx.NodeNotFound as e:
    print(f'Node not found: {e}')
