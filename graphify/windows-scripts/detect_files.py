import sys, json
from graphify.detect import detect
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

def _is_assets(path_str: str) -> bool:
    return any(part.lower() == 'assets' for part in Path(path_str).parts)

input_path = Path(sys.argv[1]).resolve()
result = detect(input_path)
result['input_path'] = str(input_path)

# Discard files inside any folder named 'assets'
for category in result.get('files', {}):
    result['files'][category] = [f for f in result['files'][category] if not _is_assets(f)]
result['total_files'] = sum(len(v) for v in result.get('files', {}).values())

Path('.graphify_detect.json').write_text(json.dumps(result), encoding='utf-8')
