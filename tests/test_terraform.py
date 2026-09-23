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


def test_terraform_attributes_primitive_literals(tmp_path):
    body = """\
resource "aws_s3_bucket" "example" {
  bucket        = "my-test-bucket"
  force_destroy = true
  versioning    = false
  max_size      = 42
  ratio         = 3.14
  logging       = null
}
"""
    r = extract_terraform(_write(tmp_path, "main.tf", body))
    node = next(n for n in r["nodes"] if n["label"] == "aws_s3_bucket.example")
    attrs = node.get("attributes")
    assert attrs is not None
    assert attrs["bucket"] == "my-test-bucket"
    assert attrs["force_destroy"] is True
    assert attrs["versioning"] is False
    assert attrs["max_size"] == 42
    assert attrs["ratio"] == 3.14
    assert attrs["logging"] is None


def test_terraform_attributes_collections(tmp_path):
    body = """\
resource "aws_security_group" "sg" {
  name          = "sg"
  tags          = { Environment = "production", ManagedBy = "terraform" }
  ingress_cidrs = ["10.0.0.0/16", "192.168.1.0/24"]
}
"""
    r = extract_terraform(_write(tmp_path, "main.tf", body))
    node = next(n for n in r["nodes"] if n["label"] == "aws_security_group.sg")
    attrs = node.get("attributes")
    assert attrs is not None
    assert attrs["name"] == "sg"
    assert attrs["tags"] == {"Environment": "production", "ManagedBy": "terraform"}
    assert attrs["ingress_cidrs"] == ["10.0.0.0/16", "192.168.1.0/24"]


def test_terraform_attributes_expressions_and_references(tmp_path):
    body = """\
variable "bucket_name" { default = "my-bucket" }
data "aws_ami" "ubuntu" { most_recent = true }

resource "aws_s3_bucket" "example" {
  bucket = var.bucket_name
  ami    = data.aws_ami.ubuntu.id
}
"""
    r = extract_terraform(_write(tmp_path, "main.tf", body))
    bucket_node = next(n for n in r["nodes"] if n["label"] == "aws_s3_bucket.example")
    attrs = bucket_node.get("attributes")
    assert attrs is not None
    assert attrs["bucket"] == "var.bucket_name"
    assert attrs["ami"] == "data.aws_ami.ubuntu.id"

    # Verify existing reference edges remain intact
    refs = _rel_pairs(r, "references")
    assert ("aws_s3_bucket.example", "var.bucket_name") in refs
    assert ("aws_s3_bucket.example", "data.aws_ami.ubuntu") in refs


def test_terraform_multiple_attributes_and_nested_block_isolation(tmp_path):
    body = """\
resource "aws_instance" "web" {
  ami           = "ami-12345"
  instance_type = "t3.micro"
  lifecycle {
    prevent_destroy = true
  }
}
"""
    r = extract_terraform(_write(tmp_path, "main.tf", body))
    node = next(n for n in r["nodes"] if n["label"] == "aws_instance.web")
    attrs = node.get("attributes")
    assert attrs is not None
    assert attrs["ami"] == "ami-12345"
    assert attrs["instance_type"] == "t3.micro"
    # Ownership rule: only direct attributes of the block are captured.
    # Nested blocks (e.g. lifecycle) must NOT be flattened into parent attributes.
    assert "prevent_destroy" not in attrs
    assert "lifecycle" not in attrs


