import sys
import json
from graphify.analyze import graph_diff
from graphify.build import build_from_json
from networkx.readwrite import json_graph
import networkx as nx
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

old_data = json.loads(Path('graphify-out/.graphify_old.json').read_text(encoding='utf-8')) if Path('graphify-out/.graphify_old.json').exists() else None
new_extract = json.loads(Path('graphify-out/.graphify_extract.json').read_text(encoding='utf-8'))
G_new = build_from_json(new_extract)

if old_data:
    G_old = json_graph.node_link_graph(old_data, edges='links')
    diff = graph_diff(G_old, G_new)
    print(diff['summary'])
    if diff['new_nodes']:
        print('New nodes:', ', '.join(n['label'] for n in diff['new_nodes'][:5]))
    if diff['new_edges']:
        print('New edges:', len(diff['new_edges']))
