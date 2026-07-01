import sys
import json
from graphify.build import build_from_json
from graphify.export import to_graphml
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

extraction = json.loads(Path('graphify-out/.graphify_extract.json').read_text(encoding='utf-8'))
analysis   = json.loads(Path('graphify-out/.graphify_analysis.json').read_text(encoding='utf-8'))

G = build_from_json(extraction)
communities = {int(k): v for k, v in analysis['communities'].items()}

to_graphml(G, communities, 'graphify-out/graph.graphml')
print('graph.graphml written - open in Gephi, yEd, or any GraphML tool')
