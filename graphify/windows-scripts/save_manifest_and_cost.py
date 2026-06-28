import sys
import json
from pathlib import Path
from datetime import datetime, timezone
from graphify.detect import save_manifest
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

input_path = sys.argv[1] if len(sys.argv) > 1 else '.'
detect = json.loads(Path('graphify-out/.graphify_detect.json').read_text(encoding='utf-8'))

# 'files' is the changed subset in --update mode, or the full corpus in a full build.
# save_manifest() seeds unchanged entries from the existing manifest, so passing
# only changed files is correct — there is no need to re-hash the full corpus.
# root= relativizes manifest keys so a later --update matches cached files (#1417).
save_manifest(detect['files'], root=Path(input_path))

extract = json.loads(Path('graphify-out/.graphify_extract.json').read_text(encoding='utf-8'))
input_tok = extract.get('input_tokens', 0)
output_tok = extract.get('output_tokens', 0)

cost_path = Path('graphify-out/cost.json')
if cost_path.exists():
    cost = json.loads(cost_path.read_text(encoding='utf-8'))
else:
    cost = {'runs': [], 'total_input_tokens': 0, 'total_output_tokens': 0}

cost['runs'].append({
    'date': datetime.now(timezone.utc).isoformat(),
    'input_tokens': input_tok,
    'output_tokens': output_tok,
    'files': detect.get('total_files', 0),
})
cost['total_input_tokens'] += input_tok
cost['total_output_tokens'] += output_tok
cost_path.write_text(json.dumps(cost, indent=2, ensure_ascii=False), encoding='utf-8')

print(f'This run: {input_tok:,} input tokens, {output_tok:,} output tokens')
print(f'All time: {cost["total_input_tokens"]:,} input, {cost["total_output_tokens"]:,} output ({len(cost["runs"])} runs)')
