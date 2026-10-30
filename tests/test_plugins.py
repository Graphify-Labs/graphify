"""Extractor plugins (graphify/plugins.py): discovery, matching, running, failure isolation."""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from graphify import plugins
from graphify.detect import FileType, classify_file
from graphify.extract import _bypass_cache, _get_extractor, extract


@pytest.fixture(autouse=True)
def clean_registry(monkeypatch):
    """Every test starts with no plugins and leaves none behind."""
    monkeypatch.delenv(plugins.ENV_PLUGINS, raising=False)
    monkeypatch.delenv(plugins.ENV_DISABLE, raising=False)
    monkeypatch.setattr(plugins, "_entry_points", lambda: [])
    plugins._extra.clear()
    plugins.reload()
    yield
    plugins._extra.clear()
    plugins.reload()


def _node(path: Path, name: str) -> dict:
    return {"id": f"{path.stem}_{name}", "label": name, "file_type": "code", "source_file": str(path)}


def _per_file(path: Path) -> dict:
    return {"nodes": [_node(path, "f")], "edges": []}


# ── building plugins ───────────────────────────────────────────────────────────

def test_dict_plugin_needs_no_graphify_import():
    [p] = plugins.coerce({"name": "x", "suffixes": ["xyz"], "extract": _per_file})
    assert p.suffixes == (".xyz",) and not p.batch


def test_factory_and_list_forms():
    one = {"name": "a", "suffixes": [".a"], "extract": _per_file}
    two = {"name": "b", "suffixes": [".b"], "extract": _per_file}
    assert [p.name for p in plugins.coerce(lambda: [one, two])] == ["a", "b"]


@pytest.mark.parametrize(
    "bad, message",
    [
        ({"suffixes": [".a"], "extract": _per_file}, "name"),
        ({"name": "x", "extract": _per_file}, "matches nothing"),
        ({"name": "x", "suffixes": [".a"]}, "exactly one"),
        ({"name": "x", "suffixes": [".a"], "extract": _per_file, "extract_batch": lambda p, c: {}}, "exactly one"),
        ({"name": "x", "suffixes": [".a"], "extract": _per_file, "file_type": "audio"}, "file_type"),
        ({"name": "x", "suffixes": [".a"], "extract": _per_file, "api": 99}, "API"),
    ],
)
def test_invalid_plugins_are_rejected_with_a_reason(bad, message):
    with pytest.raises(ValueError, match=message):
        plugins.coerce(bad)


# ── discovery ──────────────────────────────────────────────────────────────────

def test_entry_point_discovery(monkeypatch):
    class EP:
        name, value = "demo", "demo_pkg:PLUGIN"

        def load(self):
            return {"name": "demo", "suffixes": [".demo"], "extract": _per_file}

    monkeypatch.setattr(plugins, "_entry_points", lambda: [EP()])
    plugins.reload()
    assert [p.name for p in plugins.all_plugins()] == ["demo"]
    assert plugins.match("a/b.demo").name == "demo"


def test_broken_entry_point_is_reported_not_fatal(monkeypatch, capsys):
    class EP:
        name, value = "bad", "bad_pkg:X"

        def load(self):
            raise ImportError("no module named bad_pkg")

    monkeypatch.setattr(plugins, "_entry_points", lambda: [EP()])
    plugins.reload()
    assert plugins.all_plugins() == []
    assert "no module named bad_pkg" in capsys.readouterr().err


