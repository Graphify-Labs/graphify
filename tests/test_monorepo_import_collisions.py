"""Cross-project name-collision fixes for monorepos (#3237).

Two mechanisms produced confident (EXTRACTED) edges between unrelated projects
that merely share a name:

1. JVM/Android platform imports (``import java.util.UUID``,
   ``import android.graphics.Color``) emitted a bare last-segment target id.
   That id could byte-collide with an unrelated node that collapses to the
   same ``_make_id`` (npm's ``uuid`` dependency entry in another project's
   package.json), or ride build.py's pre-migration alias index onto whichever
   unrelated same-stem file uniquely claims the stem (another project's
   ``ui/theme/Color.kt``).

2. package.json dependency entries minted a global bare target node per
   package name, so two projects that independently install the same npm
   package were joined through it.

The fix applies the "ref" external namespace (J-4 / #1638 convention) to both
sites, and models a registry package as a single shared ``type="module"``
anchor node.
"""

import json

import pytest

from graphify.build import build
from graphify.extract import extract


def _extract_and_build(td, files):
    r = extract(files, cache_root=td)
    G = build([{"nodes": r["nodes"], "edges": r["edges"]}], root=str(td))
    return r, G


def _write(base, rel, text):
    p = base / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


KOTLIN_PLATFORM_UUID = (
    "package com.b.service\n\n"
    "import java.util.UUID\n\n"
    "class Service {\n"
    "    fun newId(): String = UUID.randomUUID().toString()\n"
    "}\n"
)

PACKAGE_JSON_WITH_UUID = json.dumps(
    {"name": "proj-a", "version": "1.0.0", "dependencies": {"uuid": "^9.0.0"}}
)


def test_platform_import_does_not_bind_to_npm_dependency_node(tmp_path, monkeypatch):
    """`import java.util.UUID` must not edge into another project's package.json.

    The Kotlin import's bare target id (`uuid`) used to byte-collide with the
    npm dependency node minted from an unrelated project's manifest.
    """
    monkeypatch.chdir(tmp_path)
    _write(tmp_path, "projA/package.json", PACKAGE_JSON_WITH_UUID)
    _write(tmp_path, "projB/src/Service.kt", KOTLIN_PLATFORM_UUID)

    _, G = _extract_and_build(
        tmp_path,
        [tmp_path / "projA/package.json", tmp_path / "projB/src/Service.kt"],
    )

    kotlin_sourced = {
        n for n, a in G.nodes(data=True)
        if str(a.get("source_file", "")).endswith(".kt")
    }
    manifest_sourced = {
        n for n, a in G.nodes(data=True)
        if str(a.get("source_file", "")).endswith("package.json")
    }
    crossing = [
        (u, v) for u, v in G.edges()
        if (u in kotlin_sourced and v in manifest_sourced)
        or (v in kotlin_sourced and u in manifest_sourced)
    ]
    assert crossing == [], (
        f"platform import bound across projects: {crossing}"
    )


def test_platform_import_does_not_ride_alias_onto_unrelated_file(tmp_path, monkeypatch):
    """`import android.graphics.Color` must not bind to another project's Color.kt.

    The bare `color` target used to ride build.py's pre-migration alias index
    onto the unrelated file node that uniquely claims the `color` stem.
    """
    monkeypatch.chdir(tmp_path)
    _write(
        tmp_path, "projA/app/Painter.kt",
        "package com.a.app\n\n"
        "import android.graphics.Color\n\n"
        "class Painter {\n"
        "    fun tint(): Int = Color.parseColor(\"#ff0000\")\n"
        "}\n",
    )
    _write(
        tmp_path, "projB/ui/theme/Color.kt",
        "package com.b.theme\n\n"
        "object Color {\n"
        "    val Primary: Long = 0xFF6200EE\n"
        "}\n",
    )

    _, G = _extract_and_build(
        tmp_path,
        [tmp_path / "projA/app/Painter.kt", tmp_path / "projB/ui/theme/Color.kt"],
    )

    painter_edges = [
        (u, v, a) for u, v, a in G.edges(data=True)
        if str(a.get("source_file", "")).endswith("Painter.kt")
        and a.get("relation") == "imports"
    ]
    assert painter_edges == [], (
        f"platform import survived into the built graph: {painter_edges}"
    )


def test_repo_local_kotlin_import_still_resolves(tmp_path, monkeypatch):
    """Control: a repo-local FQN import keeps resolving to the real node (#2526)."""
    monkeypatch.chdir(tmp_path)
    _write(
        tmp_path, "projA/app/Painter.kt",
        "package com.a.app\n\n"
        "import com.b.theme.Color\n\n"
        "class Painter {\n"
        "    fun tint(): Long = 1L\n"
        "}\n",
    )
    _write(
        tmp_path, "projB/ui/theme/Color.kt",
        "package com.b.theme\n\n"
        "object Color {\n"
        "    val Primary: Long = 0xFF6200EE\n"
        "}\n",
    )

    _, G = _extract_and_build(
        tmp_path,
        [tmp_path / "projA/app/Painter.kt", tmp_path / "projB/ui/theme/Color.kt"],
    )

    resolved = [
        (u, v) for u, v, a in G.edges(data=True)
        if a.get("relation") == "imports"
        and str(a.get("source_file", "")).endswith("Painter.kt")
        and any(n.startswith("projb_ui_theme_color") for n in (u, v))
    ]
    assert resolved, "repo-local Kotlin import no longer resolves (#2526 regression)"


