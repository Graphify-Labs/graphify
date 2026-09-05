import json
import os
import sys
from collections import Counter
from pathlib import Path

import pytest

from graphify.build import build_from_json
from graphify.extract import extract_python, extract, collect_files, _make_id, extract_bash, extract_json, _DISPATCH

FIXTURES = Path(__file__).parent / "fixtures"


def test_make_id_strips_dots_and_underscores():
    assert _make_id("_auth") == "auth"
    assert _make_id(".httpx._client") == "httpx_client"


def test_make_id_consistent():
    """Same input always produces same output."""
    assert _make_id("foo", "Bar") == _make_id("foo", "Bar")


def test_make_id_no_leading_trailing_underscores():
    result = _make_id("__init__")
    assert not result.startswith("_")
    assert not result.endswith("_")


def test_extract_python_finds_class():
    result = extract_python(FIXTURES / "sample.py")
    labels = [n["label"] for n in result["nodes"]]
    assert "Transformer" in labels


def test_extract_python_finds_methods():
    result = extract_python(FIXTURES / "sample.py")
    labels = [n["label"] for n in result["nodes"]]
    assert any("__init__" in l or "forward" in l for l in labels)


def test_extract_python_no_dangling_edges():
    """All edge sources must reference a known node (targets may be external imports)."""
    result = extract_python(FIXTURES / "sample.py")
    node_ids = {n["id"] for n in result["nodes"]}
    for edge in result["edges"]:
        assert edge["source"] in node_ids, f"Dangling source: {edge['source']}"


def test_structural_edges_are_extracted():
    """contains / method / inherits / imports edges must always be EXTRACTED."""
    result = extract_python(FIXTURES / "sample.py")
    structural = {"contains", "method", "inherits", "imports", "imports_from"}
    for edge in result["edges"]:
        if edge["relation"] in structural:
            assert edge["confidence"] == "EXTRACTED", f"Expected EXTRACTED: {edge}"


def test_extract_merges_multiple_files():
    files = list(FIXTURES.glob("*.py"))
    result = extract(files)
    assert len(result["nodes"]) > 0
    assert result["input_tokens"] == 0


def test_extract_disambiguates_duplicate_symbol_ids_by_source_path(tmp_path):
    first = tmp_path / "apps/api/Program.cs"
    second = tmp_path / "tools/api/Program.cs"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    first.write_text("class Program { void Run() {} }\n", encoding="utf-8")
    second.write_text("class Program { void Run() {} }\n", encoding="utf-8")

    result = extract([first, second], cache_root=tmp_path)
    program_nodes = [
        node for node in result["nodes"]
        if node["label"] == "Program" and node.get("source_file", "").endswith("Program.cs")
    ]

    assert len(program_nodes) == 2
    assert len({node["id"] for node in program_nodes}) == 2

    node_ids = {node["id"] for node in result["nodes"]}
    program_by_source = {node["source_file"]: node["id"] for node in program_nodes}
    file_nodes_by_source = {
        node["source_file"]: node["id"]
        for node in result["nodes"]
        if node["label"] == "Program.cs"
    }

    assert set(program_by_source) == set(file_nodes_by_source)
    contains_edges = [
        edge for edge in result["edges"]
        if edge["relation"] == "contains" and edge["source_file"] in program_by_source
    ]
    assert len(contains_edges) == 2
    for edge in contains_edges:
        assert edge["source"] == file_nodes_by_source[edge["source_file"]]
        assert edge["target"] == program_by_source[edge["source_file"]]

    for edge in result["edges"]:
        if edge["relation"] in {"contains", "method"}:
            assert edge["source"] in node_ids, f"Dangling structural source: {edge}"
            assert edge["target"] in node_ids, f"Dangling structural target: {edge}"


def test_cpp_unresolved_base_class_stubs_stay_disambiguated_by_file(tmp_path):
    """Two different files' same-named, otherwise-undefined base class must not
    collapse onto one shared stub node.

    The C++ base_class_clause handler used to build its stub inline instead of
    calling ensure_named_node(), so it never tagged the stub with origin_file.
    Without that tag, _disambiguate_colliding_node_ids couldn't tell file A's
    reference to unresolved `Base` apart from file B's, and every file's
    unresolved base class merged onto one bare id -- which could then collide
    with an unrelated same-named real definition anywhere else in the corpus.
    """
    first = tmp_path / "a" / "Foo.cpp"
    second = tmp_path / "b" / "Bar.cpp"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    first.write_text("class Foo : public Base {};\n", encoding="utf-8")
    second.write_text("class Bar : public Base {};\n", encoding="utf-8")

    result = extract([first, second], cache_root=tmp_path)
    base_stubs = [
        node for node in result["nodes"]
        if node["label"] == "Base" and not node.get("source_file")
    ]
    assert len(base_stubs) == 2
    assert len({node["id"] for node in base_stubs}) == 2

    inherits_edges = [e for e in result["edges"] if e["relation"] == "inherits"]
    assert len(inherits_edges) == 2
    assert len({e["target"] for e in inherits_edges}) == 2


def test_cross_file_type_annotation_refs_resolve_to_single_node(tmp_path):
    """#1402: a class defined once but referenced via type annotations in N other
    files must NOT create 1+N phantom duplicate nodes (with the referencing file's
    path — extension and all — baked into the id, e.g. ``pkg_a_py_thing``). The
    annotation references resolve to the single canonical definition.

    Contrast with test_extract_disambiguates_...: genuinely *defined* duplicates
    stay separate; only cross-file *references* collapse onto the real node."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "thing.py").write_text("class Thing:\n    def run(self):\n        return 1\n", encoding="utf-8")
    (pkg / "a.py").write_text("from pkg.thing import Thing\ndef use_a(obj: Thing) -> Thing:\n    return obj\n", encoding="utf-8")
    (pkg / "b.py").write_text("from pkg.thing import Thing\ndef use_b(obj: Thing) -> Thing:\n    return obj\n", encoding="utf-8")

    result = extract([pkg / "thing.py", pkg / "a.py", pkg / "b.py"], cache_root=tmp_path)

    thing_nodes = [n for n in result["nodes"] if n["label"] == "Thing"]
    assert len(thing_nodes) == 1, [n["id"] for n in thing_nodes]
    # The tell-tale phantom signature is the referencing file's path (with .py
    # extension) baked into the id — must not appear.
    assert "_py" not in thing_nodes[0]["id"], thing_nodes[0]["id"]


def test_go_cross_file_type_refs_resolve_to_single_node(tmp_path):
    """#1402 (Go): the sourceless-stub fix landed in six extractors but the Go copy
    of ``ensure_named_node`` was missed, so a Go type defined once but referenced via
    parameter/return types in N sibling files produced 1+N phantom duplicate nodes
    with the referencing file's path (extension and all) baked into the id
    (e.g. ``pkg_a_go_thing``). Same-package references must resolve to the single
    canonical type node instead."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "thing.go").write_text(
        "package pkg\n\ntype Thing struct{}\n\nfunc (t Thing) Run() int { return 1 }\n",
        encoding="utf-8",
    )
    (pkg / "a.go").write_text(
        "package pkg\n\nfunc UseA(obj Thing) Thing { return obj }\n", encoding="utf-8"
    )
    (pkg / "b.go").write_text(
        "package pkg\n\nfunc UseB(obj Thing) Thing { return obj }\n", encoding="utf-8"
    )

    result = extract([pkg / "thing.go", pkg / "a.go", pkg / "b.go"], cache_root=tmp_path)

    thing_nodes = [n for n in result["nodes"] if n["label"] == "Thing"]
    assert len(thing_nodes) == 1, [n["id"] for n in thing_nodes]
    # The phantom signature is the referencing file's path (with .go extension)
    # baked into the id — must not appear.
    assert "_go" not in thing_nodes[0]["id"], thing_nodes[0]["id"]


def test_imported_type_stubs_do_not_collide_across_source_files(tmp_path):
    """#1462: imported stdlib/type stubs with the same label are distinct uses
    when there is no single project definition to rewire onto. They need the
    referencing file as a disambiguator while still keeping ``source_file`` empty
    so real project definitions can be rewired by #1402."""
    first = tmp_path / "pkg/a.py"
    second = tmp_path / "pkg/b.py"
    first.parent.mkdir(parents=True)
    first.write_text("from pathlib import Path\ndef use_a(p: Path):\n    return p\n", encoding="utf-8")
    second.write_text("from pathlib import Path\ndef use_b(p: Path):\n    return p\n", encoding="utf-8")

    result = extract([first, second], cache_root=tmp_path)
    path_nodes = [node for node in result["nodes"] if node["label"] == "Path"]

    assert len(path_nodes) == 2
    assert len({node["id"] for node in path_nodes}) == 2
    assert all(not node.get("source_file") for node in path_nodes)


def test_origin_file_is_not_serialized_into_extract_output(tmp_path):
    """origin_file is an internal disambiguation hint (#1462) consumed only by the
    colliding-id pass during extraction. It must not survive into the returned nodes
    (and thus graph.json), where it would ship as an absolute, machine-specific path —
    the "no absolute paths in output" contract (#555, #932). Disambiguation still keys
    on it first, so the two same-label cross-file stubs stay distinct."""
    first = tmp_path / "pkg/a.py"
    second = tmp_path / "pkg/b.py"
    first.parent.mkdir(parents=True)
    first.write_text("from pathlib import Path\ndef use_a(p: Path):\n    return p\n", encoding="utf-8")
    second.write_text("from pathlib import Path\ndef use_b(p: Path):\n    return p\n", encoding="utf-8")

    result = extract([first, second], cache_root=tmp_path)

    # The internal field is gone from every node...
    assert all("origin_file" not in node for node in result["nodes"])
    # ...so no node leaks the absolute sandbox path that origin_file used to carry.
    leaked = [
        (node.get("id"), key, value)
        for node in result["nodes"]
        for key, value in node.items()
        if isinstance(value, str) and str(tmp_path) in value
    ]
    assert not leaked, f"absolute paths leaked into nodes: {leaked}"
    # ...yet the colliding-id pass still kept the two cross-file stubs distinct.
    path_nodes = [node for node in result["nodes"] if node["label"] == "Path"]
    assert len(path_nodes) == 2
    assert len({node["id"] for node in path_nodes}) == 2


def test_go_imported_type_stubs_do_not_collide_across_source_files(tmp_path):
    """Go external types use their import path as canonical identity.

    #1462 kept unresolved bare stubs distinct per source file because Graphify
    could not tell whether they named the same external package. The Go
    import-aware resolver now has that evidence: two ``ext.Widget`` references
    intentionally share one sourceless node without colliding with a local
    ``Widget`` definition.
    """
    first = tmp_path / "a/use_a.go"
    second = tmp_path / "b/use_b.go"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    first.write_text('package a\n\nimport "ext"\n\nfunc UseA(w ext.Widget) {}\n', encoding="utf-8")
    second.write_text('package b\n\nimport "ext"\n\nfunc UseB(w ext.Widget) {}\n', encoding="utf-8")

    result = extract([first, second], cache_root=tmp_path)
    widget_nodes = [node for node in result["nodes"] if node["label"] == "ext.Widget"]

    assert len(widget_nodes) == 1
    assert all(not node.get("source_file") for node in widget_nodes)
    target = widget_nodes[0]["id"]
    refs = [edge for edge in result["edges"] if edge.get("relation") == "references"]
    assert len(refs) == 2
    assert all(edge["target"] == target for edge in refs)


def test_extract_updates_raw_call_callers_after_duplicate_id_disambiguation(tmp_path):
    first = tmp_path / "apps/api/Program.cs"
    second = tmp_path / "tools/api/Program.cs"
    target = tmp_path / "shared/Helper.cs"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    target.parent.mkdir(parents=True)
    first.write_text("class Program { void Run() { SharedHelper(); } }\n", encoding="utf-8")
    second.write_text("class Program { void Run() {} }\n", encoding="utf-8")
    target.write_text("class Helper { void SharedHelper() {} }\n", encoding="utf-8")

    result = extract([first, second, target], cache_root=tmp_path)
    node_ids = {node["id"] for node in result["nodes"]}

    for edge in result["edges"]:
        if edge["relation"] == "calls":
            assert edge["source"] in node_ids
            assert edge["target"] in node_ids


def test_extract_rewires_unique_inheritance_stub_to_real_definition(tmp_path):
    definition = tmp_path / "interfaces.py"
    implementation = tmp_path / "services/BookStore.cs"
    definition.write_text("class BookStore:\n    pass\n", encoding="utf-8")
    implementation.parent.mkdir(parents=True)
    implementation.write_text("class SqliteBookStore : BookStore { }\n", encoding="utf-8")

    result = extract([definition, implementation], cache_root=tmp_path)
    node_by_id = {node["id"]: node for node in result["nodes"]}
    inherits_edges = [edge for edge in result["edges"] if edge["relation"] == "inherits"]

    matching = [
        edge for edge in inherits_edges
        if node_by_id[edge["source"]]["label"] == "SqliteBookStore"
        and node_by_id[edge["target"]]["label"] == "BookStore"
    ]

    assert matching
    assert matching[0]["target"] == next(
        node["id"] for node in result["nodes"]
        if node["label"] == "BookStore" and node.get("source_file") == "interfaces.py"
    )
    assert all(
        not (node["label"] == "BookStore" and not node.get("source_file"))
        for node in result["nodes"]
    )


def test_extract_keeps_stub_when_multiple_real_definitions_match(tmp_path):
    first = tmp_path / "a/interfaces.py"
    second = tmp_path / "b/interfaces.py"
    implementation = tmp_path / "services/BookStore.cs"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    implementation.parent.mkdir(parents=True)
    first.write_text("class BookStore:\n    pass\n", encoding="utf-8")
    second.write_text("class BookStore:\n    pass\n", encoding="utf-8")
    implementation.write_text("class SqliteBookStore : BookStore { }\n", encoding="utf-8")

    result = extract([first, second, implementation], cache_root=tmp_path)
    stubs = [
        node for node in result["nodes"]
        if node["label"] == "BookStore" and not node.get("source_file")
    ]

    assert stubs


def test_extract_does_not_rewire_inheritance_stub_to_same_named_function(tmp_path):
    definition = tmp_path / "factory.py"
    implementation = tmp_path / "services/BookStore.cs"
    definition.write_text("def BookStore():\n    return object()\n", encoding="utf-8")
    implementation.parent.mkdir(parents=True)
    implementation.write_text("class SqliteBookStore : BookStore { }\n", encoding="utf-8")

    result = extract([definition, implementation], cache_root=tmp_path)
    node_by_id = {node["id"]: node for node in result["nodes"]}
    inherits_edges = [edge for edge in result["edges"] if edge["relation"] == "inherits"]

    assert any(
        node["label"] == "BookStore" and not node.get("source_file")
        for node in result["nodes"]
    )
    assert not any(
        node_by_id[edge["source"]]["label"] == "SqliteBookStore"
        and node_by_id[edge["target"]]["label"] == "BookStore()"
        for edge in inherits_edges
    )


def test_extract_does_not_rewire_constructor_method_to_same_named_class(tmp_path):
    source = tmp_path / "Sample.java"
    source.write_text(
        "class DataProcessor {\n"
        "    public DataProcessor() {}\n"
        "}\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    constructor_nodes = [
        node for node in result["nodes"]
        if node["label"] == ".DataProcessor()"
    ]
    assert constructor_nodes
    assert not any(
        edge["source"] == edge["target"]
        for edge in result["edges"]
    )


def test_collect_files_from_dir():
    from graphify.extract import _DISPATCH
    files = collect_files(FIXTURES)
    supported = set(_DISPATCH.keys())
    assert all(f.suffix in supported for f in files)
    assert len(files) > 0


def test_collect_files_skips_hidden():
    files = collect_files(FIXTURES)
    for f in files:
        assert not any(part.startswith(".") for part in f.parts)


def test_collect_files_follows_symlinked_directory(requires_symlinks, tmp_path):
    real_dir = tmp_path / "real_src"
    real_dir.mkdir()
    (real_dir / "lib.py").write_text("x = 1")
    (tmp_path / "linked_src").symlink_to(real_dir)

    files_no = collect_files(tmp_path, follow_symlinks=False)
    files_yes = collect_files(tmp_path, follow_symlinks=True)

    assert [f.name for f in files_no].count("lib.py") == 1
    assert [f.name for f in files_yes].count("lib.py") == 2


def test_collect_files_skips_out_of_root_symlinked_directory(requires_symlinks, tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.py").write_text("token = 'outside'")
    (root / "linked_secret").symlink_to(outside)

    files = collect_files(root, follow_symlinks=True)

    assert not any("linked_secret" in str(f) for f in files)


def test_collect_files_skips_out_of_root_symlinked_file_by_default(requires_symlinks, tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.py").write_text("token = 'outside'")
    (root / "secret_link.py").symlink_to(outside / "secret.py")

    files = collect_files(root)

    assert not any(f.name == "secret_link.py" for f in files)


def test_collect_files_handles_circular_symlinks(requires_symlinks, tmp_path):
    sub = tmp_path / "pkg"
    sub.mkdir()
    (sub / "mod.py").write_text("x = 1")
    (sub / "cycle").symlink_to(tmp_path)

    files = collect_files(tmp_path, follow_symlinks=True)
    assert any(f.name == "mod.py" for f in files)


def _legacy_collect_files(target, *, root=None):
    """The pre-#1261 rglob-per-extension implementation, kept as a parity oracle."""
    from graphify.detect import _is_ignored, _is_noise_dir, _load_graphifyignore
    extensions = set(_DISPATCH.keys())
    ignore_root = root if root is not None else target
    patterns = _load_graphifyignore(ignore_root)
    results = []
    for ext in sorted(extensions):
        results.extend(
            p for p in target.rglob(f"*{ext}")
            if p.suffix == ext
            and not any(_is_noise_dir(part) for part in p.parts)
            and not (patterns and _is_ignored(p, ignore_root, patterns))
        )
    return sorted(results)


def test_collect_files_parity_with_legacy_on_fixtures():
    assert collect_files(FIXTURES) == _legacy_collect_files(FIXTURES)


def test_collect_files_parity_with_legacy_synthetic(tmp_path):
    (tmp_path / "src" / "deep").mkdir(parents=True)
    (tmp_path / "src" / "app.py").write_text("x = 1")
    (tmp_path / "src" / "deep" / "lib.ts").write_text("export const x = 1")
    (tmp_path / "src" / "deep" / "notes.txt").write_text("not code")
    # Fortran case distinction: .f and .F are distinct dispatch entries
    (tmp_path / "src" / "legacy.f").write_text("      END")
    (tmp_path / "src" / "modern.F").write_text("      END")
    # Hidden dirs are traversed (only noise dirs are skipped)
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "ci.sh").write_text("echo hi")
    # Noise dirs must be excluded entirely
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
    (tmp_path / "node_modules" / "pkg" / "index.js").write_text("x")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "app.py").write_text("x")
    # Ignore rules incl. a negation, so directory-level pruning must not
    # swallow re-included files
    (tmp_path / "gen").mkdir()
    (tmp_path / "gen" / "skip.py").write_text("x")
    (tmp_path / "vendored").mkdir()
    (tmp_path / "vendored" / "drop.py").write_text("x")
    (tmp_path / "vendored" / "keep.py").write_text("x")
    (tmp_path / ".gitignore").write_text("gen/\nvendored/*.py\n!vendored/keep.py\n")

    result = collect_files(tmp_path)
    assert result == _legacy_collect_files(tmp_path)
    names = {f.name for f in result}
    assert names == {"app.py", "lib.ts", "legacy.f", "modern.F", "ci.sh", "keep.py"}


def test_collect_files_walks_each_directory_once(tmp_path, monkeypatch):
    """collect_files must scan every directory at most once and never descend
    into noise dirs (#1261). The old implementation ran one rglob pass per
    supported extension (~85 walks) and filtered node_modules/.git paths only
    after descending into them.
    """
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1")
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
    (tmp_path / "node_modules" / "pkg" / "index.js").write_text("x")

    scanned: list[str] = []
    real_scandir = os.scandir

    def counting_scandir(path=".", *args, **kwargs):
        scanned.append(os.fspath(path))
        return real_scandir(path, *args, **kwargs)

    monkeypatch.setattr(os, "scandir", counting_scandir)
    files = collect_files(tmp_path)
    monkeypatch.undo()

    assert files == [tmp_path / "src" / "a.py"]
    # The traversal must be visible as plain os.scandir calls (single os.walk)
    assert any(s.endswith("src") for s in scanned)
    # Noise dirs are pruned before descending, not filtered afterwards
    assert not any("node_modules" in s for s in scanned)
    # No directory is read more than once
    counts = Counter(scanned)
    assert max(counts.values()) == 1


def test_no_dangling_edges_on_extract():
    """After merging multiple files, no internal edges should be dangling."""
    files = list(FIXTURES.glob("*.py"))
    result = extract(files)
    node_ids = {n["id"] for n in result["nodes"]}
    internal_relations = {"contains", "method", "inherits", "calls"}
    for edge in result["edges"]:
        if edge["relation"] in internal_relations:
            assert edge["source"] in node_ids, f"Dangling source: {edge}"
            assert edge["target"] in node_ids, f"Dangling target: {edge}"


def test_calls_edges_emitted():
    """Call-graph pass must produce INFERRED calls edges."""
    result = extract_python(FIXTURES / "sample_calls.py")
    calls = [e for e in result["edges"] if e["relation"] == "calls"]
    assert len(calls) > 0, "Expected at least one calls edge"


def test_calls_edges_are_extracted():
    """AST-resolved call edges are deterministic and should be EXTRACTED/1.0."""
    result = extract_python(FIXTURES / "sample_calls.py")
    for edge in result["edges"]:
        if edge["relation"] == "calls":
            assert edge["confidence"] == "EXTRACTED"
            assert edge["weight"] == 1.0


def test_python_call_edges_have_call_context():
    result = extract_python(FIXTURES / "sample_calls.py")
    call_edges = [e for e in result["edges"] if e["relation"] == "calls"]
    assert call_edges
    assert all(e.get("context") == "call" for e in call_edges)


def test_calls_no_self_loops():
    result = extract_python(FIXTURES / "sample_calls.py")
    for edge in result["edges"]:
        if edge["relation"] == "calls":
            assert edge["source"] != edge["target"], f"Self-loop: {edge}"


def test_run_analysis_calls_compute_score():
    """run_analysis() calls compute_score() - must appear as a calls edge."""
    result = extract_python(FIXTURES / "sample_calls.py")
    calls = {(e["source"], e["target"]) for e in result["edges"] if e["relation"] == "calls"}
    node_by_label = {n["label"]: n["id"] for n in result["nodes"]}
    src = node_by_label.get("run_analysis()")
    tgt = node_by_label.get("compute_score()")
    assert src and tgt, "run_analysis or compute_score node not found"
    assert (src, tgt) in calls, f"run_analysis -> compute_score not found in {calls}"


def test_run_analysis_calls_normalize():
    result = extract_python(FIXTURES / "sample_calls.py")
    calls = {(e["source"], e["target"]) for e in result["edges"] if e["relation"] == "calls"}
    node_by_label = {n["label"]: n["id"] for n in result["nodes"]}
    src = node_by_label.get("run_analysis()")
    tgt = node_by_label.get("normalize()")
    assert src and tgt
    assert (src, tgt) in calls


