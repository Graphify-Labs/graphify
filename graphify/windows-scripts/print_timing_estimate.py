import json, math
from pathlib import Path

detect = json.loads(Path('.graphify_detect.json').read_text(encoding='utf-8'))
files = detect.get('files', {})

non_code = sum(len(v) for k, v in files.items() if k != 'code')

if non_code == 0:
    print('Code-only corpus — no semantic extraction needed.')
    raise SystemExit(0)

agents = math.ceil(non_code / 22)
parallel_limit = 5
estimated_secs = math.ceil(agents / parallel_limit) * 45

print(f'Semantic extraction: ~{non_code} files -> {agents} agents, estimated ~{estimated_secs}s')
