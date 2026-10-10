"""Regression coverage for package-qualified Go calls and type references."""

from pathlib import Path

from graphify.extract import extract


def _extract(root: Path) -> dict:
    return extract(
        sorted(root.rglob("*.go")),
        cache_root=root,
        root=root,
        parallel=False,
    )


def _ids(result: dict, *, label: str, suffix: str) -> set[str]:
    return {
        node["id"]
        for node in result["nodes"]
        if str(node.get("source_file", "")).endswith(suffix)
        and str(node.get("label", "")).strip(".()") == label
    }


def test_external_package_new_does_not_bind_to_local_new(tmp_path: Path) -> None:
    """``errors.New`` must not become a call to an unrelated local ``New``."""
    (tmp_path / "go.mod").write_text("module example.com/repro\n\ngo 1.22\n")
    (tmp_path / "factory.go").write_text("package repro\n\nfunc New() int { return 1 }\n")
    (tmp_path / "worker.go").write_text(
        'package repro\n\nimport "errors"\n\nfunc Build() error { return errors.New("boom") }\n'
    )

    result = _extract(tmp_path)
    build_ids = _ids(result, label="Build", suffix="worker.go")
    local_new_ids = _ids(result, label="New", suffix="factory.go")
    phantom = [
        edge
        for edge in result["edges"]
        if edge.get("relation") == "calls"
        and edge.get("source") in build_ids
        and edge.get("target") in local_new_ids
    ]
    assert phantom == [], f"errors.New bound to the local New: {phantom}"


def test_internal_aliased_package_new_resolves_exact_import(tmp_path: Path) -> None:
    """An imported internal package selector resolves despite same-name decoys."""
    (tmp_path / "go.mod").write_text("module example.com/repro\n\ngo 1.22\n")
    factory = tmp_path / "factory"
    factory.mkdir()
    (factory / "factory.go").write_text("package factory\n\nfunc New() int { return 1 }\n")
    app = tmp_path / "app"
    app.mkdir()
    (app / "decoy.go").write_text("package app\n\nfunc New() int { return 2 }\n")
    (app / "worker.go").write_text(
        'package app\n\nimport maker "example.com/repro/factory"\n\n'
        "func Build() int { return maker.New() }\n"
    )

    result = _extract(tmp_path)
    build_ids = _ids(result, label="Build", suffix="app/worker.go")
    factory_new_ids = _ids(result, label="New", suffix="factory/factory.go")
    decoy_new_ids = _ids(result, label="New", suffix="app/decoy.go")
    calls = [
        edge
        for edge in result["edges"]
        if edge.get("relation") == "calls" and edge.get("source") in build_ids
    ]
    assert len(calls) == 1, calls
    assert calls[0]["target"] in factory_new_ids
    assert calls[0]["target"] not in decoy_new_ids
    assert calls[0]["confidence"] == "EXTRACTED"


def test_external_qualified_type_does_not_bind_to_local_function(tmp_path: Path) -> None:
    """``*testing.T`` must not reference an unrelated local function ``T``."""
    (tmp_path / "go.mod").write_text("module example.com/repro\n\ngo 1.22\n")
    (tmp_path / "translate.go").write_text(
        "package repro\n\nfunc T(message string) string { return message }\n"
    )
    (tmp_path / "worker_test.go").write_text(
        'package repro\n\nimport "testing"\n\nfunc TestBuild(t *testing.T) {}\n'
    )

    result = _extract(tmp_path)
    test_ids = _ids(result, label="TestBuild", suffix="worker_test.go")
    local_t_ids = _ids(result, label="T", suffix="translate.go")
    refs = [
        edge
        for edge in result["edges"]
        if edge.get("relation") == "references" and edge.get("source") in test_ids
    ]
    assert refs
    assert all(edge.get("target") not in local_t_ids for edge in refs), refs

    nodes = {node["id"]: node for node in result["nodes"]}
    assert any(nodes[edge["target"]]["label"] == "testing.T" for edge in refs)


def test_internal_qualified_type_resolves_exact_import(tmp_path: Path) -> None:
    """An aliased internal qualified type points to its package definition."""
    (tmp_path / "go.mod").write_text("module example.com/repro\n\ngo 1.22\n")
    model = tmp_path / "model"
    model.mkdir()
    (model / "user.go").write_text("package model\n\ntype User struct{}\n")
    app = tmp_path / "app"
    app.mkdir()
    (app / "decoy.go").write_text("package app\n\ntype User struct{}\n")
    (app / "handler.go").write_text(
        'package app\n\nimport domain "example.com/repro/model"\n\n'
        "func Handle(user *domain.User) {}\n"
    )

    result = _extract(tmp_path)
    handle_ids = _ids(result, label="Handle", suffix="app/handler.go")
    model_user_ids = _ids(result, label="User", suffix="model/user.go")
    decoy_user_ids = _ids(result, label="User", suffix="app/decoy.go")
    refs = [
        edge
        for edge in result["edges"]
        if edge.get("relation") == "references" and edge.get("source") in handle_ids
    ]
    assert len(refs) == 1, refs
    assert refs[0]["target"] in model_user_ids
    assert refs[0]["target"] not in decoy_user_ids


