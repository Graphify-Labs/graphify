"""Deterministic structural extraction from source code using tree-sitter. Outputs nodes+edges dicts."""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .cache import load_cached, save_cached
from .mcp_ingest import extract_mcp_config, is_mcp_config_path
from .manifest_ingest import extract_package_manifest, is_package_manifest_path
from .resolver_registry import (
    LanguageResolver,
    register as register_language_resolver,
    run_language_resolvers,
)
from .ruby_resolution import resolve_ruby_member_calls
from .pascal_resolution import resolve_pascal_inherited_calls

# --- migrated to graphify/extractors/ (see graphify/extractors/MIGRATION.md) ---
from graphify.extractors.base import (  # noqa: F401
    _LANGUAGE_BUILTIN_GLOBALS,
    _file_stem,
    _make_id,
    _read_text,
)
from graphify.extractors.apex import extract_apex  # noqa: F401
from graphify.extractors.bash import extract_bash  # noqa: F401
from graphify.extractors.blade import extract_blade  # noqa: F401
from graphify.extractors.csharp import (
    _resolve_cross_file_csharp_imports,
    _resolve_csharp_type_references,
)
from graphify.extractors.dart import extract_dart  # noqa: F401
from graphify.extractors.dm import extract_dm, extract_dmf, extract_dmi, extract_dmm  # noqa: F401
from graphify.extractors.elixir import extract_elixir  # noqa: F401
from graphify.extractors.fortran import _cpp_preprocess, extract_fortran  # noqa: F401
from graphify.extractors.go import extract_go  # noqa: F401
from graphify.extractors.json_config import extract_json  # noqa: F401
from graphify.extractors.markdown import extract_markdown  # noqa: F401
from graphify.extractors.pascal_forms import extract_delphi_form, extract_lazarus_form  # noqa: F401
from graphify.extractors.powershell import extract_powershell, extract_powershell_manifest  # noqa: F401
from graphify.extractors.razor import extract_razor  # noqa: F401
from graphify.extractors.rust import extract_rust  # noqa: F401
from graphify.extractors.sln import extract_sln  # noqa: F401
from graphify.extractors.sql import extract_sql  # noqa: F401
from graphify.extractors.terraform import extract_terraform  # noqa: F401
from graphify.extractors.verilog import extract_verilog  # noqa: F401
from graphify.extractors.zig import extract_zig  # noqa: F401
from graphify.security import sanitize_metadata
from graphify.paths import disambiguate_ambiguous_candidates

from graphify.extractors.models import LanguageConfig, _JS_CACHE_BYPASS_SUFFIXES, _NamespaceExportFact, _StarExportFact, _SymbolAliasFact, _SymbolDeclarationFact, _SymbolExportFact, _SymbolImportFact, _SymbolResolutionFacts, _SymbolUseFact, _WORKSPACE_PACKAGE_CACHE  # noqa: E402,F401

from graphify.extractors.resolution import (  # noqa: E402,F401
    _DECLDEF_HEADER_SUFFIXES,
    _DECLDEF_IMPL_SUFFIXES,
    _EXPORT_CONDITION_PRIORITY,
    _JS_INDEX_FILES,
    _JS_PRIMITIVE_TYPES,
    _JS_RESOLVE_EXTS,
    _TSCONFIG_ALIAS_CACHE,
    _VUE_SCRIPT_LANG_RE,
    _VUE_SCRIPT_RE,
    _WORKSPACE_MANIFEST_NAMES,
    _apply_symbol_resolution_facts,
    _augment_symbol_resolution_edges,
    _collect_js_symbol_resolution_facts,
    _collect_python_symbol_resolution_facts,
    _contained_in_package,
    _decldef_class_stem,
    _disambiguate_colliding_node_ids,
    _find_workspace_root,
    _is_type_like_definition,
    _js_call_identifier,
    _js_default_export_name,
    _js_default_import_name,
    _js_export_clause,
    _js_export_statement_is_star,
    _js_exported_declaration_names,
    _js_lexical_aliases,
    _js_module_specifier,
    _js_named_specifiers,
    _js_namespace_export_name,
    _js_source_path,
    _js_top_level_function_bodies,
    _load_tsconfig_aliases,
    _load_workspace_packages,
    _match_tsconfig_alias,
    _merge_decl_def_classes,
    _node_disambiguation_source_key,
    _package_entry_candidates,
    _parse_js_tree,
    _parse_python_tree,
    _pascal_class_stem_cache,
    _pascal_project_root,
    _pascal_resolve_class,
    _pascal_resolve_unit,
    _pascal_unit_cache,
    _pnpm_workspace_globs,
    _python_call_identifier,
    _python_import_from_module,
    _python_imported_names,
    _python_top_level_function_bodies,
    _read_tsconfig_aliases,
    _resolve_c_include_path,
    _resolve_cross_file_imports,
    _resolve_cross_file_java_imports,
    _resolve_export_target,
    _resolve_java_type_references,
    _resolve_js_import_path,
    _resolve_js_import_target,
    _resolve_js_module_path,
    _resolve_lua_import_target,
    _resolve_python_module_path,
    _resolve_tsconfig_alias,
    _resolve_workspace_import,
    _source_key,
    _strip_jsonc,
    _ts_collect_type_refs,
    _ts_heritage_clause_entries,
    _ts_walk_class_members,
    _vue_mask_non_script,
    _walk_js_tree,
    _walk_python_tree,
    _workspace_globs,
)

from graphify.extractors.engine import REFERENCE_CONTEXTS, _CSHARP_TYPE_PARAMETER_SCOPE_DECLARATIONS, _C_PRIMITIVE_TYPE_NODES, _JAVA_BUILTIN_TYPES, _JAVA_TYPE_PARAMETER_SCOPE_DECLARATIONS, _JS_FUNCTION_VALUE_TYPES, _JS_SCOPE_BOUNDARY, _PYTHON_ANNOTATION_NOISE, _PYTHON_TYPE_CONTAINERS, _RUBY_CLASS_FACTORIES, _c_collect_type_refs, _cpp_collect_type_refs, _cpp_declarator_name, _cpp_local_var_types, _csharp_attribute_names, _csharp_classify_base, _csharp_collect_type_refs, _csharp_extra_walk, _csharp_member_type_table, _csharp_namespace_id, _csharp_namespace_name, _csharp_pre_scan_interfaces, _csharp_type_parameters_in_scope, _dynamic_import_js, _extract_generic, _find_body, _find_require_call, _get_cpp_func_name, _java_annotation_names, _java_collect_type_refs, _java_extra_walk, _java_type_parameters_in_scope, _js_collect_pattern_idents, _js_dispatch_value_idents, _js_extra_walk, _js_local_bound_names, _js_member_assignment_target, _js_module_bound_names, _kotlin_collect_type_refs, _kotlin_function_return_type_node, _kotlin_property_type_node, _kotlin_user_type_name, _php_collect_type_refs, _php_method_return_type_node, _php_name_text, _python_collect_assignment_targets, _python_collect_param_refs, _python_collect_type_refs, _python_local_bound_names, _python_module_bound_names, _python_param_names, _read_csharp_type_name, _require_imports_js, _ruby_const_last_name, _ruby_extra_walk, _ruby_local_class_bindings, _ruby_new_class_name, _scala_collect_type_refs, _semantic_reference_edge, _source_location, _swift_classify_base, _swift_collect_type_refs, _swift_constructor_type, _swift_declaration_keyword, _swift_extra_walk, _swift_local_var_types, _swift_pre_scan, _swift_property_name, _swift_property_type_node, _swift_receiver_name, _swift_user_type_name, _ts_decorator_name, _ts_descendant_decorators, _ts_emit_decorator_edges, _ts_extra_walk, _ts_method_name, _ts_receiver_type_table  # noqa: E402,F401

from graphify.extractors.pascal import _PAS_BEGIN_END_TOKEN_RE, _PAS_CALL_RE, _PAS_END_SEMI_RE, _PAS_IMPL_HEADER_RE, _PAS_KEYWORDS, _PAS_METHOD_DECL_RE, _PAS_MODULE_RE, _PAS_TOKEN_RE, _PAS_TYPE_HEADER_RE, _PAS_USES_RE, _extract_pascal_regex, _pascal_find_body, _pascal_split_bases, _pascal_split_sections, _pascal_split_uses, _pascal_strip_comments, extract_pascal  # noqa: E402,F401

from graphify.extractors.objc import _objc_local_var_types, extract_objc  # noqa: E402,F401

from graphify.extractors.julia import extract_julia  # noqa: E402,F401

_RECURSION_LIMIT = 10_000

# Language built-in globals that AST may classify as call targets when used as
# constructors or coercion functions (e.g. String(x), Number(x), Boolean(x)).
# Without this filter they become god-nodes accumulating spurious edges from
# every call site. Filter applied at same-file and cross-file resolution.
# See issue #726.


def _raise_recursion_limit() -> None:
    if sys.getrecursionlimit() < _RECURSION_LIMIT:
        sys.setrecursionlimit(_RECURSION_LIMIT)


def _safe_extract(extractor: Callable, path: Path) -> dict:
    try:
        return extractor(path)
    except RecursionError:
        print(f"  warning: skipped {path} (recursion limit exceeded)", file=sys.stderr, flush=True)
        return {"nodes": [], "edges": [], "error": "recursion_limit_exceeded"}
    except Exception as e:
        if os.environ.get("GRAPHIFY_DEBUG"):
            import traceback
            traceback.print_exc(file=sys.stderr)
        print(f"  warning: skipped {path} ({type(e).__name__}: {e})", file=sys.stderr, flush=True)
        return {"nodes": [], "edges": [], "error": f"{type(e).__name__}: {e}"}


def _file_node_id(rel_path: Path) -> str:
    """File-level node ID matching the skill.md spec: ``{parent_dir}_{stem}`` —
    one parent directory level, no extension. ``rel_path`` MUST be relative to
    the project root so top-level files collapse to a bare stem (``setup.py`` ->
    ``setup``) instead of picking up the root directory name. This must equal the
    ID semantic subagents generate, or AST and semantic extraction split a file
    into two disconnected ghost nodes (#1033)."""
    return _make_id(_file_stem(rel_path))


SEMANTIC_RELATIONS = frozenset({
    "inherits", "implements", "mixes_in", "embeds", "references",
    "calls", "imports", "imports_from", "re_exports", "contains", "method",
})


# Condition keys consulted when resolving an `exports` target, in priority
# order. `default` is Node's catch-all and must be consulted LAST so a more
# specific condition (source/import/module/etc.) wins when several match.


# ── LanguageConfig dataclass ─────────────────────────────────────────────────


# ── Generic helpers ───────────────────────────────────────────────────────────


# Scalar builtins and test-mock names that appear as type annotations but carry
# no useful semantic meaning as graph nodes (#1147). Suppressed at the annotation
# walker level so they are never created as nodes or emitted as edges.


# java.lang (auto-imported) plus the ubiquitous java.util / java.io / java.time /
# java.util.{stream,function,concurrent} / java.math / java.nio.file types that
# appear as field, parameter, return, and generic-argument annotations. They never
# resolve to a project node, so emitting `references` edges to them is pure noise
# (mirrors _GO_PREDECLARED_TYPES / _PYTHON_ANNOTATION_NOISE). Suppressed at the
# type-ref walker so they are never created as nodes or emitted as edges. The
# boxed-scalar/`void` primitives are already dropped by grammar node type above;
# these are the class/interface names the grammar reports as identifiers.


# ── C / C++ type-ref helpers ─────────────────────────────────────────────────


# ── Scala type-ref helpers ───────────────────────────────────────────────────


def _resolve_name(node, source: bytes, config: LanguageConfig) -> str | None:
    """Get the name from a node using config.name_field, falling back to child types."""
    if config.resolve_function_name_fn is not None:
        # For C/C++ where the name is inside a declarator
        return None  # caller handles this separately
    n = node.child_by_field_name(config.name_field)
    if n:
        return _read_text(n, source)
    for child in node.children:
        if child.type in config.name_fallback_child_types:
            return _read_text(child, source)
    return None


# ── Import handlers ───────────────────────────────────────────────────────────

def _import_python(node, source: bytes, file_nid: str, stem: str, edges: list, str_path: str, scope_stack: list[str] | None = None) -> None:
    t = node.type
    if t == "import_statement":
        for child in node.children:
            if child.type in ("dotted_name", "aliased_import"):
                raw = _read_text(child, source)
                module_name = raw.split(" as ")[0].strip().lstrip(".")
                tgt_nid = _make_id(module_name)
                edges.append({
                    "source": file_nid,
                    "target": tgt_nid,
                    "relation": "imports",
                    "context": "import",
                    "confidence": "EXTRACTED",
                    "source_file": str_path,
                    "source_location": f"L{node.start_point[0] + 1}",
                    "weight": 1.0,
                })
    elif t == "import_from_statement":
        module_node = node.child_by_field_name("module_name")
        if module_node:
            raw = _read_text(module_node, source)
            if raw.startswith("."):
                # Relative import - resolve to full path so IDs match file node IDs
                dots = len(raw) - len(raw.lstrip("."))
                module_name = raw.lstrip(".")
                base = Path(str_path).parent
                for _ in range(dots - 1):
                    base = base.parent
                rel = (module_name.replace(".", "/") + ".py") if module_name else "__init__.py"
                tgt_nid = _make_id(str(base / rel))
            else:
                tgt_nid = _make_id(raw)
            edges.append({
                "source": file_nid,
                "target": tgt_nid,
                "relation": "imports_from",
                "context": "import",
                "confidence": "EXTRACTED",
                "source_file": str_path,
                "source_location": f"L{node.start_point[0] + 1}",
                "weight": 1.0,
            })


def _import_js(node, source: bytes, file_nid: str, stem: str, edges: list, str_path: str, scope_stack: list[str] | None = None) -> None:
    is_reexport = node.type == "export_statement"
    # Only handle export_statement if it has a `from` clause (re-export).
    # Pure exports like `export const x = 1` or `export { localVar }` have no source module.
    if is_reexport:
        has_from = any(child.type == "from" or (_read_text(child, source) == "from") for child in node.children if child.type in ("from", "identifier"))
        if not has_from:
            # Check for string child (source path) as a more reliable indicator
            has_from = any(child.type == "string" for child in node.children)
            if not has_from:
                return

    resolved_path: "Path | None" = None
    module_string = None
    for child in node.children:
        if child.type == "string":
            module_string = child
            break
        if child.type == "import_require_clause":
            # TS import-equals form: `import x = require("./m")`. The module
            # string sits inside the clause, not on the import_statement
            # itself, so the direct-child scan above never sees it.
            module_string = next(
                (sub for sub in child.children if sub.type == "string"), None
            )
            break
    if module_string is not None:
        raw = _read_text(module_string, source).strip("'\"` ")
        resolved = _resolve_js_import_target(raw, str_path)
        if resolved is not None:
            tgt_nid, resolved_path = resolved
            edges.append({
                "source": file_nid,
                "target": tgt_nid,
                "relation": "imports_from",
                "context": "re-export" if is_reexport else "import",
                "confidence": "EXTRACTED",
                "source_file": str_path,
                "source_location": f"L{node.start_point[0] + 1}",
                "weight": 1.0,
            })

    # Emit symbol-level edges for named imports/re-exports from local/aliased files.
    # e.g. `import { Foo, type Bar } from './bar'` → file → Foo, file → Bar (EXTRACTED)
    # e.g. `export { Foo } from './bar'` → file → Foo (re_exports edge)
    # Uses the same _make_id(target_stem, name) key that _extract_generic emits when
    # defining the symbol, so these edges wire importers directly to existing symbol nodes.
    if resolved_path is not None:
        target_stem = _file_stem(resolved_path)
        line = node.start_point[0] + 1

        if is_reexport:
            # Handle: export { foo, bar } from './module'
            #         export { default as baz } from './module'
            for child in node.children:
                if child.type == "export_clause":
                    for spec in child.children:
                        if spec.type == "export_specifier":
                            # The exported name is the local name from the source module
                            name_node = spec.child_by_field_name("name")
                            if name_node:
                                sym = _read_text(name_node, source)
                                if sym == "default":
                                    continue  # skip default re-exports for ID matching
                                edges.append({
                                    "source": file_nid,
                                    "target": _make_id(target_stem, sym),
                                    "relation": "re_exports",
                                    "context": "re-export",
                                    "confidence": "EXTRACTED",
                                    "source_file": str_path,
                                    "source_location": f"L{line}",
                                    "weight": 1.0,
                                })
        else:
            # Handle: import { Foo, type Bar } from './bar'
            for child in node.children:
                if child.type == "import_clause":
                    for sub in child.children:
                        if sub.type == "named_imports":
                            for spec in sub.children:
                                if spec.type == "import_specifier":
                                    name_node = spec.child_by_field_name("name")
                                    if name_node:
                                        sym = _read_text(name_node, source)
                                        edges.append({
                                            "source": file_nid,
                                            "target": _make_id(target_stem, sym),
                                            "relation": "imports",
                                            "context": "import",
                                            "confidence": "EXTRACTED",
                                            "source_file": str_path,
                                            "source_location": f"L{line}",
                                            "weight": 1.0,
                                        })


def _import_java(node, source: bytes, file_nid: str, stem: str, edges: list, str_path: str, scope_stack: list[str] | None = None) -> None:
    def _walk_scoped(n) -> str:
        parts: list[str] = []
        cur = n
        while cur:
            if cur.type == "scoped_identifier":
                name_node = cur.child_by_field_name("name")
                if name_node:
                    parts.append(_read_text(name_node, source))
                cur = cur.child_by_field_name("scope")
            elif cur.type == "identifier":
                parts.append(_read_text(cur, source))
                break
            else:
                break
        parts.reverse()
        return ".".join(parts)

    for child in node.children:
        if child.type in ("scoped_identifier", "identifier"):
            path_str = _walk_scoped(child)
            module_name = path_str.split(".")[-1].strip("*").strip(".") or (
                path_str.split(".")[-2] if len(path_str.split(".")) > 1 else path_str
            )
            if module_name:
                tgt_nid = _make_id(module_name)
                edges.append({
                    "source": file_nid,
                    "target": tgt_nid,
                    "relation": "imports",
                    "context": "import",
                    "confidence": "EXTRACTED",
                    "source_file": str_path,
                    "source_location": f"L{node.start_point[0] + 1}",
                    "weight": 1.0,
                })
            break


def _import_c(node, source: bytes, file_nid: str, stem: str, edges: list, str_path: str, scope_stack: list[str] | None = None) -> None:
    for child in node.children:
        if child.type in ("string_literal", "system_lib_string", "string"):
            raw = _read_text(child, source).strip('"<> ')
            # Quoted includes: try to resolve to a real file so the target ID
            # matches the node ID _extract_generic creates for that file.
            if child.type != "system_lib_string":
                resolved = _resolve_c_include_path(raw, str_path)
                if resolved is not None:
                    tgt_nid = _make_id(str(resolved))
                    edges.append({
                        "source": file_nid,
                        "target": tgt_nid,
                        "relation": "imports",
                        "context": "import",
                        "confidence": "EXTRACTED",
                        "source_file": str_path,
                        "source_location": f"L{node.start_point[0] + 1}",
                        "weight": 1.0,
                    })
                    break
            module_name = raw.split("/")[-1].split(".")[0]
            if module_name:
                tgt_nid = _make_id(module_name)
                edges.append({
                    "source": file_nid,
                    "target": tgt_nid,
                    "relation": "imports",
                    "context": "import",
                    "confidence": "EXTRACTED",
                    "source_file": str_path,
                    "source_location": f"L{node.start_point[0] + 1}",
                    "weight": 1.0,
                })
            break


def _import_csharp(node, source: bytes, file_nid: str, stem: str, edges: list, str_path: str, scope_stack: list[str] | None = None) -> None:
    text = _read_text(node, source).strip().rstrip(";")
    if text.startswith("global "):
        text = text[len("global "):].strip()
    if not text.startswith("using"):
        return
    body = text[len("using"):].strip()
    using_kind, alias, target_fqn = "namespace", None, body
    if body.startswith("static "):
        using_kind, target_fqn = "static", body[len("static "):].strip()
    elif "=" in body:
        lhs, rhs = body.split("=", 1)
        using_kind, alias, target_fqn = "alias", lhs.strip(), rhs.strip()
    if not target_fqn:
        return
    edges.append({
        "source": file_nid,
        "target": _make_id(target_fqn),
        "relation": "imports",
        "context": "import",
        "confidence": "EXTRACTED",
        "source_file": str_path,
        "source_location": f"L{node.start_point[0] + 1}",
        "weight": 1.0,
        "metadata": sanitize_metadata({k: v for k, v in
            {"using_kind": using_kind, "alias": alias, "target_fqn": target_fqn,
             "scope_kind": "namespace" if scope_stack else "file",
             "scope_id": scope_stack[-1] if scope_stack else None}.items() if v is not None}),
    })


def _import_kotlin(node, source: bytes, file_nid: str, stem: str, edges: list, str_path: str, scope_stack: list[str] | None = None) -> None:
    path_node = node.child_by_field_name("path")
    if path_node:
        raw = _read_text(path_node, source)
        module_name = raw.split(".")[-1].strip()
        if module_name:
            tgt_nid = _make_id(module_name)
            edges.append({
                "source": file_nid,
                "target": tgt_nid,
                "relation": "imports",
                "context": "import",
                "confidence": "EXTRACTED",
                "source_file": str_path,
                "source_location": f"L{node.start_point[0] + 1}",
                "weight": 1.0,
            })
        return
    # Fallback: find identifier child
    for child in node.children:
        if child.type == "identifier":
            raw = _read_text(child, source)
            tgt_nid = _make_id(raw)
            edges.append({
                "source": file_nid,
                "target": tgt_nid,
                "relation": "imports",
                "context": "import",
                "confidence": "EXTRACTED",
                "source_file": str_path,
                "source_location": f"L{node.start_point[0] + 1}",
                "weight": 1.0,
            })
            break


def _import_scala(node, source: bytes, file_nid: str, stem: str, edges: list, str_path: str, scope_stack: list[str] | None = None) -> None:
    for child in node.children:
        if child.type in ("stable_id", "identifier"):
            raw = _read_text(child, source)
            module_name = raw.split(".")[-1].strip("{} ")
            if module_name and module_name != "_":
                tgt_nid = _make_id(module_name)
                edges.append({
                    "source": file_nid,
                    "target": tgt_nid,
                    "relation": "imports",
                    "context": "import",
                    "confidence": "EXTRACTED",
                    "source_file": str_path,
                    "source_location": f"L{node.start_point[0] + 1}",
                    "weight": 1.0,
                })
            break


def _import_php(node, source: bytes, file_nid: str, stem: str, edges: list, str_path: str, scope_stack: list[str] | None = None) -> None:
    for child in node.children:
        if child.type in ("qualified_name", "name", "identifier"):
            raw = _read_text(child, source)
            module_name = raw.split("\\")[-1].strip()
            if module_name:
                tgt_nid = _make_id(module_name)
                edges.append({
                    "source": file_nid,
                    "target": tgt_nid,
                    "relation": "imports",
                    "context": "import",
                    "confidence": "EXTRACTED",
                    "source_file": str_path,
                    "source_location": f"L{node.start_point[0] + 1}",
                    "weight": 1.0,
                })
            break


# ── C/C++ function name helpers ───────────────────────────────────────────────

def _get_c_func_name(node, source: bytes) -> str | None:
    """Recursively unwrap declarator to find the innermost identifier (C)."""
    if node.type == "identifier":
        return _read_text(node, source)
    decl = node.child_by_field_name("declarator")
    if decl:
        return _get_c_func_name(decl, source)
    for child in node.children:
        if child.type == "identifier":
            return _read_text(child, source)
    return None


# ── JS/TS extra walk for arrow functions ──────────────────────────────────────


# Node types whose value is a callable, for the JS/TS assignment / class-field
# / function-expression forms below. Older tree-sitter-javascript grammars
# label a function expression `function`; current ones use `function_expression`.


# ── TS extra walk for namespace / module declarations ─────────────────────────


# ── C# extra walk for namespace declarations ──────────────────────────────────


# ── Swift extra walk for enum cases ──────────────────────────────────────────


# ── Java extra walk for enum constants ───────────────────────────────────────


# ── Language configs ──────────────────────────────────────────────────────────

_PYTHON_CONFIG = LanguageConfig(
    ts_module="tree_sitter_python",
    class_types=frozenset({"class_definition"}),
    function_types=frozenset({"function_definition"}),
    import_types=frozenset({"import_statement", "import_from_statement"}),
    call_types=frozenset({"call"}),
    call_function_field="function",
    call_accessor_node_types=frozenset({"attribute"}),
    call_accessor_field="attribute",
    call_accessor_object_field="object",
    function_boundary_types=frozenset({"function_definition"}),
    import_handler=_import_python,
)

