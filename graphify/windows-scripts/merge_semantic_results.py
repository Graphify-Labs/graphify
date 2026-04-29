import json
from pathlib import Path

cached = json.loads(Path('.graphify_cached.json').read_text()) if Path('.graphify_cached.json').exists() else {'nodes': [], 'edges': [], 'hyperedges': []}
new = json.loads(Path('.graphify_semantic_new.json').read_text()) if Path('.graphify_semantic_new.json').exists() else {'nodes': [], 'edges': [], 'hyperedges': []}

all_nodes = cached['nodes'] + new.get('nodes', [])
all_edges = cached['edges'] + new.get('edges', [])
all_hyperedges = cached.get('hyperedges', []) + new.get('hyperedges', [])
seen = set()
deduped = []
for n in all_nodes:
    if n['id'] not in seen:
        seen.add(n['id'])
        deduped.append(n)

merged = {
    'nodes': deduped,
    'edges': all_edges,
    'hyperedges': all_hyperedges,
    'input_tokens': new.get('input_tokens', 0),
    'output_tokens': new.get('output_tokens', 0),
}
Path('.graphify_semantic.json').write_text(json.dumps(merged, indent=2))
print(f'Extraction complete - {len(deduped)} nodes, {len(all_edges)} edges ({len(cached["nodes"])} from cache, {len(new.get("nodes", []))} new)')
