import sys, json
from pathlib import Path
from graphify.diagnostics import diagnose_extraction, format_diagnostic_report
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

input_path = sys.argv[1] if len(sys.argv) > 1 else '.'
directed = sys.argv[2].lower() == 'true' if len(sys.argv) > 2 else False

extraction = json.loads(Path('graphify-out/.graphify_extract.json').read_text(encoding='utf-8'))
summary = diagnose_extraction(extraction, directed=directed, root=input_path)
print(format_diagnostic_report(summary))
flags = [f'{summary[k]} {label}' for k, label in (
    ('dangling_endpoint_edges', 'dangling-endpoint edges'),
    ('missing_endpoint_edges', 'missing-endpoint edges'),
    ('self_loop_edges', 'self-loop edges'),
    ('directed_same_endpoint_collapsed_edges', 'collapsed (directed) edges'),
    ('undirected_same_endpoint_collapsed_edges', 'collapsed (undirected) edges'),
) if summary.get(k, 0)]
if flags:
    print('GRAPH HEALTH WARNING: ' + '; '.join(flags) + ' - graph may be incomplete/corrupt.')
else:
    print('Graph health: OK (no dangling/missing/collapsed edges).')
