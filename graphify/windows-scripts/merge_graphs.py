import sys
import json
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# Load existing graph.json (NetworkX node-link format: nodes + links keys)
existing_data = json.loads(Path('graphify-out/graph.json').read_text(encoding='utf-8'))
existing_nodes = existing_data.get('nodes', [])
# NetworkX serialises edges as 'links'; also handle 'edges' for compatibility
existing_edges = existing_data.get('links', existing_data.get('edges', []))
existing_hyperedges = existing_data.get('hyperedges', [])

# Load new extraction (changed files only, produced by Step 3)
new_extraction = json.loads(Path('.graphify_extract.json').read_text(encoding='utf-8'))
new_nodes = new_extraction.get('nodes', [])
new_edges = new_extraction.get('edges', [])
new_hyperedges = new_extraction.get('hyperedges', [])

# Merge nodes: new/changed versions take priority; existing nodes fill the rest
new_ids = {n['id'] for n in new_nodes}
merged_nodes = list(new_nodes)
for n in existing_nodes:
    if n.get('id') not in new_ids:
        merged_nodes.append(n)

# Merge edges: new edges take priority over existing edges for the same pair
new_edge_pairs = {(e.get('source'), e.get('target')) for e in new_edges}
merged_edges = list(new_edges)
for e in existing_edges:
    if (e.get('source'), e.get('target')) not in new_edge_pairs:
        merged_edges.append(e)

# Merge hyperedges: new hyperedges take priority by id
new_he_ids = {h.get('id') for h in new_hyperedges}
merged_hyperedges = list(new_hyperedges) + [
    h for h in existing_hyperedges if h.get('id') not in new_he_ids
]

merged = {
    'nodes': merged_nodes,
    'edges': merged_edges,
    'hyperedges': merged_hyperedges,
    'input_tokens': new_extraction.get('input_tokens', 0),
    'output_tokens': new_extraction.get('output_tokens', 0),
}

Path('.graphify_extract.json').write_text(json.dumps(merged, indent=2), encoding='utf-8')
print(f'Merged: {len(merged_nodes)} nodes, {len(merged_edges)} edges ({len(existing_nodes)} existing + {len(new_nodes)} new/changed)')
