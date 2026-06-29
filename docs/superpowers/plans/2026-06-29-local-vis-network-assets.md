# Local vis-network Asset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop emitting a `<script src="https://unpkg.com/vis-network@9.1.6/...">` tag from `to_html`. Ship vis-network inside the `graphify` package, copy it next to `graph.html` at generation time, and have the HTML reference the same-origin copy.

**Architecture:** A new vendored binary (`graphify/assets/vis-network.min.js`, 702,611 bytes) is committed to the repo and registered in `pyproject.toml` `package-data` so it lands in the wheel/sdist. `graphify/export.py` gains two helpers — `_vendored_vis_js()` (reads from the installed package via `importlib.resources`) and `_emit_vis_js()` (idempotent copy to the HTML output directory, skipping when the existing copy is byte-identical to avoid mtime churn) — and `to_html` calls `_emit_vis_js` and emits `<script src="./vis-network.min.js">`. The CDN URL, SRI hash, and `crossorigin="anonymous"` go away.

**Tech Stack:** Python 3.10+, `importlib.resources` (stdlib), `pytest`, `unittest.mock`/`monkeypatch`. No new third-party dependencies.

**Spec:** `docs/superpowers/specs/2026-06-29-local-vis-network-assets-design.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `graphify/assets/vis-network.min.js` | **Create** | Vendored vis-network UMD bundle, 702,611 bytes, committed. |
| `graphify/export.py` | **Modify** | Add `_VIS_NETWORK_FILENAME`, `_vendored_vis_js()`, `_emit_vis_js()`. Wire into `to_html`. Replace CDN `<script>` tag. |
| `pyproject.toml` | **Modify** | Register `assets/vis-network.min.js` in `[tool.setuptools.package-data]`. |
| `tests/test_export.py` | **Modify** | Delete `test_to_html_pins_visjs_version_with_sri`. Extend `test_to_html_contains_visjs`. Add tests for new helpers and for the new `to_html` behavior. |
| `tests/test_pipeline.py` | **Modify** | Tighten the existing `assert "vis-network" in html` assertion. |

No changes to `__main__.py`, `watch.py`, `serve.py`, or any other caller.

---

## Task 1: Vendor `vis-network.min.js` into the package

**Files:**
- Create: `graphify/assets/vis-network.min.js`

- [ ] **Step 1: Create the assets directory**

```bash
mkdir -p graphify/assets
```

- [ ] **Step 2: Download the vendored copy from upstream**

```bash
curl -sSL https://unpkg.com/vis-network@9.1.6/standalone/umd/vis-network.min.js -o graphify/assets/vis-network.min.js
```

- [ ] **Step 3: Verify size and sha384 match the expected values**

```bash
wc -c graphify/assets/vis-network.min.js
openssl dgst -sha384 graphify/assets/vis-network.min.js | awk '{print $2}'
```

Expected:
- `wc -c` reports `   702611 graphify/assets/vis-network.min.js`
- The sha384 output is `531ea986273d3c41c9dfc62dae28e1933c89f324251fc8bff9bb8147cb3798064e26b3f5830caf01c218977196b695f5`

If either check fails, delete the file and re-run the curl — the file is the only ground truth for the rest of the plan.

- [ ] **Step 4: Confirm the file is a valid JavaScript UMD bundle**

```bash
head -c 200 graphify/assets/vis-network.min.js
tail -c 200 graphify/assets/vis-network.min.js
```

Expected: head shows something like `/*! vis-network 9.1.6...` (UMD header). tail shows a closing `})();` or similar. If either looks corrupted, abort.

- [ ] **Step 5: Commit the vendored file**

```bash
git add graphify/assets/vis-network.min.js
git commit -m "chore(assets): vendor vis-network 9.1.6 (drop unpkg CDN)"
```

---

## Task 2: Register the vendored file in `package-data`

**Files:**
- Modify: `pyproject.toml:119`

- [ ] **Step 1: Add the new entry to the `package-data` glob list**

Open `pyproject.toml` and find line 119 (the `graphify` entry under `[tool.setuptools.package-data]`). It currently ends with `... "always_on/*.md"]`. Change it to append `"assets/vis-network.min.js"`:

```toml
graphify = ["skill.md", "skill-codex.md", "skill-opencode.md", "skill-kilo.md", "command-kilo.md", "skill-aider.md", "skill-amp.md", "skill-agents.md", "skill-copilot.md", "skill-claw.md", "skill-windows.md", "skill-droid.md", "skill-trae.md", "skill-kiro.md", "skill-vscode.md", "skill-pi.md", "skill-devin.md", "skills/*/references/*.md", "always_on/*.md", "assets/vis-network.min.js"]
```

- [ ] **Step 2: Build sdist and wheel into a scratch directory**

```bash
python -m build --sdist --wheel --outdir /tmp/graphify-dist
```

Expected: both a `.whl` and a `.tar.gz` appear in `/tmp/graphify-dist/`. If `python -m build` is not installed, install it first: `pip install build`.

- [ ] **Step 3: Verify the file is inside both artifacts**

```bash
python -m zipfile -l /tmp/graphify-dist/*.whl | grep vis-network
tar -tzf /tmp/graphify-dist/*.tar.gz | grep vis-network
```

Expected: each command prints one matching line containing `vis-network.min.js`. If either is empty, fix `pyproject.toml` and rebuild.

- [ ] **Step 4: Clean up the scratch artifacts**

```bash
rm -rf /tmp/graphify-dist
```

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml
git commit -m "build: include vendored vis-network in package data"
```

---

## Task 3: Add `_VIS_NETWORK_FILENAME` constant (TDD)

**Files:**
- Modify: `graphify/export.py:21` (just below the existing `_BACKUP_ARTIFACTS` block — pick any location above the first function definition; the constant is only used inside the file)
- Test: `tests/test_export.py`

- [ ] **Step 1: Write the failing test**

Open `tests/test_export.py` and append at the end of the file:

```python
def test_vis_network_filename_constant():
    from graphify.export import _VIS_NETWORK_FILENAME
    assert _VIS_NETWORK_FILENAME == "vis-network.min.js"
```

- [ ] **Step 2: Run the test and confirm it fails**

```bash
pytest tests/test_export.py::test_vis_network_filename_constant -v
```

Expected: FAIL with `ImportError: cannot import name '_VIS_NETWORK_FILENAME' from 'graphify.export'`.

- [ ] **Step 3: Add the constant in `export.py`**

Place this constant block immediately above the first function definition (`def _html_styles(...)` or whatever comes first after the module-level `_BACKUP_ARTIFACTS` list). If you cannot easily find that spot, place it directly after the `_BACKUP_ARTIFACTS` list and before the first `def`:

```python
# Filename of the vendored vis-network UMD bundle copied next to generated
# graph.html files. The actual bytes live in graphify/assets/ and are read
# via importlib.resources at generation time.
_VIS_NETWORK_FILENAME = "vis-network.min.js"
```

- [ ] **Step 4: Run the test and confirm it passes**

```bash
pytest tests/test_export.py::test_vis_network_filename_constant -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add graphify/export.py tests/test_export.py
git commit -m "feat(export): add _VIS_NETWORK_FILENAME constant"
```

---

## Task 4: Add `_vendored_vis_js()` helper (TDD)

**Files:**
- Modify: `graphify/export.py` (place directly below the constant from Task 3)
- Test: `tests/test_export.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_export.py`:

```python
def test_vendored_vis_js_returns_committed_file_bytes():
    from importlib.resources import files
    expected = files("graphify").joinpath("assets", "vis-network.min.js").read_bytes()
    from graphify.export import _vendored_vis_js
    assert _vendored_vis_js() == expected
    assert len(_vendored_vis_js()) > 0
```

- [ ] **Step 2: Run the test and confirm it fails**

```bash
pytest tests/test_export.py::test_vendored_vis_js_returns_committed_file_bytes -v
```

Expected: FAIL with `ImportError: cannot import name '_vendored_vis_js' from 'graphify.export'`.

- [ ] **Step 3: Implement `_vendored_vis_js()`**

Add this function directly below the constant in `export.py`:

```python
def _vendored_vis_js() -> bytes:
    """Read the vendored vis-network.min.js from the installed package.

    Uses importlib.resources so it works from an in-repo editable install,
    a wheel install, and an sdist install alike.
    """
    from importlib.resources import files
    return files("graphify").joinpath("assets", _VIS_NETWORK_FILENAME).read_bytes()
```

- [ ] **Step 4: Run the test and confirm it passes**

```bash
pytest tests/test_export.py::test_vendored_vis_js_returns_committed_file_bytes -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add graphify/export.py tests/test_export.py
git commit -m "feat(export): add _vendored_vis_js() helper"
```

---

## Task 5: Add `_emit_vis_js()` helper with 3 tests (TDD)

**Files:**
- Modify: `graphify/export.py` (place directly below `_vendored_vis_js`)
- Test: `tests/test_export.py`

- [ ] **Step 1: Write the three failing tests**

Append to `tests/test_export.py`:

```python
def test_emit_vis_js_creates_file_when_missing(tmp_path):
    from graphify.export import _emit_vis_js, _VIS_NETWORK_FILENAME
    target = tmp_path / "graph.html"  # parent dir is what matters here
    assert not (target.parent / _VIS_NETWORK_FILENAME).exists()
    _emit_vis_js(target)
    assert (target.parent / _VIS_NETWORK_FILENAME).exists()
    assert (target.parent / _VIS_NETWORK_FILENAME).read_bytes() == _vendored_vis_js()


def test_emit_vis_js_skips_rewrite_when_bytes_identical(tmp_path):
    from graphify.export import _emit_vis_js, _VIS_NETWORK_FILENAME, _vendored_vis_js
    html = tmp_path / "graph.html"
    _emit_vis_js(html)
    target = html.parent / _VIS_NETWORK_FILENAME
    mtime_before = target.stat().st_mtime_ns
    # Force a tiny clock tick so a no-op write would still register.
    import time
    time.sleep(0.01)
    _emit_vis_js(html)
    mtime_after = target.stat().st_mtime_ns
    assert mtime_after == mtime_before
    assert target.read_bytes() == _vendored_vis_js()


def test_emit_vis_js_overwrites_when_vendored_changes(monkeypatch, tmp_path):
    from graphify import export
    monkeypatch.setattr(export, "_vendored_vis_js", lambda: b"DIFFERENT-BYTES")
    from graphify.export import _emit_vis_js, _VIS_NETWORK_FILENAME
    html = tmp_path / "graph.html"
    _emit_vis_js(html)
    target = html.parent / _VIS_NETWORK_FILENAME
    assert target.read_bytes() == b"DIFFERENT-BYTES"
```

- [ ] **Step 2: Run the three tests and confirm they fail**

```bash
pytest tests/test_export.py::test_emit_vis_js_creates_file_when_missing tests/test_export.py::test_emit_vis_js_skips_rewrite_when_bytes_identical tests/test_export.py::test_emit_vis_js_overwrites_when_vendored_changes -v
```

Expected: all three FAIL with `ImportError: cannot import name '_emit_vis_js' from 'graphify.export'`.

- [ ] **Step 3: Implement `_emit_vis_js()`**

Add this function directly below `_vendored_vis_js()`:

```python
def _emit_vis_js(html_path: Path) -> None:
    """Copy the vendored vis-network.min.js next to html_path if missing or stale.

    Skips the write when the existing file is byte-identical to the vendored
    copy. The byte-equality short-circuit is what keeps build caches, file
    watchers, and Obsidian sync from re-processing the file on every run.
    """
    target = html_path.parent / _VIS_NETWORK_FILENAME
    vendored = _vendored_vis_js()
    if target.exists() and target.read_bytes() == vendored:
        return
    target.write_bytes(vendored)
```

- [ ] **Step 4: Run the three tests and confirm they pass**

```bash
pytest tests/test_export.py::test_emit_vis_js_creates_file_when_missing tests/test_export.py::test_emit_vis_js_skips_rewrite_when_bytes_identical tests/test_export.py::test_emit_vis_js_overwrites_when_vendored_changes -v
```

Expected: all three PASS.

- [ ] **Step 5: Commit**

```bash
git add graphify/export.py tests/test_export.py
git commit -m "feat(export): add _emit_vis_js() helper (idempotent copy)"
```

---

## Task 6: Wire `_emit_vis_js` into `to_html` and swap the script tag (TDD)

**Files:**
- Modify: `graphify/export.py:790-792` (script tag block) and `graphify/export.py:820` (the `Path(output_path).write_text(...)` line)
- Test: `tests/test_export.py` (extend `test_to_html_contains_visjs`; add a new test for the emitted asset)

- [ ] **Step 1: Extend the existing visjs test with the new assertions**

Open `tests/test_export.py`, find `test_to_html_contains_visjs` (lines 93–100), and replace its body with:

```python
def test_to_html_contains_visjs():
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.html"
        to_html(G, communities, str(out))
        content = out.read_text()
        assert "vis-network" in content
        # New: same-origin reference, no CDN, no SRI, no crossorigin.
        assert '<script src="./vis-network.min.js"></script>' in content
        assert 'unpkg.com' not in content
        assert 'integrity=' not in content
        assert 'crossorigin="anonymous"' not in content
```

- [ ] **Step 2: Add a new test for the emitted local asset**

Append to `tests/test_export.py`:

```python
def test_to_html_emits_local_vis_network_asset():
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.html"
        to_html(G, communities, str(out))
        asset = out.parent / "vis-network.min.js"
        assert asset.exists()
        # Byte-equality with the vendored copy is the correctness contract.
        assert asset.read_bytes() == _vendored_vis_js()
```

(Note: `_vendored_vis_js` is already imported in this file via `test_vendored_vis_js_returns_committed_file_bytes`; the import inside that test's body is local. Add `from graphify.export import _vendored_vis_js` at the top of `test_export.py` to make this new test cleaner, OR keep the local import inside the test body — either is fine. Choose the local import to keep this task's diff minimal.)

Revised test (use this version):

```python
def test_to_html_emits_local_vis_network_asset():
    from graphify.export import _vendored_vis_js
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.html"
        to_html(G, communities, str(out))
        asset = out.parent / "vis-network.min.js"
        assert asset.exists()
        # Byte-equality with the vendored copy is the correctness contract.
        assert asset.read_bytes() == _vendored_vis_js()
```

- [ ] **Step 3: Run the new/extended tests and confirm they fail**

```bash
pytest tests/test_export.py::test_to_html_contains_visjs tests/test_export.py::test_to_html_emits_local_vis_network_asset -v
```

Expected: BOTH fail. `test_to_html_contains_visjs` fails on the new `assert 'unpkg.com' not in content` (the old SRI-bearing script tag is still being emitted). `test_to_html_emits_local_vis_network_asset` fails on `assert asset.exists()` (the asset file is not being copied yet).

- [ ] **Step 4: Replace the script tag in `to_html`**

Open `graphify/export.py`. Find the three lines currently at 790–792:

```python
<script src="https://unpkg.com/vis-network@9.1.6/standalone/umd/vis-network.min.js"
        integrity="sha384-Ux6phic9PEHJ38YtrijhkzyJ8yQlH8i/+buBR8s3mAZOJrP1gwyvAcIYl3GWtpX1"
        crossorigin="anonymous"></script>
```

Replace with the single line:

```python
<script src="./vis-network.min.js"></script>
```

(Note: leading two-space indentation is unchanged — the line still lives inside the f-string template literal at the same column as the rest of the head block.)

- [ ] **Step 5: Wire `_emit_vis_js` into `to_html`**

In the same file, find the final line of `to_html`:

```python
Path(output_path).write_text(html, encoding="utf-8")  # nosec
```

Insert the asset-emit call immediately before it:

```python
_emit_vis_js(Path(output_path))
Path(output_path).write_text(html, encoding="utf-8")  # nosec
```

- [ ] **Step 6: Run the new/extended tests and confirm they pass**

```bash
pytest tests/test_export.py::test_to_html_contains_visjs tests/test_export.py::test_to_html_emits_local_vis_network_asset -v
```

Expected: BOTH pass.

- [ ] **Step 7: Commit**

```bash
git add graphify/export.py tests/test_export.py
git commit -m "feat(export): to_html uses local vis-network, no CDN/SRI"
```

---

## Task 7: Delete the obsolete SRI/CDN test

**Files:**
- Modify: `tests/test_export.py:103-127` (the `test_to_html_pins_visjs_version_with_sri` function)

- [ ] **Step 1: Confirm the SRI test is still in the suite**

```bash
grep -n "test_to_html_pins_visjs_version_with_sri" tests/test_export.py
```

Expected: one match at the function definition. (The SRI test will currently still pass because Task 6 has only just replaced the script tag — the docstring no longer matches reality, but the function body asserts the new tag is present and asserts the old artifacts are absent.)

- [ ] **Step 2: Delete the entire test function**

Open `tests/test_export.py`. Find the function `test_to_html_pins_visjs_version_with_sri`. It begins with a multi-line docstring explaining why SRI is required and a hash that no longer applies. Delete the entire function — the leading `def` line, the docstring, the body, and the trailing blank line that separates it from the next test. Leave the surrounding tests untouched.

The exact text to delete (verify line range with `grep -n` first):

```python
def test_to_html_pins_visjs_version_with_sri():
    """vis-network script tag must use a pinned versioned URL with a sha384
    Subresource Integrity hash and crossorigin=anonymous. Without this,
    a compromised CDN could ship arbitrary JavaScript into every rendered
    graph viewer. The hash was verified against the upstream file at
    https://unpkg.com/vis-network@9.1.6/standalone/umd/vis-network.min.js
    (sha384-Ux6phic9PEHJ38YtrijhkzyJ8yQlH8i/+buBR8s3mAZOJrP1gwyvAcIYl3GWtpX1).
    Bumping the vis-network version MUST update both the URL and the hash.
    """
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.html"
        to_html(G, communities, str(out))
        content = out.read_text()

    # Versioned URL — unversioned `vis-network/standalone/...` is rejected.
    assert "vis-network@9.1.6/standalone/umd/vis-network.min.js" in content
    assert "https://unpkg.com/vis-network/standalone" not in content

    # SRI integrity attribute pinning the known-good hash.
    assert 'integrity="sha384-Ux6phic9PEHJ38YtrijhkzyJ8yQlH8i/+buBR8s3mAZOJrP1gwyvAcIYl3GWtpX1"' in content

    # crossorigin="anonymous" is required for SRI on cross-origin scripts.
    assert 'crossorigin="anonymous"' in content
```

- [ ] **Step 3: Confirm the function is gone**

```bash
grep -n "test_to_html_pins_visjs_version_with_sri" tests/test_export.py
```

Expected: no output.

- [ ] **Step 4: Run the test_export suite and confirm it still passes**

```bash
pytest tests/test_export.py -v
```

Expected: every test passes. The 4 added in Tasks 3–6 should be visible by name.

- [ ] **Step 5: Commit**

```bash
git add tests/test_export.py
git commit -m "test(export): drop obsolete SRI/CDN pin test (local asset now)"
```

---

## Task 8: Tighten `tests/test_pipeline.py:83`

**Files:**
- Modify: `tests/test_pipeline.py:83`

- [ ] **Step 1: Read the current assertion**

```bash
sed -n '80,86p' tests/test_pipeline.py
```

Expected output: shows the surrounding context of line 83, which currently is `assert "vis-network" in html`.

- [ ] **Step 2: Replace the loose substring check with the precise path check**

Change line 83 from:

```python
    assert "vis-network" in html
```

to:

```python
    assert './vis-network.min.js' in html
```

- [ ] **Step 3: Run the pipeline test to confirm it still passes**

```bash
pytest tests/test_pipeline.py -v
```

Expected: every test in the file passes.

- [ ] **Step 4: Commit**

```bash
git add tests/test_pipeline.py
git commit -m "test(pipeline): tighten vis-network assertion to local path"
```

---

## Task 9: Final verification — full test suite + manual smoke test

**Files:** none modified; this task is a check.

- [ ] **Step 1: Run the full test suite**

```bash
pytest
```

Expected: all tests pass. If any test fails, stop and investigate — every test added in this plan is by construction green at the time it was committed, so a failure here means either an unrelated regression or a missed interaction. Read the failure carefully before proceeding.

- [ ] **Step 2: Smoke-test `to_html` end-to-end**

Run a one-off invocation that exercises the public function. The graphify CLI itself is fine if it can be run, but a direct Python call avoids any CLI flag friction:

```bash
python -c "
import json, tempfile
from pathlib import Path
from graphify.build import build_from_json
from graphify.cluster import cluster
from graphify.export import to_html

with tempfile.TemporaryDirectory() as tmp:
    fixture = Path('tests/fixtures/extraction.json')
    G = build_from_json(json.loads(fixture.read_text()))
    communities = cluster(G)
    out = Path(tmp) / 'graph.html'
    to_html(G, communities, str(out))
    html = out.read_text()
    asset = out.parent / 'vis-network.min.js'
    print('html size:', len(html), 'bytes')
    print('asset size:', asset.stat().st_size, 'bytes')
    print('asset = vendored:', asset.read_bytes() == (Path('graphify/assets/vis-network.min.js').read_bytes()))
    print('html references local asset:', './vis-network.min.js' in html)
    print('html has no unpkg:', 'unpkg.com' not in html)
    print('html has no integrity:', 'integrity=' not in html)
"
```

Expected output (numbers approximate, the booleans must all be `True`):

```
html size: ~21000 bytes
asset size: 702611 bytes
asset = vendored: True
html references local asset: True
html has no unpkg: True
html has no integrity: True
```

- [ ] **Step 3: Open the generated HTML in a browser (manual)**

Copy a generated `graph.html` to a fresh directory, open it in a browser, and confirm the graph renders. The page should load with no network requests to `unpkg.com` (visible in the browser devtools network tab). If the page is blank, the most likely cause is a path mismatch between the script tag and the asset file — double-check that `vis-network.min.js` sits beside `graph.html`, not one level deeper.

- [ ] **Step 4: Final commit (only if Step 2 or 3 surfaced a fix)**

If everything in Steps 1–3 was green, there is nothing to commit. If you had to make a tweak (e.g., a forgotten import, a path adjustment), commit it now with a `fix:` or `chore:` prefix and a one-line message describing what you fixed.

---

## Self-Review Notes

The plan was checked against `docs/superpowers/specs/2026-06-29-local-vis-network-assets-design.md`:

- **Spec §1 (vendored file location & distribution)** → Tasks 1 and 2.
- **Spec §2 (`to_html` behavior change: constant, helpers, wire-up, script tag)** → Tasks 3, 4, 5, 6.
- **Spec §3 (test updates: delete SRI test, extend visjs test, add 3 new tests, optional pipeline tighten)** → Tasks 6, 7, 8. The spec lists three new tests (3.3, 3.4, 3.5); the plan adds them across Tasks 4, 5, and 6 in TDD order — `test_vendored_vis_js_returns_committed_file_bytes` (3.3a), `test_emit_vis_js_*` (3.3b, 3.4, 3.5), and `test_to_html_emits_local_vis_network_asset` (3.3c).
- **Spec §4 (risks)** — covered by Task 9 Step 1 (full test suite catches regressions) and Step 2 (smoke test catches the wheel/sdist packaging risk explicitly).
- **Spec §5 (file map)** — every row in the spec's summary table is touched by exactly one task in the plan.

Type and name consistency: `_VIS_NETWORK_FILENAME` is defined in Task 3, consumed by `_vendored_vis_js()` and `_emit_vis_js()` in Tasks 4 and 5, and the on-disk name matches the string literal everywhere. `_emit_vis_js` is called once, by `to_html` in Task 6. No drift.
