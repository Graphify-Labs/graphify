r"""Cross-platform filesystem boundaries and Graphify output paths.

Graphify stores ordinary, user-facing paths in graph IDs, manifests, cache keys,
and diagnostics.  On Windows, direct filesystem calls additionally need the
extended-length namespace (``\\?\`` for local paths and ``\\?\UNC\`` for
UNC paths) to reach deeply nested corpus files without depending on machine-wide
policy.  The helpers in this module keep that transport-only spelling at the I/O
boundary so Linux and macOS remain no-ops and Windows paths retain one stable
logical identity.

The output directory is ``graphify-out`` by default and overridable with the
``GRAPHIFY_OUT`` environment variable (worktrees or shared-output setups, #686).
It accepts a relative name (``"graphify-out-feature"``) or an absolute path
(``"/shared/graphify-out"``).

This used to be duplicated as an identical ``_GRAPHIFY_OUT`` constant in
``__main__``, ``cache``, and ``watch``, while ``security`` and ``callflow_html``
hardcoded the literal ``"graphify-out"`` and silently ignored the override
(#1423). Centralising it here keeps the name in one place. The value is read
once at import time, matching the previous per-module constants; set
``GRAPHIFY_OUT`` before the process starts and every reader honours it.
"""

from __future__ import annotations

import json
import ntpath
import os
import re
import stat
import sys
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path, PurePosixPath
from typing import Any

GRAPHIFY_OUT = os.environ.get("GRAPHIFY_OUT", "graphify-out")


PathLike = str | os.PathLike[str]


def io_path(path: PathLike) -> str:
    r"""Return a path string suitable for Windows file-system I/O.

    Windows' legacy Win32 namespace rejects paths near ``MAX_PATH`` unless the
    machine-wide long-path policy is enabled.  The extended-length path syntax
    does not depend on that policy: local paths use ``\\?\C:\...``
    and UNC paths use ``\\?\UNC\server\share\...``.

    Keep this conversion at the I/O boundary only.  Graph IDs, manifests,
    diagnostics, ignore matching, and user-visible paths should retain their
    ordinary spelling, because the extended prefix is an API transport detail.
    """
    value = os.fspath(path)
    if sys.platform != "win32":
        return value
    if value.startswith(("\\\\?\\", "\\\\.\\")):
        return value

    # Extended-length paths must be absolute and use backslashes.  ntpath is
    # used explicitly so this helper is unit-testable from non-Windows CI.
    value = ntpath.abspath(value)
    if value.startswith("\\\\"):
        return "\\\\?\\UNC\\" + value[2:]
    return "\\\\?\\" + value


def logical_path(path: PathLike) -> str:
    r"""Remove a Windows extended-length prefix from a path string.

    ``os.walk(io_path(root))`` yields prefixed directory names.  Strip the
    transport prefix before paths enter graphify's matching/storage logic so a
    long path does not acquire a second identity merely because it was opened
    through the Windows extended namespace.
    """
    value = os.fspath(path)
    if value.upper().startswith("\\\\?\\UNC\\"):
        return "\\\\" + value[8:]
    if value.startswith("\\\\?\\"):
        return value[4:]
    return value


def resolve_path(path: PathLike) -> Path:
    """Resolve ``path`` through the I/O namespace and return ordinary spelling.

    This mirrors ``Path.resolve(strict=False)`` while ensuring the operation can
    reach a long Windows path even when the host's global long-path policy is
    disabled.  The returned ``Path`` intentionally has no extended prefix.
    """
    return Path(logical_path(os.path.realpath(io_path(path))))


def path_exists(path: PathLike) -> bool:
    """Return whether ``path`` exists, using Windows-safe path spelling."""
    return os.path.exists(io_path(path))


def path_is_file(path: PathLike) -> bool:
    """Return whether ``path`` is a regular file, using Windows-safe spelling."""
    return os.path.isfile(io_path(path))


def path_is_dir(path: PathLike) -> bool:
    """Return whether ``path`` is a directory, using Windows-safe spelling."""
    return os.path.isdir(io_path(path))


def path_is_symlink(path: PathLike) -> bool:
    """Return whether ``path`` is a symbolic link, using Windows-safe spelling."""
    return os.path.islink(io_path(path))


def path_stat(path: PathLike, *, follow_symlinks: bool = True) -> os.stat_result:
    """Stat ``path`` through the Windows-safe I/O namespace."""
    return os.stat(io_path(path), follow_symlinks=follow_symlinks)


