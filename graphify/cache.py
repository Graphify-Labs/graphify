# per-file extraction cache - skip unchanged files on re-run
from __future__ import annotations

import atexit
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

# Output directory name — override with GRAPHIFY_OUT env var for worktrees or
# shared-output setups. Accepts a relative name ("graphify-out-feature") or an
# absolute path ("/shared/graphify-out"). Single source of truth in graphify.paths
# (#1423); re-exported here as _GRAPHIFY_OUT for the existing call sites.
from graphify.paths import GRAPHIFY_OUT as _GRAPHIFY_OUT

# AST cache entries are the output of graphify's own extractor code, so they
# are only valid for the version that wrote them: keying purely on file
# content means extractor fixes shipped in a new release keep serving stale
# pre-fix results. The AST cache is therefore namespaced by package version
# (cache/ast/v{version}/), with entries from other versions removed on first
# use. The semantic cache is deliberately NOT versioned — its entries are
# produced by the LLM from file contents, and invalidating them on every
# release would re-bill extraction for unchanged files.
try:
    from importlib.metadata import version as _pkg_version

    _EXTRACTOR_VERSION = _pkg_version("graphifyy")
except Exception:
    _EXTRACTOR_VERSION = "unknown"

# Version dirs already swept this process — cleanup runs once per (base, version).
_cleaned_ast_dirs: set[str] = set()


def _cleanup_stale_ast_entries(ast_base: Path, current_dir: Path) -> None:
    """Remove AST cache entries left behind by other graphify versions.

    Sweeps sibling ``v*/`` directories and unversioned ``*.json`` entries
    (the pre-versioning layout) under ``cache/ast/``. Best-effort: failures
    are ignored, stragglers are retried on the next run.
    """
    key = str(current_dir)
    if key in _cleaned_ast_dirs:
        return
    _cleaned_ast_dirs.add(key)
    if not ast_base.is_dir():
        return
    import shutil

    for child in ast_base.iterdir():
        if child == current_dir:
            continue
        try:
            if child.is_dir() and child.name.startswith("v"):
                shutil.rmtree(child, ignore_errors=True)
            elif child.suffix == ".json":
                child.unlink()
        except OSError:
            pass


# A frontmatter delimiter is a whole line of exactly three dashes (optional
# trailing whitespace). Substring checks like startswith("---") /
# find("\n---") also match `----` thematic breaks and `--- text` prose,
# silently dropping everything above them from the hash (#1259).
_FRONTMATTER_DELIM = re.compile(r"^---[ \t]*\r?$", re.MULTILINE)


def _body_content(content: bytes) -> bytes:
    """Strip YAML frontmatter from Markdown content, returning only the body."""
    text = content.decode(errors="replace")
    opener = _FRONTMATTER_DELIM.match(text)
    if opener is None:
        return content
    closer = _FRONTMATTER_DELIM.search(text, opener.end())
    if closer is None:
        return content
    # Slice right after the closing `---` (not after its line) so the output
    # stays byte-identical with the historical implementation for well-formed
    # frontmatter -- existing semantic-cache hashes must not churn.
    return text[closer.start() + 3:].encode()


# Stat-based index: maps absolute path → {size, mtime_ns, hash}.
# Loaded once per process, flushed via atexit. Skips full file reads when
# size+mtime_ns are unchanged — same trade-off as make(1).
# Correctness risks: `touch` causes a harmless extra re-hash; same-size edits
# within NFS second-resolution mtime have a 1-second window (same as make).
# Use `graphify extract --force` to bypass when needed.
_stat_index: dict[str, dict] = {}
_stat_index_root: Path | None = None
_stat_index_dirty: bool = False


def _stat_index_file(root: Path) -> Path:
    _out = Path(_GRAPHIFY_OUT)
    base = _out if _out.is_absolute() else Path(root).resolve() / _out
    return base / "cache" / "stat-index.json"


def _ensure_stat_index(root: Path) -> None:
    global _stat_index, _stat_index_root, _stat_index_dirty
    if _stat_index_root is not None:
        return
    _stat_index_root = Path(root).resolve()
    p = _stat_index_file(_stat_index_root)
    if p.exists():
        try:
            _stat_index = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            _stat_index = {}
    else:
        _stat_index = {}
    atexit.register(_flush_stat_index)


