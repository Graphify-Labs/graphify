import json
from graphify.build import build_from_json
from graphify.export import to_json
from networkx.readwrite import json_graph
import networkx as nx
from pathlib import Path

existing_data = json.loads(Path('graphify-out/graph.json').read_text())
G_existing = json_graph.node_link_graph(existing_data, edges='links')

new_extraction = json.loads(Path('.graphify_extract.json').read_text())
G_new = build_from_json(new_extraction)

G_existing.update(G_new)
print(f'Merged: {G_existing.number_of_nodes()} nodes, {G_existing.number_of_edges()} edges')
