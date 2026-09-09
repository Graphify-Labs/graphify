"""Local Terraform module topology, including incremental graph reconciliation."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import networkx as nx
import pytest

from graphify.build import build_from_json
from graphify.extract import extract, extract_terraform


def _write(root, name, body):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _extract(root, paths=None):
    return extract(
        sorted(root.rglob("*.tf")) if paths is None else paths,
        root=root, cache_root=root, parallel=False,
    )


def _node(result, label, source=None):
    return next(n for n in result["nodes"] if n["label"] == label
                and (source is None or n["source_file"] == source))


def _module_edges(result):
    return [e for e in result.get("links", result.get("edges", []))
            if e.get("relation") == "module_source"]


def _assert_integrity(result):
    ids = {n["id"] for n in result["nodes"]}
    for e in result.get("links", result.get("edges", [])):
        assert e["source"] in ids, e
        assert e["target"] in ids, e


def test_environment_application_base_topology_and_source_provenance(tmp_path):
    _write(tmp_path, "envs/dev/main.tf", 'module "app" {\n  source = "../../applications/app"\n}\n')
    _write(tmp_path, "applications/app/main.tf", 'module "base" { source = "../../base" }\n')
    _write(tmp_path, "applications/app/outputs.tf", 'output "id" { value = "app" }\n')
    _write(tmp_path, "base/storage.tf", 'resource "aws_s3_bucket" "data" {}\n')
    result = _extract(tmp_path)
    _assert_integrity(result)
    G = build_from_json(result, root=tmp_path, directed=True)
    env = _node(result, "Terraform module: envs/dev")
    resource = _node(result, "aws_s3_bucket.data")
    assert nx.has_path(G, env["id"], resource["id"])
    app = _node(result, "Terraform module: applications/app")
    outputs = _node(result, "outputs.tf")
    assert G.has_edge(app["id"], outputs["id"])
    edge = next(e for e in _module_edges(result) if e["target"] == app["id"])
    assert edge["source_file"] == "envs/dev/main.tf"
    assert edge["source_location"] == "L2"
    assert edge["confidence"] == "EXTRACTED"
    assert len(_module_edges(result)) == 2


def test_same_named_directories_and_cross_file_references_stay_separate(tmp_path):
    for directory in ("dev/app", "prod/app", "a-b/app", "a_b/app"):
        _write(tmp_path, f"{directory}/main.tf", 'variable "name" {}\n')
        _write(tmp_path, f"{directory}/use.tf", 'output "name" { value = var.name }\n')
    result = _extract(tmp_path)
    _assert_integrity(result)
    variables = [n for n in result["nodes"] if n["label"] == "var.name"]
    assert len({n["id"] for n in variables}) == 4
    for variable in variables:
        source = str(Path(variable["source_file"]).parent / "use.tf")
        output = _node(result, "output.name", source)
        assert any(e["source"] == output["id"] and e["target"] == variable["id"]
                   for e in result["edges"])


def test_raw_extractor_scopes_ids_by_full_directory(tmp_path):
    paths = [_write(tmp_path, f"{env}/app/main.tf", 'variable "x" {}')
             for env in ("dev", "prod")]
    ids = [_node(extract_terraform(p), "var.x")["id"] for p in paths]
    assert len(set(ids)) == 2


def test_multiple_calls_share_one_module_and_cycles_are_finite(tmp_path):
    _write(tmp_path, "main.tf", 'module "a" { source = "./child" }\nmodule "b" { source = "./child" }\n')
    _write(tmp_path, "child/main.tf", 'module "parent" { source = "../" }\n')
    result = _extract(tmp_path)
    _assert_integrity(result)
    assert len([n for n in result["nodes"] if n.get("type") == "module"]) == 2
    child_id = _node(result, "Terraform module: child")["id"]
    assert sum(e["target"] == child_id for e in _module_edges(result)) == 2
    assert len(_module_edges(result)) == 3


@pytest.mark.parametrize("source", [
    '"hashicorp/consul/aws"', '"git::https://example.com/module.git//sub?ref=v1"',
    '"https://example.com/module.zip"', '"../missing"',
    '"../${var.name}"', 'var.source', '"../app" + "suffix"',
])
def test_unresolved_sources_do_not_create_topology(tmp_path, source):
    _write(tmp_path, "env/main.tf", f'module "app" {{ source = {source} }}\n')
    _write(tmp_path, "app/main.tf", 'resource "aws_s3_bucket" "data" {}\n')
    assert _module_edges(_extract(tmp_path)) == []


def test_ignored_outside_and_non_tf_targets_are_not_followed(tmp_path):
    root = tmp_path / "repo"
    caller = _write(root, "main.tf", '''
module "outside" { source = "../outside" }
module "excluded" { source = "./excluded" }
module "hcl" { source = "./hcl" }
module "vars" { source = "./vars" }
module "nested" { source = "./nested" }
''')
    _write(tmp_path, "outside/main.tf", 'variable "x" {}')
    _write(root, "excluded/main.tf", 'variable "x" {}')
    hcl = _write(root, "hcl/main.hcl", 'variable "x" {}')
    tfvars = _write(root, "vars/main.tfvars", 'x = 1')
    nested = _write(root, "nested/sub/main.tf", 'variable "x" {}')
    result = _extract(root, [caller, hcl, tfvars, nested])
    assert _module_edges(result) == []
    assert not any(n.get("_terraform_directory") in ("excluded", "hcl", "vars", "nested")
                   for n in result["nodes"] if n.get("type") == "module")


def test_source_literals_escapes_and_nested_source_attributes(tmp_path):
    _write(tmp_path, "main.tf", r'''module "app" {
  source = "./a\u0070p"
  settings = { source = "./wrong" }
}
module "escaped" { source = "./$${literal}" }
''')
    _write(tmp_path, "app/main.tf", 'variable "x" {}')
    _write(tmp_path, "${literal}/main.tf", 'variable "x" {}')
    result = _extract(tmp_path)
    assert _node(result, "module.app")["module_source"] == "./app"
    assert len(_module_edges(result)) == 2


def test_symlink_targets_respect_scan_boundary(tmp_path):
    root = tmp_path / "repo"
    _write(root, "main.tf", 'module "inside" { source = "./alias" }\nmodule "outside" { source = "./escape" }')
    _write(root, "app/main.tf", 'variable "x" {}')
    _write(tmp_path, "outside/main.tf", 'variable "y" {}')
    try:
        (root / "alias").symlink_to(root / "app", target_is_directory=True)
        (root / "escape").symlink_to(tmp_path / "outside", target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable")
    result = _extract(root, [root / "main.tf", root / "app/main.tf"])
    assert len(_module_edges(result)) == 1
    assert _module_edges(result)[0]["target"] == _node(result, "Terraform module: app")["id"]


def test_cache_recomputes_topology_and_ids_are_portable(tmp_path, monkeypatch):
    roots = [tmp_path / name for name in ("one", "two")]
    for root in roots:
        _write(root, "main.tf", 'module "app" { source = "./app" }')
        _write(root, "app/main.tf", 'variable "x" {}')
    first = _extract(roots[0])
    from graphify.extract import _DISPATCH
    with monkeypatch.context() as cached:
        def unexpected_parse(path):
            raise AssertionError(f"cache miss for unchanged {path}")
        cached.setitem(_DISPATCH, ".tf", unexpected_parse)
        assert first == _extract(roots[0])
    second = _extract(roots[1])
    assert first["nodes"] == second["nodes"]
    assert first["edges"] == second["edges"]
    monkeypatch.chdir(roots[0])
    relative = _extract(Path("."), [Path("app/main.tf"), Path("main.tf")])
    assert first["nodes"] == relative["nodes"]
    assert first["edges"] == relative["edges"]
    target = roots[0] / "app/main.tf"
    target.unlink()
    result = _extract(roots[0])
    assert _module_edges(result) == []
    assert not any(n["label"] == "Terraform module: app" for n in result["nodes"])


@pytest.mark.parametrize("mode", ["watch", "cli"])
@pytest.mark.parametrize("no_cluster", [True, False])
def test_incremental_source_change_target_addition_and_deletion(tmp_path, monkeypatch, mode, no_cluster):
    root = tmp_path / "repo"
    caller = _write(root, "env/main.tf", 'module "app" { source = "../app" }')
    a = _write(root, "app/a.tf", 'variable "x" {}')
    b = _write(root, "app/b.tf", 'variable "y" {}')
    _write(root, "other/main.tf", 'variable "z" {}')
    project_path = str(Path(__file__).resolve().parents[1])
    monkeypatch.setenv("PYTHONPATH", project_path)
    monkeypatch.chdir(root)

    def rebuild(changed=None):
        if mode == "watch":
            from graphify.watch import _rebuild_code
            assert _rebuild_code(root, changed_paths=changed, acquire_lock=False,
                                 no_cluster=no_cluster)
        else:
            args = [sys.executable, "-m", "graphify", "extract", str(root), "--code-only"]
            if no_cluster:
                args.append("--no-cluster")
            p = subprocess.run(args, cwd=root, env=os.environ.copy(), capture_output=True, text=True)
            assert p.returncode == 0, p.stdout + p.stderr
        result = json.loads((root / "graphify-out/graph.json").read_text())
        _assert_integrity(result)
        return result

    first = rebuild()
    anchor = _node(first, "Terraform module: app")["id"]
    assert _module_edges(first)[0]["target"] == anchor
    a.unlink()  # Removing the anchor's provenance file must preserve the module.
    second = rebuild([a])
    assert _module_edges(second)[0]["target"] == anchor
    assert _node(second, "Terraform module: app")["source_file"] == "app/b.tf"
    b.unlink()  # Removing the final file must also remove the incoming link.
    assert _module_edges(rebuild([b])) == []
    c = _write(root, "app/c.tf", 'variable "new" {}')
    assert _module_edges(rebuild([c]))[0]["target"] == anchor
    caller.write_text('module "app" { source = "../other" }')
    final = rebuild([caller])
    assert len(_module_edges(final)) == 1
    assert _module_edges(final)[0]["target"] == _node(final, "Terraform module: other")["id"]


@pytest.mark.parametrize("mode", ["watch", "cli"])
def test_incremental_exclusion_removes_incoming_module_links(tmp_path, monkeypatch, mode):
    root = tmp_path / "repo"
    _write(root, "main.tf", 'module "app" { source = "./app" }')
    _write(root, "app/main.tf", 'variable "x" {}')
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).resolve().parents[1]))
    monkeypatch.chdir(root)

    def rebuild(changed=None):
        if mode == "watch":
            from graphify.watch import _rebuild_code
            assert _rebuild_code(root, changed_paths=changed, acquire_lock=False, no_cluster=True)
        else:
            p = subprocess.run(
                [sys.executable, "-m", "graphify", "extract", str(root), "--code-only", "--no-cluster"],
                capture_output=True, text=True,
            )
            assert p.returncode == 0, p.stdout + p.stderr
        return json.loads((root / "graphify-out/graph.json").read_text())

    assert len(_module_edges(rebuild())) == 1
    ignore = _write(root, ".graphifyignore", "app/\n")
    result = rebuild([ignore])
    _assert_integrity(result)
    assert _module_edges(result) == []
    assert not any(n.get("_terraform_directory") == "app" for n in result["nodes"])
