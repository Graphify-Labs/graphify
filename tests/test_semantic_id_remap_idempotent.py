"""Incremental rebuild must be idempotent for dot-directory files (#1924).

`_semantic_id_remap` re-derives a non-AST node's id from its `source_file` so a
drifted/legacy fragment reconciles with the AST node (#1504/#1509). For a file in
a dot-directory the canonical full-path stem *contains* the shorter legacy stem as
a proper prefix — e.g. `.claude/CLAUDE.md` has canonical stem `claude_claude` while
its zero-parent legacy form is the bare `claude`. Without an already-canonical
guard, the greedy `_old_file_stems` match stripped one `claude_` off an
already-canonical id and re-prepended the full stem, inflating the id by one
`claude_` on every incremental rebuild so `graph.json` never converged.
"""
from __future__ import annotations

from graphify.build import _semantic_id_remap


def _remap_once(nid: str) -> str:
    node = {"id": nid, "source_file": ".claude/CLAUDE.md",
            "file_type": "document", "_origin": "semantic"}
    return _semantic_id_remap([node], root=None).get(nid, nid)


def test_canonical_dotdir_id_is_stable_across_reruns():
    # An already-canonical id (full-path stem prefix) must never be re-prefixed.
    nid = "claude_claude_graphify_trigger"
    for _ in range(5):
        nid = _remap_once(nid)
    assert nid == "claude_claude_graphify_trigger"


def test_remap_is_a_fixed_point():
    # Applying the remap to its own output changes nothing.
    canonical = "claude_claude_graphify_trigger"
    assert _remap_once(canonical) == canonical


def test_legacy_dotdir_forms_still_migrate_once():
    # The idempotency guard must not disable genuine legacy migration.
    # zero-parent form (bare stem + entity) -> canonical full-path form:
    assert _remap_once("claude_graphify_trigger") == "claude_claude_graphify_trigger"
    # the file node itself (bare stem) -> canonical full-path stem:
    assert _remap_once("claude") == "claude_claude"
    # and the migrated results are themselves stable:
    assert _remap_once("claude_claude_graphify_trigger") == "claude_claude_graphify_trigger"
    assert _remap_once("claude_claude") == "claude_claude"
