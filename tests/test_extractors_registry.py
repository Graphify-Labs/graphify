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


def test_objc_migrated():
    from graphify.extractors.objc import extract_objc

    assert facade.extract_objc is extract_objc
    assert LANGUAGE_EXTRACTORS["objc"] is extract_objc


def test_pascal_migrated():
    from graphify.extractors.pascal import extract_pascal

    assert facade.extract_pascal is extract_pascal
    assert LANGUAGE_EXTRACTORS["pascal"] is extract_pascal


def test_julia_migrated():
    from graphify.extractors.julia import extract_julia

    assert facade.extract_julia is extract_julia
    assert LANGUAGE_EXTRACTORS["julia"] is extract_julia


def test_verilog_migrated():
    from graphify.extractors.verilog import extract_verilog

    assert facade.extract_verilog is extract_verilog
    assert LANGUAGE_EXTRACTORS["verilog"] is extract_verilog


def test_markdown_migrated():
    from graphify.extractors.markdown import extract_markdown

    assert facade.extract_markdown is extract_markdown
    assert LANGUAGE_EXTRACTORS["markdown"] is extract_markdown


def test_python_migrated():
    from graphify.extractors.python import extract_python

    assert facade.extract_python is extract_python
    assert LANGUAGE_EXTRACTORS["python"] is extract_python


def test_js_migrated():
    from graphify.extractors.js import extract_js

    assert facade.extract_js is extract_js
    assert LANGUAGE_EXTRACTORS["js"] is extract_js


def test_svelte_migrated():
    from graphify.extractors.svelte import extract_svelte

    assert facade.extract_svelte is extract_svelte
    assert LANGUAGE_EXTRACTORS["svelte"] is extract_svelte


def test_astro_migrated():
    from graphify.extractors.astro import extract_astro

    assert facade.extract_astro is extract_astro
    assert LANGUAGE_EXTRACTORS["astro"] is extract_astro


def test_vue_migrated():
    from graphify.extractors.vue import extract_vue

    assert facade.extract_vue is extract_vue
    assert LANGUAGE_EXTRACTORS["vue"] is extract_vue


def test_java_migrated():
    from graphify.extractors.java import extract_java

    assert facade.extract_java is extract_java
    assert LANGUAGE_EXTRACTORS["java"] is extract_java


def test_groovy_migrated():
    from graphify.extractors.groovy import extract_groovy

    assert facade.extract_groovy is extract_groovy
    assert LANGUAGE_EXTRACTORS["groovy"] is extract_groovy


def test_c_migrated():
    from graphify.extractors.c import extract_c

    assert facade.extract_c is extract_c
    assert LANGUAGE_EXTRACTORS["c"] is extract_c


def test_cpp_migrated():
    from graphify.extractors.cpp import extract_cpp

    assert facade.extract_cpp is extract_cpp
    assert LANGUAGE_EXTRACTORS["cpp"] is extract_cpp


def test_ruby_migrated():
    from graphify.extractors.ruby import extract_ruby

    assert facade.extract_ruby is extract_ruby
    assert LANGUAGE_EXTRACTORS["ruby"] is extract_ruby


def test_csharp_migrated():
    from graphify.extractors.csharp import extract_csharp

    assert facade.extract_csharp is extract_csharp
    assert LANGUAGE_EXTRACTORS["csharp"] is extract_csharp


def test_kotlin_migrated():
    from graphify.extractors.kotlin import extract_kotlin

    assert facade.extract_kotlin is extract_kotlin
    assert LANGUAGE_EXTRACTORS["kotlin"] is extract_kotlin


def test_scala_migrated():
    from graphify.extractors.scala import extract_scala

    assert facade.extract_scala is extract_scala
    assert LANGUAGE_EXTRACTORS["scala"] is extract_scala


def test_php_migrated():
    from graphify.extractors.php import extract_php

    assert facade.extract_php is extract_php
    assert LANGUAGE_EXTRACTORS["php"] is extract_php


def test_lua_migrated():
    from graphify.extractors.lua import extract_lua

    assert facade.extract_lua is extract_lua
    assert LANGUAGE_EXTRACTORS["lua"] is extract_lua


def test_swift_migrated():
    from graphify.extractors.swift import extract_swift

    assert facade.extract_swift is extract_swift
    assert LANGUAGE_EXTRACTORS["swift"] is extract_swift


def test_xaml_migrated():
    from graphify.extractors.xaml import extract_xaml

    assert facade.extract_xaml is extract_xaml
    assert LANGUAGE_EXTRACTORS["xaml"] is extract_xaml
