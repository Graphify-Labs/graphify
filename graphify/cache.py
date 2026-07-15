# per-file extraction cache - skip unchanged files on re-run
from __future__ import annotations

import atexit
import hashlib
import json
import os
import re
import tempfile
import warnings
from collections.abc import Iterable
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


def _ensure_stat_index(root: Path, cache_root: "Path | None" = None) -> None:
    global _stat_index, _stat_index_root, _stat_index_dirty
    if _stat_index_root is not None:
        return
    # The stat index only determines the cache FILE location (entry keys are
    # absolute paths), so honoring an explicit cache_root keeps detect()'s
    # word-count cache under the requested --out dir instead of polluting the
    # scanned corpus with a stray graphify-out/ (#1747).
    _stat_index_root = Path(cache_root if cache_root is not None else root).resolve()
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


def file_hash(path: Path, root: Path = Path("."), cache_root: "Path | None" = None) -> str:
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

    # The stat index is a cache artifact, so it must follow the cache location
    # (cache_root), not the key-anchor root — otherwise it leaves a stray
    # graphify-out/cache/stat-index.json inside the analyzed source tree even when
    # the AST cache itself is redirected to CWD (#1774 completion).
    _ensure_stat_index(root, cache_root=cache_root)
    abs_key = str(p.resolve())
    st: "os.stat_result | None" = None
    try:
        st = p.stat()
        entry = _stat_index.get(abs_key)
        if (entry
                and entry.get("hash") is not None  # word-count-only entries carry no hash
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
        entry = _stat_index.get(abs_key)
        if (entry is not None
                and entry.get("size") == st.st_size
                and entry.get("mtime_ns") == st.st_mtime_ns):
            entry["hash"] = digest  # preserve a co-located word_count
        else:
            _stat_index[abs_key] = {"size": st.st_size, "mtime_ns": st.st_mtime_ns, "hash": digest}
        _stat_index_dirty = True

    return digest


def cached_word_count(path: Path, root: Path, compute, cache_root: "Path | None" = None) -> int:
    """Word count with the same (size, mtime_ns) stat-fastpath cache as
    :func:`file_hash`, persisted in the shared stat index.

    ``detect()`` counts words in every PDF/docx/text file to size the corpus,
    which re-opens and re-parses every binary on each run — minutes on a large
    docs corpus even when only a handful of files changed (#1656). This caches
    the count against the file's stat signature so an unchanged file is counted
    once and read from the index thereafter. ``compute(path)`` produces the
    count on a miss. A file that can't be stat'd (e.g. a Windows long path the
    index normalization can't reach) simply recomputes and isn't cached —
    correct, just not accelerated.
    """
    global _stat_index_dirty
    p = _normalize_path(Path(path))
    root = _normalize_path(Path(root))
    _ensure_stat_index(root, cache_root=cache_root)
    abs_key = str(p.resolve())
    st: "os.stat_result | None" = None
    try:
        st = p.stat()
        entry = _stat_index.get(abs_key)
        if (entry
                and entry.get("size") == st.st_size
                and entry.get("mtime_ns") == st.st_mtime_ns
                and "word_count" in entry):
            return entry["word_count"]
    except OSError:
        pass

    wc = compute(Path(path))

    if st is not None:
        entry = _stat_index.get(abs_key)
        if (entry
                and entry.get("size") == st.st_size
                and entry.get("mtime_ns") == st.st_mtime_ns):
            entry["word_count"] = wc  # augment the existing hash entry in place
        else:
            _stat_index[abs_key] = {
                "size": st.st_size, "mtime_ns": st.st_mtime_ns, "word_count": wc,
            }
        _stat_index_dirty = True

    return wc


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
    # raw_calls (#: Pascal/Delphi cross-file inherited-call resolution) carries
    # source_file the same way nodes/edges/hyperedges do, so it needs the same
    # portable-path treatment for cache entries to round-trip correctly across
    # machines/checkout directories.
    for bucket in ("nodes", "edges", "hyperedges", "raw_calls"):
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
    for bucket in ("nodes", "edges", "hyperedges", "raw_calls"):
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


def load_cached(path: Path, root: Path = Path("."), kind: str = "ast",
                cache_root: Path | None = None) -> dict | None:
    """Return cached extraction for this file if hash matches, else None.

    Cache key: SHA256 of file contents.
    Cache value: stored as graphify-out/cache/{kind}/{hash}.json (AST entries
    under the per-version subdirectory, see :func:`cache_dir`).

    ``root`` anchors the content-hash key and source_file relativization (it
    must stay the inferred common parent so keys remain portable). ``cache_root``
    decouples *where* the cache directory lives from that anchor — the cache is
    an output and must not land inside a read-only/analyzed source tree (#1774).
    When ``cache_root`` is None the location falls back to ``root`` (unchanged
    behavior for existing callers).

    AST entries written by other graphify versions — including the legacy
    flat cache/ layout (pre-0.5.3) and the unversioned cache/ast/ layout —
    are deliberately not consulted: they were produced by a different
    extractor and may be stale.
    Returns None if no cache entry or file has changed.
    """
    location = cache_root if cache_root is not None else root
    try:
        h = file_hash(path, root, cache_root=cache_root)
    except OSError:
        return None
    entry = cache_dir(location, kind) / f"{h}.json"
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


def save_cached(path: Path, result: dict, root: Path = Path("."), kind: str = "ast",
                cache_root: Path | None = None) -> None:
    """Save extraction result for this file.

    Stores as graphify-out/cache/{kind}/{hash}.json where hash = SHA256 of current file contents.
    result should be a dict with 'nodes' and 'edges' lists.

    ``root`` anchors the content-hash key and source_file relativization;
    ``cache_root`` (when given) is where the cache directory is written, decoupled
    from ``root`` so the cache never lands inside the analyzed source tree (#1774).

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
    if isinstance(result, dict) and any(result.get(k) for k in ("nodes", "edges", "hyperedges", "raw_calls")):
        import copy as _copy
        on_disk = _copy.deepcopy(result)
        _relativize_source_files_in(on_disk, root)
    h = file_hash(p, root, cache_root=cache_root)
    location = cache_root if cache_root is not None else root
    target_dir = cache_dir(location, kind)
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


def prune_semantic_cache(root: Path, live_hashes: set[str]) -> int:
    """Remove orphaned semantic cache entries, returning the count pruned.

    The semantic cache is content-hash-keyed (``{file_hash}.json`` under
    ``cache/semantic/``) and deliberately UNVERSIONED — entries are produced by
    the LLM from file contents, so invalidating them on every release would
    re-bill extraction. Because it is unversioned it is also never swept by the
    AST version-cleanup, so every content change or file deletion leaves a
    permanent orphan entry that accumulates unbounded.

    This sweeps ``cache/semantic/*.json`` and deletes any entry whose stem (the
    content hash) is not in ``live_hashes`` — the hashes of the current live
    document set. ``*.tmp`` atomic-write temporaries are skipped, and only this
    directory is touched (never ``cache/ast/**`` or anything else). The
    unversioned design is preserved: we prune by liveness, not by version.

    Best-effort, mirroring :func:`_cleanup_stale_ast_entries`: each unlink is
    wrapped in ``try/except OSError`` and a failure is ignored. The worst-case
    failure mode is benign — a surviving orphan costs only one re-extraction of
    one doc on a future run, never incorrect output.
    """
    _out = Path(_GRAPHIFY_OUT)
    base = _out if _out.is_absolute() else Path(root).resolve() / _out
    semantic_dir = base / "cache" / "semantic"
    if not semantic_dir.is_dir():
        return 0
    pruned = 0
    for entry in semantic_dir.glob("*.json"):
        if entry.stem in live_hashes:
            continue
        try:
            entry.unlink()
            pruned += 1
        except OSError:
            pass
    return pruned


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
    merge_existing: bool = False,
    allowed_source_files: Iterable[str | Path] | None = None,
) -> int:
    """Save semantic extraction results to cache, keyed by source_file.

    Groups nodes and edges by source_file, then saves one cache entry per file
    under cache/semantic/ (separate from AST entries in cache/ast/) to prevent
    hash-key collisions (#582).

    When ``merge_existing`` is True, any already-cached entry for a file is
    unioned with the new results before saving instead of being overwritten.
    This lets callers checkpoint incrementally (e.g. once per chunk) without
    dropping a prior slice of a large file that was split across chunks.

    When ``allowed_source_files`` is provided, only those files may be used as
    cache-write keys. Semantic nodes can legitimately mention another corpus
    file, but a model must not be able to replace that file's complete cache
    entry unless the file was part of the current extraction batch (#1757).
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

    root_path = Path(root).resolve()

    def resolved_source_path(value: str | Path) -> Path:
        path = Path(value)
        if not path.is_absolute():
            path = root_path / path
        try:
            return path.resolve()
        except (OSError, RuntimeError):
            # Keep the cache write best-effort for inaccessible paths or a
            # symlink loop emitted by an untrusted semantic result.
            return Path(os.path.abspath(path))

    allowed_paths = None
    if allowed_source_files is not None:
        allowed_paths = {resolved_source_path(path) for path in allowed_source_files}

    saved = 0
    for fpath, result in by_file.items():
        p = resolved_source_path(fpath)
        if p.is_file():
            if allowed_paths is not None and p not in allowed_paths:
                warnings.warn(
                    "semantic cache skipped out-of-scope source_file "
                    f"{fpath!r}; the file was not dispatched for extraction",
                    RuntimeWarning,
                    stacklevel=2,
                )
                continue
            if merge_existing:
                prev = load_cached(p, root, kind="semantic")
                if prev:
                    result = {
                        "nodes": (prev.get("nodes", []) or []) + result["nodes"],
                        "edges": (prev.get("edges", []) or []) + result["edges"],
                        "hyperedges": (prev.get("hyperedges", []) or []) + result["hyperedges"],
                    }
            save_cached(p, result, root, kind="semantic")
            saved += 1
    return saved
