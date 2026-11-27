"""Resolver-only edits must refresh unchanged JS/TS importers on extract."""

import json

import pytest

import graphify.__main__ as mainmod
from graphify import extract as extract_mod


@pytest.fixture
def typescript_project(tmp_path, monkeypatch):
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setenv("GRAPHIFY_MAX_WORKERS", "1")
    root = tmp_path / "source"
    root.mkdir()
    for name in ("alpha", "beta"):
        (root / f"{name}.ts").write_text(
            f'export function read() {{ return "{name}"; }}\n', encoding="utf-8"
        )
    (root / "caller.ts").write_text(
        'import { read } from "@ports";\nexport const acquire = () => read();\n',
        encoding="utf-8",
    )
    (root / "tsconfig.json").write_text(
        '{"extends":"./tsconfig.base.json"}', encoding="utf-8"
    )
    return root


def _point_to(root, target):
    (root / "tsconfig.base.json").write_text(
        json.dumps({"compilerOptions": {"baseUrl": ".", "paths": {"@ports": [f"./{target}.ts"]}}}),
        encoding="utf-8",
    )


def _run(monkeypatch, root, out, *, raw, extra=()):
    args = ["graphify", "extract", str(root), "--code-only", "--out", str(out), *extra]
    if raw:
        args.append("--no-cluster")
    monkeypatch.setattr(mainmod.sys, "argv", args)
    try:
        mainmod.main()
    except SystemExit as exc:
        assert exc.code in (None, 0)
    return json.loads((out / "graphify-out" / "graph.json").read_text(encoding="utf-8"))


def _local_caller_edges(graph, caller="caller.ts"):
    source_files = {node["id"]: node.get("source_file") for node in graph["nodes"]}
    return {
        (edge["relation"], source_files.get(edge["target"]))
        for edge in graph.get("links", graph.get("edges", []))
        if edge.get("source_file") == caller
        and edge["relation"] in {"imports_from", "imports", "calls"}
        and source_files.get(edge["target"]) in {"alpha.ts", "beta.ts"}
    }


@pytest.mark.filterwarnings("ignore:stat index switched from cache root:RuntimeWarning")
@pytest.mark.parametrize("raw", [False, True])
@pytest.mark.parametrize("change", ["edit", "add", "remove"])
def test_extract_refreshes_unchanged_typescript_importers(
    tmp_path, monkeypatch, typescript_project, raw, change
):
    root = typescript_project
    out = tmp_path / "output"
    if change != "add":
        _point_to(root, "alpha")
    prior = _run(monkeypatch, root, out, raw=raw)
    relations = {"imports_from", "imports", "calls"}
    assert _local_caller_edges(prior) == (
        set() if change == "add" else {(relation, "alpha.ts") for relation in relations}
    )
    semantic_note = {
        "id": "design_rationale",
        "label": "Port design rationale",
        "source_file": "caller.ts",
        "file_type": "code",
        "_origin": "semantic",
    }
    prior["nodes"].append(semantic_note)
    (out / "graphify-out" / "graph.json").write_text(json.dumps(prior), encoding="utf-8")

    if change == "remove":
        (root / "tsconfig.base.json").unlink()
    else:
        _point_to(root, "beta")

    warm = _run(monkeypatch, root, out, raw=raw)
    clean = _run(monkeypatch, root, tmp_path / "fresh-output", raw=raw)
    assert _local_caller_edges(warm) == _local_caller_edges(clean) == (
        set() if change == "remove" else {(relation, "beta.ts") for relation in relations}
    )
    assert any(
        node["id"] == semantic_note["id"] and node.get("_origin") == "semantic"
        for node in warm["nodes"]
    )
    assert not (root / "graphify-out").exists()


