"""Single source of truth for the graphify output-directory name.

The output directory is ``graphify-out`` by default and overridable with the
``GRAPHIFY_OUT`` env var (worktrees or shared-output setups, #686). It accepts a
relative name (``"graphify-out-feature"``) or an absolute path
(``"/shared/graphify-out"``).

This used to be duplicated as an identical ``_GRAPHIFY_OUT`` constant in
``__main__``, ``cache``, and ``watch``, while ``security`` and ``callflow_html``
hardcoded the literal ``"graphify-out"`` and silently ignored the override
(#1423). Centralising it here keeps the name in one place. The value is read
once at import time, matching the previous per-module constants — set
``GRAPHIFY_OUT`` before the process starts (the normal worktree/shared-output
flow) and every reader honours it.
"""

from __future__ import annotations

import json
import os
import re
import stat
import tempfile
from pathlib import Path, PurePosixPath

GRAPHIFY_OUT = os.environ.get("GRAPHIFY_OUT", "graphify-out")


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
    real = Path(os.path.realpath(str(path)))
    real.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(real.parent), prefix=f".{real.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            write_fn(f)
        # mkstemp creates the temp file 0600; match the destination's existing
        # mode (or the umask default for a new file) so an atomic replace never
        # silently tightens a previously group/world-readable output to
        # owner-only. Best-effort — a chmod failure must not fail the write.
        try:
            mode = stat.S_IMODE(os.stat(real).st_mode)
        except OSError:
            umask = os.umask(0)
            os.umask(umask)
            mode = 0o666 & ~umask
        try:
            os.chmod(tmp, mode)
        except OSError:
            pass
        try:
            os.replace(tmp, str(real))
        except PermissionError:
            # Windows: os.replace fails (WinError 5/32) when the destination is
            # briefly locked by another handle (antivirus, an open reader). Fall
            # back to copy-then-delete, matching graphify.cache's atomic writer.
            import shutil
            shutil.copy2(tmp, str(real))
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

# Bare directory name even when GRAPHIFY_OUT is an absolute path. Used by the
# path guards that walk parents looking for the output dir by name, and by the
# detect scan-exclude so a custom output dir is never re-ingested as source.
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