def test_method_calls_module_function():
    """Analyzer.process() calls run_analysis() - cross class→function calls edge."""
    result = extract_python(FIXTURES / "sample_calls.py")
    calls = {(e["source"], e["target"]) for e in result["edges"] if e["relation"] == "calls"}
    node_by_label = {n["label"]: n["id"] for n in result["nodes"]}
    src = node_by_label.get(".process()")
    tgt = node_by_label.get("run_analysis()")
    assert src and tgt
    assert (src, tgt) in calls


def test_calls_deduplication():
    """Same caller→callee pair must appear only once even if called multiple times."""
    result = extract_python(FIXTURES / "sample_calls.py")
    call_pairs = [(e["source"], e["target"]) for e in result["edges"] if e["relation"] == "calls"]
    assert len(call_pairs) == len(set(call_pairs)), "Duplicate calls edges found"


def test_cross_file_calls_skip_ambiguous_duplicate_labels(tmp_path):
    """Unqualified cross-file calls must not guess between duplicate helper names."""
    caller = tmp_path / "caller.py"
    helper_a = tmp_path / "a.py"
    helper_b = tmp_path / "b.py"
    caller.write_text("def run():\n    log()\n")
    helper_a.write_text("def log():\n    return 'a'\n")
    helper_b.write_text("def log():\n    return 'b'\n")

    result = extract([caller, helper_a, helper_b], cache_root=tmp_path)
    nodes = {n["id"]: n for n in result["nodes"]}
    calls = [
        e for e in result["edges"]
        if e["relation"] == "calls" and e["confidence"] == "INFERRED"
    ]

    assert not any(
        nodes[e["source"]]["label"] == "run()" and nodes[e["target"]]["label"] == "log()"
        for e in calls
    )


def test_cross_file_call_survives_same_named_test_mock(tmp_path):
    """A real cross-file call must NOT be erased by a same-named test mock.

    src/caller.py calls save(); src/service.py defines the real save(); a test
    mock save() lives in tests/test_service.py. Before #1553 the ambiguous-name
    god-node guard dropped the edge entirely. Now the non-test tie-breaker keeps
    exactly one caller->save edge pointing at the SRC definition.
    """
    src = tmp_path / "src"
    tests = tmp_path / "tests"
    src.mkdir()
    tests.mkdir()
    (src / "service.py").write_text("def save():\n    return 'real'\n")
    (src / "caller.py").write_text("def run():\n    save()\n")
    (tests / "test_service.py").write_text("def save():\n    return 'mock'\n")

    result = extract(
        [src / "caller.py", src / "service.py", tests / "test_service.py"],
        cache_root=tmp_path,
    )
    nodes = {n["id"]: n for n in result["nodes"]}
    save_calls = [
        e for e in result["edges"]
        if e["relation"] == "calls"
        and nodes[e["source"]]["label"] == "run()"
        and nodes[e["target"]]["label"] == "save()"
    ]
    assert len(save_calls) == 1, f"expected exactly one run->save edge, got {save_calls}"
    target_sf = (nodes[save_calls[0]["target"]].get("source_file") or "")
    assert "service.py" in target_sf and "test_service.py" not in target_sf, target_sf


def test_cross_file_call_god_node_guard_two_real_defs(tmp_path):
    """Two genuine NON-test defs of the same name + one caller => ZERO edges.

    Proves #543/#1219 is not reopened by the #1553 tie-breakers: with no test
    candidate to drop and no proximity winner, the guard still bails.
    """
    pkg_a = tmp_path / "a"
    pkg_b = tmp_path / "b"
    pkg_c = tmp_path / "c"
    for d in (pkg_a, pkg_b, pkg_c):
        d.mkdir()
    (pkg_a / "svc.py").write_text("def save():\n    return 'a'\n")
    (pkg_b / "svc.py").write_text("def save():\n    return 'b'\n")
    (pkg_c / "caller.py").write_text("def run():\n    save()\n")

    result = extract(
        [pkg_c / "caller.py", pkg_a / "svc.py", pkg_b / "svc.py"],
        cache_root=tmp_path,
    )
    nodes = {n["id"]: n for n in result["nodes"]}
    save_calls = [
        e for e in result["edges"]
        if e["relation"] == "calls"
        and nodes[e["source"]]["label"] == "run()"
        and nodes[e["target"]]["label"] == "save()"
    ]
    assert save_calls == [], f"god-node guard must bail, got {save_calls}"


def test_cross_file_call_survives_many_test_mocks(tmp_path):
    """One src def + many same-named test stubs + caller => exactly one src edge."""
    src = tmp_path / "src"
    tests = tmp_path / "tests"
    src.mkdir()
    tests.mkdir()
    (src / "service.py").write_text("def save():\n    return 'real'\n")
    (src / "caller.py").write_text("def run():\n    save()\n")
    for i in range(5):
        (tests / f"thing{i}_test.py").write_text("def save():\n    return 'mock'\n")

    paths = [src / "caller.py", src / "service.py"] + sorted(tests.glob("*_test.py"))
    result = extract(paths, cache_root=tmp_path)
    nodes = {n["id"]: n for n in result["nodes"]}
    save_calls = [
        e for e in result["edges"]
        if e["relation"] == "calls"
        and nodes[e["source"]]["label"] == "run()"
        and nodes[e["target"]]["label"] == "save()"
    ]
    assert len(save_calls) == 1, f"expected one run->save edge, got {save_calls}"
    assert "service.py" in (nodes[save_calls[0]["target"]].get("source_file") or "")


def test_extract_generic_surfaces_tree_sitter_version_mismatch_hint(monkeypatch):
    """When Language() raises TypeError (e.g. old tree-sitter binding meets a
    new tree-sitter API), the error message should point users at the upgrade
    path instead of leaving a bare 'missing 1 required positional argument'.
    """
    import sys
    import types
    from graphify.extract import _extract_generic, LanguageConfig

    # Build a fake tree_sitter module whose Language() raises TypeError -
    # this is exactly what users see when an older tree-sitter is paired
    # with a newer language binding.
    fake_ts = types.ModuleType("tree_sitter")
    def _raise(*args, **kwargs):
        raise TypeError("missing 1 required positional argument: 'name'")
    fake_ts.Language = _raise
    fake_ts.Parser = None
    monkeypatch.setitem(sys.modules, "tree_sitter", fake_ts)

    # Stub the language module so import_module returns something with .language
    fake_lang_mod = types.ModuleType("fake_ts_lang")
    fake_lang_mod.language = lambda: object()
    monkeypatch.setitem(sys.modules, "fake_ts_lang", fake_lang_mod)

    config = LanguageConfig(ts_module="fake_ts_lang", ts_language_fn="language")
    result = _extract_generic(Path("dummy.txt"), config)

    assert "error" in result
    assert "tree-sitter version mismatch" in result["error"]
    assert "pip install --upgrade" in result["error"]


def test_extract_js_destructured_require_imports_from():
    """`const { foo } = require('./mod')` must emit imports_from to the resolved module path."""
    from graphify.extract import extract_js
    result = extract_js(FIXTURES / "cjs_require.js")
    imports_from = [e for e in result["edges"] if e["relation"] == "imports_from"]
    targets = [e["target"] for e in imports_from]
    # Must resolve relative require() targets to file ids so they connect across the corpus
    assert any("foundation" in t for t in targets), f"No foundation import_from: {targets}"
    assert any("utils" in t for t in targets), f"No utils import_from: {targets}"
    assert any("helpers" in t for t in targets), f"No helpers import_from: {targets}"
    for e in imports_from:
        assert e["confidence"] == "EXTRACTED"


def test_extract_js_destructured_require_named_symbols():
    """Destructured CJS requires must emit symbol-level `imports` edges per binder."""
    from graphify.extract import extract_js, _make_id, _file_stem
    result = extract_js(FIXTURES / "cjs_require.js")
    sym_targets = [e["target"] for e in result["edges"] if e["relation"] == "imports"]
    foundation_stem = _file_stem(FIXTURES / "foundation.js")
    assert _make_id(foundation_stem, "loadFoundation") in sym_targets
    assert _make_id(foundation_stem, "validateConfig") in sym_targets


def test_extract_js_member_require_emits_property_symbol():
    """`const x = require('./m').y` must emit symbol edge for `y`."""
    from graphify.extract import extract_js, _make_id, _file_stem
    result = extract_js(FIXTURES / "cjs_require.js")
    sym_targets = [e["target"] for e in result["edges"] if e["relation"] == "imports"]
    helpers_stem = _file_stem(FIXTURES / "helpers.js")
    assert _make_id(helpers_stem, "helperFn") in sym_targets


def test_extract_js_function_scoped_require_emits_import_edge(tmp_path):
    """Lazy CommonJS requires belong to their enclosing function, not nowhere."""
    target = tmp_path / "target.js"
    target.write_text("exports.helper = () => 42;\n", encoding="utf-8")
    caller = tmp_path / "lazy.js"
    caller.write_text(
        "function useItLazily() {\n"
        "  const { helper } = require('./target');\n"
        "  return helper();\n"
        "}\n",
        encoding="utf-8",
    )

    result = extract([caller, target], cache_root=tmp_path, root=tmp_path, parallel=False)
    labels = {node["id"]: node["label"] for node in result["nodes"]}
    lazy_edges = [
        edge for edge in result["edges"]
        if edge["relation"] == "imports_from" and "target" in edge["target"]
    ]

    assert len(lazy_edges) == 1
    assert labels[lazy_edges[0]["source"]] == "useItLazily()"
    assert lazy_edges[0]["confidence"] == "EXTRACTED"


def test_extract_js_dynamic_require_variable_is_not_fabricated(tmp_path):
    """A lazy `require(someVar)` has no static string target, so the body pass
    must skip it rather than fabricate an edge to a guessed path (#2700)."""
    caller = tmp_path / "dyn.js"
    caller.write_text(
        "function load(name) {\n"
        "  const mod = require(name);\n"
        "  return mod;\n"
        "}\n",
        encoding="utf-8",
    )
    result = extract([caller], cache_root=tmp_path, root=tmp_path, parallel=False)
    assert not [e for e in result["edges"] if e["relation"] in ("imports_from", "imports")]


def test_extract_js_module_scope_require_still_single_edge(tmp_path):
    """No-double-count regression: the module-level and body require passes must
    never both emit for the same require — a top-level require stays exactly one
    imports_from edge (#2700)."""
    target = tmp_path / "target.js"
    target.write_text("exports.helper = () => 42;\n", encoding="utf-8")
    caller = tmp_path / "top.js"
    caller.write_text("const { helper } = require('./target');\n", encoding="utf-8")

    result = extract([caller, target], cache_root=tmp_path, root=tmp_path, parallel=False)
    lazy_edges = [
        e for e in result["edges"]
        if e["relation"] == "imports_from" and "target" in e["target"]
    ]
    assert len(lazy_edges) == 1


def test_extract_js_arrow_function_still_extracted():
    """Regression: arrow functions in lexical_declaration must still produce nodes."""
    from graphify.extract import extract_js
    arrow_fixture = FIXTURES / "_arrow_only.js"
    arrow_fixture.write_text("const greet = () => console.log('hi');\n")
    try:
        result = extract_js(arrow_fixture)
        labels = [n["label"] for n in result["nodes"]]
        assert "greet()" in labels
    finally:
        arrow_fixture.unlink()


def test_extract_js_this_assigned_methods(tmp_path):
    """`this.X = () => {}` / `this.X = function(){}` in a constructor-style
    function body must be captured as methods owned by that function.

    This is the dominant pattern in pre-class JS (DAOs, route handlers): the
    methods live in the function body, which is otherwise only walked for
    calls, so before this they were entirely invisible as symbols.
    """
    from graphify.extract import extract_js
    f = tmp_path / "dao.js"
    f.write_text(
        "function UserDAO(db) {\n"
        "  this.addUser = (name) => { return name; };\n"
        "  this.getUser = function(id) { return id; };\n"
        "}\n"
    )
    result = extract_js(f)
    by_label = {n["label"]: n for n in result["nodes"]}
    assert "UserDAO()" in by_label
    assert ".addUser()" in by_label
    assert ".getUser()" in by_label
    # The methods are owned by UserDAO via a `method` edge.
    owner = by_label["UserDAO()"]["id"]
    method_edges = {
        (e["source"], by_label_by_id(result, e["target"]))
        for e in result["edges"]
        if e["relation"] == "method"
    }
    assert (owner, ".addUser()") in method_edges
    assert (owner, ".getUser()") in method_edges


def test_extract_js_factory_object_assigned_methods(tmp_path):
    """Methods assigned to a local object-literal factory API remain visible."""
    from graphify.extract import extract_js
    f = tmp_path / "factory.js"
    f.write_text(
        "function createApi(deps) {\n"
        "  const api = {};\n"
        "  api.sourceClips = async function sourceClips(topic) { return deps.fetch(topic); };\n"
        "  api.renderVideo = function renderVideo(clips) { return api.sourceClips(clips); };\n"
        "  return api;\n"
        "}\n"
    )

    result = extract_js(f)
    by_label = {n["label"]: n for n in result["nodes"]}
    assert {"createApi()", "api", ".sourceClips()", ".renderVideo()"} <= set(by_label)

    factory_nid = by_label["createApi()"]["id"]
    api_nid = by_label["api"]["id"]
    source_clips_nid = by_label[".sourceClips()"]["id"]
    render_video_nid = by_label[".renderVideo()"]["id"]
    edges = {(e["source"], e["relation"], e["target"]) for e in result["edges"]}
    assert (factory_nid, "contains", api_nid) in edges
    assert (api_nid, "method", source_clips_nid) in edges
    assert (api_nid, "method", render_video_nid) in edges
    assert (render_video_nid, "calls", source_clips_nid) in edges


def test_extract_js_factory_object_contains_edge_not_duplicated(tmp_path):
    """The factory-to-object `contains` edge is emitted once regardless of how
    many methods hang off the object. add_edge does not dedup, so a per-method
    emission would flood the graph with N identical `contains` edges."""
    from graphify.extract import extract_js
    f = tmp_path / "many.js"
    f.write_text(
        "function build() {\n"
        "  const api = {};\n"
        "  api.a = () => 1;\n"
        "  api.b = () => 2;\n"
        "  api.c = () => 3;\n"
        "  api.d = () => 4;\n"
        "  return api;\n"
        "}\n"
    )
    result = extract_js(f)
    api_nid = next(n["id"] for n in result["nodes"] if n["label"] == "api")
    contains = [
        e for e in result["edges"]
        if e["relation"] == "contains" and e["target"] == api_nid
    ]
    assert len(contains) == 1, f"expected one contains edge, got {len(contains)}"
    methods = [e for e in result["edges"]
               if e["relation"] == "method" and e["source"] == api_nid]
    assert len(methods) == 4


def test_extract_js_factory_object_arrow_assigned_methods(tmp_path):
    """Arrow functions assigned to a factory object are captured just like
    function expressions (the dominant modern factory shape)."""
    from graphify.extract import extract_js
    f = tmp_path / "arrow_factory.js"
    f.write_text(
        "function makeStore() {\n"
        "  const store = {};\n"
        "  store.get = (k) => k;\n"
        "  store.set = (k, v) => store.get(k);\n"
        "  return store;\n"
        "}\n"
    )
    result = extract_js(f)
    by_label = {n["label"]: n for n in result["nodes"]}
    assert {"makeStore()", "store", ".get()", ".set()"} <= set(by_label)
    store_nid = by_label["store"]["id"]
    edges = {(e["source"], e["relation"], e["target"]) for e in result["edges"]}
    assert (store_nid, "method", by_label[".get()"]["id"]) in edges
    assert (store_nid, "method", by_label[".set()"]["id"]) in edges
    assert (by_label[".set()"]["id"], "calls", by_label[".get()"]["id"]) in edges


def test_extract_js_bare_object_member_assignment_not_captured(tmp_path):
    """An `obj.x = fn` where `obj` is NOT a local object-literal binding must be
    skipped — capturing arbitrary receivers reintroduces the #1077 phantom-owner
    flood the scope check exists to prevent."""
    from graphify.extract import extract_js
    f = tmp_path / "bare.js"
    f.write_text(
        "function wire(external) {\n"
        "  external.handler = () => 1;\n"
        "  return external;\n"
        "}\n"
    )
    result = extract_js(f)
    labels = {n["label"] for n in result["nodes"]}
    assert "external" not in labels
    assert ".handler()" not in labels


def test_extract_js_commonjs_exports_assignment(tmp_path):
    """`exports.X = fn` and `module.exports.X = fn` must produce function nodes."""
    from graphify.extract import extract_js
    f = tmp_path / "mod.js"
    f.write_text(
        "exports.alpha = (x) => x;\n"
        "module.exports.beta = function(y) { return y; };\n"
    )
    labels = [n["label"] for n in extract_js(f)["nodes"]]
    assert "alpha()" in labels
    assert "beta()" in labels


def test_extract_js_commonjs_exports_hof_assignment(tmp_path):
    """#3035: `exports.X = wrap(...)` and `module.exports.X = wrap(...)` must produce function nodes."""
    from graphify.extract import extract_js
    f = tmp_path / "mod.js"
    f.write_text(
        "function wrap(fn) { return fn; }\n"
        "exports.assignedCall = wrap(async (x) => x);\n"
        "module.exports.moduleAssignedCall = wrap(function(y) { return y; });\n"
    )
    res = extract_js(f)
    by_label = {n["label"]: n for n in res["nodes"]}
    assert "assignedCall()" in by_label
    assert "moduleAssignedCall()" in by_label
    assert by_label["assignedCall()"].get("_callable") is True
    assert by_label["moduleAssignedCall()"].get("_callable") is True
    file_nid = next(n["id"] for n in res["nodes"] if n["label"] == "mod.js")
    edges = {(e["source"], e["relation"], e["target"]) for e in res["edges"]}
    assert (file_nid, "contains", by_label["assignedCall()"]["id"]) in edges
    assert (file_nid, "contains", by_label["moduleAssignedCall()"]["id"]) in edges


def test_extract_js_commonjs_exports_hof_options_and_calls(tmp_path):
    """#3035: Calls inside HOF-wrapped export callbacks (with options) are attributed to the exported node."""
    from graphify.extract import extract_js
    f = tmp_path / "handler.js"
    f.write_text(
        "function onCall(opts, fn) { return fn; }\n"
        "function helperA() {}\n"
        "function helperB() {}\n"
        "exports.apiHandler = onCall({ cors: true }, async (req) => {\n"
        "    helperA();\n"
        "});\n"
        "module.exports.otherHandler = onCall({ timeout: 5000 }, (req) => helperB());\n"
    )
    res = extract_js(f)
    by_label = {n["label"]: n for n in res["nodes"]}
    assert {"apiHandler()", "otherHandler()", "helperA()", "helperB()"} <= set(by_label)
    edges = {(e["source"], e["relation"], e["target"]) for e in res["edges"]}
    assert (by_label["apiHandler()"]["id"], "calls", by_label["helperA()"]["id"]) in edges
    assert (by_label["otherHandler()"]["id"], "calls", by_label["helperB()"]["id"]) in edges


def test_extract_js_arbitrary_member_hof_assignment_not_captured(tmp_path):
    """#3035 / #1077: Arbitrary `obj.x = wrap(...)` must NOT produce a node."""
    from graphify.extract import extract_js
    f = tmp_path / "noise.js"
    f.write_text(
        "function wrap(fn) { return fn; }\n"
        "const obj = {};\n"
        "obj.assignedCall = wrap(async () => {});\n"
    )
    labels = [n["label"] for n in extract_js(f)["nodes"]]
    assert "assignedCall()" not in labels
    assert ".assignedCall()" not in labels
    assert "assignedCall" not in labels


def test_extract_js_prototype_method_assignment(tmp_path):
    """`Foo.prototype.bar = fn` must be captured as a method owned by Foo."""
    from graphify.extract import extract_js
    f = tmp_path / "proto.js"
    f.write_text(
        "function Foo() {}\n"
        "Foo.prototype.bar = function() { return 1; };\n"
    )
    by_label = {n["label"]: n for n in extract_js(f)["nodes"]}
    assert "Foo()" in by_label
    assert ".bar()" in by_label


def test_extract_js_const_function_expression(tmp_path):
    """`const f = function(){}` (function expression, not arrow) must be captured."""
    from graphify.extract import extract_js
    f = tmp_path / "fnexpr.js"
    f.write_text("const handler = function(req, res) { return res; };\n")
    labels = [n["label"] for n in extract_js(f)["nodes"]]
    assert "handler()" in labels


def test_extract_ts_class_arrow_field(tmp_path):
    """A class field initialised with an arrow function (`x = () => {}`) must be
    captured as a method of the class — common in React/TS component classes."""
    from graphify.extract import extract_js
    f = tmp_path / "comp.ts"
    f.write_text(
        "class Widget {\n"
        "  onClick = (e) => { return e; };\n"
        "  render() { return null; }\n"
        "}\n"
    )
    by_label = {n["label"]: n for n in extract_js(f)["nodes"]}
    assert "Widget" in by_label
    assert ".onClick()" in by_label   # arrow field
    assert ".render()" in by_label    # plain method (regression guard)


def test_extract_js_arbitrary_member_assignment_not_captured(tmp_path):
    """Guard against the phantom-god-node class (#1077): an arbitrary
    `obj.x = fn` (obj is neither this/exports/module.exports/<X>.prototype)
    must NOT produce a node."""
    from graphify.extract import extract_js
    f = tmp_path / "noise.js"
    f.write_text(
        "const obj = {};\n"
        "obj.whatever = () => 1;\n"
    )
    labels = [n["label"] for n in extract_js(f)["nodes"]]
    assert "whatever()" not in labels
    assert ".whatever()" not in labels


def test_extract_js_nested_function_declarations(tmp_path):
    """#2653: function declarations nested inside another function emit nodes,
    source contains edges from the enclosing function, and attribute call edges correctly."""
    from graphify.extract import extract
    f = tmp_path / "Panel.tsx"
    f.write_text(
        "function doThing() {}\n"
        "export function Panel() {\n"
        "  function handleClick() {\n"
        "    doThing()\n"
        "  }\n"
        "  return <button onClick={handleClick} />\n"
        "}\n"
    )
    result = extract([f], root=tmp_path)
    by_label = {n["label"]: n for n in result["nodes"]}

    assert "handleClick()" in by_label
    assert by_label["handleClick()"]["id"] == "panel_panel_handleclick"

    edges = [(e["source"], e["target"], e["relation"]) for e in result["edges"]]

    panel_id = by_label["Panel()"]["id"]
    handle_id = by_label["handleClick()"]["id"]
    dothing_id = by_label["doThing()"]["id"]

    assert (panel_id, handle_id, "contains") in edges
    assert (handle_id, dothing_id, "calls") in edges
    assert (panel_id, dothing_id, "calls") not in edges


def test_extract_js_deeply_nested_function_declarations(tmp_path):
    """#2653: arbitrary depth nested named function declarations establish hierarchical containment and correct call attribution."""
    from graphify.extract import extract
    f = tmp_path / "Deep.ts"
    f.write_text(
        "function doThing() {}\n"
        "function Panel() {\n"
        "  function outer() {\n"
        "    function inner() {\n"
        "      doThing()\n"
        "    }\n"
        "  }\n"
        "}\n"
    )
    result = extract([f], root=tmp_path)
    by_label = {n["label"]: n for n in result["nodes"]}

    panel_id = by_label["Panel()"]["id"]
    outer_id = by_label["outer()"]["id"]
    inner_id = by_label["inner()"]["id"]
    dothing_id = by_label["doThing()"]["id"]

    edges = [(e["source"], e["target"], e["relation"]) for e in result["edges"]]

    assert (panel_id, outer_id, "contains") in edges
    assert (outer_id, inner_id, "contains") in edges
    assert (inner_id, dothing_id, "calls") in edges
    assert (panel_id, dothing_id, "calls") not in edges
    assert (outer_id, dothing_id, "calls") not in edges


