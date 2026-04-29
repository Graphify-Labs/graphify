import sys, json
from graphify.detect import detect
from pathlib import Path

result = detect(Path(sys.argv[1]))
print(json.dumps(result))
