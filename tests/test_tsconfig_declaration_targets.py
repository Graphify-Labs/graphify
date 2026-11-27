"""#5223: tsconfig `extends` and `paths` declarations point at scanned files."""
import pytest
from graphify.extract import collect_files, extract
from graphify.build import build_from_json


def _edges(tmp_path, files):
    root = tmp_path / "repo"
    for name, text in files.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    data = extract(collect_files(root, root=root), root=root,
                   cache_root=tmp_path / "cache", parallel=False)
    g = build_from_json(data, root=root, dedup=False)
    # The graph is undirected; build keeps each edge's direction in _src/_tgt.
    out = set()
    for u, v, e in g.edges(data=True):
        if e.get("relation") == "contains":
            continue
        a, b = e.get("_src", u), e.get("_tgt", v)
        out.add((g.nodes[a].get("source_file"), e["relation"],
                 g.nodes[b].get("source_file"), g.nodes[b].get("file_type")))
    return out


TS = "export const a = 1;"
BASE = '{"compilerOptions":{"strict":true}}'  # a real base config, so it is scanned


@pytest.mark.parametrize("files, citing, target", [
    ({"a/tsconfig.json": "{}", "a/tsconfig.build.json": '{"extends":"./tsconfig.json"}',
      "b/tsconfig.json": "{}", "b/tsconfig.build.json": '{"extends":"./tsconfig.json"}'},
     "a/tsconfig.build.json", "a/tsconfig.json"),
    ({"base.json": BASE, "tsconfig.json": '{"extends":["./base.json"]}'},
     "tsconfig.json", "base.json"),
    ({"tsconfig.base.json": BASE, "tsconfig.json": '{"extends":"./tsconfig.base"}'},
     "tsconfig.json", "tsconfig.base.json"),
    ({"tsconfig.base.json": BASE, "pkg/tsconfig.json": '{"extends":"../tsconfig.base.json"}'},
     "pkg/tsconfig.json", "tsconfig.base.json"),
    ({"a/tsconfig.json": "{}", "a/tsconfig.build.json": '{\n// c\n"extends":"./tsconfig.json",\n}'},
     "a/tsconfig.build.json", "a/tsconfig.json"),
], ids=["string", "array", "no-suffix", "parent-dir", "jsonc"])
def test_local_extends_points_at_the_real_config(tmp_path, files, citing, target):
    assert (citing, "extends", target, "code") in _edges(tmp_path, files)


@pytest.mark.parametrize("value", ["@tsconfig/node18/tsconfig.json", "./missing.json"])
def test_external_or_missing_extends_keeps_its_stub(tmp_path, value):
    edges = _edges(tmp_path, {"tsconfig.json": f'{{"extends":"{value}"}}'})
    assert [e for e in edges if e[1] == "extends"] == [
        ("tsconfig.json", "extends", "tsconfig.json", "concept")]


@pytest.mark.parametrize("config, target", [
    ('{"compilerOptions":{"baseUrl":".","paths":{"@demo":["src/index.ts"]}}}', "src/index.ts"),
    ('{"compilerOptions":{"paths":{"@demo":["./src/index.ts"]}}}', "src/index.ts"),
    ('{"compilerOptions":{"baseUrl":"./src","paths":{"@demo":["index.ts"]}}}', "src/index.ts"),
    ('{"compilerOptions":{"paths":{"@demo":["gone.ts","src/index.ts"]}}}', "src/index.ts"),
    ('{"compilerOptions":{"paths":{"@demo":["src/index"]}}}', "src/index.ts"),
], ids=["repro", "no-baseurl", "baseurl-subdir", "fallback", "extensionless"])
def test_exact_paths_alias_references_its_file(tmp_path, config, target):
    edges = _edges(tmp_path, {"tsconfig.json": config, "src/index.ts": TS})
    assert ("tsconfig.json", "references", target, "code") in edges


@pytest.mark.parametrize("config", [
    '{"compilerOptions":{"paths":{"@/*":["src/*"]}}}',
    '{"compilerOptions":{"paths":{"@demo":["gone.ts"]}}}',
], ids=["wildcard", "missing"])
def test_wildcard_or_missing_paths_target_gets_no_edge(tmp_path, config):
    edges = _edges(tmp_path, {"tsconfig.json": config, "src/index.ts": TS})
    assert not [e for e in edges if e[1] == "references"]


def test_paths_use_baseurl_inherited_through_extends(tmp_path):
    """tsc resolves `paths` against an inherited baseUrl, so x.ts at the root is wrong."""
    edges = _edges(tmp_path, {
        "base/tsconfig.json": '{"compilerOptions":{"baseUrl":"../lib"}}',
        "tsconfig.json": '{"extends":"./base/tsconfig.json","compilerOptions":{"paths":{"@d":["x.ts"]}}}',
        "lib/x.ts": TS, "x.ts": TS})
    # tsc 5.9.3 resolves `@d` here to lib/x.ts (checked with --traceResolution).
    assert {e for e in edges if e[1] == "references"} == {
        ("tsconfig.json", "references", "lib/x.ts", "code")}
