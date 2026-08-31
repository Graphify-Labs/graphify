import pytest

from graphify.cargo_introspect import introspect_cargo


def _write_manifest(path, content):
    path.write_text(content.lstrip(), encoding="utf-8")


def test_cargo_introspect_workspace_internal_dependency_only(tmp_path):
    """Real workspace: pin raw graph fields while excluding registry-only deps."""
    # This exercises actual Cargo.toml discovery from disk, proving internal path
    # dependencies become edges while external registry packages stay out of the graph.
    _write_manifest(
        tmp_path / "Cargo.toml",
        """
[workspace]
members = ["app", "core"]
""",
    )
    app = tmp_path / "app"
    core = tmp_path / "core"
    app.mkdir()
    core.mkdir()
    _write_manifest(
        app / "Cargo.toml",
        """
[package]
name = "app"
version = "0.1.0"
edition = "2021"

[dependencies]
core = { path = "../core" }
serde = "1"
""",
    )
    _write_manifest(
        core / "Cargo.toml",
        """
[package]
name = "core"
version = "0.1.0"
edition = "2021"
""",
    )

    result = introspect_cargo(tmp_path)

    node_ids = {node["id"] for node in result["nodes"]}
    assert node_ids == {"crate:app", "crate:core"}
    assert "crate:serde" not in node_ids
    assert {
        "id": "crate:app",
        "label": "app",
        "source_file": "app/Cargo.toml",
        "source_location": "L1",
    } in result["nodes"]

    assert {
        "source": "crate:app",
        "target": "crate:core",
        "relation": "crate_depends_on",
        "context": "cargo_dependency",
        "weight": 1.0,
        "confidence": "EXTRACTED",
        "source_file": "app/Cargo.toml",
        "source_location": "L1",
    } in result["edges"]
    assert not any(
        edge["source"] == "crate:app" and edge["target"] == "crate:serde"
        for edge in result["edges"]
    )


def test_cargo_introspect_malformed_toml_reports_parser_error(tmp_path):
    """Malformed manifests surface the TOML parser failure, not an arbitrary crash."""
    # Pin the class name so this works with stdlib tomllib and Python 3.10 tomli.
    _write_manifest(
        tmp_path / "Cargo.toml",
        """
[package
name = "broken"
""",
    )

    with pytest.raises(Exception) as exc_info:
        introspect_cargo(tmp_path)

    assert exc_info.type.__name__ == "TOMLDecodeError"


def test_cargo_introspect_degenerate_manifests_return_empty_or_skip_bad_deps(tmp_path):
    """Degenerate but parseable manifests should not invent graph data or crash."""
    # Empty and nameless packages prove crate nodes require package identity; the
    # scalar dependencies case proves malformed dependency sections are ignored safely.
    empty_manifest = tmp_path / "empty"
    empty_manifest.mkdir()
    _write_manifest(empty_manifest / "Cargo.toml", "")

    empty_result = introspect_cargo(empty_manifest)

    assert empty_result["nodes"] == []
    assert empty_result["edges"] == []

    nameless_package = tmp_path / "nameless"
    nameless_package.mkdir()
    _write_manifest(
        nameless_package / "Cargo.toml",
        """
[package]
version = "0.1.0"
""",
    )

    nameless_result = introspect_cargo(nameless_package)

    assert nameless_result["nodes"] == []
    assert nameless_result["edges"] == []

    scalar_dependencies = tmp_path / "scalar-dependencies"
    scalar_dependencies.mkdir()
    _write_manifest(
        scalar_dependencies / "Cargo.toml",
        """
[package]
name = "app"
version = "0.1.0"

dependencies = "not-a-table"
""",
    )

    scalar_result = introspect_cargo(scalar_dependencies)

    assert scalar_result["nodes"] == [
        {
            "id": "crate:app",
            "label": "app",
            "source_file": "Cargo.toml",
            "source_location": "L1",
        }
    ]
    assert scalar_result["edges"] == []


