"""Current extraction diagnostics survive warm reconciliation without stale replay."""
from __future__ import annotations

import json

from graphify.watch import _rebuild_code

KEYS = ("diagnostics", "qml_failures", "qt_failures")


def fixture(root):
    """A real empty QML edit yields informational QML_EMPTY, not a parse failure."""
    (root / "keep.py").write_text("def keep(): return 7\n", encoding="utf-8")
    source = root / "Main.qml"
    source.write_text("Item {}\n", encoding="utf-8")
    return source


def rebuild(root):
    assert _rebuild_code(root, no_cluster=True, force=True, acquire_lock=False)
    return json.loads((root / "graphify-out/graph.json").read_text(encoding="utf-8"))


def test_real_cold_and_warm_products_keep_current_empty_diagnostic_keys(tmp_path):
    """An unchanged real source tree keeps the cold extraction's complete metadata."""
    fixture(tmp_path)
    cold = rebuild(tmp_path)
    assert {key: cold[key] for key in KEYS} == {key: [] for key in KEYS}
    # The normal empty-list comparison shortcut may correctly leave a warm
    # unchanged file alone. A real AST edit requires publication and therefore
    # exercises reconciliation's current-diagnostic projection rather than skip.
    (tmp_path / "keep.py").write_text("def keep(): return 7\ndef added(): return keep()\n", encoding="utf-8")
    warm = rebuild(tmp_path)
    assert {key: warm[key] for key in KEYS} == {key: cold[key] for key in KEYS}


def test_current_source_diagnostics_replace_prior_graph_metadata_without_replay(tmp_path):
    """Real QML_EMPTY appears on edit; subsequent healthy source clears old payloads."""
    source = fixture(tmp_path)
    rebuild(tmp_path)
    source.write_bytes(b"")
    empty = rebuild(tmp_path)
    assert [item["code"] for item in empty["diagnostics"]] == ["QML_EMPTY"]
    assert empty["qml_failures"] == empty["qt_failures"] == []
    # Prior graph metadata is deliberately stale. Only actual current producer
    # results may populate these fields; reconciliation must not replay it.
    path = tmp_path / "graphify-out/graph.json"
    for key in KEYS:
        empty[key] = [{"code": "old-diagnostic", "source_file": "Main.qml"}]
    path.write_text(json.dumps(empty), encoding="utf-8")
    source.write_text("Item {}\n", encoding="utf-8")
    healthy = rebuild(tmp_path)
    assert {key: healthy[key] for key in KEYS} == {key: [] for key in KEYS}
    before = path.read_bytes()
    rebuild(tmp_path)
    assert path.read_bytes() == before
