# graphify reference: offer to exclude committed bundles

Load this from Step 2a of the core skill (#4425). `detect()` already prunes `dist/`/`build/`/`target/` by name, but a bundle committed elsewhere still gets extracted, minting a duplicate node for every function it bundles (mirror communities, a duplicate god node).

```bash
$(cat graphify-out/.graphify_python) -c "
import json
from pathlib import Path
d = json.loads(Path('graphify-out/.graphify_detect.json').read_text(encoding='utf-8'))
marks = ('webpackBootstrap', '__webpack_require__', 'System.register(', 'For license information')
hits = []
for rel in d['files'].get('code', []):
    p = Path(rel)
    reasons = []
    if '.min.' in p.name: reasons.append('minified filename')
    size = p.stat().st_size if p.exists() else 0
    if size > 300_000 and p.suffix in ('.js', '.mjs', '.cjs'): reasons.append(f'{size:,} bytes')
    if (not reasons or size > 300_000) and any(m in p.read_text(encoding='utf-8', errors='ignore')[:4000] for m in marks): reasons.append('bundler banner')
    if reasons: hits.append({'path': rel, 'reasons': reasons})
Path('graphify-out/.graphify_bundle_candidates.json').write_text(json.dumps(hits), encoding='utf-8')
print(f'Bundle candidates: {len(hits)}')
"
```

Read `graphify-out/.graphify_bundle_candidates.json` silently. If empty, continue unchanged. Otherwise list each path with its reason(s) and ask: "These look like committed build output rather than source, which tends to produce mirror communities and a duplicate god node. Exclude before extraction?" If yes, append the confirmed paths to `.graphifyignore` at the scan root (create it if needed) and re-run Step 2's detection. If no, continue with them in scope.
