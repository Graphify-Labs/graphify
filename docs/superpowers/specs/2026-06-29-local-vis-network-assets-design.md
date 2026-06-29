# Design: Local vis-network Asset (drop CDN, ship vendored copy)

**Date:** 2026-06-29
**Branch:** v8
**Scope:** `graphify/export.py:to_html` HTML output, three call sites, tests, package data

---

## Problem

`to_html` currently emits a `<script src="https://unpkg.com/vis-network@9.1.6/..." integrity="sha384-..." crossorigin="anonymous">` tag (`graphify/export.py:790–792`). Every viewer of a generated `graph.html` must reach `unpkg.com` to render. That dependency:

- Breaks offline builds, air-gapped review, and locked-down CI runners.
- Pushes a third-party runtime dependency into a project that is otherwise fully self-contained.
- Adds an SRI + crossorigin concern the project has to keep correct across vis-network upgrades.

The fix is to ship vis-network inside the `graphify` package and copy it next to `graph.html` at generation time, so the HTML is fully offline-capable and the script tag points at a same-origin relative path.

---

## Decisions (locked)

| Question | Decision |
|---|---|
| Where does the vendored file live? | Inside the `graphify` Python package — ships with wheel + sdist. |
| Keep CDN fallback? | No. Hard switch to local. No env var, no fallback path. |
| How does `graph.html` load it? | Copy vendored copy next to `graph.html`; HTML references `./vis-network.min.js`. |
| Upgrade flow? | Out of scope. User will integrate the asset into a future offline-installer bundle. |
| First-time import flow? | Out of scope. The vendored file is committed; no downloader script is shipped. |

---

## Architecture

```
graphify/                              ← Python package
  assets/
    vis-network.min.js                 ← vendored copy, committed, ~600KB
  export.py
    to_html(...)
      ├─ _vendored_vis_js()            # importlib.resources -> bytes
      ├─ _emit_vis_js(html_path)       # copy to html_path.parent, idempotent
      └─ write HTML, <script src="./vis-network.min.js">

pyproject.toml
  [tool.setuptools.package-data]
    graphify = [..., "assets/vis-network.min.js"]

tests/test_export.py
  - delete test_to_html_pins_visjs_version_with_sri
  - extend test_to_html_contains_visjs
  - add 3 new tests (see §4)
```

Call sites (`__main__.py:3553`, `__main__.py:4061`, `watch.py:864`) need **no changes** — the new behavior is encapsulated in `to_html` itself, including the recursive aggregated-view call at `export.py:700`.

---

## 1. Vendored file location and distribution

