"""Guards for the incremental extract.py -> extractors/ migration (see graphify/extractors/MIGRATION.md)."""
from __future__ import annotations

import graphify.extract as extract_facade
import graphify.extractors as extractors
from graphify.extractors import base


def test_registry_values_are_callable():
    for name, fn in extractors.LANGUAGE_EXTRACTORS.items():
        assert callable(fn), name


def test_registry_facade_identity():
    for name, fn in extractors.LANGUAGE_EXTRACTORS.items():
        assert getattr(extract_facade, fn.__name__) is fn, name


def test_base_helpers_facade_identity():
    for name in ("_make_id", "_file_stem", "_read_text", "_LANGUAGE_BUILTIN_GLOBALS"):
        assert getattr(extract_facade, name) is getattr(base, name), name


def test_blade_migrated():
    from graphify.extractors.blade import extract_blade
    assert extract_facade.extract_blade is extract_blade
    assert extractors.LANGUAGE_EXTRACTORS["blade"] is extract_blade


def test_zig_migrated():
    from graphify.extractors.zig import extract_zig
    assert extract_facade.extract_zig is extract_zig
    assert extractors.LANGUAGE_EXTRACTORS["zig"] is extract_zig


def test_elixir_migrated():
    from graphify.extractors.elixir import extract_elixir
    assert extract_facade.extract_elixir is extract_elixir
    assert extractors.LANGUAGE_EXTRACTORS["elixir"] is extract_elixir


def test_razor_migrated():
    from graphify.extractors.razor import extract_razor
    assert extract_facade.extract_razor is extract_razor
    assert extractors.LANGUAGE_EXTRACTORS["razor"] is extract_razor
