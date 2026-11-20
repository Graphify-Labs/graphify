"""Tests for plain-import member call resolution (#5253).

A call on a plainly-imported module (`import b` then `b.f()`) where `b.py` lives
in a non-package directory outside the caller's directory (e.g. `bin/b.py`)
should bind the call to `b.f()`, not fall back to the file node `b.py`.
"""

from pathlib import Path
from graphify.extract import extract
from graphify.build import build_from_json


def test_plain_import_member_call_binds_to_function_node(tmp_path):
    bin_dir = tmp_path / "bin"
    scripts_dir = tmp_path / "skills" / "s" / "scripts"
    bin_dir.mkdir(parents=True)
    scripts_dir.mkdir(parents=True)

    b_file = bin_dir / "b.py"
    b_file.write_text("def f():\n    return 1\n", encoding="utf-8")

    c_file = scripts_dir / "c.py"
    c_file.write_text(
        "import sys\n"
        "sys.path.insert(0, '../../bin')\n"
        "import b\n\n"
        "def other():\n"
        "    return b.f()\n",
        encoding="utf-8",
    )

    result = extract([b_file, c_file], cache_root=tmp_path)
    edges = result["edges"]

    # The call from other() must target f(), NOT the file node b.py
    calls = [
        e for e in edges
        if e.get("relation") == "calls"
        and e.get("source_file", "").endswith("c.py")
    ]
    assert len(calls) == 1, f"Expected 1 call edge, got: {calls}"
    call = calls[0]

    nodes_by_id = {n["id"]: n for n in result["nodes"]}
    target_node = nodes_by_id.get(call["target"])
    assert target_node is not None, f"Target node {call['target']} not found in graph nodes"
    assert target_node.get("label") == "f()", f"Expected target f(), got {target_node}"

    # Import edge must target b.py file node
    imports = [
        e for e in edges
        if e.get("relation") in ("imports", "imports_from")
        and e.get("source_file", "").endswith("c.py")
        and e.get("target") != "sys"
    ]
    assert len(imports) == 1, f"Expected 1 import edge to b, got: {imports}"
    assert imports[0]["target"] == target_node["source_file"].replace("/", "_").replace(".py", "") or \
           nodes_by_id[imports[0]["target"]].get("label") == "b.py"

    # End-to-end graph build must preserve call -> f() and not collapse onto file node
    G = build_from_json(result)
    call_edges = [
        d for _, _, d in G.edges(data=True)
        if d.get("relation") == "calls"
        and str(d.get("source_file", "")).endswith("c.py")
    ]
    assert len(call_edges) == 1
    assert call_edges[0].get("_tgt") == target_node["id"]
    assert G.nodes[call_edges[0]["_tgt"]].get("label") == "f()"


def test_plain_import_with_alias_member_call(tmp_path):
    bin_dir = tmp_path / "bin"
    scripts_dir = tmp_path / "scripts"
    bin_dir.mkdir(parents=True)
    scripts_dir.mkdir(parents=True)

    b_file = bin_dir / "b.py"
    b_file.write_text("def f():\n    return 1\n", encoding="utf-8")

    c_file = scripts_dir / "c.py"
    c_file.write_text(
        "import sys\n"
        "sys.path.insert(0, '../bin')\n"
        "import b as helper\n\n"
        "def other():\n"
        "    return helper.f()\n",
        encoding="utf-8",
    )

    result = extract([b_file, c_file], cache_root=tmp_path)
    edges = result["edges"]
    nodes_by_id = {n["id"]: n for n in result["nodes"]}

    calls = [
        e for e in edges
        if e.get("relation") == "calls"
        and e.get("source_file", "").endswith("c.py")
    ]
    assert len(calls) == 1
    assert nodes_by_id[calls[0]["target"]].get("label") == "f()"


def test_plain_import_ambiguous_stem_does_not_bind(tmp_path):
    bin_dir = tmp_path / "bin"
    tools_dir = tmp_path / "tools"
    scripts_dir = tmp_path / "scripts"
    bin_dir.mkdir(parents=True)
    tools_dir.mkdir(parents=True)
    scripts_dir.mkdir(parents=True)

    (bin_dir / "b.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (tools_dir / "b.py").write_text("def f():\n    return 2\n", encoding="utf-8")

    c_file = scripts_dir / "c.py"
    c_file.write_text(
        "import sys\n"
        "sys.path.insert(0, '../bin')\n"
        "sys.path.insert(0, '../tools')\n"
        "import b\n\n"
        "def other():\n"
        "    return b.f()\n",
        encoding="utf-8",
    )

    result = extract([bin_dir / "b.py", tools_dir / "b.py", c_file], cache_root=tmp_path)
    edges = result["edges"]
    nodes_by_id = {n["id"]: n for n in result["nodes"]}

    # Ambiguous module name should NOT bind to either file's f()
    calls = [
        e for e in edges
        if e.get("relation") == "calls"
        and e.get("source_file", "").endswith("c.py")
    ]
    for call in calls:
        target_node = nodes_by_id.get(call["target"])
        if target_node:
            assert target_node.get("label") != "f()", "Ambiguous import must not resolve to f()"


def test_plain_import_stdlib_module_does_not_capture_local_file(tmp_path):
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir(parents=True)

    # Local file with stdlib name
    log_file = scripts_dir / "logging.py"
    log_file.write_text("def info(msg):\n    pass\n", encoding="utf-8")

    c_file = scripts_dir / "c.py"
    c_file.write_text(
        "import logging\n\n"
        "def other():\n"
        "    return logging.info('test')\n",
        encoding="utf-8",
    )

    result = extract([log_file, c_file], cache_root=tmp_path)
    edges = result["edges"]
    nodes_by_id = {n["id"]: n for n in result["nodes"]}

    # `import logging` refers to stdlib, not the local logging.py
    calls = [
        e for e in edges
        if e.get("relation") == "calls"
        and e.get("source_file", "").endswith("c.py")
    ]
    # Call to stdlib logging.info is an external module call or pruned, not local logging.py::info
    for call in calls:
        target_node = nodes_by_id.get(call["target"])
        if target_node and target_node.get("source_file", "").endswith("logging.py"):
            assert target_node.get("label") != "info()", "Stdlib import must not bind to local logging.py"