def make_dirs(
    path: PathLike,
    mode: int = 0o777,
    *,
    exist_ok: bool = False,
) -> None:
    """Create a directory tree through the Windows-safe I/O namespace."""
    os.makedirs(io_path(path), mode=mode, exist_ok=exist_ok)


def scandir_path(path: PathLike) -> os.ScandirIterator[str]:
    """Return ``os.scandir`` for ``path`` using Windows-safe spelling."""
    return os.scandir(io_path(path))


def iterdir_path(path: PathLike) -> Iterator[Path]:
    r"""Yield direct children while preserving the caller's path spelling.

    ``DirEntry.path`` inherits the extended absolute root supplied to
    :func:`os.scandir`. Rebuild each child from the logical input root and the
    entry name so a relative input remains relative and ``\\?\`` never escapes.
    """
    logical_root = Path(logical_path(path))
    with scandir_path(path) as entries:
        for entry in entries:
            yield logical_root / entry.name


def glob_paths(path: PathLike, pattern: str) -> Iterator[Path]:
    """Yield glob matches below ``path`` while retaining logical spelling.

    Prefix the root before delegating to :meth:`Path.glob`; this preserves
    pathlib's matching behavior (including dotfiles) while every recursive
    ``scandir`` stays in the extended Windows namespace. Matches are then
    reconstructed relative to the caller's root, avoiding an accidental
    relative-to-absolute API change on Windows.
    """
    logical_root = Path(logical_path(path))
    filesystem_root = Path(io_path(path))
    for match in filesystem_root.glob(pattern):
        try:
            relative = match.relative_to(filesystem_root)
        except ValueError:
            # Defensive fallback for an unusual pathlib implementation; glob
            # matches should ordinarily remain below their root.
            yield Path(logical_path(match))
        else:
            yield logical_root / relative


def unlink_path(path: PathLike, *, missing_ok: bool = False) -> None:
    """Remove a file or symlink through the Windows-safe namespace."""
    try:
        os.unlink(io_path(path))
    except FileNotFoundError:
        if not missing_ok:
            raise


def replace_path(source: PathLike, destination: PathLike) -> None:
    """Atomically replace ``destination`` using Windows-safe path spellings."""
    os.replace(io_path(source), io_path(destination))


def walk_path(
    path: PathLike,
    *,
    topdown: bool = True,
    onerror: Callable[[OSError], Any] | None = None,
    followlinks: bool = False,
) -> Iterator[tuple[str, list[str], list[str]]]:
    """Walk ``path`` safely and yield ordinary, user-facing path spellings.

    ``os.walk`` must receive the extended Windows form at the traversal root;
    otherwise a later ``scandir`` fails as soon as a descendant crosses the
    legacy ``MAX_PATH`` boundary. The extended prefix is stripped from every
    yielded directory and from errors before control returns to callers. A
    relative input remains relative even though the Windows I/O root must be
    absolute before it can use the extended namespace.
    """
    logical_root = logical_path(path)
    filesystem_root = io_path(path)
    ordinary_filesystem_root = logical_path(filesystem_root)

    def _from_filesystem_path(value: PathLike) -> str:
        ordinary = logical_path(value)
        if sys.platform != "win32":
            return ordinary
        try:
            relative = ntpath.relpath(ordinary, ordinary_filesystem_root)
        except ValueError:
            # Different UNC shares/drives cannot be relativized; stripping the
            # transport prefix is still the safest public representation.
            return ordinary
        if relative == ".":
            return logical_root
        return ntpath.join(logical_root, relative)

    def _onerror(error: OSError) -> None:
        filename = getattr(error, "filename", None)
        if filename is not None:
            try:
                error.filename = _from_filesystem_path(filename)
            except (AttributeError, TypeError):
                pass
        if onerror is not None:
            onerror(error)

    handler = _onerror if onerror is not None else None
    for dirpath, dirnames, filenames in os.walk(
        filesystem_root,
        topdown=topdown,
        onerror=handler,
        followlinks=followlinks,
    ):
        yield _from_filesystem_path(dirpath), dirnames, filenames


def read_bytes(path: PathLike, *, limit: int | None = None) -> bytes:
    """Read bytes through the Windows-safe I/O spelling of ``path``.

    ``limit`` mirrors ``file.read(limit)`` and supports bounded probes without a
    separate, long-path-unsafe ``Path.open`` call.
    """
    with open(io_path(path), "rb") as fh:
        return fh.read() if limit is None else fh.read(limit)