_JS_CONFIG = LanguageConfig(
    ts_module="tree_sitter_javascript",
    class_types=frozenset({"class_declaration"}),
    function_types=frozenset({"function_declaration", "generator_function_declaration", "method_definition"}),
    import_types=frozenset({"import_statement", "export_statement"}),
    call_types=frozenset({"call_expression", "new_expression"}),
    call_function_field="function",
    call_accessor_node_types=frozenset({"member_expression"}),
    call_accessor_field="property",
    call_accessor_object_field="object",
    function_boundary_types=frozenset({"function_declaration", "generator_function_declaration", "arrow_function", "method_definition"}),
    import_handler=_import_js,
)

_TS_CONFIG = LanguageConfig(
    ts_module="tree_sitter_typescript",
    ts_language_fn="language_typescript",
    class_types=frozenset({
        "class_declaration",
        "abstract_class_declaration",  # TS abstract class
        "interface_declaration",   # parity with Java/C#
        "enum_declaration",        # named enums
        "type_alias_declaration",  # named type aliases
    }),
    function_types=frozenset({"function_declaration", "generator_function_declaration", "method_definition", "method_signature"}),
    import_types=frozenset({"import_statement", "export_statement"}),
    call_types=frozenset({"call_expression", "new_expression"}),
    call_function_field="function",
    call_accessor_node_types=frozenset({"member_expression"}),
    call_accessor_field="property",
    call_accessor_object_field="object",
    function_boundary_types=frozenset({"function_declaration", "generator_function_declaration", "arrow_function", "method_definition"}),
    import_handler=_import_js,
)

# .tsx files must use the TSX grammar (JSX-aware), not the plain TypeScript grammar.
# tree-sitter-typescript ships two languages: language_typescript (for .ts) and
# language_tsx (for .tsx). Parsing .tsx with language_typescript silently fails on
# JSX expressions, dropping any call_expression nested inside JSX (e.g. {fmtDate(x)}).
_TSX_CONFIG = LanguageConfig(
    ts_module="tree_sitter_typescript",
    ts_language_fn="language_tsx",
    class_types=_TS_CONFIG.class_types,
    function_types=_TS_CONFIG.function_types,
    import_types=_TS_CONFIG.import_types,
    call_types=_TS_CONFIG.call_types,
    call_function_field=_TS_CONFIG.call_function_field,
    call_accessor_node_types=_TS_CONFIG.call_accessor_node_types,
    call_accessor_field=_TS_CONFIG.call_accessor_field,
    call_accessor_object_field=_TS_CONFIG.call_accessor_object_field,
    function_boundary_types=_TS_CONFIG.function_boundary_types,
    import_handler=_TS_CONFIG.import_handler,
)

_JAVA_CONFIG = LanguageConfig(
    ts_module="tree_sitter_java",
    # record_declaration shares class_declaration's name/body/interfaces fields,
    # so it becomes a first-class type node instead of an isolated file (#1373).
    # Enums and annotation declarations use the same name/body contract.
    class_types=frozenset({
        "class_declaration", "interface_declaration", "record_declaration",
        "enum_declaration", "annotation_type_declaration",
    }),
    function_types=frozenset({"method_declaration", "constructor_declaration"}),
    import_types=frozenset({"import_declaration"}),
    # object_creation_expression (`new Foo(...)`) is handled by a dedicated Java
    # branch in walk_calls below — its callee is in the `type` field, not `name`.
    call_types=frozenset({"method_invocation", "object_creation_expression"}),
    call_function_field="name",
    call_accessor_node_types=frozenset(),
    function_boundary_types=frozenset({"method_declaration", "constructor_declaration"}),
    import_handler=_import_java,
)

_GROOVY_CONFIG = LanguageConfig(
    ts_module="tree_sitter_groovy",
    class_types=frozenset({"class_declaration", "interface_declaration"}),
    function_types=frozenset({"method_declaration", "constructor_declaration"}),
    import_types=frozenset({"import_declaration"}),
    call_types=frozenset({"method_invocation"}),
    call_function_field="name",
    call_accessor_node_types=frozenset(),
    function_boundary_types=frozenset({"method_declaration", "constructor_declaration"}),
    import_handler=_import_java,
)

_C_CONFIG = LanguageConfig(
    ts_module="tree_sitter_c",
    class_types=frozenset(),
    function_types=frozenset({"function_definition"}),
    import_types=frozenset({"preproc_include"}),
    call_types=frozenset({"call_expression"}),
    call_function_field="function",
    call_accessor_node_types=frozenset({"field_expression"}),
    call_accessor_field="field",
    function_boundary_types=frozenset({"function_definition"}),
    import_handler=_import_c,
    resolve_function_name_fn=_get_c_func_name,
)

_CPP_CONFIG = LanguageConfig(
    ts_module="tree_sitter_cpp",
    class_types=frozenset({"class_specifier", "struct_specifier"}),
    function_types=frozenset({"function_definition"}),
    import_types=frozenset({"preproc_include"}),
    call_types=frozenset({"call_expression"}),
    call_function_field="function",
    call_accessor_node_types=frozenset({"field_expression", "qualified_identifier"}),
    call_accessor_field="field",
    function_boundary_types=frozenset({"function_definition"}),
    import_handler=_import_c,
    resolve_function_name_fn=_get_cpp_func_name,
)

_RUBY_CONFIG = LanguageConfig(
    ts_module="tree_sitter_ruby",
    # `module Foo` is a container node just like `class Foo` in tree-sitter's
    # Ruby grammar (name in a `constant` child, body in `body_statement`), so it
    # gets a node and its methods attach via `method` (#1640). Without it, plain
    # utility/`module_function` modules produced no node and their methods hung
    # off the file via `contains` with dot-less labels.
    class_types=frozenset({"class", "module"}),
    function_types=frozenset({"method", "singleton_method"}),
    import_types=frozenset(),
    call_types=frozenset({"call"}),
    call_function_field="method",
    call_accessor_node_types=frozenset(),
    name_fallback_child_types=("constant", "scope_resolution", "identifier"),
    body_fallback_child_types=("body_statement",),
    function_boundary_types=frozenset({"method", "singleton_method"}),
)

_CSHARP_CONFIG = LanguageConfig(
    ts_module="tree_sitter_c_sharp",
    class_types=frozenset({
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
        "struct_declaration",
        "record_declaration",
    }),
    function_types=frozenset({"method_declaration"}),
    import_types=frozenset({"using_directive"}),
    call_types=frozenset({"invocation_expression"}),
    call_function_field="function",
    call_accessor_node_types=frozenset({"member_access_expression"}),
    call_accessor_field="name",
    body_fallback_child_types=("declaration_list",),
    function_boundary_types=frozenset({"method_declaration"}),
    import_handler=_import_csharp,
)

_KOTLIN_CONFIG = LanguageConfig(
    ts_module="tree_sitter_kotlin",
    class_types=frozenset({"class_declaration", "object_declaration"}),
    function_types=frozenset({"function_declaration"}),
    import_types=frozenset({"import_header"}),
    call_types=frozenset({"call_expression"}),
    call_function_field="",
    call_accessor_node_types=frozenset({"navigation_expression"}),
    call_accessor_field="",
    # Different tree-sitter-kotlin grammar versions name plain identifier
    # nodes differently: PyPI's `tree_sitter_kotlin` uses `identifier`,
    # older forks use `simple_identifier`. Accept both so the extractor
    # works across grammar generations.
    name_fallback_child_types=("simple_identifier", "identifier"),
    body_fallback_child_types=("function_body", "class_body", "enum_class_body"),
    function_boundary_types=frozenset({"function_declaration"}),
    import_handler=_import_kotlin,
)

_SCALA_CONFIG = LanguageConfig(
    ts_module="tree_sitter_scala",
    class_types=frozenset({"class_definition", "object_definition"}),
    function_types=frozenset({"function_definition"}),
    import_types=frozenset({"import_declaration"}),
    call_types=frozenset({"call_expression"}),
    call_function_field="",
    call_accessor_node_types=frozenset({"field_expression"}),
    call_accessor_field="field",
    name_fallback_child_types=("identifier",),
    body_fallback_child_types=("template_body",),
    function_boundary_types=frozenset({"function_definition"}),
    import_handler=_import_scala,
)

_PHP_CONFIG = LanguageConfig(
    ts_module="tree_sitter_php",
    ts_language_fn="language_php",
    class_types=frozenset({"class_declaration"}),
    function_types=frozenset({"function_definition", "method_declaration"}),
    import_types=frozenset({"namespace_use_clause"}),
    call_types=frozenset({"function_call_expression", "member_call_expression", "scoped_call_expression", "class_constant_access_expression"}),
    static_prop_types=frozenset({"scoped_property_access_expression"}),
    helper_fn_names=frozenset({"config"}),
    container_bind_methods=frozenset({"bind", "singleton", "scoped", "instance"}),
    event_listener_properties=frozenset({"listen", "subscribe"}),
    call_function_field="function",
    call_accessor_node_types=frozenset({"member_call_expression"}),
    call_accessor_field="name",
    name_fallback_child_types=("name",),
    body_fallback_child_types=("declaration_list", "compound_statement"),
    function_boundary_types=frozenset({"function_definition", "method_declaration"}),
    import_handler=_import_php,
)


def _import_lua(node, source: bytes, file_nid: str, stem: str, edges: list, str_path: str, scope_stack: list[str] | None = None) -> None:
    """Extract require('module') from Lua variable_declaration nodes."""
    text = _read_text(node, source)
    import re
    m = re.search(r"""require\s*[\('"]\s*['"]?([^'")\s]+)""", text)
    if m:
        raw_module = m.group(1)
        if raw_module:
            tgt_nid = _resolve_lua_import_target(raw_module, str_path)
            if tgt_nid:
                edges.append({
                    "source": file_nid,
                    "target": tgt_nid,
                    "relation": "imports",
                    "context": "import",
                    "confidence": "EXTRACTED",
                    "confidence_score": 1.0,
                    "source_file": str_path,
                    "source_location": str(node.start_point[0] + 1),
                    "weight": 1.0,
                })


_LUA_CONFIG = LanguageConfig(
    ts_module="tree_sitter_lua",
    ts_language_fn="language",
    class_types=frozenset(),
    function_types=frozenset({"function_declaration"}),
    import_types=frozenset({"variable_declaration"}),
    call_types=frozenset({"function_call"}),
    call_function_field="name",
    call_accessor_node_types=frozenset({"method_index_expression"}),
    call_accessor_field="name",
    name_fallback_child_types=("identifier", "method_index_expression"),
    body_fallback_child_types=("block",),
    function_boundary_types=frozenset({"function_declaration"}),
    import_handler=_import_lua,
)


def _import_swift(node, source: bytes, file_nid: str, stem: str, edges: list, str_path: str, scope_stack: list[str] | None = None) -> list[tuple[str, str]]:
    """Emit module-level ``imports`` edges and report the imported modules.

    A Swift ``import CoreKit`` names a module, not a file path, so — unlike the
    file-resolving JS/TS handlers — there is no existing node for the edge to
    point at. The returned ``(id, label)`` pairs let the extractor materialize a
    ``type=module`` anchor node so the edge survives; without it ``build_from_json``
    prunes every Swift import edge as a dangling/external reference (#1327).
    """
    modules: list[tuple[str, str]] = []
    for child in node.children:
        if child.type == "identifier":
            raw = _read_text(child, source)
            tgt_nid = _make_id(raw)
            edges.append({
                "source": file_nid,
                "target": tgt_nid,
                "relation": "imports",
                "context": "import",
                "confidence": "EXTRACTED",
                "source_file": str_path,
                "source_location": f"L{node.start_point[0] + 1}",
                "weight": 1.0,
            })
            modules.append((tgt_nid, raw))
            break
    return modules


_SWIFT_CONFIG = LanguageConfig(
    ts_module="tree_sitter_swift",
    class_types=frozenset({"class_declaration", "protocol_declaration"}),
    function_types=frozenset({"function_declaration", "init_declaration", "deinit_declaration", "subscript_declaration"}),
    import_types=frozenset({"import_declaration"}),
    call_types=frozenset({"call_expression"}),
    call_function_field="",
    call_accessor_node_types=frozenset({"navigation_expression"}),
    call_accessor_field="",
    name_fallback_child_types=("simple_identifier", "type_identifier", "user_type"),
    body_fallback_child_types=("class_body", "protocol_body", "function_body", "enum_class_body"),
    function_boundary_types=frozenset({"function_declaration", "init_declaration", "deinit_declaration", "subscript_declaration"}),
    import_handler=_import_swift,
)

# ── Ruby local type inference (for member-call resolution) ─────────────────────


# `Const = <factory>(...)` shapes that define a lightweight class named after the
# constant. tree-sitter parses each as an `assignment`, not a `class`, so the
# generic class branch never saw them (#1640).


# ── Generic extractor ─────────────────────────────────────────────────────────


# ── Python rationale extraction ───────────────────────────────────────────────

_RATIONALE_PREFIXES = ("# NOTE:", "# IMPORTANT:", "# HACK:", "# WHY:", "# RATIONALE:", "# TODO:", "# FIXME:")


def _is_autogenerated_python(source: bytes) -> bool:
    """Return True if this Python file is auto-generated and its module docstring is noise.

    Covers: Alembic/Flask-Migrate revisions, Django migrations, protobuf/gRPC/OpenAPI stubs.
    Module docstrings in these files are change annotations or boilerplate, not rationale.
    """
    head = source[:2048].decode("utf-8", errors="replace")
    # Generic generated-file markers (protobuf, gRPC, OpenAPI codegen, etc.)
    if any(m in head for m in ("DO NOT EDIT", "@generated", "Generated by the protocol buffer")):
        return True
    # Alembic / Flask-Migrate revision files
    if (re.search(r"^revision\s*[:=]", head, re.MULTILINE)
            and "def upgrade(" in head
            and "down_revision" in head):
        return True
    # Django migrations
    if "class Migration(migrations.Migration)" in head and "operations" in head:
        return True
    return False


def _extract_python_rationale(path: Path, result: dict) -> None:
    """Post-pass: extract docstrings and rationale comments from Python source.
    Mutates result in-place by appending to result['nodes'] and result['edges'].
    """
    try:
        import tree_sitter_python as tspython
        from tree_sitter import Language, Parser
        language = Language(tspython.language())
        parser = Parser(language)
        source = path.read_bytes()
        tree = parser.parse(source)
        root = tree.root_node
    except Exception:
        return

    stem = _file_stem(path)
    str_path = str(path)
    nodes = result["nodes"]
    edges = result["edges"]
    seen_ids = {n["id"] for n in nodes}
    file_nid = _make_id(str(path))

    def _get_docstring(body_node) -> tuple[str, int] | None:
        if not body_node:
            return None
        for child in body_node.children:
            if child.type == "expression_statement":
                for sub in child.children:
                    if sub.type in ("string", "concatenated_string"):
                        text = source[sub.start_byte:sub.end_byte].decode("utf-8", errors="replace")
                        text = text.strip("\"'").strip('"""').strip("'''").strip()
                        if len(text) > 20:
                            return text, child.start_point[0] + 1
            break
        return None

    def _add_rationale(text: str, line: int, parent_nid: str) -> None:
        label = text[:80].replace("\r\n", " ").replace("\r", " ").replace("\n", " ").strip()
        rid = _make_id(stem, "rationale", str(line))
        if rid not in seen_ids:
            seen_ids.add(rid)
            nodes.append({
                "id": rid,
                "label": label,
                "file_type": "rationale",
                "source_file": str_path,
                "source_location": f"L{line}",
            })
        edges.append({
            "source": rid,
            "target": parent_nid,
            "relation": "rationale_for",
            "confidence": "EXTRACTED",
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": 1.0,
        })

    # Module-level docstring — skip for auto-generated files (Alembic, Django
    # migrations, protobuf stubs, etc.) whose module docstrings are revision
    # annotations, not architectural rationale.
    if not _is_autogenerated_python(source):
        ds = _get_docstring(root)
        if ds:
            _add_rationale(ds[0], ds[1], file_nid)

    # Class and function docstrings
    def walk_docstrings(node, parent_nid: str) -> None:
        t = node.type
        if t == "class_definition":
            name_node = node.child_by_field_name("name")
            body = node.child_by_field_name("body")
            if name_node and body:
                class_name = source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                nid = _make_id(stem, class_name)
                ds = _get_docstring(body)
                if ds:
                    _add_rationale(ds[0], ds[1], nid)
                for child in body.children:
                    walk_docstrings(child, nid)
            return
        if t == "function_definition":
            name_node = node.child_by_field_name("name")
            body = node.child_by_field_name("body")
            if name_node and body:
                func_name = source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                nid = _make_id(parent_nid, func_name) if parent_nid != file_nid else _make_id(stem, func_name)
                ds = _get_docstring(body)
                if ds:
                    _add_rationale(ds[0], ds[1], nid)
            return
        for child in node.children:
            walk_docstrings(child, parent_nid)

    walk_docstrings(root, file_nid)

    # Rationale comments (# NOTE:, # IMPORTANT:, etc.)
    source_text = source.decode("utf-8", errors="replace")
    for lineno, line_text in enumerate(source_text.splitlines(), start=1):
        stripped = line_text.strip()
        if any(stripped.startswith(p) for p in _RATIONALE_PREFIXES):
            _add_rationale(stripped, lineno, file_nid)


# ── Public API ────────────────────────────────────────────────────────────────

def extract_python(path: Path) -> dict:
    """Extract classes, functions, and imports from a .py file via tree-sitter AST."""
    result = _extract_generic(path, _PYTHON_CONFIG)
    if "error" not in result:
        _extract_python_rationale(path, result)
    return result


def extract_js(path: Path) -> dict:
    """Extract classes, functions, arrow functions, and imports from a .js/.ts/.tsx/.mts/.cts file."""
    suffix = path.suffix.lower()
    if suffix == ".tsx":
        config = _TSX_CONFIG
    elif suffix in (".ts", ".mts", ".cts"):
        config = _TS_CONFIG
    else:
        config = _JS_CONFIG
    result = _extract_generic(path, config)
    if "error" not in result:
        _extract_js_rationale(path, result)
    return result


# ── JS/TS rationale + doc-reference extraction ────────────────────────────────
#
# Parity with _extract_python_rationale: Python files get rationale nodes from
# docstrings and `# NOTE:`-style comments, but JS/TS comments were discarded
# entirely. That silently drops two high-value signals in mixed corpora:
#   1. rationale comments (`// NOTE:`, `// WHY:`, ...) — same as Python;
#   2. architecture-decision references (`ADR-0011`, `RFC 793`) that teams
#      conventionally cite in file/function headers. These are the natural
#      join points between code and design docs in the same graph — without
#      them, code<->ADR edges never form even when the code cites the ADR.

_JS_RATIONALE_PREFIXES = (
    "// NOTE:", "// IMPORTANT:", "// HACK:", "// WHY:", "// RATIONALE:",
    "// TODO:", "// FIXME:",
    "* NOTE:", "* IMPORTANT:", "* HACK:", "* WHY:", "* RATIONALE:",
    "* TODO:", "* FIXME:",
)

# Doc-reference tokens worth first-classing as graph nodes. Deliberately
# conservative: ADR-NNNN (Architecture Decision Records, any zero padding)
# and RFC NNNN / RFC-NNNN.
_JS_DOC_REF_RE = re.compile(r"\b(ADR[- ]?\d{1,5}|RFC[- ]?\d{1,5})\b", re.IGNORECASE)

# Only look for doc references inside comments, not string literals or code.
_JS_COMMENT_LINE_RE = re.compile(r"^\s*(//|/\*|\*)")


def _extract_js_rationale(path: Path, result: dict) -> None:
    """Post-pass: extract rationale comments and doc references from JS/TS source.
    Mutates result in-place by appending to result['nodes'] and result['edges'].
    """
    try:
        source_text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return

    stem = _file_stem(path)
    str_path = str(path)
    nodes = result["nodes"]
    edges = result["edges"]
    seen_ids = {n["id"] for n in nodes}
    file_nid = _make_id(str(path))
    seen_doc_refs: set[str] = set()

    def _add_rationale(text: str, line: int) -> None:
        label = text[:80].replace("\r\n", " ").replace("\r", " ").replace("\n", " ").strip()
        rid = _make_id(stem, "rationale", str(line))
        if rid not in seen_ids:
            seen_ids.add(rid)
            nodes.append({
                "id": rid,
                "label": label,
                "file_type": "rationale",
                "source_file": str_path,
                "source_location": f"L{line}",
            })
        edges.append({
            "source": rid,
            "target": file_nid,
            "relation": "rationale_for",
            "confidence": "EXTRACTED",
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": 1.0,
        })

    def _add_doc_ref(token: str, line: int) -> None:
        # Normalize "adr 11" / "ADR-0011" spellings to a canonical "ADR-0011"
        # style label so references to the same document collapse to one node.
        kind, num = re.match(r"([A-Za-z]+)[- ]?(\d+)", token).groups()
        kind = kind.upper()
        label = f"{kind}-{num.zfill(4)}" if kind == "ADR" else f"{kind}-{num}"
        if label in seen_doc_refs:
            return
        seen_doc_refs.add(label)
        rid = _make_id("docref", label)
        if rid not in seen_ids:
            seen_ids.add(rid)
            nodes.append({
                "id": rid,
                "label": label,
                "file_type": "doc_ref",
                "source_file": str_path,
                "source_location": f"L{line}",
            })
        edges.append({
            "source": file_nid,
            "target": rid,
            "relation": "cites",
            "confidence": "EXTRACTED",
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": 1.0,
        })

    for lineno, line_text in enumerate(source_text.splitlines(), start=1):
        stripped = line_text.strip()
        if any(stripped.startswith(p) for p in _JS_RATIONALE_PREFIXES):
            _add_rationale(stripped.lstrip("/* "), lineno)
        if _JS_COMMENT_LINE_RE.match(line_text):
            for m in _JS_DOC_REF_RE.finditer(stripped):
                _add_doc_ref(m.group(1), lineno)


def extract_svelte(path: Path) -> dict:
    """Extract imports from .svelte files: script-block via JS AST + template regex fallback.

    Tree-sitter only sees the <script> block. Svelte template syntax like
    {#await import('./X.svelte')} lives in the markup layer and is invisible
    to the JS parser, so a regex pass covers those dynamic imports.
    """
    result = _extract_generic(path, _JS_CONFIG)
    try:
        import re as _re
        src = path.read_text(encoding="utf-8", errors="replace")
        existing_ids = {n["id"] for n in result.get("nodes", [])}
        # Source file node ID must match the one _extract_generic creates:
        # _make_id(str(path)) - single arg, no stem prefix. Otherwise the source
        # endpoint is a phantom node and build_from_json drops the edge (#701).
        file_node_id = _make_id(str(path))
        aliases = _load_tsconfig_aliases(path.parent)
        for m in _re.finditer(r"""import\(\s*['"]([^'"]+)['"]\s*\)""", src):
            raw = m.group(1)
            if not raw:
                continue
            if raw.startswith("."):
                # Relative import - resolve to full path so IDs match file node IDs.
                resolved = Path(os.path.normpath(path.parent / raw))
                # Apply same TS/Svelte resolver fixups as static imports so dynamic
                # imports of bare paths and .svelte.ts rune files land on real
                # file nodes instead of phantom ids (#716).
                resolved = _resolve_js_module_path(resolved)
                node_id = _make_id(str(resolved))
                stub_source_file = str(resolved)
            else:
                # Check tsconfig.json path aliases (e.g. "$lib/" -> "src/lib/", "@/" -> "src/")
                # before treating as external. Mirrors _import_js logic so SvelteKit alias
                # imports resolve to the same file node IDs the extractor creates (#701).
                resolved_alias = _resolve_tsconfig_alias(raw, aliases)
                if resolved_alias is not None:
                    resolved_alias = _resolve_js_module_path(resolved_alias)
                    node_id = _make_id(str(resolved_alias))
                    stub_source_file = str(resolved_alias)
                else:
                    # Bare/scoped import (node_modules) - use last segment;
                    # build_from_json drops as external if no matching node exists.
                    module_name = raw.split("/")[-1]
                    if not module_name:
                        continue
                    node_id = _make_id(module_name)
                    stub_source_file = raw
            if node_id in existing_ids:
                # Edge target already a real node - just add the edge, don't add a node.
                result.setdefault("edges", []).append({
                    "source": file_node_id, "target": node_id,
                    "relation": "dynamic_import", "confidence": "EXTRACTED",
                    "source_file": str(path),
                })
                continue
            result.setdefault("nodes", []).append({
                "id": node_id, "label": raw,
                "file_type": "code", "source_file": stub_source_file,
                "confidence": "EXTRACTED",
            })
            result.setdefault("edges", []).append({
                "source": file_node_id, "target": node_id,
                "relation": "dynamic_import", "confidence": "EXTRACTED",
                "source_file": str(path),
            })
            existing_ids.add(node_id)
        # Static imports inside <script> blocks. The JS tree-sitter parser fed
        # the full .svelte file produces a top-level ERROR node (HTML markup
        # is not valid JS), so import_statement nodes are never reached and
        # static imports are silently dropped (#713). Regex over each script
        # body recovers them.
        script_re = _re.compile(
            r"<script\b[^>]*>([\s\S]*?)</script\s*>", _re.IGNORECASE
        )
        static_import_re = _re.compile(
            r"""import\s+(?:[^'"`;]+?\s+from\s+)?['"]([^'"]+)['"]"""
        )
        for script_match in script_re.finditer(src):
            script_body = script_match.group(1)
            for m in static_import_re.finditer(script_body):
                raw = m.group(1)
                if not raw:
                    continue
                if raw.startswith("."):
                    resolved = Path(os.path.normpath(path.parent / raw))
                    if resolved.suffix == ".js":
                        resolved = resolved.with_suffix(".ts")
                    elif resolved.suffix == ".jsx":
                        resolved = resolved.with_suffix(".tsx")
                    node_id = _make_id(str(resolved))
                    stub_source_file = str(resolved)
                else:
                    resolved_alias = _resolve_tsconfig_alias(raw, aliases)
                    if resolved_alias is not None:
                        node_id = _make_id(str(resolved_alias))
                        stub_source_file = str(resolved_alias)
                    else:
                        module_name = raw.split("/")[-1]
                        if not module_name:
                            continue
                        node_id = _make_id(module_name)
                        stub_source_file = raw
                if node_id in existing_ids:
                    result.setdefault("edges", []).append({
                        "source": file_node_id, "target": node_id,
                        "relation": "imports_from", "confidence": "EXTRACTED",
                        "source_file": str(path),
                    })
                    continue
                result.setdefault("nodes", []).append({
                    "id": node_id, "label": raw,
                    "file_type": "code", "source_file": stub_source_file,
                    "confidence": "EXTRACTED",
                })
                result.setdefault("edges", []).append({
                    "source": file_node_id, "target": node_id,
                    "relation": "imports_from", "confidence": "EXTRACTED",
                    "source_file": str(path),
                })
                existing_ids.add(node_id)
    except Exception:
        pass
    return result


