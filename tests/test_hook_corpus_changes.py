import json
from pathlib import Path

import pytest

from graphify.watch import _rebuild_code


@pytest.mark.parametrize("change", ["rename", "ignore", "unignore"])
def test_hook_reconciles_corpus_only_changes(tmp_path, monkeypatch, change):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app.py").write_text("def main(): return 0\n", encoding="utf-8")
    source = tmp_path / "util.py"
    source.write_text("def helper(): return 1\n", encoding="utf-8")
    ignore = tmp_path / ".graphifyignore"
    if change == "unignore":
        ignore.write_text("util.py\n", encoding="utf-8")

    def rebuild(paths=None):
        return _rebuild_code(tmp_path, changed_paths=paths,
                             no_cluster=True, acquire_lock=False)

    def graph():
        return json.loads((tmp_path / "graphify-out/graph.json").read_text(encoding="utf-8"))

    assert rebuild()
    assert any(n["id"] == "util_helper" for n in graph()["nodes"]) == (change != "unignore")
    if change == "rename":
        destination = source.rename(tmp_path / "util.py.bak")
        paths = [Path(destination.name)]
    else:
        ignore.write_text("util.py\n" if change == "ignore" else "", encoding="utf-8")
        paths = [Path(ignore.name)]
    assert rebuild(paths)
    result = graph()
    assert any(n["id"] == "app_main" for n in result["nodes"])
    assert any(n["id"] == "util_helper" for n in result["nodes"]) == (change == "unignore")
    assert any(e.get("source_file") == "util.py" and e.get("relation") == "contains"
               for e in result["links"]) == (change == "unignore")