def test_extract_js_function_nested_in_arrow_component(tmp_path):
    """#2653 (the motivating React idiom): a named function declared inside an
    ARROW-defined component `const Panel = () => { function handleRegen(){…} }`
    is noded, contained by the component, and its calls resolve — the main walk
    never recurses into arrow bodies, so this must be scanned explicitly."""
    from graphify.extract import extract
    f = tmp_path / "Panel.jsx"
    f.write_text(
        "function doThing() {}\n"
        "const Panel = () => {\n"
        "  function handleRegen() {\n"
        "    doThing()\n"
        "  }\n"
        "  return handleRegen\n"
        "}\n"
    )
    result = extract([f], root=tmp_path)
    by_label = {n["label"]: n for n in result["nodes"]}

    assert "handleRegen()" in by_label
    edges = [(e["source"], e["target"], e["relation"]) for e in result["edges"]]
    panel_id = by_label["Panel()"]["id"]
    handle_id = by_label["handleRegen()"]["id"]
    dothing_id = by_label["doThing()"]["id"]

    assert (panel_id, handle_id, "contains") in edges
    assert (handle_id, dothing_id, "calls") in edges
    assert (panel_id, dothing_id, "calls") not in edges


def test_extract_js_function_nested_in_arrow_callback(tmp_path):
    """#2653: a named function declared inside an arrow CALLBACK nested in a
    function (`function Panel(){ useEffect(() => { function h(){…} }) }`) is
    attributed to the nearest enclosing named scope (the anonymous arrow is not
    a node), and its calls resolve instead of dangling."""
    from graphify.extract import extract
    f = tmp_path / "Effect.jsx"
    f.write_text(
        "function doThing() {}\n"
        "function Panel() {\n"
        "  useEffect(() => {\n"
        "    function h() {\n"
        "      doThing()\n"
        "    }\n"
        "  })\n"
        "}\n"
    )
    result = extract([f], root=tmp_path)
    by_label = {n["label"]: n for n in result["nodes"]}

    assert "h()" in by_label
    edges = [(e["source"], e["target"], e["relation"]) for e in result["edges"]]
    panel_id = by_label["Panel()"]["id"]
    h_id = by_label["h()"]["id"]
    dothing_id = by_label["doThing()"]["id"]

    # the anonymous arrow is not noded, so h is contained directly by Panel
    assert (panel_id, h_id, "contains") in edges
    assert (h_id, dothing_id, "calls") in edges


def test_extract_js_nested_function_local_variable_preservation(tmp_path):
    """#2653 / #1077: extracting nested named functions must preserve local variable suppression."""
    from graphify.extract import extract_js
    f = tmp_path / "LocalVar.ts"
    f.write_text(
        "function doThing() {}\n"
        "function Panel() {\n"
        "  const localValue = 123;\n"
        "  function handleClick() {\n"
        "    doThing();\n"
        "  }\n"
        "}\n"
    )
    res = extract_js(f)
    labels = [n["label"] for n in res["nodes"]]
    assert "handleClick()" in labels
    assert "localValue" not in labels



def by_label_by_id(result, node_id):
    for n in result["nodes"]:
        if n["id"] == node_id:
            return n["label"]
    return None


def test_cross_file_call_promoted_to_extracted_with_import_evidence(tmp_path):
    """A cross-file `calls` edge must be EXTRACTED when the caller's file has
    an `imports` or `imports_from` edge linking it to the callee."""
    caller = tmp_path / "caller.js"
    callee = tmp_path / "lib.js"
    caller.write_text(
        "const { doWork } = require('./lib');\n"
        "function run() { doWork(); }\n"
    )
    callee.write_text(
        "function doWork() { return 1; }\n"
        "module.exports = { doWork };\n"
    )
    result = extract([caller, callee], cache_root=tmp_path)
    nodes = {n["id"]: n for n in result["nodes"]}
    call_edges = [
        e for e in result["edges"]
        if e["relation"] == "calls"
        and nodes[e["source"]]["label"] == "run()"
        and nodes[e["target"]]["label"] == "doWork()"
    ]
    assert len(call_edges) == 1
    assert call_edges[0]["confidence"] == "EXTRACTED"
    assert call_edges[0]["confidence_score"] == 1.0


def test_js_cross_file_call_without_import_emits_no_edge(tmp_path):
    """A JS/TS call with no local definition and no import must NOT bind to a
    same-named export in another file (#1659). JS/TS modules have no implicit
    cross-module scope, so name collision alone is not a real call — it used to
    produce a phantom INFERRED edge that fabricated cross-package dependencies."""
    caller = tmp_path / "caller.js"
    callee = tmp_path / "lib.js"
    # Caller does NOT require lib — same-name function happens to exist elsewhere
    caller.write_text("function run() { doUnique(); }\n")
    callee.write_text(
        "function doUnique() { return 1; }\n"
        "module.exports = { doUnique };\n"
    )
    result = extract([caller, callee], cache_root=tmp_path)
    nodes = {n["id"]: n for n in result["nodes"]}
    call_edges = [
        e for e in result["edges"]
        if e["relation"] == "calls"
        and nodes[e["source"]]["label"] == "run()"
        and nodes[e["target"]]["label"] == "doUnique()"
    ]
    assert call_edges == [], f"unimported cross-file JS call should not resolve: {call_edges}"


def test_python_qualified_class_method_call_resolves_extracted(tmp_path):
    """`ClassName.method()` across files resolves to the class-qualified method
    node with an EXTRACTED `calls` edge (#1446)."""
    actions = tmp_path / "actions.py"
    viewset = tmp_path / "viewset.py"
    actions.write_text(
        "class TaskActions:\n"
        "    @staticmethod\n"
        "    def approve(pk):\n"
        "        return pk\n"
    )
    viewset.write_text(
        "from actions import TaskActions\n\n"
        "class TaskViewSet:\n"
        "    def handle(self, request):\n"
        "        return TaskActions.approve(request)\n"
    )
    result = extract([viewset, actions], cache_root=tmp_path)
    nodes = {n["id"]: n for n in result["nodes"]}
    call_edges = [
        e for e in result["edges"]
        if e["relation"] == "calls"
        and "handle" in nodes[e["source"]]["label"]
        and "approve" in nodes[e["target"]]["label"]
        and "actions.py" in (nodes[e["target"]].get("source_file") or "")
    ]
    assert len(call_edges) == 1, f"expected one handle->approve edge, got {call_edges}"
    assert call_edges[0]["confidence"] == "EXTRACTED"


def test_degenerate_symbol_name_does_not_leak_absolute_id(tmp_path):
    """#1899 variant B: a symbol whose name normalizes to nothing (a minified `$`
    function, a JSONC `"//"` key) must not be minted — `_make_id(stem, "")`
    collapses to the bare, absolute-path-derived file stem, leaking the scan path
    and colliding with the file node. Such nodes carry no graph signal."""
    (tmp_path / "vendor.js").write_text(
        "function $(){return 1}\nfunction real(){return 2}\n", encoding="utf-8"
    )
    result = extract([tmp_path / "vendor.js"], cache_root=tmp_path)
    marker = str(tmp_path)
    for n in result["nodes"]:
        assert marker not in n["id"], f"absolute path leaked into id: {n}"
    labels = {n.get("label") for n in result["nodes"]}
    assert "real()" in labels, "the real function must still be extracted"
    assert "$()" not in labels, "the degenerate `$` symbol must be dropped (#1899)"


def test_out_of_tree_cache_root_keeps_source_file_relative_to_scan_root(tmp_path):
    """#1941: `--out <far-away-dir>` must not basename every in-root node.

    The CLI passes cache_root=<out dir> to relocate the cache, but that value also
    anchored relativization, so every scanned file failed `relative_to(root)`, fell
    into `_portable_out_of_root_sf`, tripped the `updepth > 3` walk-up guard meant
    for stray out-of-root ProjectReferences, and collapsed to a bare basename.
    An explicit `root=` anchors ids/source_file on the SCAN root regardless of
    where the cache lives.
    """
    scan_root = tmp_path / "corpus"
    nested = scan_root / "src" / "Data" / "Database" / "RepositoryTests"
    nested.mkdir(parents=True)
    (nested / "order_repository_tests.py").write_text(
        "class OrderRepositoryTests:\n    def test_get(self):\n        return 1\n",
        encoding="utf-8",
    )
    # >3 levels off the shared ancestor: the exact shape that triggered basenaming.
    out_dir = tmp_path / "a" / "b" / "c" / "d" / "out"
    out_dir.mkdir(parents=True)

    result = extract(
        [nested / "order_repository_tests.py"],
        cache_root=out_dir,
        root=scan_root,
    )
    source_files = {
        n["source_file"] for n in result["nodes"] if n.get("source_file")
    }
    assert source_files, "expected nodes carrying a source_file"
    assert source_files == {
        "src/Data/Database/RepositoryTests/order_repository_tests.py"
    }, f"source_file must stay relative to the scan root, got {source_files}"
    # The point of the field: it resolves back to a real file against the root.
    for sf in source_files:
        assert (scan_root / sf).is_file(), f"{sf} does not resolve under {scan_root}"
    # #1899 must not regress: no absolute path / username leak.
    for n in result["nodes"]:
        assert str(tmp_path) not in (n.get("source_file") or "")
        assert str(tmp_path) not in n["id"]


def test_c_include_out_of_root_target_id_is_portable(tmp_path):
    """#2243 (residual of #1899, in edges not nodes): a `#include "../lib/foo.h"`
    reaching OUTSIDE the scan root must not leak the absolute scan path
    (including the OS username) into the edge's target id. #1899's out-of-root
    fix taught the belt-and-braces pass to catch a NODE whose id was minted from
    the same absolute path it carries as source_file -- but `_import_c` mints no
    node of its own for an include target, only an edge, so that pass had
    nothing to learn from and the raw `_make_id(str(absolute_path))` slug
    survived untouched."""
    app = tmp_path / "app"
    app.mkdir()
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "foo.h").write_text("int foo_compute(int x);\n")
    (app / "main.c").write_text(
        '#include "../lib/foo.h"\nint main(void) { return foo_compute(1); }\n'
    )
    result = extract([app / "main.c"], cache_root=app)
    marker = str(tmp_path)
    for e in result["edges"]:
        for f in ("source", "target", "source_file"):
            assert marker not in str(e.get(f, "")), f"leaked into edge {f}: {e}"
        assert "target_file" not in e, f"transient target_file hint leaked: {e}"
    include_edges = [e for e in result["edges"] if e["relation"] == "imports"]
    assert include_edges, "expected an imports edge for the #include"
    assert include_edges[0]["target"] == "ext_lib_foo_h"


def test_c_include_out_of_root_target_id_is_deterministic_across_checkout_paths(tmp_path):
    """#2243: the SAME corpus, scanned from two differently-named, differently
    nested checkout locations, must produce a byte-identical edge target id for
    an out-of-root `#include`. Before the fix each checkout baked its own
    absolute scan path into the target, so a graph.json committed to git showed
    a spurious `links` diff on every rebuild even though nothing else changed."""

    def _build(root_dir_name):
        base = tmp_path / root_dir_name / "deeper" / "nesting"
        app = base / "app"
        app.mkdir(parents=True)
        lib = base / "lib"
        lib.mkdir()
        (lib / "foo.h").write_text("int foo_compute(int x);\n")
        (app / "main.c").write_text(
            '#include "../lib/foo.h"\nint main(void) { return foo_compute(1); }\n'
        )
        result = extract([app / "main.c"], cache_root=app)
        return [e["target"] for e in result["edges"] if e["relation"] == "imports"][0]

    target_a = _build("checkout_alice")
    target_b = _build("checkout_bob_at_a_totally_different_nesting_depth")
    assert target_a == target_b == "ext_lib_foo_h"


def test_c_include_in_root_same_batch_still_resolves_to_real_node(tmp_path):
    """Negative companion to the two tests above: when the included header IS
    inside the scan root and IS part of the same extraction batch, the edge must
    keep pointing at the real file node's id -- the out-of-root fix must never
    fire, or dangle, for a target the scan already covers."""
    app = tmp_path / "app"
    app.mkdir()
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "foo.h").write_text("int foo_compute(int x);\n")
    (app / "main.c").write_text(
        '#include "../lib/foo.h"\nint main(void) { return foo_compute(1); }\n'
    )
    result = extract([app / "main.c", lib / "foo.h"], cache_root=tmp_path, root=tmp_path)
    header_nodes = [n for n in result["nodes"] if n.get("source_file") == "lib/foo.h"]
    assert header_nodes, "expected a real node for the in-batch header"
    include_edges = [
        e for e in result["edges"]
        if e["relation"] == "imports" and e.get("source_file") == "app/main.c"
    ]
    assert include_edges
    assert include_edges[0]["target"] == header_nodes[0]["id"]
    assert not include_edges[0]["target"].startswith("ext_")


def test_python_relative_import_out_of_root_target_id_is_portable(tmp_path):
    """#2243 is not C-specific: it is a gap in the shared target_file remap path
    every language resolver funnels through. Python's cross-directory relative
    import already stamped `target_file` (#1814/#2169) -- but for a genuinely
    out-of-root target that stamp was still discarded ("out-of-root target:
    leave its ids alone") with no fallback, so the raw absolute-path id leaked
    exactly as it did for C. Covering this second, independent consumer of the
    same remap path guards against a fix that only special-cased `_import_c`."""
    app = tmp_path / "app"
    app.mkdir()
    lib = tmp_path / "lib"
    lib.mkdir()
    (app / "__init__.py").write_text("")
    (lib / "__init__.py").write_text("")
    (lib / "mod.py").write_text("def compute(x):\n    return x + 1\n")
    (app / "main.py").write_text(
        "from ..lib.mod import compute\n\ndef run():\n    return compute(1)\n"
    )
    result = extract([app / "main.py", app / "__init__.py"], cache_root=app)
    marker = str(tmp_path)
    for e in result["edges"]:
        assert marker not in str(e.get("target", "")), f"leaked into edge target: {e}"
    import_edges = [e for e in result["edges"] if e["relation"] == "imports_from"]
    assert import_edges
    assert import_edges[0]["target"] == "ext_lib_mod_py"


def test_python_module_qualified_call_resolves_extracted(tmp_path):
    """`module.func()` where `module` is imported resolves to the callable that
    module contains, with an EXTRACTED `calls` edge (#1883), even when the caller
    file contains a same-named function that bare-name lookup could select."""
    mathlib = tmp_path / "mathlib.py"
    caller = tmp_path / "caller.py"
    mathlib.write_text("def compute(x):\n    return x * 2\n")
    caller.write_text(
        "import mathlib\n\n"
        "def compute(x):\n"
        "    return x + 1\n\n"
        "def use_qualified(n):\n"
        "    return mathlib.compute(n)\n"
    )
    result = extract([caller, mathlib], cache_root=tmp_path)
    nodes = {n["id"]: n for n in result["nodes"]}
    edges = [
        e for e in result["edges"]
        if e["relation"] == "calls"
        and "use_qualified" in nodes[e["source"]]["label"]
        and "compute" in nodes[e["target"]]["label"]
    ]
    assert len(edges) == 1, f"expected one use_qualified->compute edge, got {edges}"
    assert "mathlib.py" in (nodes[edges[0]["target"]].get("source_file") or "")
    assert edges[0]["confidence"] == "EXTRACTED"


def test_python_module_qualified_call_requires_the_import(tmp_path):
    """A `module.func()` call must resolve only against a module the caller's own
    file imports — a local instance `o.compute()` (o is a parameter) must NOT be
    linked to a same-named function in some other module (#1883 false-edge guard)."""
    mathlib = tmp_path / "mathlib.py"
    caller = tmp_path / "caller.py"
    mathlib.write_text("def compute(x):\n    return x * 2\n")
    # no `import mathlib`; `o` is just a parameter that happens to expose compute()
    caller.write_text("def via_obj(o):\n    return o.compute(3)\n")
    result = extract([caller, mathlib], cache_root=tmp_path)
    nodes = {n["id"]: n for n in result["nodes"]}
    bad = [
        e for e in result["edges"]
        if e["relation"] == "calls"
        and "via_obj" in nodes[e["source"]]["label"]
        and "compute" in nodes[e["target"]]["label"]
    ]
    assert bad == [], f"non-imported receiver must not link cross-file: {bad}"