def test_cargo_introspect_old_manifest_keeps_internal_path_dep_and_skips_external(tmp_path):
    """Legacy manifests still resolve path deps and ignore bare-string externals."""
    # Older Cargo files may omit modern metadata and use bare version strings; the
    # graph should keep only workspace-internal relationships.
    _write_manifest(
        tmp_path / "Cargo.toml",
        """
[workspace]
members = ["legacy", "internal"]
""",
    )
    legacy = tmp_path / "legacy"
    internal = tmp_path / "internal"
    legacy.mkdir()
    internal.mkdir()
    _write_manifest(
        legacy / "Cargo.toml",
        """
[package]
name = "legacy"
version = "0.1.0"

[dependencies]
rand = "0.8"
internal = { path = "../internal" }
""",
    )
    _write_manifest(
        internal / "Cargo.toml",
        """
[package]
name = "internal"
version = "0.1.0"
""",
    )

    result = introspect_cargo(tmp_path)

    node_ids = {node["id"] for node in result["nodes"]}
    edge_pairs = {(edge["source"], edge["target"]) for edge in result["edges"]}
    assert node_ids == {"crate:legacy", "crate:internal"}
    assert "crate:rand" not in node_ids
    assert len(result["edges"]) == 1
    assert ("crate:legacy", "crate:internal") in edge_pairs
    assert ("crate:legacy", "crate:rand") not in edge_pairs


def test_cargo_introspect_modern_virtual_and_root_package_workspaces(tmp_path):
    """Modern workspace forms cover virtual roots, workspace deps, and root packages."""
    # Virtual manifests and root-package workspaces discover members differently;
    # both must produce exact internal graph shapes without registry-only edges.
    virtual_root = tmp_path / "virtual"
    virtual_root.mkdir()
    _write_manifest(
        virtual_root / "Cargo.toml",
        """
[workspace]
members = ["crates/*"]

[workspace.dependencies]
beta = { path = "crates/beta" }
serde = "1"
""",
    )
    alpha = virtual_root / "crates" / "alpha"
    beta = virtual_root / "crates" / "beta"
    alpha.mkdir(parents=True)
    beta.mkdir(parents=True)
    _write_manifest(
        alpha / "Cargo.toml",
        """
[package]
name = "alpha"
version = "0.1.0"
edition = "2021"

[dependencies]
beta = { workspace = true }
serde = { workspace = true }
""",
    )
    _write_manifest(
        beta / "Cargo.toml",
        """
[package]
name = "beta"
version = "0.1.0"
edition = "2021"
""",
    )

    virtual_result = introspect_cargo(virtual_root)

    assert {node["id"] for node in virtual_result["nodes"]} == {
        "crate:alpha",
        "crate:beta",
    }
    assert len(virtual_result["nodes"]) == 2
    assert len(virtual_result["edges"]) == 1
    assert {
        "source": "crate:alpha",
        "target": "crate:beta",
        "relation": "crate_depends_on",
        "context": "cargo_dependency",
        "weight": 1.0,
        "confidence": "EXTRACTED",
        "source_file": "crates/alpha/Cargo.toml",
        "source_location": "L1",
    } in virtual_result["edges"]

    package_root = tmp_path / "package-root"
    package_root.mkdir()
    _write_manifest(
        package_root / "Cargo.toml",
        """
[package]
name = "root_pkg"
version = "0.1.0"
edition = "2021"

[workspace]
members = ["crates/*"]
""",
    )
    member = package_root / "crates" / "member"
    member.mkdir(parents=True)
    _write_manifest(
        member / "Cargo.toml",
        """
[package]
name = "member"
version = "0.1.0"
edition = "2021"

[dependencies]
root_pkg = { path = "../.." }
""",
    )

    package_result = introspect_cargo(package_root)

    assert {node["id"] for node in package_result["nodes"]} == {
        "crate:root_pkg",
        "crate:member",
    }
    assert len(package_result["nodes"]) == 2
    assert len(package_result["edges"]) == 1
    assert {
        "source": "crate:member",
        "target": "crate:root_pkg",
        "relation": "crate_depends_on",
        "context": "cargo_dependency",
        "weight": 1.0,
        "confidence": "EXTRACTED",
        "source_file": "crates/member/Cargo.toml",
        "source_location": "L1",
    } in package_result["edges"]