def test_terraform_attributes_query_and_search_discovery(tmp_path):
    from graphify.serve import _query_graph_text

    body = """\
resource "aws_s3_bucket" "prod" {
  bucket         = "company-prod-assets"
  force_destroy  = true
  engine_version = "15.4"
}

resource "aws_s3_bucket" "backup" {
  bucket         = "company-backup-assets"
  force_destroy  = false
  engine_version = "14.2"
}
"""
    r = extract_terraform(_write(tmp_path, "main.tf", body))
    G = build_from_json(r)

    # 1. Attribute name contributes to searchability
    res_key = _query_graph_text(G, "force_destroy", depth=1)
    assert "aws_s3_bucket.prod" in res_key
    assert "aws_s3_bucket.backup" in res_key

    # 2. Attribute literal value contributes to retrieval
    res_val = _query_graph_text(G, "company-prod-assets", depth=1)
    assert "aws_s3_bucket.prod" in res_val

    # 3. Attribute name contributes to searchability
    res_engine = _query_graph_text(G, "engine_version", depth=1)
    assert "aws_s3_bucket.prod" in res_engine

    # 4. Verified node retrieval and serialized attribute map content
    prod_node = next(n for n in r["nodes"] if n["label"] == "aws_s3_bucket.prod")
    assert prod_node["attributes"]["force_destroy"] is True
    assert prod_node["attributes"]["engine_version"] == "15.4"


def test_terraform_attributes_context_rendering(tmp_path):
    from graphify.serve import _subgraph_to_text

    body = """\
resource "aws_s3_bucket" "example" {
  bucket        = "var.bucket_name"
  force_destroy = true
  tags = {
    Environment = "production"
  }
}
"""
    r = extract_terraform(_write(tmp_path, "main.tf", body))
    G = build_from_json(r)
    node_id = next(n["id"] for n in r["nodes"] if n["label"] == "aws_s3_bucket.example")

    rendered = _subgraph_to_text(G, {node_id}, set(), token_budget=2000)
    assert "attrs={" in rendered
    assert 'bucket="var.bucket_name"' in rendered
    assert "force_destroy=true" in rendered
    assert '"Environment": "production"' in rendered


def test_terraform_attributes_round_trip_serialization(tmp_path):
    from graphify.export import to_json
    from graphify.serve import _load_graph

    body = """\
resource "aws_s3_bucket" "example" {
  bucket        = "my-bucket"
  force_destroy = true
}
"""
    r = extract_terraform(_write(tmp_path, "main.tf", body))
    G = build_from_json(r)
    out_file = tmp_path / "graph.json"
    to_json(G, {}, str(out_file), force=True)
    loaded_G = _load_graph(str(out_file))
    node_id = next(n["id"] for n in r["nodes"] if n["label"] == "aws_s3_bucket.example")
    assert loaded_G.nodes[node_id].get("attributes") == {"bucket": "my-bucket", "force_destroy": True}


def test_terraform_sensitive_attribute_values_are_redacted(tmp_path):
    """Attribute values are persisted to graph.json and surfaced to the model,
    so a hardcoded credential must not leak: the VALUE of a secret-named key is
    redacted while the key stays visible, and non-secret keys are untouched
    (#3644 security follow-up). Redaction recurses into map values too."""
    body = """\
resource "aws_db_instance" "main" {
  identifier    = "prod-db"
  instance_class = "db.t3.medium"
  password      = "hunter2-super-secret"
  db_password   = "another-secret"
  aws_secret_access_key = "AKIAWHATEVER"
  tags = {
    Name         = "prod"
    client_secret = "leaky"
  }
}
"""
    r = extract_terraform(_write(tmp_path, "db.tf", body))
    node = next(n for n in r["nodes"] if n["label"] == "aws_db_instance.main")
    attrs = node["attributes"]
    # non-secret keys pass through unchanged
    assert attrs["identifier"] == "prod-db"
    assert attrs["instance_class"] == "db.t3.medium"
    # secret-named keys keep their key but redact the value
    assert attrs["password"] == "[redacted]"
    assert attrs["db_password"] == "[redacted]"
    assert attrs["aws_secret_access_key"] == "[redacted]"
    # nested map: the secret is redacted, the ordinary key is not
    assert attrs["tags"]["Name"] == "prod"
    assert attrs["tags"]["client_secret"] == "[redacted]"
    # the literal secret must appear nowhere in the serialized node
    import json as _json
    assert "hunter2-super-secret" not in _json.dumps(node)
    assert "AKIAWHATEVER" not in _json.dumps(node)
    assert "leaky" not in _json.dumps(node)