def test_python_from_import_alias_module_call_resolves(tmp_path):
    """`from pkg import mod as alias` must resolve `alias.func()` the same way the
    unaliased `from pkg import mod` / `mod.func()` form already does (#2082). The
    local alias binding was untracked, so the aliased receiver never matched the
    submodule's own stem and the `calls` edge silently disappeared while the
    file-level `imports_from` edge stayed present and made the graph look intact.

    Also covers the fix's `local_alias` hint hygiene: like the existing
    `target_file` transient hint (#1814), it must be popped once the resolver
    that reads it has run, never surviving into the returned edges/graph.json --
    otherwise an internal local-variable name from the source tree leaks into
    every graph.json produced from an aliased import."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "gate.py").write_text("def validate(rows):\n    return bool(rows)\n")
    caller = pkg / "caller.py"
    caller.write_text(
        "from pkg import gate as m_gate\n\n"
        "def use_alias(rows):\n"
        "    return m_gate.validate(rows)\n"
    )
    result = extract(
        [caller, pkg / "gate.py", pkg / "__init__.py"],
        cache_root=tmp_path,
        root=tmp_path,
    )
    nodes = {n["id"]: n for n in result["nodes"]}
    edges = [
        e for e in result["edges"]
        if e["relation"] == "calls"
        and "use_alias" in nodes[e["source"]]["label"]
        and "validate" in nodes[e["target"]]["label"]
        and "gate.py" in (nodes[e["target"]].get("source_file") or "")
    ]
    assert len(edges) == 1, f"expected one use_alias->validate edge, got {edges}"
    assert edges[0]["confidence"] == "EXTRACTED"
    leaked = [e for e in result["edges"] if "local_alias" in e]
    assert leaked == [], f"local_alias hint must not survive into the output: {leaked}"


def test_python_import_as_alias_module_call_resolves(tmp_path):
    """`import mod as alias` must resolve `alias.func()` the same way `import mod`
    / `mod.func()` already does (#1883) -- the same untracked-alias regression as
    `from pkg import mod as alias` (#2082), on the plain `import` form."""
    mathlib = tmp_path / "mathlib.py"
    caller = tmp_path / "caller.py"
    mathlib.write_text("def compute(x):\n    return x * 2\n")
    caller.write_text(
        "import mathlib as m\n\n"
        "def use_aliased_import(n):\n"
        "    return m.compute(n)\n"
    )
    result = extract([caller, mathlib], cache_root=tmp_path)
    nodes = {n["id"]: n for n in result["nodes"]}
    edges = [
        e for e in result["edges"]
        if e["relation"] == "calls"
        and "use_aliased_import" in nodes[e["source"]]["label"]
        and "compute" in nodes[e["target"]]["label"]
        and "mathlib.py" in (nodes[e["target"]].get("source_file") or "")
    ]
    assert len(edges) == 1, f"expected one use_aliased_import->compute edge, got {edges}"
    assert edges[0]["confidence"] == "EXTRACTED"


def test_python_try_except_from_import_alias_module_call_resolves(tmp_path):
    """The issue's own motivating shape (#2082): `from pkg import mod as alias`
    guarded by a `try:`/`except ImportError:` fallback assignment, the pattern
    real code uses for an optional dependency. The issue explicitly called out
    that the drop is independent of the `try:` nesting -- this locks that in as
    a regression test rather than relying only on the unwrapped module-level
    form above."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "gate.py").write_text("def validate(rows):\n    return bool(rows)\n")
    caller = pkg / "caller_try.py"
    caller.write_text(
        "try:\n"
        "    from pkg import gate as t_gate\n"
        "except ImportError:\n"
        "    t_gate = None\n\n"
        "def use_try_alias(rows):\n"
        "    return t_gate.validate(rows)\n"
    )
    result = extract(
        [caller, pkg / "gate.py", pkg / "__init__.py"],
        cache_root=tmp_path,
        root=tmp_path,
    )
    nodes = {n["id"]: n for n in result["nodes"]}
    edges = [
        e for e in result["edges"]
        if e["relation"] == "calls"
        and "use_try_alias" in nodes[e["source"]]["label"]
        and "validate" in nodes[e["target"]]["label"]
        and "gate.py" in (nodes[e["target"]].get("source_file") or "")
    ]
    assert len(edges) == 1, f"expected one use_try_alias->validate edge, got {edges}"
    assert edges[0]["confidence"] == "EXTRACTED"


def test_python_dotted_import_alias_module_call_resolves(tmp_path):
    """`import pkg.mod as alias` -- the dotted absolute-import form the issue
    flagged as needing coverage -- must resolve `alias.func()` the same way the
    single-segment `import mathlib as m` form above does. This exercises the
    `aliased_import` branch of `_import_python`'s `import_statement` arm with a
    multi-segment module name, where the target id comes from collapsing
    `pkg.gate` rather than a bare stem."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "gate.py").write_text("def validate(rows):\n    return bool(rows)\n")
    caller = pkg / "caller_dotted.py"
    caller.write_text(
        "import pkg.gate as g_alias\n\n"
        "def use_dotted_alias(rows):\n"
        "    return g_alias.validate(rows)\n"
    )
    result = extract(
        [caller, pkg / "gate.py", pkg / "__init__.py"],
        cache_root=tmp_path,
        root=tmp_path,
    )
    nodes = {n["id"]: n for n in result["nodes"]}
    edges = [
        e for e in result["edges"]
        if e["relation"] == "calls"
        and "use_dotted_alias" in nodes[e["source"]]["label"]
        and "validate" in nodes[e["target"]]["label"]
        and "gate.py" in (nodes[e["target"]].get("source_file") or "")
    ]
    assert len(edges) == 1, f"expected one use_dotted_alias->validate edge, got {edges}"
    assert edges[0]["confidence"] == "EXTRACTED"


def test_python_relative_from_import_alias_module_call_resolves(tmp_path):
    """`from . import mod as alias` -- a relative sibling-module import with an
    alias -- must resolve `alias.func()` the same way the absolute `from pkg
    import mod as alias` form above does. Relative imports route through the
    same #1146 submodule-import path (module_imports' local_name slot) with a
    level instead of an absolute module name, which is a distinct branch from
    the absolute-import case already covered."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "gate.py").write_text("def validate(rows):\n    return bool(rows)\n")
    caller = pkg / "caller_relative.py"
    caller.write_text(
        "from . import gate as r_gate\n\n"
        "def use_relative_alias(rows):\n"
        "    return r_gate.validate(rows)\n"
    )
    result = extract(
        [caller, pkg / "gate.py", pkg / "__init__.py"],
        cache_root=tmp_path,
        root=tmp_path,
    )
    nodes = {n["id"]: n for n in result["nodes"]}
    edges = [
        e for e in result["edges"]
        if e["relation"] == "calls"
        and "use_relative_alias" in nodes[e["source"]]["label"]
        and "validate" in nodes[e["target"]]["label"]
        and "gate.py" in (nodes[e["target"]].get("source_file") or "")
    ]
    assert len(edges) == 1, f"expected one use_relative_alias->validate edge, got {edges}"
    assert edges[0]["confidence"] == "EXTRACTED"


def test_python_external_aliased_import_fabricates_no_call_edge(tmp_path):
    """#2082 must not over-resolve: an aliased import of an EXTERNAL/uncorpus
    module (`import numpy as np; np.array()`) has no in-corpus callee, so it must
    produce NO `calls` edge — the alias resolution stays inside the member-call
    carve-out (in-corpus target required)."""
    caller = tmp_path / "app.py"
    caller.write_text(
        "import numpy as np\n"
        "from os import path as p\n\n"
        "def build(rows):\n"
        "    p.join('a', 'b')\n"
        "    return np.array(rows)\n"
    )
    result = extract([caller], cache_root=tmp_path, root=tmp_path)
    nodes = {n["id"]: n for n in result["nodes"]}
    fabricated = [
        e for e in result["edges"]
        if e["relation"] in ("calls", "indirect_call")
        and ("array" in nodes.get(e["target"], {}).get("label", "")
             or "join" in nodes.get(e["target"], {}).get("label", ""))
    ]
    assert fabricated == [], f"external aliased calls must not fabricate edges: {fabricated}"


def test_python_aliased_call_survives_warm_cache(tmp_path):
    """#2082: the aliased `calls` edge must survive a warm (cache-hit) re-extract.
    The fix threads a transient `local_alias` hint that is popped after the
    resolver runs; the per-file cache must serialize it BEFORE the pop, or the
    edge would resolve only on a cold run and silently vanish on the next."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "gate.py").write_text("def validate(rows):\n    return bool(rows)\n")
    caller = pkg / "caller.py"
    caller.write_text(
        "from pkg import gate as m_gate\n\n"
        "def use_alias(rows):\n"
        "    return m_gate.validate(rows)\n"
    )
    paths = [caller, pkg / "gate.py", pkg / "__init__.py"]

    def _alias_edges(result):
        nodes = {n["id"]: n for n in result["nodes"]}
        return [
            e for e in result["edges"]
            if e["relation"] == "calls"
            and "use_alias" in nodes[e["source"]]["label"]
            and "validate" in nodes[e["target"]]["label"]
        ]

    cold = extract(paths, cache_root=tmp_path, root=tmp_path)
    assert len(_alias_edges(cold)) == 1, "cold run must resolve the aliased call"
    warm = extract(paths, cache_root=tmp_path, root=tmp_path)  # cache-hit
    assert len(_alias_edges(warm)) == 1, "aliased call edge vanished on warm cache (#2082)"


def test_python_qualified_call_resolves_when_method_name_collides_with_caller(tmp_path):
    """The real #1446 shape: a viewset action `approve()` delegates to a SERVICE
    action of the SAME name via `Service.approve()`. The bare-name in-file lookup
    would match the caller's own node (tgt == caller) and silently drop the call;
    the qualified receiver must still resolve it cross-file to the service method."""
    actions = tmp_path / "actions.py"
    viewset = tmp_path / "viewset.py"
    actions.write_text(
        "class TaskActions:\n"
        "    @staticmethod\n"
        "    def approve(pk):\n"
        "        return pk\n"
    )
    viewset.write_text(
        "from actions import TaskActions\n\n"
        "class TaskViewSet:\n"
        "    def approve(self, request):\n"          # same name as the callee
        "        return TaskActions.approve(request)\n"
    )
    result = extract([viewset, actions], cache_root=tmp_path)
    nodes = {n["id"]: n for n in result["nodes"]}
    cross = [
        e for e in result["edges"]
        if e["relation"] == "calls"
        and "viewset.py" in (nodes[e["source"]].get("source_file") or "")
        and "actions.py" in (nodes[e["target"]].get("source_file") or "")
        and "approve" in nodes[e["target"]]["label"]
    ]
    assert len(cross) == 1, f"expected viewset->service approve edge, got {cross}"
    assert cross[0]["confidence"] == "EXTRACTED"


def test_python_instance_member_call_not_overconnected(tmp_path):
    """A lowercase-receiver member call (`obj.run()`, `self.run()`) must NOT be
    resolved cross-file — the #543/#1219 god-node guard stays intact (#1446)."""
    svc = tmp_path / "svc.py"
    worker = tmp_path / "worker.py"
    svc.write_text(
        "class Service:\n"
        "    def run(self):\n"
        "        return 1\n"
    )
    worker.write_text(
        "class Worker:\n"
        "    def go(self, obj):\n"
        "        return obj.run()\n"
    )
    result = extract([worker, svc], cache_root=tmp_path)
    nodes = {n["id"]: n for n in result["nodes"]}
    bad = [
        e for e in result["edges"]
        if e["relation"] == "calls"
        and "go" in nodes[e["source"]]["label"]
        and "run" in nodes[e["target"]]["label"]
    ]
    assert bad == [], f"instance member call must not connect cross-file: {bad}"


def test_python_unresolved_member_calls_do_not_bind_to_bare_function(tmp_path):
    """#2417: unresolved attribute calls must not bind by bare method name.

    ``d.get()`` and ``self.store.get()`` do not identify the module-level
    ``get()`` definition, so only the direct ``get()`` call is a real edge.
    The result must also survive a warm cache extraction.
    """
    fixture = tmp_path / "fixture.py"
    fixture.write_text(
        "def get(k):\n"
        "    return k\n\n"
        "class Store:\n"
        "    def __init__(self):\n"
        "        self.store = {}\n\n"
        "    def read(self, k):\n"
        "        return self.store.get(k)\n\n"
        "def other(d):\n"
        "    return d.get('x')\n\n"
        "def real():\n"
        "    return get('real')\n",
        encoding="utf-8",
    )

    def _get_callers(result):
        nodes = {node["id"]: node for node in result["nodes"]}
        target_ids = {
            node["id"] for node in result["nodes"]
            if node.get("label") == "get()" and node.get("source_file")
        }
        return sorted(
            nodes[edge["source"]]["label"]
            for edge in result["edges"]
            if edge.get("relation") == "calls" and edge.get("target") in target_ids
        )

    cold = extract([fixture], cache_root=tmp_path, root=tmp_path)
    assert _get_callers(cold) == ["real()"]
    warm = extract([fixture], cache_root=tmp_path, root=tmp_path)
    assert _get_callers(warm) == ["real()"]


def test_python_known_member_receivers_keep_local_call_edges(tmp_path):
    """Preserve self/cls/super calls while deferring other call receivers."""
    fixture = tmp_path / "known_receivers.py"
    fixture.write_text(
        "class Base:\n"
        "    def inherited(self):\n"
        "        return 1\n\n"
        "class Worker(Base):\n"
        "    def local(self):\n"
        "        return 2\n\n"
        "    @classmethod\n"
        "    def class_local(cls):\n"
        "        return 3\n\n"
        "    def via_self(self):\n"
        "        return self.local()\n\n"
        "    @classmethod\n"
        "    def via_cls(cls):\n"
        "        return cls.class_local()\n\n"
        "    def via_super(self):\n"
        "        return super().inherited()\n\n"
        "def via_factory(factory):\n"
        "    return factory().local()\n",
        encoding="utf-8",
    )
    result = extract([fixture], cache_root=tmp_path, root=tmp_path)
    nodes = {node["id"]: node for node in result["nodes"]}
    call_pairs = {
        (nodes[edge["source"]]["label"], nodes[edge["target"]]["label"])
        for edge in result["edges"]
        if edge.get("relation") == "calls"
    }

    for caller, callee in (
        ("via_self", "local"),
        ("via_cls", "class_local"),
        ("via_super", "inherited"),
    ):
        assert any(
            caller in source_label and callee in target_label
            for source_label, target_label in call_pairs
        ), f"missing {caller} -> {callee} call edge: {call_pairs}"
    assert not any(
        "via_factory" in source_label and "local" in target_label
        for source_label, target_label in call_pairs
    ), f"unresolved factory() receiver must not bind by bare name: {call_pairs}"


def test_python_unresolved_receiver_never_crosses_modules(tmp_path):
    """#2417 cross-file guard: `client.fetch('x')` must not bind to `util.fetch`
    just because the caller's file imports that name — the receiver `client`
    supplies no evidence it is the `util` module. A plain `fetch('y')` call to
    the imported name still resolves."""
    util = tmp_path / "util.py"
    caller = tmp_path / "app.py"
    util.write_text("def fetch(url):\n    return url\n")
    caller.write_text(
        "from util import fetch\n\n"
        "def via_receiver(client):\n"
        "    return client.fetch('x')\n\n"
        "def via_name():\n"
        "    return fetch('y')\n"
    )
    result = extract([caller, util], cache_root=tmp_path)
    nodes = {n["id"]: n for n in result["nodes"]}
    fetch_edges = [
        (nodes[e["source"]]["label"], e)
        for e in result["edges"]
        if e["relation"] == "calls"
        and "fetch" in nodes[e["target"]]["label"]
        and "util.py" in (nodes[e["target"]].get("source_file") or "")
    ]
    callers = sorted(label for label, _ in fetch_edges)
    assert not any("via_receiver" in c for c in callers), (
        f"unresolved receiver bound cross-module by bare name: {callers}"
    )
    assert any("via_name" in c for c in callers), (
        f"imported-name call lost its edge: {callers}"
    )


def test_python_qualified_call_ambiguous_class_bails(tmp_path):
    """When the class name is defined in 2+ files, the qualified call must not
    resolve — single-definition god-node guard (#1446)."""
    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    caller = tmp_path / "caller.py"
    a.write_text("class Helper:\n    def do(self):\n        return 1\n")
    b.write_text("class Helper:\n    def do(self):\n        return 2\n")
    caller.write_text(
        "from a import Helper\n\n"
        "class C:\n"
        "    def f(self):\n"
        "        return Helper.do(self)\n"
    )
    result = extract([caller, a, b], cache_root=tmp_path)
    nodes = {n["id"]: n for n in result["nodes"]}
    resolved = [
        e for e in result["edges"]
        if e["relation"] == "calls"
        and "f" == nodes[e["source"]]["label"].strip("().")
        and "do" in nodes[e["target"]]["label"]
    ]
    assert resolved == [], f"ambiguous class name must not resolve: {resolved}"


# ── TSX (JSX-aware) parsing ──────────────────────────────────────────────────
# .tsx files require tree-sitter-typescript's `language_tsx`, not the plain
# `language_typescript` grammar. Parsing JSX with the wrong grammar produces
# silent ERROR nodes and drops every function/call inside JSX trees.

def test_extract_tsx_finds_helpers_and_component():
    """Functions defined alongside a JSX-returning component must be captured."""
    from graphify.extract import extract_js
    result = extract_js(FIXTURES / "sample.tsx")
    labels = [n["label"] for n in result["nodes"]]
    assert any("fmtDate" in l for l in labels), f"fmtDate missing from {labels}"
    assert any("fmtCount" in l for l in labels), f"fmtCount missing from {labels}"
    assert any("App" in l for l in labels), f"App missing from {labels}"


def test_extract_tsx_jsx_expression_calls_resolve():
    """Calls inside JSX expressions like `{fmtDate(now)}` must yield call edges.

    Regression guard for the TSX language fix: with `language_typescript`,
    JSX is parsed as ERROR nodes and these call_expressions disappear.
    """
    from graphify.extract import extract_js
    result = extract_js(FIXTURES / "sample.tsx")
    nodes_by_id = {n["id"]: n for n in result["nodes"]}
    call_targets = {
        nodes_by_id[e["target"]]["label"]
        for e in result["edges"]
        if e["relation"] == "calls" and e["target"] in nodes_by_id
    }
    assert "fmtDate()" in call_targets, (
        f"JSX expression call to fmtDate() not captured. Targets: {call_targets}"
    )
    assert "fmtCount()" in call_targets, (
        f"JSX expression call to fmtCount() not captured. Targets: {call_targets}"
    )


def test_extract_tsx_uses_tsx_grammar():
    """Wiring check: the .tsx config must use tree-sitter's `language_tsx`."""
    from graphify.extract import _TSX_CONFIG, _TS_CONFIG
    assert _TSX_CONFIG.ts_language_fn == "language_tsx"
    assert _TS_CONFIG.ts_language_fn == "language_typescript"


# --- Windows-spawn ProcessPool fallback (regression for #?) ---
# When the caller has no `if __name__ == "__main__":` guard, ProcessPoolExecutor
# on Windows raises BrokenProcessPool before any work completes. extract() must
# detect this, warn, and fall back to sequential extraction rather than
# propagating a 290-line traceback.

def test_extract_falls_back_to_sequential_when_parallel_returns_false(tmp_path, monkeypatch):
    """extract() must run sequential when _extract_parallel signals failure (returns False)."""
    from graphify import extract as extract_mod

    files = [FIXTURES / "sample.py"] * 25  # >= _PARALLEL_THRESHOLD triggers parallel branch
    cache_root = tmp_path / "cache"
    cache_root.mkdir()

    calls = {"parallel": 0, "sequential": 0}
    real_sequential = extract_mod._extract_sequential

    def fake_parallel(uncached_work, per_file, root, max_workers, total_files, cache_location=None):
        calls["parallel"] += 1
        return False  # simulate the post-fix BrokenProcessPool branch

    def wrapped_sequential(*args, **kwargs):
        calls["sequential"] += 1
        return real_sequential(*args, **kwargs)

    monkeypatch.setattr(extract_mod, "_extract_parallel", fake_parallel)
    monkeypatch.setattr(extract_mod, "_extract_sequential", wrapped_sequential)

    result = extract_mod.extract(files, cache_root=cache_root)
    assert calls["parallel"] == 1, "parallel path should have been attempted once"
    assert calls["sequential"] == 1, "sequential fallback should have run exactly once"
    assert result["nodes"], "extract should still produce nodes after fallback"


def test_extract_parallel_returns_false_on_broken_pool(tmp_path, monkeypatch, capsys):
    """_extract_parallel must catch BrokenProcessPool internally and return False."""
    from concurrent.futures.process import BrokenProcessPool
    import concurrent.futures
    from graphify import extract as extract_mod

    class FakePool:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def submit(self, *a, **kw):
            raise BrokenProcessPool("simulated spawn failure")

    monkeypatch.setattr(
        concurrent.futures, "ProcessPoolExecutor", lambda *a, **kw: FakePool()
    )

    uncached = [(0, FIXTURES / "sample.py")]
    per_file: list = [None]
    ok = extract_mod._extract_parallel(uncached, per_file, tmp_path, 2, 1)
    assert ok is False, "function should report failure via return value, not raise"
    out = capsys.readouterr().out
    assert "BrokenProcessPool" in out, "user-facing warning must mention the failure"
    assert "__main__" in out, "warning must hint at the Windows __main__ guard idiom"


def test_extract_parallel_skips_pool_when_max_workers_is_one(tmp_path, monkeypatch):
    """#2173: a resolved worker count of 1 must not spawn a ProcessPoolExecutor.

    The Windows post-commit hook exports GRAPHIFY_MAX_WORKERS=1, so before this the
    rebuild spawned a one-worker pool for >= _PARALLEL_THRESHOLD files: no
    parallelism, one process spawn plus an IPC round trip per file, and the only
    window where the parent's rebuild watchdog (os._exit) can orphan a worker
    mid-task. _extract_parallel must decline (return False) so the caller extracts
    sequentially in-process.
    """
    import concurrent.futures
    from graphify import extract as extract_mod

    spawned = {"count": 0}

    def fake_pool(*args, **kwargs):
        spawned["count"] += 1
        raise AssertionError("ProcessPoolExecutor must not be constructed for 1 worker")

    monkeypatch.setattr(concurrent.futures, "ProcessPoolExecutor", fake_pool)
    monkeypatch.setenv("GRAPHIFY_MAX_WORKERS", "1")

    uncached = [(i, FIXTURES / "sample.py") for i in range(25)]  # >= _PARALLEL_THRESHOLD
    per_file: list = [None] * len(uncached)

    ok = extract_mod._extract_parallel(uncached, per_file, tmp_path, None, len(uncached))
    assert ok is False, "must hand the work back for sequential extraction"
    assert spawned["count"] == 0, "no pool may be spawned when max_workers resolves to 1"


def test_extract_parallel_still_spawns_pool_for_multiple_workers(tmp_path, monkeypatch):
    """Guard the #2173 skip: >1 worker must still take the pool path."""
    import concurrent.futures
    from graphify import extract as extract_mod

    spawned = {"count": 0}

    class FakePool:
        def __init__(self, *a, **kw):
            spawned["count"] += 1
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def submit(self, *a, **kw):
            raise concurrent.futures.process.BrokenProcessPool("stop here")

    monkeypatch.setattr(concurrent.futures, "ProcessPoolExecutor", FakePool)
    monkeypatch.setenv("GRAPHIFY_MAX_WORKERS", "4")

    uncached = [(i, FIXTURES / "sample.py") for i in range(25)]
    per_file: list = [None] * len(uncached)

    extract_mod._extract_parallel(uncached, per_file, tmp_path, None, len(uncached))
    assert spawned["count"] == 1, "multi-worker runs must still use the pool"


def test_extract_falls_back_when_worker_future_breaks_pool(
    tmp_path, monkeypatch, capsys
):
    """#2444: a BrokenProcessPool raised from future.result() (pool died while
    results were being consumed) must trigger the sequential fallback, not be
    swallowed per-future leaving empty per_file slots."""
    from concurrent.futures.process import BrokenProcessPool
    import concurrent.futures
    from graphify import extract as extract_mod

    class BrokenFuture:
        def result(self):
            raise BrokenProcessPool("simulated worker termination")

    class FakePool:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def submit(self, *a, **kw):
            return BrokenFuture()

    monkeypatch.setattr(concurrent.futures, "ProcessPoolExecutor", FakePool)
    monkeypatch.setattr(
        concurrent.futures, "as_completed", lambda futures: iter(futures)
    )
    # A 1-CPU runner resolves max_workers to 1 and never enters the pool (#2173).
    monkeypatch.setenv("GRAPHIFY_MAX_WORKERS", "2")

    sequential_calls = 0
    real_sequential = extract_mod._extract_sequential

    def wrapped_sequential(*args, **kwargs):
        nonlocal sequential_calls
        sequential_calls += 1
        return real_sequential(*args, **kwargs)

    monkeypatch.setattr(extract_mod, "_extract_sequential", wrapped_sequential)

    files = [FIXTURES / "sample.py"] * 25  # >= _PARALLEL_THRESHOLD
    result = extract_mod.extract(files, cache_root=tmp_path / "cache")

    assert sequential_calls == 1, "sequential fallback should have run exactly once"
    assert result["nodes"], "sequential fallback must recover AST nodes"
    assert "BrokenProcessPool" in capsys.readouterr().out


def test_extract_bpp_fallback_skips_already_completed_files(tmp_path, monkeypatch):
    """#2444: when the pool breaks mid-run, the sequential fallback must
    re-extract only the files whose futures never completed."""
    from concurrent.futures.process import BrokenProcessPool
    import concurrent.futures
    from graphify import extract as extract_mod

    completed_before_break = 5

    class GoodFuture:
        def __init__(self, value): self._value = value
        def result(self): return self._value

    class BrokenFuture:
        def result(self):
            raise BrokenProcessPool("simulated worker termination")

    class FakePool:
        def __init__(self, *a, **kw):
            self._submitted = 0
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def submit(self, fn, item):
            self._submitted += 1
            if self._submitted <= completed_before_break:
                return GoodFuture(fn(item))  # extract in-process, eagerly
            return BrokenFuture()

    monkeypatch.setattr(concurrent.futures, "ProcessPoolExecutor", FakePool)
    monkeypatch.setattr(
        concurrent.futures, "as_completed", lambda futures: iter(futures)
    )
    monkeypatch.setenv("GRAPHIFY_MAX_WORKERS", "2")

    retried: list[list[int]] = []
    real_sequential = extract_mod._extract_sequential

    def wrapped_sequential(uncached_work, *args, **kwargs):
        retried.append([idx for idx, _ in uncached_work])
        return real_sequential(uncached_work, *args, **kwargs)

    monkeypatch.setattr(extract_mod, "_extract_sequential", wrapped_sequential)

    files = [FIXTURES / "sample.py"] * 25
    result = extract_mod.extract(files, cache_root=tmp_path / "cache")

    assert len(retried) == 1, "sequential fallback should have run exactly once"
    assert sorted(retried[0]) == list(range(completed_before_break, 25)), (
        "files whose futures completed before the pool broke must not be re-extracted"
    )
    assert result["nodes"]


def test_extract_parallel_retries_failed_future_sequentially(
    tmp_path, monkeypatch, capsys
):
    """#2445: a non-BPP per-future failure must be surfaced and retried
    in-process, not silently replaced by a well-formed empty result."""
    import concurrent.futures
    from graphify import extract as extract_mod

    class GoodFuture:
        def __init__(self, value): self._value = value
        def result(self): return self._value

    class FailingFuture:
        def result(self):
            raise RuntimeError("simulated worker crash")

    class FakePool:
        def __init__(self, *a, **kw):
            self._submitted = 0
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def submit(self, fn, item):
            self._submitted += 1
            if self._submitted == 1:
                return FailingFuture()
            return GoodFuture(fn(item))

    monkeypatch.setattr(concurrent.futures, "ProcessPoolExecutor", FakePool)
    monkeypatch.setattr(
        concurrent.futures, "as_completed", lambda futures: iter(futures)
    )
    monkeypatch.setenv("GRAPHIFY_MAX_WORKERS", "2")

    retried: list[list[int]] = []
    real_sequential = extract_mod._extract_sequential

    def wrapped_sequential(uncached_work, *args, **kwargs):
        retried.append([idx for idx, _ in uncached_work])
        return real_sequential(uncached_work, *args, **kwargs)

    monkeypatch.setattr(extract_mod, "_extract_sequential", wrapped_sequential)

    files = [FIXTURES / "sample.py"] * 25
    result = extract_mod.extract(files, cache_root=tmp_path / "cache")

    assert retried == [[0]], "only the failed file may be retried, exactly once"
    assert result["nodes"]
    err = capsys.readouterr().err
    assert "worker failed" in err
    assert "zero nodes" not in err, (
        "a retried-and-recovered file must not trip the #1666 empty warning"
    )


def test_extract_twice_failing_file_carries_error_marker(tmp_path, monkeypatch):
    """#2445: a file that fails in the pool AND on the sequential retry must
    end up with an error-carrying result (via _safe_extract), not loop and not
    masquerade as legitimately empty. Other files still complete."""
    import concurrent.futures
    from graphify import extract as extract_mod

    bad_file = tmp_path / "boom.go"
    bad_file.write_text("package main\n")

    def _boom_extractor(path):
        raise RuntimeError("extractor always crashes")

    monkeypatch.setitem(extract_mod._DISPATCH, ".go", _boom_extractor)

    class GoodFuture:
        def __init__(self, value): self._value = value
        def result(self): return self._value

    class FailingFuture:
        def result(self):
            raise RuntimeError("simulated worker crash")

    class FakePool:
        def __init__(self, *a, **kw):
            self._submitted = 0
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def submit(self, fn, item):
            self._submitted += 1
            if self._submitted == 1:  # boom.go is first in the batch
                return FailingFuture()
            return GoodFuture(fn(item))

    monkeypatch.setattr(concurrent.futures, "ProcessPoolExecutor", FakePool)
    monkeypatch.setattr(
        concurrent.futures, "as_completed", lambda futures: iter(futures)
    )
    monkeypatch.setenv("GRAPHIFY_MAX_WORKERS", "2")

    captured: dict = {"calls": 0}
    real_sequential = extract_mod._extract_sequential

    def wrapped_sequential(uncached_work, per_file, *args, **kwargs):
        captured["calls"] += 1
        captured["retry_indices"] = [idx for idx, _ in uncached_work]
        real_sequential(uncached_work, per_file, *args, **kwargs)
        captured["per_file"] = list(per_file)

    monkeypatch.setattr(extract_mod, "_extract_sequential", wrapped_sequential)

    files = [bad_file] + [FIXTURES / "sample.py"] * 24
    result = extract_mod.extract(files, cache_root=tmp_path / "cache")

    assert captured["calls"] == 1, "the retry must be bounded: one pass, no loop"
    assert captured["retry_indices"] == [0]
    assert "error" in captured["per_file"][0], (
        "a twice-failing file must carry an error marker, not a clean empty"
    )
    assert result["nodes"], "the other files must still complete"


def test_extract_legitimately_empty_result_keeps_no_error_marker(
    tmp_path, monkeypatch, capsys
):
    """Guard for the #2445 error-marked None-fill: a file whose extractor
    genuinely returns zero nodes gets a real (marker-free) result and still
    trips the #1666 zero-nodes warning — behavior unchanged."""
    from graphify import extract as extract_mod

    empty_file = tmp_path / "empty.go"
    empty_file.write_text("package main\n")

    monkeypatch.setitem(
        extract_mod._DISPATCH, ".go", lambda path: {"nodes": [], "edges": []}
    )

    captured: dict = {}
    real_sequential = extract_mod._extract_sequential

    def wrapped_sequential(uncached_work, per_file, *args, **kwargs):
        real_sequential(uncached_work, per_file, *args, **kwargs)
        captured["per_file"] = list(per_file)

    monkeypatch.setattr(extract_mod, "_extract_sequential", wrapped_sequential)

    extract_mod.extract([empty_file], cache_root=tmp_path / "cache")

    assert "error" not in captured["per_file"][0], (
        "a legitimately-empty extraction must not be error-marked"
    )
    assert "zero nodes" in capsys.readouterr().err, (
        "the #1666 zero-nodes warning must still fire for a genuine empty"
    )


# ---------------------------------------------------------------------------
# Bash extractor tests (#866)
# ---------------------------------------------------------------------------

def test_dispatch_includes_sh_and_json():
    assert ".sh" in _DISPATCH
    assert ".bash" in _DISPATCH
    assert ".json" in _DISPATCH


def test_extract_bash_finds_functions():
    result = extract_bash(FIXTURES / "sample.sh")
    assert "error" not in result
    labels = {n["label"] for n in result["nodes"]}
    assert "build()" in labels
    assert "test_suite()" in labels
    assert "deploy()" in labels


def test_extract_bash_emits_defines_edges():
    result = extract_bash(FIXTURES / "sample.sh")
    relations = {e["relation"] for e in result["edges"]}
    assert "defines" in relations


def test_extract_bash_emits_calls_edges():
    result = extract_bash(FIXTURES / "sample.sh")
    calls = [(e["source"], e["target"]) for e in result["edges"] if e["relation"] == "calls"]
    # deploy() calls build() and test_suite(); test_suite() calls build()
    assert any("deploy" in s and "build" in t for s, t in calls)
    assert any("deploy" in s and "test_suite" in t for s, t in calls)
    assert any("test_suite" in s and "build" in t for s, t in calls)


def test_extract_bash_calls_have_extracted_confidence():
    result = extract_bash(FIXTURES / "sample.sh")
    for e in result["edges"]:
        if e["relation"] == "calls":
            assert e["confidence"] == "EXTRACTED"
            assert e.get("context") == "call"


def test_extract_bash_emits_source_imports_from(tmp_path):
    helpers = tmp_path / "helpers.sh"
    helpers.write_text("# helper\n")
    script = tmp_path / "deploy.sh"
    script.write_text(f"#!/bin/bash\nsource ./helpers.sh\nfoo() {{ echo hi; }}\n")
    result = extract_bash(script)
    import_edges = [e for e in result["edges"] if e["relation"] == "imports_from"]
    assert len(import_edges) >= 1
    assert import_edges[0].get("context") == "import"


def test_extract_bash_source_via_variable_path_resolves_to_real_file(tmp_path):
    """`source "${DIR}/lib/x.sh"` (the `dirname "${BASH_SOURCE[0]}"` idiom) must
    resolve to the real file node relative to the script dir — never emit a dead
    id baking in the literal `${DIR}` text (#2079)."""
    lib = tmp_path / "lib"
    lib.mkdir()
    helper = lib / "gpu-discover.sh"
    helper.write_text("# helper\n", encoding="utf-8")
    script = tmp_path / "bench.sh"
    script.write_text(
        '#!/bin/bash\n'
        'BENCH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
        'source "${BENCH_DIR}/lib/gpu-discover.sh"\n',
        encoding="utf-8",
    )
    result = extract_bash(script)
    import_edges = [e for e in result["edges"] if e["relation"] == "imports_from"]
    targets = [e["target"] for e in import_edges]
    assert _make_id(str(helper.resolve())) in targets, import_edges
    assert not any("$" in t for t in targets), f"dead expansion id emitted: {targets}"
    inferred = next(e for e in import_edges
                    if e["target"] == _make_id(str(helper.resolve())))
    assert inferred.get("confidence") == "INFERRED"
    assert inferred.get("context") == "import"


def test_extract_bash_source_via_variable_path_no_match_emits_no_dead_edge(tmp_path):
    """A variable-built source path with no matching file on disk must emit no
    import edge at all — not an `imports` edge to an id containing `${VAR}` (#2079)."""
    script = tmp_path / "bench.sh"
    script.write_text(
        '#!/bin/bash\nsource "${BENCH_DIR}/lib/missing.sh"\n',
        encoding="utf-8",
    )
    result = extract_bash(script)
    edges = [e for e in result["edges"]
             if e["relation"] in ("imports", "imports_from")]
    assert edges == [], f"variable source with no on-disk match must emit no edge; got: {edges}"


@pytest.mark.parametrize("command", ["./helpers.sh", "bash ./helpers.sh"])
def test_extract_bash_emits_script_invocation_calls(tmp_path, command):
    helpers = tmp_path / "helpers.sh"
    helpers.write_text("#!/bin/bash\necho helper\n", encoding="utf-8")
    script = tmp_path / "deploy.sh"
    script.write_text(f"#!/bin/bash\n{command}\n", encoding="utf-8")

    result = extract_bash(script)
    invocation = [
        edge for edge in result["edges"]
        if edge.get("relation") == "calls" and edge.get("context") == "script_invocation"
    ]

    assert invocation == [{
        "source": _make_id(str(script)) + "__entry",
        "target": _make_id(str(helpers.resolve())) + "__entry",
        "relation": "calls",
        "confidence": "EXTRACTED",
        "source_file": str(script),
        "source_location": "L2",
        "weight": 1.0,
        "context": "script_invocation",
        # Transient canonicalization hint (#2243); popped before persist.
        "target_file": str(helpers.resolve()),
    }]


def test_extract_bash_skips_missing_and_shadowed_script_invocations(tmp_path):
    helpers = tmp_path / "helpers.sh"
    helpers.write_text("#!/bin/bash\necho helper\n", encoding="utf-8")
    script = tmp_path / "deploy.sh"
    script.write_text(
        "#!/bin/bash\n"
        "bash() { echo custom; }\n"
        "bash ./helpers.sh\n"
        "./missing.sh\n",
        encoding="utf-8",
    )

    result = extract_bash(script)

    assert not any(edge.get("context") == "script_invocation" for edge in result["edges"])


def test_extract_bash_skips_dynamic_script_invocation(tmp_path):
    helpers = tmp_path / "helpers.sh"
    helpers.write_text("#!/bin/bash\necho helper\n", encoding="utf-8")
    script = tmp_path / "deploy.sh"
    script.write_text('#!/bin/bash\nbash "./$SCRIPT.sh"\n', encoding="utf-8")

    result = extract_bash(script)

    assert not any(edge.get("context") == "script_invocation" for edge in result["edges"])


def test_extract_bash_relative_script_invocation_targets_existing_entrypoint(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    helpers = Path("helpers.sh")
    helpers.write_text("#!/bin/bash\necho helper\n", encoding="utf-8")
    script = Path("deploy.sh")
    script.write_text("#!/bin/bash\n./helpers.sh\n", encoding="utf-8")

    result = extract([script, helpers], cache_root=tmp_path, parallel=False)
    node_ids = {node["id"] for node in result["nodes"]}
    invocation = next(edge for edge in result["edges"] if edge.get("context") == "script_invocation")

    assert invocation["target"] in node_ids


def test_extract_bash_attributes_script_invocation_to_function(tmp_path):
    helpers = tmp_path / "helpers.sh"
    helpers.write_text("#!/bin/bash\necho helper\n", encoding="utf-8")
    script = tmp_path / "deploy.sh"
    script.write_text("#!/bin/bash\ndeploy() { bash ./helpers.sh; }\n", encoding="utf-8")

    result = extract_bash(script)
    deploy = next(node for node in result["nodes"] if node["label"] == "deploy()")
    invocation = next(edge for edge in result["edges"] if edge.get("context") == "script_invocation")

    assert invocation["source"] == deploy["id"]


def test_extract_bash_no_self_loops():
    result = extract_bash(FIXTURES / "sample.sh")
    for e in result["edges"]:
        assert e["source"] != e["target"], f"Self-loop: {e}"


def test_extract_bash_no_dangling_edges():
    result = extract_bash(FIXTURES / "sample.sh")
    node_ids = {n["id"] for n in result["nodes"]}
    for e in result["edges"]:
        assert e["source"] in node_ids, f"Dangling source: {e['source']}"
        # targets may reference external files (imports_from) — only check non-import edges
        if e["relation"] not in ("imports_from", "imports"):
            assert e["target"] in node_ids, f"Dangling target: {e['target']}"


def test_extract_bash_skip_builtins_in_calls():
    from graphify.extract import _file_stem, _make_id

    result = extract_bash(FIXTURES / "sample.sh")
    builtins = {"echo", "cd", "set", "export", "local", "mkdir", "if", "then"}
    # The file-stem prefix is now the full repo-relative path, which can embed a
    # builtin as a substring (e.g. "graphify" contains "if"). Compare against the
    # call's SYMBOL NAME — the id with its file-stem prefix stripped — so the
    # check tests the actual callee, not the path it lives in.
    prefix = _make_id(_file_stem(FIXTURES / "sample.sh")) + "_"
    call_names = {
        t[len(prefix):] if t.startswith(prefix) else t
        for e in result["edges"] if e["relation"] == "calls"
        for t in [e["target"]]
    }
    for b in builtins:
        assert b not in call_names, f"Builtin '{b}' appeared as calls target"


def test_extract_bash_missing_grammar_returns_error():
    """extract_bash returns error dict when tree-sitter-bash not installed (mocked)."""
    import unittest.mock as mock
    import builtins
    real_import = builtins.__import__

    def patched(name, *args, **kwargs):
        if name == "tree_sitter_bash":
            raise ImportError("mocked")
        return real_import(name, *args, **kwargs)

    with mock.patch("builtins.__import__", side_effect=patched):
        result = extract_bash(FIXTURES / "sample.sh")
    assert "error" in result
    assert result["nodes"] == []


def test_extract_bash_rejects_command_substitution_as_call(tmp_path):
    """`$(build)` must not be recorded as a call edge to build()."""
    script = tmp_path / "command_substitution.sh"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "build() { echo build; }\n"
        "$(build)\n"
    )
    result = extract_bash(script)
    labels = {n["id"]: n["label"] for n in result["nodes"]}
    call_pairs = [
        (labels.get(e["source"], e["source"]), labels.get(e["target"], e["target"]))
        for e in result["edges"]
        if e["relation"] == "calls"
    ]
    assert call_pairs == [], f"Command substitution erroneously emitted call edges: {call_pairs}"


def test_extract_bash_command_substitution_in_assignment_emits_call(tmp_path):
    """#2978: x=$(helper) inside a function must emit a calls edge to helper()."""
    script = tmp_path / "a.sh"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "helper() { echo ok; }\n"
        "bare()      { helper; }\n"
        "subst()     { x=$(helper); echo \"$x\"; }\n"
        "orlist()    { helper || return 1; }\n"
        "andlist()   { true && helper; }\n"
        "pipe()      { helper | cat; }\n"
        "cond()      { if helper; then :; fi; }\n"
        "loop()      { while helper; do break; done; }\n"
        "redir()     { helper >/dev/null; }\n"
        "neg()       { ! helper; }\n",
        encoding="utf-8",
    )
    result = extract_bash(script)
    labels = {n["id"]: n["label"] for n in result["nodes"]}
    call_pairs = [
        (labels.get(e["source"], e["source"]), labels.get(e["target"], e["target"]))
        for e in result["edges"]
        if e["relation"] == "calls"
    ]
    assert ("subst()", "helper()") in call_pairs
    assert ("bare()", "helper()") in call_pairs
    assert ("orlist()", "helper()") in call_pairs
    assert ("andlist()", "helper()") in call_pairs
    assert ("pipe()", "helper()") in call_pairs
    assert ("cond()", "helper()") in call_pairs
    assert ("loop()", "helper()") in call_pairs
    assert ("redir()", "helper()") in call_pairs
    assert ("neg()", "helper()") in call_pairs


def test_extract_bash_process_substitution_not_recorded(tmp_path):
    """`<(helper)` (process substitution) must not be recorded as a call edge."""
    script = tmp_path / "process_substitution.sh"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "helper() { echo h; }\n"
        "diff <(helper) <(helper)\n"
    )
    result = extract_bash(script)
    labels = {n["id"]: n["label"] for n in result["nodes"]}
    call_pairs = [
        (labels.get(e["source"], e["source"]), labels.get(e["target"], e["target"]))
        for e in result["edges"]
        if e["relation"] == "calls"
    ]
    assert call_pairs == [], f"Process substitution erroneously emitted call edges: {call_pairs}"


