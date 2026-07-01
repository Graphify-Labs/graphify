import sys
import json
from graphify.build import build_from_json
from graphify.export import to_html
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

extraction = json.loads(Path('graphify-out/.graphify_extract.json').read_text(encoding='utf-8'))
analysis   = json.loads(Path('graphify-out/.graphify_analysis.json').read_text(encoding='utf-8'))
labels_raw = json.loads(Path('graphify-out/.graphify_labels.json').read_text(encoding='utf-8')) if Path('graphify-out/.graphify_labels.json').exists() else {}

G = build_from_json(extraction)
communities = {int(k): v for k, v in analysis['communities'].items()}
labels = {int(k): v for k, v in labels_raw.items()}

if G.number_of_nodes() > 5000:
    print(f'Graph has {G.number_of_nodes()} nodes - too large for HTML viz. Use Obsidian vault instead.')
else:
    to_html(G, communities, 'graphify-out/graph.html', community_labels=labels or None)
    print('graph.html written - open in any browser, no server needed')
