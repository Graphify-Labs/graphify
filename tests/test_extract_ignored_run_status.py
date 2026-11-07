"""The CLI must preserve ignore reporting and machine-readable run status."""
import json
import sys

import pytest

import graphify.__main__ as mainmod


@pytest.mark.parametrize("has_visible_code", [False, True])
def test_ignored_sources_keep_run_status(
    monkeypatch, tmp_path, capsys, has_visible_code
):
    corpus = tmp_path / "corpus"
    hidden = corpus / "hidden"
    hidden.mkdir(parents=True)
    (hidden / "secret.py").write_text("def hidden(): pass\n", encoding="utf-8")
    (corpus / ".graphifyignore").write_text("hidden/\n", encoding="utf-8")
    if has_visible_code:
        (corpus / "keep.py").write_text("def keep(): return 1\n", encoding="utf-8")
    out = tmp_path / "output"
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(sys, "argv", [
        "graphify", "extract", str(corpus), "--code-only", "--no-cluster",
        "--out", str(out),
    ])

    try:
        mainmod.main()
    except SystemExit as error:
        assert error.code in (None, 0)

    text = capsys.readouterr().out
    assert "1 path(s) ignored by ignore rules" in text
    assert "'hidden/'" in text
    assert "secret.py" not in text
    status = json.loads((out / "graphify-out" / "last_run.json").read_text(encoding="utf-8"))
    assert status["ok"] is True
    assert status["exit_code"] == 0
    assert status["files_dispatched"] == int(has_visible_code)
