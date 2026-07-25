"""The top-level CLI help advertises every MultiDiGraph entry point."""

from __future__ import annotations

import sys


def test_main_help_documents_multigraph_flags(capsys, monkeypatch):
    from graphify.__main__ import main

    monkeypatch.setattr(sys, "argv", ["graphify", "--help"])
    main()
    output = capsys.readouterr().out

    assert "force MultiDiGraph post-build simulation" in output
    assert "preserve parallel relations in a directed multigraph" in output
    assert "preserve parallel directed relations (also preserves existing mode)" in output
    assert "preserve parallel directed relations in a MultiDiGraph" in output
