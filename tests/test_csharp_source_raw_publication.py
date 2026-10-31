"""INC-QML-89 raw updates publish the same explicit source storage profile."""
from __future__ import annotations

import json

import pytest

from graphify.source_relationships import FIELD, storage_key
from tests.test_csharp_local_persistence import fixture
from tests.test_qt_final_incremental_parity import run
from tests.test_qt_semantic_correction_updates import products


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_raw_publication_persists_profile_keys_and_settles(tmp_path, monkeypatch, operation):
    """The actual raw writer declares multigraph mode before accepted publication."""
    fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    run(tmp_path, monkeypatch, operation)
    data = json.loads((tmp_path / "graphify-out/graph.json").read_text())
    assert data["multigraph"] is True and data["graph"][FIELD] == {"contract_version": 1}
    assert all(edge["key"] == storage_key(edge["source"], edge["target"], edge["relation"]) for edge in data["links"])
    before = products(tmp_path)
    run(tmp_path, monkeypatch, operation, [])
    assert products(tmp_path) == before
