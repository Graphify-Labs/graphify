import sys
import json
from graphify.build import build_from_json
from graphify.export import to_cypher
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

G = build_from_json(json.loads(Path('graphify-out/.graphify_extract.json').read_text(encoding='utf-8')))
to_cypher(G, 'graphify-out/cypher.txt')
print('cypher.txt written - import with: cypher-shell < graphify-out/cypher.txt')
