import sys, json
from graphify.build import build_from_json
from graphify.cluster import score_all
from graphify.analyze import suggest_questions
from graphify.report import generate
from pathlib import Path

input_path = sys.argv[1] if len(sys.argv) > 1 else '.'
# Read labels from file to avoid shell command-line length limits.
# Falls back to inline sys.argv[2] for backward compatibility.
_labels_file = Path('.graphify_labels_input.json')
if _labels_file.exists():
    labels = {int(k): v for k, v in json.loads(_labels_file.read_text()).items()}
elif len(sys.argv) > 2:
    labels = {int(k): v for k, v in json.loads(sys.argv[2]).items()}
else:
    labels = {}

extraction = json.loads(Path('.graphify_extract.json').read_text())
detection  = json.loads(Path('.graphify_detect.json').read_text())
analysis   = json.loads(Path('.graphify_analysis.json').read_text())

G = build_from_json(extraction)
communities = {int(k): v for k, v in analysis['communities'].items()}
cohesion = {int(k): v for k, v in analysis['cohesion'].items()}
tokens = {'input': extraction.get('input_tokens', 0), 'output': extraction.get('output_tokens', 0)}

questions = suggest_questions(G, communities, labels)

report = generate(G, communities, cohesion, labels, analysis['gods'], analysis['surprises'], detection, tokens, input_path, suggested_questions=questions)
Path('graphify-out/GRAPH_REPORT.md').write_text(report)
Path('.graphify_labels.json').write_text(json.dumps({str(k): v for k, v in labels.items()}))
print('Report updated with community labels')