def test_extract_bash_shadowing_function_is_recorded(tmp_path):
    """User-defined function shadowing an external command (install/find/etc.) must still produce a call edge."""
    script = tmp_path / "shadowing.sh"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "install() { echo install; }\n"
        "deploy() { install; }\n"
    )
    result = extract_bash(script)
    labels = {n["id"]: n["label"] for n in result["nodes"]}
    call_pairs = [
        (labels.get(e["source"], e["source"]), labels.get(e["target"], e["target"]))
        for e in result["edges"]
        if e["relation"] == "calls"
    ]
    assert ("deploy()", "install()") in call_pairs, (
        f"Shadowing function call not recorded; got: {call_pairs}"
    )


def test_extract_bash_creates_entrypoint_node(tmp_path):
    """Every bash file produces a `bash_entrypoint` node distinct from the file node, joined by a `contains` edge."""
    script = tmp_path / "with_entrypoint.sh"
    script.write_text("#!/usr/bin/env bash\nfoo() { :; }\n")
    result = extract_bash(script)
    kinds = [n.get("metadata", {}).get("kind") for n in result["nodes"]]
    assert "bash_entrypoint" in kinds, f"No bash_entrypoint node; kinds={kinds}"
    assert "file" in kinds, f"No file node; kinds={kinds}"
    file_node = next(n for n in result["nodes"] if n.get("metadata", {}).get("kind") == "file")
    entry_node = next(n for n in result["nodes"] if n.get("metadata", {}).get("kind") == "bash_entrypoint")
    contains_edges = [
        e for e in result["edges"]
        if e["relation"] == "contains" and e["source"] == file_node["id"] and e["target"] == entry_node["id"]
    ]
    assert contains_edges, "Missing contains edge from file → bash_entrypoint"


def test_extract_bash_top_level_call_attributes_to_entrypoint(tmp_path):
    """Top-level function call attaches to the entrypoint node, not orphaned."""
    script = tmp_path / "top_level_call.sh"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "build() { echo build; }\n"
        "build\n"
    )
    result = extract_bash(script)
    entry_node = next(
        (n for n in result["nodes"] if n.get("metadata", {}).get("kind") == "bash_entrypoint"),
        None,
    )
    assert entry_node is not None, "No entrypoint node created"
    call_pairs = [
        (e["source"], e["target"])
        for e in result["edges"]
        if e["relation"] == "calls"
    ]
    target_ids = {tgt for _, tgt in call_pairs if any(n["id"] == tgt and n["label"] == "build()" for n in result["nodes"])}
    source_ids_to_build = {src for src, tgt in call_pairs if tgt in target_ids}
    assert entry_node["id"] in source_ids_to_build, (
        f"Top-level call to build not attributed to entrypoint; calls={call_pairs}"
    )


# ---------------------------------------------------------------------------
# PR #893 regression tests — bash extractor Copilot review findings
# ---------------------------------------------------------------------------


def test_extract_bash_entrypoint_no_collision_with_function_named_script(tmp_path):
    """Entrypoint node must have a distinct ID from a function also named 'script'.

    _make_id strips leading/trailing '_.' from each part, so
    _make_id(stem, "__script__") strips to _make_id(stem, "script"), which is
    identical to _make_id(stem, "script") for a function named 'script'.
    """
    script = tmp_path / "deploy.sh"
    script.write_text("#!/usr/bin/env bash\nfunction script() { echo hi; }\n")
    result = extract_bash(script)
    entry_nodes = [n for n in result["nodes"] if n.get("metadata", {}).get("kind") == "bash_entrypoint"]
    func_nodes = [n for n in result["nodes"] if n.get("metadata", {}).get("kind") == "bash_function"]
    assert entry_nodes, "Must have a bash_entrypoint node"
    assert func_nodes, "Must have a bash_function node for 'script'"
    entry_id = entry_nodes[0]["id"]
    func_id = func_nodes[0]["id"]
    assert entry_id != func_id, (
        f"Entrypoint ID must not collide with function 'script' ID; both are '{entry_id}'"
    )


def test_extract_bash_nested_function_calls_recorded(tmp_path):
    """Calls made inside a nested (inner) function body must be collected."""
    script = tmp_path / "nested.sh"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "function do_work() { :; }\n"
        "function outer() {\n"
        "    function inner() {\n"
        "        do_work\n"
        "    }\n"
        "    inner\n"
        "}\n"
    )
    result = extract_bash(script)
    node_id_by_label = {n["label"].rstrip("()"): n["id"] for n in result["nodes"]}
    assert "inner" in node_id_by_label, f"inner function must be discovered; labels={list(node_id_by_label)}"
    assert "do_work" in node_id_by_label, f"do_work function must be discovered; labels={list(node_id_by_label)}"
    calls = {(e["source"], e["target"]) for e in result["edges"] if e.get("relation") == "calls"}
    inner_id = node_id_by_label["inner"]
    do_work_id = node_id_by_label["do_work"]
    assert (inner_id, do_work_id) in calls, (
        f"inner→do_work call edge must be recorded; got calls={calls}"
    )


def test_extract_bash_source_user_defined_emits_calls_not_imports_from(tmp_path):
    """When 'source' is a user-defined function, 'source ./file.sh' must emit a
    calls edge, not an imports_from edge.  The user-defined function shadows the
    built-in source command."""
    helpers = tmp_path / "helpers.sh"
    helpers.write_text("#!/bin/bash\n")
    script = tmp_path / "run.sh"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "function source() { echo 'custom source'; }\n"
        "source ./helpers.sh\n"
    )
    result = extract_bash(script)
    import_edges = [e for e in result["edges"] if e.get("relation") == "imports_from"]
    assert not import_edges, (
        f"'source' is a user-defined function; 'source ./helpers.sh' must not emit imports_from; got: {import_edges}"
    )


def test_extract_bash_emits_raw_calls_and_bash_sources_for_sourced_calls(tmp_path):
    """extract_bash must surface the data cross-file resolution needs: a
    ``bash_sources`` entry per sourced file and a ``raw_calls`` entry for each
    call whose callee is not defined in the same file. Without these,
    resolve_bash_source_edges has nothing to resolve a sourced-function call
    from (#2141)."""
    (tmp_path / "b.sh").write_text("#!/usr/bin/env bash\nb_func() { echo ok; }\n")
    a = tmp_path / "a.sh"
    a.write_text(
        "#!/usr/bin/env bash\n"
        "source ./b.sh\n"
        "main() { b_func; }\n"
    )
    result = extract_bash(a)

    sources = result.get("bash_sources", [])
    assert any(str(s.get("target_path", "")).endswith("b.sh") for s in sources), sources

    main_nid = next(n["id"] for n in result["nodes"] if n.get("label") == "main()")
    raw_calls = result.get("raw_calls", [])
    assert any(
        rc.get("language") == "bash"
        and rc.get("callee") == "b_func"
        and rc.get("caller_nid") == main_nid
        for rc in raw_calls
    ), raw_calls


def test_extract_bash_call_to_sourced_function_resolves(tmp_path):
    """#2141 repro: a call to a function defined in a sourced file must produce a
    real ``calls`` edge through the full extract() pipeline, so ``path`` and
    ``callers`` can traverse it."""
    (tmp_path / "b.sh").write_text("#!/usr/bin/env bash\nb_func() { echo ok; }\n")
    (tmp_path / "a.sh").write_text(
        "#!/usr/bin/env bash\n"
        "source ./b.sh\n"
        "main() { b_func; }\n"
    )
    result = extract([tmp_path / "a.sh", tmp_path / "b.sh"], cache_root=tmp_path)
    calls = {(e["source"], e["target"]) for e in result["edges"] if e["relation"] == "calls"}
    assert ("a_main", "b_b_func") in calls, sorted(calls)


def test_extract_bash_sourced_call_does_not_duplicate_source_edge(tmp_path):
    """Wiring the source-backed call resolver must not re-emit the ``imports_from``
    source edge the extractor already resolved for ``source ./b.sh`` (#2141)."""
    (tmp_path / "b.sh").write_text("#!/usr/bin/env bash\nb_func() { echo ok; }\n")
    (tmp_path / "a.sh").write_text(
        "#!/usr/bin/env bash\n"
        "source ./b.sh\n"
        "main() { b_func; }\n"
    )
    result = extract([tmp_path / "a.sh", tmp_path / "b.sh"], cache_root=tmp_path)
    imports = [(e["source"], e["target"]) for e in result["edges"]
               if e["relation"] == "imports_from"]
    assert imports.count(("a", "b")) == 1, imports


def test_extract_bash_call_to_external_command_stays_unlinked(tmp_path):
    """A call to a command that is not a function in any sourced file (an external
    binary) must not gain a cross-file ``calls`` edge — even when a same-named
    function exists in an *unsourced* file. Source-scoped resolution is what keeps
    #2141 from over-connecting the graph (acceptance criterion)."""
    # b.sh is NOT sourced by a.sh, yet defines a function named `deploy`.
    (tmp_path / "b.sh").write_text("#!/usr/bin/env bash\ndeploy() { echo ok; }\n")
    (tmp_path / "a.sh").write_text(
        "#!/usr/bin/env bash\n"
        "main() { deploy; }\n"
    )
    result = extract([tmp_path / "a.sh", tmp_path / "b.sh"], cache_root=tmp_path)
    calls = {(e["source"], e["target"]) for e in result["edges"] if e["relation"] == "calls"}
    assert ("a_main", "b_deploy") not in calls, sorted(calls)