def extract_astro(path: Path) -> dict:
    """Extract imports from .astro files: frontmatter (TS) + template regex fallback.

    Astro files start with a ``---\\n...\\n---`` frontmatter block of TypeScript
    setup code (where almost all imports live), followed by an HTML-with-expressions
    template body, and optionally ``<script>`` blocks for client-side JS. Tree-sitter
    only sees the file usefully through the frontmatter — feeding the whole file to
    the JS parser produces a top-level ERROR node because the template is not valid
    JS, so ``import_statement`` nodes are never reached and static imports are
    silently dropped (#850). Mirrors :func:`extract_svelte` — same regex-rescue
    approach, scanning the frontmatter block and any client-side ``<script>`` blocks
    for static and dynamic imports.
    """
    result = _extract_generic(path, _JS_CONFIG)
    try:
        import re as _re
        src = path.read_text(encoding="utf-8", errors="replace")
        existing_ids = {n["id"] for n in result.get("nodes", [])}
        file_node_id = _make_id(str(path))
        aliases = _load_tsconfig_aliases(path.parent)
        # Dynamic imports anywhere in the file: `import('./X.astro')` is legal in
        # frontmatter setup code and inside expression slots.
        for m in _re.finditer(r"""import\(\s*['"]([^'"]+)['"]\s*\)""", src):
            raw = m.group(1)
            if not raw:
                continue
            if raw.startswith("."):
                resolved = Path(os.path.normpath(path.parent / raw))
                resolved = _resolve_js_module_path(resolved)
                node_id = _make_id(str(resolved))
                stub_source_file = str(resolved)
            else:
                resolved_alias = _resolve_tsconfig_alias(raw, aliases)
                if resolved_alias is not None:
                    resolved_alias = _resolve_js_module_path(resolved_alias)
                    node_id = _make_id(str(resolved_alias))
                    stub_source_file = str(resolved_alias)
                else:
                    module_name = raw.split("/")[-1]
                    if not module_name:
                        continue
                    node_id = _make_id(module_name)
                    stub_source_file = raw
            if node_id in existing_ids:
                result.setdefault("edges", []).append({
                    "source": file_node_id, "target": node_id,
                    "relation": "dynamic_import", "confidence": "EXTRACTED",
                    "source_file": str(path),
                })
                continue
            result.setdefault("nodes", []).append({
                "id": node_id, "label": raw,
                "file_type": "code", "source_file": stub_source_file,
                "confidence": "EXTRACTED",
            })
            result.setdefault("edges", []).append({
                "source": file_node_id, "target": node_id,
                "relation": "dynamic_import", "confidence": "EXTRACTED",
                "source_file": str(path),
            })
            existing_ids.add(node_id)
        # Static imports: scan the `---...---` frontmatter at the file head plus any
        # client-side <script> blocks. Both are TS/JS regions but live inside a file
        # the JS tree-sitter parser cannot validate as a whole.
        frontmatter_re = _re.compile(
            r"\A\s*---\s*\r?\n([\s\S]*?)\r?\n---\s*(?:\r?\n|\Z)"
        )
        script_re = _re.compile(
            r"<script\b[^>]*>([\s\S]*?)</script\s*>", _re.IGNORECASE
        )
        static_import_re = _re.compile(
            r"""import\s+(?:[^'"`;]+?\s+from\s+)?['"]([^'"]+)['"]"""
        )
        regions: list[str] = []
        fm = frontmatter_re.search(src)
        if fm:
            regions.append(fm.group(1))
        for script_match in script_re.finditer(src):
            regions.append(script_match.group(1))
        for region in regions:
            for m in static_import_re.finditer(region):
                raw = m.group(1)
                if not raw:
                    continue
                if raw.startswith("."):
                    resolved = Path(os.path.normpath(path.parent / raw))
                    if resolved.suffix == ".js":
                        resolved = resolved.with_suffix(".ts")
                    elif resolved.suffix == ".jsx":
                        resolved = resolved.with_suffix(".tsx")
                    node_id = _make_id(str(resolved))
                    stub_source_file = str(resolved)
                else:
                    resolved_alias = _resolve_tsconfig_alias(raw, aliases)
                    if resolved_alias is not None:
                        node_id = _make_id(str(resolved_alias))
                        stub_source_file = str(resolved_alias)
                    else:
                        module_name = raw.split("/")[-1]
                        if not module_name:
                            continue
                        node_id = _make_id(module_name)
                        stub_source_file = raw
                if node_id in existing_ids:
                    result.setdefault("edges", []).append({
                        "source": file_node_id, "target": node_id,
                        "relation": "imports_from", "confidence": "EXTRACTED",
                        "source_file": str(path),
                    })
                    continue
                result.setdefault("nodes", []).append({
                    "id": node_id, "label": raw,
                    "file_type": "code", "source_file": stub_source_file,
                    "confidence": "EXTRACTED",
                })
                result.setdefault("edges", []).append({
                    "source": file_node_id, "target": node_id,
                    "relation": "imports_from", "confidence": "EXTRACTED",
                    "source_file": str(path),
                })
                existing_ids.add(node_id)
    except Exception:
        pass
    return result


# The open-tag matcher skips over quoted attribute values so a `>` inside one
# (e.g. Vue 3.3+ generic components: `<script setup lang="ts"
# generic="T extends Record<string, unknown>">`) doesn't prematurely end the tag.


def extract_vue(path: Path) -> dict:
    """Extract imports, symbols, and type refs from a ``.vue`` SFC.

    Masks the non-``<script>`` regions and parses the script with the grammar
    its ``lang`` implies (``tsx``→TSX, ``js``/``jsx``→JS, ``ts`` or unset→TS;
    TS is a superset of JS so it is a safe default). A regex pass then recovers
    ``import('…')`` dynamic imports the AST does not edge.
    """
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"nodes": [], "edges": []}

    masked, lang = _vue_mask_non_script(src)
    if lang == "tsx":
        config = _TSX_CONFIG
    elif lang in ("js", "jsx"):
        config = _JS_CONFIG
    else:  # "ts" or unspecified — default to the TS grammar (superset of JS)
        config = _TS_CONFIG

    result = _extract_generic(path, config, source_override=masked.encode("utf-8"))

    # Dynamic `import('…')` calls aren't edged by the AST pass; recover by regex,
    # mirroring extract_svelte/extract_astro.
    try:
        existing_ids = {n["id"] for n in result.get("nodes", [])}
        file_node_id = _make_id(str(path))
        aliases = _load_tsconfig_aliases(path.parent)
        for m in re.finditer(r"""import\(\s*['"]([^'"]+)['"]\s*\)""", src):
            raw = m.group(1)
            if not raw:
                continue
            if raw.startswith("."):
                resolved = Path(os.path.normpath(path.parent / raw))
                resolved = _resolve_js_module_path(resolved)
                node_id = _make_id(str(resolved))
                stub_source_file = str(resolved)
            else:
                resolved_alias = _resolve_tsconfig_alias(raw, aliases)
                if resolved_alias is not None:
                    resolved_alias = _resolve_js_module_path(resolved_alias)
                    node_id = _make_id(str(resolved_alias))
                    stub_source_file = str(resolved_alias)
                else:
                    module_name = raw.split("/")[-1]
                    if not module_name:
                        continue
                    node_id = _make_id(module_name)
                    stub_source_file = raw
            if node_id in existing_ids:
                result.setdefault("edges", []).append({
                    "source": file_node_id, "target": node_id,
                    "relation": "dynamic_import", "confidence": "EXTRACTED",
                    "source_file": str(path),
                })
                continue
            result.setdefault("nodes", []).append({
                "id": node_id, "label": raw,
                "file_type": "code", "source_file": stub_source_file,
                "confidence": "EXTRACTED",
            })
            result.setdefault("edges", []).append({
                "source": file_node_id, "target": node_id,
                "relation": "dynamic_import", "confidence": "EXTRACTED",
                "source_file": str(path),
            })
            existing_ids.add(node_id)
    except Exception:
        pass
    return result


def extract_java(path: Path) -> dict:
    """Extract classes, interfaces, methods, constructors, and imports from a .java file."""
    return _extract_generic(path, _JAVA_CONFIG)


def _is_spock_file(path: Path, ts_result: dict) -> bool:
    """Return True when the file contains Spock-style ``def "feature"()`` methods
    that tree-sitter-groovy cannot parse, detected by checking the raw source."""
    import re as _re
    _SPOCK_FEATURE_RE = _re.compile(r"""^\s*def\s+[\"']""", _re.MULTILINE)
    try:
        return bool(_SPOCK_FEATURE_RE.search(path.read_text(errors="replace")))
    except OSError:
        return False


def _extract_spock_fallback(path: Path, ts_result: dict) -> dict:
    """Regex-based fallback for Spock spec files where tree-sitter-groovy cannot parse
    ``def "feature name"()`` methods. Merges import edges from the tree-sitter pass
    (which survive reliably) with class and feature-method nodes extracted via regex.
    """
    import re as _re
    source = path.read_text(errors="replace")
    str_path = str(path)
    stem = _file_stem(path)

    # Only keep the file node from the tree-sitter pass (guaranteed present and
    # correctly IDed) plus all import edges.  All other ts nodes are discarded to
    # avoid orphaned method/constructor nodes whose parent edges were dropped.
    file_node = next((n for n in ts_result.get("nodes", []) if n.get("label") == path.name), None)
    nodes: list[dict] = [file_node] if file_node else []
    edges: list[dict] = [e for e in ts_result.get("edges", []) if e.get("context") == "import"]
    seen_ids: set[str] = {n["id"] for n in nodes}

    def _add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({
                "id": nid,
                "label": label,
                "file_type": "code",
                "source_file": str_path,
                "source_location": f"L{line}",
            })

    def _add_edge(src: str, tgt: str, relation: str, line: int,
                  confidence: str = "EXTRACTED") -> None:
        edges.append({
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": confidence,
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": 1.0,
        })

    lines_text = source.splitlines()

    # Extract class declarations
    class_re = _re.compile(r"^\s*(?:[\w@]+\s+)*class\s+(\w+)")
    # Extract Spock feature methods: def "..." () or def '...' ()
    # Two separate capture groups per quote style so apostrophes inside
    # double-quoted names (e.g. "shouldn't") are captured correctly.
    feature_re = _re.compile(r"""^\s*def\s+(?:\"([^\"]+)\"|'([^']+)')\s*\(""")
    # Extract plain def methods (non-string names) as well
    plain_method_re = _re.compile(r"""^\s*def\s+(\w+)\s*\(""")

    current_class_nid: str | None = None
    file_nid = _make_id(str_path)

    # Ensure the file node exists (tree-sitter pass may have emitted it)
    if file_nid not in seen_ids:
        _add_node(file_nid, path.name, 1)

    for lineno, line_text in enumerate(lines_text, start=1):
        cm = class_re.match(line_text)
        if cm:
            class_name = cm.group(1)
            class_nid = _make_id(stem, class_name)
            _add_node(class_nid, class_name, lineno)
            _add_edge(file_nid, class_nid, "contains", lineno)
            current_class_nid = class_nid
            continue

        if current_class_nid is None:
            continue

        fm = feature_re.match(line_text)
        if fm:
            method_name = fm.group(1) or fm.group(2)
            method_label = f'"{method_name}"'
            method_nid = _make_id(current_class_nid, method_name)
            _add_node(method_nid, method_label, lineno)
            _add_edge(current_class_nid, method_nid, "method", lineno)
            continue

        pm = plain_method_re.match(line_text)
        if pm:
            method_name = pm.group(1)
            if method_name not in ("if", "while", "for", "switch", "catch"):
                method_label = f".{method_name}()"
                method_nid = _make_id(current_class_nid, method_name)
                _add_node(method_nid, method_label, lineno)
                _add_edge(current_class_nid, method_nid, "method", lineno)

    return {"nodes": nodes, "edges": edges}


def extract_groovy(path: Path) -> dict:
    """Extract classes, methods, constructors, and imports from a .groovy/.gradle file.

    Falls back to a regex-based Spock extractor when tree-sitter-groovy cannot parse
    ``def "feature name"()`` methods (common in Spock specification classes).
    """
    result = _extract_generic(path, _GROOVY_CONFIG)
    if _is_spock_file(path, result):
        result = _extract_spock_fallback(path, result)
    return result


def extract_c(path: Path) -> dict:
    """Extract functions and includes from a .c/.h file."""
    return _extract_generic(path, _C_CONFIG)


def extract_cpp(path: Path) -> dict:
    """Extract functions, classes, and includes from a .cpp/.cc/.cxx/.hpp file."""
    return _extract_generic(path, _CPP_CONFIG)


def extract_ruby(path: Path) -> dict:
    """Extract classes, methods, singleton methods, and calls from a .rb file."""
    return _extract_generic(path, _RUBY_CONFIG)


def extract_csharp(path: Path) -> dict:
    """Extract C# type declarations, methods, namespaces, and usings from a .cs file."""
    return _extract_generic(path, _CSHARP_CONFIG)


def extract_kotlin(path: Path) -> dict:
    """Extract classes, objects, functions, and imports from a .kt/.kts file."""
    return _extract_generic(path, _KOTLIN_CONFIG)


def extract_scala(path: Path) -> dict:
    """Extract classes, objects, functions, and imports from a .scala file."""
    return _extract_generic(path, _SCALA_CONFIG)


def extract_php(path: Path) -> dict:
    """Extract classes, functions, methods, namespace uses, and calls from a .php file."""
    return _extract_generic(path, _PHP_CONFIG)


# One level of balanced parens (e.g. `Foo #(Bar #(int))`) — bounded so malformed
# input cannot trigger pathological backtracking.


def extract_lua(path: Path) -> dict:
    """Extract functions, methods, require() imports, and calls from a .lua file."""
    return _extract_generic(path, _LUA_CONFIG)


def extract_swift(path: Path) -> dict:
    """Extract classes, structs, protocols, functions, imports, and calls from a .swift file."""
    return _extract_generic(path, _SWIFT_CONFIG)


# ── Julia extractor (custom walk) ────────────────────────────────────────────


# ── Go extractor (custom walk) ────────────────────────────────────────────────


# ── Rust extractor (custom walk) ──────────────────────────────────────────────

# Common Rust trait/stdlib method names that appear in virtually every codebase.
# Resolving these cross-file produces spurious INFERRED edges across crate
# boundaries (issue #908) — skip them from the unresolved-call queue entirely.


# ── Zig ───────────────────────────────────────────────────────────────────────


# ── PowerShell ────────────────────────────────────────────────────────────────


# ── PowerShell manifest (.psd1) ──────────────────────────────────────────────

# Keys in a .psd1 whose values are module names/paths we treat as imports.


# ── Cross-file import resolution ──────────────────────────────────────────────


def _canonicalize_csharp_namespace_nodes(all_nodes: list[dict], all_edges: list[dict]) -> None:
    """Collapse duplicate C# namespace node entries to one canonical node per label."""
    by_label: dict[str, list[dict]] = {}
    for node in all_nodes:
        if node.get("type") != "namespace":
            continue
        label = node.get("label")
        if isinstance(label, str):
            by_label.setdefault(label, []).append(node)

    remap: dict[str, str] = {}
    drop_node_ids: set[int] = set()
    for group in by_label.values():
        if len(group) < 2:
            continue
        canonical = sorted(
            group,
            key=lambda node: (
                str(node.get("source_file") or ""),
                str(node.get("source_location") or ""),
                str(node.get("id") or ""),
            ),
        )[0]
        canonical_id = canonical.get("id")
        for node in group:
            if node is canonical:
                continue
            drop_node_ids.add(id(node))
            dup_id = node.get("id")
            if isinstance(dup_id, str) and isinstance(canonical_id, str):
                remap[dup_id] = canonical_id

    if remap:
        for edge in all_edges:
            if edge.get("source") in remap:
                edge["source"] = remap[str(edge["source"])]
            if edge.get("target") in remap:
                edge["target"] = remap[str(edge["target"])]

    if drop_node_ids:
        all_nodes[:] = [node for node in all_nodes if id(node) not in drop_node_ids]


# Languages whose identifiers are case-insensitive, so cross-file name resolution
# may fold case. Everywhere else, case is semantic (`Path` the class vs `PATH` the
# env var are distinct) and folding manufactures false edges / super-hubs (#1581).
_CASE_INSENSITIVE_EXTS = frozenset({
    ".php", ".phtml", ".php3", ".php4", ".php5", ".php7", ".phps",  # PHP fns/classes
    ".sql",                                                          # SQL identifiers
    ".nim", ".nims", ".nimble",                                      # Nim (style-insensitive)
})


def _lang_is_case_insensitive(source_file: object) -> bool:
    """True when the file's language resolves identifiers case-insensitively (#1581)."""
    if not source_file:
        return False
    return Path(str(source_file)).suffix.lower() in _CASE_INSENSITIVE_EXTS


# Language interop families for cross-file call resolution. A call in one language
# can never bind by name to a definition in another family — a TSX component does
# not invoke a Kotlin method, and a Python function does not invoke a Java one.
# Families are grouped by REAL interop so legitimate cross-language resolution
# keeps working: Kotlin/Java/Scala/Groovy share the JVM, C/C++/Objective-C/CUDA
# share headers and symbols (Swift bridges to Objective-C), and JS/TS variants
# (plus Vue/Svelte/Astro SFC script blocks) compile into one module graph.
# Extensions absent from this map (docs, configs, unknown languages) resolve to
# no family and are never filtered — same permissive default as before.
_LANG_FAMILY_BY_EXT: dict[str, str] = {
    # JS/TS module graph (SFCs embed JS/TS)
    ".js": "jsts", ".jsx": "jsts", ".mjs": "jsts", ".cjs": "jsts",
    ".ts": "jsts", ".tsx": "jsts", ".mts": "jsts", ".cts": "jsts",
    ".vue": "jsts", ".svelte": "jsts", ".astro": "jsts",
    # JVM interop
    ".java": "jvm", ".kt": "jvm", ".kts": "jvm",
    ".scala": "jvm", ".groovy": "jvm", ".gradle": "jvm",
    # C-family: shared headers, Objective-C/C++ mix, Swift↔ObjC bridging
    ".c": "native", ".h": "native", ".cpp": "native", ".cc": "native",
    ".cxx": "native", ".hpp": "native", ".cu": "native", ".cuh": "native",
    ".metal": "native", ".m": "native", ".mm": "native", ".swift": "native",
    # Single-language families
    ".py": "python",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby", ".rake": "ruby",
    ".php": "php", ".phtml": "php", ".php3": "php", ".php4": "php",
    ".php5": "php", ".php7": "php", ".phps": "php",
    ".cs": "dotnet", ".razor": "dotnet", ".cshtml": "dotnet", ".xaml": "dotnet",
    ".lua": "lua", ".luau": "lua",
    ".zig": "zig",
    ".ex": "elixir", ".exs": "elixir",
    ".jl": "julia",
    ".dart": "dart",
    ".sh": "shell", ".bash": "shell",
    ".ps1": "powershell", ".psm1": "powershell", ".psd1": "powershell",
}


def _lang_family(source_file: object) -> str | None:
    """Interop family of the file's language, or None when unknown/not code."""
    if not source_file:
        return None
    return _LANG_FAMILY_BY_EXT.get(Path(str(source_file)).suffix.lower())


def _node_label_key(node: dict, fold: bool = False) -> str:
    label = str(node.get("label", "")).strip()
    key = re.sub(r"[^a-zA-Z0-9]+", "", label)
    return key.lower() if fold else key


def _is_top_level_function_definition(node: dict) -> bool:
    """A free/top-level function def (label ``name()``), not a method or type.

    Methods carry a leading dot (``.foo()``) or a qualifier (``Class.foo()``);
    excluding those keeps a bare-name reference from binding to a receiver-scoped
    method, which the receiver-typed resolvers own (#1781).
    """
    label = str(node.get("label", "")).strip()
    return (
        node.get("file_type") == "code"
        and label.endswith(")")
        and not label.startswith(".")
        and "." not in label
    )


def _rewire_unique_stub_nodes(nodes: list[dict], edges: list[dict]) -> None:
    """Map unresolved no-source stubs to a unique real definition with the same label."""
    real_by_label: dict[str, list[dict]] = {}       # exact-case type-like (all languages)
    real_by_label_ci: dict[str, list[dict]] = {}    # case-INSENSITIVE-language reals only
    func_by_label: dict[str, list[dict]] = {}       # top-level function defs (#1781)
    stubs: list[dict] = []

    for node in nodes:
        key = _node_label_key(node)
        if not key:
            continue
        if node.get("source_file"):
            if _is_type_like_definition(node):
                # Match stubs case-SENSITIVELY: a `Path` reference must not rewire to a
                # `PATH` env var (#1581). Fold only for genuinely case-insensitive
                # languages, where `foo` legitimately resolves to `Foo`.
                real_by_label.setdefault(key, []).append(node)
                if _lang_is_case_insensitive(node.get("source_file")):
                    real_by_label_ci.setdefault(
                        _node_label_key(node, fold=True), []).append(node)
            elif _is_top_level_function_definition(node):
                func_by_label.setdefault(key, []).append(node)
            continue
        stubs.append(node)

    # Language families referencing each stub, for the function-merge guard (#1781):
    # a cross-module `references` edge to a function used to dangle on a sourceless
    # name-only stub because functions were excluded as rewire targets. We now allow
    # a UNIQUE function definition to absorb it, but only when it shares a language
    # family with the stub's referrers — so a Python `get_db` reference can't bind to
    # a unique Go `get_db()` (mirrors the #1718/#1749 interop guard).
    stub_ids = {str(s.get("id")) for s in stubs if s.get("id")}
    stub_families: dict[str, set] = {}
    supertype_stub_ids: set[str] = set()  # stubs used as a base type — never a function
    _SUPERTYPE_RELATIONS = {"inherits", "implements", "extends"}
    for edge in edges:
        rel = edge.get("relation")
        for endpoint in ("source", "target"):
            nid = edge.get(endpoint)
            if nid in stub_ids:
                fam = _lang_family(edge.get("source_file"))
                if fam is not None:
                    stub_families.setdefault(str(nid), set()).add(fam)
                # A stub referenced as a supertype must resolve to a class/type,
                # not a same-named function (you don't inherit from a function).
                if endpoint == "target" and rel in _SUPERTYPE_RELATIONS:
                    supertype_stub_ids.add(str(nid))

    remap: dict[str, str] = {}
    for stub in stubs:
        stub_id = str(stub.get("id", ""))
        if not stub_id:
            continue
        candidates = real_by_label.get(_node_label_key(stub), [])
        if len(candidates) != 1:
            # No unique exact type match — fall back to a case-insensitive match, but
            # only against case-insensitive-language definitions (so a case-sensitive
            # `PATH` can never absorb a `Path` reference).
            candidates = real_by_label_ci.get(_node_label_key(stub, fold=True), [])
        if len(candidates) != 1:
            # #1781: no unique type — try a unique top-level FUNCTION definition,
            # gated by (a) the stub not being used as a supertype and (b) a
            # language-family match with the stub's referrers.
            fcands = func_by_label.get(_node_label_key(stub), [])
            if len(fcands) == 1 and stub_id not in supertype_stub_ids:
                fams = stub_families.get(stub_id, set())
                cand_fam = _lang_family(fcands[0].get("source_file"))
                if not fams or cand_fam is None or cand_fam in fams:
                    candidates = fcands
        if len(candidates) != 1:
            continue
        target_id = candidates[0].get("id")
        if isinstance(target_id, str) and target_id and target_id != stub_id:
            remap[stub_id] = target_id

    if not remap:
        return

    by_id = {node.get("id"): node for node in nodes if node.get("id")}
    csharp_scoped_relations = {"inherits", "implements", "references", "imports"}
    for edge in edges:
        is_csharp_scoped_edge = (
            str(edge.get("source_file", "")).endswith(".cs")
            and edge.get("relation") in csharp_scoped_relations
        )
        source = edge.get("source")
        if source in remap:
            remapped_source = remap[str(source)]
            if not (
                is_csharp_scoped_edge
                and str(by_id.get(remapped_source, {}).get("source_file", "")).endswith(".cs")
            ):
                edge["source"] = remapped_source
        target = edge.get("target")
        if target in remap:
            remapped_target = remap[str(target)]
            if not (
                is_csharp_scoped_edge
                and str(by_id.get(remapped_target, {}).get("source_file", "")).endswith(".cs")
            ):
                edge["target"] = remapped_target

    referenced = {x for e in edges for x in (e.get("source"), e.get("target"))}
    drop_ids = {stub_id for stub_id in remap if stub_id not in referenced}
    nodes[:] = [node for node in nodes if node.get("id") not in drop_ids]


