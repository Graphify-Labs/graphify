"""Real watch/CLI fixtures for publication-version recovery, without fake facts."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import graphify
import graphify.__main__ as entrypoint
import graphify.extract as extraction
import graphify.watch as watch
from graphify.paths import load_node_link_graph
from tests.test_cpp_allocated_member_updates import full_fields
from tests.test_qt_final_incremental_parity import project as qt_project

VERSION_KEY = "projection_version"


def project(root, monkeypatch, profile="python"):
    """Keep independent source files so partial events cannot masquerade as full."""
    root.mkdir()
    monkeypatch.chdir(root)
    monkeypatch.setenv("GRAPHIFY_VIZ_NODE_LIMIT", "0")
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    if profile == "qt":
        qt_project(root)
    else:
        (root / "first.py").write_text("def source():\n    return 1\n", encoding="utf-8")
        (root / "second.py").write_text(
            "from first import source\ndef caller():\n    return source()\n", encoding="utf-8")
        (root / "untouched.py").write_text("def retained(): return 7\n", encoding="utf-8")
        if profile == "csharp":
            (root / "Service.cs").write_text(
                "class Service { int Value; int Run() { int Local() => 1; return Local(); } }\n",
                encoding="utf-8")
    return root


def run(root, monkeypatch, *, raw=True, operation="watch", changes=None):
    """Run actual coordination, producers and publishers; suppress only skill upkeep."""
    if operation == "manual":
        monkeypatch.setattr(entrypoint, "_check_skill_version", lambda *_: None)
        monkeypatch.setattr(entrypoint, "_refresh_stale_skills", lambda: None)
        arguments = ["graphify", "update", str(root)]
        if raw:
            arguments.append("--no-cluster")
        monkeypatch.setattr(entrypoint.sys, "argv", arguments)
        entrypoint.main()
    else:
        assert watch._rebuild_code(root, no_cluster=raw, changed_paths=changes)
    return load_node_link_graph(root / "graphify-out/graph.json")


def products(root):
    """All accepted top-level outputs/state, excluding native coordination requests."""
    return {path.name: path.read_bytes() for path in (root / "graphify-out").iterdir()
            if path.is_file() and path.name not in {".rebuild.lock", ".pending_changes", ".pending_full"}}


def caches(root):
    directory = root / "graphify-out/cache"
    return {path.relative_to(directory).as_posix(): path.read_bytes()
            for path in directory.rglob("*") if path.is_file()}


def state(root):
    return json.loads((root / "graphify-out" / watch._BUILD_STATE_NAME).read_text(encoding="utf-8"))


def legacy(root, value=0, *, missing=False, obsolete_score=False):
    """Model an accepted old projection while keeping every old skip fingerprint valid."""
    graph = root / "graphify-out/graph.json"
    if obsolete_score:
        payload = json.loads(graph.read_text(encoding="utf-8"))
        links = payload.get("links", payload.get("edges"))
        assert links
        links[0]["confidence_score"] = .1234
        graph.write_text(json.dumps(payload), encoding="utf-8")
    previous = state(root)
    if missing:
        previous.pop(VERSION_KEY, None)
    else:
        previous[VERSION_KEY] = value
    current = graph.stat()
    previous.update(graph_size=current.st_size, graph_mtime_ns=current.st_mtime_ns)
    (graph.parent / watch._BUILD_STATE_NAME).write_text(json.dumps(previous), encoding="utf-8")


def spy_extract(monkeypatch):
    """Observe the real admitted targets without replacing extraction results."""
    calls, real = [], extraction.extract

    def counted(paths, *args, **kwargs):
        calls.append(tuple(Path(path).name for path in paths))
        return real(paths, *args, **kwargs)

    monkeypatch.setattr(extraction, "extract", counted)
    return calls


def prior_cache_retained(root, before):
    after = caches(root)
    assert before and all(after.get(key) == value for key, value in before.items())


# The child selects the same source package/root but an independent cold output
# before imports. It never moves/deletes the accepted publication or its cache.
_COLD = """
from pathlib import Path
import sys
package, root, raw = sys.argv[1:]
sys.path.insert(0, package)
import graphify
assert Path(graphify.__file__).resolve() == Path(package, 'graphify/__init__.py').resolve()
from graphify.watch import _rebuild_code
sys.exit(0 if _rebuild_code(Path(root), no_cluster=raw == '1') else 1)
"""


def cold(root, raw):
    retained = Path(tempfile.mkdtemp(prefix="projection-cold-", dir=root.parent)).resolve()
    assert retained.parent == root.parent.resolve()
    output = retained / "products"
    before = products(root), caches(root)
    environment = dict(os.environ, GRAPHIFY_OUT=str(output), GRAPHIFY_NO_AUTO_REFRESH="1")
    with (retained / "child.log").open("wb") as stream:
        result = subprocess.run(
            [sys.executable, "-I", "-X", "utf8", "-c", _COLD,
             str(Path(graphify.__file__).resolve().parent.parent), str(root), "1" if raw else "0"],
            cwd=root, env=environment, stdout=stream, stderr=subprocess.STDOUT)
    result.check_returncode()
    assert (products(root), caches(root)) == before
    return full_fields(load_node_link_graph(output / "graph.json"))
