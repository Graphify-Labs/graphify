"""Global graph commands recover from JSON with the wrong manifest shape."""

import json

import pytest

from graphify import global_graph


@pytest.mark.parametrize("payload", [None, [], {}, {"repos": []}, {"repos": {"legacy": "invalid"}}])
def test_global_list_backs_up_wrong_manifest_shape(tmp_path, monkeypatch, capsys, payload):
    manifest = tmp_path / "global-manifest.json"
    original = json.dumps(payload)
    manifest.write_text(original, encoding="utf-8")
    monkeypatch.setattr(global_graph, "_GLOBAL_MANIFEST", manifest)

    assert global_graph.global_list() == {}

    assert not manifest.exists()
    backup, = tmp_path.glob("global-manifest.json.corrupt.*")
    assert backup.read_text(encoding="utf-8") == original
    assert "moved to" in capsys.readouterr().err


def test_global_list_preserves_valid_manifest(tmp_path, monkeypatch):
    manifest = tmp_path / "global-manifest.json"
    repos = {"project": {"source_path": "graph.json", "node_count": 2}}
    manifest.write_text(json.dumps({"version": 1, "repos": repos}), encoding="utf-8")
    monkeypatch.setattr(global_graph, "_GLOBAL_MANIFEST", manifest)

    assert global_graph.global_list() == repos
    assert manifest.is_file()
