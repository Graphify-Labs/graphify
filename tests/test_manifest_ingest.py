from __future__ import annotations

from pathlib import Path

from graphify.build import build_from_json
from graphify.detect import FileType, classify_file
from graphify.extract import extract
from graphify.manifest_ingest import (
    extract_package_manifest,
    is_package_manifest_path,
)


def _write(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


# ── routing: manifests are deterministic (CODE), not LLM documents ───────────

def test_manifests_classify_as_code_not_document(tmp_path):
    for name in ("apm.yml", "pyproject.toml", "go.mod", "pom.xml"):
        p = _write(tmp_path / name, "x")
        assert is_package_manifest_path(p)
        assert classify_file(p) is FileType.CODE, name
    # a generic yaml stays a document
    assert classify_file(_write(tmp_path / "config.yaml", "a: 1")) is FileType.DOCUMENT


# ── per-format parsing ───────────────────────────────────────────────────────

def _pkg_nodes(result):
    return [n for n in result["nodes"] if n.get("type") == "package"]


def test_apm_parses_name_and_deps(tmp_path):
    p = _write(tmp_path / "apm.yml",
               "name: my-pkg\nversion: 1.2.3\ndependencies:\n  - dep-a\n  - dep-b\n")
    r = extract_package_manifest(p)
    pkg = _pkg_nodes(r)[0]
    assert pkg["label"] == "my-pkg" and pkg["version"] == "1.2.3"
    deps = {e["target"] for e in r["edges"] if e["relation"] == "depends_on"}
    assert {"pkg_dep_a", "pkg_dep_b"} <= deps


def test_pyproject_parses_pep508_deps(tmp_path):
    p = _write(tmp_path / "pyproject.toml",
               '[project]\nname = "cool-lib"\nversion = "0.1"\n'
               'dependencies = ["requests>=2.0", "rich[jupyter]==13.0", "tomli; python_version<\'3.11\'"]\n')
    r = extract_package_manifest(p)
    assert _pkg_nodes(r)[0]["label"] == "cool-lib"
    deps = {e["target"] for e in r["edges"]}
    assert {"pkg_requests", "pkg_rich", "pkg_tomli"} <= deps  # versions/extras/markers stripped


def test_gomod_parses_module_and_requires(tmp_path):
    p = _write(tmp_path / "go.mod",
               "module example.com/me/app\n\ngo 1.22\n\nrequire (\n"
               "\tgithub.com/x/y v1.2.3\n\tgithub.com/a/b v0.4.0\n)\n")
    r = extract_package_manifest(p)
    assert _pkg_nodes(r)[0]["label"] == "example.com/me/app"
    deps = {e["target"] for e in r["edges"]}
    assert "pkg_github_com_x_y" in deps and "pkg_github_com_a_b" in deps


def test_pom_parses_artifact_and_deps(tmp_path):
    p = _write(tmp_path / "pom.xml",
               '<project xmlns="http://maven.apache.org/POM/4.0.0">\n'
               '  <groupId>com.acme</groupId>\n  <artifactId>widget</artifactId>\n  <version>2.0</version>\n'
               '  <dependencies>\n    <dependency><groupId>org.lib</groupId><artifactId>core</artifactId></dependency>\n'
               '  </dependencies>\n</project>\n')
    r = extract_package_manifest(p)
    assert _pkg_nodes(r)[0]["label"] == "com.acme:widget"
    assert any(e["target"] == "pkg_org_lib_core" for e in r["edges"])


# ── #1377: a package referenced by N manifests is ONE node ───────────────────

def test_apm_dependency_collapses_to_single_canonical_node(tmp_path):
    base = tmp_path / "packages"
    _write(base / "core/apm.yml", "name: coding-standards-core\nversion: 1.0.4\n")
    _write(base / "csharp/apm.yml",
           "name: coding-standards-csharp\ndependencies:\n  - coding-standards-core\n")
    _write(base / "python/apm.yml",
           'name: coding-standards-python\ndependencies:\n  coding-standards-core: ">=1.0"\n')
    files = sorted(base.rglob("apm.yml"))
    result = extract(files, cache_root=tmp_path)

    core = [n for n in result["nodes"]
            if n.get("type") == "package" and n["label"] == "coding-standards-core"]
    assert len(core) == 1, "core package must be a single canonical node"
    assert core[0]["id"] == "pkg_coding_standards_core" and core[0]["source_file"]

    g = build_from_json(result)
    core_ids = [n for n, d in g.nodes(data=True) if d.get("label") == "coding-standards-core"]
    dep_edges = [(u, v) for u, v, d in g.edges(data=True) if d.get("relation") == "depends_on"]
    assert len(core_ids) == 1
    assert len(dep_edges) == 2  # both dependents point at the one core node


def test_external_dependency_edge_pruned_not_orphaned(tmp_path):
    # A dep whose manifest isn't in the corpus: the edge dangles and build prunes it.
    p = _write(tmp_path / "apm.yml", "name: leaf\ndependencies:\n  - some-external-pkg\n")
    result = extract([p], cache_root=tmp_path)
    g = build_from_json(result)
    assert "pkg_some_external_pkg" not in set(g.nodes())  # no fabricated external node
    assert [n for n, d in g.nodes(data=True) if d.get("label") == "leaf"]


def test_malformed_manifest_does_not_crash(tmp_path):
    p = _write(tmp_path / "pom.xml", "<project><not closed")
    r = extract_package_manifest(p)  # parse error -> empty, no exception
    assert r["nodes"] == [] and r["edges"] == []


# ── #2434: Cargo.toml joins pyproject.toml/go.mod/pom.xml as a package manifest ─

def test_cargo_classifies_as_code_manifest(tmp_path):
    p = _write(tmp_path / "Cargo.toml", '[package]\nname = "x"\n')
    assert is_package_manifest_path(p)
    assert classify_file(p) is FileType.CODE


def test_cargo_parses_name_version_and_deps(tmp_path):
    # A crate declares its name/version under [package]; deps appear both as a
    # bare version string and as an inline table (version + features).
    p = _write(tmp_path / "Cargo.toml",
               '[package]\nname = "my-crate"\nversion = "0.3.1"\nedition = "2021"\n\n'
               '[dependencies]\nserde = "1.0"\ntokio = { version = "1", features = ["full"] }\n')
    r = extract_package_manifest(p)
    pkg = _pkg_nodes(r)[0]
    assert pkg["label"] == "my-crate" and pkg["version"] == "0.3.1"
    assert pkg["ecosystem"] == "cargo"
    deps = {e["target"] for e in r["edges"] if e["relation"] == "depends_on"}
    assert {"pkg_serde", "pkg_tokio"} <= deps  # inline-table dep keyed by name


def test_cargo_virtual_workspace_manifest_emits_no_package(tmp_path):
    # A virtual workspace root has no [package] table, so it declares no package
    # of its own — it must not fabricate a node.
    p = _write(tmp_path / "Cargo.toml", '[workspace]\nmembers = ["a", "b"]\n')
    r = extract_package_manifest(p)
    assert _pkg_nodes(r) == []


def test_cargo_target_conditional_deps_are_collected(tmp_path):
    # Platform-gated deps under [target.'cfg(...)'.dependencies] are common in
    # real crates and must not be dropped just because they are conditional.
    p = _write(tmp_path / "Cargo.toml",
               '[package]\nname = "portable"\n\n'
               '[dependencies]\nserde = "1"\n\n'
               '[target."cfg(windows)".dependencies]\nwinapi = "0.3"\n')
    r = extract_package_manifest(p)
    deps = {e["target"] for e in r["edges"] if e["relation"] == "depends_on"}
    assert {"pkg_serde", "pkg_winapi"} <= deps


def test_cargo_workspace_inherited_version_does_not_crash(tmp_path):
    # `version.workspace = true` yields a table, not a string. It must be ignored
    # (no bogus version attribute) rather than crash the parse.
    p = _write(tmp_path / "Cargo.toml",
               '[package]\nname = "member"\nversion.workspace = true\n')
    pkg = _pkg_nodes(extract_package_manifest(p))[0]
    assert pkg["label"] == "member" and "version" not in pkg


# ── #3806: inherited groupId and ${...} properties in pom.xml ────────────────

def test_pom_inherits_groupid_and_resolves_properties(tmp_path):
    _write(tmp_path / "rsc/pom.xml",
           '<project xmlns="http://maven.apache.org/POM/4.0.0">\n'
           '  <parent><groupId>org.acme</groupId><artifactId>main</artifactId><version>1.0</version></parent>\n'
           '  <groupId>org.acme</groupId>\n  <artifactId>acme-rsc</artifactId>\n</project>\n')
    _write(tmp_path / "server/pom.xml",
           '<project xmlns="http://maven.apache.org/POM/4.0.0">\n'
           '  <parent><groupId>org.acme</groupId><artifactId>main</artifactId><version>1.0</version></parent>\n'
           '  <artifactId>acme-server</artifactId>\n'
           '  <properties><core.suffix>2.12</core.suffix></properties>\n'
           '  <dependencies>\n'
           '    <dependency><groupId>${project.groupId}</groupId><artifactId>acme-rsc</artifactId></dependency>\n'
           '    <dependency><groupId>org.acme</groupId><artifactId>acme-core_${core.suffix}</artifactId></dependency>\n'
           '  </dependencies>\n</project>\n')
    _write(tmp_path / "web/pom.xml",
           '<project xmlns="http://maven.apache.org/POM/4.0.0">\n'
           '  <parent><groupId>org.acme</groupId><artifactId>main</artifactId><version>1.0</version></parent>\n'
           '  <artifactId>acme-web</artifactId>\n'
           '  <dependencies>\n'
           '    <dependency><groupId>org.acme</groupId><artifactId>acme-server</artifactId></dependency>\n'
           '  </dependencies>\n</project>\n')

    server = extract_package_manifest(tmp_path / "server/pom.xml")
    pkg = _pkg_nodes(server)[0]
    assert pkg["label"] == "org.acme:acme-server" and pkg["version"] == "1.0"
    targets = {e["target"] for e in server["edges"] if e["relation"] == "depends_on"}
    assert {"pkg_org_acme_acme_rsc", "pkg_org_acme_acme_core_2_12"} <= targets

    result = extract(sorted(tmp_path.rglob("pom.xml")), cache_root=tmp_path)
    g = build_from_json(result)
    labels = {n: d.get("label") for n, d in g.nodes(data=True)}
    dep_edges = {frozenset((labels[u], labels[v])) for u, v, d in g.edges(data=True)
                 if d.get("relation") == "depends_on"}
    assert frozenset(("org.acme:acme-server", "org.acme:acme-rsc")) in dep_edges
    assert frozenset(("org.acme:acme-web", "org.acme:acme-server")) in dep_edges
