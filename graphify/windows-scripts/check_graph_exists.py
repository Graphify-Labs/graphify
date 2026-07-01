import sys
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

if not Path('graphify-out/graph.json').exists():
    print('ERROR: No graph found. Run /graphify <path> first to build the graph.')
    raise SystemExit(1)
