Add Two factor authentication for pull request

# Security Audit — graphify

**Auditor:** Pushkar  
**Date:** 2026-07-21  
**Scope:** Static analysis of `graphify/` Python source

---

## Finding 1 — Cypher Injection via Unsanitised Node Labels and Relationship Types

**File:** `graphify/exporters/graphdb.py` (lines 55–75)  
**Severity:** High

The `push_to_neo4j` and `push_to_falkordb` functions construct Cypher queries by interpolating label and relationship-type strings directly into f-string templates:

```python
session.run(
    f"MERGE (n:{ftype} {{id: $id}}) SET n += $props",   # ftype injected directly
    ...
)
session.run(
    f"MATCH (a {{id: $src}}), (b {{id: $tgt}}) "
    f"MERGE (a)-[r:{rel}]->(b) SET r += $props",        # rel injected directly
    ...
)
```

Although `_safe_label` and `_safe_rel` strip most special characters, the sanitisation is applied to data that originates from `G.nodes` / `G.edges` attributes, which are populated from arbitrary source files. A node with `file_type = "A} DETACH DELETE n //"` could survive a weak regex and produce a destructive query.

**Fix:** Enforce a strict allowlist on `_safe_label` / `_safe_rel` (letters, digits, underscore only, max 64 chars) and raise an error — rather than silently coercing — when the sanitised value differs from the input:

```python
def _safe_label(label: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_]", "", label)[:64]
    if not sanitized:
        return "Entity"
    if sanitized != label:
        raise ValueError(f"Unsafe node label rejected: {label!r}")
    return sanitized
```

---

## Finding 2 — Password Exposed in Process Listing via `--password` CLI Flag

**File:** `graphify/cli.py` (line 2101), `graphify/exporters/graphdb.py`  
**Severity:** High

The `graphify export neo4j --push URI --password <pass>` and equivalent FalkorDB flag pass database credentials as a command-line argument. On any multi-user Linux/macOS system `ps aux` reveals the plaintext password to all local users. The help text acknowledges the risk ("or set `NEO4J_PASSWORD` instead") but no runtime warning is emitted when the insecure flag is used.

**Fix:** Emit a warning at runtime when `--password` is supplied on the command line, and prefer the environment variable path:

```python
if push_password:
    import warnings
    warnings.warn(
        "Passing --password on the command line exposes credentials in process "
        "listings. Use the NEO4J_PASSWORD / FALKORDB_PASSWORD environment variable instead.",
        stacklevel=2,
    )
```

Consider deprecating the flag in a future release in favour of env-var-only auth.

---

## Finding 3 — Predictable RNG Seed in MinHash Makes Deduplication Bypassable

**File:** `graphify/_minhash.py` (line 29)  
**Severity:** Medium

```python
rng = np.random.RandomState(1)   # hardcoded seed
```

MinHash security relies on the hash functions being unknown to an adversary. With a public, hardcoded seed of `1`, an attacker who can influence what files are fed into graphify can craft two semantically different files that produce identical MinHash signatures, forcing deduplication to silently drop one. This is relevant when graphify runs in automated CI pipelines processing untrusted repositories.

**Fix:** Derive the seed from `os.urandom` so the functions are unpredictable per run:

```python
import os, struct
seed = struct.unpack("<I", os.urandom(4))[0]
rng = np.random.RandomState(seed)
```

If reproducibility is needed for testing, accept the seed as an explicit parameter with no default, making the insecure usage opt-in rather than the default.

---

## Finding 4 — Temporary Files with `delete=False` Risk Sensitive Data Leakage on Exception

**File:** `graphify/google_workspace.py` (lines 184, 197, 212)  
**Severity:** Medium

```python
with tempfile.NamedTemporaryFile("w+b", suffix=".md", delete=False, dir=out_dir) as tmp:
    ...
```

Three export paths use `delete=False` and write exported Google Workspace content (documents, spreadsheets, slides) to `out_dir`. If an exception is raised inside the `with` block or at any later processing step, the temporary file is left on disk with its full contents and no cleanup guarantee.

**Fix:** Wrap each block in a `try/finally` to guarantee removal on failure:

```python
tmp_path = None
try:
    with tempfile.NamedTemporaryFile("w+b", suffix=".md", delete=False, dir=out_dir) as tmp:
        tmp_path = Path(tmp.name)
        # ... write content ...
    tmp_path.rename(final_path)
    tmp_path = None
finally:
    if tmp_path and tmp_path.exists():
        tmp_path.unlink(missing_ok=True)
```

---

## Finding 5 — Dynamically Constructed Python Code Executed in git Hook Launcher

**File:** `graphify/hooks.py` (lines ~200–230)  
**Severity:** Medium

The `_detached_launch` function embeds a caller-supplied `rebuild_body` string directly into a Python launcher template and hands it to `subprocess.Popen` via `-c`:

```python
launcher = _LAUNCHER_TEMPLATE.replace("__REBUILD_BODY__", rebuild_body)
return '"$GRAPHIFY_PYTHON" -c "' + launcher + '"\n'
```

The current callers are safe module-level constants. However, the function's signature imposes no constraint on what `rebuild_body` may contain. Any future code path that passes externally influenced content (e.g. a branch name or file path read from git output) would result in arbitrary code execution at git-hook time.

**Fix:** Guard the function with an allowlist of approved constants to turn a latent injection surface into a hard runtime error if the constraint is ever violated:

```python
_ALLOWED_REBUILD_BODIES = frozenset({_REBUILD_BODY_CHECKOUT, _REBUILD_BODY_COMMIT})

def _detached_launch(rebuild_body: str) -> str:
    if rebuild_body not in _ALLOWED_REBUILD_BODIES:
        raise ValueError(
            "_detached_launch: rebuild_body must be a pre-approved module-level constant"
        )
    ...
```

---

## Summary

| # | Finding | File | Severity |
|---|---------|------|----------|
| 1 | Cypher injection via node labels / relationship types | `exporters/graphdb.py` | **High** |
| 2 | Database password exposed in process listing | `cli.py` | **High** |
| 3 | Hardcoded MinHash RNG seed enables collision crafting | `_minhash.py` | Medium |
| 4 | Leaked temporary files on exception in GWS export | `google_workspace.py` | Medium |
| 5 | Unconstrained dynamic Python code in git hook launcher | `hooks.py` | Medium |