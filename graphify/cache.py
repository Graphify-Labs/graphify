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


# Semantic cache entries are LLM output, so they depend on the extraction prompt
# that produced them, not just on file contents. Keying purely on content means a
# release that changes the prompt keeps replaying entries from the older prompt on
# every unchanged file, silently mixing extraction vintages in one graph (#1939).
# Versioning them by package version (as the AST cache does) would re-bill LLM
# extraction on every patch release — the reason #1252 deliberately left them
# unversioned. Fingerprinting the prompt itself keeps both properties: entries
# survive releases that don't touch the prompt, and invalidate only when it
# actually changed. Entries live under cache/semantic/p{fingerprint}/ when the
# caller supplies its prompt; callers that don't keep the historical flat layout.
_PROMPT_FP_LEN = 12

# Count of pre-fingerprint (flat-layout) entries served this process, so
# check_semantic_cache can report N to the user (#1939).
_legacy_semantic_hits = 0

# Prompt-file fingerprints already computed, keyed by (path, size, mtime_ns) —
# the same stat signature the hash index uses. check_semantic_cache resolves the
# prompt once per FILE in the corpus, so without this a 500-doc run re-reads and
# re-hashes the same spec 500 times (and warns 500 times when it is unreadable).
_prompt_fp_cache: dict[tuple, str] = {}


def prompt_fingerprint(prompt: "str | Path") -> str:
    """Return a short stable fingerprint of an extraction prompt.

    ``prompt`` is either the prompt text itself (the Python extraction path owns
    its system prompt, :func:`graphify.llm._extraction_system`) or a Path to the
    prompt file an agent loaded (the skill path's
    ``references/extraction-spec.md``).

    Line endings and trailing whitespace are normalized before hashing: the same
    spec file checked out with CRLF on Windows must not fingerprint differently
    from the LF checkout that wrote the cache, or every Windows run would look
    like a prompt change and re-bill extraction.
    """
    if isinstance(prompt, Path):
        text = prompt.read_text(encoding="utf-8", errors="replace")
    else:
        text = prompt
    normalized = "\n".join(
        line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ).strip()
    return hashlib.sha256(normalized.encode()).hexdigest()[:_PROMPT_FP_LEN]


