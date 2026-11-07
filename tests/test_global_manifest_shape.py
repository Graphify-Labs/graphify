"""Global graph commands recover from JSON with the wrong manifest shape."""

import json

import pytest

from graphify import global_graph


@pytest.mark.parametrize("payload", [None, [], {}, {"repos": []}])
def test_global_list_backs_up_wrong_manifest_shape(tmp_path, monkeypatch, capsys, payload):
    # A non-dict root, or a repos value that is not a map at all, is too broken
    # to recover per-entry: back it up and start fresh.
    manifest = tmp_path / "global-manifest.json"
    original = json.dumps(payload)
    manifest.write_text(original, encoding="utf-8")
    monkeypatch.setattr(global_graph, "_GLOBAL_MANIFEST", manifest)

    assert global_graph.global_list() == {}

    assert not manifest.exists()
    backup, = tmp_path.glob("global-manifest.json.corrupt.*")
    assert backup.read_text(encoding="utf-8") == original
    assert "moved to" in capsys.readouterr().err


def test_global_list_isolates_malformed_repo_entries(tmp_path, monkeypatch, capsys):
    # A single malformed entry must not discard the user's other repos (#5020):
    # drop only the bad one, keep the good ones, and do NOT back up the file.
    manifest = tmp_path / "global-manifest.json"
    good = {"source_path": "graph.json", "node_count": 2}
    manifest.write_text(
        json.dumps({"version": 1, "repos": {"goodA": good, "bad": "oops", "goodB": good}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(global_graph, "_GLOBAL_MANIFEST", manifest)

    assert global_graph.global_list() == {"goodA": good, "goodB": good}

    assert manifest.is_file()  # not backed up
    assert not list(tmp_path.glob("global-manifest.json.corrupt.*"))
    err = capsys.readouterr().err
    assert "dropped 1 malformed repo" in err and "bad" in err


def test_global_list_drops_all_malformed_entries_without_backup(tmp_path, monkeypatch):
    # An all-malformed repos map is still a valid shape: it collapses to empty
    # rather than being backed up.
    manifest = tmp_path / "global-manifest.json"
    manifest.write_text(json.dumps({"repos": {"legacy": "invalid"}}), encoding="utf-8")
    monkeypatch.setattr(global_graph, "_GLOBAL_MANIFEST", manifest)

    assert global_graph.global_list() == {}
    assert manifest.is_file()
    assert not list(tmp_path.glob("global-manifest.json.corrupt.*"))


def test_global_list_preserves_valid_manifest(tmp_path, monkeypatch):
    manifest = tmp_path / "global-manifest.json"
    repos = {"project": {"source_path": "graph.json", "node_count": 2}}
    manifest.write_text(json.dumps({"version": 1, "repos": repos}), encoding="utf-8")
    monkeypatch.setattr(global_graph, "_GLOBAL_MANIFEST", manifest)

    assert global_graph.global_list() == repos
    assert manifest.is_file()
