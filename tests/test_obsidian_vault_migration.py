"""A vault written before the ownership manifest must not end up with two generations.

#1506 added `.graphify_obsidian_manifest.json` so a re-export can update its own
notes while refusing to touch the user's. A vault created by an EARLIER graphify
has no manifest, so `_owned` starts empty and every note graphify itself wrote
last time reads as a user file: the re-export writes fresh notes beside the
stale ones, and warns that graphify "did not create" files it did (#2863).

The fix adopts, once, the notes carrying graphify's own signature:

  * node notes    - YAML frontmatter with a tag in the ``graphify/`` namespace
  * community notes - no frontmatter at all, so matched on graphify's own
                      filename prefix AND the Dataview query it writes

`.obsidian/graph.json` is deliberately NOT adopted: graphify writes one, but so
does Obsidian, and without a manifest there is no way to tell whose it is.
"""
import io
import json
from contextlib import redirect_stderr
from pathlib import Path

import pytest

from graphify.build import build_from_json
from graphify.export import to_obsidian

try:
    from graphify.export import _adopt_pre_manifest_notes, _is_graphify_note
except ImportError:  # pre-fix tree
    _adopt_pre_manifest_notes = _is_graphify_note = None

MANIFEST = ".graphify_obsidian_manifest.json"


def _graph(labels):
    nodes = [{"id": f"n{i}", "label": l, "file_type": "document",
              "source_file": f"d{i}.md"} for i, l in enumerate(labels)]
    edges = [{"source": f"n{i}", "target": f"n{i+1}", "relation": "references",
              "confidence": "EXTRACTED", "source_file": f"d{i}.md"}
             for i in range(len(labels) - 1)]
    return build_from_json({"nodes": nodes, "edges": edges, "hyperedges": []})


def _export(vault, labels):
    ids = [f"n{i}" for i in range(len(labels))]
    buf = io.StringIO()
    with redirect_stderr(buf):
        to_obsidian(_graph(labels), {0: ids}, str(vault))
    return buf.getvalue()


def _notes(vault):
    return {p.name for p in Path(vault).glob("*.md")}


@pytest.fixture
def pre_manifest_vault(tmp_path):
    """A vault as an older graphify would have left it: its notes, no manifest."""
    vault = tmp_path / "vault"
    _export(vault, ["Alpha", "Beta", "Gamma"])
    (vault / MANIFEST).unlink()
    return vault


# ---------------------------------------------------------------------------
# The bug
# ---------------------------------------------------------------------------

def test_a_reexport_leaves_no_second_generation(pre_manifest_vault):
    _export(pre_manifest_vault, ["Alpha", "Beta renamed", "Gamma renamed"])
    assert _notes(pre_manifest_vault) == {
        "Alpha.md", "Beta renamed.md", "Gamma renamed.md",
        "_COMMUNITY_Community 0.md",
    }


def test_stale_notes_for_renamed_nodes_are_gone(pre_manifest_vault):
    _export(pre_manifest_vault, ["Alpha", "Beta renamed", "Gamma renamed"])
    left = _notes(pre_manifest_vault)
    assert "Beta.md" not in left and "Gamma.md" not in left


def test_graphify_no_longer_claims_it_did_not_write_its_own_notes(pre_manifest_vault):
    err = _export(pre_manifest_vault, ["Alpha", "Beta renamed", "Gamma renamed"])
    for name in ("Alpha.md", "Beta.md", "_COMMUNITY_"):
        assert name not in err, err


def test_the_manifest_is_written_so_migration_happens_once(pre_manifest_vault):
    _export(pre_manifest_vault, ["Alpha", "Beta", "Gamma"])
    owned = json.loads((pre_manifest_vault / MANIFEST).read_text(encoding="utf-8"))["files"]
    assert "Alpha.md" in owned
    assert any(f.startswith("_COMMUNITY_") for f in owned)


# ---------------------------------------------------------------------------
# The user's own notes must still be safe
# ---------------------------------------------------------------------------