def _resolve_prompt_fp(prompt: "str | Path | None" = None,
                       prompt_file: "str | Path | None" = None) -> str | None:
    """Fingerprint the caller's extraction prompt, or None when it supplied none.

    ``prompt`` is prompt TEXT; ``prompt_file`` is a path to a file CONTAINING the
    prompt. They are separate parameters rather than one overloaded argument
    because the skill-driven callers are markdown snippets an agent copies with a
    path substituted in — passing that path as ``prompt`` would hash the path
    string itself, yielding a fingerprint that is stable, plausible, and tracks
    nothing about the prompt. A silent wrong fingerprint is the exact failure
    class #1939 is about, so the two are not inferred from each other.

    Best-effort: an unreadable ``prompt_file`` falls back to the flat, unattributed
    layout rather than failing the run — a cache is never worth aborting an
    extraction over. It warns rather than falling back quietly, because that
    fallback silently restores the very behavior this fixes, and the skill-side
    caller substitutes this path by hand.
    """
    memo_key = None
    if prompt_file is not None:
        prompt = Path(prompt_file)
        try:
            st = prompt.stat()
            memo_key = (str(prompt), st.st_size, st.st_mtime_ns)
            if memo_key in _prompt_fp_cache:
                return _prompt_fp_cache[memo_key]
        except OSError:
            pass  # unreadable — fall through to the warning below
    if prompt is None:
        return None
    try:
        fp = prompt_fingerprint(prompt)
        if memo_key is not None:
            _prompt_fp_cache[memo_key] = fp
        return fp
    except (OSError, UnicodeError) as exc:
        warnings.warn(
            f"could not read extraction prompt {str(prompt)!r} ({exc}); semantic cache "
            "entries cannot be attributed to a prompt version and fall back to the "
            "unversioned layout, so this run may replay entries from an older "
            "extraction prompt (#1939).",
            RuntimeWarning,
            stacklevel=3,
        )
        return None


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
# `graphify extract --force` / `graphify update --force` (or GRAPHIFY_FORCE=1)
# skip the cache reads and re-dispatch everything when needed (#1894).
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
    resolved = p.resolve()
    abs_key = str(resolved)
    # The salt is the path component that enters the digest (relative to root, or
    # the absolute-path fallback). The stat-index memo MUST be keyed by it too:
    # the same file hashed under two different roots yields two different digests
    # (this happens within one `--out` run), and a memo keyed only by absolute
    # path served whichever was computed first — making file_hash order-dependent
    # and poisoning the persisted stat-index across runs (#1989). Store one digest
    # per salt so alternating roots don't force re-reads.
    try:
        salt = resolved.relative_to(Path(root).resolve()).as_posix().lower()
    except ValueError:
        salt = resolved.as_posix().lower()

    st: "os.stat_result | None" = None
    try:
        st = p.stat()
        entry = _stat_index.get(abs_key)
        if (isinstance(entry, dict)
                and entry.get("size") == st.st_size
                and entry.get("mtime_ns") == st.st_mtime_ns):
            hashes = entry.get("hashes")
            if isinstance(hashes, dict):
                cached = hashes.get(salt)
                if isinstance(cached, str):
                    return cached
            # Legacy single-digest entries ("hash") don't record which salt
            # produced them, so they are never trusted (#1989) — recompute once.
    except OSError:
        pass

    raw = p.read_bytes()
    content = _body_content(raw) if p.suffix.lower() == ".md" else raw
    h = hashlib.sha256()
    h.update(content)
    h.update(b"\x00")
    h.update(salt.encode())
    digest = h.hexdigest()

    if st is not None:
        entry = _stat_index.get(abs_key)
        if (isinstance(entry, dict)
                and entry.get("size") == st.st_size
                and entry.get("mtime_ns") == st.st_mtime_ns):
            hashes = entry.get("hashes")
            if not isinstance(hashes, dict):
                hashes = {}
                entry["hashes"] = hashes
            hashes[salt] = digest       # preserve a co-located word_count / other salts
            entry.pop("hash", None)     # retire the un-salted legacy digest
        else:
            _stat_index[abs_key] = {"size": st.st_size, "mtime_ns": st.st_mtime_ns,
                                    "hashes": {salt: digest}}
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