- Path: `graphify/assets/vis-network.min.js` (no new top-level directory; aligns with the existing `assets/` convention mentioned in code comments elsewhere).
- File is committed to git. ~600KB.
- `pyproject.toml` `[tool.setuptools.package-data]` `graphify` list gains `"assets/vis-network.min.js"`.
- Verification at release time (manual, not in this spec's automation): `python -m build` then `python -m zipfile -l dist/*.whl | grep vis-network` and `tar -tzf dist/*.tar.gz | grep vis-network` both show the file.

No downloader script, no upgrade script, no CI network test. Those concerns are deferred to the user's offline-installer work.

---

## 2. `to_html` behavior change

### New module-level constant

```python
_VIS_NETWORK_FILENAME = "vis-network.min.js"
```

### New helper: `_vendored_vis_js() -> bytes`

```python
def _vendored_vis_js() -> bytes:
    """Read the vendored vis-network.min.js from the installed package."""
    from importlib.resources import files
    return (files("graphify").joinpath("assets", _VIS_NETWORK_FILENAME).read_bytes())
```

Uses `importlib.resources` so it works identically from an in-repo editable install, a wheel, and an sdist install.

### New helper: `_emit_vis_js(html_path: Path) -> None`

```python
def _emit_vis_js(html_path: Path) -> None:
    """Copy vendored vis-network.min.js next to html_path if missing or stale.

    Skips the write when the existing file is byte-identical to the vendored
    copy. This avoids mtime churn that would invalidate build caches and
    confuse file watchers / Obsidian sync.
    """
    target = html_path.parent / _VIS_NETWORK_FILENAME
    vendored = _vendored_vis_js()
    if target.exists() and target.read_bytes() == vendored:
        return
    target.write_bytes(vendored)
```

### `to_html` edits

1. Immediately before the `Path(output_path).write_text(html, ...)` call (`export.py:820`), insert:
   ```python
   _emit_vis_js(Path(output_path))
   ```
2. Replace lines 790–792:
   ```html
   <script src="https://unpkg.com/vis-network@9.1.6/standalone/umd/vis-network.min.js"
           integrity="sha384-Ux6phic9PEHJ38YtrijhkzyJ8yQlH8i/+buBR8s3mAZOJrP1gwyvAcIYl3GWtpX1"
           crossorigin="anonymous"></script>
   ```
   with:
   ```html
   <script src="./vis-network.min.js"></script>
   ```

That's it for the production code. The aggregated-view recursive call at line 700 inherits the change automatically.

### Failure modes

- Vendored file missing in installed package → `_vendored_vis_js()` raises `FileNotFoundError` → `to_html` propagates. **No silent fallback to CDN** — by design (the whole point is "no CDN").
- Output directory not writable → `target.write_bytes` raises `PermissionError` → propagates. Caller surfaces the error as it does today.

---

## 3. Test updates (`tests/test_export.py`)

### 3.1 Delete

`test_to_html_pins_visjs_version_with_sri` (lines 103–127). The CDN URL, SRI hash, and `crossorigin="anonymous"` assertions no longer apply.

### 3.2 Extend

`test_to_html_contains_visjs` (lines 93–100) — append:

```python
assert '<script src="./vis-network.min.js"></script>' in content
assert 'unpkg.com' not in content
assert 'integrity=' not in content
assert 'crossorigin="anonymous"' not in content
```

### 3.3 Add: `test_to_html_emits_local_vis_js_asset`

- Call `to_html` with a `tmp` directory.
- Assert `(out.parent / "vis-network.min.js").exists()`.
- Assert its bytes equal the vendored copy (`(files("graphify") / "assets" / "vis-network.min.js").read_bytes()`).

### 3.4 Add: `test_to_html_skips_rewrite_when_asset_unchanged`

- First `to_html`, record `target.stat().st_mtime_ns`.
- Second `to_html` to the same directory.
- Assert `mtime_ns` unchanged.

### 3.5 Add: `test_to_html_rewrites_asset_when_vendored_changes`

- Monkeypatch `graphify.export._vendored_vis_js` to return `b"DIFFERENT"`.
- Call `to_html`.
- Assert `target.read_bytes() == b"DIFFERENT"`.
- Restore the original function.

### 3.6 Other tests

- `tests/test_pipeline.py:83` (`assert "vis-network" in html`) still passes — the literal string `vis-network` appears in the new `<script src="./vis-network.min.js">`. Optionally tighten to `'./vis-network.min.js'` for clarity.

---

## 4. Risks and boundaries

1. **Package data must actually ship.** A typo in `pyproject.toml` silently drops the file from the wheel; sdist readers will get a `FileNotFoundError` from `_vendored_vis_js()`. Release-time manual check (`zipfile -l`, `tar -tzf`) catches this.

2. **Repo weight.** One ~600KB binary is committed. Acceptable per the user's deferral to a future offline-installer plan; no action here.

3. **No CDN fallback.** Any environment where the vendored file is missing fails hard. This is intentional and matches the "硬切到本地" decision. The error message will be a `FileNotFoundError` from `importlib.resources` — explicit and fixable, not silent.

4. **Idempotent copy is correctness, not just optimization.** Build caches, `watch.py` re-runs, and Obsidian sync all care that `vis-network.min.js` is not rewritten on every run. The byte-equality check is essential.

5. **Out of scope (deferred to user):**
   - vis-network version upgrade flow.
   - Downloader / hash-verification script.
   - Offline-installer integration.
   - Any other CDN reference (this is the only one in the project).

---

## 5. Summary of touched files

| File | Change |
|---|---|
| `graphify/assets/vis-network.min.js` | **New** — vendored copy, ~600KB, committed. |
| `graphify/export.py` | Add `_VIS_NETWORK_FILENAME`, `_vendored_vis_js()`, `_emit_vis_js()`. Call `_emit_vis_js` before `write_text`. Replace script tag (lines 790–792). |
| `pyproject.toml` | Add `"assets/vis-network.min.js"` to `graphify` in `[tool.setuptools.package-data]`. |
| `tests/test_export.py` | Delete `test_to_html_pins_visjs_version_with_sri`. Extend `test_to_html_contains_visjs`. Add 3 new tests (3.3, 3.4, 3.5). |
| `tests/test_pipeline.py` | Optional: tighten `assert "vis-network"` to `'./vis-network.min.js'`. |

No changes to: `__main__.py`, `watch.py`, `serve.py`, or any other caller.