def read_text(
    path: PathLike,
    *,
    encoding: str | None = None,
    errors: str | None = None,
) -> str:
    """Read text through the Windows-safe I/O spelling of ``path``.

    The default encoding intentionally mirrors :meth:`Path.read_text` and the
    built-in :func:`open`; corpus readers that require UTF-8 pass it explicitly.
    """
    with open(io_path(path), "r", encoding=encoding, errors=errors) as fh:
        return fh.read()


def write_text(
    path: PathLike,
    text: str,
    *,
    encoding: str | None = None,
    errors: str | None = None,
    newline: str | None = None,
) -> int:
    """Write text through the Windows-safe I/O spelling of ``path``."""
    with open(
        io_path(path),
        "w",
        encoding=encoding,
        errors=errors,
        newline=newline,
    ) as fh:
        return fh.write(text)


def write_bytes(path: PathLike, data: bytes) -> int:
    """Write bytes through the Windows-safe I/O spelling of ``path``."""
    with open(io_path(path), "wb") as fh:
        return fh.write(data)


def _atomic_replace(path: "str | Path", write_fn) -> None:
    """Atomically replace ``path`` with content written by ``write_fn(f)``.

    Writes a temp file in the SAME directory, then ``os.replace``s it into place
    (an atomic rename on one filesystem). A process kill (SIGKILL/Ctrl-C), OOM, or
    ENOSPC mid-write leaves the previous file intact — the destination is
    untouched until the rename. This is NOT a power-loss durability guarantee:
    there is no fsync (matching the rest of the codebase), so an OS/hardware crash
    right after the rename can still expose unflushed bytes on some filesystems.
    The temp file is removed if the write fails.

    A symlinked destination is resolved first so the write goes THROUGH the link
    to its target (rather than replacing the link with a regular file), keeping
    the shared-output/worktree symlink setups this module documents working.
    """
    # Resolve symlinks so the temp lands on the target's filesystem (same-fs
    # atomic rename) and the replace writes through the link, not over it.
    real = resolve_path(path)
    make_dirs(real.parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=io_path(real.parent),
        prefix=f".{real.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            write_fn(f)
        # mkstemp creates the temp file 0600; match the destination's existing
        # mode (or the umask default for a new file) so an atomic replace never
        # silently tightens a previously group/world-readable output to
        # owner-only. Best-effort — a chmod failure must not fail the write.
        try:
            mode = stat.S_IMODE(path_stat(real).st_mode)
        except OSError:
            umask = os.umask(0)
            os.umask(umask)
            mode = 0o666 & ~umask
        try:
            os.chmod(tmp, mode)
        except OSError:
            pass
        try:
            os.replace(tmp, io_path(real))
        except PermissionError:
            # Windows: os.replace fails (WinError 5/32) when the destination is
            # briefly locked by another handle (antivirus, an open reader). Fall
            # back to copy-then-delete, matching graphify.cache's atomic writer.
            import shutil
            shutil.copy2(tmp, io_path(real))
            os.unlink(tmp)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_text_atomic(path: "str | Path", text: str) -> None:
    """Atomically write ``text`` (UTF-8) to ``path``. See :func:`_atomic_replace`."""
    _atomic_replace(path, lambda f: f.write(text))


def write_json_atomic(path: "str | Path", obj, *, indent: "int | None" = None, ensure_ascii: bool = True) -> None:
    """Atomically write ``obj`` as JSON to ``path``, streaming the encode into the
    temp file rather than materializing the whole string first (matters for very
    large graphs). ``ensure_ascii`` mirrors ``json.dump`` so callers that emit raw
    UTF-8 (non-ASCII labels/paths) keep byte-for-byte output. See :func:`_atomic_replace`."""
    _atomic_replace(path, lambda f: json.dump(obj, f, indent=indent, ensure_ascii=ensure_ascii))

# Directory segments that, when they appear as a whole path component, mark the
# whole path as a test location. Matched against path *segments* (not raw
# substrings) so "src/contest.py" / "latest/x.py" / "src/greatest/x.py" do NOT
# match — only a segment that *equals* one of these names (case-insensitively).
_TEST_DIR_SEGMENTS = frozenset({"tests", "test", "spec", "specs", "__tests__"})

# Filename patterns marking a file as a test, matched against the *filename*
# only (case-insensitive). These are conventions across ecosystems:
#   test_*.py            pytest / unittest
#   *_test.*             Go / Python / Rust
#   *.test.*             JS/TS (jest, vitest)
#   *.spec.* / *_spec.*  Jasmine / RSpec / Karma
#   *.Tests.ps1          PowerShell Pester
#   *Test.java / *Tests.cs (case-sensitive convention, handled below)
_TEST_FILENAME_PATTERNS = (
    re.compile(r"^test_.*", re.IGNORECASE),
    re.compile(r".*_test\..+$", re.IGNORECASE),
    re.compile(r".*\.test\..+$", re.IGNORECASE),
    re.compile(r".*\.spec\..+$", re.IGNORECASE),
    re.compile(r".*_spec\..+$", re.IGNORECASE),
    re.compile(r".*\.tests\.ps1$", re.IGNORECASE),
    # Java `FooTest.java` / `FooTests.java`, C# `FooTests.cs` style. Require an
    # uppercase-led `Test`/`Tests` immediately before the extension so plain
    # words like "greatest"/"contest.cs" do not match.
    re.compile(r".*Test\.java$"),
    re.compile(r".*Tests\.java$"),
    re.compile(r".*Tests\.cs$"),
)


def _is_test_path(path: str) -> bool:
    """Classify a source path as a test path (case-insensitive, segment-aware).

    Shared by extract.py and symbol_resolution.py so cross-file call resolution
    treats test mocks/stubs identically. A path is a test path when:
      * any whole path segment equals a known test dir name
        (``tests``/``test``/``spec``/``specs``/``__tests__``), or
      * the filename matches a known test-file naming convention.

    Conservative on purpose: matches segments/filenames, never raw substrings,
    so ``latest.py``, ``src/contest.py`` and ``src/greatest/x.py`` are NON-test.
    """
    if not path:
        return False
    # Accept both POSIX and Windows separators regardless of host OS so the
    # classifier is stable across the mixed paths that flow through extraction.
    norm = str(path).replace("\\", "/")
    pure = PurePosixPath(norm)
    segments = list(pure.parts)
    # Strip a leading drive/anchor segment (e.g. "C:/") that PureWindowsPath
    # would surface; with the manual "\\"->"/" swap above PurePosixPath keeps
    # the path body intact, but guard against a Windows drive embedded as a
    # segment just in case.
    for segment in segments:
        if segment.lower() in _TEST_DIR_SEGMENTS:
            return True
        # A drive-letter colon segment like "c:" is never a test dir.
    filename = pure.name
    if not filename:
        return False
    for pattern in _TEST_FILENAME_PATTERNS:
        if pattern.match(filename):
            return True
    return False


def _path_proximity_winner(call_site_file: str, candidate_files: dict[str, str]) -> str | None:
    """Pick the candidate whose source file is closest to the call site.

    ``candidate_files`` maps candidate id -> its source_file. Returns a single
    winning candidate id, or ``None`` when no proximity tier yields a unique
    winner. Tiers, in order:

      1. same file as the call site,
      2. same directory,
      3. longest common path-prefix (must be a strict, unique maximum).

    Used only as a secondary tie-break after the test/non-test filter, so the
    god-node guard still holds when proximity is genuinely ambiguous.
    """
    if not call_site_file:
        return None
    call_norm = str(call_site_file).replace("\\", "/")
    call_dir = PurePosixPath(call_norm).parent

    # Tier 1: exact same file.
    same_file = [cid for cid, f in candidate_files.items()
                 if str(f).replace("\\", "/") == call_norm]
    if len(same_file) == 1:
        return same_file[0]
    if len(same_file) > 1:
        return None  # genuinely ambiguous within one file; bail

    # Tier 2: same directory.
    same_dir = [cid for cid, f in candidate_files.items()
                if PurePosixPath(str(f).replace("\\", "/")).parent == call_dir]
    if len(same_dir) == 1:
        return same_dir[0]
    if len(same_dir) > 1:
        return None

    # Tier 3: longest common path-prefix, computed over path segments. The
    # winner must be a strict unique maximum, else we bail (guard holds).
    call_parts = call_dir.parts

    def _common_prefix_len(f: str) -> int:
        parts = PurePosixPath(str(f).replace("\\", "/")).parent.parts
        n = 0
        for a, b in zip(call_parts, parts):
            if a != b:
                break
            n += 1
        return n

    scored = sorted(
        ((cid, _common_prefix_len(f)) for cid, f in candidate_files.items()),
        key=lambda kv: kv[1],
        reverse=True,
    )
    if not scored:
        return None
    best = scored[0][1]
    winners = [cid for cid, score in scored if score == best]
    if len(winners) == 1 and best > 0:
        return winners[0]
    return None


def disambiguate_ambiguous_candidates(
    candidates: list[str],
    candidate_files: dict[str, str],
    call_site_file: str,
) -> str | None:
    """Resolve an ambiguous bare-name call to one candidate, or ``None``.

    Shared god-node tie-breaker (#1553) used by both the inline cross-file call
    pass in ``extract.py`` and ``symbol_resolution.resolve_cross_file_raw_calls``
    so the heuristics stay aligned across languages. ``candidates`` is the list
    of node ids sharing the callee's name; ``candidate_files`` maps each id ->
    its source_file. Returns the surviving candidate id only when exactly one
    survives; otherwise ``None`` (caller keeps the god-node guard / ``continue``).

    Tie-breakers, in order:
      1. NON-TEST preference. Classify the call site and each candidate as
         test/non-test. When the call site is NON-test, drop test candidates.
         When the call site IS a test file, prefer test-local candidates
         (same file first, then any test candidate); fall back to the full set
         only if no test candidate exists.
      2. PATH PROXIMITY over whatever survived step 1.
    """
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    call_is_test = _is_test_path(call_site_file)
    test_cands = [c for c in candidates if _is_test_path(candidate_files.get(c, ""))]
    nontest_cands = [c for c in candidates if c not in set(test_cands)]

    if call_is_test:
        # Prefer a test-local definition (same file) first.
        call_norm = str(call_site_file).replace("\\", "/")
        same_file_test = [
            c for c in test_cands
            if str(candidate_files.get(c, "")).replace("\\", "/") == call_norm
        ]
        if len(same_file_test) == 1:
            return same_file_test[0]
        if test_cands:
            survivors = test_cands
        else:
            survivors = nontest_cands or candidates
    else:
        # Non-test call site: drop test mocks/stubs entirely.
        survivors = nontest_cands

    if len(survivors) == 1:
        return survivors[0]
    if not survivors:
        return None

    # Step 2: path proximity over the survivors.
    return _path_proximity_winner(
        call_site_file,
        {c: candidate_files.get(c, "") for c in survivors},
    )

# Bare directory name even when GRAPHIFY_OUT is an absolute path. Used by path
# guards that walk parents looking for the output directory by name.
GRAPHIFY_OUT_NAME = os.path.basename(os.path.normpath(GRAPHIFY_OUT))


def out_path(*parts: str) -> Path:
    """A path inside the configured output dir, e.g. ``out_path("cache")``.

    ``Path(GRAPHIFY_OUT) / ...`` resolves correctly for both a relative name
    ("graphify-out") and an absolute override ("/shared/graphify-out").
    """
    return Path(GRAPHIFY_OUT, *parts)


def default_graph_json() -> str:
    """Default ``graph.json`` path under the configured output dir.

    The package-wide fallback used by serve/build/benchmark/prs and the CLI read
    commands so a ``GRAPHIFY_OUT`` override is honoured everywhere, not just where
    the path is passed explicitly (#1423).
    """
    return str(out_path("graph.json"))


def nfc(s: str) -> str:
    """NFC-normalize a path string.

    macOS (HFS+/APFS) reports filenames in NFD while manifests, graph
    ``source_file`` entries and user input are typically NFC. Comparing raw
    strings makes the same file look like two different paths, so any path
    membership test must normalize BOTH sides (#2210, #2221/#2224).
    """
    import unicodedata
    return unicodedata.normalize("NFC", s)


def load_node_link_graph(path_or_data):
    """Load a graphify graph.json into a networkx graph, accepting both writers.

    The clustered writer stores edges under ``links`` (networkx's node-link
    default); the raw ``--no-cluster`` writer stores them under ``edges``.
    Consumers that call ``node_link_graph(data, edges="links")`` directly
    raise ``KeyError: 'links'`` on a raw graph (#2212) — the ``except
    TypeError`` fallback only covers old networkx without the ``edges``
    kwarg, not the missing key. Normalize before parsing, same idiom as
    affected.py/serve.py.

    Accepts a path (size-cap-checked via the security module, then parsed)
    or an already-parsed dict (no size check — the caller owns any cap).
    """
    from networkx.readwrite import json_graph
    data = path_or_data
    if not isinstance(data, dict):
        p = Path(data)
        from graphify.security import check_graph_file_size_cap  # lazy: security imports paths
        check_graph_file_size_cap(p)
        data = json.loads(read_text(p, encoding="utf-8"))
    if isinstance(data, dict) and "links" not in data and "edges" in data:
        data = dict(data, links=data["edges"])
    try:
        return json_graph.node_link_graph(data, edges="links")
    except TypeError:  # networkx too old for the edges kwarg; default is "links"
        return json_graph.node_link_graph(data)
