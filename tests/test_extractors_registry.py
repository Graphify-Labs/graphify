"""Facade / registry identity guards for the per-language extractor split (#1212).

The ``extract.py`` decomposition (#1737) moved each language extractor into its
own ``graphify/extractors/<lang>.py`` module, kept a verbatim re-export in
``graphify.extract`` (the facade every existing importer uses), and seeded a
``graphify.extractors.LANGUAGE_EXTRACTORS`` registry. Three things must stay
true for that split to be behavior-preserving:

- the function is importable from its new per-language module,
- ``graphify.extract`` still re-exports the SAME function object (facade
  identity — a stale copy or shadowing import would silently diverge),
- ``LANGUAGE_EXTRACTORS`` maps to that same object (registry identity).

Originally proposed by @Cekaru in #1721 as a per-language check; generalized
here to sweep the whole registry so a future move that forgets the facade
re-export (or re-exports a different object) fails loudly.
"""
from __future__ import annotations

import graphify.extract as facade
from graphify.extractors import LANGUAGE_EXTRACTORS


def test_every_registry_extractor_is_reexported_from_facade():
    missing = []
    diverged = []
    for lang, fn in LANGUAGE_EXTRACTORS.items():
        name = getattr(fn, "__name__", None)
        if not name or not hasattr(facade, name):
            missing.append((lang, name))
            continue
        if getattr(facade, name) is not fn:
            diverged.append((lang, name))
    assert not missing, f"registry extractors not re-exported from graphify.extract: {missing}"
    assert not diverged, f"facade object diverges from registry: {diverged}"


def test_terraform_migrated():
    # The concrete anchor from #1721: extract_terraform lives in its own module,
    # and both the facade and the registry point at that one object.
    from graphify.extractors.terraform import extract_terraform

    assert facade.extract_terraform is extract_terraform
    assert LANGUAGE_EXTRACTORS["terraform"] is extract_terraform


def test_lazarus_package_migrated():
    from graphify.extractors.lazarus_package import extract_lazarus_package

    assert facade.extract_lazarus_package is extract_lazarus_package
    assert LANGUAGE_EXTRACTORS["lazarus_package"] is extract_lazarus_package


def test_slnx_migrated():
    from graphify.extractors.slnx import extract_slnx

    assert facade.extract_slnx is extract_slnx
    assert LANGUAGE_EXTRACTORS["slnx"] is extract_slnx


def test_csproj_migrated():
    from graphify.extractors.csproj import extract_csproj

    assert facade.extract_csproj is extract_csproj
    assert LANGUAGE_EXTRACTORS["csproj"] is extract_csproj
