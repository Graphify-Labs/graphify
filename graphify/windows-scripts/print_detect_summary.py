import sys
import json, sys
from collections import Counter
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

detect = json.loads(Path('.graphify_detect.json').read_text(encoding='utf-8'))
files = detect.get('files', {})
total_files = detect.get('total_files', 0)
total_words = detect.get('total_words', 0)
skipped = detect.get('skipped_sensitive', [])
input_path = Path(detect.get('input_path', '.'))

if total_files == 0:
    print('No supported files found.')
    sys.exit(1)

print(f'Corpus: {total_files} files - ~{total_words:,} words')
for cat in ['code', 'docs', 'document', 'papers', 'paper', 'images', 'image', 'video']:
    file_list = [
        f for f in files.get(cat, [])
        if '/assets/' not in f and '\\assets\\' not in f
    ]
    if not file_list:
        continue
    display = cat if cat not in ('document', 'paper', 'image') else {'document': 'docs', 'paper': 'papers', 'image': 'images'}[cat]
    exts = sorted({Path(f).suffix for f in file_list if Path(f).suffix})
    pad = max(1, 10 - len(display))
    print(f'  {display}:{" " * pad}{len(file_list)} files ({" ".join(exts[:6])})')

if skipped:
    print(f'  [{len(skipped)} sensitive file(s) skipped]')

has_video = bool([f for f in files.get('video', []) if '/assets/' not in f and '\\assets\\' not in f])
print(f'HAS_VIDEO={str(has_video).lower()}')

if total_words > 2_000_000 or total_files > 200:
    print(f'\nWARNING: Large corpus ({total_files} files, ~{total_words:,} words). Recommend running on a subfolder.')
    subdir_counts: Counter = Counter()
    all_file_paths = [f for flist in files.values() for f in flist]
    for f in all_file_paths:
        try:
            rel = Path(f).relative_to(input_path)
            top = rel.parts[0] if len(rel.parts) > 1 else '.'
        except ValueError:
            top = Path(f).parts[-2] if len(Path(f).parts) > 1 else '.'
        subdir_counts[top] += 1
    print('Top subdirectories by file count:')
    for subdir, count in subdir_counts.most_common(5):
        print(f'  {subdir}/  ({count} files)')
    sys.exit(2)

sys.exit(0)