def test_extract_bash_call_into_extensionless_sourced_lib_resolves(tmp_path):
    """#2171: a sourced lib with a bash shebang but no extension must resolve.

    _SHEBANG_DISPATCH already routes an extensionless `#!/usr/bin/env bash` file to
    extract_bash, so its functions are indexed, but the cross-file source pass
    selected participants by filename suffix only — so the lib was left out and
    calls into it never bound.
    """
    lib = tmp_path / "mylib"
    lib.write_text("#!/usr/bin/env bash\nlib_helper() { echo ok; }\n", encoding="utf-8")
    (tmp_path / "a.sh").write_text(
        "#!/usr/bin/env bash\n"
        "source ./mylib\n"
        "main() { lib_helper; }\n",
        encoding="utf-8",
    )
    result = extract([tmp_path / "a.sh", lib], cache_root=tmp_path)
    calls = {(e["source"], e["target"]) for e in result["edges"] if e["relation"] == "calls"}
    assert ("a_main", "mylib_lib_helper") in calls, sorted(calls)


def test_extract_bash_bare_source_name_resolves_to_sibling(tmp_path):
    """#2171: `source lib.sh` with no ./ prefix must bind to the sibling file.

    Only the ``./``/``/``-prefixed branch recorded bash_sources; a bare name fell
    through to the opaque ``imports`` fallback, so neither the source edge nor
    calls into the lib resolved even though the file sits next to the script.
    """
    (tmp_path / "lib.sh").write_text(
        "#!/usr/bin/env bash\nbare_helper() { echo ok; }\n", encoding="utf-8"
    )
    (tmp_path / "a.sh").write_text(
        "#!/usr/bin/env bash\n"
        "source lib.sh\n"
        "main() { bare_helper; }\n",
        encoding="utf-8",
    )
    result = extract([tmp_path / "a.sh", tmp_path / "lib.sh"], cache_root=tmp_path)
    imports = [(e["source"], e["target"]) for e in result["edges"]
               if e["relation"] == "imports_from"]
    assert ("a", "lib") in imports, imports
    calls = {(e["source"], e["target"]) for e in result["edges"] if e["relation"] == "calls"}
    assert ("a_main", "lib_bare_helper") in calls, sorted(calls)


def test_extract_bash_bare_source_missing_file_fabricates_nothing(tmp_path):
    """The #2171 bare-name branch keeps the existence gate: a name that resolves to
    no sibling must not produce an imports_from edge or a bash_sources entry."""
    script = tmp_path / "a.sh"
    script.write_text("#!/usr/bin/env bash\nsource nope.sh\n", encoding="utf-8")
    result = extract_bash(script)
    assert result["bash_sources"] == [], result["bash_sources"]
    imports_from = [e for e in result["edges"] if e["relation"] == "imports_from"]
    assert imports_from == [], imports_from


def test_bash_var_sourced_function_call_resolves(tmp_path):
    """End-to-end integration of #2079 + #2141 (#2157/#2139): a library sourced
    via the canonical ``${VAR}`` idiom must feed ``bash_sources`` so that
    resolve_bash_source_edges binds calls into its functions — not just the
    imports_from source edge. Before the extractor appended the resolved path to
    ``bash_sources`` in the ``${VAR}`` branch, main() -> util_fn() produced no
    calls edge at all."""
    # realpath: tempfile on macOS hands out /var/... which symlinks to
    # /private/var/...; the extractor stores the *resolved* target path, so the
    # scan root must be the resolved form too or ids anchor inconsistently.
    root = Path(os.path.realpath(tmp_path))
    lib = root / "lib"
    lib.mkdir()
    (lib / "util.sh").write_text(
        "#!/usr/bin/env bash\nutil_fn() { :; }\n", encoding="utf-8"
    )
    (root / "bench.sh").write_text(
        '#!/usr/bin/env bash\n'
        'BENCH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
        'source "${BENCH_DIR}/lib/util.sh"\n'
        "main() { util_fn; }\n",
        encoding="utf-8",
    )
    result = extract(
        [root / "bench.sh", lib / "util.sh"], cache_root=root, root=root
    )

    main_id = next(
        n["id"] for n in result["nodes"]
        if n["label"] == "main()" and n["source_file"].endswith("bench.sh")
    )
    util_id = next(
        n["id"] for n in result["nodes"]
        if n["label"] == "util_fn()" and n["source_file"].endswith("util.sh")
    )
    sourced_calls = [
        e for e in result["edges"]
        if e["relation"] == "calls"
        and e["source"] == main_id and e["target"] == util_id
    ]
    assert len(sourced_calls) == 1, (
        f"expected exactly one calls edge {main_id} -> {util_id}; got: "
        f"{sorted((e['source'], e['target']) for e in result['edges'] if e['relation'] == 'calls')}"
    )
    # The source edge itself must still be there alongside the call binding.
    imports = {(e["source"], e["target"]) for e in result["edges"]
               if e["relation"] == "imports_from"}
    assert ("bench", "lib_util") in imports, sorted(imports)


def test_extract_bash_source_suffix_guard_mid_path_variable(tmp_path):
    """`source "lib/${X}.sh"` keeps an expansion in the suffix, so the
    ``$``-in-suffix guard of _bash_source_suffix must reject it: no
    imports/imports_from edge and no bash_sources entry may be fabricated."""
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "extras.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    script = tmp_path / "run.sh"
    script.write_text(
        '#!/usr/bin/env bash\nsource "lib/${X}.sh"\n', encoding="utf-8"
    )
    result = extract_bash(script)
    fabricated = [e for e in result["edges"]
                  if e["relation"] in ("imports", "imports_from")]
    assert fabricated == [], fabricated
    assert result["bash_sources"] == [], result["bash_sources"]


def test_extract_bash_source_suffix_guard_whole_variable_path(tmp_path):
    """`source "$CONFIG_FILE"` strips to an empty suffix — nothing literal is
    left to resolve, so no edge and no bash_sources entry may be emitted."""
    (tmp_path / "config.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    script = tmp_path / "run.sh"
    script.write_text(
        '#!/usr/bin/env bash\nsource "$CONFIG_FILE"\n', encoding="utf-8"
    )
    result = extract_bash(script)
    fabricated = [e for e in result["edges"]
                  if e["relation"] in ("imports", "imports_from")]
    assert fabricated == [], fabricated
    assert result["bash_sources"] == [], result["bash_sources"]


def test_extract_bash_source_suffix_guard_rejects_traversal(tmp_path):
    """`source "${D}/../secret.sh"` must hit the ``..`` guard. The target file
    exists one level up, so without the guard the suffix WOULD resolve and
    fabricate both the edge and the bash_sources entry."""
    (tmp_path / "secret.sh").write_text(
        "#!/usr/bin/env bash\nleak() { :; }\n", encoding="utf-8"
    )
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    script = scripts / "run.sh"
    script.write_text(
        '#!/usr/bin/env bash\nsource "${D}/../secret.sh"\n', encoding="utf-8"
    )
    result = extract_bash(script)
    fabricated = [e for e in result["edges"]
                  if e["relation"] in ("imports", "imports_from")]
    assert fabricated == [], fabricated
    assert result["bash_sources"] == [], result["bash_sources"]


def test_extract_bash_var_source_uses_tracked_assignment_base(tmp_path):
    """#2172: `${VAR}` must resolve against the variable's tracked base.

    #2079 always resolved the literal suffix against the script's own directory.
    That is right for `DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"`, but
    when the variable points elsewhere -- here ROOT is the script dir's parent --
    and a same-named decoy exists under the script dir, the edge bound to the
    decoy: a wrong edge to a real node.
    """
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "utils.sh").write_text(
        "#!/usr/bin/env bash\nreal_util() { echo real; }\n", encoding="utf-8"
    )
    scripts = tmp_path / "scripts"
    (scripts / "lib").mkdir(parents=True)
    decoy = scripts / "lib" / "utils.sh"
    decoy.write_text(
        "#!/usr/bin/env bash\ndecoy_util() { echo decoy; }\n", encoding="utf-8"
    )
    script = scripts / "deploy.sh"
    script.write_text(
        '#!/usr/bin/env bash\n'
        'ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"\n'
        'source "${ROOT}/lib/utils.sh"\n',
        encoding="utf-8",
    )
    result = extract_bash(script)
    targets = [str(s["target_path"]) for s in result["bash_sources"]]
    assert targets, "the ${VAR} source must still resolve"
    for t in targets:
        assert Path(t).resolve() == (tmp_path / "lib" / "utils.sh").resolve(), t
        assert Path(t).resolve() != decoy.resolve(), f"bound to the decoy: {t}"


def test_extract_bash_var_source_script_dir_idiom_still_resolves(tmp_path):
    """The canonical script-dir idiom must keep working (#2079 regression guard)."""
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "x.sh").write_text(
        "#!/usr/bin/env bash\nx_fn() { :; }\n", encoding="utf-8"
    )
    script = tmp_path / "bench.sh"
    script.write_text(
        '#!/usr/bin/env bash\n'
        'BENCH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
        'source "${BENCH_DIR}/lib/x.sh"\n',
        encoding="utf-8",
    )
    result = extract_bash(script)
    targets = [Path(s["target_path"]).resolve() for s in result["bash_sources"]]
    assert (tmp_path / "lib" / "x.sh").resolve() in targets, targets


def test_extract_bash_var_source_untracked_var_keeps_script_dir_guess(tmp_path):
    """An untracked variable (assigned from the environment, or not assigned in
    this file at all) keeps the #2079 script-dir guess rather than binding
    nowhere -- the fallback must survive the #2172 change."""
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "y.sh").write_text("#!/usr/bin/env bash\ny_fn() { :; }\n", encoding="utf-8")
    script = tmp_path / "run.sh"
    script.write_text(
        '#!/usr/bin/env bash\nsource "${SOME_EXTERNAL_DIR}/lib/y.sh"\n',
        encoding="utf-8",
    )
    result = extract_bash(script)
    targets = [Path(s["target_path"]).resolve() for s in result["bash_sources"]]
    assert (lib / "y.sh").resolve() in targets, targets


def test_extract_bash_source_dirname_cmdsubst_in_argument(tmp_path):
    """Form 3 (#2596): `source "$(dirname "$VAR")/lib/y.sh"` — command
    substitution in the source argument.  The dirname idiom on the *source*
    line should resolve the same way it does on an assignment line: treat
    `$(dirname "$VAR")` as `var_bases[VAR].parent` (or `script_dir.parent`
    when VAR is untracked), then resolve the literal suffix against it.
    """
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "y.sh").write_text(
        "#!/usr/bin/env bash\ny_fn() { :; }\n", encoding="utf-8"
    )
    script = tmp_path / "bin" / "x.sh"
    script.parent.mkdir(parents=True)
    # SCRIPT_DIR is tracked by the existing idiom, so dirname("$SCRIPT_DIR")
    # should resolve to tmp_path, and tmp_path/lib/y.sh is the target.
    script.write_text(
        '#!/usr/bin/env bash\n'
        'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
        'source "$(dirname "$SCRIPT_DIR")/lib/y.sh"\n',
        encoding="utf-8",
    )
    result = extract_bash(script)
    targets = [Path(s["target_path"]).resolve() for s in result["bash_sources"]]
    assert (tmp_path / "lib" / "y.sh").resolve() in targets, targets


def test_extract_bash_source_dirname_cmdsubst_untracked_var(tmp_path):
    """Form 3 with an untracked variable: `source "$(dirname "$SCRIPT_DIR")/lib/y.sh"`
    where SCRIPT_DIR is NOT assigned via the recognised idiom.  The fallback
    is the script's own directory (same as the existing untracked-var path),
    so dirname of the script dir is the parent.
    """
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "y.sh").write_text(
        "#!/usr/bin/env bash\ny_fn() { :; }\n", encoding="utf-8"
    )
    script = tmp_path / "bin" / "x.sh"
    script.parent.mkdir(parents=True)
    # No SCRIPT_DIR assignment — the var is untracked, so the extractor
    # falls back to script_dir.parent (= tmp_path) for dirname.
    script.write_text(
        '#!/usr/bin/env bash\n'
        'source "$(dirname "$SCRIPT_DIR")/lib/y.sh"\n',
        encoding="utf-8",
    )
    result = extract_bash(script)
    targets = [Path(s["target_path"]).resolve() for s in result["bash_sources"]]
    assert (tmp_path / "lib" / "y.sh").resolve() in targets, targets


def test_extract_bash_source_dotdot_suffix_with_tracked_var(tmp_path):
    """Form 4 (#2596): `source "$VAR/../lib/y.sh"` — `..` in the literal
    suffix.  When the base comes from a tracked var_bases entry, `..` is
    safe (it's a known directory, not a guess), so resolve via normpath
    and the existing is_file() gate.  The `..` rejection should only apply
    on the script-dir-guess path where the base is uncertain.
    """
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "y.sh").write_text(
        "#!/usr/bin/env bash\ny_fn() { :; }\n", encoding="utf-8"
    )
    script = tmp_path / "bin" / "x.sh"
    script.parent.mkdir(parents=True)
    # SCRIPT_DIR is tracked (= bin/), so $SCRIPT_DIR/../lib/y.sh resolves
    # to tmp_path/lib/y.sh.
    script.write_text(
        '#!/usr/bin/env bash\n'
        'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
        'source "$SCRIPT_DIR/../lib/y.sh"\n',
        encoding="utf-8",
    )
    result = extract_bash(script)
    targets = [Path(s["target_path"]).resolve() for s in result["bash_sources"]]
    assert (tmp_path / "lib" / "y.sh").resolve() in targets, targets


def test_extract_bash_source_dotdot_suffix_script_dir_guess_still_rejected(tmp_path):
    """Form 4 guard: `..` in the suffix must still be rejected when the base
    is the script-dir *guess* (no tracked variable).  Otherwise a path like
    `source "${UNTRACKED}/../../etc/passwd"` could traverse outside the tree.
    """
    script = tmp_path / "run.sh"
    script.write_text(
        '#!/usr/bin/env bash\n'
        'source "${UNTRACKED}/../evil.sh"\n',
        encoding="utf-8",
    )
    result = extract_bash(script)
    targets = [Path(s["target_path"]).resolve() for s in result["bash_sources"]]
    assert not targets, f"untracked var with .. should not resolve: {targets}"


def test_extract_bash_source_dirname_cmdsubst_rejects_traversal(tmp_path):
    """Form 3 hardening (#2596): the `$(dirname …)` base is a guessed directory,
    so a `..` suffix must be rejected before the target is probed or recorded —
    otherwise `source "$(dirname "$VAR")/../../../../etc/passwd"` resolves to an
    arbitrary host path and leaks it as a source edge on an attacker-controlled
    corpus."""
    outside = tmp_path / "secret.sh"
    outside.write_text("echo secret\n", encoding="utf-8")  # a real file to escape to
    script = tmp_path / "proj" / "bin" / "x.sh"
    script.parent.mkdir(parents=True)
    script.write_text(
        '#!/usr/bin/env bash\n'
        'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
        'source "$(dirname "$SCRIPT_DIR")/../../secret.sh"\n',
        encoding="utf-8",
    )
    result = extract_bash(script)
    assert not result["bash_sources"], result["bash_sources"]
    leaked = [e.get("target_file") for e in result["edges"]
              if e.get("relation") == "imports_from" and "secret.sh" in (e.get("target_file") or "")]
    assert not leaked, f"traversal target leaked as an edge: {leaked}"


def test_extract_bash_source_dotdot_tracked_var_cannot_escape_to_root(tmp_path):
    """Form 4 hardening (#2596): a tracked base legitimately reaches a sibling via
    `$VAR/../lib`, but a multi-level `..` that walks past the base's parent to an
    arbitrary host path must be dropped, not probed and recorded."""
    outside = tmp_path / "secret.sh"
    outside.write_text("echo secret\n", encoding="utf-8")
    # bin is two levels below tmp_path, so ../../.. escapes past base.parent.
    script = tmp_path / "proj" / "bin" / "x.sh"
    script.parent.mkdir(parents=True)
    script.write_text(
        '#!/usr/bin/env bash\n'
        'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
        'source "$SCRIPT_DIR/../../../secret.sh"\n',
        encoding="utf-8",
    )
    result = extract_bash(script)
    assert not result["bash_sources"], result["bash_sources"]
    leaked = [e.get("target_file") for e in result["edges"]
              if e.get("relation") == "imports_from" and "secret.sh" in (e.get("target_file") or "")]
    assert not leaked, f"traversal target leaked as an edge: {leaked}"


# ---------------------------------------------------------------------------
# JSON extractor tests (#866)
# ---------------------------------------------------------------------------

def test_extract_json_top_level_keys():
    result = extract_json(FIXTURES / "sample.json")
    assert "error" not in result
    labels = {n["label"] for n in result["nodes"]}
    assert "name" in labels
    assert "version" in labels
    assert "scripts" in labels
    assert "dependencies" in labels


def test_extract_json_nested_contains():
    result = extract_json(FIXTURES / "sample.json")
    contains = [(e["source"], e["target"]) for e in result["edges"] if e["relation"] == "contains"]
    assert any("scripts" in s and "build" in t for s, t in contains)
    assert any("scripts" in s and "test" in t for s, t in contains)
    assert any("dependencies" in s and "react" in t for s, t in contains)


def test_extract_json_dependencies_become_imports():
    result = extract_json(FIXTURES / "sample.json")
    import_edges = [e for e in result["edges"] if e["relation"] == "imports"]
    targets = {e["target"] for e in import_edges}
    assert any("react" in t for t in targets)
    assert any("axios" in t for t in targets)
    assert any("typescript" in t for t in targets)


def test_extract_json_extends_resolved():
    result = extract_json(FIXTURES / "sample_tsconfig.json")
    extends_edges = [e for e in result["edges"] if e["relation"] == "extends"]
    assert len(extends_edges) >= 1
    assert extends_edges[0].get("context") == "import"


def test_extract_json_dependency_edges_are_not_label_self_loops(tmp_path):
    """A dependency must not point at another node carrying its own label.

    test_extract_json_import_and_extends_targets_are_real_nodes already forbids
    self-loops, but it compares node *ids*. The dependency branch minted a
    second node for the same name under a different id, so every dependency
    rendered as ``react --imports--> react`` -- a self-loop by label that an
    id-based guard cannot see.
    """
    package_json = tmp_path / "package.json"
    package_json.write_text(json.dumps({
        "name": "demo",
        "dependencies": {"react": "^19.0.0", "next": "^15.0.0"},
        "devDependencies": {"wrangler": "^4.71.0"},
    }))

    result = extract_json(package_json)
    labels = {n["id"]: n["label"] for n in result["nodes"]}
    offenders = [
        (labels.get(e["source"]), e["relation"], labels.get(e["target"]))
        for e in result["edges"]
        if e["relation"] == "imports"
        and labels.get(e["source"]) == labels.get(e["target"])
    ]
    assert offenders == [], f"label self-loop: {offenders}"

    # The dependency structure #1764 restored is still present.
    imports = [e for e in result["edges"] if e["relation"] == "imports"]
    assert {labels.get(e["target"]) for e in imports} == {"react", "next", "wrangler"}

    # External dependency ids stay "ref"-namespaced (J-4), so build.py's alias
    # index cannot collapse a dep named `utils`/`colors` onto a local module.
    assert all(e["target"].startswith("ref") for e in imports), [e["target"] for e in imports]


def test_extract_json_non_extends_arrays_are_not_inheritance(tmp_path):
    """Only an ``extends`` array is inheritance.

    ``compilerOptions.lib`` and ``exclude`` are ordinary string lists; emitting
    ``extends`` for them turns array membership into a supertype relation and
    manufactures a hub out of a build-output glob.
    """
    tsconfig = tmp_path / "tsconfig.json"
    tsconfig.write_text(json.dumps({
        "extends": ["./base.json", "./strict.json"],
        "compilerOptions": {"lib": ["dom", "esnext"]},
        "exclude": ["node_modules", ".next"],
    }))

    result = extract_json(tsconfig)
    labels = {n["id"]: n["label"] for n in result["nodes"]}
    extends_targets = {
        labels.get(e["target"]) for e in result["edges"] if e["relation"] == "extends"
    }
    assert extends_targets == {"./base.json", "./strict.json"}
    for not_inheritance in ("dom", "esnext", ".next", "node_modules"):
        assert not_inheritance not in extends_targets


def test_extract_json_import_and_extends_targets_are_real_nodes(tmp_path):
    package_json = tmp_path / "package.json"
    package_json.write_text(json.dumps({
        "name": "demo",
        "dependencies": {"left-pad": "^1.3.0"},
        "devDependencies": {"bats": "^1.11.0"},
    }))
    tsconfig = tmp_path / "tsconfig.json"
    tsconfig.write_text(json.dumps({
        "extends": "./tsconfig.base.json",
        "compilerOptions": {"strict": True},
    }))

    results = [extract_json(package_json), extract_json(tsconfig)]
    combined = {
        "nodes": [node for result in results for node in result["nodes"]],
        "edges": [edge for result in results for edge in result["edges"]],
    }
    node_ids = {node["id"] for node in combined["nodes"]}
    dangling = [
        edge for edge in combined["edges"]
        if edge["source"] not in node_ids or edge["target"] not in node_ids
    ]
    assert dangling == []
    assert {"left-pad", "bats", "./tsconfig.base.json"} <= {
        node["label"] for node in combined["nodes"] if node["file_type"] == "concept"
    }

    extracted = extract([package_json, tsconfig], cache_root=tmp_path, parallel=False)
    graph = build_from_json(extracted, directed=True)
    import_targets = {
        graph.nodes[data["_tgt"]]["label"]
        for _, _, data in graph.edges(data=True)
        if data.get("relation") == "imports"
    }
    extends_targets = {
        graph.nodes[data["_tgt"]]["label"]
        for _, _, data in graph.edges(data=True)
        if data.get("relation") == "extends"
    }
    self_loops = [
        data for _, _, data in graph.edges(data=True)
        if data.get("relation") in {"imports", "extends"} and data["_src"] == data["_tgt"]
    ]
    assert self_loops == []
    assert {"left-pad", "bats"} <= import_targets
    assert extends_targets == {"./tsconfig.base.json"}


def test_extract_json_large_file_skipped(tmp_path):
    big = tmp_path / "big.json"
    # Write a JSON file just over 1 MiB
    big.write_bytes(b'{"x": "' + b"a" * (1_048_576) + b'"}')
    result = extract_json(big)
    assert "error" in result
    assert result["nodes"] == []


def test_extract_json_handles_invalid_json(tmp_path):
    bad = tmp_path / "broken.json"
    bad.write_text("{this is not: valid json!!!")
    result = extract_json(bad)
    # Should not crash — returns empty or error result
    assert isinstance(result, dict)
    assert "nodes" in result


def test_extract_json_no_self_loops():
    result = extract_json(FIXTURES / "sample.json")
    for e in result["edges"]:
        assert e["source"] != e["target"], f"Self-loop: {e}"


# ---------------------------------------------------------------------------
# Data JSON must not explode into orphan key-nodes (#1224)
# ---------------------------------------------------------------------------

def test_extract_json_data_file_skipped(tmp_path):
    """A data-shaped .json (eval fixture / dataset) must NOT emit per-key nodes."""
    data = tmp_path / "cases.json"
    data.write_text(json.dumps({
        "generation": {"target": "gpt-4", "cases_file": "c.json", "num_cases": 12},
        "prompt_inputs_spec": {"a": 1, "b": 2},
        "suite": [{"name": "x"}, {"name": "y"}],
    }))
    result = extract_json(data)
    assert result["nodes"] == []
    assert result["edges"] == []
    assert "skipped" in result


