import json
from graphify.build import build_from_json
from graphify.export import to_cypher
from pathlib import Path

G = build_from_json(json.loads(Path('.graphify_extract.json').read_text(encoding='utf-8')))
to_cypher(G, 'graphify-out/cypher.txt')
print('cypher.txt written - import with: cypher-shell < graphify-out/cypher.txt')
