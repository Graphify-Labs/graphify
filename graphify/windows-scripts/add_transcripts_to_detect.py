import sys
import json
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

transcripts_file = Path('graphify-out/.graphify_transcripts.json')
detect_file = Path('.graphify_detect.json')

if not transcripts_file.exists():
    print('No transcripts file found, skipping.')
    raise SystemExit(0)

transcript_paths = json.loads(transcripts_file.read_text(encoding='utf-8'))
if not transcript_paths:
    print('No transcripts produced.')
    raise SystemExit(0)

detect = json.loads(detect_file.read_text(encoding='utf-8'))
detect.setdefault('files', {}).setdefault('docs', []).extend(transcript_paths)
detect['total_files'] = detect.get('total_files', 0) + len(transcript_paths)
detect_file.write_text(json.dumps(detect, indent=2), encoding='utf-8')
print(f'Transcribed {len(transcript_paths)} video file(s) -> treating as docs')