def test_extract_json_top_level_array_skipped(tmp_path):
    """A JSON file whose root is an array is data, never a config/manifest."""
    data = tmp_path / "records.json"
    data.write_text(json.dumps([{"id": 1}, {"id": 2}]))
    result = extract_json(data)
    assert result["nodes"] == []
    assert result["edges"] == []


def test_extract_json_config_by_filename_still_extracted(tmp_path):
    """tsconfig.json must still be AST-extracted even without telltale keys."""
    cfg = tmp_path / "tsconfig.json"
    cfg.write_text(json.dumps({"compilerOptions": {"strict": True}}))
    result = extract_json(cfg)
    assert len(result["nodes"]) > 0
    assert "skipped" not in result


def test_extract_json_config_by_key_probe(tmp_path):
    """An arbitrarily-named JSON with config keys (dependencies) is still extracted."""
    cfg = tmp_path / "weird-name.json"
    cfg.write_text(json.dumps({"dependencies": {"lodash": "^4"}}))
    result = extract_json(cfg)
    import_edges = [e for e in result["edges"] if e["relation"] == "imports"]
    assert any("lodash" in e["target"] for e in import_edges)
    assert "skipped" not in result


def test_extract_bash_via_dispatch():
    from graphify.extract import _get_extractor
    assert _get_extractor(Path("foo.sh")) is extract_bash
    assert _get_extractor(Path("foo.bash")) is extract_bash


def test_extract_json_via_dispatch():
    from graphify.extract import _get_extractor
    assert _get_extractor(Path("foo.json")) is extract_json


def test_extensionless_shebang_via_dispatch(tmp_path):
    """Extensionless CLIs resolve their extractor from the shebang, mirroring
    detect.classify_file — otherwise detect labels them code and extraction
    silently drops them."""
    from graphify.extract import _get_extractor

    cli = tmp_path / "devctl"
    cli.write_text("#!/usr/bin/env bash\necho hi\n")
    assert _get_extractor(cli) is extract_bash

    pytool = tmp_path / "manage"
    pytool.write_text("#!/usr/bin/env python3\nprint('hi')\n")
    assert _get_extractor(pytool) is extract_python

    # env -S split-args form is handled by the shared shebang parser
    split = tmp_path / "runner"
    split.write_text("#!/usr/bin/env -S bash -eu\necho hi\n")
    assert _get_extractor(split) is extract_bash


def test_extensionless_without_usable_shebang_stays_unsupported(tmp_path):
    from graphify.extract import _get_extractor

    plain = tmp_path / "LICENSE-COPY"
    plain.write_text("plain text, no shebang\n")
    assert _get_extractor(plain) is None

    # Interpreter known to detect but with no AST extractor: stays skipped
    # rather than being mis-parsed by a wrong grammar.
    perl = tmp_path / "legacy"
    perl.write_text("#!/usr/bin/env perl\nprint 1;\n")
    assert _get_extractor(perl) is None


def test_extract_extensionless_bash_cli_end_to_end(tmp_path):
    """A shebang-only bash CLI must contribute nodes with the same ID scheme
    as a .sh file (path stem + entity), so doc-created stub IDs merge."""
    cli = tmp_path / "devctl"
    cli.write_text(
        "#!/usr/bin/env bash\n"
        "helper() { echo hi; }\n"
        "main() { helper; }\n"
        'main "$@"\n'
    )
    result = extract([cli], cache_root=tmp_path)
    ids = {n["id"] for n in result["nodes"]}
    assert "devctl_helper" in ids
    assert "devctl_main" in ids


def test_extract_bash_node_metadata_is_sanitized():
    """Bash extractor must route node metadata through sanitize_metadata so
    HTML-sensitive characters cannot reach downstream graph viewers raw."""
    result = extract_bash(FIXTURES / "sample.sh")
    assert "error" not in result
    for node in result["nodes"]:
        meta = node.get("metadata", {})
        # Static bash metadata is currently {"language": "bash", "kind": "code"};
        # both pass through sanitisation unchanged, but the values must be the
        # post-sanitisation strings (not raw objects).
        for value in meta.values():
            if isinstance(value, str):
                assert "<" not in value
                assert "\x00" not in value


# ── Barrel re-export tests ────────────────────────────────────────────────────


def test_barrel_reexport_emits_re_exports_edges():
    """export { X } from './mod' must emit re_exports edges for each named specifier."""
    from graphify.extract import extract_js
    result = extract_js(FIXTURES / "barrel_reexport.ts")
    reexports = [e for e in result["edges"] if e["relation"] == "re_exports"]
    targets = [e["target"] for e in reexports]
    # Should find re_exports for readCookie, writeCookie, getFullUrl, basePathRewrite
    assert len(reexports) >= 4, f"Expected >=4 re_exports, got {len(reexports)}: {targets}"
    assert any("readcookie" in t for t in targets)
    assert any("writecookie" in t for t in targets)
    assert any("getfullurl" in t for t in targets)
    assert any("basepathrewrite" in t for t in targets)


def test_barrel_reexport_emits_imports_from():
    """Barrel file must emit file-level imports_from edges to source modules."""
    from graphify.extract import extract_js
    result = extract_js(FIXTURES / "barrel_reexport.ts")
    imports_from = [e for e in result["edges"] if e["relation"] == "imports_from"]
    targets = [e["target"] for e in imports_from]
    assert any("cookiehelpers" in t for t in targets)
    assert any("urlhelpers" in t for t in targets)
    assert any("storagehelpers" in t for t in targets)


def test_barrel_reexport_context_tagged():
    """re_exports edges should have context='re-export'."""
    from graphify.extract import extract_js
    result = extract_js(FIXTURES / "barrel_reexport.ts")
    reexports = [e for e in result["edges"] if e["relation"] == "re_exports"]
    for e in reexports:
        assert e.get("context") == "re-export"


def test_barrel_local_exports_still_extracted():
    """export function/const in a barrel file must still create nodes."""
    from graphify.extract import extract_js
    result = extract_js(FIXTURES / "barrel_reexport.ts")
    labels = [n["label"] for n in result["nodes"]]
    assert "localHelper()" in labels or "localHelper" in labels
    # File node should also exist
    assert any("barrel_reexport" in n["label"] for n in result["nodes"])


def test_barrel_reexport_confidence_extracted():
    """All re_exports edges should have confidence=EXTRACTED."""
    from graphify.extract import extract_js
    result = extract_js(FIXTURES / "barrel_reexport.ts")
    reexports = [e for e in result["edges"] if e["relation"] == "re_exports"]
    for e in reexports:
        assert e["confidence"] == "EXTRACTED"


def test_semantic_reference_edges_carry_context_and_source():
    from graphify.extract import _semantic_reference_edge

    edge = _semantic_reference_edge(
        "source_node",
        "target_node",
        "parameter_type",
        "/repo/src/Foo.cs",
        12,
    )

    assert edge == {
        "source": "source_node",
        "target": "target_node",
        "relation": "references",
        "context": "parameter_type",
        "confidence": "EXTRACTED",
        "source_file": "/repo/src/Foo.cs",
        "source_location": "L12",
        "weight": 1.0,
    }


def test_pure_export_no_from_not_treated_as_reexport():
    """export { localVar } without 'from' should NOT create re_exports edges."""
    from graphify.extract import extract_js
    import tempfile
    code = b"const x = 1;\nexport { x };\n"
    with tempfile.NamedTemporaryFile(suffix=".ts", delete=False) as f:
        f.write(code)
        f.flush()
        result = extract_js(Path(f.name))
    reexports = [e for e in result["edges"] if e["relation"] == "re_exports"]
    assert reexports == [], f"Pure export should not create re_exports: {reexports}"


def test_dart_child_node_ids_are_stem_based(tmp_path):
    """Dart child node IDs must be built from _file_stem rather than absolute path."""
    from graphify.extract import extract_dart, _file_stem, _make_id

    src_file = tmp_path / "mydir" / "sample.dart"
    src_file.parent.mkdir(parents=True, exist_ok=True)
    src_file.write_bytes(b"class MyClass {}\nvoid myFunc() {}\n")

    result = extract_dart(src_file)

    stem = _file_stem(src_file)  # -> full-path form, e.g. ".../mydir/sample"
    expected_class_nid = _make_id(stem, "MyClass")   # -> ..._mydir_sample_myclass
    expected_func_nid  = _make_id(stem, "myFunc")    # -> ..._mydir_sample_myfunc

    node_ids = {n["id"] for n in result["nodes"]}

    assert expected_class_nid in node_ids, (
        f"Class node ID '{expected_class_nid}' not found in {node_ids}. "
        "extract_dart may still be using str(path) instead of _file_stem(path)."
    )
    assert expected_func_nid in node_ids, (
        f"Function node ID '{expected_func_nid}' not found in {node_ids}. "
        "extract_dart may still be using str(path) instead of _file_stem(path)."
    )

    # Sanity-check: no child node ID should contain a raw path separator; every
    # child must share the normalized file-stem prefix (slashes collapsed to _).
    file_nid = next(n["id"] for n in result["nodes"] if n.get("label") == src_file.name)
    norm_stem = _make_id(stem)
    for node in result["nodes"]:
        if node["id"] == file_nid:
            continue
        assert "/" not in node["id"]
        assert node["id"].startswith(norm_stem), (
            f"Child node ID '{node['id']}' does not start with the expected stem prefix '{norm_stem}'. "
            "This suggests an absolute path is still leaking into the ID."
        )




def test_separator_collision_paths_get_distinct_ids(tmp_path):
    """#1522: two distinct paths whose only difference is a separator-vs-punctuation
    swap (foo/bar_baz.py vs foo_bar/baz.py) normalize to the same stem; the
    disambiguation pass now salts the colliders with a stable path hash so they
    stay distinct instead of silently merging."""
    a = tmp_path / "foo/bar_baz.py"
    b = tmp_path / "foo_bar/baz.py"
    a.parent.mkdir(parents=True)
    b.parent.mkdir(parents=True)
    a.write_text("class Widget:\n    pass\n")
    b.write_text("class Gadget:\n    pass\n")

    result = extract([a, b], cache_root=tmp_path)
    # file-level nodes are labeled with the filename; both files must survive as
    # distinct nodes (no silent separator-collision merge)
    file_nodes = [n for n in result["nodes"] if str(n.get("label", "")).endswith(".py")]
    assert len(file_nodes) == 2
    assert len({n["id"] for n in file_nodes}) == 2, [n["id"] for n in file_nodes]


def test_non_colliding_path_id_is_not_salted(tmp_path):
    """The collision hash must touch only actual colliders — a path with no collision
    keeps its plain full-path stem id (no hash suffix)."""
    from graphify.extractors.base import _file_stem
    from graphify.ids import make_id
    p = tmp_path / "src/auth/session.py"
    p.parent.mkdir(parents=True)
    p.write_text("class Session:\n    pass\n")
    result = extract([p], cache_root=tmp_path)
    file_id = next(n["id"] for n in result["nodes"] if n.get("source_location") == "L1")
    assert file_id == make_id(_file_stem(Path("src/auth/session.py"))) == "src_auth_session"


def test_case_insensitive_suffix_filtering(tmp_path):
    py_file = tmp_path / "app.PY"
    js_file = tmp_path / "script.JS"
    ts_file = tmp_path / "lib.Ts"
    
    py_file.write_text("class MyPythonClass:\n    pass\n")
    js_file.write_text("function myJSFunction() {}\n")
    ts_file.write_text("export class MyTSClass {}\n")
    
    collected = collect_files(tmp_path)
    collected_names = {f.name for f in collected}
    assert "app.PY" in collected_names
    assert "script.JS" in collected_names
    assert "lib.Ts" in collected_names

    result = extract(collected, cache_root=tmp_path)
    nodes = result["nodes"]
    labels = {n.get("label") for n in nodes if "label" in n}
    
    assert "MyPythonClass" in labels
    assert "myJSFunction()" in labels
    assert "MyTSClass" in labels



def test_extract_warns_on_code_files_with_no_ast_extractor(tmp_path, capsys):
    # #1689: .r/.R is in CODE_EXTENSIONS (counted as code) but has no AST extractor,
    # so R files silently contribute nothing. extract() must surface that instead of
    # reporting success as if the language were mapped.
    r1 = tmp_path / "analysis.R"; r1.write_text("f <- function(x) x + 1\n")
    r2 = tmp_path / "helper.r"; r2.write_text("g <- function(y) y * 2\n")
    py = tmp_path / "main.py"; py.write_text("def main():\n    return 1\n")

    result = extract([r1, r2, py], cache_root=tmp_path)
    err = capsys.readouterr().err

    assert "no AST extractor" in err
    assert ".r (2)" in err            # both R files grouped under the lowercased ext
    assert "#1689" in err
    # the Python file still extracts normally
    labels = [n.get("label") for n in result["nodes"]]
    assert any(str(l).startswith("main") for l in labels)


def test_extract_no_warning_when_all_code_has_extractors(tmp_path, capsys):
    py = tmp_path / "a.py"; py.write_text("def a():\n    return 1\n")
    extract([py], cache_root=tmp_path)
    err = capsys.readouterr().err
    assert "no AST extractor" not in err


def test_extract_warns_when_sql_extra_missing(tmp_path, capsys, monkeypatch):
    # #1745: .sql HAS a dispatch entry, so the #1689 warning can't fire, and
    # extract_sql returns an "error" result when tree-sitter-sql is absent, so
    # the #1666 warning skips it too. The files must not vanish silently:
    # extract() surfaces them with the [sql] extra named.
    monkeypatch.setitem(sys.modules, "tree_sitter_sql", None)  # import -> ImportError
    s1 = tmp_path / "schema.sql"; s1.write_text("CREATE TABLE users (id INT);\n")
    s2 = tmp_path / "views.sql"; s2.write_text("CREATE VIEW v AS SELECT * FROM users;\n")
    py = tmp_path / "main.py"; py.write_text("def main():\n    return 1\n")

    result = extract([s1, s2, py], cache_root=tmp_path)
    err = capsys.readouterr().err

    assert "2 .sql file(s)" in err
    assert "tree_sitter_sql not installed" in err
    assert 'graphifyy[sql]' in err
    assert "#1745" in err
    # the Python file still extracts normally
    labels = [n.get("label") for n in result["nodes"]]
    assert any(str(l).startswith("main") for l in labels)
    # #2543: failed sql sources must be surfaced so the CLI can leave them
    # unstamped in the incremental manifest.
    failed = {Path(p).name for p in result.get("failed_sources", [])}
    assert failed == {"schema.sql", "views.sql"}
    assert "main.py" not in failed


def test_extract_failed_sources_empty_when_sql_installed(tmp_path):
    """#2543: successful extracts do not appear in failed_sources."""
    pytest.importorskip("tree_sitter_sql")
    s = tmp_path / "schema.sql"; s.write_text("CREATE TABLE users (id INT);\n")
    py = tmp_path / "main.py"; py.write_text("def main():\n    return 1\n")
    result = extract([s, py], cache_root=tmp_path)
    assert result.get("failed_sources") == []


def test_extract_no_missing_dep_warning_when_sql_installed(tmp_path, capsys):
    pytest.importorskip("tree_sitter_sql")
    s = tmp_path / "schema.sql"; s.write_text("CREATE TABLE users (id INT);\n")
    extract([s], cache_root=tmp_path)
    err = capsys.readouterr().err
    assert "#1745" not in err


def test_extract_sql_reports_load_failure_not_missing(tmp_path, monkeypatch):
    # #2602: an installed-but-broken grammar (e.g. a wheel built for a different
    # Python ABI) raises ImportError at import time just like an absent one. The
    # extractor must NOT claim "not installed" — that sends the user to a no-op
    # `pip install` — but surface the real load exception instead.
    import builtins
    from graphify.extractors.sql import extract_sql
    pytest.importorskip("tree_sitter_sql")  # find_spec must see it as installed

    _orig_import = builtins.__import__

    def _broken_import(name, *args, **kwargs):
        if name == "tree_sitter_sql":
            raise ImportError("dynamic module does not define module export function")
        return _orig_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _broken_import)
    err = extract_sql(tmp_path / "schema.sql", "SELECT 1;").get("error") or ""
    assert "failed to load" in err
    assert "dynamic module does not define module export function" in err
    assert "pip install" not in err


def test_extract_warns_sql_grammar_failed_to_load(tmp_path, capsys, monkeypatch):
    # #2602: the aggregated #1745 warning must surface a present-but-broken
    # grammar with the real cause and WITHOUT the misleading "install the extra"
    # hint, so the files are neither silently dropped nor sent to a no-op fix.
    import builtins
    pytest.importorskip("tree_sitter_sql")

    _orig_import = builtins.__import__

    def _broken_import(name, *args, **kwargs):
        if name == "tree_sitter_sql":
            raise ImportError("dynamic module does not define module export function")
        return _orig_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _broken_import)
    s1 = tmp_path / "schema.sql"; s1.write_text("CREATE TABLE users (id INT);\n")
    s2 = tmp_path / "views.sql"; s2.write_text("CREATE VIEW v AS SELECT * FROM users;\n")

    result = extract([s1, s2], cache_root=tmp_path)
    err = capsys.readouterr().err

    assert "2 .sql file(s)" in err
    assert "failed to load" in err
    assert "#1745" in err
    # the no-op fix must NOT be suggested for a present-but-broken grammar
    assert "graphifyy[sql]" not in err
    assert "pip install" not in err
    # #2543: still surfaced as failed so the incremental manifest retries them
    failed = {Path(p).name for p in result.get("failed_sources", [])}
    assert failed == {"schema.sql", "views.sql"}


def test_extract_progress_final_line_uses_consistent_denominator(tmp_path, capsys):
    # #1693: intermediate progress lines count against uncached_work; the final
    # "100%" line must NOT switch to total_files (which includes cached hits and
    # files with no extractor), or the count appears to jump upward at the end.
    for i in range(100):
        (tmp_path / f"m{i}.py").write_text(f"def f{i}():\n    return {i}\n")
    for i in range(5):
        (tmp_path / f"s{i}.r").write_text(f"g{i} <- function(x) x\n")  # no extractor
    paths = sorted(tmp_path.glob("*.py")) + sorted(tmp_path.glob("*.r"))  # total 105

    extract(paths, cache_root=tmp_path, parallel=False)
    out = capsys.readouterr().out

    # final progress line reports the uncached count (100), not the total (105)
    assert "100/100 uncached files (100%)" in out
    assert "105/105 files" not in out, "final line must not switch to total_files (#1693)"


def test_get_extractor_routes_matlab_m_away_from_objc(tmp_path):
    # #1702: .m is shared by Objective-C and MATLAB. A real ObjC .m still routes to
    # extract_objc, but a MATLAB .m must NOT be force-parsed by the ObjC grammar
    # (which produces garbage) — it gets no extractor instead.
    from graphify.extract import _get_extractor, extract_objc

    objc = tmp_path / "Foo.m"
    objc.write_text('#import "Foo.h"\n@implementation Foo\n- (void)bar {}\n@end\n')
    matlab_fn = tmp_path / "solver.m"
    matlab_fn.write_text("function y = solver(x)\n  y = x + 1;\nend\n")
    matlab_cls = tmp_path / "Model.m"
    matlab_cls.write_text("classdef Model\n  methods\n    function run(obj); end\n  end\nend\n")
    mm = tmp_path / "x.mm"
    mm.write_text("#import <F/F.h>\n@implementation X\n@end\n")

    assert _get_extractor(objc) is extract_objc            # real ObjC .m -> objc
    assert _get_extractor(matlab_fn) is None               # MATLAB function -> no garbage
    assert _get_extractor(matlab_cls) is None              # MATLAB classdef -> no garbage
    assert _get_extractor(mm) is extract_objc              # .mm is unambiguously ObjC++


def test_matlab_m_not_extracted_as_garbage(tmp_path, capsys):
    # End to end: a MATLAB .m produces no (garbage) nodes and is surfaced by the
    # no-AST-extractor warning (#1702 + #1689), rather than mis-parsed as ObjC.
    m = tmp_path / "controller.m"
    m.write_text("function u = controller(x)\n  u = -x;\nend\n")
    result = extract([m], cache_root=tmp_path)
    assert result["nodes"] == []                           # no garbage ObjC nodes
    assert "no AST extractor" in capsys.readouterr().err    # surfaced, not silent


def test_rewire_binds_cross_module_function_reference_to_definition():
    """#1781: a cross-module reference to a function must land on the real
    definition, not a sourceless name-only stub (functions were excluded as
    rewire targets)."""
    from graphify.extract import _rewire_unique_stub_nodes
    nodes = [
        {"id": "pkg_dep_get_db", "label": "get_db()", "file_type": "code",
         "source_file": "pkg/dep.py", "source_location": "L1"},
        {"id": "get_db", "label": "get_db()", "file_type": "code", "source_file": ""},
    ]
    edges = [{"source": "pkg_ep_route", "target": "get_db", "relation": "references",
              "source_file": "pkg/ep.py", "weight": 1.0}]
    _rewire_unique_stub_nodes(nodes, edges)
    assert edges[0]["target"] == "pkg_dep_get_db"
    assert "get_db" not in {n["id"] for n in nodes}  # stub dropped


def test_rewire_does_not_bind_function_reference_across_language():
    """#1781 safety: a Python reference stub must not bind to a unique Go
    function of the same name (mirrors the #1749 interop guard)."""
    from graphify.extract import _rewire_unique_stub_nodes
    nodes = [
        {"id": "svc_get_db", "label": "get_db()", "file_type": "code",
         "source_file": "svc/main.go", "source_location": "L1"},
        {"id": "get_db", "label": "get_db()", "file_type": "code", "source_file": ""},
    ]
    edges = [{"source": "app_route", "target": "get_db", "relation": "references",
              "source_file": "app/route.py", "weight": 1.0}]
    _rewire_unique_stub_nodes(nodes, edges)
    assert edges[0]["target"] == "get_db"  # unchanged — cross-language blocked


def test_rewire_does_not_bind_ambiguous_function_reference():
    """#1781 safety: two same-named functions leave the reference on the stub."""
    from graphify.extract import _rewire_unique_stub_nodes
    nodes = [
        {"id": "a_get_db", "label": "get_db()", "file_type": "code", "source_file": "a.py", "source_location": "L1"},
        {"id": "b_get_db", "label": "get_db()", "file_type": "code", "source_file": "b.py", "source_location": "L1"},
        {"id": "get_db", "label": "get_db()", "file_type": "code", "source_file": ""},
    ]
    edges = [{"source": "c_route", "target": "get_db", "relation": "references",
              "source_file": "c.py", "weight": 1.0}]
    _rewire_unique_stub_nodes(nodes, edges)
    assert edges[0]["target"] == "get_db"  # ambiguous — not merged


def test_rewire_does_not_bind_supertype_stub_to_function():
    """#1781 safety: a stub used as a base type must never resolve to a
    same-named, same-language function."""
    from graphify.extract import _rewire_unique_stub_nodes
    nodes = [
        {"id": "factory_BookStore", "label": "BookStore()", "file_type": "code",
         "source_file": "factory.py", "source_location": "L1"},
        {"id": "BookStore", "label": "BookStore", "file_type": "code", "source_file": ""},
    ]
    edges = [{"source": "store_Sqlite", "target": "BookStore", "relation": "inherits",
              "source_file": "store.py", "weight": 1.0}]
    _rewire_unique_stub_nodes(nodes, edges)
    assert edges[0]["target"] == "BookStore"  # inherits stub not bound to function