def test_extract_rechecks_lockfile_but_keeps_ordinary_edits_incremental(
    tmp_path, monkeypatch, typescript_project
):
    root = typescript_project
    out = tmp_path / "output"
    _point_to(root, "alpha")
    lockfile = root / "pnpm-lock.yaml"
    lockfile.write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    _run(monkeypatch, root, out, raw=True)
    actual_extract = extract_mod.extract
    batches = []

    def record_extract(paths, **kwargs):
        assert not (set(paths) & {lockfile})
        batches.append({path.name for path in paths})
        return actual_extract(paths, **kwargs)

    monkeypatch.setattr(extract_mod, "extract", record_extract)
    _run(monkeypatch, root, out, raw=True)
    assert not batches

    lockfile.write_text("lockfileVersion: '9.0'\nimporters: {}\n", encoding="utf-8")
    _run(monkeypatch, root, out, raw=True)
    _run(monkeypatch, root, out, raw=True)
    assert batches == [{"alpha.ts", "beta.ts", "caller.ts", "tsconfig.json", "tsconfig.base.json"}]

    lockfile.unlink()
    _run(monkeypatch, root, out, raw=True)
    _run(monkeypatch, root, out, raw=True)
    assert batches[-1] == batches[0]
    assert len(batches) == 2

    source = root / "beta.ts"
    source.write_text('export function read() { return "modified"; }\n', encoding="utf-8")
    _run(monkeypatch, root, out, raw=True)
    assert batches[2:] == [{"beta.ts"}]


@pytest.mark.parametrize("workers", [1, 2])
def test_extract_refreshes_cached_astro_imports(tmp_path, monkeypatch, typescript_project, workers):
    root = typescript_project
    out = tmp_path / "output"
    monkeypatch.setenv("GRAPHIFY_MAX_WORKERS", str(workers))
    if workers > 1:
        for index in range(20):
            (root / f"worker-input-{index}.ts").write_text(
                f"export function workerInput{index}() {{ return {index}; }}\n",
                encoding="utf-8",
            )
    (root / "page.astro").write_text(
        '---\nimport { read } from "@ports";\n---\n<p>{read()}</p>\n',
        encoding="utf-8",
    )
    _point_to(root, "alpha")
    prior = _run(monkeypatch, root, out, raw=True)
    assert ("imports_from", "alpha.ts") in _local_caller_edges(prior, "page.astro")

    _point_to(root, "beta")
    warm = _run(monkeypatch, root, out, raw=True)
    assert ("imports_from", "beta.ts") in _local_caller_edges(warm, "page.astro")
    assert ("imports_from", "alpha.ts") not in _local_caller_edges(warm, "page.astro")


@pytest.mark.parametrize("raw", [False, True])
def test_extract_retries_incomplete_refresh_after_deleting_last_config(
    tmp_path, monkeypatch, typescript_project, raw
):
    root = typescript_project
    out = tmp_path / "output"
    config = root / "tsconfig.json"
    _point_to(root, "alpha")
    (root / "tsconfig.base.json").replace(config)
    prior = _run(monkeypatch, root, out, raw=raw)
    assert ("calls", "alpha.ts") in _local_caller_edges(prior)
    manifest = out / "graphify-out" / "manifest.json"
    snapshot = manifest.read_bytes()

    config.unlink()
    original = extract_mod._DISPATCH[".ts"]

    def flaky_extractor(path):
        if path.name == "alpha.ts":
            return {"nodes": [], "edges": [], "error": "transient failure"}
        return original(path)

    monkeypatch.setitem(extract_mod._DISPATCH, ".ts", flaky_extractor)
    for _ in range(2):
        _run(monkeypatch, root, out, raw=raw, extra=("--allow-partial",))
        assert manifest.read_bytes() == snapshot

    monkeypatch.setitem(extract_mod._DISPATCH, ".ts", original)
    recovered = _run(monkeypatch, root, out, raw=raw)
    assert _local_caller_edges(recovered) == set()
    assert "tsconfig.json" not in json.loads(manifest.read_text(encoding="utf-8"))
