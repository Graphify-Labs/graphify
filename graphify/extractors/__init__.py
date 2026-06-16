"""Graphify language extractors package."""
from __future__ import annotations

# Import registry first
from .registry import get_extractor, get_all_extensions, extract, register

# Import base classes  
from .base import Extractor, BaseExtractor

# Import all extractor modules to trigger registration
from . import (
    apex, astro, bash, blade, c, cpp, csharp, dart, dm, dotnet,
    elixir, fortran, go, groovy, java, javascript, json_ast, jsx,
    julia, kotlin, lua, markdown, objc, pascal, php, powershell,
    python, ruby, rust, scala, sql, svelte, swift, terraform,
    typescript, verilog, vue, zig
)

__all__ = [
    "get_extractor",
    "get_all_extensions", 
    "extract",
    "register",
    "Extractor",
    "BaseExtractor",
]
