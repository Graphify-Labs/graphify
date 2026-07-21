"""Learning-state explain regression not covered by the compact native suite."""

import graphify.__main__ as mainmod
from graphify.helix.state import new_state
from tests.native_helpers import make_loaded


def test_explain_shows_contested_and_stale_lesson(monkeypatch, tmp_path, capsys):
    state = new_state(learning={
        "version": 1,
        "nodes": {
            "validate": {
                "status": "contested",
                "score": -0.1,
                "uses": 2,
                "neg": 1,
                "verdict": "dead end",
                "source_file": "server/missing.ts",
                "code_fingerprint": "deadbeef",
            }
        },
    })
    loaded = make_loaded(
        tmp_path,
        nodes=[{"id": "validate", "label": "validateSanitySession()", "source_file": "server/missing.ts"}],
        state=state,
    )
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "explain", "validate", "--store", str(loaded.store_path)],
    )
    mainmod.main()
    output = capsys.readouterr().out
    assert "Lesson: contested (useful 2 / dead-end 1)" in output
    assert "[code changed since — re-verify]" in output