def test_env_spec_loads_a_module_not_installed_as_a_package(tmp_path, monkeypatch):
    (tmp_path / "myplug.py").write_text(
        "def _x(path):\n    return {'nodes': [], 'edges': []}\n"
        "PLUGIN = {'name': 'local', 'suffixes': ['.loc'], 'extract': _x}\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv(plugins.ENV_PLUGINS, "myplug:PLUGIN")
    plugins.reload()
    assert plugins.match("a.loc").name == "local"


def test_off_and_disable_switches(monkeypatch):
    plugins.register({"name": "x", "suffixes": [".x"], "extract": _per_file})
    assert plugins.match("a.x")
    monkeypatch.setenv(plugins.ENV_PLUGINS, "off")
    plugins.reload()
    assert plugins.match("a.x") is None


def test_unavailable_plugin_does_not_match_and_says_why(capsys):
    plugins.register({"name": "x", "suffixes": [".x"], "extract": _per_file, "available": lambda: "tool X not found"})
    assert plugins.match("a.x") is None
    assert "tool X not found" in capsys.readouterr().err


# ── matching ───────────────────────────────────────────────────────────────────

def test_matching_by_filename_glob_and_priority():
    plugins.register([
        {"name": "low", "filenames": ["Buildfile"], "extract": _per_file},
        {"name": "glob", "globs": ["*.tpl.*"], "extract": _per_file},
        {"name": "hi", "suffixes": [".dup"], "extract": _per_file, "priority": 5},
        {"name": "lo", "suffixes": [".dup"], "extract": _per_file, "priority": 1},
    ])
    assert plugins.match("x/Buildfile").name == "low"
    assert plugins.match("x/a.tpl.html").name == "glob"
    assert plugins.match("x/a.dup").name == "hi"
    assert plugins.match("x/other.txt") is None


def test_builtin_extractor_wins_unless_override(tmp_path):
    py = tmp_path / "a.py"
    py.write_text("def f():\n    pass\n")
    plugins.register({"name": "p", "suffixes": [".py"], "extract": _per_file})
    assert _get_extractor(py).__name__ == "extract_python"
    plugins.register({"name": "p2", "suffixes": [".py"], "extract": _per_file, "override_builtin": True, "priority": 9})
    assert _get_extractor(py).__name__ != "extract_python"


def test_plugin_claims_file_type_in_detect(tmp_path):
    f = tmp_path / "a.zz"
    f.write_text("x")
    assert classify_file(f) is None
    plugins.register({"name": "z", "suffixes": [".zz"], "extract": _per_file})
    assert classify_file(f) == FileType.CODE
    plugins.register({"name": "z", "suffixes": [".zz"], "extract": _per_file, "file_type": "document"})
    assert classify_file(f) == FileType.DOCUMENT


# ── running ────────────────────────────────────────────────────────────────────

def test_per_file_plugin_end_to_end(tmp_path):
    a, b = tmp_path / "a.zz", tmp_path / "b.zz"
    a.write_text("1")
    b.write_text("2")
    plugins.register({"name": "z", "suffixes": [".zz"], "extract": _per_file})
    out = extract([a, b], cache_root=tmp_path / "c", parallel=False)
    assert {n["label"] for n in out["nodes"]} == {"f"} and len(out["nodes"]) == 2
    assert not out.get("errors")


def test_batch_plugin_runs_once_over_all_files(tmp_path):
    calls = []

    def batch(paths, ctx):
        calls.append(sorted(p.name for p in paths))
        return {p: {"nodes": [_node(p, "n")], "edges": []} for p in paths}

    files = [tmp_path / f"{n}.zz" for n in "abc"]
    for f in files:
        f.write_text("x")
    plugins.register({"name": "z", "suffixes": [".zz"], "extract_batch": batch})
    out = extract(files, cache_root=tmp_path / "c", parallel=False)
    assert calls == [["a.zz", "b.zz", "c.zz"]]
    assert len(out["nodes"]) == 3


def test_batch_results_are_never_cached(tmp_path):
    f = tmp_path / "a.zz"
    f.write_text("x")
    plugins.register({"name": "z", "suffixes": [".zz"], "extract_batch": lambda ps, c: {}})
    assert _bypass_cache(f)
    plugins.register({"name": "z", "suffixes": [".zz"], "extract": _per_file})
    assert not _bypass_cache(f)
    plugins.register({"name": "z", "suffixes": [".zz"], "extract": _per_file, "cross_file": True})
    assert _bypass_cache(f)


def test_ctx_is_passed_only_to_functions_that_take_it(tmp_path):
    seen = {}

    def with_ctx(path, ctx):
        seen["root"] = ctx.root
        return _per_file(path)

    f = tmp_path / "a.zz"
    f.write_text("x")
    plugins.register({"name": "z", "suffixes": [".zz"], "extract": with_ctx})
    extract([f], cache_root=tmp_path / "c", root=tmp_path, parallel=False)
    assert seen["root"] == tmp_path.resolve()


def test_cache_key_change_invalidates_cached_results(tmp_path):
    f = tmp_path / "a.zz"
    f.write_text("x")
    runs = []

    def ex(path):
        runs.append(1)
        return _per_file(path)

    for key in ("1", "1", "2"):
        plugins.register({"name": "z", "suffixes": [".zz"], "extract": ex, "cache_key": key})
        extract([f], cache_root=tmp_path / "c", parallel=False)
    assert len(runs) == 2  # second run served from cache, third re-ran


# ── failure isolation: no fallback, no corrupt graph ───────────────────────────

def test_crashing_plugin_becomes_a_visible_error(tmp_path, capsys):
    f = tmp_path / "a.zz"
    f.write_text("x")
    plugins.register({"name": "z", "suffixes": [".zz"], "extract": lambda p: 1 / 0})
    out = extract([f], cache_root=tmp_path / "c", parallel=False)
    assert out["nodes"] == []
    assert out["failed_sources"] == [str(f)]  # graphify's own failure channel; nothing falls back
    captured = capsys.readouterr()
    assert "plugin z: ZeroDivisionError" in captured.out + captured.err


def test_failing_batch_marks_every_file_with_the_error(tmp_path, capsys):
    files = [tmp_path / "a.zz", tmp_path / "b.zz"]
    for f in files:
        f.write_text("x")

    def boom(paths, ctx):
        raise RuntimeError("tool exploded")

    plugins.register({"name": "z", "suffixes": [".zz"], "extract_batch": boom})
    res = plugins.run_batches(files, tmp_path)
    assert all("tool exploded" in r["error"] for r in res.values()) and len(res) == 2
    assert "tool exploded" in capsys.readouterr().err


@pytest.mark.parametrize(
    "bad",
    [
        "nope",
        {"nodes": "x", "edges": []},
        {"nodes": [{"label": "no id"}], "edges": []},
        {"nodes": [], "edges": [{"source": "a"}]},
    ],
)
def test_malformed_output_is_rejected(bad, tmp_path):
    p = plugins.coerce({"name": "z", "suffixes": [".zz"], "extract": lambda x: bad})[0]
    assert "error" in plugins.normalise(bad, tmp_path / "a.zz", p)


def test_normalise_fills_optional_fields(tmp_path):
    p = plugins.coerce({"name": "z", "suffixes": [".zz"], "extract": _per_file})[0]
    f = tmp_path / "a.zz"
    out = plugins.normalise(
        {"nodes": [{"id": "a", "label": "a"}, {"id": "b", "label": "b"}],
         "edges": [{"source": "a", "target": "b", "relation": "calls"}]}, f, p)
    assert out["nodes"][0]["file_type"] == "code" and out["nodes"][0]["source_file"] == str(f)
    e = out["edges"][0]
    assert e["confidence"] == "EXTRACTED" and e["confidence_score"] == 1.0 and e["source_file"] == str(f)


def test_post_process_can_rewrite_results(tmp_path):
    f = tmp_path / "a.zz"
    f.write_text("x")

    def tag(res, path):
        for n in res["nodes"]:
            n["label"] = n["label"].upper()
        return res

    plugins.register({"name": "z", "suffixes": [".zz"], "extract": _per_file, "post_process": tag})
    out = extract([f], cache_root=tmp_path / "c", parallel=False)
    assert [n["label"] for n in out["nodes"]] == ["F"]


# ── workers: a plugin must work under the process pool ─────────────────────────

def test_plugin_works_in_worker_processes(tmp_path):
    (tmp_path / "plug").mkdir()
    (tmp_path / "plug" / "wplug.py").write_text(textwrap.dedent("""
        def ex(path):
            return {"nodes": [{"id": path.stem, "label": path.stem, "file_type": "code",
                               "source_file": str(path)}], "edges": []}
        PLUGIN = {"name": "w", "suffixes": [".wk"], "extract": ex}
    """))
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    for i in range(25):  # above _PARALLEL_THRESHOLD
        (corpus / f"f{i}.wk").write_text("x")
    script = tmp_path / "run.py"
    script.write_text(textwrap.dedent(f"""
        import json
        from pathlib import Path
        from graphify.extract import extract
        if __name__ == "__main__":
            out = extract(sorted(Path({str(corpus)!r}).glob("*.wk")), cache_root=Path({str(tmp_path / 'c')!r}), parallel=True)
            print(json.dumps({{"n": len(out["nodes"])}}))
    """))
    env = {**__import__("os").environ, plugins.ENV_PLUGINS: "wplug:PLUGIN", "PYTHONPATH": str(tmp_path / "plug")}
    cp = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, env=env, cwd=tmp_path)
    assert json.loads(cp.stdout.strip().splitlines()[-1]) == {"n": 25}, cp.stderr[-500:]


# ── CLI ────────────────────────────────────────────────────────────────────────

def test_plugins_command_lists_plugins_as_json(tmp_path):
    (tmp_path / "clip.py").write_text(
        "PLUGIN = {'name': 'cli', 'suffixes': ['.cl'], 'extract_batch': lambda p, c: {}, 'cache_key': 'v3'}\n"
    )
    env = {**__import__("os").environ, plugins.ENV_PLUGINS: "clip:PLUGIN", "PYTHONPATH": str(tmp_path)}
    cp = subprocess.run([sys.executable, "-m", "graphify", "plugins", "--json"], capture_output=True, text=True, env=env, cwd=tmp_path)
    data = json.loads(cp.stdout)
    assert data["api"] == plugins.API_VERSION
    assert data["plugins"][0]["name"] == "cli" and data["plugins"][0]["mode"] == "batch"
