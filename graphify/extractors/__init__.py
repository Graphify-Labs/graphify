"""Per-language extractors, incrementally migrated out of graphify/extract.py.

Dispatch still flows through graphify.extract (the facade re-exports every
moved name), so importing from graphify.extract keeps working unchanged.
LANGUAGE_EXTRACTORS is the registry seed; wiring dispatch through it is a
later, separate step. See MIGRATION.md for how to port another language.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from graphify.extractors.apex import extract_apex
from graphify.extractors.astro import extract_astro
from graphify.extractors.bash import extract_bash
from graphify.extractors.blade import extract_blade
from graphify.extractors.c import extract_c
from graphify.extractors.cpp import extract_cpp
from graphify.extractors.csharp import extract_csharp
from graphify.extractors.csproj import extract_csproj
from graphify.extractors.dart import extract_dart
from graphify.extractors.dm import extract_dm, extract_dmf, extract_dmi, extract_dmm
from graphify.extractors.elixir import extract_elixir
from graphify.extractors.fortran import extract_fortran
from graphify.extractors.go import extract_go
from graphify.extractors.groovy import extract_groovy
from graphify.extractors.java import extract_java
from graphify.extractors.js import extract_js
from graphify.extractors.json_config import extract_json
from graphify.extractors.julia import extract_julia
from graphify.extractors.kotlin import extract_kotlin
from graphify.extractors.lazarus_package import extract_lazarus_package
from graphify.extractors.lua import extract_lua
from graphify.extractors.markdown import extract_markdown
from graphify.extractors.objc import extract_objc
from graphify.extractors.pascal import extract_pascal
from graphify.extractors.pascal_forms import extract_delphi_form, extract_lazarus_form
from graphify.extractors.php import extract_php
from graphify.extractors.powershell import extract_powershell, extract_powershell_manifest
from graphify.extractors.python import extract_python
from graphify.extractors.razor import extract_razor
from graphify.extractors.ruby import extract_ruby
from graphify.extractors.rust import extract_rust
from graphify.extractors.scala import extract_scala
from graphify.extractors.sln import extract_sln
from graphify.extractors.slnx import extract_slnx
from graphify.extractors.sql import extract_sql
from graphify.extractors.svelte import extract_svelte
from graphify.extractors.swift import extract_swift
from graphify.extractors.terraform import extract_terraform
from graphify.extractors.verilog import extract_verilog
from graphify.extractors.vue import extract_vue
from graphify.extractors.xaml import extract_xaml
from graphify.extractors.zig import extract_zig

LANGUAGE_EXTRACTORS: dict[str, Callable[[Path], dict]] = {
    "apex": extract_apex,
    "astro": extract_astro,
    "bash": extract_bash,
    "c": extract_c,
    "cpp": extract_cpp,
    "csharp": extract_csharp,
    "csproj": extract_csproj,
    "blade": extract_blade,
    "dart": extract_dart,
    "delphi_form": extract_delphi_form,
    "dm": extract_dm,
    "dmf": extract_dmf,
    "dmi": extract_dmi,
    "dmm": extract_dmm,
    "elixir": extract_elixir,
    "fortran": extract_fortran,
    "go": extract_go,
    "groovy": extract_groovy,
    "java": extract_java,
    "js": extract_js,
    "json": extract_json,
    "julia": extract_julia,
    "kotlin": extract_kotlin,
    "lazarus_form": extract_lazarus_form,
    "lazarus_package": extract_lazarus_package,
    "lua": extract_lua,
    "markdown": extract_markdown,
    "objc": extract_objc,
    "pascal": extract_pascal,
    "php": extract_php,
    "powershell": extract_powershell,
    "powershell_manifest": extract_powershell_manifest,
    "python": extract_python,
    "razor": extract_razor,
    "ruby": extract_ruby,
    "rust": extract_rust,
    "scala": extract_scala,
    "sln": extract_sln,
    "slnx": extract_slnx,
    "sql": extract_sql,
    "svelte": extract_svelte,
    "swift": extract_swift,
    "terraform": extract_terraform,
    "verilog": extract_verilog,
    "vue": extract_vue,
    "xaml": extract_xaml,
    "zig": extract_zig,
}
