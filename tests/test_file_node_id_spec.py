"""Regression tests for path-derived AST node IDs.

AST file-level node IDs must match the skill.md repo-relative stem spec so AST
and semantic extraction produce the SAME node for a file instead of disconnected
ghosts.

skill.md spec (line ~390):
    stem = {repo_relative_path_without_ext}, lowercased, non-alphanumeric -> _
    examples:
        src/auth/session.py + ValidateToken -> src_auth_session_validatetoken
        match/script/pipeline_step.py (file node) -> match_script_pipeline_step
        setup.py (top-level) -> setup
"""
from pathlib import Path

from graphify.extract import extract


def _file_nodes(extraction: dict) -> list[dict]:
    # File-level nodes carry a label equal to the file's basename.
    return [
        n for n in extraction["nodes"]
        if n.get("source_file", "").endswith(n.get("label", "\0"))
        and n.get("file_type") == "code"
    ]


def test_file_node_id_uses_repo_relative_stem_no_extension(tmp_path):
    """match/script/pipeline_step.py -> file node id 'match_script_pipeline_step'."""
    sub = tmp_path / "match" / "script"
    sub.mkdir(parents=True)
    f = sub / "pipeline_step.py"
    f.write_text("def run():\n    pass\n")

    extraction = extract([f], cache_root=tmp_path)
    ids = {n["id"] for n in extraction["nodes"]}

    assert "match_script_pipeline_step" in ids, (
        f"expected spec-format file id 'match_script_pipeline_step', got {sorted(ids)}"
    )
    # The old buggy full-path-with-extension id must be gone.
    assert "match_script_pipeline_step_py" not in ids
    assert not any(i.endswith("_py") for i in ids if "pipeline_step" in i)


def test_top_level_file_node_id_is_bare_stem(tmp_path):
    """A file directly at the project root collapses to just its stem."""
    f = tmp_path / "setup.py"
    f.write_text("def configure():\n    pass\n")

    extraction = extract([f], cache_root=tmp_path)
    ids = {n["id"] for n in extraction["nodes"]}

    assert "setup" in ids, f"expected bare stem 'setup', got {sorted(ids)}"
    assert "setup_py" not in ids


def test_top_level_file_SYMBOL_ids_use_bare_stem(tmp_path):
    """A SYMBOL in a root-level file must use the bare-stem prefix (`setup_configure`),
    not pick up the project-root directory name (`<rootdir>_setup_configure`). The
    semantic subagent emits the bare-stem form per skill.md, so an absolute-parent
    stem here splits the symbol into two ghost nodes (#1096). Pass ABSOLUTE paths,
    as the CLI does, to exercise the root-relative remap."""
    f = tmp_path / "main.py"
    f.write_text("def run():\n    return 1\n")

    extraction = extract([f.resolve()], cache_root=tmp_path)
    ids = {n["id"] for n in extraction["nodes"]}

    assert "main_run" in ids, f"expected bare-stem symbol 'main_run', got {sorted(ids)}"
    # The root directory name must NOT appear in any symbol id.
    rootname = tmp_path.name.lower().replace("-", "_")
    assert not any(rootname in i for i in ids), (
        f"root dir name leaked into ids: {sorted(ids)}"
    )

    # contains edge file -> symbol must connect with the canonical ids.
    contains = [e for e in extraction["edges"]
                if e["relation"] == "contains" and e["target"] == "main_run"]
    assert contains and contains[0]["source"] == "main"


def test_single_directory_nested_file_ids_stay_readable(tmp_path):
    """A one-directory nested file keeps the same concise repo-relative stem."""
    sub = tmp_path / "sub"
    sub.mkdir()
    f = sub / "mod.py"
    f.write_text("def work():\n    return 2\n")

    extraction = extract([f.resolve()], cache_root=tmp_path)
    ids = {n["id"] for n in extraction["nodes"]}
    assert "sub_mod" in ids
    assert "sub_mod_work" in ids