def test_a_users_own_note_is_never_adopted(pre_manifest_vault):
    mine = pre_manifest_vault / "Alpha.md"
    mine.write_text("# My own note about Alpha\n\nI wrote this.\n", encoding="utf-8")
    _export(pre_manifest_vault, ["Alpha", "Beta", "Gamma"])
    assert "I wrote this." in mine.read_text(encoding="utf-8")


def test_a_note_merely_mentioning_graphify_is_not_adopted(pre_manifest_vault):
    mine = pre_manifest_vault / "Notes.md"
    mine.write_text("# Notes\n\nI use graphify/document tags manually.\n", encoding="utf-8")
    _export(pre_manifest_vault, ["Alpha", "Beta", "Gamma"])
    assert "I use graphify" in mine.read_text(encoding="utf-8")


def test_a_user_community_named_file_needs_the_query_marker_too(pre_manifest_vault):
    """The filename prefix alone must not be enough to adopt a file."""
    mine = pre_manifest_vault / "_COMMUNITY_mine.md"
    mine.write_text("# My own community summary\n\nhand written\n", encoding="utf-8")
    _export(pre_manifest_vault, ["Alpha", "Beta", "Gamma"])
    assert "hand written" in mine.read_text(encoding="utf-8")


def test_obsidian_config_is_not_adopted(pre_manifest_vault):
    """graphify writes .obsidian/graph.json, but so does Obsidian. With no
    manifest there is no way to tell, so it stays unowned."""
    cfg = pre_manifest_vault / ".obsidian" / "graph.json"
    cfg.parent.mkdir(exist_ok=True)
    cfg.write_text('{"mine": true}', encoding="utf-8")
    _export(pre_manifest_vault, ["Alpha", "Beta", "Gamma"])
    assert json.loads(cfg.read_text(encoding="utf-8")) == {"mine": True}


# ---------------------------------------------------------------------------
# Unchanged behaviour
# ---------------------------------------------------------------------------

def test_a_vault_with_a_manifest_is_untouched_by_the_migration(tmp_path):
    vault = tmp_path / "v"
    _export(vault, ["Alpha", "Beta"])
    before = json.loads((vault / MANIFEST).read_text(encoding="utf-8"))["files"]
    _export(vault, ["Alpha", "Beta"])
    after = json.loads((vault / MANIFEST).read_text(encoding="utf-8"))["files"]
    assert sorted(before) == sorted(after)


def test_a_fresh_directory_still_works(tmp_path):
    vault = tmp_path / "brand-new"
    _export(vault, ["Alpha", "Beta"])
    assert "Alpha.md" in _notes(vault)


# ---------------------------------------------------------------------------
# The detector itself
# ---------------------------------------------------------------------------

@pytest.mark.skipif(_is_graphify_note is None, reason="pre-fix tree")
def test_detector_accepts_a_graphify_node_note(tmp_path):
    p = tmp_path / "n.md"
    p.write_text('---\nsource_file: "a.md"\ntags:\n  - graphify/document\n---\n\n# N\n',
                 encoding="utf-8")
    assert _is_graphify_note(p)


@pytest.mark.skipif(_is_graphify_note is None, reason="pre-fix tree")
@pytest.mark.parametrize("body", [
    "# plain note\n",
    "---\ntitle: mine\ntags:\n  - personal\n---\n\n# mine\n",
    "---\nnot even closed\n",
    "",
])
def test_detector_rejects_everything_else(tmp_path, body):
    p = tmp_path / "x.md"
    p.write_text(body, encoding="utf-8")
    assert not _is_graphify_note(p)


@pytest.mark.skipif(_adopt_pre_manifest_notes is None, reason="pre-fix tree")
def test_adoption_only_looks_at_top_level_markdown(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "deep.md").write_text(
        "---\ntags:\n  - graphify/document\n---\n", encoding="utf-8")
    assert _adopt_pre_manifest_notes(tmp_path) == set()
