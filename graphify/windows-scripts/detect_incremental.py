import sys, json
from graphify.detect import detect_incremental, save_manifest
from pathlib import Path

result = detect_incremental(Path(sys.argv[1]))
new_total = result.get('new_total', 0)
print(json.dumps(result, indent=2))
Path('.graphify_incremental.json').write_text(json.dumps(result), encoding='utf-8')
if new_total == 0:
    print('No files changed since last run. Nothing to update.')
    raise SystemExit(0)
print(f'{new_total} new/changed file(s) to re-extract.')