def test_incremental_qualified_resolution_uses_unchanged_context(tmp_path: Path) -> None:
    """Changed callers still resolve calls and types defined in unchanged files."""
    (tmp_path / "go.mod").write_text("module example.com/repro\n\ngo 1.22\n")
    factory = tmp_path / "factory"
    factory.mkdir()
    target = factory / "factory.go"
    target.write_text(
        "package factory\n\ntype User struct{}\n\n"
        "func New() *User { return &User{} }\n"
    )
    app = tmp_path / "app"
    app.mkdir()
    caller = app / "worker.go"
    caller.write_text(
        'package app\n\nimport maker "example.com/repro/factory"\n\n'
        "func Build() *maker.User { return maker.New() }\n"
    )
    full = _extract(tmp_path)

    caller.write_text(caller.read_text() + "\n")
    changed = extract(
        [caller],
        cache_root=tmp_path,
        root=tmp_path,
        parallel=False,
        resolution_context_nodes=full["nodes"],
        resolution_context_edges=full["edges"],
    )

    build_ids = _ids(changed, label="Build", suffix="app/worker.go")
    full_new_ids = _ids(full, label="New", suffix="factory/factory.go")
    full_user_ids = _ids(full, label="User", suffix="factory/factory.go")
    assert any(
        edge.get("relation") == "calls"
        and edge.get("source") in build_ids
        and edge.get("target") in full_new_ids
        for edge in changed["edges"]
    )
    assert any(
        edge.get("relation") == "references"
        and edge.get("source") in build_ids
        and edge.get("target") in full_user_ids
        for edge in changed["edges"]
    )


def _case_only_sibling_corpus(tmp_path: Path) -> None:
    """Exported wrapper + unexported worker of the same name, plus a decoy."""
    (tmp_path / "go.mod").write_text("module example.com/repro\n\ngo 1.22\n")
    pkg_a = tmp_path / "pkga"
    pkg_a.mkdir()
    (pkg_a / "a.go").write_text(
        "package pkga\n"
        "\n"
        "func Run() error {\n"
        "\treturn run(1)\n"
        "}\n"
        "\n"
        "func run(n int) error {\n"
        "\treturn nil\n"
        "}\n"
    )
    pkg_b = tmp_path / "pkgb"
    pkg_b.mkdir()
    (pkg_b / "b.go").write_text(
        "package pkgb\n\nfunc run(s string) error {\n\treturn nil\n}\n"
    )


def test_case_only_sibling_functions_are_both_extracted(tmp_path: Path) -> None:
    """``Run`` and ``run`` in one file are two symbols, not one."""
    _case_only_sibling_corpus(tmp_path)
    result = _extract(tmp_path)

    exported = _ids(result, label="Run", suffix="a.go")
    unexported = _ids(result, label="run", suffix="a.go")
    assert len(exported) == 1, f"exported Run missing: {exported}"
    assert len(unexported) == 1, f"unexported run missing: {unexported}"
    assert exported != unexported, "Run and run collapsed onto one node id"


def test_case_only_sibling_does_not_bind_to_another_package(tmp_path: Path) -> None:
    """``Run`` calls its own file's ``run``, never another package's."""
    _case_only_sibling_corpus(tmp_path)
    result = _extract(tmp_path)

    exported = _ids(result, label="Run", suffix="a.go")
    foreign = _ids(result, label="run", suffix="b.go")
    phantom = [
        edge
        for edge in result["edges"]
        if edge.get("relation") == "calls"
        and edge.get("source") in exported
        and edge.get("target") in foreign
    ]
    assert phantom == [], f"Run bound to another package's unexported run: {phantom}"


def test_case_only_sibling_exported_keeps_stable_id(tmp_path: Path) -> None:
    """The exported member keeps the plain id whether or not a sibling exists.

    Cross-package edges and graph.json entries from files an incremental rebuild
    does not touch all target the exported symbol, so its id must not depend on
    the presence of an unexported case-only sibling.
    """
    (tmp_path / "go.mod").write_text("module example.com/repro\n\ngo 1.22\n")
    pkg = tmp_path / "pkga"
    pkg.mkdir()
    solo = "package pkga\n\nfunc Run() error {\n\treturn nil\n}\n"
    with_sibling = (
        "package pkga\n"
        "\n"
        "func Run() error {\n"
        "\treturn run(1)\n"
        "}\n"
        "\n"
        "func run(n int) error {\n"
        "\treturn nil\n"
        "}\n"
    )

    (pkg / "a.go").write_text(solo)
    solo_ids = _ids(_extract(tmp_path), label="Run", suffix="a.go")

    (pkg / "a.go").write_text(with_sibling)
    result = _extract(tmp_path)
    exported = _ids(result, label="Run", suffix="a.go")
    unexported = _ids(result, label="run", suffix="a.go")

    assert exported == solo_ids, (
        f"adding an unexported sibling moved the exported id: {solo_ids} -> {exported}"
    )
    assert unexported and unexported != exported


