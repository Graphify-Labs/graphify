"""Native ``graphify explain`` direction and learning-state tests."""

import graphify.__main__ as mainmod
from graphify.helix.state import new_state
from tests.native_helpers import make_loaded


def _store(tmp_path, *, learning=None):
    state = new_state(learning=learning or {})
    return make_loaded(
        tmp_path,
        nodes=[
            {"id": "validate", "label": "validateSanitySession()", "source_file": "server/validate.ts", "source_location": "L1", "file_type": "code"},
            {"id": "patch", "label": "createPatchHandler()", "source_file": "server/patch.ts", "file_type": "code"},
            {"id": "edit", "label": "createEditHandler()", "source_file": "server/edit.ts", "file_type": "code"},
            {"id": "stringify", "label": "stableStringify()", "source_file": "shared/stringify.ts", "file_type": "code"},
        ],
        edges=[
            {"source": "patch", "target": "validate", "relation": "calls"},
            {"source": "edit", "target": "validate", "relation": "calls"},
            {"source": "validate", "target": "stringify", "relation": "calls"},
        ],
        state=state,
    )


def _run(monkeypatch, capsys, store, query):
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", "explain", query, "--store", str(store)])
    mainmod.main()
    return capsys.readouterr().out


def test_callee_shows_callers_inbound_and_callee_outbound(monkeypatch, tmp_path, capsys):
    store = _store(tmp_path).store_path
    out = _run(monkeypatch, capsys, store, "validateSanitySession")
    assert "<-- createPatchHandler() [calls]" in out
    assert "<-- createEditHandler() [calls]" in out
    assert "--> stableStringify() [calls]" in out


def test_caller_shows_callee_outbound(monkeypatch, tmp_path, capsys):
    store = _store(tmp_path).store_path
    out = _run(monkeypatch, capsys, store, "createPatchHandler")
    assert "--> validateSanitySession() [calls]" in out


def test_source_path_exact_match_prefers_file_node(monkeypatch, tmp_path, capsys):
    loaded = make_loaded(
        tmp_path,
        nodes=[
            {"id": "route_get", "label": "GET()", "source_file": "app/route.ts", "source_location": "L42"},
            {"id": "route", "label": "route.ts", "source_file": "app/route.ts", "source_location": "L1"},
        ],
        edges=[{"source": "route", "target": "route_get", "relation": "contains"}],
    )
    out = _run(monkeypatch, capsys, loaded.store_path, "app/route.ts")
    assert "Node: route.ts" in out and "ID:        route" in out


def test_learning_state_is_rendered(monkeypatch, tmp_path, capsys):
    learning = {
        "version": 1,
        "nodes": {"validate": {"status": "preferred", "score": 2.4, "uses": 3}},
    }
    store = _store(tmp_path, learning=learning).store_path
    out = _run(monkeypatch, capsys, store, "validate")
    assert "Lesson: preferred source (start here) — 3 useful, score=2.4" in out


def test_unannotated_node_has_no_lesson(monkeypatch, tmp_path, capsys):
    out = _run(monkeypatch, capsys, _store(tmp_path).store_path, "validate")
    assert "Lesson:" not in out
