import json
from pathlib import Path

result = json.loads(open('.graphify_incremental.json').read()) if Path('.graphify_incremental.json').exists() else {}
code_exts = {'.py', '.ts', '.js', '.go', '.rs', '.java', '.cpp', '.c', '.rb', '.swift', '.kt', '.cs', '.scala', '.php', '.cc', '.cxx', '.hpp', '.h', '.kts', '.lua', '.toc'}
new_files = result.get('new_files', {})
all_changed = [f for files in new_files.values() for f in files]
code_only = all(Path(f).suffix.lower() in code_exts for f in all_changed)
print('code_only:', code_only)
