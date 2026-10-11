"""pytest fixture parameters type member calls in tests.

`def test_x(runner): runner.invoke(cli)` names the fixture `runner` as a parameter; pytest passes
what the fixture returns. The parameter has no annotation, so the call used to get no edge. It is
now typed from the fixture pytest would pick: the test's own module first, then the conftest.py of
its directory and of each directory above it.
"""
from __future__ import annotations

import json
from pathlib import Path

from graphify.extract import extract

_RUNNER = "class CliRunner:\n    def invoke(self, cli):\n        return cli\n"
_OTHER = "class Other:\n    def invoke(self, cli):\n        return cli\n"


def _calls(tmp_path: Path, files: dict[str, str]):
    paths = []
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        paths.append(p)
    r = extract(paths, root=tmp_path, cache_root=tmp_path / "graphify-out", parallel=False)
    nodes = {n["id"]: n for n in r["nodes"]}
    owner = {e["target"]: nodes[e["source"]]["label"] for e in r["edges"] if e["relation"] == "method"}
    return {(nodes[e["source"]]["label"], owner.get(e["target"], ""), nodes[e["target"]]["label"])
            for e in r["edges"] if e["relation"] == "calls"}, r


_CONFTEST = "import pytest\nfrom app.testing import CliRunner\n\n\n@pytest.fixture\ndef runner():\n    return CliRunner()\n"


def test_conftest_fixture_types_the_test_parameter(tmp_path: Path):
    calls, _ = _calls(tmp_path, {
        "app/__init__.py": "",
        "app/testing.py": _RUNNER,
        "app/other.py": _OTHER,
        "tests/conftest.py": _CONFTEST,
        "tests/test_cli.py": "def test_run(runner):\n    runner.invoke(None)\n",
    })
    assert ("test_run()", "CliRunner", ".invoke()") in calls
    assert not any(c[0] == "test_run()" and c[1] == "Other" for c in calls)


def test_module_fixture_wins_over_conftest(tmp_path: Path):
    calls, _ = _calls(tmp_path, {
        "app/__init__.py": "",
        "app/testing.py": _RUNNER,
        "app/other.py": _OTHER,
        "tests/conftest.py": _CONFTEST,
        "tests/test_cli.py": ("import pytest\nfrom app.other import Other\n\n\n@pytest.fixture\n"
                              "def runner():\n    return Other()\n\n\ndef test_run(runner):\n    runner.invoke(None)\n"),
    })
    assert ("test_run()", "Other", ".invoke()") in calls
    assert ("test_run()", "CliRunner", ".invoke()") not in calls


def test_untyped_nearer_fixture_shadows_a_typed_one(tmp_path: Path):
    calls, _ = _calls(tmp_path, {
        "app/__init__.py": "",
        "app/testing.py": _RUNNER,
        "tests/conftest.py": _CONFTEST,
        "tests/test_cli.py": ("import pytest\n\n\n@pytest.fixture\ndef runner(make):\n    return make()\n\n\n"
                              "def test_run(runner):\n    runner.invoke(None)\n"),
    })
    assert not any(c[0] == "test_run()" and c[2] == ".invoke()" for c in calls)


def test_parent_directory_conftest_is_visible_and_a_sibling_one_is_not(tmp_path: Path):
    calls, _ = _calls(tmp_path, {
        "app/__init__.py": "",
        "app/testing.py": _RUNNER,
        "tests/conftest.py": _CONFTEST,
        "tests/unit/test_a.py": "def test_a(runner):\n    runner.invoke(None)\n",
        "other/conftest.py": _CONFTEST.replace("def runner", "def runner2"),
        "other/test_b.py": "def test_b(runner):\n    runner.invoke(None)\n",
    })
    assert ("test_a()", "CliRunner", ".invoke()") in calls
    assert not any(c[0] == "test_b()" for c in calls)


