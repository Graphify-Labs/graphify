"""Tests for honouring `os.path.join(os.path.dirname(__file__), ...)` and
`Path(__file__).parent / ...` sys.path roots (#5252).

`_extract_python_rationale`'s sys.path.insert/append scan (#5253) only recognized a
bare string literal argument (`sys.path.insert(0, '../../bin')`). The far more common
real-world idiom resolves the path relative to the importing file itself instead of
cwd (`os.path.join(os.path.dirname(__file__), "../../bin")`, `Path(__file__).parent /
"bin"`), which was not recognized at all: the file's sys.path entries stayed empty, so
a module name duplicated across two independent, sys.path-extended trees fabricated an
`ambiguous_python_import_*` node for both importers instead of each resolving to its
own tree's file, exactly as it already did for the literal-string form.
"""

from graphify.extract import extract


def test_os_path_join_dirname_sys_path_resolves_per_tree(tmp_path):
    a_bin = tmp_path / "a" / "bin"
    a_skill = tmp_path / "a" / "skills" / "x"
    b_bin = tmp_path / "b" / "bin"
    b_skill = tmp_path / "b" / "skills" / "y"
    for d in (a_bin, a_skill, b_bin, b_skill):
        d.mkdir(parents=True)

    (a_bin / "lib.py").write_text("def f():\n    return 'a'\n", encoding="utf-8")
    (b_bin / "lib.py").write_text("def f():\n    return 'b'\n", encoding="utf-8")

    a_run = a_skill / "run.py"
    a_run.write_text(
        "import sys, os\n"
        "sys.path.insert(0, os.path.join(os.path.dirname(__file__), \"../../bin\"))\n"
        "import lib\n\n"
        "def main():\n"
        "    return lib.f()\n",
        encoding="utf-8",
    )
    b_run = b_skill / "run.py"
    b_run.write_text(
        "import sys, os\n"
        "sys.path.insert(0, os.path.join(os.path.dirname(__file__), \"../../bin\"))\n"
        "import lib\n\n"
        "def main():\n"
        "    return lib.f()\n",
        encoding="utf-8",
    )

    paths = [a_bin / "lib.py", b_bin / "lib.py", a_run, b_run]
    result = extract(paths, cache_root=tmp_path, root=tmp_path)
    edges = result["edges"]
    nodes_by_id = {n["id"]: n for n in result["nodes"]}

    def target_label(source_file_suffix: str, relation: str) -> set[str]:
        return {
            nodes_by_id[e["target"]].get("label")
            for e in edges
            if e.get("relation") == relation
            and e.get("source_file", "").endswith(source_file_suffix)
            and e.get("target") in nodes_by_id
        }

    a_imports = target_label("a/skills/x/run.py", "imports") | target_label(
        "a/skills/x/run.py", "imports_from"
    )
    b_imports = target_label("b/skills/y/run.py", "imports") | target_label(
        "b/skills/y/run.py", "imports_from"
    )
    assert "a/bin/lib.py" in a_imports or "lib.py" in a_imports
    assert "a/bin/lib.py" not in b_imports
    assert "b/bin/lib.py" in b_imports or "lib.py" in b_imports

    assert not any(str(n.get("id", "")).startswith("ambiguous_python_import_") for n in result["nodes"])

    a_calls = [
        e for e in edges
        if e.get("relation") == "calls" and e.get("source_file", "").endswith("a/skills/x/run.py")
    ]
    assert len(a_calls) == 1
    assert nodes_by_id[a_calls[0]["target"]].get("label") == "f()"
    assert nodes_by_id[a_calls[0]["target"]].get("source_file", "").endswith("a/bin/lib.py")

    b_calls = [
        e for e in edges
        if e.get("relation") == "calls" and e.get("source_file", "").endswith("b/skills/y/run.py")
    ]
    assert len(b_calls) == 1
    assert nodes_by_id[b_calls[0]["target"]].get("label") == "f()"
    assert nodes_by_id[b_calls[0]["target"]].get("source_file", "").endswith("b/bin/lib.py")