def test_cargo_introspect_large_workspace_dependency_chain(tmp_path):
    """Large deterministic workspace proves chain extraction scales by shape, not timing."""
    # The exact 200-node/199-edge chain guards against truncation, glob misses, or
    # accidental timing-based assertions that would make the test flaky.
    crate_count = 200
    _write_manifest(
        tmp_path / "Cargo.toml",
        """
[workspace]
members = ["crates/*"]
""",
    )

    for index in range(crate_count):
        crate_dir = tmp_path / "crates" / f"crate_{index:03d}"
        crate_dir.mkdir(parents=True)
        dependency_block = ""
        if index + 1 < crate_count:
            dependency_block = f"""

[dependencies]
crate_{index + 1:03d} = {{ path = "../crate_{index + 1:03d}" }}
"""
        _write_manifest(
            crate_dir / "Cargo.toml",
            f'''
[package]
name = "crate_{index:03d}"
version = "0.1.0"
edition = "2021"{dependency_block}
''',
        )

    result = introspect_cargo(tmp_path)

    assert len(result["nodes"]) == crate_count
    assert len(result["edges"]) == crate_count - 1
    assert {node["id"] for node in result["nodes"]} == {
        f"crate:crate_{index:03d}" for index in range(crate_count)
    }
    assert {
        "source": "crate:crate_000",
        "target": "crate:crate_001",
        "relation": "crate_depends_on",
        "context": "cargo_dependency",
        "weight": 1.0,
        "confidence": "EXTRACTED",
        "source_file": "crates/crate_000/Cargo.toml",
        "source_location": "L1",
    } in result["edges"]
    assert {
        "source": "crate:crate_198",
        "target": "crate:crate_199",
        "relation": "crate_depends_on",
        "context": "cargo_dependency",
        "weight": 1.0,
        "confidence": "EXTRACTED",
        "source_file": "crates/crate_198/Cargo.toml",
        "source_location": "L1",
    } in result["edges"]


def test_cargo_introspect_honors_package_rename_on_internal_dep(tmp_path):
    """Renamed workspace-internal deps still produce a `crate_depends_on` edge (#1858).

    Cargo's `package = "..."` inside a dep table entry lets the key used in
    `use db::…;` differ from the crate's real `[package].name`. Looking up
    `crates` by the raw dep-table key misses the rename and silently drops
    the edge.
    """
    _write_manifest(
        tmp_path / "Cargo.toml",
        """
[workspace]
members = ["app", "storage"]
""",
    )
    app = tmp_path / "app"
    storage = tmp_path / "storage"
    app.mkdir()
    storage.mkdir()
    _write_manifest(
        app / "Cargo.toml",
        """
[package]
name = "app"
version = "0.1.0"
edition = "2021"

[dependencies]
db = { path = "../storage", package = "internal-storage" }
""",
    )
    _write_manifest(
        storage / "Cargo.toml",
        """
[package]
name = "internal-storage"
version = "0.1.0"
edition = "2021"
""",
    )

    result = introspect_cargo(tmp_path)

    node_ids = {node["id"] for node in result["nodes"]}
    assert node_ids == {"crate:app", "crate:internal-storage"}
    assert {
        "source": "crate:app",
        "target": "crate:internal-storage",
        "relation": "crate_depends_on",
        "context": "cargo_dependency",
        "weight": 1.0,
        "confidence": "EXTRACTED",
        "source_file": "app/Cargo.toml",
        "source_location": "L1",
    } in result["edges"]


def test_cargo_introspect_package_rename_falls_through_when_unresolved(tmp_path):
    """A rename pointing at an external (non-workspace) crate stays a no-op.

    Guards against the fix silently emitting edges to registry crates: the
    resolved name still has to appear in `crates` (the workspace-internal
    index) for an edge to be produced.
    """
    _write_manifest(
        tmp_path / "Cargo.toml",
        """
[workspace]
members = ["app"]
""",
    )
    app = tmp_path / "app"
    app.mkdir()
    _write_manifest(
        app / "Cargo.toml",
        """
[package]
name = "app"
version = "0.1.0"
edition = "2021"

[dependencies]
tokio_rt = { version = "1", package = "tokio" }
""",
    )

    result = introspect_cargo(tmp_path)

    assert {node["id"] for node in result["nodes"]} == {"crate:app"}
    assert result["edges"] == []
