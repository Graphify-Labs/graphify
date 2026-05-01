import sys
import json, sys
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

out_dir = Path('graphify-out')
chunk_files = sorted(out_dir.glob('.graphify_chunk_*.json'))

if not chunk_files:
    print('ERROR: No chunk files found in graphify-out/. Subagents may not have written results.')
    print('Re-run and ensure subagent_type="general-purpose" is used.')
    sys.exit(1)

all_nodes, all_edges, all_hyperedges = [], [], []
total_input = total_output = 0
failed = []

for cf in chunk_files:
    try:
        data = json.loads(cf.read_text(encoding='utf-8'))
        if 'nodes' not in data or 'edges' not in data:
            raise ValueError('missing nodes or edges keys')
        all_nodes.extend(data['nodes'])
        all_edges.extend(data['edges'])
        all_hyperedges.extend(data.get('hyperedges', []))
        total_input += data.get('input_tokens', 0)
        total_output += data.get('output_tokens', 0)
    except Exception as e:
        print(f'WARNING: {cf.name} failed validation: {e}')
        failed.append(cf.name)

total = len(chunk_files)
if len(failed) > total / 2:
    print(f'ERROR: {len(failed)}/{total} chunks failed. Re-run and ensure subagent_type="general-purpose".')
    sys.exit(1)

if failed:
    print(f'WARNING: {len(failed)} chunk(s) invalid: {", ".join(failed)}')

seen: set = set()
deduped_nodes = []
for n in all_nodes:
    if n['id'] not in seen:
        seen.add(n['id'])
        deduped_nodes.append(n)

Path('.graphify_semantic_new.json').write_text(json.dumps({
    'nodes': deduped_nodes,
    'edges': all_edges,
    'hyperedges': all_hyperedges,
    'input_tokens': total_input,
    'output_tokens': total_output,
}, indent=2), encoding='utf-8')
print(f'Collected {total - len(failed)}/{total} chunks: {len(deduped_nodes)} nodes, {len(all_edges)} edges')

for cf in chunk_files:
    cf.unlink(missing_ok=True)