def test_symbol_and_file_ids_share_the_same_stem(tmp_path):
    """Symbol ids already use {repo_relative_stem}_{name}; the file node must share
    that stem prefix so 'contains' edges connect file -> symbol."""
    sub = tmp_path / "match" / "script"
    sub.mkdir(parents=True)
    f = sub / "pipeline_step.py"
    f.write_text("def run():\n    pass\n\nclass Stage:\n    pass\n")

    extraction = extract([f], cache_root=tmp_path)
    ids = {n["id"] for n in extraction["nodes"]}

    assert "match_script_pipeline_step" in ids          # file node
    assert "match_script_pipeline_step_stage" in ids     # class symbol shares stem

    # The file -> class 'contains' edge must reference the real file node id.
    contains = [
        e for e in extraction["edges"]
        if e["relation"] == "contains" and e["target"] == "match_script_pipeline_step_stage"
    ]
    assert contains, "no 'contains' edge to the class symbol"
    assert contains[0]["source"] == "match_script_pipeline_step", (
        f"contains edge source {contains[0]['source']!r} does not match file node"
    )


def test_cross_file_import_edges_stay_connected(tmp_path):
    """Changing the file-id format must not orphan import edges: the import
    target must resolve to the imported file's (new-format) node id."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "models.py").write_text("class User:\n    pass\n")
    (pkg / "auth.py").write_text(
        "from models import User\n\n"
        "class Session:\n"
        "    def check(self):\n"
        "        return User()\n"
    )

    files = [pkg / "models.py", pkg / "auth.py"]
    extraction = extract(files, cache_root=tmp_path)
    ids = {n["id"] for n in extraction["nodes"]}

    assert "pkg_models" in ids
    assert "pkg_auth" in ids

    # Every edge endpoint that looks like a file node must point at a real node
    # (no dangling '*_py' ghosts left behind by the old format).
    node_ids = ids
    for e in extraction["edges"]:
        for endpoint in (e["source"], e["target"]):
            assert not endpoint.endswith("_py"), (
                f"edge endpoint {endpoint!r} kept the old extension-suffixed format"
            )
        # imports_from edges between files must land on a known node.
        if e["relation"] == "imports_from" and e["source"] == "pkg_auth":
            assert e["target"] in node_ids or "models" in e["target"]


def test_deep_same_named_files_use_full_repo_relative_identity(tmp_path):
    """Same-named files below different package roots must not merge through the
    old one-parent stem form (`src_index`)."""
    package_a = tmp_path / "packages" / "a" / "src"
    package_b = tmp_path / "packages" / "b" / "src"
    package_a.mkdir(parents=True)
    package_b.mkdir(parents=True)
    (package_a / "index.py").write_text("class Parser:\n    pass\n")
    (package_b / "index.py").write_text("class Contract:\n    pass\n")

    extraction = extract(
        [(package_a / "index.py").resolve(), (package_b / "index.py").resolve()],
        cache_root=tmp_path,
    )
    ids = {n["id"] for n in extraction["nodes"]}

    assert "packages_a_src_index" in ids
    assert "packages_b_src_index" in ids
    assert "packages_a_src_index_parser" in ids
    assert "packages_b_src_index_contract" in ids
    assert "src_index" not in ids


def test_repo_root_name_does_not_affect_deep_symbol_ids(tmp_path):
    """The repo folder name belongs in graph metadata, not in node IDs."""
    root_one = tmp_path / "checkout-one"
    root_two = tmp_path / "checkout-two"
    rel_path = Path("packages/a/src/index.py")
    for root in (root_one, root_two):
        source_file = root / rel_path
        source_file.parent.mkdir(parents=True)
        source_file.write_text("def parse():\n    return 1\n")

    first = extract([(root_one / rel_path).resolve()], cache_root=root_one)
    second = extract([(root_two / rel_path).resolve()], cache_root=root_two)

    first_ids = {n["id"] for n in first["nodes"]}
    second_ids = {n["id"] for n in second["nodes"]}
    assert first_ids == second_ids
    assert "packages_a_src_index_parse" in first_ids
    assert not any("checkout" in node_id for node_id in first_ids)