def cache_dir(root: Path = Path("."), kind: str = "ast",
              prompt_fp: str | None = None) -> Path:
    """Returns the cache directory for ``kind`` - creates it if needed.

    kind is "ast", "semantic", or a mode-namespaced semantic kind such as
    "semantic-deep" (#1894). Separate subdirectories prevent semantic cache
    entries from overwriting AST cache entries for the same source_file (#582).

    AST entries live in graphify-out/cache/ast/v{version}/ — namespaced by
    graphify version because they depend on extractor code, not just file
    contents. Semantic entries are still NOT version-namespaced (re-extraction
    costs LLM calls, #1252): they live in graphify-out/cache/semantic/, with
    deep-mode entries beside them in graphify-out/cache/semantic-deep/.

    ``prompt_fp`` (semantic kinds only) adds a p{fingerprint}/ subdirectory so
    entries are attributed to the extraction prompt that produced them (#1939).
    Omitting it yields the historical flat layout, where entries of unknown
    vintage live.
    """
    _out = Path(_GRAPHIFY_OUT)
    base = _out if _out.is_absolute() else Path(root).resolve() / _out
    d = base / "cache" / kind
    if kind == "ast":
        d = d / f"v{_EXTRACTOR_VERSION}"
        _cleanup_stale_ast_entries(d.parent, d)
    elif prompt_fp:
        d = d / f"p{prompt_fp}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_cached(path: Path, root: Path = Path("."), kind: str = "ast",
                cache_root: Path | None = None, prompt: "str | Path | None" = None,
                prompt_file: "str | Path | None" = None,
                allow_legacy: bool = True,
                allow_partial: bool = False) -> dict | None:
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

    ``prompt`` (semantic kinds) is the extraction prompt — text, or a Path to
    the prompt file — that the caller is about to extract with. It selects the
    p{fingerprint}/ namespace, so an entry produced by a different prompt is a
    miss rather than a silent stale hit (#1939). When it is given and the
    fingerprinted namespace misses, ``allow_legacy`` (default True) falls back
    to a flat-layout entry: those predate fingerprinting, so their vintage is
    unknowable — they are served rather than re-billed, and the hit is counted
    so :func:`check_semantic_cache` can report N to the user. Callers that must
    not mix vintages within one entry (see :func:`save_semantic_cache`'s
    ``merge_existing``) pass allow_legacy=False.
    Returns None if no cache entry or file has changed.
    """
    global _legacy_semantic_hits
    location = cache_root if cache_root is not None else root
    try:
        h = file_hash(path, root, cache_root=cache_root)
    except OSError:
        return None
    prompt_fp = _resolve_prompt_fp(prompt, prompt_file)
    entry = cache_dir(location, kind, prompt_fp) / f"{h}.json"
    legacy_hit = False
    if prompt_fp and not entry.exists() and allow_legacy:
        legacy = cache_dir(location, kind) / f"{h}.json"
        if legacy.exists():
            entry, legacy_hit = legacy, True
    if entry.exists():
        try:
            result = json.loads(entry.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        # A ``partial`` entry was produced from a truncated LLM response and
        # covers only part of the file's symbols. Serving it as authoritative
        # would return the incomplete node set forever until the file is
        # re-extracted. Treat it as a cache MISS (the normal read path) so the
        # file is re-dispatched and retried. Self-heals: a later complete
        # extraction overwrites the same content-hash key with a non-partial
        # entry. ``allow_partial`` is the one exception — the merge_existing
        # checkpoint peeks at a partial prev so it can accumulate a file's slices
        # across chunks without losing the truncated one (it stays partial).
        if not allow_partial and isinstance(result, dict) and result.get("partial"):
            return None
        if legacy_hit:
            _legacy_semantic_hits += 1
        # Re-anchor relative source_file fields so callers see the same
        # absolute-path shape that a fresh in-process extraction produces
        # (#777). Legacy entries with absolute source_file pass through.
        if isinstance(result, dict):
            _absolutize_source_files_in(result, root)
        return result
    return None


def save_cached(path: Path, result: dict, root: Path = Path("."), kind: str = "ast",
                cache_root: Path | None = None, prompt: "str | Path | None" = None,
                prompt_file: "str | Path | None" = None) -> None:
    """Save extraction result for this file.

    Stores as graphify-out/cache/{kind}/{hash}.json where hash = SHA256 of current file contents.
    result should be a dict with 'nodes' and 'edges' lists.

    ``root`` anchors the content-hash key and source_file relativization;
    ``cache_root`` (when given) is where the cache directory is written, decoupled
    from ``root`` so the cache never lands inside the analyzed source tree (#1774).

    ``prompt`` (semantic kinds) is the extraction prompt that produced ``result``
    — text, or a Path to the prompt file. It stamps the entry into the
    p{fingerprint}/ namespace so a later run under a different prompt does not
    replay it (#1939). Writes always land in the fingerprinted namespace when a
    prompt is given: an entry of known vintage is never written back into the
    flat unknown-vintage layout.

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
    target_dir = cache_dir(location, kind, _resolve_prompt_fp(prompt, prompt_file))
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
    # Namespaced entries, all globbed recursively: ast/ has per-version subdirs,
    # semantic-deep/ holds --mode deep entries (#1894), and both semantic kinds
    # have per-prompt-fingerprint subdirs alongside pre-fingerprint flat entries
    # (#1939).
    for kind in ("ast", "semantic", "semantic-deep"):
        d = base / kind
        if d.is_dir():
            hashes.update(p.stem for p in d.glob("**/*.json"))
    return hashes


def clear_cache(root: Path = Path(".")) -> None:
    """Delete all cache entries (ast/, semantic/, semantic-deep/, and legacy
    flat entries)."""
    base = Path(root).resolve() / _GRAPHIFY_OUT / "cache"
    # Legacy flat entries
    if base.is_dir():
        for f in base.glob("*.json"):
            f.unlink()
    # Namespaced entries, all globbed recursively: ast/ has per-version subdirs,
    # semantic-deep/ holds --mode deep entries (#1894), and both semantic kinds
    # have per-prompt-fingerprint subdirs (#1939).
    for kind in ("ast", "semantic", "semantic-deep"):
        d = base / kind
        if d.is_dir():
            for f in d.glob("**/*.json"):
                f.unlink()


def prune_semantic_cache(root: Path, live_hashes: set[str]) -> int:
    """Remove orphaned semantic cache entries, returning the count pruned.

    The semantic cache is content-hash-keyed (``{file_hash}.json`` under
    ``cache/semantic/``) and deliberately UNVERSIONED — entries are produced by
    the LLM from file contents, so invalidating them on every release would
    re-bill extraction. Because it is unversioned it is also never swept by the
    AST version-cleanup, so every content change or file deletion leaves a
    permanent orphan entry that accumulates unbounded.

    This sweeps ``cache/semantic/*.json`` AND ``cache/semantic-deep/*.json``
    (the ``--mode deep`` namespace, #1894) and deletes any entry whose stem
    (the content hash) is not in ``live_hashes`` — the hashes of the current
    live document set. Both namespaces are pruned against the SAME live set:
    liveness is content-based and mode-independent, so a hash that is live for
    one namespace is live for both. Skipping the deep namespace would re-grow
    the unbounded-orphan problem this function fixed (#1527). ``*.tmp``
    atomic-write temporaries are skipped, and only these directories are
    touched (never ``cache/ast/**`` or anything else). The unversioned design
    is preserved: we prune by liveness, not by version.

    The sweep recurses into the per-prompt-fingerprint subdirs (#1939) for the
    same reason it covers the deep namespace: a glob that stopped at the top
    level would leave every fingerprinted entry permanently unprunable. Entries
    under a fingerprint other than the current one are pruned by liveness only,
    never swept wholesale the way :func:`_cleanup_stale_ast_entries` sweeps old
    AST versions — two hosts with different prompts (verbose vs compact
    extraction-spec) can share one graphify-out/, and a wholesale sweep would
    have each run delete the other's entries and re-bill extraction on every
    alternation. Liveness keeps the total bounded by live docs × prompts seen.

    Best-effort, mirroring :func:`_cleanup_stale_ast_entries`: each unlink is
    wrapped in ``try/except OSError`` and a failure is ignored. The worst-case
    failure mode is benign — a surviving orphan costs only one re-extraction of
    one doc on a future run, never incorrect output.
    """
    _out = Path(_GRAPHIFY_OUT)
    base = _out if _out.is_absolute() else Path(root).resolve() / _out
    pruned = 0
    for kind in ("semantic", "semantic-deep"):
        semantic_dir = base / "cache" / kind
        if not semantic_dir.is_dir():
            continue
        for entry in semantic_dir.glob("**/*.json"):
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
    mode: str | None = None,
    prompt: "str | Path | None" = None,
    prompt_file: "str | Path | None" = None,
    cache_root: "Path | None" = None,
) -> tuple[list[dict], list[dict], list[dict], list[str]]:
    """Check semantic extraction cache for a list of absolute file paths.

    Returns (cached_nodes, cached_edges, cached_hyperedges, uncached_files).
    Uncached files need Claude extraction; cached files are merged directly.

    ``mode`` selects the cache namespace: ``None`` (the default) reads
    ``cache/semantic/`` — byte-identical to the historical behavior, so
    existing callers that omit it (including older installed skill flows)
    are unaffected. A non-None mode (e.g. ``"deep"``) reads
    ``cache/semantic-{mode}/`` instead, so deep-mode results never shadow
    (or get shadowed by) standard-mode entries for the same content (#1894).

    ``prompt`` is the extraction prompt this run will use for the uncached
    files — the prompt text (Python path) or a Path to the prompt file the
    agent loaded (skill path, ``references/extraction-spec.md``). Supplying it
    restricts hits to entries produced by that same prompt, so an upgrade that
    changed the prompt re-extracts instead of replaying the older vintage
    (#1939). Entries written before fingerprinting existed still hit — their
    vintage is unknowable and dropping them would re-bill a whole corpus — but
    a warning reports how many were served. Omitting ``prompt`` keeps the
    historical behavior for existing callers.

    ``cache_root`` decouples *where* the cache is read from the key-anchor
    ``root``, mirroring :func:`load_cached` and :func:`save_semantic_cache`
    (#1774 / #1990). With ``--out``, pass the corpus as ``root`` (so content-hash
    keys and relative-path resolution stay anchored to the source tree) and the
    output directory as ``cache_root``. Omitting it keeps ``root`` for both.
    """
    global _legacy_semantic_hits
    kind = "semantic" if mode is None else f"semantic-{mode}"
    cached_nodes: list[dict] = []
    cached_edges: list[dict] = []
    cached_hyperedges: list[dict] = []
    uncached: list[str] = []
    legacy_before = _legacy_semantic_hits

    for fpath in files:
        p = Path(fpath)
        if not p.is_absolute():
            p = Path(root) / p
        result = load_cached(p, root, kind=kind, cache_root=cache_root,
                             prompt=prompt, prompt_file=prompt_file)
        if result is not None:
            cached_nodes.extend(result.get("nodes", []))
            cached_edges.extend(result.get("edges", []))
            cached_hyperedges.extend(result.get("hyperedges", []))
        else:
            uncached.append(fpath)

    legacy = _legacy_semantic_hits - legacy_before
    if legacy:
        warnings.warn(
            f"{legacy} semantic cache entr{'y' if legacy == 1 else 'ies'} predate "
            "extraction-prompt fingerprinting and were written by an unknown prompt "
            "version; they were replayed as-is, so this graph may mix extraction "
            "vintages. Re-run with --force (or GRAPHIFY_FORCE=1) to re-extract them "
            "with the current prompt (#1939).",
            RuntimeWarning,
            stacklevel=2,
        )

    return cached_nodes, cached_edges, cached_hyperedges, uncached


def _group_has_partial_marker(group: dict) -> bool:
    """True if any node/edge/hyperedge in a per-file group carries the internal
    ``_partial`` truncation marker set by the adaptive-retry give-up sites.

    The marker rides the item dicts up through every chunk merge, so it reaches
    ``save_semantic_cache`` on BOTH the incremental checkpoint path (llm.py) and
    the final authoritative save (cli.py) without either caller having to thread
    an extra argument — the final save would otherwise overwrite a checkpoint's
    ``partial`` flag with a clean-looking entry.
    """
    for bucket in ("nodes", "edges", "hyperedges"):
        for item in group.get(bucket, []):
            if isinstance(item, dict) and item.get("_partial"):
                return True
    return False


def save_semantic_cache(
    nodes: list[dict],
    edges: list[dict],
    hyperedges: list[dict] | None = None,
    root: Path = Path("."),
    merge_existing: bool = False,
    allowed_source_files: Iterable[str | Path] | None = None,
    mode: str | None = None,
    prompt: "str | Path | None" = None,
    prompt_file: "str | Path | None" = None,
    partial_source_files: Iterable[str | Path] | None = None,
    cache_root: "Path | None" = None,
) -> int:
    """Save semantic extraction results to cache, keyed by source_file.

    Groups nodes and edges by source_file, then saves one cache entry per file
    under cache/semantic/ (separate from AST entries in cache/ast/) to prevent
    hash-key collisions (#582).

    ``mode`` selects the cache namespace, mirroring
    :func:`check_semantic_cache`: ``None`` (the default) writes
    ``cache/semantic/`` — byte-identical to the historical behavior for
    existing callers that omit it — while a non-None mode (e.g. ``"deep"``)
    writes ``cache/semantic-{mode}/`` so richer deep-mode results never
    overwrite standard-mode entries and vice versa (#1894).

    When ``merge_existing`` is True, any already-cached entry for a file is
    unioned with the new results before saving instead of being overwritten.
    This lets callers checkpoint incrementally (e.g. once per chunk) without
    dropping a prior slice of a large file that was split across chunks.

    When ``allowed_source_files`` is provided, only those files may be used as
    cache-write keys. Semantic nodes can legitimately mention another corpus
    file, but a model must not be able to replace that file's complete cache
    entry unless the file was part of the current extraction batch (#1757).

    When ``partial_source_files`` is provided, entries for those files are
    stamped ``partial: True`` — the extraction was truncated, so the entry is
    incomplete and :func:`load_cached` must treat it as a miss. Partial-ness is
    ALSO detected intrinsically from a ``_partial`` marker on any grouped item,
    so the flag survives even when a caller (e.g. cli.py's final save) does not
    pass ``partial_source_files``.

    ``prompt`` is the extraction prompt that produced these results — text, or
    a Path to the prompt file. It stamps entries into the p{fingerprint}/
    namespace so a later run under a different prompt re-extracts rather than
    replaying them (#1939). Pass the same prompt here as to
    :func:`check_semantic_cache`, or the write lands in a namespace the next
    read won't consult.

    ``cache_root`` decouples *where* the cache directory is written from the
    source-key anchor ``root`` — mirroring the same split that :func:`load_cached`
    and :func:`save_cached` already expose (#1774). When given, cache files land
    under ``cache_root`` while ``source_file`` paths are still resolved and
    relativized against ``root``. When omitted, ``root`` is used for both
    purposes (unchanged behaviour for existing callers). This fixes checkpoints
    and the final save going to the corpus tree instead of ``--out`` (#1990,
    #1991).

    Returns the number of files cached.
    """
    from collections import defaultdict

    kind = "semantic" if mode is None else f"semantic-{mode}"
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

    partial_paths = None
    if partial_source_files is not None:
        partial_paths = {resolved_source_path(path) for path in partial_source_files}
        # A chunk that truncated to an EMPTY parse contributes no grouped items,
        # so its file is absent from by_file and the write loop below would never
        # stamp it partial — leaving a prior clean slice looking complete (#1950
        # empty-parse gap). Seed an empty group for each named partial file that
        # isn't already present, so the loop merges its existing entry and stamps
        # it partial. Keyed by the resolved path (deduped against present groups).
        _present = {resolved_source_path(k) for k in by_file}
        for _pp in partial_paths:
            if _pp not in _present:
                by_file[str(_pp)]  # defaultdict: create an empty {nodes,edges,hyperedges}

    def group_skipped(fpath: str) -> bool:
        """Mirror the write-loop skip condition for one source_file group."""
        p = resolved_source_path(fpath)
        return not p.is_file() or (allowed_paths is not None and p not in allowed_paths)

    # Dangling-reference pruning (#1916). A node group is skipped by the write
    # loop below when its source_file is not a real file (ghost path) or is
    # out-of-scope per the #1757 guard — but an edge/hyperedge in an ALLOWED
    # group that references a node id from a skipped group used to be written
    # verbatim, so on replay (check_semantic_cache) it dangled forever (the
    # #1895 merged-result filter runs AFTER this checkpoint write and is
    # bypassed entirely on replay). Compute the node ids that will be skipped
    # and drop any to-be-written edge whose endpoint — or hyperedge whose
    # member (whole-hyperedge drop, mirroring #1895) — references one. Gated
    # on allowed_source_files so unscoped callers stay byte-identical.
    if allowed_paths is not None:
        skipped_ids: set = set()
        written_ids: set = set()
        for fpath, result in by_file.items():
            target = skipped_ids if group_skipped(fpath) else written_ids
            for n in result["nodes"]:
                nid = n.get("id")
                if nid is None:
                    continue
                try:
                    hash(nid)
                except TypeError:
                    continue
                target.add(nid)
        # A duplicate-attribution node (defined in a skipped AND a written
        # group) still reaches the cache — don't over-prune references to it.
        skipped_ids -= written_ids
        if skipped_ids:

            def edge_dangles(e: dict) -> bool:
                try:
                    return e.get("source") in skipped_ids or e.get("target") in skipped_ids
                except TypeError:
                    # Non-hashable endpoint from an untrusted result; leave it
                    # to build-time validation rather than fail the save.
                    return False

            def hyperedge_dangles(h: dict) -> bool:
                try:
                    return bool(skipped_ids & set(h.get("nodes") or []))
                except TypeError:
                    return False

            for fpath, result in by_file.items():
                if group_skipped(fpath):
                    continue
                result["edges"] = [e for e in result["edges"] if not edge_dangles(e)]
                result["hyperedges"] = [
                    h for h in result["hyperedges"] if not hyperedge_dangles(h)
                ]

    saved = 0
    skipped_not_file = 0
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
                # allow_legacy=False: merging a pre-fingerprint entry into this
                # write would fuse two prompt vintages inside a single entry and
                # then stamp the result as current-vintage — the exact mixing
                # #1939 is about, made unfixable because the entry now claims a
                # prompt that only produced half of it.
                # allow_partial=True: a file split into slices across chunks
                # accumulates here; if an earlier slice truncated, keep its nodes
                # in the union AND let the entry stay partial (the _partial
                # markers ride through, so is_partial below re-detects it) rather
                # than a later clean slice silently replacing it and promoting the
                # half-file to complete.
                prev = load_cached(p, root, kind=kind, cache_root=cache_root,
                                   prompt=prompt, prompt_file=prompt_file,
                                   allow_legacy=False, allow_partial=True)
                _prev_partial = bool(prev.get("partial")) if prev else False
                if prev:
                    result = {
                        "nodes": (prev.get("nodes", []) or []) + result["nodes"],
                        "edges": (prev.get("edges", []) or []) + result["edges"],
                        "hyperedges": (prev.get("hyperedges", []) or []) + result["hyperedges"],
                    }
            else:
                _prev_partial = False
            # A file is partial if the caller named it, any of its grouped items
            # carries the intrinsic ``_partial`` marker, OR the entry it merged
            # onto was already partial (an empty-parse truncation leaves a
            # ``partial: True`` entry with no item markers, so a later clean slice
            # merging over it must NOT silently promote the half-file to complete
            # — #1950). Copy so the caller's dict is never mutated. A genuine
            # complete re-extraction (merge_existing=False) overwrites the
            # content-hash key with a non-partial entry that then serves normally.
            is_partial = (
                (partial_paths is not None and p in partial_paths)
                or _group_has_partial_marker(result)
                or _prev_partial
            )
            if is_partial:
                result = {**result, "partial": True}
            save_cached(p, result, root, kind=kind, cache_root=cache_root,
                        prompt=prompt, prompt_file=prompt_file)
            saved += 1
        else:
            skipped_not_file += 1
    if skipped_not_file and skipped_not_file == len(by_file):
        warnings.warn(
            f"save_semantic_cache: all {skipped_not_file} source_file group(s) were "
            "skipped because their paths do not resolve to real files. This usually "
            "means ``root`` is anchored to the wrong directory (e.g. the --out "
            "directory instead of the corpus root). Pass the corpus directory as "
            "``root`` and the output directory as ``cache_root`` (#1991).",
            RuntimeWarning,
            stacklevel=2,
        )
    return saved
