import sys
import json, sys
from graphify.benchmark import run_benchmark, print_benchmark
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

detection = json.loads(Path('graphify-out/.graphify_detect.json').read_text(encoding='utf-8'))
total_words = detection.get('total_words', 0)
if total_words <= 5000:
    sys.exit(0)

result = run_benchmark('graphify-out/graph.json', corpus_words=total_words)
print_benchmark(result)
