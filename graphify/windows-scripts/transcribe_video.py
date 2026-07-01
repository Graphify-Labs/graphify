import sys
import json, os
from pathlib import Path
from graphify.transcribe import transcribe_all
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

detect = json.loads(Path('graphify-out/.graphify_detect.json').read_text(encoding='utf-8'))
video_files = detect.get('files', {}).get('video', [])
prompt = os.environ.get('GRAPHIFY_WHISPER_PROMPT', 'Use proper punctuation and paragraph breaks.')

transcript_paths = transcribe_all(video_files, initial_prompt=prompt)
print(json.dumps(transcript_paths))
