"""Deterministic package-manifest ingestion (#1377).

Package manifests (``apm.yml``, ``pyproject.toml``, ``Cargo.toml``, ``go.mod``,
``pom.xml``) declare a package and its dependencies. Left to the LLM document path, the same
package gets a different file-anchored node id from its own manifest than from
each dependent's dependency reference, so it splits into duplicate nodes. This
module parses manifests deterministically and emits ONE canonical package node
per package -- keyed by NAME via :func:`graphify.ids.make_id` -- plus
``depends_on`` edges, so a package referenced from N manifests collapses to a
single hub node (the dependency stub and the package's own definition node share
the canonical id and merge at build time).

Mirrors ``mcp_ingest``: recognized by filename, routed to the deterministic AST
path (never the LLM), so a manifest is extracted exactly once.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from graphify.ids import make_id

__all__ = ["is_package_manifest_path", "extract_package_manifest", "PACKAGE_MANIFEST_NAMES"]

# manifest filename (lowercased) -> ecosystem tag
PACKAGE_MANIFEST_NAMES: dict[str, str] = {
    "apm.yml": "apm",
    "apm.yaml": "apm",
    "pyproject.toml": "python",
    "cargo.toml": "cargo",
    "go.mod": "go",
    "pom.xml": "maven",
}

_MAX_MANIFEST_BYTES = 2_000_000  # 2 MB cap — manifests are small; this rejects junk

_TOMLI_REQUIRED = (
    "Package-manifest ingestion on Python < 3.11 needs tomli. "
    "Install with: pip install 'tomli' "
    "(or reinstall graphifyy, which declares tomli for python_version < '3.11')."
)


def _load_toml_module():
    """Return a tomllib-compatible module, or raise ImportError (#3283).

    Returning ``None`` used to look identical to a virtual workspace root with
    nothing to emit, so missing ``tomli`` on Python 3.10 silently dropped every
    ``Cargo.toml`` / ``pyproject.toml``. Raise instead: the caller
    (``extract_package_manifest``) surfaces this as a visible per-manifest error
    rather than dropping the file silently. In practice the runtime ``tomli``
    dependency (python_version < '3.11') keeps this path unreachable for a
    standard install.
    """
    try:
        import tomllib as _toml  # type: ignore[import-not-found]

        return _toml
    except ImportError:
        try:
            import tomli as _toml  # type: ignore[import-not-found,no-redef]

            return _toml
        except ImportError as exc:
            raise ImportError(_TOMLI_REQUIRED) from exc


def is_package_manifest_path(path: Path) -> bool:
    """True if ``path`` is a recognized package manifest (by filename)."""
    return path.name.lower() in PACKAGE_MANIFEST_NAMES


def _pkg_id(name: str) -> str:
    """Canonical package node id, keyed by package NAME so every reference to the
    same package -- its own manifest and any dependent's dependency line -- maps
    to one node."""
    return make_id("pkg", name)


def extract_package_manifest(path: Path) -> dict[str, Any]:
    """Parse a package manifest into a canonical package node + ``depends_on`` edges."""
    try:
        if path.stat().st_size > _MAX_MANIFEST_BYTES:
            return {"nodes": [], "edges": [], "error": "manifest too large to index"}
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"nodes": [], "edges": [], "error": f"manifest read error: {exc}"}

    eco = PACKAGE_MANIFEST_NAMES[path.name.lower()]
    try:
        if eco == "maven":
            info = _PARSERS[eco](text, path)
        else:
            info = _PARSERS[eco](text)
    except Exception as exc:  # noqa: BLE001 — a malformed manifest must not abort extraction
        return {"nodes": [], "edges": [], "error": f"manifest parse error: {exc}"}
    if not info or not info.get("name"):
        return {"nodes": [], "edges": []}

    name = info["name"]
    str_path = str(path)
    pkg_nid = _pkg_id(name)
    node: dict[str, Any] = {
        "id": pkg_nid,
        "label": name,
        "file_type": "code",  # valid schema type; `type` distinguishes packages
        "type": "package",
        "ecosystem": eco,
        "source_file": str_path,
        "source_location": "L1",
    }
    if info.get("version"):
        node["version"] = info["version"]
    nodes: list[dict] = [node]
    edges: list[dict] = []

    seen: set[str] = set()
    for dep in info.get("deps", []):
        if not dep:
            continue
        dep_nid = _pkg_id(dep)
        if dep_nid == pkg_nid or dep_nid in seen:
            continue
        seen.add(dep_nid)
        # The edge targets the dependency's canonical package id. If that package's
        # own manifest is in the corpus, the edge resolves to its (single) node; if
        # the dependency is external, build_from_json prunes the dangling edge. We
        # deliberately do NOT emit a stub node — a stub with an empty source_file
        # would risk clobbering the real node's source_file under id-dedup.
        edges.append(
            {
                "source": pkg_nid,
                "target": dep_nid,
                "relation": "depends_on",
                "context": "dependency",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": str_path,
                "source_location": "L1",
                "weight": 1.0,
            }
        )
    return {"nodes": nodes, "edges": edges}


# ── per-ecosystem parsers: text -> {"name", "version"?, "deps": [str]} | None ──


def _coerce_deps(value: Any) -> list[str]:
    """A dependency block may be a list of names or a name->spec map."""
    if isinstance(value, dict):
        return [str(k) for k in value]
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict) and item:
                out.append(str(next(iter(item))))
        return out
    return []


def _parse_apm(text: str) -> dict | None:
    try:
        import yaml
    except ImportError:
        return _parse_apm_fallback(text)
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        return None
    return {
        "name": data.get("name"),
        "version": data.get("version"),
        "deps": _coerce_deps(data.get("dependencies")),
    }


def _parse_apm_fallback(text: str) -> dict | None:
    """Minimal line parser for apm.yml when PyYAML is unavailable: a top-level
    ``name:``/``version:`` plus a simple ``dependencies:`` block (list items or
    a name map)."""
    name = None
    version = None
    deps: list[str] = []
    in_deps = False
    for line in text.splitlines():
        if not in_deps:
            m = re.match(r'^name:\s*["\']?([^"\'\s#]+)', line)
            if m:
                name = m.group(1)
                continue
            # `version` is part of the manifest contract the YAML path already
            # returns; dropping it here made a package node lose its version
            # on every machine without PyYAML installed.
            m = re.match(r'^version:\s*["\']?([^"\'\s#]+)', line)
            if m:
                version = m.group(1)
                continue
        if re.match(r"^dependencies:\s*$", line):
            in_deps = True
            continue
        if in_deps:
            dm = re.match(r'^\s*-\s*["\']?([^"\'\s#:]+)', line) or re.match(
                r"^\s{2,}([A-Za-z0-9._/@-]+)\s*:", line
            )
            if dm:
                deps.append(dm.group(1))
            elif re.match(r"^\S", line):  # next top-level key ends the block
                in_deps = False
    return {"name": name, "version": version, "deps": deps} if name else None


def _pep508_name(spec: str) -> str:
    """`requests>=2.0` -> `requests`; `pkg[extra]==1; python_version<'3.9'` -> `pkg`."""
    return re.split(r"[\s<>=!~;\[\(]", spec.strip(), maxsplit=1)[0]


def _parse_pyproject(text: str) -> dict | None:
    _toml = _load_toml_module()
    data = _toml.loads(text)
    proj = data.get("project", {}) if isinstance(data.get("project"), dict) else {}
    poetry = (
        (data.get("tool", {}) or {}).get("poetry", {}) if isinstance(data.get("tool"), dict) else {}
    )
    name = proj.get("name") or (poetry.get("name") if isinstance(poetry, dict) else None)
    if not name:
        return None
    deps: list[str] = [
        _pep508_name(s) for s in (proj.get("dependencies") or []) if isinstance(s, str)
    ]
    if isinstance(poetry, dict):
        for dep in poetry.get("dependencies") or {}:
            if str(dep).lower() != "python":
                deps.append(str(dep))
    return {
        "name": name,
        "version": proj.get("version")
        or (poetry.get("version") if isinstance(poetry, dict) else None),
        "deps": deps,
    }


def _parse_cargo(text: str) -> dict | None:
    """Cargo.toml: name/version from ``[package]``, runtime deps from
    ``[dependencies]`` plus every ``[target.<cfg>.dependencies]`` table (mirrors
    ``_parse_pyproject``'s runtime-only scope; dev-/build-dependencies excluded)."""
    _toml = _load_toml_module()
    data = _toml.loads(text)
    pkg = data.get("package", {}) if isinstance(data.get("package"), dict) else {}
    name = pkg.get("name")
    # A virtual workspace root (``[workspace]``, no ``[package]``) declares no
    # package of its own — emit nothing rather than a fabricated node. ``name`` is
    # never workspace-inheritable in Cargo, but guard on the type anyway.
    if not isinstance(name, str) or not name:
        return None
    # ``version`` may be workspace-inherited (``version.workspace = true``), which
    # parses to a table; keep only a concrete string version.
    version = pkg.get("version")
    if not isinstance(version, str):
        version = None
    # A dependency value is a bare version string or an inline table; either way
    # _coerce_deps keys it by the dependency NAME (the table/map key).
    deps = _coerce_deps(data.get("dependencies"))
    # Platform-conditional deps live under ``[target.<cfg>.dependencies]``; fold
    # them in so a crate whose deps are entirely cfg-gated still emits its edges.
    targets = data.get("target")
    if isinstance(targets, dict):
        for cfg in targets.values():
            if isinstance(cfg, dict):
                deps += _coerce_deps(cfg.get("dependencies"))
    return {"name": name, "version": version, "deps": deps}


def _parse_gomod(text: str) -> dict | None:
    name = None
    deps: list[str] = []
    in_block = False
    for line in text.splitlines():
        s = line.strip()
        if name is None:
            m = re.match(r"^module\s+(\S+)", s)
            if m:
                name = m.group(1)
                continue
        if re.match(r"^require\s*\(", s):
            in_block = True
            continue
        if in_block:
            if s.startswith(")"):
                in_block = False
                continue
            dm = re.match(r"^(\S+)\s+v\S+", s)
            if dm:
                deps.append(dm.group(1))
        else:
            dm = re.match(r"^require\s+(\S+)\s+v\S+", s)
            if dm:
                deps.append(dm.group(1))
    return {"name": name, "version": None, "deps": deps} if name else None


def _parse_pom(text: str, pom: Path | None = None) -> dict | None:
    root = _pom_root(text)
    aid = root.findtext("artifactId")
    gid = root.findtext("groupId") or root.findtext("parent/groupId")
    version = root.findtext("version") or root.findtext("parent/version")
    if not aid:
        return None
    # Ancestor properties first, so this POM's own <properties> override them.
    props: dict[str, str] = _inherited_pom_properties(pom, root) if pom is not None else {}
    for prop in root.findall("properties/*"):
        if isinstance(prop.tag, str) and prop.text:
            props[prop.tag] = prop.text.strip()
    # A module may name itself with an inherited property; resolve it so
    # dependents referencing the same literal match.
    aid = _expand(aid, props)
    for key, value in (
        ("project.groupId", gid),
        ("project.artifactId", aid),
        ("project.version", version),
        ("project.parent.groupId", root.findtext("parent/groupId")),
        ("project.parent.version", root.findtext("parent/version")),
    ):
        if value:
            props.setdefault(key, value.strip())

    gid = _expand(gid, props)
    version = _expand(version, props)
    name = f"{gid}:{aid}" if gid else aid
    deps: list[str] = []
    for dep in root.findall(".//dependencies/dependency"):
        da = _expand(dep.findtext("artifactId"), props)
        dg = _expand(dep.findtext("groupId"), props)
        if da:
            deps.append(f"{dg}:{da}" if dg else da)
    return {"name": name, "version": version, "deps": deps}


# ── pom.xml: parent-chain property inheritance ────────────────────────────────

# Bounds the <parent> chain walk; real chains are a few levels deep.
_MAX_POM_ANCESTORS = 32


def _pom_root(text: str) -> ET.Element:
    """Parse a POM's ``<project>`` element, dropping the default namespace so
    findtext/findall don't need the ``{uri}`` prefix."""
    return ET.fromstring(re.sub(r'\sxmlns="[^"]*"', "", text, count=1))


def _expand(value: str | None, props: dict[str, str]) -> str | None:
    """Substitute ``${...}`` from ``props``; unknown keys are left literal."""
    if not value:
        return value
    return re.sub(r"\$\{([^}]+)\}", lambda m: props.get(m.group(1), m.group(0)), value.strip())


def _parent_pom_path(pom: Path, root: ET.Element) -> Path | None:
    """Parent POM location per Maven's ``<relativePath>`` rule (default
    ``../pom.xml``); ``None`` for ``<relativePath/>`` (repository parent) or
    an absolute path outside the POM's repository."""
    parent = root.find("parent")
    if parent is None:
        return None
    rel = parent.findtext("relativePath")
    if rel is not None and not rel.strip():
        return None
    path = pom.parent / (rel.strip() if rel else "../pom.xml")
    if path.is_absolute():
        from graphify.detect import _find_vcs_root

        vcs_root = _find_vcs_root(pom)
        if vcs_root is not None and not path.resolve().is_relative_to(vcs_root):
            return None
    return path


def _inherited_pom_properties(pom: Path, root: ET.Element) -> dict[str, str]:
    """``<properties>`` declared by ``pom``'s ancestors, outermost first.

    The chain stops at the first ancestor that isn't on disk (a parent like
    ``org.apache:apache`` lives in the repository, not the tree).
    """
    levels: list[dict[str, str]] = []
    seen: set[Path] = {pom.resolve()}
    cur_pom, cur_root = pom, root
    while len(seen) <= _MAX_POM_ANCESTORS:
        parent_el = cur_root.find("parent")
        if parent_el is None:
            break
        parent_pom = _parent_pom_path(cur_pom, cur_root)
        if parent_pom is None:
            break
        parent_pom = parent_pom.resolve()
        if parent_pom in seen or not parent_pom.is_file():
            break
        seen.add(parent_pom)
        try:
            if parent_pom.stat().st_size > _MAX_MANIFEST_BYTES:
                break
            cur_root = _pom_root(parent_pom.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ET.ParseError):
            break
        # Inherit only from the declared parent, not any file at that path.
        if any(
            (want := parent_el.findtext(tag))
            and (have := cur_root.findtext(tag) or cur_root.findtext(f"parent/{tag}"))
            and want.strip() != have.strip()
            for tag in ("groupId", "artifactId", "version")
        ):
            break
        cur_pom = parent_pom
        levels.append(
            {
                p.tag: p.text.strip()
                for p in cur_root.findall("properties/*")
                if isinstance(p.tag, str) and p.text
            }
        )
    # Merge outermost-first so each level can reference its parent's properties.
    props: dict[str, str] = {}
    for level in reversed(levels):
        for key, value in level.items():
            props[key] = _expand(value, props) or value
    return props


_PARSERS = {
    "apm": _parse_apm,
    "python": _parse_pyproject,
    "cargo": _parse_cargo,
    "go": _parse_gomod,
    "maven": _parse_pom,
}
