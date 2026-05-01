import sys
import json
from graphify.build import build_from_json
from graphify.wiki import to_wiki
from graphify.analyze import god_nodes
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

extraction = json.loads(Path('.graphify_extract.json').read_text(encoding='utf-8'))
analysis   = json.loads(Path('.graphify_analysis.json').read_text(encoding='utf-8'))
labels_raw = json.loads(Path('.graphify_labels.json').read_text(encoding='utf-8')) if Path('.graphify_labels.json').exists() else {}

G = build_from_json(extraction)
communities = {int(k): v for k, v in analysis['communities'].items()}
cohesion = {int(k): v for k, v in analysis['cohesion'].items()}
labels = {int(k): v for k, v in labels_raw.items()}
gods = god_nodes(G)

n = to_wiki(G, communities, 'graphify-out/wiki', community_labels=labels or None, cohesion=cohesion, god_nodes_data=gods)
print(f'Wiki: {n} articles written to graphify-out/wiki/')
print('  graphify-out/wiki/index.md  ->  agent entry point')
