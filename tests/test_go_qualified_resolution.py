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
