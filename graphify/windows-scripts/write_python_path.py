import sys
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

Path('graphify-out').mkdir(exist_ok=True)
Path('graphify-out/.graphify_python').write_text(sys.executable, encoding='utf-8')
