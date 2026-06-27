import sys
import json
from graphify.cache import check_semantic_cache
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

input_path = sys.argv[1] if len(sys.argv) > 1 else '.'
detect = json.loads(Path('graphify-out/.graphify_detect.json').read_text(encoding='utf-8'))

# Only content files go to semantic extraction; code is handled by AST (Part A).
# Video is transcribed to document in Step 2.5 first.
all_files = [f for cat in ('document', 'paper', 'image') for f in detect['files'].get(cat, [])]

cached_nodes, cached_edges, cached_hyperedges, uncached = check_semantic_cache(all_files, root=Path(input_path))

# Always (re)write or DELETE the cache file so Part C never merges stale data (#1392).
if cached_nodes or cached_edges or cached_hyperedges:
    Path('graphify-out/.graphify_cached.json').write_text(
        json.dumps({'nodes': cached_nodes, 'edges': cached_edges, 'hyperedges': cached_hyperedges}, ensure_ascii=False),
        encoding='utf-8'
    )
else:
    Path('graphify-out/.graphify_cached.json').unlink(missing_ok=True)
Path('graphify-out/.graphify_uncached.txt').write_text('\n'.join(uncached), encoding='utf-8')
print(f'Cache: {len(all_files)-len(uncached)} files hit, {len(uncached)} files need extraction')
