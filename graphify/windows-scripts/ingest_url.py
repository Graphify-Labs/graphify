import sys
from graphify.ingest import ingest
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

url        = sys.argv[1] if len(sys.argv) > 1 else ''
author     = sys.argv[2] if len(sys.argv) > 2 else None
contributor = sys.argv[3] if len(sys.argv) > 3 else None

try:
    out = ingest(url, Path('./raw'), author=author, contributor=contributor)
    print(f'Saved to {out}')
except ValueError as e:
    print(f'error: {e}', file=sys.stderr)
    sys.exit(1)
except RuntimeError as e:
    print(f'error: {e}', file=sys.stderr)
    sys.exit(1)