def _flush_stat_index() -> None:
    global _stat_index_dirty, _stat_index_root
    if not _stat_index_dirty or _stat_index_root is None:
        return
    p = _stat_index_file(_stat_index_root)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=p.parent, prefix="stat-index.", suffix=".tmp")
        try:
            os.write(fd, json.dumps(_stat_index, separators=(",", ":")).encode())
            os.close(fd)
            os.replace(tmp, p)
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                os.unlink(tmp)
            except OSError:
                pass
    except OSError:
        pass
    _stat_index_dirty = False


def _normalize_path(path: Path) -> Path:
    """Normalize path for consistent cache keys across Windows path spellings."""
    import sys
    if sys.platform != "win32":
        return path
    s = str(path)
    if s.startswith("\\\\?\\"):
        s = s[4:]  # strip extended-length prefix \\?\
    return Path(os.path.normcase(s))


def file_hash(path: Path, root: Path = Path(".")) -> str:
    """SHA256 of file contents + path relative to root.

    Uses a stat-based fastpath (size + mtime_ns) to skip full reads when the
    file hasn't changed. Falls through to full SHA256 on first encounter or
    when stat changes. Index is flushed atomically at process exit.

    Using a relative path (not absolute) makes cache entries portable across
    machines and checkout directories, so shared caches and CI work correctly.
    Falls back to the resolved absolute path if the file is outside root.

    For Markdown files (.md), only the body below the YAML frontmatter is hashed,
    so metadata-only changes (e.g. reviewed, status, tags) do not invalidate the cache.
    """
    global _stat_index_dirty
    p = _normalize_path(Path(path))
    root = _normalize_path(Path(root))
    if not p.is_file():
        raise IsADirectoryError(f"file_hash requires a file, got: {p}")

    _ensure_stat_index(root)
    abs_key = str(p.resolve())
    st: "os.stat_result | None" = None
    try:
        st = p.stat()
        entry = _stat_index.get(abs_key)
        if (entry
                and entry.get("size") == st.st_size
                and entry.get("mtime_ns") == st.st_mtime_ns):
            return entry["hash"]
    except OSError:
        pass

    raw = p.read_bytes()
    content = _body_content(raw) if p.suffix.lower() == ".md" else raw
    h = hashlib.sha256()
    h.update(content)
    h.update(b"\x00")
    try:
        rel = p.resolve().relative_to(Path(root).resolve())
        h.update(rel.as_posix().lower().encode())
    except ValueError:
        h.update(p.resolve().as_posix().lower().encode())
    digest = h.hexdigest()

    if st is not None:
        _stat_index[abs_key] = {"size": st.st_size, "mtime_ns": st.st_mtime_ns, "hash": digest}
        _stat_index_dirty = True

    return digest


def _relativize_source_files_in(payload: dict, root: Path) -> None:
    """Mutate ``payload`` to rewrite absolute ``source_file`` fields as
    forward-slash relative paths from ``root``.

    Mirror of :func:`graphify.watch._relativize_source_files` so cached
    extraction fragments persist in portable form (#777). Already-relative
    fields and out-of-root paths pass through unchanged.

    Only ``root`` is resolved — ``source_file`` itself is relativized
    symbolically so in-root symlinks keep their original name rather than
    pointing at the resolved target. Same reasoning as
    :func:`graphify.detect._to_relative_for_storage`.
    """
    try:
        root_resolved = Path(root).resolve()
    except OSError:
        return
    for bucket in ("nodes", "edges", "hyperedges"):
        for item in payload.get(bucket, []):
            if not isinstance(item, dict):
                continue
            source = item.get("source_file")
            if not source:
                continue
            sp = Path(source)
            if not sp.is_absolute():
                continue
            try:
                rel = os.path.relpath(sp, root_resolved)
            except (ValueError, OSError):
                continue  # out-of-root (e.g. Windows cross-drive)
            if rel == ".." or rel.startswith(".." + os.sep) or rel.startswith("../"):
                continue  # escaped root — keep absolute
            item["source_file"] = rel.replace(os.sep, "/")


