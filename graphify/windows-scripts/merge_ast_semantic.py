import sys
import json
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

ast = json.loads(Path('.graphify_ast.json').read_text(encoding='utf-8'))
sem = json.loads(Path('.graphify_semantic.json').read_text(encoding='utf-8'))

# Semantic nodes take priority: richer labels, rationale, cross-file context.
# AST source_location is backfilled onto semantic nodes that lack it so precise
# line numbers are never lost.
ast_by_id = {n['id']: n for n in ast['nodes']}
seen: set = set()
merged_nodes = []
for n in sem['nodes']:
    seen.add(n['id'])
    ast_node = ast_by_id.get(n['id'])
    if ast_node and not n.get('source_location') and ast_node.get('source_location'):
        n = dict(n, source_location=ast_node['source_location'])
    merged_nodes.append(n)
for n in ast['nodes']:
    if n['id'] not in seen:
        merged_nodes.append(n)
        seen.add(n['id'])

merged_edges = ast['edges'] + sem['edges']
merged_hyperedges = sem.get('hyperedges', [])
merged = {
    'nodes': merged_nodes,
    'edges': merged_edges,
    'hyperedges': merged_hyperedges,
    'input_tokens': sem.get('input_tokens', 0),
    'output_tokens': sem.get('output_tokens', 0),
}
Path('.graphify_extract.json').write_text(json.dumps(merged, indent=2), encoding='utf-8')
total = len(merged_nodes)
edges = len(merged_edges)
print(f'Merged: {total} nodes, {edges} edges ({len(ast["nodes"])} AST + {len(sem["nodes"])} semantic)')
