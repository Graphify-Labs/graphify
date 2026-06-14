"""Cargo manifest introspection for workspace-internal crate dependencies."""

from __future__ import annotations

from pathlib import Path
from typing import Any


_CONFIDENCE_EXTRACTED = "EXTRACTED"


def _load_toml(path: Path) -> dict[str, Any]:
    try:
        import tomllib  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        try:
            import tomli as tomllib  # type: ignore[import-not-found,no-redef]
        except ModuleNotFoundError:
            raise ImportError(
                "--cargo on Python 3.10 needs tomli. Install with: pip install tomli"
            ) from None

    with path.open("rb") as manifest:
        return tomllib.load(manifest)


def _member_manifest_paths(root: Path, root_data: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    if isinstance(root_data.get("package"), dict):
        paths.append(root / "Cargo.toml")

    workspace = root_data.get("workspace")
    members = workspace.get("members", []) if isinstance(workspace, dict) else []
    if not isinstance(members, list):
        return paths

    for pattern in members:
        if not isinstance(pattern, str):
            continue
        for member in sorted(root.glob(pattern)):
            manifest = member / "Cargo.toml"
            if manifest.is_file() and manifest not in paths:
                paths.append(manifest)
    return paths


def introspect_cargo(root: str | Path) -> dict[str, Any]:
    """Return crate nodes and internal dependency edges from Cargo manifests."""
    root_path = Path(root).resolve()
    root_manifest = root_path / "Cargo.toml"
    root_data = _load_toml(root_manifest)

    manifests = _member_manifest_paths(root_path, root_data)
    crates: dict[str, tuple[str, Path, dict[str, Any]]] = {}

    for manifest in manifests:
        data = root_data if manifest == root_manifest else _load_toml(manifest)
        package = data.get("package")
        if not isinstance(package, dict):
            continue
        name = package.get("name")
        if isinstance(name, str):
            crates[name] = (f"crate:{name}", manifest, data)

    nodes = [
        {
            "id": crate_id,
            "label": name,
            "source_file": manifest.relative_to(root_path).as_posix(),
            "source_location": "L1",
        }
        for name, (crate_id, manifest, _data) in sorted(crates.items())
    ]

    edges: list[dict[str, Any]] = []
    for source_name, (source_id, manifest, data) in sorted(crates.items()):
        dependencies = data.get("dependencies", {})
        if not isinstance(dependencies, dict):
            continue
        source_file = manifest.relative_to(root_path).as_posix()
        for dependency_name in sorted(dependencies):
            target = crates.get(dependency_name)
            if target is None:
                continue
            edges.append(
                {
                    "source": source_id,
                    "target": target[0],
                    "relation": "crate_depends_on",
                    "context": "cargo_dependency",
                    "weight": 1.0,
                    "confidence": _CONFIDENCE_EXTRACTED,
                    "source_file": source_file,
                    "source_location": "L1",
                }
            )

    return {"nodes": nodes, "edges": edges}