def test_rebound_parameter_and_non_test_function_are_not_typed(tmp_path: Path):
    calls, _ = _calls(tmp_path, {
        "app/__init__.py": "",
        "app/testing.py": _RUNNER,
        "app/use.py": "def helper(runner):\n    runner.invoke(None)\n",
        "tests/conftest.py": _CONFTEST,
        "tests/test_cli.py": "def test_run(runner, other):\n    runner = other\n    runner.invoke(None)\n",
    })
    assert not any(c[0] in ("helper()", "test_run()") and c[2] == ".invoke()" for c in calls)


def test_yield_fixture_with_iterator_annotation(tmp_path: Path):
    calls, _ = _calls(tmp_path, {
        "app/__init__.py": "",
        "app/testing.py": _RUNNER,
        "tests/conftest.py": ("from typing import Iterator\n\nimport pytest\nfrom app.testing import CliRunner\n\n\n"
                              "@pytest.fixture(scope='module')\ndef runner() -> Iterator[CliRunner]:\n"
                              "    r = make()\n    yield r\n"),
        "tests/test_cli.py": "class TestCli:\n    def test_run(self, runner):\n        runner.invoke(None)\n",
    })
    assert (".test_run()", "CliRunner", ".invoke()") in calls


def test_changed_test_file_rebuild_keeps_the_fixture_edge(tmp_path: Path):
    from graphify.watch import _rebuild_code

    files = {
        "app/__init__.py": "",
        "app/testing.py": _RUNNER,
        "tests/conftest.py": _CONFTEST,
        "tests/test_cli.py": "def test_run(runner):\n    runner.invoke(None)\n",
    }
    roots = []
    for name in ("inc", "full"):
        root = tmp_path / name
        for fname, body in files.items():
            (root / fname).parent.mkdir(parents=True, exist_ok=True)
            (root / fname).write_text(body, encoding="utf-8")
        roots.append(root)
    inc, full = roots
    assert _rebuild_code(inc, no_cluster=True, acquire_lock=False, force=True)
    for root in roots:
        p = root / "tests" / "test_cli.py"
        p.write_text(p.read_text(encoding="utf-8") + "# touched\n", encoding="utf-8")
    assert _rebuild_code(inc, changed_paths=[inc / "tests" / "test_cli.py"], no_cluster=True, acquire_lock=False)
    assert _rebuild_code(full, no_cluster=True, acquire_lock=False, force=True)

    def calls_of(root):
        g = json.loads((root / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
        return {(e["source"], e["target"]) for e in g.get("links", g.get("edges", [])) if e["relation"] == "calls"}

    assert calls_of(inc) == calls_of(full)
    assert any(t.endswith("clirunner_invoke") for _, t in calls_of(full))


def test_schema_bump_retires_entries_cached_without_fixture_markers(tmp_path: Path, monkeypatch):
    import graphify.cache as cache_mod
    from graphify.cache import save_cached
    from graphify.extract import extract_python

    files = {
        "app/__init__.py": "",
        "app/testing.py": _RUNNER,
        "tests/conftest.py": _CONFTEST,
        "tests/test_cli.py": "def test_run(runner):\n    runner.invoke(None)\n",
    }
    paths = []
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        paths.append(p)
    current = cache_mod._AST_CACHE_SCHEMA
    monkeypatch.setattr(cache_mod, "_EXTRACTOR_VERSION", "same-version")
    monkeypatch.setattr(cache_mod, "_AST_CACHE_SCHEMA", 7)  # last schema without the markers
    monkeypatch.setattr(cache_mod, "_cleaned_ast_dirs", set())
    for p in paths:
        stale = extract_python(p)
        for node in stale["nodes"]:
            node.pop("_py_fixture", None)
        for rc in stale.get("raw_calls", []):
            rc.pop("_python_fixture_param", None)
        save_cached(p, stale, root=tmp_path, cache_root=tmp_path, kind="ast")
    monkeypatch.setattr(cache_mod, "_AST_CACHE_SCHEMA", current)
    monkeypatch.setattr(cache_mod, "_cleaned_ast_dirs", set())
    r = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    nodes = {n["id"]: n for n in r["nodes"]}
    assert any(e["relation"] == "calls" and nodes[e["source"]]["label"] == "test_run()"
               and nodes[e["target"]]["label"] == ".invoke()" for e in r["edges"])
