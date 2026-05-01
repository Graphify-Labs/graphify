import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

with open(".graphify_python", "w") as f:
    f.write(sys.executable)
