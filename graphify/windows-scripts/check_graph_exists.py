from pathlib import Path

if not Path('graphify-out/graph.json').exists():
    print('ERROR: No graph found. Run /graphify <path> first to build the graph.')
    raise SystemExit(1)
