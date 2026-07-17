"""models — moved verbatim from graphify/extract.py."""
from __future__ import annotations

from typing import Any, Callable
from pathlib import Path
from dataclasses import dataclass, field


_WORKSPACE_PACKAGE_CACHE: dict[str, dict[str, Path]] = {}

_JS_CACHE_BYPASS_SUFFIXES = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts", ".vue", ".svelte"}

@dataclass
class LanguageConfig:
    ts_module: str                                   # e.g. "tree_sitter_python"
    ts_language_fn: str = "language"                 # attr to call: e.g. tslang.language()

    class_types: frozenset = frozenset()
    function_types: frozenset = frozenset()
    import_types: frozenset = frozenset()
    call_types: frozenset = frozenset()
    static_prop_types: frozenset = frozenset()
    helper_fn_names: frozenset = frozenset()
    container_bind_methods: frozenset = frozenset()
    event_listener_properties: frozenset = frozenset()

    # Name extraction
    name_field: str = "name"
    name_fallback_child_types: tuple = ()

    # Body detection
    body_field: str = "body"
    body_fallback_child_types: tuple = ()   # e.g. ("declaration_list", "compound_statement")

    # Call name extraction
    call_function_field: str = "function"           # field on call node for callee
    call_accessor_node_types: frozenset = frozenset()  # member/attribute nodes
    call_accessor_field: str = "attribute"          # field on accessor for method name
    call_accessor_object_field: str = ""            # field on accessor for the receiver/object

    # Stop recursion at these types in walk_calls
    function_boundary_types: frozenset = frozenset()

    # Import handler: called for import nodes instead of generic handling
    import_handler: Callable | None = None

    # Optional custom name resolver for functions (C, C++ declarator unwrapping)
    resolve_function_name_fn: Callable | None = None

    # Extra label formatting for functions: if True, functions get "name()" label
    function_label_parens: bool = True

    # Extra walk hook called after generic dispatch (for JS arrow functions, C# namespaces, etc.)
    extra_walk_fn: Callable | None = None

@dataclass(frozen=True)
class _SymbolDeclarationFact:
    file_path: Path
    name: str
    line: int

@dataclass(frozen=True)
class _SymbolImportFact:
    file_path: Path
    local_name: str
    target_path: Path
    imported_name: str
    line: int

@dataclass(frozen=True)
class _SymbolAliasFact:
    file_path: Path
    alias: str
    target_name: str
    line: int

@dataclass(frozen=True)
class _SymbolExportFact:
    file_path: Path
    exported_name: str
    line: int
    local_name: str | None = None
    target_path: Path | None = None
    target_name: str | None = None

@dataclass(frozen=True)
class _StarExportFact:
    file_path: Path
    target_path: Path
    line: int

@dataclass(frozen=True)
class _NamespaceExportFact:
    file_path: Path
    exported_name: str
    target_path: Path
    line: int

@dataclass(frozen=True)
class _SymbolUseFact:
    file_path: Path
    source_id: str
    local_name: str
    relation: str
    context: str
    line: int

@dataclass
class _SymbolResolutionFacts:
    declarations: list[_SymbolDeclarationFact] = field(default_factory=list)
    imports: list[_SymbolImportFact] = field(default_factory=list)
    aliases: list[_SymbolAliasFact] = field(default_factory=list)
    exports: list[_SymbolExportFact] = field(default_factory=list)
    star_exports: list[_StarExportFact] = field(default_factory=list)
    namespace_exports: list[_NamespaceExportFact] = field(default_factory=list)
    uses: list[_SymbolUseFact] = field(default_factory=list)
    # File-to-file submodule imports from `from pkg import submod` (#1146).
    # Each entry is (importing_file, submodule_file, line).
    module_imports: list[tuple[Path, Path, int]] = field(default_factory=list)
