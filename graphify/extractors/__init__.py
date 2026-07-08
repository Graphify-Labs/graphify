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
from graphify.extractors.bash import extract_bash
from graphify.extractors.blade import extract_blade
from graphify.extractors.dart import extract_dart
from graphify.extractors.dm import extract_dm, extract_dmf, extract_dmi, extract_dmm
from graphify.extractors.elixir import extract_elixir
from graphify.extractors.fortran import extract_fortran
from graphify.extractors.go import extract_go
from graphify.extractors.json_config import extract_json
from graphify.extractors.pascal_forms import extract_delphi_form, extract_lazarus_form
from graphify.extractors.powershell import extract_powershell, extract_powershell_manifest
from graphify.extractors.razor import extract_razor
from graphify.extractors.rust import extract_rust
from graphify.extractors.sln import extract_sln
from graphify.extractors.sql import extract_sql
from graphify.extractors.terraform import extract_terraform
from graphify.extractors.zig import extract_zig

LANGUAGE_EXTRACTORS: dict[str, Callable[[Path], dict]] = {
    "apex": extract_apex,
    "bash": extract_bash,
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
    "json": extract_json,
    "lazarus_form": extract_lazarus_form,
    "powershell": extract_powershell,
    "powershell_manifest": extract_powershell_manifest,
    "razor": extract_razor,
    "rust": extract_rust,
    "sln": extract_sln,
    "sql": extract_sql,
    "terraform": extract_terraform,
    "zig": extract_zig,
}