def _augment_js_reexport_edges(
    paths: list[Path],
    nodes: list[dict],
    edges: list[dict],
    root: Path,
) -> None:
    """Compatibility wrapper for the JS/TS symbol-resolution post-pass."""
    facts = _SymbolResolutionFacts()
    _collect_js_symbol_resolution_facts(paths, facts)
    _apply_symbol_resolution_facts(paths, nodes, edges, root, facts)


# Header / implementation file-extension pairing for the decl/def class merge.


def _merge_swift_extensions(
    per_file: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> None:
    """Collapse cross-file Swift `extension Foo` nodes into the canonical `Foo`.

    tree-sitter-swift reuses `class_declaration` for both `class Foo` and
    `extension Foo`, and node ids carry the file stem, so each file that
    extends `Foo` produces its own `Foo` node. The match is done by label:
    when exactly one non-extension declaration shares the label, extension
    nodes redirect onto it. Extensions of types outside the corpus (no match)
    and ambiguous labels (more than one match) are left untouched — picking
    arbitrarily would invent edges.
    """
    extension_nids: set[str] = set()
    extension_labels: dict[str, str] = {}
    for result in per_file:
        for ext in result.get("swift_extensions", []) or []:
            extension_nids.add(ext["nid"])
            extension_labels[ext["nid"]] = ext["label"]

    if not extension_nids:
        return

    label_to_canonical: dict[str, list[str]] = {}
    for n in all_nodes:
        if n.get("id") in extension_nids:
            continue
        label = n.get("label")
        if not label:
            continue
        label_to_canonical.setdefault(label, []).append(n["id"])

    remap: dict[str, str] = {}
    for ext_nid in extension_nids:
        candidates = label_to_canonical.get(extension_labels[ext_nid], [])
        if len(candidates) != 1:
            continue
        canonical_nid = candidates[0]
        if canonical_nid != ext_nid:
            remap[ext_nid] = canonical_nid

    if not remap:
        return

    all_nodes[:] = [n for n in all_nodes if n.get("id") not in remap]

    # Each extension file's `contains` edge ends up pointing at the canonical
    # type — multiple files containing the same node is the intended shape:
    # the type owns the methods, the files own their slice. Self-loops are
    # dropped (e.g. an in-file extension method whose call already pointed at
    # the canonical type).
    rewritten: list[dict] = []
    seen_keys: set[tuple] = set()
    for e in all_edges:
        src = remap.get(e.get("source"), e.get("source"))
        tgt = remap.get(e.get("target"), e.get("target"))
        if src == tgt:
            continue
        e["source"] = src
        e["target"] = tgt
        key = (src, tgt, e.get("relation"), e.get("source_file"), e.get("source_location"))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        rewritten.append(e)
    all_edges[:] = rewritten


def _resolve_swift_member_calls(
    per_file: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> None:
    """Resolve cross-file Swift member calls (``recv.method()``) to the real
    definition of the receiver's type (#1356).

    The shared cross-file call pass drops every ``is_member_call`` because a bare
    method name (``update``) collides across the corpus and inflates god-nodes
    (#543/#1219). Swift extractors record the receiver of each member call and a
    per-file ``name -> type`` table (``swift_type_table``); this pass uses them to
    type the receiver, then emits an edge ONLY when that type name resolves to
    exactly one definition. A type-qualified call (``Type.staticMethod()``) is
    EXTRACTED (the type is named explicitly in source); an instance call typed via
    local inference (``obj.method()``) is INFERRED. The shared-pass member-call drop
    stays intact: this is purely additive and fires only on receiver-typed Swift calls.

    Must run after id-disambiguation so node ids and caller_nids are final.
    """
    type_table_by_file: dict[str, dict[str, str]] = {}
    for result in per_file:
        tt = result.get("swift_type_table")
        if tt and tt.get("path"):
            type_table_by_file[tt["path"]] = tt.get("table", {})
    if not type_table_by_file:
        return

    def _key(label: str) -> str:
        return re.sub(r"[^a-zA-Z0-9]+", "", str(label)).lower()

    # A genuine Swift type is the target of a `contains` edge from its file node.
    # Bare type references create a same-label shadow node (via ensure_named_node)
    # that carries a source_file but is NOT contained; excluding non-contained
    # nodes keeps that shadow from making a real type name look ambiguous.
    contained = {e.get("target") for e in all_edges if e.get("relation") == "contains"}

    # Type name -> definition node ids (real, source-backed, type-like defs only).
    # len != 1 is the god-node guard: an ambiguous type name bails.
    type_def_nids: dict[str, list[str]] = {}
    node_by_id: dict[str, dict] = {}
    for n in all_nodes:
        node_by_id[n.get("id")] = n
        if n.get("source_file") and n.get("id") in contained and _is_type_like_definition(n):
            type_def_nids.setdefault(_key(n.get("label", "")), []).append(n["id"])

    # (type_node_id, method_key) -> method_node_id, from `method` edges.
    method_index: dict[tuple[str, str], str] = {}
    for e in all_edges:
        if e.get("relation") != "method":
            continue
        src, tgt = e.get("source"), e.get("target")
        tnode = node_by_id.get(tgt)
        if tnode is not None:
            method_index[(src, _key(tnode.get("label", "")))] = tgt

    all_raw_calls: list[dict] = []
    for result in per_file:
        all_raw_calls.extend(result.get("raw_calls", []))

    existing_pairs = {(e.get("source"), e.get("target")) for e in all_edges}
    for rc in all_raw_calls:
        if not rc.get("is_member_call"):
            continue
        receiver = rc.get("receiver")
        callee = rc.get("callee")
        if not receiver or not callee:
            continue
        # Determine the receiver's type. An upper-cased receiver is itself a type
        # (Type.staticMethod(), Singleton.shared.x()); otherwise look it up in the
        # declaring file's local type table.
        if receiver[:1].isupper():
            type_name = receiver
            type_qualified = True
        else:
            type_name = type_table_by_file.get(rc.get("source_file", ""), {}).get(receiver)
            type_qualified = False
        if not type_name:
            continue
        type_defs = type_def_nids.get(_key(type_name), [])
        if len(type_defs) != 1:  # ambiguous or absent -> bail (god-node guard)
            continue
        type_nid = type_defs[0]
        caller = rc.get("caller_nid")
        if not caller:
            continue
        method_nid = method_index.get((type_nid, _key(callee)))
        target = method_nid or type_nid
        relation = "calls" if method_nid else "references"
        if target == caller or (caller, target) in existing_pairs:
            continue
        existing_pairs.add((caller, target))
        # A type-qualified call (`Type.staticMethod()`) names the receiver type
        # explicitly in source, so it is an exact reference — EXTRACTED, matching
        # the Python qualified-class-method pass (#1533). An instance call whose
        # receiver type came from local inference (`obj.method()`) stays INFERRED.
        all_edges.append({
            "source": caller,
            "target": target,
            "relation": relation,
            "context": "call",
            "confidence": "EXTRACTED" if type_qualified else "INFERRED",
            "confidence_score": 1.0 if type_qualified else 0.8,
            "source_file": rc.get("source_file", ""),
            "source_location": rc.get("source_location"),
            "weight": 1.0,
        })


def _resolve_python_member_calls(
    per_file: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> None:
    """Resolve cross-file Python qualified class-method calls (``ClassName.method()``)
    to the class-qualified method node (#1446).

    The shared cross-file call pass drops every ``is_member_call`` because a bare
    method name (``log``) collides across the corpus and inflates god-nodes
    (#543/#1219). That guard is right for *instance* calls (``obj.method()``) but
    misses *class-qualified* calls (``ClassName.method()``), where the receiver is
    an explicitly-named class — an exact, unambiguous reference. This pass uses the
    receiver captured by the extractor, and when it is a capitalized name resolving
    to exactly one class node that owns the called method, emits an EXTRACTED
    ``calls`` edge. Purely additive (only member calls the shared pass skipped),
    with a single-definition god-node guard.

    Must run after id-disambiguation so node ids and caller_nids are final.
    """
    def _key(label: str) -> str:
        return re.sub(r"[^a-zA-Z0-9]+", "", str(label)).lower()

    node_by_id: dict[str, dict] = {n.get("id"): n for n in all_nodes}

    # A class owns methods: it is the source of one or more `method` edges. Index
    # class label -> owning class node ids (len != 1 is the god-node guard), and
    # (class_node_id, method_key) -> method_node_id.
    class_def_nids: dict[str, list[str]] = {}
    method_index: dict[tuple[str, str], str] = {}
    for e in all_edges:
        if e.get("relation") != "method":
            continue
        src, tgt = e.get("source"), e.get("target")
        cnode = node_by_id.get(src)
        if cnode is not None:
            class_def_nids.setdefault(_key(cnode.get("label", "")), []).append(src)
        tnode = node_by_id.get(tgt)
        if tnode is not None:
            method_index[(src, _key(tnode.get("label", "")))] = tgt
    # A class with N methods produced N entries; collapse to a unique set. (No
    # early return when there are no classes: the module arm below resolves
    # `module.func()` where the callable is a plain function, not a method.)
    for k in list(class_def_nids):
        class_def_nids[k] = sorted(set(class_def_nids[k]))

    all_raw_calls: list[dict] = []
    for result in per_file:
        all_raw_calls.extend(result.get("raw_calls", []))

    # Module-alias arm index (#1883): `module.func()` where `module` is imported.
    # Key on stable node ids, not source_file strings (source_file is relativized
    # by the CLI id-remap pass but raw_calls keep their original path, so a string
    # join would miss under an explicit cache_root). The `imports` edge's source
    # is the caller's own file node; `contains` maps a file node to its children.
    contains_children: dict[str, dict[str, list[str]]] = {}
    file_of_node: dict[str, str] = {}
    for e in all_edges:
        if e.get("relation") == "contains":
            src, tgt = e.get("source"), e.get("target")
            tnode = node_by_id.get(tgt)
            if tnode is not None:
                contains_children.setdefault(src, {}).setdefault(
                    _key(tnode.get("label", "")), []).append(tgt)
                file_of_node[tgt] = src
    imported_by_filenode: dict[str, set[str]] = {}
    for e in all_edges:
        if e.get("relation") in ("imports", "imports_from"):
            imported_by_filenode.setdefault(e.get("source"), set()).add(e.get("target"))

    def _module_stem_key(nid: str) -> str:
        n = node_by_id.get(nid)
        if not n:
            return ""
        sf = n.get("source_file") or ""
        stem = Path(sf).stem if sf else ""
        return _key(stem or n.get("label", ""))

    existing_pairs = {(e.get("source"), e.get("target")) for e in all_edges}

    def _emit_call(caller: str, target_nid: "str | None", rc: dict) -> None:
        if not target_nid or target_nid == caller or (caller, target_nid) in existing_pairs:
            return
        existing_pairs.add((caller, target_nid))
        # EXTRACTED: a qualified call (`ClassName.method()` or `module.func()`) is
        # an explicit, unambiguous static reference resolved to exactly one
        # definition (each arm applies a single-definition god-node guard).
        all_edges.append({
            "source": caller,
            "target": target_nid,
            "relation": "calls",
            "context": "call",
            "confidence": "EXTRACTED",
            "confidence_score": 1.0,
            "source_file": rc.get("source_file", ""),
            "source_location": rc.get("source_location"),
            "weight": 1.0,
        })

    for rc in all_raw_calls:
        if not rc.get("is_member_call"):
            continue
        receiver = rc.get("receiver")
        callee = rc.get("callee")
        caller = rc.get("caller_nid")
        if not receiver or not callee or not caller:
            continue
        if receiver[:1].isupper():
            # Class arm (#1446): a capitalized receiver is a class reference; an
            # instance (`self`, `obj`) never collides with a same-spelled class.
            class_nids = class_def_nids.get(_key(receiver), [])
            if len(class_nids) != 1:  # absent or ambiguous -> bail (god-node guard)
                continue
            _emit_call(caller, method_index.get((class_nids[0], _key(callee))), rc)
        else:
            # Module arm (#1883): a lowercase receiver may be an imported module.
            # Resolve it against the modules imported into the caller's own file
            # (so `self`/`obj`/local instances, which are not imported modules,
            # never match), then to the single callable that module contains.
            rkey = _key(receiver)
            caller_file = file_of_node.get(caller)
            mods = [t for t in imported_by_filenode.get(caller_file, ())
                    if t in contains_children and _module_stem_key(t) == rkey]
            if len(mods) != 1:  # not an imported module, or ambiguous -> bail
                continue
            children = contains_children[mods[0]].get(_key(callee), [])
            if len(children) != 1:  # absent or ambiguous callable -> bail
                continue
            _emit_call(caller, children[0], rc)


def _resolve_typescript_member_calls(
    per_file: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> None:
    """Resolve cross-file TS/JS member calls via constructor-injection type tables (#1316).

    ``this.repo.findById()`` drops out in the shared cross-file pass because bare
    ``findById`` collides across the corpus (god-node guard).  TS constructors with
    parameter-property modifiers (``private repo: IUserRepository``) produce a
    per-file type table mapping field names to their declared types.  This pass
    looks up the receiver field's type, finds a single-definition class/interface
    owning a method with the callee name, and emits an EXTRACTED ``calls`` edge.
    """
    type_table_by_file: dict[str, dict[str, str]] = {}
    for result in per_file:
        tt = result.get("ts_type_table")
        if tt and tt.get("path"):
            type_table_by_file[tt["path"]] = tt.get("table", {})
    if not type_table_by_file:
        return

    def _key(label: str) -> str:
        return re.sub(r"[^a-zA-Z0-9]+", "", str(label)).lower()

    contained = {e.get("target") for e in all_edges if e.get("relation") == "contains"}

    type_def_nids: dict[str, list[str]] = {}
    node_by_id: dict[str, dict] = {}
    for n in all_nodes:
        node_by_id[n.get("id")] = n
        if n.get("source_file") and n.get("id") in contained and _is_type_like_definition(n):
            type_def_nids.setdefault(_key(n.get("label", "")), []).append(n["id"])

    method_index: dict[tuple[str, str], str] = {}
    for e in all_edges:
        if e.get("relation") != "method":
            continue
        src, tgt = e.get("source"), e.get("target")
        tnode = node_by_id.get(tgt)
        if tnode is not None:
            method_index[(src, _key(tnode.get("label", "")))] = tgt

    all_raw_calls: list[dict] = []
    for result in per_file:
        all_raw_calls.extend(result.get("raw_calls", []))

    existing_pairs = {(e.get("source"), e.get("target")) for e in all_edges}
    for rc in all_raw_calls:
        if not rc.get("is_member_call"):
            continue
        receiver = rc.get("receiver")
        callee = rc.get("callee")
        caller = rc.get("caller_nid")
        if not receiver or not callee or not caller:
            continue
        if receiver[:1].isupper():
            type_name = receiver
        else:
            type_name = type_table_by_file.get(rc.get("source_file", ""), {}).get(receiver)
        if not type_name:
            continue
        # A builtin global receiver type (Date, Promise, Map, ...) must not resolve
        # to a user symbol. _key() casefolds, so `x: Date; x.getTime()` would bind
        # the caller to a same-named user `class DATE` in another file, inventing
        # phantom `references[call]` edges and a false god node (#1726). The
        # cross-file CALL resolver already skips these globals; do the same here.
        if type_name in _LANGUAGE_BUILTIN_GLOBALS:
            continue
        type_defs = type_def_nids.get(_key(type_name), [])
        if len(type_defs) != 1:
            continue
        type_nid = type_defs[0]
        method_nid = method_index.get((type_nid, _key(callee)))
        target = method_nid or type_nid
        relation = "calls" if method_nid else "references"
        if target == caller or (caller, target) in existing_pairs:
            continue
        existing_pairs.add((caller, target))
        all_edges.append({
            "source": caller,
            "target": target,
            "relation": relation,
            "context": "call",
            "confidence": "EXTRACTED",
            "confidence_score": 1.0,
            "source_file": rc.get("source_file", ""),
            "source_location": rc.get("source_location"),
            "weight": 1.0,
        })


def _resolve_cpp_member_calls(
    per_file: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> None:
    """Resolve cross-file C++ member calls (``f.bar()``, ``f->bar()``,
    ``Foo::bar()``, ``this->bar()``) to the real definition of the receiver's type
    (#1547).

    The shared cross-file pass drops every ``is_member_call`` because a bare method
    name (``bar``) collides across the corpus and inflates god-nodes (#543/#1219).
    The C++ extractor records each member call's receiver and a per-file
    ``var -> ClassName`` table (``cpp_type_table``) built from local declarations.
    This pass types the receiver, then emits an edge ONLY when that type resolves
    to exactly ONE definition (the god-node guard).

    Receiver typing, by precision tier:
      * ``Foo::bar()`` — the scope ``Foo`` names the type explicitly -> EXTRACTED.
      * ``this->bar()`` — the receiver is the caller's own enclosing class -> EXTRACTED.
      * ``f.bar()`` / ``f->bar()`` — ``f`` typed via the file's local table -> INFERRED.
    A receiver whose type can't be inferred locally is SKIPPED (no guess): a false
    call edge is worse than a missing one. The ``_merge_decl_def_classes`` pass has
    already folded each header/impl class pair into one node, so a paired class is a
    single definition and clears the single-definition guard.

    Must run after id-disambiguation so node ids and caller_nids are final.
    """
    type_table_by_file: dict[str, dict[str, str]] = {}
    for result in per_file:
        tt = result.get("cpp_type_table")
        if tt and tt.get("path"):
            type_table_by_file[tt["path"]] = tt.get("table", {})

    def _key(label: str) -> str:
        return re.sub(r"[^a-zA-Z0-9]+", "", str(label)).lower()

    # A genuine C++ type is the target of a `contains` edge from its file node;
    # bare-reference shadow nodes (ensure_named_node stubs) are not contained, so
    # excluding non-contained nodes keeps them from making a real type ambiguous.
    contained = {e.get("target") for e in all_edges if e.get("relation") == "contains"}

    type_def_nids: dict[str, list[str]] = {}
    node_by_id: dict[str, dict] = {}
    for n in all_nodes:
        node_by_id[n.get("id")] = n
        if n.get("source_file") and n.get("id") in contained and _is_type_like_definition(n):
            type_def_nids.setdefault(_key(n.get("label", "")), []).append(n["id"])

    # (type_node_id, method_key) -> method_node_id, and caller -> enclosing type
    # (the owning class) for `this->` calls. A C++ class owns its members via
    # `method` edges (out-of-line definitions) AND `defines` edges (in-class
    # declarations, which the extractor models as fields); index both so a header-
    # declared `void bar();` resolves. `method` wins when a key has both.
    method_index: dict[tuple[str, str], str] = {}
    enclosing_type: dict[str, str] = {}
    for rel in ("defines", "method"):
        for e in all_edges:
            if e.get("relation") != rel:
                continue
            src, tgt = e.get("source"), e.get("target")
            tnode = node_by_id.get(tgt)
            if tnode is None:
                continue
            enclosing_type.setdefault(tgt, src)
            method_index[(src, _key(tnode.get("label", "")))] = tgt

    all_raw_calls: list[dict] = []
    for result in per_file:
        all_raw_calls.extend(result.get("raw_calls", []))

    existing_pairs = {(e.get("source"), e.get("target")) for e in all_edges}
    for rc in all_raw_calls:
        if not rc.get("is_member_call"):
            continue
        receiver = rc.get("receiver")
        callee = rc.get("callee")
        caller = rc.get("caller_nid")
        if not receiver or not callee or not caller:
            continue
        src_file = rc.get("source_file", "")
        # Only resolve C++ raw_calls (other languages share the raw_calls list;
        # a `.h` may route to either extract_cpp or extract_objc by content, so the
        # extractor-stamped `lang` tag — not the suffix — is the unambiguous gate).
        if rc.get("lang") != "cpp":
            continue
        # Determine the receiver's type and the resulting confidence.
        if receiver == "this":
            # this->bar(): receiver is the caller's own enclosing class.
            type_nid = enclosing_type.get(caller)
            if not type_nid:
                continue
            type_qualified = True
        elif receiver[:1].isupper():
            # Foo::bar(): the type is named explicitly in source.
            type_defs = type_def_nids.get(_key(receiver), [])
            if len(type_defs) != 1:  # ambiguous or absent -> bail (god-node guard)
                continue
            type_nid = type_defs[0]
            type_qualified = True
        else:
            # f.bar() / f->bar(): type the receiver via the file's local table.
            type_name = type_table_by_file.get(src_file, {}).get(receiver)
            if not type_name:
                continue
            type_defs = type_def_nids.get(_key(type_name), [])
            if len(type_defs) != 1:  # ambiguous or absent -> bail (god-node guard)
                continue
            type_nid = type_defs[0]
            type_qualified = False
        method_nid = method_index.get((type_nid, _key(callee)))
        target = method_nid or type_nid
        relation = "calls" if method_nid else "references"
        if target == caller or (caller, target) in existing_pairs:
            continue
        existing_pairs.add((caller, target))
        all_edges.append({
            "source": caller,
            "target": target,
            "relation": relation,
            "context": "call",
            "confidence": "EXTRACTED" if type_qualified else "INFERRED",
            "confidence_score": 1.0 if type_qualified else 0.8,
            "source_file": src_file,
            "source_location": rc.get("source_location"),
            "weight": 1.0,
        })


def _resolve_csharp_member_calls(
    per_file: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> None:
    """Resolve C# member calls (``recv.Method()``) to the receiver's declared type
    (#1609).

    The shared cross-file pass drops every ``is_member_call`` because a bare method
    name collides across the corpus — and for C# an in-file bare match silently
    mis-bound ``_server.Save()`` to an unrelated ``Cache.Save()``. The C# extractor
    now records each member call's receiver plus a per-file ``name -> Type`` table
    (``csharp_type_table``) of fields/properties/params/locals. This pass types the
    receiver, then emits an edge ONLY when that type resolves to exactly ONE
    definition (the god-node guard); an untypable receiver is skipped (no guess).

    Receiver typing, by precision tier:
      * ``this.M()`` — receiver is the caller's own enclosing class -> EXTRACTED.
      * ``Type.M()`` (capitalized) — the type is named explicitly in source -> EXTRACTED.
      * ``recv.M()`` — ``recv`` typed via the file's field/param/local table -> INFERRED.

    Must run after id-disambiguation so node ids and caller_nids are final.
    """
    type_table_by_file: dict[str, dict[str, str]] = {}
    for result in per_file:
        tt = result.get("csharp_type_table")
        if tt and tt.get("path"):
            type_table_by_file[tt["path"]] = tt.get("table", {})

    def _key(label: str) -> str:
        return re.sub(r"[^a-zA-Z0-9]+", "", str(label)).lower()

    contained = {e.get("target") for e in all_edges if e.get("relation") == "contains"}

    type_def_nids: dict[str, list[str]] = {}
    node_by_id: dict[str, dict] = {}
    for n in all_nodes:
        node_by_id[n.get("id")] = n
        if n.get("source_file") and n.get("id") in contained and _is_type_like_definition(n):
            type_def_nids.setdefault(_key(n.get("label", "")), []).append(n["id"])

    # (type_node_id, method_key) -> method_node_id, and caller -> enclosing type.
    # C# owns its methods via `method` edges.
    method_index: dict[tuple[str, str], str] = {}
    enclosing_type: dict[str, str] = {}
    for e in all_edges:
        if e.get("relation") != "method":
            continue
        src, tgt = e.get("source"), e.get("target")
        tnode = node_by_id.get(tgt)
        if tnode is None:
            continue
        enclosing_type.setdefault(tgt, src)
        method_index[(src, _key(tnode.get("label", "")))] = tgt

    all_raw_calls: list[dict] = []
    for result in per_file:
        all_raw_calls.extend(result.get("raw_calls", []))

    existing_pairs = {(e.get("source"), e.get("target")) for e in all_edges}
    for rc in all_raw_calls:
        if rc.get("lang") != "csharp" or not rc.get("is_member_call"):
            continue
        receiver = rc.get("receiver")
        callee = rc.get("callee")
        caller = rc.get("caller_nid")
        if not receiver or not callee or not caller:
            continue
        src_file = rc.get("source_file", "")
        if receiver == "this":
            type_nid = enclosing_type.get(caller)
            if not type_nid:
                continue
            type_qualified = True
        elif receiver[:1].isupper():
            # Type.M() — the type is named explicitly (also covers a Pascal-cased
            # local whose name equals its type, resolved via the table below if the
            # explicit-type lookup misses).
            type_defs = type_def_nids.get(_key(receiver), [])
            if len(type_defs) != 1:
                type_name = type_table_by_file.get(src_file, {}).get(receiver)
                type_defs = type_def_nids.get(_key(type_name), []) if type_name else []
                if len(type_defs) != 1:
                    continue
            type_nid = type_defs[0]
            type_qualified = True
        else:
            type_name = type_table_by_file.get(src_file, {}).get(receiver)
            if not type_name:
                continue
            type_defs = type_def_nids.get(_key(type_name), [])
            if len(type_defs) != 1:  # ambiguous or absent -> bail (god-node guard)
                continue
            type_nid = type_defs[0]
            type_qualified = False
        method_nid = method_index.get((type_nid, _key(callee)))
        if not method_nid:
            continue  # receiver typed, but the type has no such method — skip
        if method_nid == caller or (caller, method_nid) in existing_pairs:
            continue
        existing_pairs.add((caller, method_nid))
        all_edges.append({
            "source": caller,
            "target": method_nid,
            "relation": "calls",
            "context": "call",
            "confidence": "EXTRACTED" if type_qualified else "INFERRED",
            "confidence_score": 1.0 if type_qualified else 0.8,
            "source_file": src_file,
            "source_location": rc.get("source_location"),
            "weight": 1.0,
        })


def _resolve_java_member_calls(
    per_file: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> None:
    """Resolve Java member calls against the receiver's declared type.

    Explicit type receivers and ``this`` are exact. Fields declared on the
    caller's class plus method parameters and explicit locals are inferred from
    the extractor's method-scoped type table. A missing or ambiguous receiver
    type is skipped rather than falling back to a bare method-name match.
    """
    def key(label: str) -> str:
        return str(label).strip().removeprefix(".").removesuffix("()")

    contained = {edge.get("target") for edge in all_edges
                 if edge.get("relation") == "contains"}
    node_by_id = {node.get("id"): node for node in all_nodes}

    type_def_nids: dict[str, list[str]] = {}
    for node in all_nodes:
        if (
            node.get("source_file")
            and node.get("id") in contained
            and _is_type_like_definition(node)
        ):
            type_def_nids.setdefault(key(node.get("label", "")), []).append(node["id"])

    method_index: dict[tuple[str, str], set[str]] = {}
    enclosing_type: dict[str, str] = {}
    for edge in all_edges:
        if edge.get("relation") != "method":
            continue
        owner, method = edge.get("source"), edge.get("target")
        method_node = node_by_id.get(method)
        if method_node is None:
            continue
        enclosing_type.setdefault(method, owner)
        method_index.setdefault((owner, key(method_node.get("label", ""))), set()).add(method)

    existing_pairs = {(edge.get("source"), edge.get("target")) for edge in all_edges}
    for result in per_file:
        for raw_call in result.get("raw_calls", []):
            if raw_call.get("lang") != "java" or not raw_call.get("is_member_call"):
                continue
            receiver = raw_call.get("receiver")
            callee = raw_call.get("callee")
            caller = raw_call.get("caller_nid")
            if not receiver or not callee or not caller:
                continue

            exact = False
            if receiver == "this":
                type_nid = enclosing_type.get(caller)
                exact = True
                if not type_nid:
                    continue
            else:
                type_name = raw_call.get("receiver_type")
                if not type_name and receiver[:1].isupper():
                    type_name = receiver
                    exact = True
                if not type_name:
                    continue
                type_defs = type_def_nids.get(key(type_name), [])
                if len(type_defs) != 1:
                    continue
                type_nid = type_defs[0]

            method_nids = method_index.get((type_nid, key(callee)), set())
            if len(method_nids) != 1:
                continue
            method_nid = next(iter(method_nids))
            if method_nid == caller or (caller, method_nid) in existing_pairs:
                continue
            existing_pairs.add((caller, method_nid))
            all_edges.append({
                "source": caller,
                "target": method_nid,
                "relation": "calls",
                "context": "call",
                "confidence": "EXTRACTED" if exact else "INFERRED",
                "confidence_score": 1.0 if exact else 0.8,
                "source_file": raw_call.get("source_file", ""),
                "source_location": raw_call.get("source_location"),
                "weight": 1.0,
            })


def _resolve_objc_member_calls(
    per_file: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> None:
    """Resolve cross-file Objective-C message sends (``[recv sel]``) to the real
    definition of the receiver's type (#1556).

    The ObjC extractor keeps its same-file selector matching (alloc/init refs,
    dot-syntax accesses, @selector) and additionally emits ``raw_calls`` for every
    message send, with the receiver and the reconstructed selector as the callee.
    This pass types the receiver and emits a cross-file ``calls`` edge ONLY when the
    type resolves to exactly ONE definition (the god-node guard).

    Receiver typing:
      * ``self`` / ``super`` — the caller's own enclosing class -> EXTRACTED.
      * Capitalized receiver (``[Foo new]``) — the type named explicitly -> EXTRACTED.
      * ``[f doThing]`` — ``f`` typed via the file's ``Foo *f`` local table -> INFERRED.
    An uninferable receiver is SKIPPED (no guess), so an ambiguous selector across
    classes never fans out. ``_merge_decl_def_classes`` folds each @interface/@impl
    pair into one node, so a paired class clears the single-definition guard.

    Must run after id-disambiguation so node ids and caller_nids are final.
    """
    type_table_by_file: dict[str, dict[str, str]] = {}
    for result in per_file:
        tt = result.get("objc_type_table")
        if tt and tt.get("path"):
            type_table_by_file[tt["path"]] = tt.get("table", {})

    def _key(label: str) -> str:
        return re.sub(r"[^a-zA-Z0-9]+", "", str(label)).lower()

    contained = {e.get("target") for e in all_edges if e.get("relation") == "contains"}

    type_def_nids: dict[str, list[str]] = {}
    node_by_id: dict[str, dict] = {}
    for n in all_nodes:
        node_by_id[n.get("id")] = n
        if n.get("source_file") and n.get("id") in contained and _is_type_like_definition(n):
            type_def_nids.setdefault(_key(n.get("label", "")), []).append(n["id"])

    method_index: dict[tuple[str, str], str] = {}
    enclosing_type: dict[str, str] = {}
    for e in all_edges:
        if e.get("relation") != "method":
            continue
        src, tgt = e.get("source"), e.get("target")
        enclosing_type.setdefault(tgt, src)
        tnode = node_by_id.get(tgt)
        if tnode is not None:
            # ObjC method labels carry a +/- sigil (`-doThing`); strip it so the
            # selector `doThing` keys to the method.
            method_index[(src, _key(tnode.get("label", "")))] = tgt

    all_raw_calls: list[dict] = []
    for result in per_file:
        all_raw_calls.extend(result.get("raw_calls", []))

    existing_pairs = {(e.get("source"), e.get("target")) for e in all_edges}
    for rc in all_raw_calls:
        if not rc.get("is_member_call"):
            continue
        receiver = rc.get("receiver")
        callee = rc.get("callee")
        caller = rc.get("caller_nid")
        if not receiver or not callee or not caller:
            continue
        src_file = rc.get("source_file", "")
        if rc.get("lang") != "objc":
            continue
        if receiver in ("self", "super"):
            type_nid = enclosing_type.get(caller)
            if not type_nid:
                continue
            type_qualified = True
        elif receiver[:1].isupper():
            type_defs = type_def_nids.get(_key(receiver), [])
            if len(type_defs) != 1:  # ambiguous or absent -> bail (god-node guard)
                continue
            type_nid = type_defs[0]
            type_qualified = True
        else:
            type_name = type_table_by_file.get(src_file, {}).get(receiver)
            if not type_name:
                continue
            type_defs = type_def_nids.get(_key(type_name), [])
            if len(type_defs) != 1:  # ambiguous or absent -> bail (god-node guard)
                continue
            type_nid = type_defs[0]
            type_qualified = False
        method_nid = method_index.get((type_nid, _key(callee)))
        target = method_nid or type_nid
        relation = "calls" if method_nid else "references"
        if target == caller or (caller, target) in existing_pairs:
            continue
        existing_pairs.add((caller, target))
        all_edges.append({
            "source": caller,
            "target": target,
            "relation": relation,
            "context": "call",
            "confidence": "EXTRACTED" if type_qualified else "INFERRED",
            "confidence_score": 1.0 if type_qualified else 0.8,
            "source_file": src_file,
            "source_location": rc.get("source_location"),
            "weight": 1.0,
        })


# Register the cross-file, language-specific member-call resolvers into the shared
# registry (framework lives in graphify.resolver_registry). A new language plugs in
# by adding one register() call below — no edits to extract()'s body. Order
# preserved from the prior inlined wiring: Swift (#1356) before Python (#1446).
register_language_resolver(
    LanguageResolver("swift_member_calls", frozenset({".swift"}), _resolve_swift_member_calls)
)
register_language_resolver(
    LanguageResolver("python_member_calls", frozenset({".py"}), _resolve_python_member_calls)
)
# Ruby type-aware member-call resolution (Class.new + typed var.method). Lives in
# graphify.ruby_resolution; registered here as a second consumer of the framework.
register_language_resolver(
    LanguageResolver("ruby_member_calls", frozenset({".rb", ".rake"}), resolve_ruby_member_calls)
)
register_language_resolver(
    LanguageResolver("typescript_member_calls", frozenset({".ts", ".tsx", ".mts", ".cts", ".js", ".jsx"}), _resolve_typescript_member_calls)
)
# C++ (#1547) and ObjC (#1556) receiver-typed member-call resolution. `.h` is in
# both suffix sets because it routes to extract_cpp or extract_objc by content; the
# resolvers each claim only their own raw_calls via the extractor-stamped `lang`.
register_language_resolver(
    LanguageResolver(
        "cpp_member_calls",
        frozenset({".cpp", ".cc", ".cxx", ".hpp", ".cu", ".cuh", ".metal", ".h"}),
        _resolve_cpp_member_calls,
    )
)
register_language_resolver(
    LanguageResolver(
        "objc_member_calls",
        frozenset({".m", ".mm", ".h"}),
        _resolve_objc_member_calls,
    )
)
# C# receiver-typed member-call resolution (#1609): `field/param/local.Method()`
# bound to the receiver's declared type instead of a bare same-named match.
register_language_resolver(
    LanguageResolver("csharp_member_calls", frozenset({".cs"}), _resolve_csharp_member_calls)
)
register_language_resolver(
    LanguageResolver("java_member_calls", frozenset({".java"}), _resolve_java_member_calls)
)
# Pascal/Delphi cross-file inherited-method-call resolution: a call from a
# manual descendant class to a method it inherits from an ancestor declared
# in a DIFFERENT file (the common generated-base/manual-descendant split,
# e.g. Sistec's Th0Xxx/Th5Xxx) falls outside the per-file extractor's own
# scope. Lives in graphify.pascal_resolution; registered here as a consumer
# of the framework, same as the Ruby resolver above.
register_language_resolver(
    LanguageResolver(
        "pascal_inherited_calls",
        frozenset({".pas", ".pp", ".dpr", ".dpk", ".inc"}),
        resolve_pascal_inherited_calls,
    )
)


# Inline markdown link: [text](target "optional title"). The negative lookbehind
# excludes images (![alt](src)). The target stops at whitespace/closing paren so
# an optional "title" after the URL is dropped; an optional <...> wrapper is too.
# Reference-style link definition line: [label]: target "optional title"
# Obsidian-style wikilink: [[target]] / [[target|alias]] / [[target#anchor]].

# Extensions graphify creates document file nodes for. A link to one of these
# resolves to that file's node; links to code/assets are skipped (left to the
# language extractors).


# ── Pascal / Delphi extractor ─────────────────────────────────────────────────


# Size cap for project XML files we parse with stdlib ElementTree.
# Real .csproj/.fsproj/.vbproj/.lpk files are well under 2 MiB; anything
# larger is either malformed or hostile.
_PROJECT_XML_MAX_BYTES = 2 * 1024 * 1024


def _project_xml_is_safe(src: bytes) -> bool:
    """Reject XML that declares DTDs or entities.

    Stdlib ``xml.etree.ElementTree`` does not cap entity expansion, so a
    crafted project file could trigger a billion-laughs style DoS. External
    entity resolution is already disabled by pyexpat defaults, but rejecting
    ``<!DOCTYPE`` / ``<!ENTITY`` outright is defense in depth.

    Legitimate MSBuild and Lazarus package files never contain a DOCTYPE
    or ENTITY declaration, so this is a zero-false-positive screen.
    """
    # Only the prolog can hold a DTD/internal subset, but be conservative
    # and scan the full byte range -- these formats use ASCII tags so a
    # case-insensitive substring match is sufficient.
    lowered = src.lower()
    return b"<!doctype" not in lowered and b"<!entity" not in lowered


def extract_lazarus_package(path: Path) -> dict:
    """Extract package metadata from Lazarus .lpk package files (XML format).

    .lpk is an XML file listing the package name, required dependencies,
    and the Pascal units that belong to the package.

    Produces nodes for:
    - The package file itself
    - The package (by name)
    - Each required package (dependency)
    - Each listed unit file (resolved to path-based IDs where possible)

    Produces edges for:
    - file --contains--> package
    - package --imports--> required dependency (context: "import")
    - package --contains--> listed unit
    """
    try:
        import xml.etree.ElementTree as ET
        src = path.read_bytes()
    except OSError as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    if len(src) > _PROJECT_XML_MAX_BYTES:
        return {"nodes": [], "edges": [], "error": "package file too large"}
    if not _project_xml_is_safe(src):
        return {"nodes": [], "edges": [],
                "error": "refusing XML with DOCTYPE/ENTITY declaration"}

    try:
        xml_root = ET.fromstring(src)
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    str_path = str(path)
    stem = _file_stem(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()

    def add_node(nid: str, label: str) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({
                "id": nid, "label": label, "file_type": "code",
                "source_file": str_path, "source_location": "L1",
            })

    def add_edge(src: str, tgt: str, relation: str, context: str | None = None) -> None:
        edge: dict[str, Any] = {
            "source": src, "target": tgt, "relation": relation,
            "confidence": "EXTRACTED", "source_file": str_path,
            "source_location": "L1", "weight": 1.0,
        }
        if context:
            edge["context"] = context
        edges.append(edge)

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name)

    name_elem = xml_root.find(".//Package/Name")
    pkg_name = name_elem.get("Value") if name_elem is not None else path.stem
    pkg_nid = _make_id(stem, pkg_name)
    add_node(pkg_nid, pkg_name)
    add_edge(file_nid, pkg_nid, "contains")

    # Required packages → imports edges
    for item in xml_root.findall(".//RequiredPkgs/"):
        dep_elem = item.find("PackageName")
        if dep_elem is not None:
            dep_name = dep_elem.get("Value", "")
            if dep_name:
                dep_nid = _make_id(dep_name)
                add_node(dep_nid, dep_name)
                add_edge(pkg_nid, dep_nid, "imports", context="import")

    # Listed units → contains edges, resolved to path-based IDs where possible
    for item in xml_root.findall(".//Files/"):
        unit_elem = item.find("UnitName")
        if unit_elem is not None:
            unit_name = unit_elem.get("Value", "")
            if unit_name:
                unit_nid = _pascal_resolve_unit(path, unit_name)
                add_node(unit_nid, unit_name)
                add_edge(pkg_nid, unit_nid, "contains")

    return {"nodes": nodes, "edges": edges, "input_tokens": 0, "output_tokens": 0}


# ── Main extract and collect_files ────────────────────────────────────────────


def _check_tree_sitter_version() -> None:
    """Raise a clear error if tree-sitter is too old for the new Language API."""
    try:
        from tree_sitter import LANGUAGE_VERSION
    except ImportError:
        raise ImportError(
            "tree-sitter is not installed. Run: pip install 'tree-sitter>=0.23.0'"
        )
    # Language API v2 starts at LANGUAGE_VERSION 14
    if LANGUAGE_VERSION < 14:
        import tree_sitter as _ts
        raise RuntimeError(
            f"tree-sitter {getattr(_ts, '__version__', 'unknown')} is too old. "
            f"graphify requires tree-sitter >= 0.23.0 (Language API v2). "
            f"Run: pip install --upgrade tree-sitter"
        )


# ── .NET project files (.sln, .slnx, .csproj, .razor) ───────────────────────


def extract_slnx(path: Path) -> dict:
    """Extract projects and inter-project dependencies from a .slnx file.

    .slnx is the XML-based replacement for the legacy .sln format. Projects
    are listed as ``<Project Path="..."/>`` elements (optionally nested inside
    ``<Folder>`` elements) and build-order dependencies as ``<BuildDependency
    Project="..."/>`` children. Unlike .sln there are no GUIDs -- projects are
    identified by their path.
    """
    import xml.etree.ElementTree as ET

    try:
        src = path.read_bytes()
    except OSError:
        return {"nodes": [], "edges": [], "error": f"cannot read {path}"}

    if len(src) > _PROJECT_XML_MAX_BYTES:
        return {"nodes": [], "edges": [], "error": "project file too large"}
    if not _project_xml_is_safe(src):
        return {"nodes": [], "edges": [],
                "error": "refusing XML with DOCTYPE/ENTITY declaration"}

    try:
        tree = ET.fromstring(src)
    except ET.ParseError as e:
        return {"nodes": [], "edges": [], "error": f"XML parse error: {e}"}

    file_nid = _make_id(str(path))
    str_path = str(path)
    nodes: list[dict] = [{"id": file_nid, "label": path.name, "file_type": "code",
                          "source_file": str_path, "source_location": None}]
    edges: list[dict] = []
    seen_ids: set[str] = set()
    seen_ids.add(file_nid)

    ns = ""
    if tree.tag.startswith("{"):
        ns = tree.tag.split("}")[0] + "}"

    def _resolve(proj_path: str) -> str:
        proj_path = proj_path.replace("\\", "/")
        try:
            return str((path.parent / proj_path).resolve())
        except Exception:
            return proj_path

    # First pass: collect projects (anywhere in the tree, incl. <Folder>).
    project_nids: set[str] = set()
    for proj in tree.iter(f"{ns}Project"):
        proj_path = proj.get("Path")
        if not proj_path:
            continue
        abs_proj = _resolve(proj_path)
        proj_nid = _make_id(abs_proj)
        if proj_nid and proj_nid not in seen_ids:
            seen_ids.add(proj_nid)
            label = Path(proj_path).stem
            nodes.append({"id": proj_nid, "label": label,
                          "file_type": "code", "source_file": abs_proj,
                          "source_location": None})
            edges.append({"source": file_nid, "target": proj_nid,
                          "relation": "contains", "confidence": "EXTRACTED",
                          "source_file": str_path, "weight": 1.0})
        if proj_nid:
            project_nids.add(proj_nid)

    # Second pass: build-order dependencies between known projects.
    for proj in tree.iter(f"{ns}Project"):
        proj_path = proj.get("Path")
        if not proj_path:
            continue
        from_nid = _make_id(_resolve(proj_path))
        for dep in proj.iter(f"{ns}BuildDependency"):
            dep_path = dep.get("Project")
            if not dep_path:
                continue
            to_nid = _make_id(_resolve(dep_path))
            if (from_nid and to_nid and from_nid != to_nid
                    and to_nid in project_nids):
                edges.append({"source": from_nid, "target": to_nid,
                              "relation": "imports", "confidence": "EXTRACTED",
                              "source_file": str_path, "weight": 1.0})

    return {"nodes": nodes, "edges": edges}


def extract_csproj(path: Path) -> dict:
    """Extract packages, project refs, and target framework from a .csproj/.fsproj/.vbproj."""
    import xml.etree.ElementTree as ET

    try:
        src = path.read_bytes()
    except OSError:
        return {"nodes": [], "edges": [], "error": f"cannot read {path}"}

    if len(src) > _PROJECT_XML_MAX_BYTES:
        return {"nodes": [], "edges": [], "error": "project file too large"}
    if not _project_xml_is_safe(src):
        return {"nodes": [], "edges": [],
                "error": "refusing XML with DOCTYPE/ENTITY declaration"}

    try:
        tree = ET.fromstring(src)
    except ET.ParseError as e:
        return {"nodes": [], "edges": [], "error": f"XML parse error: {e}"}

    file_nid = _make_id(str(path))
    str_path = str(path)
    nodes: list[dict] = [{"id": file_nid, "label": path.name, "file_type": "code",
                          "source_file": str_path, "source_location": None}]
    edges: list[dict] = []
    seen_ids: set[str] = set()
    seen_ids.add(file_nid)

    ns = ""
    root_tag = tree.tag
    if root_tag.startswith("{"):
        ns = root_tag.split("}")[0] + "}"

    def find_all(tag: str):
        return tree.iter(f"{ns}{tag}")

    for tf in find_all("TargetFramework"):
        if tf.text:
            fw_nid = _make_id("framework", tf.text.strip())
            if fw_nid and fw_nid not in seen_ids:
                seen_ids.add(fw_nid)
                nodes.append({"id": fw_nid, "label": tf.text.strip(),
                              "file_type": "concept", "source_file": str_path,
                              "source_location": None})
                edges.append({"source": file_nid, "target": fw_nid,
                              "relation": "references", "confidence": "EXTRACTED",
                              "source_file": str_path, "weight": 1.0})

    for tf in find_all("TargetFrameworks"):
        if tf.text:
            for fw in tf.text.strip().split(";"):
                fw = fw.strip()
                if fw:
                    fw_nid = _make_id("framework", fw)
                    if fw_nid and fw_nid not in seen_ids:
                        seen_ids.add(fw_nid)
                        nodes.append({"id": fw_nid, "label": fw,
                                      "file_type": "concept", "source_file": str_path,
                                      "source_location": None})
                        edges.append({"source": file_nid, "target": fw_nid,
                                      "relation": "references", "confidence": "EXTRACTED",
                                      "source_file": str_path, "weight": 1.0})

    for pkg in find_all("PackageReference"):
        name = pkg.get("Include") or pkg.get("include") or ""
        version = pkg.get("Version") or pkg.get("version") or ""
        if not name:
            continue
        pkg_nid = _make_id("nuget", name)
        label = f"{name} ({version})" if version else name
        if pkg_nid and pkg_nid not in seen_ids:
            seen_ids.add(pkg_nid)
            nodes.append({"id": pkg_nid, "label": label,
                          "file_type": "code", "source_file": str_path,
                          "source_location": None})
        edges.append({"source": file_nid, "target": pkg_nid,
                      "relation": "imports", "confidence": "EXTRACTED",
                      "source_file": str_path, "weight": 1.0})

    for proj in find_all("ProjectReference"):
        ref_path = proj.get("Include") or proj.get("include") or ""
        if not ref_path:
            continue
        ref_path_norm = ref_path.replace("\\", "/")
        try:
            abs_ref = str((path.parent / ref_path_norm).resolve())
        except Exception:
            abs_ref = ref_path_norm
        proj_nid = _make_id(abs_ref)
        if proj_nid and proj_nid not in seen_ids:
            seen_ids.add(proj_nid)
            proj_label = Path(ref_path_norm).name
            nodes.append({"id": proj_nid, "label": proj_label,
                          "file_type": "code", "source_file": abs_ref,
                          "source_location": None})
        edges.append({"source": file_nid, "target": proj_nid,
                      "relation": "imports", "confidence": "EXTRACTED",
                      "source_file": str_path, "weight": 1.0})

    sdk = tree.get("Sdk") or ""
    if sdk:
        sdk_nid = _make_id("sdk", sdk)
        if sdk_nid and sdk_nid not in seen_ids:
            seen_ids.add(sdk_nid)
            nodes.append({"id": sdk_nid, "label": sdk,
                          "file_type": "concept", "source_file": str_path,
                          "source_location": None})
            edges.append({"source": file_nid, "target": sdk_nid,
                          "relation": "references", "confidence": "EXTRACTED",
                          "source_file": str_path, "weight": 1.0})

    return {"nodes": nodes, "edges": edges}


def _xml_local_name(name: str) -> str:
    return name.rsplit("}", 1)[-1] if name.startswith("{") else name


# A .NET event handler has the signature `(object sender, <T>EventArgs e)`. Used
# to tell a real event handler in the code-behind apart from an ordinary method
# whose name a XAML attribute value happens to match. Tolerates `object?`, a
# namespace-qualified args type, and a generic `EventArgs<T>`.
_EVENT_HANDLER_SIGNATURE_RE = re.compile(
    r"\(\s*object\??\s+\w+\s*,\s*[\w.]*EventArgs(?:<[^>]*>)?\s+\w+\s*\)"
)

# XAML attribute names that carry free-form strings or identifiers and never name
# an event handler. They are skipped when matching attribute values to code-behind
# methods so e.g. Content="Save" or Tag="Refresh" can't fabricate an event edge.
_XAML_NON_EVENT_ATTRS = frozenset({
    "Name", "Content", "Text", "Title", "Tag", "ToolTip", "Header",
    "Class", "Key", "Uid", "DataContext", "Style", "Source",
})

# A handler attribute value is a bare method name (e.g. Click="Save_Click"), not
# markup, a path, or a sentence. Used to skip values like "{Binding ...}" or
# free-form content before looking them up as code-behind methods.
_XAML_IDENT_RE = re.compile(r"[A-Za-z_]\w*")
_XAML_DESIGN_INSTANCE_TYPE_RE = re.compile(
    r"\bType\s*=\s*(?:\{x:Type\s+)?(?P<type>[\w.:+]+)"
)


def _xaml_markup_extension(value: str) -> tuple[str, str] | None:
    value = value.strip()
    if not (value.startswith("{") and value.endswith("}")):
        return None
    inner = value[1:-1].strip()
    if not inner or inner.startswith("}"):
        return None
    name, _, args = inner.partition(" ")
    return name, args.strip()


def _xaml_split_markup_args(args: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    for idx, ch in enumerate(args):
        if ch == "{":
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(args[start:idx].strip())
            start = idx + 1
    tail = args[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def _xaml_static_resource_key(value: str) -> str | None:
    markup = _xaml_markup_extension(value)
    if not markup:
        return None
    name, args = markup
    if name != "StaticResource":
        return None
    for part in _xaml_split_markup_args(args):
        if "=" not in part:
            return part.strip() or None
        key, resource = part.split("=", 1)
        if key.strip() == "ResourceKey":
            return resource.strip() or None
    return None


def _xaml_binding_refs(value: str) -> tuple[str | None, str | None]:
    markup = _xaml_markup_extension(value)
    if not markup:
        return None, None
    name, args = markup
    if name != "Binding":
        return None, None

    path_ref = None
    converter_ref = None
    for part in _xaml_split_markup_args(args):
        if not part:
            continue
        if "=" not in part:
            if path_ref is None:
                path_ref = part.strip()
            continue
        key, raw_value = part.split("=", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        if key == "Path":
            path_ref = raw_value
        elif key == "Converter":
            converter_ref = _xaml_static_resource_key(raw_value)

    if path_ref and ("{" in path_ref or "}" in path_ref):
        path_ref = None
    return path_ref or None, converter_ref or None


def _xaml_codebehind_path(path: Path) -> Path | None:
    expected = path.with_suffix(path.suffix + ".cs")
    if expected.exists():
        return expected
    try:
        for sibling in path.parent.iterdir():
            if sibling.name.casefold() == expected.name.casefold():
                return sibling
    except OSError:
        return None
    return None


def _xaml_codebehind_symbols(
    path: Path,
    class_name: str | None,
) -> tuple[dict | None, dict[str, dict], list[dict]]:
    codebehind = _xaml_codebehind_path(path)
    if not codebehind:
        return None, {}, []
    result = extract_csharp(codebehind)
    if result.get("error"):
        return None, {}, []

    class_simple = class_name.rsplit(".", 1)[-1] if class_name else None
    class_node = None
    if class_simple:
        for node in result.get("nodes", []):
            if node.get("label") == class_simple:
                class_node = node
                break

    class_method_edges: list[dict] = []
    if class_node:
        class_id = class_node.get("id")
        for edge in result.get("edges", []):
            if edge.get("source") == class_id and edge.get("relation") == "method":
                class_method_edges.append(edge)
    method_ids = {edge.get("target") for edge in class_method_edges} if class_node else None

    # Only methods with a .NET event-handler signature -- (object sender,
    # <T>EventArgs e) -- are eligible to be wired to a XAML attribute as an
    # event. Without this gate, any attribute whose value happens to match a
    # method name (e.g. Content="Save" next to a business method Save()) would
    # produce a spurious "event" edge. The C# extractor does not record the
    # parameter list on method nodes, so we read it from the code-behind source
    # at the method's recorded line.
    try:
        cb_lines = codebehind.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        cb_lines = []

    def _has_event_handler_signature(node: dict) -> bool:
        loc = str(node.get("source_location") or "")
        m = re.match(r"L(\d+)", loc)
        if not m or not cb_lines:
            return False
        start = int(m.group(1)) - 1
        # Join a few lines so a signature split across lines still matches.
        snippet = " ".join(cb_lines[start:start + 3])
        return _EVENT_HANDLER_SIGNATURE_RE.search(snippet) is not None

    methods: dict[str, dict] = {}
    for node in result.get("nodes", []):
        if method_ids is not None and node.get("id") not in method_ids:
            continue
        label = str(node.get("label", ""))
        if label.startswith(".") and label.endswith("()") and _has_event_handler_signature(node):
            methods[label.strip("()").lstrip(".")] = node
    return class_node, methods, class_method_edges


def _xaml_type_simple_name(type_ref: str) -> str | None:
    type_ref = type_ref.strip().strip("{}")
    if not type_ref:
        return None
    type_ref = type_ref.split(",", 1)[0].strip()
    if type_ref.startswith("x:Type "):
        type_ref = type_ref[len("x:Type "):].strip()
    if ":" in type_ref:
        type_ref = type_ref.rsplit(":", 1)[-1]
    if "." in type_ref:
        type_ref = type_ref.rsplit(".", 1)[-1]
    if "+" in type_ref:
        type_ref = type_ref.rsplit("+", 1)[-1]
    return type_ref if _XAML_IDENT_RE.fullmatch(type_ref) else None


def _xaml_explicit_viewmodel_names(tree) -> tuple[bool, list[str]]:
    has_data_context = False
    names: list[str] = []
    for elem in tree.iter():
        elem_type = _xml_local_name(elem.tag)
        if elem_type.endswith(".DataContext") or elem_type == "DataContext":
            has_data_context = True
            for child in list(elem):
                vm_name = _xaml_type_simple_name(_xml_local_name(child.tag))
                if vm_name and vm_name not in names:
                    names.append(vm_name)
        for key, value in elem.attrib.items():
            if _xml_local_name(key) != "DataContext" or not value:
                continue
            has_data_context = True
            match = _XAML_DESIGN_INSTANCE_TYPE_RE.search(value)
            if match:
                vm_name = _xaml_type_simple_name(match.group("type"))
                if vm_name and vm_name not in names:
                    names.append(vm_name)
    return has_data_context, names


def _xaml_prism_autowire_viewmodel(tree) -> bool:
    for elem in tree.iter():
        for key, value in elem.attrib.items():
            if (
                _xml_local_name(key).endswith("ViewModelLocator.AutoWireViewModel")
                and value.strip().lower() == "true"
            ):
                return True
    return False


def _xaml_inferred_viewmodel_names(view_name: str | None) -> list[str]:
    if not view_name:
        return []
    names: list[str] = []

    def add(name: str) -> None:
        if name.endswith("ViewModel") and name not in names:
            names.append(name)

    if view_name == "MainWindow":
        add("MainWindowViewModel")
        add("MainViewModel")
    for suffix in ("UserControl", "View", "Page", "Control"):
        if view_name.endswith(suffix) and len(view_name) > len(suffix):
            add(view_name[:-len(suffix)] + "ViewModel")
            break
    return names


def _xaml_project_root(path: Path) -> Path:
    project_markers = (".csproj", ".fsproj", ".vbproj", ".sln", ".slnx")
    root = path.parent
    for directory in (path.parent, *path.parent.parents):
        try:
            if any(child.suffix in project_markers for child in directory.iterdir()):
                root = directory
                break
        except OSError:
            continue
    if _XAML_ACTIVE_EXTRACT_ROOT is None:
        return root
    boundary = _XAML_ACTIVE_EXTRACT_ROOT.resolve()
    try:
        root.resolve().relative_to(boundary)
        return root
    except ValueError:
        return boundary


def _xaml_csharp_class_nodes(path: Path) -> dict[str, list[dict]]:
    from graphify.detect import _is_ignored, _is_noise_dir, _load_graphifyignore
    root = _xaml_project_root(path)
    cache_key = str(root.resolve()) if _XAML_ACTIVE_EXTRACT_ROOT is not None else None
    if cache_key and cache_key in _XAML_CSHARP_CLASS_CACHE:
        return _XAML_CSHARP_CLASS_CACHE[cache_key]
    classes: dict[str, list[dict]] = {}
    patterns = _load_graphifyignore(root)
    ignore_cache: dict[Path, bool] = {}
    try:
        cs_files = sorted(root.rglob("*.cs"))
    except OSError:
        return classes
    for cs_path in cs_files:
        if any(_is_noise_dir(part) for part in cs_path.parts):
            continue
        if patterns and _is_ignored(cs_path, root, patterns, _cache=ignore_cache):
            continue
        result = extract_csharp(cs_path)
        if result.get("error"):
            continue
        for node in result.get("nodes", []):
            label = str(node.get("label", ""))
            if not label.endswith("ViewModel") or not _XAML_IDENT_RE.fullmatch(label):
                continue
            if node.get("source_file"):
                classes.setdefault(label, []).append(node)
    if cache_key:
        _XAML_CSHARP_CLASS_CACHE[cache_key] = classes
    return classes


def _xaml_pascal_name(name: str) -> str | None:
    name = name.strip().lstrip("_")
    if name.startswith("m_"):
        name = name[2:]
    return name[:1].upper() + name[1:] if _XAML_IDENT_RE.fullmatch(name) else None


_XAML_TOOLKIT_FIELD_RE = re.compile(r"\b(?P<name>_?m?_?[A-Za-z_]\w*)\s*(?:=.*)?;")
_XAML_TOOLKIT_METHOD_RE = re.compile(r"\b(?P<name>[A-Za-z_]\w*)\s*\(")
_XAML_ACTIVE_EXTRACT_ROOT: Path | None = None
_XAML_CSHARP_CLASS_CACHE: dict[str, dict[str, list[dict]]] = {}


def _xaml_communitytoolkit_members(vm_node: dict) -> tuple[dict[str, dict], list[dict]]:
    source_file = vm_node.get("source_file")
    vm_id = vm_node.get("id")
    if not source_file or not vm_id:
        return {}, []
    try:
        # errors="replace" so a non-UTF8 code-behind can't raise UnicodeDecodeError
        # and abort the whole extract_xaml (matches every other reader here).
        lines = Path(source_file).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {}, []

    members: dict[str, dict] = {}
    edges: list[dict] = []

    def add_member(label: str, line_no: int, context: str) -> None:
        nid = _make_id(vm_id, label)
        members[label] = {
            "id": nid,
            "label": label,
            "file_type": "code",
            "source_file": source_file,
            "source_location": f"L{line_no}",
        }
        edges.append({
            "source": vm_id,
            "target": nid,
            "relation": "defines",
            "confidence": "INFERRED",
            "source_file": source_file,
            "source_location": f"L{line_no}",
            "weight": 1.0,
            "context": context,
        })

    pending: tuple[str, int] | None = None
    for line_no, line in enumerate(lines, 1):
        remainder = line.split("]", 1)[1].strip() if "]" in line else ""
        if "[" in line and "ObservableProperty" in line:
            pending = ("property", line_no)
            if not remainder:
                continue
            line = remainder
        if "[" in line and "RelayCommand" in line:
            pending = ("command", line_no)
            if not remainder:
                continue
            line = remainder
        if not pending or not line.strip() or line.lstrip().startswith("["):
            continue

        kind, attr_line = pending
        pending = None
        if kind == "property":
            match = _XAML_TOOLKIT_FIELD_RE.search(line)
            label = _xaml_pascal_name(match.group("name")) if match else None
            if label:
                add_member(label, attr_line, "communitytoolkit_observable_property")
        else:
            match = _XAML_TOOLKIT_METHOD_RE.search(line)
            if match:
                method = match.group("name").removesuffix("Async")
                add_member(f"{method}Command", attr_line, "communitytoolkit_relay_command")

    return members, edges


def extract_xaml(path: Path) -> dict:
    """Extract WPF/XAML structure, bindings, x:Class, and event handler references."""
    import xml.etree.ElementTree as ET

    try:
        src = path.read_bytes()
    except OSError:
        return {"nodes": [], "edges": [], "error": f"cannot read {path}"}

    if len(src) > _PROJECT_XML_MAX_BYTES:
        return {"nodes": [], "edges": [], "error": "xaml file too large"}
    if not _project_xml_is_safe(src):
        return {"nodes": [], "edges": [],
                "error": "refusing XML with DOCTYPE/ENTITY declaration"}

    try:
        tree = ET.fromstring(src)
    except ET.ParseError as e:
        return {"nodes": [], "edges": [], "error": f"XML parse error: {e}"}

    text = src.decode("utf-8", errors="replace")
    lines = text.splitlines()
    str_path = str(path)
    stem = _file_stem(path)
    file_nid = _make_id(str(path))
    root_type = _xml_local_name(tree.tag)
    root_nid = _make_id(stem, root_type)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()
    seen_edges: set[tuple[str, str, str, str | None]] = set()

    def line_for(value: str | None) -> int:
        if value:
            for idx, line in enumerate(lines, 1):
                if value in line:
                    return idx
        return 1

    def add_node(
        nid: str,
        label: str,
        line: int | None,
        *,
        file_type: str = "code",
        source_file: str = str_path,
    ) -> None:
        if nid in seen_ids:
            return
        seen_ids.add(nid)
        nodes.append({
            "id": nid, "label": label, "file_type": file_type,
            "source_file": source_file,
            "source_location": f"L{line}" if line else None,
        })

    def add_existing_node(node: dict | None) -> None:
        if not node:
            return
        nid = node.get("id")
        if not nid or nid in seen_ids:
            return
        seen_ids.add(nid)
        nodes.append(dict(node))

    def add_edge(
        src_nid: str,
        tgt_nid: str,
        relation: str,
        line: int,
        *,
        context: str | None = None,
        source_file: str = str_path,
        confidence: str = "EXTRACTED",
    ) -> None:
        key = (src_nid, tgt_nid, relation, context)
        if key in seen_edges:
            return
        seen_edges.add(key)
        edge = {
            "source": src_nid, "target": tgt_nid, "relation": relation,
            "confidence": confidence, "source_file": source_file,
            "source_location": f"L{line}", "weight": 1.0,
        }
        if context:
            edge["context"] = context
        edges.append(edge)

    def add_existing_edge(edge: dict) -> None:
        key = (edge.get("source"), edge.get("target"), edge.get("relation"), edge.get("context"))
        if key in seen_edges:
            return
        seen_edges.add(key)
        edges.append(dict(edge))

    add_node(file_nid, path.name, 1)
    add_node(root_nid, root_type, 1)
    add_edge(file_nid, root_nid, "contains", 1)

    class_name = None
    for key, value in tree.attrib.items():
        if _xml_local_name(key) == "Class" and value:
            class_name = value.strip()
            break

    class_node, codebehind_methods, class_method_edges = _xaml_codebehind_symbols(path, class_name)
    if class_name:
        if class_node:
            class_nid = class_node["id"]
            add_existing_node(class_node)
        else:
            class_label = class_name.rsplit(".", 1)[-1]
            class_nid = _make_id(stem, class_label)
            add_node(class_nid, class_label, line_for(class_name))
        add_edge(root_nid, class_nid, "references", line_for(class_name), context="x_class")

    has_data_context, vm_names = _xaml_explicit_viewmodel_names(tree)
    prism_autowire = _xaml_prism_autowire_viewmodel(tree)
    vm_confidence = "EXTRACTED"
    if not has_data_context:
        view_name = class_name.rsplit(".", 1)[-1] if class_name else None
        view_name = view_name or (path.stem if prism_autowire else None)
        vm_names = _xaml_inferred_viewmodel_names(view_name)
        vm_confidence = "INFERRED"
    generated_members: dict[str, dict] = {}
    generated_member_edges: list[dict] = []
    if vm_names:
        csharp_classes = _xaml_csharp_class_nodes(path)
        vm_candidates = []
        for vm_name in vm_names:
            vm_candidates.extend(csharp_classes.get(vm_name, []))
        by_id = {node.get("id"): node for node in vm_candidates if node.get("id")}
        if len(by_id) == 1:
            vm_node = next(iter(by_id.values()))
            add_existing_node(vm_node)
            add_edge(
                root_nid,
                vm_node["id"],
                "references",
                line_for(vm_node["label"]),
                context="view_model",
                confidence=vm_confidence,
            )
            generated_members, generated_member_edges = _xaml_communitytoolkit_members(vm_node)
            for member in generated_members.values():
                add_existing_node(member)
            for member_edge in generated_member_edges:
                add_existing_edge(member_edge)

    for elem in tree.iter():
        elem_type = _xml_local_name(elem.tag)
        elem_name = None
        for key, value in elem.attrib.items():
            if _xml_local_name(key) == "Name" and value:
                elem_name = value.strip()
                break
        owner_nid = root_nid
        if elem_name:
            owner_nid = _make_id(stem, elem_name)
            add_node(owner_nid, elem_name, line_for(elem_name))
            add_edge(root_nid, owner_nid, "contains", line_for(elem_name))
            type_nid = _make_id("xaml", elem_type)
            add_node(type_nid, elem_type, line_for(elem_name), file_type="concept")
            add_edge(owner_nid, type_nid, "references", line_for(elem_name), context="type")

        for key, value in elem.attrib.items():
            value = value or ""
            # Event wiring: an attribute references a handler only when its local
            # name isn't a known free-form/identity property, its value is a bare
            # identifier (a method name, not markup or a sentence), and the matched
            # code-behind method actually has an event-handler signature (the gate
            # in _xaml_codebehind_symbols). This stops Content="Save" / Tag="..."
            # from fabricating event edges against same-named ordinary methods.
            attr_local = _xml_local_name(key)
            if attr_local not in _XAML_NON_EVENT_ATTRS and _XAML_IDENT_RE.fullmatch(value):
                method = codebehind_methods.get(value)
                if method:
                    add_existing_node(method)
                    add_edge(owner_nid, method["id"], "references", line_for(value), context="event")
                    for method_edge in class_method_edges:
                        if method_edge.get("target") == method["id"]:
                            add_existing_node(class_node)
                            add_existing_edge(method_edge)
                            break
            binding_path, binding_converter = _xaml_binding_refs(value)
            if binding_path:
                bind_nid = _make_id("binding", binding_path)
                add_node(bind_nid, binding_path, line_for(value), file_type="concept")
                binding_context = (
                    "binding_command"
                    if attr_local == "Command" or attr_local.endswith(".Command")
                    else "binding_path"
                )
                add_edge(owner_nid, bind_nid, "references", line_for(value), context=binding_context)
                generated_member = generated_members.get(binding_path)
                if generated_member:
                    add_existing_node(generated_member)
                    add_edge(
                        owner_nid,
                        generated_member["id"],
                        "references",
                        line_for(value),
                        context=binding_context,
                        confidence="INFERRED",
                    )
            if binding_converter:
                converter_nid = _make_id("binding_converter", binding_converter)
                add_node(converter_nid, binding_converter, line_for(value), file_type="concept")
                add_edge(owner_nid, converter_nid, "references", line_for(value), context="binding_converter")
            if elem_type == "Binding" and attr_local == "Path":
                direct_path = value.strip()
                if direct_path and "{" not in direct_path and "}" not in direct_path:
                    bind_nid = _make_id("binding", direct_path)
                    add_node(bind_nid, direct_path, line_for(value), file_type="concept")
                    add_edge(owner_nid, bind_nid, "references", line_for(value), context="binding_path")
            if elem_type == "Binding" and attr_local == "Converter":
                direct_converter = _xaml_static_resource_key(value)
                if direct_converter:
                    converter_nid = _make_id("binding_converter", direct_converter)
                    add_node(converter_nid, direct_converter, line_for(value), file_type="concept")
                    add_edge(owner_nid, converter_nid, "references", line_for(value), context="binding_converter")

    return {"nodes": nodes, "edges": edges}


# Config/manifest JSON filenames the structural extractor understands. Anything
# else (eval fixtures, datasets, GeoJSON, API dumps) is *data* and must NOT be
# AST-walked into per-key nodes — that floods the graph with orphan key-nodes
# and near-duplicate communities (#1224). Data JSON is left to the LLM semantic
# pass instead. Matched case-insensitively against the bare filename.

# Top-level keys that prove a JSON object is a config/manifest the extractor can
# draw *cross-file* edges from (deps, extends chains, schema refs).


# ── DM (BYOND DreamMaker) extractor ──────────────────────────────────────────
# DM identity is path-based (`/datum/object/proc/New()`), not block-based, so
# the generic class-body walker doesn't fit well.


# ── DMI (BYOND icon files) ────────────────────────────────────────────────────
# .dmi is a PNG with a tEXt/zTXt "Description" chunk containing BYOND state
# metadata. We want the icon state names (icon_state = "X" in DM code
# references them).


# ── DMM (BYOND map files) ─────────────────────────────────────────────────────
# A .dmm starts with a tile dictionary — each "key" = (type, type{var=val}, ...)
# names one or more types that compose a tile — then a grid. We only need the
# dictionary section: every type path referenced is a `uses` edge.


# ── DMF (BYOND interface forms) ───────────────────────────────────────────────


# Head tokens in an HCL traversal that are meta/builtins, not references to a
# block defined in the corpus (count.index, each.key, self.*, path.module, ...).


_DISPATCH: dict[str, Any] = {
    ".py": extract_python,
    ".js": extract_js,
    ".jsx": extract_js,
    ".mjs": extract_js,
    ".ts": extract_js,
    ".tsx": extract_js,
    ".mts": extract_js,
    ".cts": extract_js,
    ".go": extract_go,
    ".rs": extract_rust,
    ".java": extract_java,
    ".groovy": extract_groovy,
    ".gradle": extract_groovy,
    ".c": extract_c,
    ".h": extract_c,
    ".cpp": extract_cpp,
    ".cc": extract_cpp,
    ".cxx": extract_cpp,
    ".hpp": extract_cpp,
    ".cu": extract_cpp,
    ".cuh": extract_cpp,
    ".metal": extract_cpp,
    ".rb": extract_ruby, ".rake": extract_ruby,
    ".cs": extract_csharp,
    ".kt": extract_kotlin,
    ".kts": extract_kotlin,
    ".scala": extract_scala,
    ".php": extract_php,
    ".swift": extract_swift,
    ".lua": extract_lua,
    ".luau": extract_lua,
    ".toc": extract_lua,
    ".zig": extract_zig,
    ".ps1": extract_powershell,
    ".psm1": extract_powershell,
    ".psd1": extract_powershell_manifest,
    ".ex": extract_elixir,
    ".exs": extract_elixir,
    ".m": extract_objc,
    ".mm": extract_objc,
    ".jl": extract_julia,
    ".f": extract_fortran,
    ".F": extract_fortran,
    ".f90": extract_fortran,
    ".F90": extract_fortran,
    ".f95": extract_fortran,
    ".F95": extract_fortran,
    ".f03": extract_fortran,
    ".F03": extract_fortran,
    ".f08": extract_fortran,
    ".F08": extract_fortran,
    ".vue": extract_vue,
    ".svelte": extract_svelte,
    ".astro": extract_astro,
    ".dart": extract_dart,
    ".v": extract_verilog,
    ".sv": extract_verilog,
    ".svh": extract_verilog,
    ".sql": extract_sql,
    ".md": extract_markdown,
    ".mdx": extract_markdown,
    ".qmd": extract_markdown,
    ".skill": extract_markdown,
    ".pas": extract_pascal,
    ".pp": extract_pascal,
    ".dpr": extract_pascal,
    ".dpk": extract_pascal,
    ".lpr": extract_pascal,
    ".inc": extract_pascal,
    ".dfm": extract_delphi_form,
    ".lfm": extract_lazarus_form,
    ".lpk": extract_lazarus_package,
    ".sh": extract_bash,
    ".bash": extract_bash,
    ".json": extract_json,
    ".tf": extract_terraform,
    ".tfvars": extract_terraform,
    ".hcl": extract_terraform,
    ".dm": extract_dm,
    ".dme": extract_dm,
    ".dmi": extract_dmi,
    ".dmm": extract_dmm,
    ".dmf": extract_dmf,
    ".sln": extract_sln,
    ".slnx": extract_slnx,
    ".csproj": extract_csproj,
    ".fsproj": extract_csproj,
    ".vbproj": extract_csproj,
    ".xaml": extract_xaml,
    ".razor": extract_razor,
    ".cshtml": extract_razor,
    ".cls": extract_apex,
    ".trigger": extract_apex,
}


# Extensions whose extractor depends on an optional-dependency extra
# (pyproject [project.optional-dependencies]) and hard-fails without it,
# rather than falling back like Pascal does. Used by the #1745 warning in
# extract() to tell the user which extra restores the language.
_EXTRA_FOR_EXTENSION = {
    ".sql": "sql",
    ".tf": "terraform",
    ".tfvars": "terraform",
    ".hcl": "terraform",
    ".dm": "dm",
    ".dme": "dm",
}


# Extensionless executables (CLI entry points like `devctl` or `manage`) carry
# their language in the shebang, not the suffix. detect.classify_file already
# routes them to the CODE path via _shebang_interpreter; _get_extractor must
# honor the same signal or these files are classified as code and then silently
# dropped by extraction. Only interpreters with a real extractor are mapped —
# detect's wider set (perl, fish, tcsh, Rscript) stays unmapped and skipped.
_SHEBANG_DISPATCH: dict[str, Any] = {
    "python": extract_python,
    "python2": extract_python,
    "python3": extract_python,
    "bash": extract_bash,
    "sh": extract_bash,
    "dash": extract_bash,
    "zsh": extract_bash,
    "ksh": extract_bash,
    "node": extract_js,
    "nodejs": extract_js,
    "ruby": extract_ruby,
    "lua": extract_lua,
    "php": extract_php,
    "julia": extract_julia,
}


# ObjC-only directives. They are illegal in C and C++, so finding one in a `.h`
# file is a near-zero-false-positive signal that the header is Objective-C (and so
# belongs to extract_objc, not extract_c). `@property` is deliberately excluded: it
# doubles as a Doxygen comment command and ObjC properties only ever live inside an
# @interface/@protocol anyway, so the stronger directives already cover them.
#
# `#import` is included because an ObjC *bridging* header is often nothing but
# `#import "X.h"` lines with no @interface (#1556). Routed to extract_c it parses
# `#import` as a `preproc_call` (not `preproc_include`), so every import edge is
# dropped and the header is isolated. `#import` is an ObjC-only directive (illegal
# in C and C++), so this won't hijack genuine C/C++ headers, and extract_objc
# resolves quoted imports via _resolve_c_include_path.
_OBJC_HEADER_MARKERS = (b"@interface", b"@protocol", b"@implementation", b"@import", b"#import")


def _is_objc_header(path: Path) -> bool:
    """Whether a `.h` file is Objective-C rather than C/C++ (#1475).

    `.h` is shared by C, C++, and ObjC; the suffix map routes it to extract_c,
    which silently drops every @interface/@protocol/@property/method (1 node, 0
    edges). Sniffing for an ObjC-only directive reroutes genuine ObjC headers to
    extract_objc while leaving every C/C++ header on its existing extractor.
    """
    try:
        head = path.read_bytes()[:256 * 1024]
    except OSError:
        return False
    return any(marker in head for marker in _OBJC_HEADER_MARKERS)


# C++-only signals. None of these are valid in a plain C header, so finding one
# in a `.h` is a high-confidence signal the header is C++ (#1547). The C grammar
# has no class_specifier, so a `class Foo { ... };` header routed to extract_c
# loses the class and its method prototypes (a junk `foo_foo` node + a sourceless
# `class` stub); routing to extract_cpp recovers the real type. Kept CONSERVATIVE:
# a plain C header with none of these stays on extract_c. ObjC sniffing keeps
# priority (an ObjC header can legitimately contain `::`/`class` inside an inline
# C++ block when compiled as Objective-C++).
_CPP_HEADER_MARKERS = (
    b"class ", b"namespace ", b"template", b"::",
    b"public:", b"private:", b"protected:",
)


def _is_objc_source(path: Path) -> bool:
    """Whether a `.m` file is Objective-C rather than MATLAB/Octave (#1702).

    `.m` is shared by Objective-C implementation files and MATLAB (also Octave).
    The suffix map routes `.m` to extract_objc unconditionally, which force-parses
    MATLAB through the Objective-C tree-sitter grammar and emits garbage nodes/edges
    (worse than skipping). A genuine ObjC `.m` always carries an ObjC directive
    (@implementation/@interface/@import/#import); MATLAB has none of them. Reuses
    the same marker set as the `.h` sniff. `.mm` is unambiguously Objective-C++ and
    is not sniffed.
    """
    return _is_objc_header(path)


def _is_cpp_header(path: Path) -> bool:
    """Whether a `.h` file is C++ rather than plain C (#1547).

    Mirrors `_is_objc_header`: sniffs for a C++-only token. Used only to reroute
    a `.h` from extract_c to extract_cpp when no ObjC marker is present (ObjC has
    priority). Conservative by construction — a plain C header matches nothing
    here and keeps its existing extract_c routing.
    """
    try:
        head = path.read_bytes()[:256 * 1024]
    except OSError:
        return False
    return any(marker in head for marker in _CPP_HEADER_MARKERS)


def _get_extractor(path: Path) -> Any | None:
    """Return the correct extractor function for a file, or None if unsupported."""
    if path.name.lower().endswith(".blade.php"):
        return extract_blade
    # MCP config files (.mcp.json, claude_desktop_config.json, ...) are routed
    # by filename before generic .json dispatch so they get MCP-aware nodes
    # (servers, commands, packages, env vars) instead of opaque JSON keys.
    if is_mcp_config_path(path):
        return extract_mcp_config
    # Package manifests (apm.yml, pyproject.toml, go.mod, pom.xml) → a canonical
    # package node + depends_on edges, by filename before generic suffix dispatch
    # (#1377). apm.yml would otherwise be a .yml document handled by the LLM.
    if is_package_manifest_path(path):
        return extract_package_manifest
    # `.h` is C/C++/ObjC-ambiguous; route Objective-C headers to extract_objc
    # (the suffix map sends `.h` to extract_c, which can't read @interface etc.).
    # ObjC sniffing has priority over the C++ sniff: an Objective-C++ header can
    # contain both `@interface` and inline C++ (`::`), and it must parse as ObjC.
    suffix = path.suffix
    if suffix not in _DISPATCH and suffix.lower() in _DISPATCH:
        suffix = suffix.lower()
    if suffix == ".h":
        if _is_objc_header(path):
            return extract_objc
        # A C++ class header routed to extract_c loses the class entirely (the C
        # grammar has no class_specifier). Reroute to extract_cpp (#1547).
        if _is_cpp_header(path):
            return extract_cpp
    # `.m` is Objective-C OR MATLAB. extract_objc unconditionally would force-parse
    # MATLAB through the ObjC grammar into garbage (#1702). Route to extract_objc
    # only when the file actually looks like Objective-C; otherwise leave it without
    # an extractor (surfaced by the no-AST-extractor warning, #1689) rather than
    # mis-parsed. `.mm` is unambiguously Objective-C++ and stays on extract_objc.
    if suffix == ".m" and not _is_objc_source(path):
        return None
    # Extensionless files: resolve by shebang, mirroring detect.classify_file.
    # Without this, detect labels e.g. `#!/usr/bin/env bash` CLIs as code but
    # extraction returns no extractor and the file silently contributes nothing.
    if not suffix:
        from graphify.detect import _shebang_interpreter
        interp = _shebang_interpreter(path)
        if interp is not None:
            return _SHEBANG_DISPATCH.get(interp)
    return _DISPATCH.get(suffix)


def _safe_extract_with_xaml_root(extractor, path: Path, root: Path) -> dict:
    global _XAML_ACTIVE_EXTRACT_ROOT
    previous_root = _XAML_ACTIVE_EXTRACT_ROOT
    _XAML_ACTIVE_EXTRACT_ROOT = root.resolve()
    try:
        return _safe_extract(extractor, path)
    finally:
        _XAML_ACTIVE_EXTRACT_ROOT = previous_root


def _extract_single_file(args: tuple) -> tuple[int, dict]:
    """Worker function for parallel extraction. Runs in a subprocess.

    Must be at module level (not a closure) so it can be pickled by
    ProcessPoolExecutor.

    Args:
        args: (index, path_str, root_str, cache_location_str) tuple. ``root``
            anchors hash keys / node ids / the XAML boundary; ``cache_location``
            is where the cache dir is written, decoupled per #1774. A legacy
            3-tuple (no cache_location) is still accepted for back-compat.

    Returns:
        (index, result_dict) so results can be placed back in order.
    """
    if len(args) == 4:
        idx, path_str, root_str, cache_location_str = args
    else:  # legacy 3-tuple: location == anchor
        idx, path_str, root_str = args
        cache_location_str = root_str
    path = Path(path_str)
    root = Path(root_str)
    cache_location = Path(cache_location_str)
    _raise_recursion_limit()
    bypass_cache = path.suffix in _JS_CACHE_BYPASS_SUFFIXES

    # Check cache first (avoid re-extraction)
    if not bypass_cache:
        cached = load_cached(path, root, cache_root=cache_location)
        if cached is not None:
            return idx, cached

    extractor = _get_extractor(path)
    if extractor is None:
        return idx, {"nodes": [], "edges": []}

    result = _safe_extract_with_xaml_root(extractor, path, root)
    # Never cache a zero-node result for an extractable file. Every supported
    # source produces at least a file node, so an empty node list is anomalous
    # (e.g. a transient batch/parallel hiccup). Caching it makes the empty
    # byte-stable across runs and silently blinds affected/explain to and
    # through the file (#1666); skipping the write lets a rerun self-heal.
    if not bypass_cache and "error" not in result and result.get("nodes"):
        save_cached(path, result, root, cache_root=cache_location)
    return idx, result


def _extract_parallel(
    uncached_work: list[tuple[int, Path]],
    per_file: list[dict | None],
    root: Path,
    max_workers: int | None,
    total_files: int,
    cache_location: Path | None = None,
) -> bool:
    """Extract uncached files in parallel using ProcessPoolExecutor.

    Returns True if the pool ran to completion. Returns False if the pool
    failed in a recoverable way (typically Windows-spawn without an
    ``if __name__ == "__main__"`` guard in the calling script, which causes
    BrokenProcessPool); the caller should fall back to sequential extraction.
    """
    import concurrent.futures

    if max_workers is None:
        # Honour GRAPHIFY_MAX_WORKERS env override; otherwise scale to the
        # full CPU. The historical `, 8)` cap was a safety bound for laptops
        # in 2023 — on a 32-thread workstation it costs a 4x slowdown
        # (issue #792). Capping at len(uncached_work) keeps small jobs
        # from spawning useless idle workers.
        env_raw = os.environ.get("GRAPHIFY_MAX_WORKERS", "").strip()
        env_cap = None
        if env_raw:
            try:
                v = int(env_raw)
                if v > 0:
                    env_cap = v
            except ValueError:
                pass
        cpu_cap = env_cap if env_cap is not None else (os.cpu_count() or 4)
        max_workers = min(cpu_cap, len(uncached_work))

    # Windows ProcessPoolExecutor hard-caps at 61 workers (CPython limitation
    # tied to WaitForMultipleObjects). Clamp here so every path — auto-compute,
    # GRAPHIFY_MAX_WORKERS, and --max-workers — stays valid on >61-core boxes
    # (issue #1298). Guard against 0 from an empty work list.
    if sys.platform == "win32":
        max_workers = min(max_workers, 61)
    max_workers = max(max_workers, 1)

    # root anchors hash keys / node ids / XAML boundary; cache_location is where
    # the cache dir is written (defaults to root when not decoupled) (#1774).
    root_str = str(root)
    cache_loc_str = str(cache_location if cache_location is not None else root)
    work_items = [(idx, str(path), root_str, cache_loc_str) for idx, path in uncached_work]

    done_count = 0
    _PROGRESS_INTERVAL = 100
    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(_extract_single_file, item): pos
                for pos, item in enumerate(work_items)
            }
            for future in concurrent.futures.as_completed(futures):
                try:
                    idx, result = future.result()
                    per_file[idx] = result
                except Exception as exc:
                    pos = futures[future]
                    print(
                        f"  warning: worker failed for {work_items[pos][1]}: {exc}",
                        file=sys.stderr, flush=True,
                    )
                done_count += 1
                if (
                    total_files >= _PROGRESS_INTERVAL
                    and done_count % _PROGRESS_INTERVAL == 0
                ):
                    print(
                        f"  AST extraction: {done_count}/{len(uncached_work)} uncached files "
                        f"({done_count * 100 // len(uncached_work)}%) [{max_workers} workers]",
                        flush=True,
                    )
    except concurrent.futures.process.BrokenProcessPool:
        # On Windows (spawn start method) the worker subprocesses re-import the
        # caller's __main__. Inline invocations like `python -c "..."` have no
        # __main__ guard, so worker bootstrap raises and the pool dies before
        # any work completes. Fall back to in-process sequential extraction —
        # slower but correct.
        print(
            "  warning: parallel extraction failed (BrokenProcessPool); "
            "falling back to sequential. On Windows this usually means the "
            'caller is missing an `if __name__ == "__main__":` guard. Pass '
            "parallel=False to extract() to skip the pool entirely.",
            flush=True,
        )
        return False
    if total_files >= _PROGRESS_INTERVAL:
        # Report the same denominator the intermediate lines used (uncached files
        # actually processed this run), not total_files — switching to the full
        # corpus made the count jump upward at the end (cached hits + files with no
        # extractor never entered uncached_work), which read as inconsistent (#1693).
        _done = len(uncached_work)
        print(
            f"  AST extraction: {_done}/{_done} uncached files (100%) [{max_workers} workers]",
            flush=True,
        )
    return True


def _extract_sequential(
    uncached_work: list[tuple[int, Path]],
    per_file: list[dict | None],
    root: Path,
    total_files: int,
    cache_location: Path | None = None,
) -> None:
    """Extract uncached files sequentially (fallback for small batches)."""
    _PROGRESS_INTERVAL = 100
    for work_idx, (idx, path) in enumerate(uncached_work):
        if (
            total_files >= _PROGRESS_INTERVAL
            and work_idx % _PROGRESS_INTERVAL == 0
            and work_idx > 0
        ):
            print(
                f"  AST extraction: {work_idx}/{len(uncached_work)} uncached files ({work_idx * 100 // len(uncached_work)}%)",
                flush=True,
            )
        extractor = _get_extractor(path)
        if extractor is None:
            per_file[idx] = {"nodes": [], "edges": []}
            continue
        bypass_cache = path.suffix in _JS_CACHE_BYPASS_SUFFIXES
        # XAML boundary anchors on `root` (the corpus), not the cache location.
        result = _safe_extract_with_xaml_root(extractor, path, root)
        # See _extract_single_file: don't cache an anomalous zero-node result (#1666).
        if not bypass_cache and "error" not in result and result.get("nodes"):
            save_cached(path, result, root, cache_root=cache_location)
        per_file[idx] = result
    if total_files >= _PROGRESS_INTERVAL:
        # Consistent denominator with the intermediate lines (#1693).
        _done = len(uncached_work)
        print(f"  AST extraction: {_done}/{_done} uncached files (100%)", flush=True)


_PARALLEL_THRESHOLD = 20


def extract(
    paths: list[Path],
    cache_root: Path | None = None,
    *,
    parallel: bool = True,
    max_workers: int | None = None,
) -> dict:
    """Extract AST nodes and edges from a list of code files.

    Two-pass process:
    1. Per-file structural extraction (classes, functions, imports)
    2. Cross-file import resolution: turns file-level imports into
       class-level INFERRED edges (DigestAuth --uses--> Response)

    Args:
        paths: files to extract from
        cache_root: explicit root for graphify-out/cache/ (overrides the
            inferred common path prefix). Pass Path('.') when running on a
            subdirectory so the cache stays at ./graphify-out/cache/.
        parallel: if True and there are >= _PARALLEL_THRESHOLD uncached files,
            use ProcessPoolExecutor for multi-core extraction.
        max_workers: max subprocess count. Defaults to cpu_count (or the
            value of GRAPHIFY_MAX_WORKERS if set), bounded by len(uncached_work).
    """
    paths = [Path(p) for p in paths]
    _check_tree_sitter_version()
    _raise_recursion_limit()
    # Workspace package manifests/globs can change during watch or repeated extraction.
    _WORKSPACE_PACKAGE_CACHE.clear()
    _XAML_CSHARP_CLASS_CACHE.clear()

    # Infer a common root for cache keys (use first diverging segment, not sum of all matches)
    try:
        if not paths:
            root = Path(".")
        elif len(paths) == 1:
            root = paths[0].parent
        else:
            min_parts = min(len(p.parts) for p in paths)
            common_len = 0
            for i in range(min_parts):
                if len({p.parts[i] for p in paths}) == 1:
                    common_len += 1
                else:
                    break
            root = Path(*paths[0].parts[:common_len]) if common_len else Path(".")
    except Exception:
        root = Path(".")
    if cache_root is not None:
        root = cache_root
    root = root.resolve()

    # #1774: the cache is an OUTPUT, so when no explicit cache_root is given it is
    # written under the current working directory — never `root` (the inferred
    # common parent of the inputs), which would drop graphify-out/ inside a
    # read-only or foreign corpus. `root` still anchors the content-hash keys,
    # node ids, symbol resolution, and the XAML project-scan boundary; only the
    # cache directory's location diverges from it.
    cache_location = (cache_root if cache_root is not None else Path(".")).resolve()
    total = len(paths)

    # Phase 1: separate cached hits from uncached work
    per_file: list[dict | None] = [None] * total
    uncached_work: list[tuple[int, Path]] = []

    for i, path in enumerate(paths):
        if _get_extractor(path) is None:
            per_file[i] = {"nodes": [], "edges": []}
            continue
        bypass_cache = path.suffix in _JS_CACHE_BYPASS_SUFFIXES
        if not bypass_cache:
            cached = load_cached(path, root, cache_root=cache_location)
            if cached is not None:
                per_file[i] = cached
                continue
        uncached_work.append((i, path))

    # Phase 2: extract uncached files (parallel or sequential)
    if uncached_work:
        ran_parallel = False
        if parallel and len(uncached_work) >= _PARALLEL_THRESHOLD:
            ran_parallel = _extract_parallel(
                uncached_work, per_file, root, max_workers, total, cache_location
            )
        if not ran_parallel:
            _extract_sequential(uncached_work, per_file, root, total, cache_location)

    # Fill any remaining None slots (shouldn't happen, but defensive)
    for i in range(total):
        if per_file[i] is None:
            per_file[i] = {"nodes": [], "edges": []}

    # #1666: surface any source file an extractor accepted but that produced zero
    # nodes (not even a file node). Such a file is silently absent from the graph,
    # so affected/explain are blind to and through it with no other signal.
    _empty_sources: list[str] = []
    for i, _p in enumerate(paths):
        _res = per_file[i] or {}
        if _res.get("nodes") or _res.get("error"):
            continue
        if _get_extractor(_p) is not None:
            _empty_sources.append(str(_p))
    if _empty_sources:
        _shown = ", ".join(Path(x).name for x in _empty_sources[:5])
        _more = f" (+{len(_empty_sources) - 5} more)" if len(_empty_sources) > 5 else ""
        print(
            f"  warning: {len(_empty_sources)} source file(s) produced zero nodes and "
            f"are absent from the graph: {_shown}{_more}. A re-run will retry them "
            f"(empties are no longer cached); if it persists, please report the "
            f"file(s) (#1666).",
            file=sys.stderr, flush=True,
        )

    # #1689: a file counted as code (extension in CODE_EXTENSIONS) but with no AST
    # extractor wired up (e.g. .r/.R — there is no tree-sitter-r dispatch) silently
    # contributes zero nodes. The #1666 warning above deliberately skips these (it
    # only fires when an extractor exists), so surface them explicitly, grouped by
    # extension, rather than reporting success as if the language were mapped.
    from graphify.detect import CODE_EXTENSIONS as _CODE_EXTS
    _no_extractor: dict[str, int] = {}
    for _p in paths:
        _ext = _p.suffix.lower()
        if _ext in _CODE_EXTS and _get_extractor(_p) is None:
            _no_extractor[_ext] = _no_extractor.get(_ext, 0) + 1
    if _no_extractor:
        _by_count = ", ".join(
            f"{ext} ({n})" for ext, n in sorted(_no_extractor.items(), key=lambda kv: (-kv[1], kv[0]))
        )
        _tot = sum(_no_extractor.values())
        print(
            f"  warning: {_tot} file(s) are classified as code but graphify has no AST "
            f"extractor for their language, so they contributed nothing to the graph: "
            f"{_by_count}. Please open an issue to request support for these (#1689).",
            file=sys.stderr, flush=True,
        )

    # #1745: an extractor IS wired up for these files but bailed out because its
    # dependency is missing (e.g. .sql needs tree-sitter-sql from the [sql]
    # extra). Neither warning above fires — #1666 skips results that carry an
    # error, #1689 only covers files with no extractor — so the graph builds
    # "successfully" while every such file silently contributes nothing.
    # Surface them grouped by extension, naming the extra that provides the
    # dependency when there is one.
    _missing_dep_count: dict[str, int] = {}
    _missing_dep_error: dict[str, str] = {}
    for i, _p in enumerate(paths):
        _err = (per_file[i] or {}).get("error") or ""
        if "not installed" in _err:
            _ext = _p.suffix.lower()
            _missing_dep_count[_ext] = _missing_dep_count.get(_ext, 0) + 1
            _missing_dep_error.setdefault(_ext, _err)
    for _ext, _n in sorted(_missing_dep_count.items(), key=lambda kv: (-kv[1], kv[0])):
        _extra = _EXTRA_FOR_EXTENSION.get(_ext)
        if _extra:
            _reason = _missing_dep_error[_ext].split(". ")[0]
            _hint = f' Install it with: pip install "graphifyy[{_extra}]"'
        else:
            _reason = _missing_dep_error[_ext]
            _hint = ""
        print(
            f"  warning: {_n} {_ext} file(s) contributed nothing to the graph "
            f"because a dependency is missing: {_reason}.{_hint} (#1745)",
            file=sys.stderr, flush=True,
        )

    all_nodes: list[dict] = []
    all_edges: list[dict] = []
    all_raw_calls: list[dict] = []
    for result in per_file:
        all_nodes.extend(result.get("nodes", []))
        all_edges.extend(result.get("edges", []))
        all_raw_calls.extend(result.get("raw_calls", []))
    # Function / method / class def ids for the cross-file indirect_call callable
    # guard. Built from the `_callable` node marker AFTER the id-remap / disambiguation
    # passes below (which rewrite node ids), so it can never go stale — see the
    # marker set in the per-file extractor. Populated just before the pass that uses it.
    callable_nids: set[str] = set()

    _augment_symbol_resolution_edges(paths, all_nodes, all_edges, root)

    # Merge a header-declared class (and its methods) with its sibling-impl
    # definition into ONE node (C/C++/ObjC #1547/#1556). Runs BEFORE the id-remap
    # below: a header symbol and its impl counterpart share an id only while both
    # still carry the raw file-stem prefix; the per-file prefix remap then diverges
    # them (foo_h vs foo_cpp), so the collapse must happen first. Collapsing here
    # also means disambiguation sees one source_file per id and won't split them.
    _merge_decl_def_classes(all_nodes, all_edges)

    # Remap file node IDs from absolute-path-derived to the canonical
    # {parent_dir}_{stem} spec form so (a) graph.json edge endpoints are stable
    # across machines (#502) and (b) AST file nodes match the IDs semantic
    # subagents generate (#1033). Resolve before relativizing so paths passed in
    # relative form still anchor to the (resolved) root.
    id_remap: dict[str, str] = {}
    # Symbol node IDs embed the file stem as a prefix (_file_node_id of the path
    # the extractor saw). For a root-level file that stem picks up the absolute
    # parent directory name, so a symbol becomes <rootdir>_main_run while the
    # file node is correctly relativized to main and the skill.md spec wants
    # main_run -- splitting the symbol into AST/semantic ghosts (#1096). Relativize
    # the symbol prefix the same way, gated by source_file so two files sharing a
    # prefix can't cross-contaminate. Keyed by resolved path -> (old_pref, new_pref).
    # Each file maps from up to TWO old prefixes — the input-form prefix
    # _file_node_id(path) and the absolute-resolved-form prefix
    # _file_node_id(path.resolve()). Alias/workspace imports resolve specifiers
    # through .resolve(), so their edge targets are keyed off the ABSOLUTE form;
    # when inputs are relative the two forms differ and absolute-derived targets
    # would otherwise orphan (#1529). Stored as a list so the symbol-prefix remap
    # below can try both (identical forms collapse to one — a no-op).
    prefix_remap: dict[Path, list[tuple[str, str]]] = {}
    for path in paths:
        old_id = _make_id(str(path))
        try:
            rel = path.relative_to(root)
        except ValueError:
            try:
                rel = path.resolve().relative_to(root)
            except ValueError:
                continue
        new_id = _file_node_id(rel)
        if old_id != new_id:
            id_remap[old_id] = new_id
        # Also register the absolute-resolved form of the file-level id so
        # alias/workspace import targets (resolved via .resolve()) remap to
        # canonical instead of orphaning (#1529).
        old_id_abs = _make_id(str(path.resolve()))
        if old_id_abs != new_id:
            id_remap[old_id_abs] = new_id
        old_prefs: list[tuple[str, str]] = []
        old_pref = _file_node_id(path)
        if old_pref != new_id:
            old_prefs.append((old_pref, new_id))
        old_pref_abs = _file_node_id(path.resolve())
        if old_pref_abs != new_id and old_pref_abs != old_pref:
            old_prefs.append((old_pref_abs, new_id))
        if old_prefs:
            prefix_remap[path.resolve()] = old_prefs
    if id_remap:
        for n in all_nodes:
            if n.get("id") in id_remap:
                n["id"] = id_remap[n["id"]]
        for e in all_edges:
            if e.get("source") in id_remap:
                e["source"] = id_remap[e["source"]]
            if e.get("target") in id_remap:
                e["target"] = id_remap[e["target"]]
    if prefix_remap:
        sym_remap: dict[str, str] = {}
        for n in all_nodes:
            sf = n.get("source_file")
            if not sf:
                continue
            # Package nodes carry a canonical name-keyed id (pkg_<name>) that must
            # stay identical across every manifest that references the package, so
            # they are exempt from the file-stem prefix remap (#1377), like the
            # type=module anchors (#1327).
            if n.get("type") == "package":
                continue
            try:
                entry = prefix_remap.get(Path(sf).resolve())
            except Exception:
                continue
            if entry is None:
                continue
            nid = n.get("id", "")
            # Try both the input-form and absolute-form prefixes for this file
            # (#1529). source_file gating above already prevents cross-file
            # contamination, so the first matching prefix wins.
            for old_pref, new_pref in entry:
                if nid.startswith(old_pref + "_"):
                    new_nid = new_pref + nid[len(old_pref):]
                    if new_nid != nid:
                        sym_remap[nid] = new_nid
                    break
        if sym_remap:
            for n in all_nodes:
                if n.get("id") in sym_remap:
                    n["id"] = sym_remap[n["id"]]
            for e in all_edges:
                if e.get("source") in sym_remap:
                    e["source"] = sym_remap[e["source"]]
                if e.get("target") in sym_remap:
                    e["target"] = sym_remap[e["target"]]
            # raw_calls carry caller_nid (a symbol id) consumed by the cross-file
            # call pass below, after this remap — rewrite it too or those edges
            # would dangle on their (stale) source.
            for rc in all_raw_calls:
                cn = rc.get("caller_nid")
                if cn in sym_remap:
                    rc["caller_nid"] = sym_remap[cn]

    _merge_swift_extensions(per_file, all_nodes, all_edges)
    _disambiguate_colliding_node_ids(all_nodes, all_edges, all_raw_calls, root)
    _canonicalize_csharp_namespace_nodes(all_nodes, all_edges)
    _rewire_unique_stub_nodes(all_nodes, all_edges)

    # Add cross-file class-level edges (Python only - uses Python parser internally)
    py_paths = [p for p in paths if p.suffix == ".py"]
    if py_paths:
        py_results = [r for r, p in zip(per_file, paths) if p.suffix == ".py"]
        try:
            cross_file_edges = _resolve_cross_file_imports(py_results, py_paths)
            all_edges.extend(cross_file_edges)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Cross-file import resolution failed, skipping: %s", exc)

    # Cross-file Java import resolution
    java_paths = [p for p in paths if p.suffix == ".java"]
    if java_paths:
        java_results = [r for r, p in zip(per_file, paths) if p.suffix == ".java"]
        try:
            all_edges.extend(_resolve_cross_file_java_imports(java_results, java_paths))
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Java cross-file import resolution failed, skipping: %s", exc)
        # Re-point dangling implements/inherits edges that bare-name resolution
        # left on shadow stubs, using imports for exact-package disambiguation (#1318).
        try:
            _resolve_java_type_references(java_results, java_paths, all_nodes, all_edges)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Java type-reference resolution failed, skipping: %s", exc)

    # Cross-file C# type-reference resolution: re-point dangling inherits/implements/
    # references edges left on shadow stubs, disambiguating same-named types by the
    # referencing file's `using` directives + enclosing namespace (mirrors Java #1318).
    cs_paths = [p for p in paths if p.suffix == ".cs"]
    if cs_paths:
        cs_results = [r for r, p in zip(per_file, paths) if p.suffix == ".cs"]
        try:
            _resolve_csharp_type_references(cs_results, cs_paths, all_nodes, all_edges)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("C# type-reference resolution failed, skipping: %s", exc)
        try:
            _resolve_cross_file_csharp_imports(cs_results, cs_paths, all_nodes, all_edges)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("C# cross-file import resolution failed, skipping: %s", exc)

    # Cross-file call resolution for all languages
    # Each extractor saved unresolved calls in raw_calls. Now that we have all
    # nodes from all files, resolve any callee that exists in another file.
    # Build name → ALL matching node IDs so we can skip ambiguous common names
    # (e.g. "log", "execute", "find") that appear in multiple files — resolving
    # those inflates god_nodes ranking with spurious cross-file edges.
    # Build label -> node_id index for cross-file call resolution.
    # Skip rationale nodes (their labels are docstring text, not callable
    # identifiers, and they were polluting matches for short names — #563).
    global_label_to_nids: dict[str, list[str]] = {}      # exact-case (all languages)
    global_label_to_nids_ci: dict[str, list[str]] = {}   # case-INSENSITIVE-language nodes
    for n in all_nodes:
        if n.get("file_type") == "rationale" or n.get("type") == "namespace":
            continue
        raw = n.get("label", "")
        normalised = raw.strip("()").lstrip(".")
        if normalised:
            # Case is semantic in most languages, so index (and match, below) by exact
            # case — folding collapses `Path` (class) into `PATH` (env var) and makes a
            # single shell variable the #1 god-node (#1581). Only case-insensitive
            # languages (PHP/SQL/Nim) also get a folded key for legitimate fold-matching.
            global_label_to_nids.setdefault(normalised, []).append(n["id"])
            if _lang_is_case_insensitive(n.get("source_file")):
                global_label_to_nids_ci.setdefault(normalised.lower(), []).append(n["id"])

    # Callable-def ids for the indirect_call callable guard, read from the `_callable`
    # marker on the FINAL (post-remap) nodes — so a callback resolves only to a real
    # function/method/class, never a same-named data symbol, and the guard never goes
    # stale when node ids were relativized/disambiguated above (#1566).
    callable_nids = {n["id"] for n in all_nodes if n.get("_callable")}

    # Build evidence index from import edges so cross-file calls backed by an
    # explicit import statement can be promoted from INFERRED to EXTRACTED.
    # Direct symbol imports (`import { foo }` / `const { foo } = require()`) are
    # the strongest evidence — caller's file_id has an `imports` edge directly to
    # the callee's symbol id. Module imports (`imports_from`) are weaker but still
    # confirm the caller pulled in the callee's source file.
    file_to_symbol_imports: dict[str, set[str]] = {}
    file_to_module_imports: dict[str, set[str]] = {}
    for e in all_edges:
        if e.get("relation") == "imports":
            file_to_symbol_imports.setdefault(e["source"], set()).add(e["target"])
        elif e.get("relation") == "imports_from":
            file_to_module_imports.setdefault(e["source"], set()).add(e["target"])

    # Map each node back to its containing file node id so we can ask
    # "did the caller's file import the callee's file?"
    # A node and its file node share the exact same ``source_file`` string, and a
    # file node is the one whose label is the basename (``add_node(file_nid,
    # path.name)``). Resolving file membership by that shared string is robust
    # against the path-resolution/symlink mismatch that makes
    # ``relative_to(root.resolve())`` throw and fall back to a non-matching
    # absolute-derived id — which would spuriously fail import evidence and (with
    # the #1659 JS/TS gate below) drop a legitimately-imported call.
    sf_to_file_nid: dict[str, str] = {}
    for n in all_nodes:
        sf = n.get("source_file")
        if sf and n.get("label") == Path(str(sf)).name:
            sf_to_file_nid.setdefault(str(sf), n["id"])
    nid_to_file_nid: dict[str, str] = {}
    # nid -> raw source_file string, for the ambiguous-name tie-breakers below
    # (test/non-test classification + path proximity). Kept separate from the
    # file-node-id map because tie-breaking compares the actual file paths.
    nid_to_source_file: dict[str, str] = {}
    for n in all_nodes:
        sf = n.get("source_file")
        if not sf:
            continue
        nid_to_source_file[n["id"]] = str(sf)
        fnid = sf_to_file_nid.get(str(sf))
        if fnid is not None:
            nid_to_file_nid[n["id"]] = fnid
            continue
        # Fallback (no file node found for this source_file): derive it the old
        # way from the relativized path.
        sf_path = Path(sf)
        try:
            sf_rel = sf_path.relative_to(root) if sf_path.is_absolute() else sf_path
        except ValueError:
            sf_rel = sf_path
        nid_to_file_nid[n["id"]] = _file_node_id(sf_rel)

    existing_pairs = {(e["source"], e["target"]) for e in all_edges}
    # Call-like pairs only, for the indirect_call dedup: an `imports` edge from a
    # file to the symbol it imports is EXPECTED and must not suppress an
    # indirect_call to that same symbol (JS/TS named imports create such an edge).
    call_like_pairs = {
        (e["source"], e["target"]) for e in all_edges
        if e.get("relation") in ("calls", "indirect_call")
    }
    # JS/TS/JSX modules have no implicit cross-module scope: a call into another
    # file is real ONLY if the caller imported it. So a cross-file call from one
    # of these files with no import evidence is gated below (#1659).
    _JS_TS_CALL_SUFFIXES = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")
    for rc in all_raw_calls:
        callee = rc.get("callee", "")
        if not callee:
            continue
        if callee in _LANGUAGE_BUILTIN_GLOBALS:
            continue
        # Skip member-call callees: obj.log() → "log" has no import evidence
        # and collides with any top-level function named "log" in the corpus.
        if rc.get("is_member_call"):
            continue
        # Skip Ruby include/extend/prepend mixin markers: they carry a module
        # name as `callee` but are not calls — the Ruby resolver turns them into
        # `mixes_in` edges. Letting the shared pass emit a `calls` edge here would
        # both mislabel the relation and block the mixes_in emit as a dup (#1668).
        if rc.get("is_mixin"):
            continue
        # Exact-case match first (case is semantic). Fold only when the CALLING
        # file's language is case-insensitive, and only against the folded index of
        # case-insensitive-language definitions — so a Python `Path()` call can never
        # resolve to a shell `PATH` node (#1581).
        candidates = global_label_to_nids.get(callee, [])
        if not candidates and _lang_is_case_insensitive(rc.get("source_file")):
            candidates = global_label_to_nids_ci.get(callee.lower(), [])
        if not candidates:
            continue
        # Cross-language guard: never bind a call to a definition in a different
        # language family. Name-only matching was resolving a TSX callback passed
        # by name to a same-named Kotlin method in the Android half of the repo
        # (and a Python call to a Kotlin fun) — phantom edges the extraction spec
        # explicitly forbids. Candidates whose family is unknown (no source_file,
        # non-code nodes) are kept, preserving the previous permissive behavior;
        # real interop pairs (Kotlin↔Java, C↔C++↔ObjC, JS↔TS) share a family and
        # still resolve.
        caller_family = _lang_family(rc.get("source_file"))
        if caller_family is not None:
            candidates = [
                c for c in candidates
                if (candidate_family := _lang_family(nid_to_source_file.get(c))) is None
                or candidate_family == caller_family
            ]
            if not candidates:
                continue
        caller = rc["caller_nid"]
        # Resolve the caller's file via the raw_call's own source_file string,
        # which is stable regardless of any caller_nid remap. An indirect
        # callback's caller_nid is the file node, whose id may have been
        # relativized after the raw_call was recorded, so a caller_nid lookup can
        # miss and (with the #1659 gate) drop a legitimately-imported callback.
        caller_file_nid = (
            sf_to_file_nid.get(str(rc.get("source_file", "")))
            or nid_to_file_nid.get(caller)
        )
        imported_symbols = file_to_symbol_imports.get(caller_file_nid, set())
        imported_modules = file_to_module_imports.get(caller_file_nid, set())

        def _has_import_evidence(candidate_id: str) -> bool:
            # Direct symbol import (`import { foo }`) is the strongest evidence:
            # the caller's file has an `imports` edge straight to this symbol.
            # A module import (`import './helper.js'`) confirms the caller pulled
            # in the file the candidate lives in.
            candidate_file_nid = nid_to_file_nid.get(candidate_id)
            return (
                candidate_id in imported_symbols
                or (candidate_file_nid is not None and candidate_file_nid in imported_modules)
            )

        if len(candidates) == 1:
            tgt = candidates[0]
            has_import_evidence = _has_import_evidence(tgt)
        else:
            # Ambiguous name (defined in 2+ files). Don't bail outright (#1219):
            # if the caller has explicit import evidence pointing at exactly one
            # of the candidates, that named import disambiguates unambiguously.
            # Prefer direct symbol-import matches; fall back to module-import
            # matches only when they too collapse to a single target. Without a
            # unique evidence-backed pick we skip, preserving the #543 guard
            # against over-connecting common short names (log, execute, find).
            symbol_matches = [c for c in candidates if c in imported_symbols]
            if len(symbol_matches) == 1:
                tgt = symbol_matches[0]
                has_import_evidence = True
            else:
                module_matches = [
                    c for c in candidates
                    if (cf := nid_to_file_nid.get(c)) is not None and cf in imported_modules
                ]
                if len(module_matches) == 1:
                    tgt = module_matches[0]
                    has_import_evidence = True
                else:
                    # No unique import evidence. Instead of dropping the edge
                    # outright (which let a single same-named test mock erase the
                    # real call graph, #1553), apply the shared god-node
                    # tie-breakers (non-test preference, then path proximity).
                    # Resolve only if exactly one candidate survives; otherwise
                    # the #543/#1219 guard still holds and we skip.
                    tgt = disambiguate_ambiguous_candidates(
                        candidates,
                        {c: nid_to_source_file.get(c, "") for c in candidates},
                        rc.get("source_file", ""),
                    )
                    if tgt is None:
                        continue
                    has_import_evidence = False
        if rc.get("indirect"):
            # Cross-file indirect dispatch: a callback passed BY NAME
            # (`from .h import fn; pool.submit(fn)`, or listed in a dispatch
            # table). Resolved through the same single-definition / import-evidence
            # candidate logic as a direct call, but emitted as a distinct INFERRED
            # `indirect_call` and ONLY when the target is a real callable def —
            # never a same-named data symbol. Stays INFERRED even with import
            # evidence: the name is referenced as a value here, not invoked. Dedup
            # is call-aware (an existing direct `calls` edge pre-empts it; a benign
            # `imports` edge to the same symbol does NOT suppress it).
            if tgt != caller and (caller, tgt) not in call_like_pairs and tgt in callable_nids:
                call_like_pairs.add((caller, tgt))
                all_edges.append({
                    "source": caller,
                    "target": tgt,
                    "relation": "indirect_call",
                    "context": rc.get("context", "argument"),
                    "confidence": "INFERRED",
                    "confidence_score": 0.8,
                    "source_file": rc.get("source_file", ""),
                    "source_location": rc.get("source_location"),
                    "weight": 1.0,
                })
            continue
        # #1659: a JS/TS DIRECT call with no import evidence is almost always an
        # unrelated same-named export in a package that was never imported — a
        # phantom cross-package edge (a 14-package monorepo had `platform` and
        # `sidecar` shown as depending on `registry-protocol` purely because it
        # exported generically-named symbols). JS/TS modules have no implicit
        # cross-module scope, so leave it unresolved rather than binding by name
        # alone. Other languages keep the #1553 single-candidate resolution:
        # C/C++ headers, Ruby autoload, and same-package implicit scope
        # legitimately call across files without an explicit import. Scoped to
        # direct calls: the indirect_call path above is already conservative
        # (INFERRED, callable-target-gated) and independent of import evidence.
        if not has_import_evidence and str(rc.get("source_file", "")).endswith(_JS_TS_CALL_SUFFIXES):
            continue
        if tgt != caller and (caller, tgt) not in existing_pairs:
            existing_pairs.add((caller, tgt))
            # Promote to EXTRACTED when there's a direct import edge from the
            # caller's file pointing at either the callee symbol itself or the
            # file the callee lives in.
            if has_import_evidence:
                confidence = "EXTRACTED"
                confidence_score = 1.0
            else:
                confidence = "INFERRED"
                confidence_score = 0.8
            all_edges.append({
                "source": caller,
                "target": tgt,
                "relation": "calls",
                "context": "call",
                "confidence": confidence,
                "confidence_score": confidence_score,
                "source_file": rc.get("source_file", ""),
                "source_location": rc.get("source_location"),
                "weight": 1.0,
            })

    # Cross-file, language-specific member-call resolution. Runs after the shared
    # call pass so node ids/caller_nids are final; each pass is additive (only the
    # receiver-typed/qualified calls the shared pass skipped) with its own
    # single-definition god-node guard. Registered in graphify.resolver_registry so
    # a new language plugs in without editing this body (#1356 Swift, #1446 Python).
    run_language_resolvers(paths, per_file, all_nodes, all_edges)

    # Relativize source_file fields so paths are portable across machines (#555).
    # A target OUTSIDE the scan root (an out-of-root ProjectReference/.sln/bash
    # `source`) can't be made relative to root; leaving it absolute leaked the
    # scan path including the OS username into a committed graph.json (#1899).
    # Fall back to a walk-up relative form, or the bare basename when that would
    # still embed foreign path segments (a far-away or cross-drive target). When
    # the node's id was itself minted from the absolute path, remap it to a
    # portable id and rewrite the edge endpoints that reference it.
    def _portable_out_of_root_sf(p: Path) -> str:
        try:
            rel = os.path.relpath(str(p), str(root)).replace("\\", "/")
        except ValueError:
            return p.name  # different Windows drive: no relative path exists
        updepth = 0
        for seg in rel.split("/"):
            if seg == "..":
                updepth += 1
            else:
                break
        # More than a couple of walk-ups means the target lives well outside the
        # corpus; its ancestor dirs would embed foreign (possibly user-named)
        # segments, so collapse to the basename.
        return p.name if updepth > 3 else rel

    ext_id_remap: dict[str, str] = {}
    for item in all_nodes + all_edges:
        sf = item.get("source_file")
        if not sf:
            continue
        sf_path = Path(sf)
        if not sf_path.is_absolute():
            continue
        try:
            item["source_file"] = sf_path.relative_to(root).as_posix()
            continue
        except ValueError:
            pass
        portable = _portable_out_of_root_sf(sf_path)
        # A node whose id was minted from this absolute path also leaks it.
        if "id" in item and item.get("id") == _make_id(str(sf_path)):
            ext_id_remap[item["id"]] = _make_id("ext", portable)
        item["source_file"] = portable

    if ext_id_remap:
        for n in all_nodes:
            if n.get("id") in ext_id_remap:
                n["id"] = ext_id_remap[n["id"]]
        for e in all_edges:
            if e.get("source") in ext_id_remap:
                e["source"] = ext_id_remap[e["source"]]
            if e.get("target") in ext_id_remap:
                e["target"] = ext_id_remap[e["target"]]

    # origin_file is an internal disambiguation hint (#1462): the colliding-id pass
    # above reads it to keep same-named cross-file stubs distinct, after which nothing
    # consumes it. Drop it from the returned nodes so it never ships into graph.json as
    # an absolute, machine-specific path — the same "no absolute paths in output"
    # contract that relativizes source_file just above (#555, #932). The per-file AST
    # cache keeps its own copy, which is what the colliding-id pass reads on a cache hit.
    for n in all_nodes:
        n.pop("origin_file", None)
        n.pop("_callable", None)  # internal indirect_call marker — never ships to graph.json

    # Tag AST provenance so the incremental watch rebuild can distinguish
    # AST-extracted nodes from semantic/LLM nodes. On a full re-extraction
    # the watcher drops any AST-marked node missing from the fresh output
    # even when its source file still exists (#1116). Edges carry the same
    # marker so edge eviction can be tier-scoped: re-extracting a source
    # replaces its AST edges without evicting the semantic edges the AST
    # pass cannot regenerate (#1865).
    for n in all_nodes:
        n["_origin"] = "ast"
    for e in all_edges:
        e["_origin"] = "ast"

    return {
        "nodes": all_nodes,
        "edges": all_edges,
        "input_tokens": 0,
        "output_tokens": 0,
    }


def collect_files(target: Path, *, follow_symlinks: bool = False, root: Path | None = None) -> list[Path]:
    containment_root = root if root is not None else target
    from graphify.detect import _resolves_under_root
    if target.is_file():
        return [target] if _resolves_under_root(target, containment_root) else []
    _EXTENSIONS = set(_DISPATCH.keys())
    from graphify.detect import _is_ignored, _is_noise_dir, _load_graphifyignore
    ignore_root = root if root is not None else target
    patterns = _load_graphifyignore(ignore_root)
    # Shared across all _is_ignored calls in this scan so ancestor-directory
    # results are memoised instead of re-evaluated per file.
    ignore_cache: dict[Path, bool] = {}

    def _ignored(p: Path) -> bool:
        return bool(patterns and _is_ignored(p, ignore_root, patterns, _cache=ignore_cache))

    if not follow_symlinks:
        # The old rglob filter rejected paths with a noise component anywhere,
        # including components of target itself — preserve that.
        if any(_is_noise_dir(part) for part in target.parts):
            return []
        # When negation (!) patterns exist, skip directory-level ignore pruning
        # so negated files inside ignored dirs can still be reached (same
        # conservatism as detect's scan walk).
        has_negation = any(pat.startswith("!") for _, pat in patterns)
        results: list[Path] = []
        for dirpath, dirnames, filenames in os.walk(target):
            dp = Path(dirpath)
            dirnames[:] = [
                d for d in dirnames
                if not _is_noise_dir(d)
                and (has_negation or not _ignored(dp / d))
            ]
            for fname in filenames:
                p = dp / fname
                suffix = p.suffix
                if (suffix in _EXTENSIONS or suffix.lower() in _EXTENSIONS) and not _ignored(p) and _resolves_under_root(p, containment_root):
                    results.append(p)
        return sorted(results)
    # Walk with symlink following + cycle detection
    results = []
    for dirpath, dirnames, filenames in os.walk(target, followlinks=True):
        if os.path.islink(dirpath):
            real = os.path.realpath(dirpath)
            parent_real = os.path.realpath(os.path.dirname(dirpath))
            if parent_real == real or parent_real.startswith(real + os.sep):
                dirnames.clear()
                continue
        dp = Path(dirpath)
        dirnames[:] = [
            d for d in dirnames
            if not _is_noise_dir(d)
            and (not (dp / d).is_symlink() or _resolves_under_root(dp / d, containment_root))
        ]
        for fname in filenames:
            p = dp / fname
            suffix = p.suffix
            if (suffix in _EXTENSIONS or suffix.lower() in _EXTENSIONS) and not _ignored(p) and _resolves_under_root(p, containment_root):
                results.append(p)
    return sorted(results)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m graphify.extract <file_or_dir> ...", file=sys.stderr)
        sys.exit(1)

    paths: list[Path] = []
    for arg in sys.argv[1:]:
        paths.extend(collect_files(Path(arg)))

    result = extract(paths)
    print(json.dumps(result, indent=2))
