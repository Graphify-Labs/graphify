"""Drift guard for the node-ID spec shown to LLM semantic subagents.

`tools/skillgen/fragments/references/shared/extraction-spec.md` (and the per-host
copies skillgen renders from it) tell the subagents how to build node IDs, with
worked examples like::

    `src/auth/session.py` + `ValidateToken` → `auth_session_validatetoken`

Those examples are the LLM's ground truth, and they must reproduce exactly what
the AST extractor emits (`extract._file_stem` + `extract._make_id`) or the two
producers generate different IDs for the same symbol and the graph splits it into
disconnected ghost nodes — the bug class the prose itself warns about
(#811/#550/#1033/#1104).

The prose is hand-maintained, so it can silently drift from the code. This test
parses every example straight out of the shipped specs and asserts the real
functions reproduce each one. It fails if the spec examples are edited to a wrong
value, OR if the ID functions change so the documented examples no longer hold.
"""
import re
from pathlib import Path

import pytest

from graphify.extract import _file_stem, _make_id

REPO_ROOT = Path(__file__).resolve().parents[1]

# `path` + `entity` → `id`  (arrow is U+2192). Backtick-delimited so prose around
# the examples never leaks in.
_EXAMPLE_RE = re.compile(r"`([^`]+)`\s*\+\s*`([^`]+)`\s*→\s*`([^`]+)`")

# `path.md` → `id`  — the whole-file-node convention (no `+`/entity group, so this
# never overlaps with `_EXAMPLE_RE` above).
_WHOLE_FILE_EXAMPLE_RE = re.compile(r"`([\w./-]+\.md)`\s*→\s*`([a-z0-9_]+)`")


def _spec_files() -> list[Path]:
    roots = [REPO_ROOT / "graphify" / "skills", REPO_ROOT / "tools" / "skillgen" / "fragments"]
    files: list[Path] = []
    for root in roots:
        for p in root.rglob("extraction-spec.md"):
            # build/ is a packaging artifact; expected/ is skillgen's own golden
            # output and is already covered by `skillgen --check`.
            if "/build/" in p.as_posix() or "/expected/" in p.as_posix():
                continue
            files.append(p)
    return sorted(files)


def _examples() -> list[tuple[Path, str, str, str]]:
    out: list[tuple[Path, str, str, str]] = []
    for f in _spec_files():
        text = f.read_text(encoding="utf-8")
        for path, entity, expected in _EXAMPLE_RE.findall(text):
            out.append((f, path, entity, expected))
    return out


def _ast_symbol_id(path: str, entity: str) -> str:
    """Reproduce the symbol ID the AST extractor emits for a file + symbol, using
    the real production helpers (not a re-implementation)."""
    return _make_id(_file_stem(Path(path)), entity)


def _ast_file_id(path: str) -> str:
    """Reproduce the AST extractor's whole-file node ID (no entity part) - what
    `extract_markdown`'s `file_nid` canonicalizes to after extract()'s id-remap
    post-pass, and what a semantic subagent must independently reproduce for a
    whole-file node to merge instead of splitting (#1033-shaped bug class)."""
    return _make_id(_file_stem(Path(path)))


def _whole_file_examples() -> list[tuple[Path, str, str]]:
    out: list[tuple[Path, str, str]] = []
    for f in _spec_files():
        text = f.read_text(encoding="utf-8")
        for path, expected in _WHOLE_FILE_EXAMPLE_RE.findall(text):
            out.append((f, path, expected))
    return out


def test_spec_files_are_discoverable():
    """Guard the guard: if the spec moves or the example format changes so nothing
    parses, fail loudly rather than passing vacuously."""
    files = _spec_files()
    assert files, "no extraction-spec.md files found — did the skills tree move?"
    examples = _examples()
    assert len(examples) >= 13, (
        f"expected the documented node-ID examples across host specs, parsed only "
        f"{len(examples)} — the example format may have changed"
    )


@pytest.mark.parametrize(
    "path,entity,expected",
    [(p, e, x) for (_f, p, e, x) in _examples()],
    ids=[f"{f.parent.parent.name}:{p}+{e}" for (f, p, e, x) in _examples()],
)
def test_spec_node_id_examples_match_ast_extractor(path, entity, expected):
    got = _ast_symbol_id(path, entity)
    assert got == expected, (
        f"node-ID spec drift: spec says `{path}` + `{entity}` → `{expected}`, but "
        f"extract._make_id(_file_stem(...), ...) produces `{got}`. Update the spec "
        f"examples and the ID functions together."
    )


def test_cautionary_wrong_forms_are_actually_wrong():
    """The canonical spec warns against the filename-only and full-path ID forms.
    Lock those anti-examples to the code too, so the warning can't go stale."""
    correct = _ast_symbol_id("src/auth/session.py", "ValidateToken")
    assert correct == "src_auth_session_validatetoken"
    # filename-only (drops every dir) and immediate-parent-only (drops outer dirs)
    # are both wrong now that the stem is the full repo-relative path (#1504).
    assert _make_id("session", "ValidateToken") != correct
    assert _make_id("auth", "session", "ValidateToken") != correct


def test_whole_file_node_examples_are_discoverable():
    """Guard the guard, for the whole-file-node convention specifically: if the
    spec wording changes so the example no longer parses, fail loudly."""
    examples = _whole_file_examples()
    assert examples, (
        "no whole-file-node ID examples found across host specs — did the "
        "'Whole-file nodes' wording change?"
    )


@pytest.mark.parametrize(
    "path,expected",
    [(p, x) for (_f, p, x) in _whole_file_examples()],
    ids=[f"{f.parent.parent.name}:{p}" for (f, p, x) in _whole_file_examples()],
)
def test_whole_file_node_id_examples_match_ast_extractor(path, expected):
    got = _ast_file_id(path)
    assert got == expected, (
        f"whole-file node-ID spec drift: spec says `{path}` → `{expected}`, but "
        f"extract._make_id(_file_stem(...)) produces `{got}`. Update the spec "
        f"example and the ID functions together."
    )


def test_whole_file_node_id_has_no_document_suffix():
    """Regression test for the exact split-node bug this spec section closes: two
    subagents extracting the same doc suite in parallel independently produced
    `docs_architecture` and `docs_architecture_document` for one real file,
    because nothing told either of them what a whole-file node's ID should be.
    The correct, single ID is the bare stem — the same recipe as a symbol ID
    with the entity part simply omitted, never a `_document`/`_file` suffix."""
    correct = _ast_file_id("docs/ARCHITECTURE.md")
    assert correct == "docs_architecture"
    assert correct != "docs_architecture_document"