def test_java_platform_import_emits_ref_namespaced_target(tmp_path, monkeypatch):
    """A .java platform import gets a non-collidable `ref_` target, a repo-shaped
    one keeps the bare stem for downstream resolution."""
    monkeypatch.chdir(tmp_path)
    f = _write(
        tmp_path, "src/Service.java",
        "package com.b.service;\n\n"
        "import java.util.UUID;\n"
        "import com.b.util.Helper;\n\n"
        "public class Service {\n"
        "    public String newId() { return UUID.randomUUID().toString(); }\n"
        "}\n",
    )
    r = extract([f], cache_root=tmp_path)
    targets = {
        e["target"] for e in r["edges"] if e.get("relation") == "imports"
    }
    assert "uuid" not in targets, "platform import still emits a bare collidable id"
    assert any(t.startswith("ref_java_util_uuid") for t in targets), targets
    assert "helper" in targets, "repo-shaped import lost its resolvable bare stem"


def test_kotlin_platform_import_emits_ref_namespaced_target(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    f = _write(
        tmp_path, "src/Service.kt",
        "package com.b.service\n\n"
        "import java.util.UUID\n"
        "import androidx.compose.material3.Typography\n"
        "import com.b.util.Helper\n\n"
        "class Service {\n"
        "    fun newId(): String = UUID.randomUUID().toString()\n"
        "}\n",
    )
    r = extract([f], cache_root=tmp_path)
    targets = {
        e["target"] for e in r["edges"] if e.get("relation") == "imports"
    }
    assert "uuid" not in targets and "typography" not in targets, targets
    assert any(t.startswith("ref_java_util_uuid") for t in targets), targets
    assert any(t.startswith("ref_androidx_compose") for t in targets), targets
    assert "helper" in targets, "repo-shaped import lost its resolvable bare stem"


def test_shared_dependency_joins_manifests_through_one_module_node(tmp_path, monkeypatch):
    """Two projects installing the same npm package share ONE `type=module` ref
    node instead of edging one project's declaration into the other's."""
    monkeypatch.chdir(tmp_path)
    _write(tmp_path, "projA/package.json", json.dumps(
        {"name": "proj-a", "dependencies": {"typescript": "^5.2.4"}}))
    _write(tmp_path, "projC/package.json", json.dumps(
        {"name": "proj-c", "dependencies": {"typescript": "6.0.8"}}))

    r, G = _extract_and_build(
        tmp_path,
        [tmp_path / "projA/package.json", tmp_path / "projC/package.json"],
    )

    ref_nodes = [n for n in G.nodes() if n.startswith("ref_typescript")]
    assert len(ref_nodes) == 1, f"expected one shared registry node, got {ref_nodes}"
    ref = ref_nodes[0]
    assert G.nodes[ref].get("type") == "module"

    entry_nodes = {
        n for n, a in G.nodes(data=True)
        if a.get("label") == "typescript" and n != ref
    }
    # Both manifests' entries reach the shared node...
    for entry in entry_nodes:
        assert G.has_edge(entry, ref), f"{entry} not wired to the shared node"
    # ...and no edge joins the two projects' entries directly.
    proj_of = {
        n: str(G.nodes[n].get("source_file", "")).split("/")[0] for n in entry_nodes
    }
    direct = [
        (u, v) for u, v in G.edges()
        if u in entry_nodes and v in entry_nodes and proj_of[u] != proj_of[v]
    ]
    assert direct == [], f"projects still joined directly: {direct}"


def test_js_bare_specifier_binds_to_manifest_dependency(tmp_path, monkeypatch):
    """`import ... from "uuid"` already targets _make_id("ref", "uuid") (#2457);
    with the dependency node in the same namespace the code→manifest link binds."""
    monkeypatch.chdir(tmp_path)
    _write(tmp_path, "package.json", PACKAGE_JSON_WITH_UUID)
    _write(tmp_path, "main.ts", 'import { v4 } from "uuid";\nexport const x = v4();\n')

    _, G = _extract_and_build(
        tmp_path, [tmp_path / "package.json", tmp_path / "main.ts"]
    )

    bind = [
        (u, v) for u, v, a in G.edges(data=True)
        if a.get("relation") == "imports_from"
        and str(a.get("source_file", "")).endswith("main.ts")
        and ("ref_uuid" in (u, v))
    ]
    assert bind, "TS npm import no longer binds to the manifest dependency node"