def test_incremental_sibling_addition_keeps_cross_package_edge(tmp_path: Path) -> None:
    """A hook-style partial rebuild must not re-point edges from untouched files.

    Build the full corpus, then add an unexported ``run`` sibling and re-extract
    ONLY a.go (the --update path). The stored ``Start -> Run`` edge from the
    untouched app package has to keep pointing at the exported ``Run``.
    """
    from graphify.build import build_from_json, build_merge
    from graphify.export import to_json

    (tmp_path / "go.mod").write_text("module example.com/repro\n\ngo 1.22\n")
    (tmp_path / "pkga").mkdir()
    (tmp_path / "app").mkdir()
    (tmp_path / "pkga" / "a.go").write_text(
        "package pkga\n\nfunc Run() error {\n\treturn nil\n}\n"
    )
    (tmp_path / "app" / "app.go").write_text(
        'package app\n\nimport "example.com/repro/pkga"\n\n'
        "func Start() error {\n\treturn pkga.Run()\n}\n"
    )

    full = _extract(tmp_path)
    graph = build_from_json(full, root=str(tmp_path), directed=False)
    graph_path = tmp_path / "graph.json"
    to_json(graph, {i: [n] for i, n in enumerate(graph.nodes)}, str(graph_path))

    (tmp_path / "pkga" / "a.go").write_text(
        "package pkga\n"
        "\n"
        "func Run() error {\n"
        "\treturn run(1)\n"
        "}\n"
        "\n"
        "func run(n int) error {\n"
        "\treturn nil\n"
        "}\n"
    )
    partial = extract(
        [tmp_path / "pkga" / "a.go"],
        cache_root=tmp_path,
        root=tmp_path,
        parallel=False,
    )
    merged = build_merge(
        [partial], graph_path=str(graph_path), root=str(tmp_path), directed=False
    )

    # The merged graph is undirected; edge iteration order is arbitrary. The
    # build stores the real direction in _src/_tgt, so read those.
    start_targets = {
        merged.nodes[d.get("_tgt", v)].get("label")
        for u, v, d in merged.edges(data=True)
        if d.get("relation") == "calls" and "start" in str(d.get("_src", u))
    }
    assert start_targets == {"Run()"}, (
        f"cross-package edge re-pointed after partial rebuild: {start_targets}"
    )


def test_case_only_sibling_methods_are_both_extracted(tmp_path: Path) -> None:
    """Methods ``Get`` and ``get`` on the same type in one file are two symbols,
    not one — the receiver-based id path must salt the collision too (#2779)."""
    (tmp_path / "go.mod").write_text("module example.com/repro\n\ngo 1.22\n")
    pkg = tmp_path / "pkga"
    pkg.mkdir()
    (pkg / "a.go").write_text(
        "package pkga\n\n"
        "type Store struct{}\n\n"
        "func (s Store) Get() int { return s.get() }\n\n"
        "func (s Store) get() int { return 0 }\n"
    )
    result = _extract(tmp_path)
    exported = _ids(result, label="Get", suffix="a.go")
    unexported = _ids(result, label="get", suffix="a.go")
    assert len(exported) == 1, f"exported Get missing: {exported}"
    assert len(unexported) == 1, f"unexported get missing: {unexported}"
    assert exported != unexported, "Get and get collapsed onto one node id"


def test_case_only_sibling_all_exported_are_both_extracted(tmp_path: Path) -> None:
    """When no member is the unique exported one (``Run`` and ``RUN`` both start
    uppercase), each is salted so neither is dropped (#2779, all-salted branch)."""
    (tmp_path / "go.mod").write_text("module example.com/repro\n\ngo 1.22\n")
    pkg = tmp_path / "pkga"
    pkg.mkdir()
    (pkg / "a.go").write_text(
        "package pkga\n\n"
        "func Run() int { return 1 }\n\n"
        "func RUN() int { return 2 }\n"
    )
    result = _extract(tmp_path)
    run1 = _ids(result, label="Run", suffix="a.go")
    run2 = _ids(result, label="RUN", suffix="a.go")
    assert len(run1) == 1 and len(run2) == 1, f"Run={run1} RUN={run2}"
    assert run1 != run2, "Run and RUN collapsed onto one node id"
