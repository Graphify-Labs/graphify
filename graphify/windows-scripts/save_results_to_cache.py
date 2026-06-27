import sys
import json
from graphify.cache import save_semantic_cache
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

input_path = sys.argv[1] if len(sys.argv) > 1 else '.'
new = json.loads(Path('graphify-out/.graphify_semantic_new.json').read_text(encoding='utf-8')) if Path('graphify-out/.graphify_semantic_new.json').exists() else {'nodes':[],'edges':[],'hyperedges':[]}
saved = save_semantic_cache(new.get('nodes', []), new.get('edges', []), new.get('hyperedges', []), root=Path(input_path))
print(f'Cached {saved} files')