def test_pathlib_parent_sys_path_resolves_per_tree(tmp_path):
    a_bin = tmp_path / "a" / "bin"
    a_skill = tmp_path / "a" / "skills" / "x"
    b_bin = tmp_path / "b" / "bin"
    b_skill = tmp_path / "b" / "skills" / "y"
    for d in (a_bin, a_skill, b_bin, b_skill):
        d.mkdir(parents=True)

    (a_bin / "lib.py").write_text("def f():\n    return 'a'\n", encoding="utf-8")
    (b_bin / "lib.py").write_text("def f():\n    return 'b'\n", encoding="utf-8")

    a_run = a_skill / "run.py"
    a_run.write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, str(Path(__file__).parent.parent / \"bin\"))\n"
        "import lib\n\n"
        "def main():\n"
        "    return lib.f()\n",
        encoding="utf-8",
    )
    b_run = b_skill / "run.py"
    b_run.write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, str(Path(__file__).parent.parent / \"bin\"))\n"
        "import lib\n\n"
        "def main():\n"
        "    return lib.f()\n",
        encoding="utf-8",
    )

    paths = [a_bin / "lib.py", b_bin / "lib.py", a_run, b_run]
    result = extract(paths, cache_root=tmp_path, root=tmp_path)
    nodes_by_id = {n["id"]: n for n in result["nodes"]}

    assert not any(str(n.get("id", "")).startswith("ambiguous_python_import_") for n in result["nodes"])

    a_calls = [
        e for e in result["edges"]
        if e.get("relation") == "calls" and e.get("source_file", "").endswith("a/skills/x/run.py")
    ]
    assert len(a_calls) == 1
    assert nodes_by_id[a_calls[0]["target"]].get("source_file", "").endswith("a/bin/lib.py")

    b_calls = [
        e for e in result["edges"]
        if e.get("relation") == "calls" and e.get("source_file", "").endswith("b/skills/y/run.py")
    ]
    assert len(b_calls) == 1
    assert nodes_by_id[b_calls[0]["target"]].get("source_file", "").endswith("b/bin/lib.py")


def test_os_path_join_multi_segment_entry_resolves(tmp_path):
    bin_dir = tmp_path / "bin"
    scripts_dir = tmp_path / "skills" / "s" / "scripts"
    bin_dir.mkdir(parents=True)
    scripts_dir.mkdir(parents=True)

    (bin_dir / "helper.py").write_text("def f():\n    return 1\n", encoding="utf-8")

    c_file = scripts_dir / "c.py"
    c_file.write_text(
        "import sys, os\n"
        "sys.path.insert(0, os.path.join(os.path.dirname(__file__), \"..\", \"..\", \"bin\"))\n"
        "import helper\n\n"
        "def other():\n"
        "    return helper.f()\n",
        encoding="utf-8",
    )

    result = extract([bin_dir / "helper.py", c_file], cache_root=tmp_path, root=tmp_path)
    nodes_by_id = {n["id"]: n for n in result["nodes"]}

    calls = [
        e for e in result["edges"]
        if e.get("relation") == "calls" and e.get("source_file", "").endswith("c.py")
    ]
    assert len(calls) == 1
    assert nodes_by_id[calls[0]["target"]].get("label") == "f()"


def test_dynamic_sys_path_argument_stays_unrecognized(tmp_path):
    """A non-literal sys.path argument (a variable, not a recognized call shape) must
    keep today's fail-closed behaviour: no entry is recorded for it, so a genuine
    cross-tree collision it cannot explain away still ends up dangling, not guessed."""
    a_bin = tmp_path / "a" / "bin"
    a_skill = tmp_path / "a" / "skills" / "x"
    b_bin = tmp_path / "b" / "bin"
    for d in (a_bin, a_skill, b_bin):
        d.mkdir(parents=True)

    (a_bin / "lib.py").write_text("def f():\n    return 'a'\n", encoding="utf-8")
    (b_bin / "lib.py").write_text("def f():\n    return 'b'\n", encoding="utf-8")

    a_run = a_skill / "run.py"
    a_run.write_text(
        "import sys, os\n"
        "computed = os.environ.get('EXTRA_PATH', '../../bin')\n"
        "sys.path.insert(0, computed)\n"
        "import lib\n\n"
        "def main():\n"
        "    return lib.f()\n",
        encoding="utf-8",
    )

    paths = [a_bin / "lib.py", b_bin / "lib.py", a_run]
    result = extract(paths, cache_root=tmp_path, root=tmp_path)
    nodes_by_id = {n["id"]: n for n in result["nodes"]}

    calls = [
        e for e in result["edges"]
        if e.get("relation") == "calls" and e.get("source_file", "").endswith("a/skills/x/run.py")
    ]
    for call in calls:
        target = nodes_by_id.get(call["target"])
        if target:
            assert target.get("label") != "f()", "Dynamic sys.path argument must not be guessed at"