def _absolutize_source_files_in(payload: dict, root: Path) -> None:
    """Inverse of :func:`_relativize_source_files_in`.

    Re-anchor relative ``source_file`` fields against ``root`` so callers
    that load a cached fragment see the same absolute-path shape that a
    fresh in-process extraction would produce. Legacy cache entries with
    absolute ``source_file`` values pass through unchanged.
    """
    try:
        root_resolved = Path(root).resolve()
    except OSError:
        return
    for bucket in ("nodes", "edges", "hyperedges"):
        for item in payload.get(bucket, []):
            if not isinstance(item, dict):
                continue
            source = item.get("source_file")
            if not source:
                continue
            sp = Path(source)
            if sp.is_absolute():
                continue
            try:
                item["source_file"] = str(root_resolved / sp)
            except (TypeError, OSError):
                continue


def cache_dir(root: Path = Path("."), kind: str = "ast") -> Path:
    """Returns the cache directory for ``kind`` - creates it if needed.

    kind is "ast" or "semantic". Separate subdirectories prevent semantic cache
    entries from overwriting AST cache entries for the same source_file (#582).

    AST entries live in graphify-out/cache/ast/v{version}/ — namespaced by
    graphify version because they depend on extractor code, not just file
    contents. Semantic entries live unversioned in graphify-out/cache/semantic/
    (re-extraction costs LLM calls).
    """
    _out = Path(_GRAPHIFY_OUT)
    base = _out if _out.is_absolute() else Path(root).resolve() / _out
    d = base / "cache" / kind
    if kind == "ast":
        d = d / f"v{_EXTRACTOR_VERSION}"
        _cleanup_stale_ast_entries(d.parent, d)
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_cached(path: Path, root: Path = Path("."), kind: str = "ast") -> dict | None:
    """Return cached extraction for this file if hash matches, else None.

    Cache key: SHA256 of file contents.
    Cache value: stored as graphify-out/cache/{kind}/{hash}.json (AST entries
    under the per-version subdirectory, see :func:`cache_dir`).

    AST entries written by other graphify versions — including the legacy
    flat cache/ layout (pre-0.5.3) and the unversioned cache/ast/ layout —
    are deliberately not consulted: they were produced by a different
    extractor and may be stale.
    Returns None if no cache entry or file has changed.
    """
    try:
        h = file_hash(path, root)
    except OSError:
        return None
    entry = cache_dir(root, kind) / f"{h}.json"
    if entry.exists():
        try:
            result = json.loads(entry.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        # Re-anchor relative source_file fields so callers see the same
        # absolute-path shape that a fresh in-process extraction produces
        # (#777). Legacy entries with absolute source_file pass through.
        if isinstance(result, dict):
            _absolutize_source_files_in(result, root)
        return result
    return None


def save_cached(path: Path, result: dict, root: Path = Path("."), kind: str = "ast") -> None:
    """Save extraction result for this file.

    Stores as graphify-out/cache/{kind}/{hash}.json where hash = SHA256 of current file contents.
    result should be a dict with 'nodes' and 'edges' lists.

    No-ops if `path` is not a regular file. Subagent-produced semantic fragments
    occasionally carry a directory path in `source_file`; skipping them prevents
    IsADirectoryError from aborting the whole batch.
    """
    p = Path(path)
    if not p.is_file():
        return
    # Relativize source_file fields against ``root`` before write so the
    # cache file on disk is portable across machines and checkout
    # directories (#777). The cache key is content-hashed so lookup is
    # already path-independent; this fixes the embedded path leak.
    #
    # Serialize a relativized copy rather than mutating the caller's dict —
    # downstream pipeline steps (notably extract.py's AST prefix remap, which
    # looks up Path(source_file).resolve() in a prefix table) depend on the
    # source_file field's original absolute form. Mutating the input here would
    # silently break those remaps on the first extraction pass.
    on_disk = result
    if isinstance(result, dict) and any(result.get(k) for k in ("nodes", "edges", "hyperedges")):
        import copy as _copy
        on_disk = _copy.deepcopy(result)
        _relativize_source_files_in(on_disk, root)
    h = file_hash(p, root)
    target_dir = cache_dir(root, kind)
    entry = target_dir / f"{h}.json"
    fd, tmp_path = tempfile.mkstemp(dir=target_dir, prefix=f"{h}.", suffix=".tmp")
    try:
        os.write(fd, json.dumps(on_disk).encode())
        os.close(fd)
        try:
            os.replace(tmp_path, entry)
        except PermissionError:
            # Windows: os.replace can fail with WinError 5 if the target is
            # briefly locked. Fall back to copy-then-delete.
            import shutil
            shutil.copy2(tmp_path, entry)
            os.unlink(tmp_path)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def cached_files(root: Path = Path(".")) -> set[str]:
    """Return set of file hashes that have a valid cache entry (any kind)."""
    base = Path(root).resolve() / _GRAPHIFY_OUT / "cache"
    hashes: set[str] = set()
    # Legacy flat entries
    if base.is_dir():
        hashes.update(p.stem for p in base.glob("*.json"))
    # Namespaced entries (ast/ recursively, covering per-version subdirs)
    for kind, pattern in (("ast", "**/*.json"), ("semantic", "*.json")):
        d = base / kind
        if d.is_dir():
            hashes.update(p.stem for p in d.glob(pattern))
    return hashes


def clear_cache(root: Path = Path(".")) -> None:
    """Delete all cache entries (ast/, semantic/, and legacy flat entries)."""
    base = Path(root).resolve() / _GRAPHIFY_OUT / "cache"
    # Legacy flat entries
    if base.is_dir():
        for f in base.glob("*.json"):
            f.unlink()
    # Namespaced entries (ast/ recursively, covering per-version subdirs)
    for kind, pattern in (("ast", "**/*.json"), ("semantic", "*.json")):
        d = base / kind
        if d.is_dir():
            for f in d.glob(pattern):
                f.unlink()


def check_semantic_cache(
    files: list[str],
    root: Path = Path("."),
) -> tuple[list[dict], list[dict], list[dict], list[str]]:
    """Check semantic extraction cache for a list of absolute file paths.

    Returns (cached_nodes, cached_edges, cached_hyperedges, uncached_files).
    Uncached files need Claude extraction; cached files are merged directly.
    """
    cached_nodes: list[dict] = []
    cached_edges: list[dict] = []
    cached_hyperedges: list[dict] = []
    uncached: list[str] = []

    for fpath in files:
        p = Path(fpath)
        if not p.is_absolute():
            p = Path(root) / p
        result = load_cached(p, root, kind="semantic")
        if result is not None:
            cached_nodes.extend(result.get("nodes", []))
            cached_edges.extend(result.get("edges", []))
            cached_hyperedges.extend(result.get("hyperedges", []))
        else:
            uncached.append(fpath)

    return cached_nodes, cached_edges, cached_hyperedges, uncached


def save_semantic_cache(
    nodes: list[dict],
    edges: list[dict],
    hyperedges: list[dict] | None = None,
    root: Path = Path("."),
) -> int:
    """Save semantic extraction results to cache, keyed by source_file.

    Groups nodes and edges by source_file, then saves one cache entry per file
    under cache/semantic/ (separate from AST entries in cache/ast/) to prevent
    hash-key collisions (#582).
    Returns the number of files cached.
    """
    from collections import defaultdict

    by_file: dict[str, dict] = defaultdict(lambda: {"nodes": [], "edges": [], "hyperedges": []})
    for n in nodes:
        src = n.get("source_file", "")
        if src:
            by_file[src]["nodes"].append(n)
    for e in edges:
        src = e.get("source_file", "")
        if src:
            by_file[src]["edges"].append(e)
    for h in (hyperedges or []):
        src = h.get("source_file", "")
        if src:
            by_file[src]["hyperedges"].append(h)

    saved = 0
    for fpath, result in by_file.items():
        p = Path(fpath)
        if not p.is_absolute():
            p = Path(root) / p
        if p.is_file():
            save_cached(p, result, root, kind="semantic")
            saved += 1
    return saved
