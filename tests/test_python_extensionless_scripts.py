"""Extensionless scripts reach the Python member-call pass only when they are Python.

An extensionless file has no suffix to gate on, so before the shebang stamp a
`#!/usr/bin/env node` or `ruby` script was "unknown" and passed: a Python
`Inner.go()` bound a node `Inner`, a node `Inner` tripped the single-definition
guard for a Python `Inner`, and node/ruby `Inner.go()` bound a Python `Inner`.
The language is read from the shebang through the path extract() was given, and
for an unchanged file of a changed-files rebuild through the scan root, never
the working directory. A Python shebang script still binds.
"""

from graphify.extract import extract

INNER_PY = "class Inner:\n    @staticmethod\n    def go():\n        return 1\n"
USE_PY = "from inner import Inner\n\ndef run():\n    Inner.go()\n"
BARE_USE_PY = "def run():\n    Inner.go()\n"
NODE_INNER = "#!/usr/bin/env node\nclass Inner {\n  static go() { return 1; }\n}\nmodule.exports = { Inner };\n"
NODE_CALLER = "#!/usr/bin/env node\nfunction toolMain() {\n  Inner.go();\n}\n"
RUBY_CALLER = "#!/usr/bin/env ruby\ndef tool_main\n  Inner.go()\nend\n"
PYTHON_CALLER = "#!/usr/bin/env python3\nfrom inner import Inner\n\ndef tool_main():\n    Inner.go()\n"
PYTHON_INNER = "#!/usr/bin/env python3\nclass Inner:\n    @staticmethod\n    def go():\n        return 1\n"

# What a changed-files rebuild carries for an unchanged file (cli.py builds the
# same shape from graph.json).
_CONTEXT_NODE_KEYS = ("id", "label", "source_file", "file_type", "type", "_callable",
                      "_callable_class", "_py_property", "_py_fixture", "metadata")
_CONTEXT_RELATIONS = ("contains", "method", "inherits", "imports", "imports_from")


def _write(src, files):
    src.mkdir(exist_ok=True)
    for name, text in files.items():
        (src / name).write_text(text)
    return [src / name for name in files]


def _calls(result, known_nodes=()):
    nodes = {n["id"]: n for n in [*known_nodes, *result["nodes"]]}
    return {(nodes[e["source"]].get("label"), nodes[e["source"]].get("source_file"),
             nodes[e["target"]].get("label"), nodes[e["target"]].get("source_file"))
            for e in result["edges"]
            if e["relation"] == "calls" and e["source"] in nodes and e["target"] in nodes}


def _fresh(tmp_path, files):
    src = tmp_path / "src"
    paths = _write(src, files)
    return _calls(extract(paths, root=src, cache_root=tmp_path / "cache", parallel=False))


def _rebuild(tmp_path, files, changed, rewrite=None):
    """Full build, then a changed-files rebuild of `changed` with the rest as context.
    `rewrite` replaces files on disk between the two builds."""
    src = tmp_path / "src"
    paths = _write(src, files)
    full = extract(paths, root=src, cache_root=tmp_path / "cache-full", parallel=False)
    _write(src, rewrite or {})
    context_nodes = [{k: n[k] for k in _CONTEXT_NODE_KEYS if k in n} for n in full["nodes"]
                     if n.get("source_file") and n["source_file"] != changed]
    context_edges = [{k: e[k] for k in ("source", "target", "relation", "source_file")}
                     for e in full["edges"]
                     if e.get("relation") in _CONTEXT_RELATIONS
                     and e.get("source_file") and e["source_file"] != changed]
    result = extract([src / changed], root=src, cache_root=tmp_path / "cache-rebuild",
                     parallel=False, resolution_context_nodes=context_nodes,
                     resolution_context_edges=context_edges)
    return _calls(result, full["nodes"])


def _edges_from(calls, caller):
    return {(dst_label, dst_file) for label, _, dst_label, dst_file in calls if label == caller}


def test_extensionless_node_class_is_not_a_python_target(tmp_path):
    calls = _fresh(tmp_path, {"use.py": BARE_USE_PY, "tool": NODE_INNER})
    assert (".go()", "tool") not in _edges_from(calls, "run()")


def test_extensionless_node_class_does_not_trip_python_guard(tmp_path):
    calls = _fresh(tmp_path, {"inner.py": INNER_PY, "use.py": USE_PY, "tool": NODE_INNER})
    assert (".go()", "inner.py") in _edges_from(calls, "run()")


def test_extensionless_node_caller_skips_python_pass(tmp_path):
    calls = _fresh(tmp_path, {"inner.py": INNER_PY, "tool": NODE_CALLER})
    assert (".go()", "inner.py") not in _edges_from(calls, "toolMain()")


def test_extensionless_ruby_caller_skips_python_pass(tmp_path):
    calls = _fresh(tmp_path, {"inner.py": INNER_PY, "tool": RUBY_CALLER})
    assert (".go()", "inner.py") not in _edges_from(calls, "tool_main()")


def test_extensionless_python_script_still_binds(tmp_path):
    calls = _fresh(tmp_path, {"inner.py": INNER_PY, "tool": PYTHON_CALLER})
    assert (".go()", "inner.py") in _edges_from(calls, "tool_main()")


def test_rebuild_unchanged_node_class_is_not_a_python_target(tmp_path, monkeypatch):
    # The decoy in the working directory is a Python `tool`: a read relative to the
    # cwd would call the unchanged node script Python and bind it.
    decoy = tmp_path / "cwd"
    _write(decoy, {"tool": PYTHON_INNER})
    monkeypatch.chdir(decoy)
    calls = _rebuild(tmp_path, {"use.py": BARE_USE_PY, "tool": NODE_INNER}, "use.py")
    assert (".go()", "tool") not in _edges_from(calls, "run()")


def test_rebuild_unchanged_node_class_does_not_trip_python_guard(tmp_path):
    files = {"inner.py": INNER_PY, "use.py": USE_PY, "tool": NODE_INNER}
    calls = _rebuild(tmp_path, files, "use.py")
    assert (".go()", "inner.py") in _edges_from(calls, "run()")


def test_rebuild_unchanged_python_script_target_still_binds(tmp_path, monkeypatch):
    # The decoy in the working directory is a node `tool`: a read relative to the
    # cwd would call the unchanged Python script non-Python and drop the edge.
    decoy = tmp_path / "cwd"
    _write(decoy, {"tool": NODE_INNER})
    monkeypatch.chdir(decoy)
    calls = _rebuild(tmp_path, {"use.py": BARE_USE_PY, "tool": PYTHON_INNER}, "use.py")
    assert (".go()", "tool") in _edges_from(calls, "run()")


def test_rebuild_of_only_a_python_script_binds(tmp_path):
    # No `.py` among the changed paths: the pass must still wake for the script.
    calls = _rebuild(tmp_path, {"inner.py": INNER_PY, "tool": PYTHON_CALLER}, "tool")
    assert (".go()", "inner.py") in _edges_from(calls, "tool_main()")


def test_rebuild_unknown_interpreter_target_is_unknown_and_binds(tmp_path):
    # The unchanged script was extracted as Python, but its shebang now names an
    # interpreter with no extractor: unknown, so it passes; only a shebang that
    # maps to a non-Python extractor shuts a script out.
    wrapped = PYTHON_INNER.replace("python3", "python-wrapper", 1)
    calls = _rebuild(tmp_path, {"use.py": BARE_USE_PY, "tool": PYTHON_INNER}, "use.py",
                     rewrite={"tool": wrapped})
    assert (".go()", "tool") in _edges_from(calls, "run()")
