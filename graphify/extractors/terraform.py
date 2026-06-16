"""Terraform/HCL extractor - delegates to extract.py implementation."""

from __future__ import annotations

from pathlib import Path

from .registry import register

_EXTENSIONS = {".tf", ".tfvars", ".hcl"}


@register(_EXTENSIONS)
def extract_terraform(path: Path) -> dict:
    """Extract Terraform/HCL blocks and the references between them via tree-sitter."""
    from graphify.extract import extract_terraform as _extract_terraform

    return _extract_terraform(path)
