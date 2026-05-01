import sys, json
from graphify.detect import detect_incremental, save_manifest
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

def _is_assets(path_str: str) -> bool:
    return any(part.lower() == 'assets' for part in Path(path_str).parts)

result = detect_incremental(Path(sys.argv[1]))

# Discard files inside any folder named 'assets'
for category in result.get('files', {}):
    result['files'][category] = [f for f in result['files'][category] if not _is_assets(f)]
for category in result.get('new_files', {}):
    result['new_files'][category] = [f for f in result['new_files'][category] if not _is_assets(f)]
result['new_total'] = sum(len(v) for v in result.get('new_files', {}).values())
result['total_files'] = sum(len(v) for v in result.get('files', {}).values())

new_total = result.get('new_total', 0)
print(json.dumps(result, indent=2))
Path('.graphify_incremental.json').write_text(json.dumps(result), encoding='utf-8')
if new_total == 0:
    print('No files changed since last run. Nothing to update.')
    raise SystemExit(0)
print(f'{new_total} new/changed file(s) to re-extract.')

# Write .graphify_detect.json scoped to new files only so all downstream
# scripts (check_extraction_cache, print_timing_estimate, build_graph, etc.)
# operate on the changed file set, not the full corpus.
detect_for_update = {
    'files': result['new_files'],
    'total_files': result['new_total'],
    'total_words': result.get('total_words', 0),
    'skipped_sensitive': result.get('skipped_sensitive', []),
    'input_path': result.get('input_path', str(Path(sys.argv[1]).resolve())),
}
Path('.graphify_detect.json').write_text(json.dumps(detect_for_update), encoding='utf-8')
