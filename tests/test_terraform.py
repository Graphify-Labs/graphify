"""Tests for the Terraform/HCL extractor (graphify/extract.py, issue #187)."""
from __future__ import annotations

from pathlib import Path

from graphify.build import build_from_json
from graphify.extract import extract_terraform


def _write(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


def _labels(r) -> list[str]:
    return [n["label"] for n in r["nodes"]]


def _rel_pairs(r, relation: str) -> set[tuple[str, str]]:
    lab = {n["id"]: n["label"] for n in r["nodes"]}
    return {
        (lab.get(e["source"], e["source"]), lab.get(e["target"], e["target"]))
        for e in r["edges"]
        if e["relation"] == relation
    }


SAMPLE = """\
# leading comment so the body is not children[0]
terraform {
  required_providers { azurerm = { source = "hashicorp/azurerm" } }
}

variable "region" { default = "us-east-1" }

provider "aws" { region = var.region }

data "aws_ami" "ubuntu" { most_recent = true }

resource "aws_instance" "web" {
  ami       = data.aws_ami.ubuntu.id
  subnet_id = var.region
  depends_on = [aws_security_group.sg]
}

resource "aws_security_group" "sg" { name = "sg" }

module "vpc" {
  source = "./modules/vpc"
  cidr   = local.cidr
}

locals { cidr = "10.0.0.0/16" }

output "ip" { value = aws_instance.web.private_ip }
"""


def test_no_error_and_all_block_types_become_nodes(tmp_path):
    r = extract_terraform(_write(tmp_path, "main.tf", SAMPLE))
    assert r.get("error") is None
    labels = set(_labels(r))
    # one node per block type (the terraform{} settings block is intentionally skipped)
    for expected in (
        "var.region",
        "provider.aws",
        "data.aws_ami.ubuntu",
        "aws_instance.web",
        "aws_security_group.sg",
        "module.vpc",
        "local.cidr",
        "output.ip",
    ):
        assert expected in labels, f"missing node {expected!r}"


def test_reference_edges(tmp_path):
    r = extract_terraform(_write(tmp_path, "main.tf", SAMPLE))
    refs = _rel_pairs(r, "references")
    assert ("provider.aws", "var.region") in refs
    assert ("aws_instance.web", "data.aws_ami.ubuntu") in refs
    assert ("aws_instance.web", "var.region") in refs
    assert ("module.vpc", "local.cidr") in refs
    assert ("output.ip", "aws_instance.web") in refs


def test_depends_on_edge(tmp_path):
    r = extract_terraform(_write(tmp_path, "main.tf", SAMPLE))
    assert ("aws_instance.web", "aws_security_group.sg") in _rel_pairs(r, "depends_on")


def test_file_contains_blocks(tmp_path):
    r = extract_terraform(_write(tmp_path, "main.tf", SAMPLE))
    contains = _rel_pairs(r, "contains")
    assert ("main.tf", "aws_instance.web") in contains
    assert ("main.tf", "var.region") in contains


def test_meta_heads_not_emitted(tmp_path):
    # count.index / each.key / self.* / path.module are builtins, not references.
    body = """\
resource "aws_instance" "web" {
  count = 2
  name  = "web-${count.index}"
  tags  = each.value
  dir   = path.module
}
"""
    r = extract_terraform(_write(tmp_path, "main.tf", body))
    targets = {t for _, t in _rel_pairs(r, "references")}
    assert not any(t.startswith(("count", "each", "path")) for t in targets)


def test_cross_file_references_resolve_after_merge(tmp_path):
    # A resource defined in one file is referenced from another in the same
    # directory; directory-scoped IDs must let the edge resolve at build time.
    defn = """\
resource "azurerm_resource_group" "main" { name = "rg" }
"""
    user = """\
resource "azurerm_network_interface" "nic" {
  resource_group_name = azurerm_resource_group.main.name
}
"""
    r_defn = extract_terraform(_write(tmp_path, "main.tf", defn))
    r_user = extract_terraform(_write(tmp_path, "nic.tf", user))

    # The cross-file edge target id equals the definition's node id.
    rg_id = next(n["id"] for n in r_defn["nodes"] if n["label"] == "azurerm_resource_group.main")
    nic_ref_targets = {e["target"] for e in r_user["edges"] if e["relation"] == "references"}
    assert rg_id in nic_ref_targets

    # And it survives a real merge: the edge is present (not dropped as dangling).
    G = build_from_json(
        {
            "nodes": r_defn["nodes"] + r_user["nodes"],
            "edges": r_defn["edges"] + r_user["edges"],
        }
    )
    nic_id = next(n["id"] for n in r_user["nodes"] if n["label"] == "azurerm_network_interface.nic")
    assert G.has_edge(nic_id, rg_id)


def test_empty_and_commentonly_files_are_safe(tmp_path):
    assert extract_terraform(_write(tmp_path, "a.tf", "")).get("error") is None
    r = extract_terraform(_write(tmp_path, "b.tf", "# just a comment\n"))
    # only the file node, no crash
    assert len(r["nodes"]) == 1


def test_tfvars_key_value_is_safe(tmp_path):
    # .tfvars files contain only key=value assignments (no block structure),
    # so extract_terraform produces zero block nodes — only the file node.
    # This is the documented intended behaviour for .tfvars.
    r = extract_terraform(_write(tmp_path, "terraform.tfvars", 'region = "us-east-1"\nenv = "prod"\n'))
    assert r.get("error") is None
    assert len(r["nodes"]) == 1  # only the file node, no variable nodes


def test_terraform_attribute_extraction(tmp_path):
    """Verify attribute names, values, and nested block attributes are preserved (#3625)."""
    hcl = """\
variable "bucket_name" {
  type = string
}

resource "aws_s3_bucket" "example" {
  bucket        = var.bucket_name
  force_destroy = true

  tags = {
    Environment = "production"
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_db_instance" "example" {
  engine_version    = "15.4"
  instance_class    = "db.t3.micro"
  allocated_storage = 20
  multi_az          = false
}

locals {
  app_env = "staging"
}
"""
    r = extract_terraform(_write(tmp_path, "main.tf", hcl))
    assert r.get("error") is None
    nodes_by_label = {n["label"]: n for n in r["nodes"]}

    s3_node = nodes_by_label["aws_s3_bucket.example"]
    assert "attributes" in s3_node
    s3_attrs = s3_node["attributes"]
    assert s3_attrs.get("bucket") == "var.bucket_name"
    assert s3_attrs.get("force_destroy") == "true"
    assert s3_attrs.get("tags.Environment") == "production"
    assert s3_attrs.get("lifecycle.prevent_destroy") == "true"

    db_node = nodes_by_label["aws_db_instance.example"]
    assert "attributes" in db_node
    db_attrs = db_node["attributes"]
    assert db_attrs.get("engine_version") == "15.4"
    assert db_attrs.get("instance_class") == "db.t3.micro"
    assert db_attrs.get("allocated_storage") == "20"
    assert db_attrs.get("multi_az") == "false"

    var_node = nodes_by_label["var.bucket_name"]
    assert var_node.get("attributes", {}).get("type") == "string"

    local_node = nodes_by_label["local.app_env"]
    assert local_node.get("attributes", {}).get("app_env") == "staging"


def test_terraform_attribute_querying(tmp_path):
    """Attribute values allow graph queries to find the configured resource (#3625)."""
    from graphify.serve import _query_graph_text

    hcl = """\
resource "aws_s3_bucket" "example" {
  bucket        = "my-bucket"
  force_destroy = true
}

resource "aws_db_instance" "example" {
  engine_version = "15.4"
  multi_az       = false
}
"""
    r = extract_terraform(_write(tmp_path, "main.tf", hcl))
    G = build_from_json(r)

    # Query for force_destroy attribute on aws_s3_bucket
    out = _query_graph_text(G, "which aws_s3_bucket sets force_destroy = true")
    assert "aws_s3_bucket.example" in out
    assert "Start: ['aws_s3_bucket.example']" in out

