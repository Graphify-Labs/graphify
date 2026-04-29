import sys, json
from graphify.build import build_from_json
from graphify.cluster import cluster
from graphify.export import push_to_neo4j
from pathlib import Path

uri      = sys.argv[1] if len(sys.argv) > 1 else 'bolt://localhost:7687'
user     = sys.argv[2] if len(sys.argv) > 2 else 'neo4j'
password = sys.argv[3] if len(sys.argv) > 3 else ''

extraction = json.loads(Path('.graphify_extract.json').read_text())
analysis   = json.loads(Path('.graphify_analysis.json').read_text())
G = build_from_json(extraction)
communities = {int(k): v for k, v in analysis['communities'].items()}

result = push_to_neo4j(G, uri=uri, user=user, password=password, communities=communities)
print(f'Pushed to Neo4j: {result["nodes"]} nodes, {result["edges"]} edges')
