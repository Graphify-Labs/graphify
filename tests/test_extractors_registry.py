"""Identity checks for extractors migrated out of graphify/extract.py (issue #1212).

Each migrated language asserts three things:
- the function is importable from its new per-language module,
- graphify.extract still re-exports the same function object (facade identity),
- graphify.extractors.LANGUAGE_EXTRACTORS maps to the same object (registry identity).
"""
from __future__ import annotations

import graphify.extract as facade
from graphify.extractors import LANGUAGE_EXTRACTORS


def test_terraform_migrated():
    from graphify.extractors.terraform import extract_terraform

    assert facade.extract_terraform is extract_terraform
    assert LANGUAGE_EXTRACTORS["terraform"] is extract_terraform