def test_rewire_does_not_bind_supertype_stub_across_language():
    """#2812: a bare `extends Exception` in PHP is the language's own built-in.
    It must not fuse onto a unique same-named TypeScript class."""
    from graphify.extract import _rewire_unique_stub_nodes
    nodes = [
        {"id": "app_exception_Exception", "label": "Exception", "file_type": "code",
         "source_file": "app/exception.ts", "source_location": "L1"},
        {"id": "Exception", "label": "Exception", "file_type": "code", "source_file": ""},
    ]
    edges = [{"source": "pkg_FooApiException", "target": "Exception", "relation": "inherits",
              "source_file": "pkg/FooApiException.php", "weight": 1.0}]
    _rewire_unique_stub_nodes(nodes, edges)
    assert edges[0]["target"] == "Exception"  # unchanged — cross-language blocked
    assert "Exception" in {n["id"] for n in nodes}  # stub kept as the external base


def test_rewire_binds_builtin_named_supertype_stub_within_same_language():
    """#2812 control: the guard is per language family, not a name blocklist — a
    PHP corpus that declares its own `Exception` must still absorb the stub."""
    from graphify.extract import _rewire_unique_stub_nodes
    nodes = [
        {"id": "pkg_support_Exception", "label": "Exception", "file_type": "code",
         "source_file": "pkg/Support/Exception.php", "source_location": "L1"},
        {"id": "Exception", "label": "Exception", "file_type": "code", "source_file": ""},
    ]
    edges = [{"source": "pkg_FooApiException", "target": "Exception", "relation": "inherits",
              "source_file": "pkg/FooApiException.php", "weight": 1.0}]
    _rewire_unique_stub_nodes(nodes, edges)
    assert edges[0]["target"] == "pkg_support_Exception"


def test_rewire_builtin_supertype_guard_folds_case_insensitive_languages():
    """#2812: PHP resolves class names case-insensitively, so `extends \\exception`
    names the same built-in as `extends \\Exception` and must be blocked too."""
    from graphify.extract import _rewire_unique_stub_nodes
    nodes = [
        {"id": "app_exception_exception", "label": "exception", "file_type": "code",
         "source_file": "app/exception.ts", "source_location": "L1"},
        {"id": "exception", "label": "exception", "file_type": "code", "source_file": ""},
    ]
    edges = [{"source": "pkg_FooApiException", "target": "exception", "relation": "inherits",
              "source_file": "pkg/FooApiException.php", "weight": 1.0}]
    _rewire_unique_stub_nodes(nodes, edges)
    assert edges[0]["target"] == "exception"


def test_rewire_builtin_supertype_guard_is_per_edge_not_per_stub():
    """#2812: one sourceless `Exception` stub collects referrers from every
    language that names it. A TypeScript referrer sharing the stub must not
    re-open the cross-language bind for the PHP one — the guard reads the
    referring file, not the union of the stub's referrer families."""
    from graphify.extract import _rewire_unique_stub_nodes
    nodes = [
        {"id": "app_exception_Exception", "label": "Exception", "file_type": "code",
         "source_file": "app/exception.ts", "source_location": "L1"},
        {"id": "Exception", "label": "Exception", "file_type": "code", "source_file": ""},
    ]
    edges = [
        {"source": "pkg_FooApiException", "target": "Exception", "relation": "inherits",
         "source_file": "pkg/FooApiException.php", "weight": 1.0},
        {"source": "app_http_HttpError", "target": "Exception", "relation": "inherits",
         "source_file": "app/http.ts", "weight": 1.0},
    ]
    _rewire_unique_stub_nodes(nodes, edges)
    assert edges[0]["target"] == "Exception"                 # PHP still blocked
    assert edges[1]["target"] == "app_exception_Exception"   # TS still resolves


def test_extract_emits_posix_source_file_for_relative_inputs(tmp_path):
    r"""source_file must be canonical POSIX on every node AND edge, whatever
    separator the caller's input paths used.

    Extractors build source_file from the Path handed to them, and only the
    relativizing branch of extract()'s remap calls as_posix(), so a run given
    relative inputs used to keep the native separator on Windows — mixing
    `src\lib\content.ts` and `src/pages/index.astro` in one extraction.
    source_file is compared as a string downstream (build keying, prune-root
    derivation, dedup, analyze.find_import_cycles), so two spellings are two
    different files (#683 / #2625).

    Uses the relative-input form deliberately: passing an explicit ``root``
    takes the branch that already normalized, and would make this vacuous.
    """
    (tmp_path / "src" / "lib").mkdir(parents=True)
    (tmp_path / "src" / "pages").mkdir(parents=True)
    (tmp_path / "src" / "lib" / "content.ts").write_text(
        "export function getPosts() { return []; }\n", encoding="utf-8"
    )
    (tmp_path / "src" / "pages" / "index.astro").write_text(
        "---\nimport { getPosts } from '../lib/content';\n"
        "const posts = getPosts();\n---\n<h1>{posts.length}</h1>\n",
        encoding="utf-8",
    )

    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        result = extract([Path("src/lib/content.ts"), Path("src/pages/index.astro")])
    finally:
        os.chdir(cwd)

    carriers = [
        (kind, item.get("source_file"))
        for kind, items in (("node", result["nodes"]), ("edge", result["edges"]))
        for item in items
        if item.get("source_file")
    ]
    assert carriers, "fixture produced nothing with a source_file; test would be vacuous"

    offenders = [(kind, sf) for kind, sf in carriers if "\\" in sf]
    assert not offenders, f"native separator survived into source_file: {offenders}"

    # ...and both files are present under one spelling each, so the graph sees
    # two files rather than four.
    assert {sf for _, sf in carriers} == {
        "src/lib/content.ts", "src/pages/index.astro",
    }


def _inferred_uses(result):
    """(source, target) pairs of every INFERRED cross-file `uses` edge."""
    return {
        (e["source"], e["target"])
        for e in result["edges"]
        if e.get("relation") == "uses" and e.get("confidence") == "INFERRED"
    }


def test_inferred_uses_edge_attributes_to_the_referencing_symbol(tmp_path):
    """A cross-file INFERRED `uses` edge binds to the symbol that actually
    references the import — a function is a valid source and a co-located class
    that never touches the import gets no edge (#2652)."""
    (tmp_path / "helpers.py").write_text("class Helper:\n    pass\n", encoding="utf-8")
    (tmp_path / "api.py").write_text(
        "from helpers import Helper\n\n\n"
        "class Request:\n    x: int = 0\n\n\n"
        "def handler(req):\n    return Helper()\n",
        encoding="utf-8",
    )

    result = extract([tmp_path / "api.py", tmp_path / "helpers.py"], cache_root=tmp_path)
    uses = _inferred_uses(result)

    # handler() references Helper -> it is the source.
    assert ("api_handler", "helpers_helper") in uses
    # Request never references Helper -> no false edge from the co-located class.
    assert ("api_request", "helpers_helper") not in uses


def test_inferred_uses_edge_kept_when_the_class_body_references_the_import(tmp_path):
    """Positive control: a class that genuinely uses the imported symbol still
    gets its class-level INFERRED `uses` edge (the DigestAuth->Response case)."""
    (tmp_path / "models.py").write_text("class Response:\n    pass\n", encoding="utf-8")
    (tmp_path / "auth.py").write_text(
        "from models import Response\n\n\n"
        "class DigestAuth:\n    def build(self):\n        return Response()\n",
        encoding="utf-8",
    )

    result = extract([tmp_path / "auth.py", tmp_path / "models.py"], cache_root=tmp_path)

    assert ("auth_digestauth", "models_response") in _inferred_uses(result)


def test_inferred_uses_edge_follows_an_import_alias(tmp_path):
    """`from helpers import Helper as H` attributes via the local alias `H`, so a
    body that only ever names `H` still resolves to the imported target (#2652)."""
    (tmp_path / "helpers.py").write_text("class Helper:\n    pass\n", encoding="utf-8")
    (tmp_path / "api.py").write_text(
        "from helpers import Helper as H\n\n\n"
        "def handler(req):\n    return H()\n",
        encoding="utf-8",
    )

    result = extract([tmp_path / "api.py", tmp_path / "helpers.py"], cache_root=tmp_path)

    assert ("api_handler", "helpers_helper") in _inferred_uses(result)


def test_inferred_uses_edge_emitted_once_per_referencing_symbol(tmp_path):
    """Each symbol that references the import gets its own edge, and only those
    symbols do — guards against the old fan-out (every class in the file) and
    against collapsing distinct sources into one (#2652)."""
    (tmp_path / "helpers.py").write_text("class Helper:\n    pass\n", encoding="utf-8")
    (tmp_path / "api.py").write_text(
        "from helpers import Helper\n\n\n"
        "def a(x):\n    return Helper()\n\n\n"
        "def b(x):\n    return Helper()\n\n\n"
        "def c(x):\n    return x\n",  # references nothing -> no edge
        encoding="utf-8",
    )

    result = extract([tmp_path / "api.py", tmp_path / "helpers.py"], cache_root=tmp_path)
    uses = _inferred_uses(result)

    assert ("api_a", "helpers_helper") in uses
    assert ("api_b", "helpers_helper") in uses
    assert ("api_c", "helpers_helper") not in uses


def test_inferred_uses_edge_dropped_for_module_top_level_reference(tmp_path):
    """A reference at true module top level has no enclosing symbol to anchor on,
    so no INFERRED `uses` edge is emitted (rather than falling back to the file
    node) — the deliberate drop documented for #2652."""
    (tmp_path / "helpers.py").write_text("class Helper:\n    pass\n", encoding="utf-8")
    (tmp_path / "api.py").write_text(
        "from helpers import Helper\n\n\n"
        "SENTINEL = Helper()\n",  # top-level, outside any def/class
        encoding="utf-8",
    )

    result = extract([tmp_path / "api.py", tmp_path / "helpers.py"], cache_root=tmp_path)
    uses = _inferred_uses(result)

    assert not any(tgt == "helpers_helper" for _, tgt in uses)


def test_extract_declined_data_json_is_not_failed(tmp_path, capsys):
    """#2879: data JSON is declined by design (#1224), not failed.

    A `.json` extractor is registered, so a declined file used to satisfy both
    halves of the failed-source test (zero nodes + extractor exists) and was
    re-queued on every incremental run because the CLI never stamped it as
    processed.
    """
    pytest.importorskip("tree_sitter_json")
    data = tmp_path / "meta.json"
    data.write_text('{"pages": ["a", "b"], "title": "Docs"}\n')
    cfg = tmp_path / "package.json"
    cfg.write_text('{"dependencies": {"left-pad": "^1.0.0"}}\n')

    result = extract([data, cfg], cache_root=tmp_path)
    err = capsys.readouterr().err

    assert result.get("failed_sources") == []
    # ...and no "produced zero nodes" noise for a deliberate decline (#1666).
    assert "zero nodes" not in err
    # the config JSON still extracts normally
    assert any(str(n.get("label", "")).startswith("package.json") for n in result["nodes"])


def test_extract_genuinely_empty_json_still_failed(tmp_path, monkeypatch):
    """#2879 guard: only an explicit `skipped` marker is exempt."""
    pytest.importorskip("tree_sitter_json")
    import graphify.extract as _ex

    monkeypatch.setattr(
        _ex, "_get_extractor",
        lambda p: (lambda _p: {"nodes": [], "edges": []}) if p.suffix == ".json" else None,
    )
    p = tmp_path / "meta.json"
    p.write_text("{}\n")
    result = _ex.extract([p], cache_root=tmp_path)
    assert [Path(x).name for x in result.get("failed_sources", [])] == ["meta.json"]


# ── #3252: Authoritative Python Type Reference and Inheritance Rewiring ────────

def test_3252_exact_import_beats_global_ambiguity(tmp_path):
    """#3252: When two packages define same-named types, exact import resolution
    repoints references to the imported canonical definition without ghost stubs."""
    (tmp_path / "pkg_a").mkdir()
    (tmp_path / "pkg_b").mkdir()
    (tmp_path / "pkg_a" / "types.py").write_text("class StateFrame:\n    pass\n", encoding="utf-8")
    (tmp_path / "pkg_b" / "types.py").write_text("class StateFrame:\n    pass\n", encoding="utf-8")
    (tmp_path / "consumer_a.py").write_text(
        "from pkg_a.types import StateFrame\ndef foo_a(x: StateFrame):\n    pass\n", encoding="utf-8"
    )
    (tmp_path / "consumer_b.py").write_text(
        "from pkg_b.types import StateFrame\ndef foo_b(x: StateFrame):\n    pass\n", encoding="utf-8"
    )

    files = [
        tmp_path / "pkg_a" / "types.py",
        tmp_path / "pkg_b" / "types.py",
        tmp_path / "consumer_a.py",
        tmp_path / "consumer_b.py",
    ]
    res = extract(files, root=tmp_path, cache_root=tmp_path)
    node_by_id = {n["id"]: n for n in res["nodes"]}

    ref_edges = [e for e in res["edges"] if e.get("relation") == "references"]
    ref_a = next(e for e in ref_edges if "consumer_a_foo_a" in e["source"])
    ref_b = next(e for e in ref_edges if "consumer_b_foo_b" in e["source"])

    assert node_by_id[ref_a["target"]]["source_file"] == "pkg_a/types.py"
    assert node_by_id[ref_b["target"]]["source_file"] == "pkg_b/types.py"

    # All StateFrame nodes in the graph must be source-backed definitions (0 stubs)
    sf_nodes = [n for n in res["nodes"] if n.get("label") == "StateFrame"]
    assert len(sf_nodes) == 2
    assert all(n.get("source_file") for n in sf_nodes)


def test_3252_aliased_import_repoints_references(tmp_path):
    """#3252: Aliased import (`from state import StateFrame as SF`) repoints
    references to the canonical StateFrame and removes the SF stub."""
    (tmp_path / "state.py").write_text("class StateFrame:\n    pass\n", encoding="utf-8")
    (tmp_path / "consumer.py").write_text(
        "from state import StateFrame as SF\ndef foo(x: SF):\n    pass\n", encoding="utf-8"
    )

    res = extract([tmp_path / "state.py", tmp_path / "consumer.py"], root=tmp_path, cache_root=tmp_path)
    node_by_id = {n["id"]: n for n in res["nodes"]}

    ref_edge = next(e for e in res["edges"] if e.get("relation") == "references")
    assert ref_edge["source"] == "consumer_foo"
    assert node_by_id[ref_edge["target"]]["label"] == "StateFrame"
    assert node_by_id[ref_edge["target"]]["source_file"] == "state.py"
    assert ref_edge["context"] == "parameter_type"
    assert ref_edge["confidence"] == "EXTRACTED"

    # SF stub removed
    assert not any(n.get("label") == "SF" for n in res["nodes"])


def test_3252_inheritance_repoints_inherits_edge(tmp_path):
    """#3252: Class inheritance (`class Child(StateFrame):`) repoints the inherits
    edge to the canonical definition without ghost stubs."""
    (tmp_path / "state.py").write_text("class StateFrame:\n    pass\n", encoding="utf-8")
    (tmp_path / "consumer.py").write_text(
        "from state import StateFrame\nclass Child(StateFrame):\n    pass\n", encoding="utf-8"
    )

    res = extract([tmp_path / "state.py", tmp_path / "consumer.py"], root=tmp_path, cache_root=tmp_path)
    node_by_id = {n["id"]: n for n in res["nodes"]}

    inherits_edge = next(e for e in res["edges"] if e.get("relation") == "inherits")
    assert inherits_edge["source"] == "consumer_child"
    assert node_by_id[inherits_edge["target"]]["label"] == "StateFrame"
    assert node_by_id[inherits_edge["target"]]["source_file"] == "state.py"

    # No sourceless StateFrame stubs remain
    sf_nodes = [n for n in res["nodes"] if n.get("label") == "StateFrame"]
    assert len(sf_nodes) == 1
    assert sf_nodes[0].get("source_file") == "state.py"


def test_3252_relative_imports(tmp_path):
    """#3252: Relative imports (`from .types import StateFrame`) repoint accurately."""
    (tmp_path / "pkg" / "sub").mkdir(parents=True)
    (tmp_path / "pkg" / "sub" / "types.py").write_text("class StateFrame:\n    pass\n", encoding="utf-8")
    (tmp_path / "pkg" / "sub" / "consumer.py").write_text(
        "from .types import StateFrame\ndef foo(x: StateFrame):\n    pass\n", encoding="utf-8"
    )

    files = [tmp_path / "pkg" / "sub" / "types.py", tmp_path / "pkg" / "sub" / "consumer.py"]
    res = extract(files, root=tmp_path, cache_root=tmp_path)
    node_by_id = {n["id"]: n for n in res["nodes"]}

    ref_edge = next(e for e in res["edges"] if e.get("relation") == "references")
    assert node_by_id[ref_edge["target"]]["source_file"] == "pkg/sub/types.py"
    assert not any(n.get("label") == "StateFrame" and not n.get("source_file") for n in res["nodes"])


def test_3252_unimported_ambiguous_type_remains_unresolved(tmp_path):
    """#3252: When multiple definitions exist but consumer has no import, Graphify
    must NOT guess or collapse to an arbitrary definition."""
    (tmp_path / "pkg_a").mkdir()
    (tmp_path / "pkg_b").mkdir()
    (tmp_path / "pkg_a" / "types.py").write_text("class StateFrame:\n    pass\n", encoding="utf-8")
    (tmp_path / "pkg_b" / "types.py").write_text("class StateFrame:\n    pass\n", encoding="utf-8")
    (tmp_path / "consumer.py").write_text(
        "def foo(x: StateFrame):\n    pass\n", encoding="utf-8"
    )

    files = [
        tmp_path / "pkg_a" / "types.py",
        tmp_path / "pkg_b" / "types.py",
        tmp_path / "consumer.py",
    ]
    res = extract(files, root=tmp_path, cache_root=tmp_path)
    node_by_id = {n["id"]: n for n in res["nodes"]}

    ref_edge = next(e for e in res["edges"] if e.get("relation") == "references")
    # Stub must NOT have bound to either definition
    target_node = node_by_id[ref_edge["target"]]
    assert not target_node.get("source_file")


def test_3252_cross_language_same_name_definition(tmp_path):
    """#3252: Python import resolution resolves only to Python definitions, not
    same-named TypeScript definitions."""
    pytest.importorskip("tree_sitter_typescript")
    (tmp_path / "types.py").write_text("class StateFrame:\n    pass\n", encoding="utf-8")
    (tmp_path / "types.ts").write_text("export interface StateFrame { id: string; }\n", encoding="utf-8")
    (tmp_path / "consumer.py").write_text(
        "from types import StateFrame\ndef foo(x: StateFrame):\n    pass\n", encoding="utf-8"
    )

    files = [tmp_path / "types.py", tmp_path / "types.ts", tmp_path / "consumer.py"]
    res = extract(files, root=tmp_path, cache_root=tmp_path)
    node_by_id = {n["id"]: n for n in res["nodes"]}

    ref_edge = next(e for e in res["edges"] if e.get("relation") == "references")
    assert node_by_id[ref_edge["target"]]["source_file"] == "types.py"


def test_3252_alias_and_inheritance(tmp_path):
    """#3252: Aliased import in inheritance (`class Child(SF):`) repoints inherits
    edge to canonical StateFrame and drops the SF stub."""
    (tmp_path / "state.py").write_text("class StateFrame:\n    pass\n", encoding="utf-8")
    (tmp_path / "consumer.py").write_text(
        "from state import StateFrame as SF\nclass Child(SF):\n    pass\n", encoding="utf-8"
    )

    res = extract([tmp_path / "state.py", tmp_path / "consumer.py"], root=tmp_path, cache_root=tmp_path)
    node_by_id = {n["id"]: n for n in res["nodes"]}

    inherits_edge = next(e for e in res["edges"] if e.get("relation") == "inherits")
    assert inherits_edge["source"] == "consumer_child"
    assert node_by_id[inherits_edge["target"]]["label"] == "StateFrame"
    assert node_by_id[inherits_edge["target"]]["source_file"] == "state.py"
    assert not any(n.get("label") == "SF" for n in res["nodes"])


def test_3252_metadata_preservation(tmp_path):
    """#3252: Repointing mutates only edge['target'] while preserving relation,
    context, confidence, confidence_score, source_file, and source_location."""
    (tmp_path / "models.py").write_text("class User:\n    pass\n", encoding="utf-8")
    (tmp_path / "service.py").write_text(
        "from models import User\ndef get_user(u: User) -> User:\n    pass\n", encoding="utf-8"
    )

    res = extract([tmp_path / "models.py", tmp_path / "service.py"], root=tmp_path, cache_root=tmp_path)
    node_by_id = {n["id"]: n for n in res["nodes"]}

    param_ref = next(
        e for e in res["edges"]
        if e.get("relation") == "references" and e.get("context") == "parameter_type"
    )
    assert param_ref["relation"] == "references"
    assert param_ref["context"] == "parameter_type"
    assert param_ref["confidence"] == "EXTRACTED"
    assert param_ref["source_file"] == "service.py"
    assert param_ref["source_location"] == "L2"
    assert node_by_id[param_ref["target"]]["label"] == "User"
    assert node_by_id[param_ref["target"]]["source_file"] == "models.py"


def test_relative_input_source_file_is_normalized_to_posix(tmp_path, monkeypatch):
    """#2625: extract()'s canonicalization pass only ran a relative source_file
    through as_posix() when the caller passed an explicit `root` — the
    documented `extract(paths)` entry point with no root (and
    `python -m graphify.extract <file>...`) left it exactly as the extractor
    set it. Every extractor sets source_file via plain str(path), which on
    Windows renders with a native `\\` separator, diverging from the POSIX
    form every other path (explicit root, the CLI) produces — fragmenting
    the string-equality lookups keyed on source_file (build._norm_source_file,
    analyze.find_import_cycles, the semantic-cache key) into two spellings of
    one file.

    A real WindowsPath can't be constructed on a POSIX test runner, so this
    monkeypatches one extension's dispatch to return a node/edge whose
    source_file is a literal backslash-separated string — exactly the shape
    str(WindowsPath("sub/file.py")) produces on a real Windows machine —
    and asserts extract()'s post-pass normalizes it, exercising the actual
    fixed code path rather than the OS-dependent symptom.
    """
    import graphify.extract as extract_mod

    def _fake_windows_extractor(path):
        return {
            "nodes": [{
                "id": "fake_node", "label": "fake", "file_type": "code",
                "source_file": "sub\\file.py", "source_location": "L1",
            }],
            "edges": [{
                "source": "fake_node", "target": "other_node", "relation": "calls",
                "confidence": "EXTRACTED", "source_file": "sub\\file.py",
            }],
        }

    real_get_extractor = extract_mod._get_extractor

    def _patched_get_extractor(path):
        if path.suffix == ".fakewin":
            return _fake_windows_extractor
        return real_get_extractor(path)

    monkeypatch.setattr(extract_mod, "_get_extractor", _patched_get_extractor)

    (tmp_path / "sub").mkdir()
    target = tmp_path / "sub" / "file.fakewin"
    target.write_text("irrelevant", encoding="utf-8")

    old_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        result = extract([Path("sub/file.fakewin")])
    finally:
        os.chdir(old_cwd)

    node = next(n for n in result["nodes"] if n["id"] == "fake_node")
    edge = next(e for e in result["edges"] if e["source"] == "fake_node")
    assert node["source_file"] == "sub/file.py", node["source_file"]
    assert edge["source_file"] == "sub/file.py", edge["source_file"]
