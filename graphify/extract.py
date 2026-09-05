"""Deterministic structural extraction from source code using tree-sitter. Outputs nodes+edges dicts."""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import sys
import textwrap
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path, PurePath
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
from .csharp_dispatch import resolve_csharp_interface_dispatch
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
    CsharpNameResolver,
    _resolve_cross_file_csharp_imports,
    _resolve_csharp_type_references,
)
from graphify.extractors.dart import extract_dart  # noqa: F401
from graphify.extractors.dm import extract_dm, extract_dmf, extract_dmi, extract_dmm  # noqa: F401
from graphify.extractors.elixir import extract_elixir  # noqa: F401
from graphify.extractors.fortran import _cpp_preprocess, extract_fortran  # noqa: F401
from graphify.extractors.go import _GO_PREDECLARED_FUNCS, extract_go  # noqa: F401
from graphify.extractors.json_config import extract_json  # noqa: F401
from graphify.extractors.commonlisp import extract_commonlisp  # noqa: F401
from graphify.extractors.markdown import extract_markdown, _MD_LINK_INDEX_CACHE  # noqa: F401
from graphify.extractors.ocaml import extract_ocaml  # noqa: F401
from graphify.extractors.pascal_forms import extract_delphi_form, extract_lazarus_form  # noqa: F401
from graphify.extractors.powershell import extract_powershell, extract_powershell_manifest  # noqa: F401
from graphify.extractors.razor import extract_razor  # noqa: F401
from graphify.extractors.robot import extract_robot  # noqa: F401
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
    _TSCONFIG_BASEURL_CACHE,
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
    _go_import_path_for_file,
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
    _load_tsconfig_base_url,
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
    _resolve_go_type_references,
    _resolve_java_type_references,
    _resolve_php_type_references,
    _resolve_js_import_path,
    _resolve_js_import_target,
    _resolve_js_module_path,
    _resolve_lua_import_target,
    _probe_python_module_candidate,
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

from graphify.symbol_resolution import resolve_bash_source_edges  # noqa: E402

from graphify.extractors.engine import REFERENCE_CONTEXTS, _CSHARP_TYPE_PARAMETER_SCOPE_DECLARATIONS, _C_PRIMITIVE_TYPE_NODES, _JAVA_BUILTIN_TYPES, _JAVA_TYPE_PARAMETER_SCOPE_DECLARATIONS, _JS_FUNCTION_VALUE_TYPES, _JS_SCOPE_BOUNDARY, _PYTHON_ANNOTATION_NOISE, _PYTHON_TYPE_CONTAINERS, _RUBY_CLASS_FACTORIES, _c_collect_type_refs, _cpp_collect_type_refs, _cpp_declarator_name, _cpp_local_var_types, _csharp_attribute_names, _csharp_classify_base, _csharp_collect_type_refs, _csharp_extra_walk, _csharp_namespace_id, _csharp_namespace_name, _csharp_pre_scan_interfaces, _csharp_type_parameters_in_scope, _dynamic_import_js, _extract_generic, _find_body, _find_require_call, _get_cpp_func_name, _java_annotation_names, _java_collect_type_refs, _java_extra_walk, _java_type_parameters_in_scope, _js_collect_pattern_idents, _js_dispatch_value_idents, _js_extra_walk, _js_local_bound_names, _js_member_assignment_target, _js_module_bound_names, _kotlin_collect_type_refs, _kotlin_function_return_type_node, _kotlin_property_type_node, _kotlin_user_type_name, _php_collect_type_refs, _php_method_return_type_node, _php_name_text, _python_collect_assignment_targets, _python_collect_param_refs, _python_collect_type_refs, _python_local_bound_names, _python_module_bound_names, _python_param_names, _read_csharp_type_name, _require_imports_js, _ruby_const_last_name, _ruby_extra_walk, _ruby_local_class_bindings, _ruby_new_class_name, _scala_collect_type_refs, _semantic_reference_edge, _source_location, _swift_classify_base, _swift_collect_type_refs, _swift_constructor_type, _swift_declaration_keyword, _swift_extra_walk, _swift_local_var_types, _swift_pre_scan, _swift_property_name, _swift_property_type_node, _swift_receiver_name, _swift_user_type_name, _ts_decorator_name, _ts_descendant_decorators, _ts_emit_decorator_edges, _ts_extra_walk, _ts_method_name, _ts_receiver_type_table  # noqa: E402,F401

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


def _repoint_python_package_imports(paths, all_nodes, all_edges, root) -> None:
    """Repoint Python absolute-import edges to the real file node under a nested
    (e.g. ``src/``) package root (#2072).

    Absolute imports target an id derived from the dotted module path
    (``_make_id('pkg.mod')`` -> ``pkg_mod``), but file-node ids are
    scan-root-relative (``src_pkg_mod`` when the code lives under ``src/``), so
    the edge dangles and is silently dropped — the graph loses most ``imports``
    edges purely because of where the scan started. Build an alias map from the
    dotted-module id to the real file-node id by detecting each ``.py`` file's
    package root (the contiguous run of ancestor dirs carrying ``__init__.py``)
    and rewrite matching ``imports``/``imports_from`` edge targets. Guards: never
    shadow an existing node id, and drop an alias claimed by more than one file
    (ambiguous -> leave dangling, as before). Files whose package root IS the
    scan root are skipped (ids already coincide)."""
    try:
        root = Path(root).resolve()
    except OSError:
        root = Path(root)
    node_ids = {n.get("id") for n in all_nodes if isinstance(n, dict)}
    alias_to_files: dict[str, set[str]] = {}
    for p in paths:
        if p.suffix.lower() not in (".py", ".pyi"):
            continue
        try:
            rel = Path(p).resolve().relative_to(root)
        except (ValueError, OSError):
            continue
        parts = rel.parts
        if len(parts) < 2:
            continue  # top-level file: scan-root-relative id already matches
        d = Path(p).resolve().parent
        levels = 0
        # Bounded by the number of dirs between the file and the scan root, so a
        # pathological `/__init__.py` chain can't loop forever.
        while levels < len(parts) - 1 and (d / "__init__.py").is_file():
            levels += 1
            d = d.parent
        if levels == 0:
            continue  # not inside a package (namespace pkg / loose module)
        mod_parts = parts[-(levels + 1):]  # package dirs + the file itself
        if len(mod_parts) == len(parts):
            continue  # package root == scan root: file-node id already coincides
        file_node = _file_node_id(rel)
        alias = _make_id(str(Path(*mod_parts).with_suffix("")))
        alias_to_files.setdefault(alias, set()).add(file_node)
        if p.name in ("__init__.py", "__init__.pyi") and len(mod_parts) > 1:
            # `import pkg` / `from pkg import x` targets the package-dir id.
            pkg_alias = _make_id(str(Path(*mod_parts[:-1])))
            alias_to_files.setdefault(pkg_alias, set()).add(file_node)
    alias_map = {
        a: next(iter(fs))
        for a, fs in alias_to_files.items()
        if len(fs) == 1 and a not in node_ids
    }
    if not alias_map:
        return
    for e in all_edges:
        # Only repoint edges emitted from a Python file: a non-Python import edge
        # (e.g. C# `using Pkg.Mod;`, Java/Go dotted imports) can have a dangling
        # target string that coincides with a Python alias, and repointing it
        # would fabricate a cross-language import edge (#2072 review).
        if (
            isinstance(e, dict)
            and e.get("relation") in ("imports", "imports_from")
            and str(e.get("source_file", "")).lower().endswith((".py", ".pyi"))
        ):
            tgt = e.get("target")
            if tgt in alias_map:
                e["target"] = alias_map[tgt]


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
                raw_module, _, raw_alias = raw.partition(" as ")
                module_name = raw_module.strip().lstrip(".")
                tgt_nid = _make_id(module_name)
                edge = {
                    "source": file_nid,
                    "target": tgt_nid,
                    "relation": "imports",
                    "context": "import",
                    "confidence": "EXTRACTED",
                    "source_file": str_path,
                    "source_location": f"L{node.start_point[0] + 1}",
                    "weight": 1.0,
                }
                if raw_alias:
                    # `import pkg.mod as alias` binds the local name `alias`, not
                    # `mod`'s own stem, to the module -- stash it so the cross-file
                    # member-call resolver can match `alias.func()` against this
                    # edge instead of dropping it (#2082).
                    edge["local_alias"] = raw_alias.strip()
                edges.append(edge)
    elif t == "import_from_statement":
        module_node = node.child_by_field_name("module_name")
        if module_node:
            raw = _read_text(module_node, source)
            target_path: "Path | None" = None
            if raw.startswith("."):
                # Relative import - resolve to full path so IDs match file node IDs
                dots = len(raw) - len(raw.lstrip("."))
                module_name = raw.lstrip(".")
                base = Path(str_path).parent
                for _ in range(dots - 1):
                    base = base.parent
                # A relative import can name a subpackage (a directory with an
                # __init__.py), not a module file. Probing the candidate on disk
                # (mirroring the companion `imports` edge's
                # _resolve_python_module_path) resolves `graphs` -> graphs/__init__.py
                # instead of a nonexistent graphs.py: without it the target keeps an
                # absolute-path-derived slug that the target_file stamp below can't
                # heal, so it dangles per-checkout (#2455).
                candidate = base / module_name.replace(".", "/") if module_name else base
                resolved = _probe_python_module_candidate(candidate)
                if resolved is not None:
                    target_path = resolved
                else:
                    rel = (module_name.replace(".", "/") + ".py") if module_name else "__init__.py"
                    target_path = base / rel
                tgt_nid = _make_id(str(target_path))
            else:
                tgt_nid = _make_id(raw)
            edge = {
                "source": file_nid,
                "target": tgt_nid,
                "relation": "imports_from",
                "context": "import",
                "confidence": "EXTRACTED",
                "source_file": str_path,
                "source_location": f"L{node.start_point[0] + 1}",
                "weight": 1.0,
            }
            # Stamp the resolved target file (mirroring _import_js, #1814) so
            # the #2169 remap pass can canonicalize this edge's target on an
            # incremental run where the target file itself is not in the
            # batch — without it the target keeps an absolute-path-derived id
            # that matches no node in the merged graph and dangles (#2213).
            # Existence-gated: a speculative import of a nonexistent sibling
            # must stay dangling, exactly as before. The stamp is transient
            # and popped before graph.json ships.
            if target_path is not None:
                try:
                    if target_path.is_file():
                        edge["target_file"] = str(target_path)
                except OSError:
                    pass
            edges.append(edge)


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

    # `import type {...} from` / `export type {...} from` are erased by the
    # TypeScript compiler: no runtime emit, no module-graph edge. The
    # dependency is still real for "what references this type", so the edge is
    # stamped `type_only` rather than dropped, and Import Cycles excludes it
    # the way it already excludes deferred `import(...)` (#1241) - on the
    # reporter's corpus all 3 reported cycles closed only through these
    # (#3123). The grammar keeps `import type from './x'` (a default binding
    # NAMED type) distinct: there `type` sits inside the import_clause, not as
    # a bare keyword child of the statement. A mixed `import { type B, C }`
    # stays a runtime edge - C is a runtime import.
    is_type_only = any(
        child.type == "type" and not child.is_named for child in node.children
    )
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
            # `_resolve_js_import_path` returns the attempted path when no
            # local file exists. Static ES imports must treat that as unresolved
            # rather than minting a checkout-specific target ID (#2457).
            if resolved_path is not None and not resolved_path.is_file():
                tgt_nid = _make_id("ref", raw)
                resolved_path = None
            edge = {
                "source": file_nid,
                "target": tgt_nid,
                "relation": "imports_from",
                "context": "re-export" if is_reexport else "import",
                "confidence": "EXTRACTED",
                "source_file": str_path,
                "source_location": f"L{node.start_point[0] + 1}",
                "weight": 1.0,
            }
            # Stamp the resolved target file so a same-basename cross-extension
            # sibling (foo.ts importing/re-exporting ./foo.mjs) keys its target salt
            # by the TARGET's file rather than the importer's. Both files collapse to
            # the base id `foo`; without this the salted lookup mis-points the target
            # back onto the importer's own variant, a phantom self-loop (#1814).
            if resolved_path is not None:
                edge["target_file"] = str(resolved_path)
            if is_type_only:
                edge["type_only"] = True
            edges.append(edge)

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
                                    **({"type_only": True} if is_type_only else {}),
                                    "source": file_nid,
                                    "target": _make_id(target_stem, sym),
                                    "relation": "re_exports",
                                    "context": "re-export",
                                    "confidence": "EXTRACTED",
                                    "source_file": str_path,
                                    "source_location": f"L{line}",
                                    "weight": 1.0,
                                    # Which file this symbol target was synthesized
                                    # from, so the id-remap post-pass can repoint a
                                    # target the candidates rewrite never learns —
                                    # a barrel defines no symbols (#1983). Transient,
                                    # stripped at build like the #1814 stamp.
                                    "target_file": str(resolved_path),
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
                                            # See the re_exports stamp above (#1983).
                                            "target_file": str(resolved_path),
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
                        # Stamp the resolved target, mirroring _import_python (#1814):
                        # without it, an include whose header lives outside this
                        # batch's paths keeps the raw absolute-path id no later pass
                        # ever learns to relativize (#2243).
                        "target_file": str(resolved),
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
    # Grammar 1.1.0 (PyPI tree_sitter_kotlin) emits an `import` node whose
    # children are the `import` keyword and a `qualified_identifier` (the dotted
    # path), optionally followed by `.` `*` (wildcard) or `as` + `identifier`
    # (alias). There is no `path` field. Older forks emit `import_header` with a
    # `path` field or a bare `identifier` child; keep those branches so the
    # extractor works across grammar generations (#2526, adapted from PR #2531
    # by @Mustaqeem66).
    path_node = node.child_by_field_name("path")
    if path_node is None:
        path_node = next(
            (c for c in node.children if c.type == "qualified_identifier"), None
        )
    if path_node is not None:
        raw = _read_text(path_node, source).strip()
    else:
        raw = next(
            (_read_text(c, source).strip() for c in node.children
             if c.type == "identifier"),
            "",
        )
    if not raw:
        return
    # Wildcard (`import a.b.*`): imports a whole package, not a symbol. The last
    # path segment is a PACKAGE name, so a symbol-level edge would dangle on (or
    # collide with) an unrelated node that happens to share the package's name.
    if raw.endswith(".*") or raw == "*" or any(c.type == "*" for c in node.children):
        return
    # Alias (`import a.b.C as D`): the alias is the identifier child after `as`.
    alias = None
    saw_as = False
    for child in node.children:
        if not saw_as:
            saw_as = child.type == "as"
        elif child.type in ("identifier", "simple_identifier"):
            alias = _read_text(child, source).strip() or None
            break
    module_name = raw.split(".")[-1].strip()
    if not module_name:
        return
    # Target is the bare last segment for now; _resolve_kotlin_import_targets
    # rewrites it to the real node id via the target_fqn stamped here, once the
    # per-file package index exists. Unresolved targets stay dangling like other
    # languages' external imports.
    edges.append({
        "source": file_nid,
        "target": _make_id(module_name),
        "relation": "imports",
        "context": "import",
        "confidence": "EXTRACTED",
        "source_file": str_path,
        "source_location": f"L{node.start_point[0] + 1}",
        "weight": 1.0,
        "metadata": sanitize_metadata({k: v for k, v in
            {"target_fqn": raw, "alias": alias}.items() if v is not None}),
    })


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
    # `function_expression` belongs here so UNTRACKED inline/nested expressions
    # reach walk_calls' existing closure handler, which already names the type
    # (`_JS_CLOSURE_TYPES`). Without it the gate never opens, so such an
    # expression's parameters and locals never fold into extra_locals for its
    # subtree and read as by-name references (#2241 family). A top-level
    # `const f = function (…) {}` is tracked via its declarator and was already
    # fine; the inline/nested forms are what this covers.
    function_boundary_types=frozenset({"function_declaration", "generator_function_declaration", "arrow_function", "method_definition", "function_expression", "generator_function"}),
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
    # `function_expression`: see the note on the JS config above.
    function_boundary_types=frozenset({"function_declaration", "generator_function_declaration", "arrow_function", "method_definition", "function_expression", "generator_function"}),
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

def _ruby_sanitize_method_name(name: str) -> str:
    """Encode trailing Ruby method suffixes (!, ?, =) into safe node ID components (#3077)."""
    if not name:
        return name
    if name.endswith("!"):
        return f"{name[:-1]}_bang"
    if name.endswith("?"):
        return f"{name[:-1]}_pred"
    if name.endswith("="):
        return f"{name[:-1]}_eq"
    return name


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
    sanitize_symbol_name_fn=_ruby_sanitize_method_name,
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
    # `object_creation_expression` joins the invocation node so `new Foo(...)`
    # links the constructing method to Foo, the way Java has since #1373.
    call_types=frozenset({"invocation_expression", "object_creation_expression"}),
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
    # Grammar 1.1.0 (PyPI tree_sitter_kotlin) names the import node `import`;
    # older forks use `import_header`. Accept both (#2526).
    import_types=frozenset({"import_header", "import"}),
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
    # traits are class-like containers with their own heritage (extends / with),
    # so they need a node and the heritage walk just like classes and objects.
    class_types=frozenset({"class_definition", "object_definition", "trait_definition"}),
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
    # interfaces/enums/traits are class-like containers whose heritage
    # (extends/implements) and members must be captured, same as classes.
    class_types=frozenset({
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
        "trait_declaration",
    }),
    function_types=frozenset({"function_definition", "method_declaration"}),
    import_types=frozenset({"namespace_use_clause"}),
    # object_creation_expression joins the dispatch set so `new Foo(...)` links
    # the constructing method to Foo (engine has a dedicated PHP branch: the
    # class sits in a bare name/qualified_name child, not a field) - the PHP
    # twin of Java #1373 / C# #2997 (#3115).
    call_types=frozenset({"function_call_expression", "member_call_expression", "scoped_call_expression", "class_constant_access_expression", "object_creation_expression"}),
    static_prop_types=frozenset({"scoped_property_access_expression"}),
    helper_fn_names=frozenset({"config"}),
    container_bind_methods=frozenset({"bind", "singleton", "scoped", "instance"}),
    event_listener_properties=frozenset({"listen", "subscribe"}),
    call_function_field="function",
    call_accessor_node_types=frozenset({"member_call_expression"}),
    call_accessor_field="name",
    name_fallback_child_types=("name",),
    # enums wrap their members in an enum_declaration_list rather than a
    # declaration_list, so the body walk needs it to reach enum methods/cases.
    body_fallback_child_types=("declaration_list", "compound_statement", "enum_declaration_list"),
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


def _shorten_rationale_label(text: str, width: int = 80) -> str:
    """Collapse whitespace and truncate ``text`` to ``width`` chars for a
    rationale node label, cutting on a word boundary rather than mid-word.
    Shared by the Python and JS/TS rationale extractors (#2206).

    ``textwrap.shorten`` collapses to just the placeholder when the first
    "word" alone exceeds ``width`` (e.g. a docstring/comment that opens with
    an unbroken URL) -- that would emit a content-free label, so fall back to
    a plain character truncation of the normalized text in that case.
    """
    label = textwrap.shorten(text, width=width, placeholder="…")
    if label in ("", "…"):
        flat = " ".join(text.split())
        label = flat if len(flat) <= width else flat[: width - 1] + "…"
    return label


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
        """A docstring is the first STATEMENT in a module/class/function body.

        A leading `comment` node — the shebang line essentially every
        executable script starts with, a coding-declaration or license
        header, or any ordinary comment — is not a statement: tree-sitter
        still parses it as a sibling child of the body, but Python's own
        docstring rule skips right over it. The old unconditional `break`
        after the first loop iteration stopped at that comment instead of
        looking past it, so a module docstring behind a shebang (or any
        leading comment) was silently never found (#3312).
        """
        if not body_node:
            return None
        for child in body_node.children:
            if child.type == "comment":
                continue
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
        # Normalize whitespace before truncating, not after: slicing raw text
        # first can land mid-word, leave a run of literal spaces where a
        # newline + indentation used to be, or end on a "." that turns into
        # an Obsidian "..md" filename once export.py appends the extension.
        label = _shorten_rationale_label(text)
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


# ── TypeScript import type normalization (#3154) ──────────────────────────────
# tree-sitter-typescript misparses `import(...)` types used inside explicit call-
# expression type arguments (e.g. `f<typeof import("mod")>()` or
# `f<import("mod").Foo>()`) as binary comparison expressions (`<` and `>`).
# The trailing `();` generates an ERROR node, leaving an open `binary_expression`
# that absorbs subsequent declarations as anonymous `function_expression` or `class`
# expressions, silently dropping them from extraction. Normalizing `import(...)`
# within generic call type arguments `<...>(...)` to a valid type identifier of
# identical byte length keeps AST parsing clean while preserving source offsets.

_TS_IMPORT_CALL_RE = re.compile(
    rb"\bimport\s*\(\s*['\"][^'\"\r\n]+['\"]\s*\)"
)


def _ts_import_is_code(root: Any, start: int) -> bool:
    """Return whether an import-call match starts in executable source.

    Regex matching is only used to locate a literal specifier; comments,
    strings, regular expressions, and template text must never be fed into the
    structural masking pass.  A template substitution is executable again, so
    it is the one exception to the ``template_string`` guard.
    """
    node = root.descendant_for_byte_range(start, start + 1)
    if node is None:
        # A malformed tree can leave a byte range uncovered. Treat it as code
        # and let the structural pass decide whether it belongs to a type list;
        # never turn an uncertain lexical result into a crash.
        return True
    in_template_substitution = False
    while node is not None:
        if node.type == "comment" or node.type in ("string", "regex", "regex_pattern"):
            return False
        if node.type == "template_substitution":
            in_template_substitution = True
        elif node.type == "template_string" and not in_template_substitution:
            return False
        node = node.parent
    return True


def _ts_type_argument_ranges(root: Any, *, call_only: bool) -> list[tuple[int, int]]:
    """Collect byte ranges tree-sitter already parsed as type arguments."""
    ranges: list[tuple[int, int]] = []
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type == "type_arguments":
            parent = node.parent
            if not call_only or (
                parent is not None and parent.type in ("call_expression", "new_expression")
            ):
                ranges.append((node.start_byte, node.end_byte))
        stack.extend(node.children)
    return ranges


def _ts_error_nodes(root: Any) -> list[Any]:
    """Return parser error nodes without depending on a grammar's error name."""
    errors: list[Any] = []
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type == "ERROR" or node.is_error:
            errors.append(node)
        stack.extend(node.children)
    return errors


def _ts_mask_candidate_is_malformed(
    original_root: Any,
    masked_range: tuple[int, int],
    errors: list[Any],
) -> bool:
    """Tell whether a masked generic is backed by an actual parse failure.

    A valid runtime comparison can have the same token shape as a generic call
    after the import is replaced (``a < import("x") > (a)``).  Tree-sitter
    exposes the opening ``<`` as a binary operator in the original tree for
    both forms, so the structural second pass alone cannot distinguish them.
    Only repair that ambiguity when the original parser has an error adjacent
    to the candidate's closing angle; that is the signature of the known
    ``import(...)``-type grammar failure.  Valid comparisons, including ones
    nested in another call's arguments, remain byte-for-byte untouched.
    """
    start, end = masked_range
    opener = original_root.descendant_for_byte_range(start, start + 1)
    if opener is None or opener.type != "<":
        # A grammar that already gives us a structural type_arguments node is
        # safe to normalize; no binary/comparison ambiguity is present.
        return True
    if opener.parent is None or opener.parent.type != "binary_expression":
        return True

    # A malformed generic's ERROR starts at the closing `>` (or at the call
    # punctuation immediately following it). Keep this window deliberately
    # narrow so an unrelated syntax error elsewhere cannot authorize masking a
    # valid runtime comparison.
    for error in errors:
        if error.start_byte <= end + 2 and error.end_byte >= end - 1:
            return True
    return False


def _normalize_ts_import_types(source: bytes, *, tsx: bool = False) -> bytes | None:
    """Rewrite only syntactic TypeScript ``import(...)`` type arguments.

    The first implementation of #3154 used a ``<...>`` regular expression.
    In semicolon-less code that expression could span two comparison
    operators, so a *runtime* dynamic import was blanked before parsing.  A
    temporary, byte-preserving mask lets tree-sitter identify the actual
    ``type_arguments`` node without asking it to parse the known-invalid
    ``import(...)`` call-site form.  We then rewrite only placeholders inside
    call/new-expression type arguments.  Keeping every replacement the same
    byte length preserves source offsets and line locations.
    """
    raw_matches = list(_TS_IMPORT_CALL_RE.finditer(source))
    if not raw_matches:
        return None

    # tree-sitter is already a required TypeScript dependency for extraction.
    # If it cannot be loaded here, leave the source untouched; the normal AST
    # path will report its own dependency/parser error rather than applying an
    # unsafe textual guess.
    try:
        import tree_sitter_typescript as ts_typescript
        from tree_sitter import Language, Parser

        language_factory = (
            ts_typescript.language_tsx if tsx else ts_typescript.language_typescript
        )
        parser = Parser(Language(language_factory()))
        original_root = parser.parse(source).root_node
    except Exception:
        return None

    matches = [
        match for match in raw_matches
        if _ts_import_is_code(original_root, match.start())
    ]
    if not matches:
        return None

    # If the original tree already has a type_arguments node around a match,
    # its syntax is parseable as written. This includes the grammar's deliberate
    # comparison-vs-generic ambiguity (`a < b, import("...") > (d)`); retaining
    # that source is essential because it is a runtime expression, not a type.
    original_type_ranges = _ts_type_argument_ranges(original_root, call_only=False)
    matches = [
        match for match in matches
        if not any(start <= match.start() < end for start, end in original_type_ranges)
    ]
    if not matches:
        return None

    def placeholder(match: "re.Match[bytes]") -> bytes:
        # Keep CR/LF bytes intact. The first byte becomes an ordinary type
        # identifier and the remaining bytes are padding, so every downstream
        # byte offset remains identical to the user's source.
        matched = match.group(0)
        return b"T" + re.sub(rb"[^\r\n]", b" ", matched[1:])

    masked = bytearray(source)
    for match in matches:
        masked[match.start():match.end()] = placeholder(match)

    root = parser.parse(bytes(masked)).root_node

    # Only call/new-expression type arguments need this workaround. Ordinary
    # type annotations already parse ``import(...)`` correctly and should keep
    # their native AST shape. A range from an outer call's type_arguments also
    # covers nested generic arguments.
    type_argument_ranges = _ts_type_argument_ranges(root, call_only=True)
    errors = _ts_error_nodes(original_root)

    if not type_argument_ranges:
        return None

    norm = bytearray(source)
    changed = False
    for match in matches:
        containing_ranges = [
            candidate for candidate in type_argument_ranges
            if candidate[0] <= match.start() < candidate[1]
        ]
        if containing_ranges and any(
            _ts_mask_candidate_is_malformed(original_root, candidate, errors)
            for candidate in containing_ranges
        ):
            norm[match.start():match.end()] = placeholder(match)
            changed = True
    return bytes(norm) if changed else None


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
    is_ts = suffix in (".ts", ".tsx", ".mts", ".cts")
    if suffix == ".tsx":
        config = _TSX_CONFIG
    elif suffix in (".ts", ".mts", ".cts"):
        config = _TS_CONFIG
    else:
        config = _JS_CONFIG
    source_override = None
    if is_ts:
        try:
            source = path.read_bytes()
            source_override = _normalize_ts_import_types(source, tsx=suffix == ".tsx")
        except OSError:
            pass
    result = _extract_generic(path, config, source_override=source_override)
    if "error" not in result:
        _extract_js_rationale(path, result)
        _rescue_js_dynamic_imports(path, result)
    return result


def _rescue_js_dynamic_imports(path: Path, result: dict) -> None:
    """Recover ``import('…')`` edges the AST pass does not emit for plain JS/TS.

    tree-sitter models ``await import('x')`` as a ``call_expression``, not an
    ``import_statement``, so the specifier only reaches the graph when
    ``walk_calls`` visits that call — which it never does at module scope
    (only function bodies are walked for calls). The Svelte/Astro/Vue
    extractors already patch the same gap by regex because their AST pass
    fails wholesale; plain ``.ts``/``.js`` was left out on the reasoning that
    its AST pass "works". It works for STATIC imports; dynamic ones outside a
    walked body fell through silently (#2575), and because they cluster under
    hub modules the loss compounds with ``affected`` traversal depth.

    Dedupe: a dynamic import the AST pass DID capture is already in the graph
    as an ``imports_from`` edge marked ``deferred`` (``_dynamic_import_js``).
    Re-emitting it here as a second ``dynamic_import`` edge would state the
    same fact twice, so a match whose resolved target already has a deferred
    edge FROM THIS FILE'S NODE is skipped. The source check matters: the AST
    pass anchors the edge on the enclosing function when the ``import()`` is
    written inside one, and that is a different fact from "this file depends on
    that module" — the only one file-level traversal can use (#2584).

    Regex false positives in comments/strings are the precedented trade of
    the Svelte/Vue rescues; a ``//``-prefix guard covers the common case.
    """
    try:
        import re as _re
        src = path.read_text(encoding="utf-8", errors="replace")
        if not _re.search(r"(?<!\w)import\s*\(", src):  # cheap bail — most files have none
            return
        existing_ids = {n["id"] for n in result.get("nodes", [])}
        file_node_id = _make_id(str(path))
        aliases = _load_tsconfig_aliases(path.parent)
        base_url = _load_tsconfig_base_url(path.parent)
        deferred_ids: set[str] = set()
        deferred_files: set[str] = set()
        rescued_targets: set[str] = set()
        for e in result.get("edges", []):
            # Only a FILE-level deferred edge makes the rescue redundant (#2584).
            #
            # `_dynamic_import_js` emits `caller_nid -> target`, and `caller_nid` is this
            # file's node only when the `import()` sits at module scope. Written inside a
            # function it is that function's node — a different fact, at a granularity
            # `affected` does not walk. Matching on target alone treated the two as one and
            # skipped the rescue, so a dynamic import inside a function ended up with no
            # file-level edge at all. The reverse walk then reached the enclosing function
            # and stopped: the only edge pointing at it is `contains`, deliberately kept out
            # of DEFAULT_AFFECTED_RELATIONS.
            #
            # Measured on a ~700-file TS repo: `affected --depth 3` returned 39 of 49 truly
            # affected files (recall 0.80, precision 1.00) and deeper traversal did not help,
            # which is a dead end rather than a depth limit. It stayed hidden because the
            # usual case still resolves — when the next importer imports that exact symbol
            # by name there IS an edge into the function. Switch that importer to
            # `import * as ns` or a side-effect `import './dyn'` and the same graph goes
            # silent.
            if (e.get("deferred") and e.get("relation") == "imports_from"
                    and e.get("source") == file_node_id):
                deferred_ids.add(e.get("target"))
                tf = e.get("target_file")
                if tf:
                    try:
                        deferred_files.add(str(Path(tf).resolve()))
                    except OSError:
                        deferred_files.add(str(tf))
        # `(?<!\w)` so `fooimport('x')` and `_import('x')` do not match. The
        # backtick alternative mirrors _dynamic_import_js's template-string
        # handling: a literal `import(`./x`)` resolves, `${`-substituted ones
        # are excluded (no `$` in the class) as statically unresolvable.
        for m in _re.finditer(
            r"""(?<!\w)import\s*\(\s*(?:'([^'\n]+)'|"([^"\n]+)"|`([^`$\n]+)`)\s*\)""",
            src,
        ):
            raw = m.group(1) or m.group(2) or m.group(3)
            if not raw:
                continue
            line_start = src.rfind("\n", 0, m.start()) + 1
            if "//" in src[line_start:m.start()]:
                continue  # line-commented-out import
            resolution = _resolve_rescued_specifier(path, raw, aliases, base_url)
            if resolution is None:
                continue
            node_id, _stub_sf, resolved_file = resolution
            # AST-captured already: same resolved target id, same resolved
            # on-disk file, or the engine's ref-namespaced external id.
            if node_id in deferred_ids or _make_id("ref", raw) in deferred_ids:
                continue
            if resolved_file is not None:
                try:
                    if str(resolved_file.resolve()) in deferred_files:
                        continue
                except OSError:
                    pass
            # One file depending on one module is one file-level fact, however many
            # call sites defer it. Pre-existing (two module-scope `import('./x')` in one
            # file already emitted two identical edges on v8), but #2584 routes every
            # in-function dynamic import through here too, which would turn an edge case
            # into the common one — a hub module deferred from eight functions of the same
            # file would carry eight identical arrows.
            emit_key = str(resolved_file.resolve()) if resolved_file is not None else raw
            if emit_key in rescued_targets:
                continue
            rescued_targets.add(emit_key)
            _emit_rescued_import(
                result, existing_ids, file_node_id, path, raw,
                "dynamic_import", aliases, base_url,
            )
    except Exception:
        pass


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
        # Normalize whitespace before truncating, not after: slicing raw text
        # first can land mid-word, leave a run of literal spaces where a
        # newline + indentation used to be, or end on a "." that turns into
        # an Obsidian "..md" filename once export.py appends the extension.
        label = _shorten_rationale_label(text)
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


def _resolve_rescued_specifier(
    path: Path,
    raw: str,
    aliases,
    base_url,
) -> "tuple[str, str, Path | None] | None":
    """Resolve a regex-rescued import specifier the way ``_import_js`` does.

    Returns ``(node_id, stub_source_file, resolved_file)`` — ``resolved_file``
    is the target as a real on-disk file, or None when the specifier is
    external or dangling. Returns None when no target can be minted at all
    (empty bare-import segment). Split out of :func:`_emit_rescued_import` so
    :func:`_rescue_js_dynamic_imports` can resolve a match FIRST and skip
    specifiers the AST pass already emitted, without duplicating the
    resolution rules.
    """
    if raw.startswith("."):
        resolved = _resolve_js_module_path(
            Path(os.path.normpath(path.parent / raw))
        )
        resolved_file = resolved if resolved is not None and resolved.is_file() else None
        return _make_id(str(resolved)), str(resolved), resolved_file
    # Check tsconfig.json path aliases (e.g. "$lib/" -> "src/lib/",
    # "@/" -> "src/") before treating as external. Mirrors _import_js
    # logic so alias imports resolve to the same file node IDs the
    # extractor creates (#701).
    resolved_alias = _resolve_tsconfig_alias(raw, aliases, base_url=base_url)
    if resolved_alias is not None:
        resolved_alias = _resolve_js_module_path(resolved_alias)
        resolved_file = (resolved_alias if resolved_alias is not None
                         and resolved_alias.is_file() else None)
        return _make_id(str(resolved_alias)), str(resolved_alias), resolved_file
    # Bare/scoped import (node_modules) - use last segment;
    # build_from_json drops as external if no matching node exists.
    module_name = raw.split("/")[-1]
    if not module_name:
        return None
    return _make_id(module_name), raw, None


def _emit_rescued_import(
    result: dict,
    existing_ids: set,
    file_node_id: str,
    path: Path,
    raw: str,
    relation: str,
    aliases,
    base_url,
) -> None:
    """Shared edge/stub emit for the Svelte/Astro/Vue regex-rescue import passes.

    Resolves the specifier the same way ``_import_js`` does — relative paths and
    tsconfig aliases both go through :func:`_resolve_js_module_path` so
    extensionless specifiers probe real on-disk extensions (``../lib/content``
    -> ``content.ts``) instead of a naive ``.js``->``.ts`` suffix swap.

    When the resolved target is a real file on disk, mirror ``_import_js``:
    emit ONLY the edge, stamped with ``target_file``, and mint no stub node.
    The #2169 canonicalization loop in :func:`extract` reads the stamp and
    repoints the edge at the real file node's canonical id. Minting a stub
    here would carry an absolute-path-derived id when the input path is
    absolute — a ghost node (e.g. ``private_tmp_..._src_lib_content``)
    duplicating the real ``src_lib_content`` node and clobbering its label on
    dedupe (#2195). Stub nodes are still minted for unresolved specifiers
    (externals, not-yet-created files) so prior behavior is preserved.
    """
    resolution = _resolve_rescued_specifier(path, raw, aliases, base_url)
    if resolution is None:
        return
    node_id, stub_source_file, resolved_file = resolution
    edge = {
        "source": file_node_id, "target": node_id,
        "relation": relation, "confidence": "EXTRACTED",
        "source_file": str(path),
    }
    if resolved_file is not None:
        # Real file on disk: edge only (no stub node), stamped so the #2169
        # canonicalization pass repoints it at the real node (#2195).
        edge["target_file"] = str(resolved_file)
        result.setdefault("edges", []).append(edge)
        return
    if node_id in existing_ids:
        # Edge target already a real node - just add the edge, don't add a node.
        result.setdefault("edges", []).append(edge)
        return
    result.setdefault("nodes", []).append({
        "id": node_id, "label": raw,
        "file_type": "code", "source_file": stub_source_file,
        "confidence": "EXTRACTED",
    })
    result.setdefault("edges", []).append(edge)
    existing_ids.add(node_id)


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
        base_url = _load_tsconfig_base_url(path.parent)
        for m in _re.finditer(r"""import\(\s*['"]([^'"]+)['"]\s*\)""", src):
            raw = m.group(1)
            if not raw:
                continue
            # Resolution + emit shared with the static pass below: relative
            # paths and tsconfig aliases probe real on-disk extensions (#716,
            # #701), and a target that IS a real file emits an edge stamped
            # with target_file instead of an absolute-id ghost stub (#2195).
            _emit_rescued_import(
                result, existing_ids, file_node_id, path, raw,
                "dynamic_import", aliases, base_url,
            )
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
                _emit_rescued_import(
                    result, existing_ids, file_node_id, path, raw,
                    "imports_from", aliases, base_url,
                )
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
        base_url = _load_tsconfig_base_url(path.parent)
        # Dynamic imports anywhere in the file: `import('./X.astro')` is legal in
        # frontmatter setup code and inside expression slots.
        for m in _re.finditer(r"""import\(\s*['"]([^'"]+)['"]\s*\)""", src):
            raw = m.group(1)
            if not raw:
                continue
            _emit_rescued_import(
                result, existing_ids, file_node_id, path, raw,
                "dynamic_import", aliases, base_url,
            )
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
                _emit_rescued_import(
                    result, existing_ids, file_node_id, path, raw,
                    "imports_from", aliases, base_url,
                )
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
    masked_bytes = masked.encode("utf-8")
    if config in (_TS_CONFIG, _TSX_CONFIG):
        masked_bytes = _normalize_ts_import_types(
            masked_bytes, tsx=config is _TSX_CONFIG
        ) or masked_bytes

    result = _extract_generic(path, config, source_override=masked_bytes)

    # Dynamic `import('…')` calls aren't edged by the AST pass; recover by regex,
    # mirroring extract_svelte/extract_astro.
    try:
        existing_ids = {n["id"] for n in result.get("nodes", [])}
        file_node_id = _make_id(str(path))
        aliases = _load_tsconfig_aliases(path.parent)
        base_url = _load_tsconfig_base_url(path.parent)
        for m in re.finditer(r"""import\(\s*['"]([^'"]+)['"]\s*\)""", src):
            raw = m.group(1)
            if not raw:
                continue
            _emit_rescued_import(
                result, existing_ids, file_node_id, path, raw,
                "dynamic_import", aliases, base_url,
            )
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


# doctest / Catch2 name each test case with a string literal
# (``TEST_CASE("name")``), which tree-sitter-cpp cannot parse: the construct
# becomes an ERROR node and the whole test function is dropped from the graph
# (issue #2594). Recover the test cases with a regex fallback, mirroring the
# Spock handling of Groovy ``def "feature"()`` above. Scoped to doctest +
# Catch2, which share this string-named-macro surface.
#
# Only the top-level test-declaration macros are recovered as callable nodes.
# ``SUBCASE`` / ``SECTION`` are *nested* scopes inside a test body and
# ``TEST_SUITE`` is a grouping wrapper, not a test function — emitting them as
# file-contained nodes would fabricate wrong-granularity nodes and edges.
_CPP_STRING_TEST_MACROS = (
    "TEST_CASE", "TEST_CASE_TEMPLATE", "SCENARIO",
)
# The name group consumes C-string escapes (``\"``, ``\\``) so a test whose
# name embeds an escaped quote is captured whole, not truncated at the escape.
_CPP_STRING_TEST_RE = re.compile(
    r'^[ \t]*(?:' + "|".join(_CPP_STRING_TEST_MACROS) + r')\s*\(\s*"((?:[^"\\]|\\.)+)"',
    re.MULTILINE,
)


def _augment_cpp_string_tests(path: Path, result: dict) -> dict:
    """Append callable nodes for doctest/Catch2 string-named test cases that
    tree-sitter-cpp drops as ERROR nodes (issue #2594).

    The generic C++ pass still recovers the surrounding functions and include
    edges reliably, so this only adds the missing ``TEST_CASE("...")`` nodes and
    their ``contains`` edge from the file node — it does not rebuild the result.

    Matching is line-anchored raw text, mirroring the Spock fallback above; it is
    deliberately not comment/preprocessor aware (a ``TEST_CASE`` disabled behind
    a block comment or ``#if 0`` may still surface as a node, exactly as a
    commented Spock ``def "feature"()`` would).
    """
    try:
        source = path.read_text(errors="replace")
    except OSError:
        return result
    matches = list(_CPP_STRING_TEST_RE.finditer(source))
    if not matches:
        return result

    str_path = str(path)
    stem = _file_stem(path)
    file_nid = _make_id(str_path)
    # A test name that is all punctuation (TEST_CASE("***")) normalizes to empty,
    # so _make_id(stem, name) collapses onto this bare-stem id — colliding with
    # the file's namespace and silently swallowing every later such test under
    # one id (#1899). Detect that collapse and fall back to a line-positional id.
    stem_collapse_id = _make_id(stem)
    nodes = result.setdefault("nodes", [])
    edges = result.setdefault("edges", [])
    seen_ids = {n.get("id") for n in nodes}

    for m in matches:
        test_name = m.group(1)
        line = source.count("\n", 0, m.start()) + 1
        test_nid = _make_id(stem, test_name)
        if test_nid == stem_collapse_id:
            test_nid = _make_id(stem, "test", f"L{line}")
        if test_nid in seen_ids:
            continue
        seen_ids.add(test_nid)
        # Keep the raw test name as the label (mirroring the Spock fallback,
        # which labels feature methods with their quoted string name).
        nodes.append({
            "id": test_nid,
            "label": f'"{test_name}"',
            "file_type": "code",
            "source_file": str_path,
            "source_location": f"L{line}",
        })
        edges.append({
            "source": file_nid,
            "target": test_nid,
            "relation": "contains",
            "confidence": "EXTRACTED",
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": 1.0,
        })
    return result


# ── C++/CLI normalization (#2876) ────────────────────────────────────────────
# tree-sitter-cpp implements none of `ref class`, `Type^`, `Type%`, `gcnew` or
# `[assembly:…]`. The ERROR lands on the type header, which dissolves the whole
# class body — a 141-method .NET interop wrapper yielded 12 junk symbols. These
# rewrites map each spelling onto the nearest standard C++ one.

# Only files carrying one of these engage the rewrite, so plain C/C++/CUDA is
# parsed byte-for-byte as before. `^`/`%` alone are not markers: they are the
# ordinary XOR and modulo operators.
_CPP_CLI_MARKER_RE = re.compile(
    rb"\b(?:ref|value)\s+(?:class|struct)\b"
    rb"|\binterface\s+class\b"
    rb"|\bgcnew\b"
    rb"|\[\s*(?:assembly|module)\s*:"
)

# `public ref class Foo` / `value struct Bar` / `interface class Baz` → the
# access specifier goes too: it is not legal at namespace scope, and leaving it
# behind is what made recovery invent a stray `public` node.
_CPP_CLI_CLASS_RE = re.compile(
    rb"(?:\b(?:public|private|protected)\s+)?\b(?:ref|value)\s+(?=(?:class|struct)\b)"
    rb"|(?:\b(?:public|private|protected)\s+)?\binterface\s+(?=class\b)"
)
# Handle (`String^ s`) and tracking-reference (`int% n`) suffixes.
#
# `^` and `%` are also XOR and modulo, and `String^ s` is lexically identical to
# `a^ b` — attachment to the preceding token does not separate them, because
# `a% b` and `hash^ mask` are attached too. Rewriting on attachment alone
# corrupted those into `a  b` / `hash  mask`. So the rewrite is restricted to
# the two positions where an operator reading is impossible or implausible.
#
# 1. Followed by a token that cannot begin an operand: `f(String^, int)`,
#    `List<String^>`, `(String^)x`, `Object^;`. `a^,` is not valid C++, so
#    there is no arithmetic to lose here. `*` and `&` are deliberately NOT in
#    the set — `a^*p` and `a^&b` are valid XOR expressions, and `String^*` is
#    rare enough not to be worth trading for them.
_CPP_CLI_SUFFIX_UNAMBIGUOUS_RE = re.compile(rb"(?<=[A-Za-z0-9_>])[\^%](?=\s*[,)\]>;])")
# 2. A type-shaped left side followed by a declarator: `System::String^ s`,
#    `List<int>^ items`, `DataTable^ t`, `int% n`. Qualified names, a closing
#    generic bracket, .NET's PascalCase convention and the primitive value
#    types are all type positions; requiring one keeps lowercase operands like
#    `count% 2` and `hash^ mask` as arithmetic. A capitalized name must also
#    carry a lowercase letter, so SCREAMING_CASE constants stay arithmetic
#    too (`MASK^ value`); a lone capital is exempt for generic parameters
#    (`T^ x`). The type is captured and re-emitted so the substitution stays
#    byte-length preserving.
_CPP_CLI_SUFFIX_DECL_RE = re.compile(
    rb"(\b[A-Za-z_][A-Za-z0-9_]*(?:::[A-Za-z_][A-Za-z0-9_]*)+"   # System::String
    rb"|\b[A-Z][A-Za-z0-9_]*[a-z][A-Za-z0-9_]*"                   # String, DataTable
    rb"|\b[A-Z](?=[\^%])"                                        # T
    rb"|\b(?:bool|char|wchar_t|short|int|long|float|double|unsigned|signed)"
    rb"|>)"                                                      # List<int>^
    rb"[\^%](?=\s+[A-Za-z_])"
)
# `[assembly:AssemblyVersion("1.0")]` and friends.
_CPP_CLI_ATTR_RE = re.compile(rb"\[\s*(?:assembly|module)\s*:[^\[\]]*\]", re.S)


def _blank_keeping_newlines(m: "re.Match[bytes]") -> bytes:
    """Replace a match with spaces, but keep its line breaks.

    Byte length alone is not enough. Both the class-header and the attribute
    pattern can span lines — ``[assembly:AssemblyVersion(\\n  "1.0"\\n)]`` is
    ordinary formatting — and blanking a newline merges two source lines, which
    shifts the reported line number of every symbol below it. Preserving CR and
    LF in place keeps line and column stable as well as offset.
    """
    return re.sub(rb"[^\r\n]", b" ", m.group(0))


def _normalize_cpp_cli(source: bytes) -> bytes | None:
    """Rewrite C++/CLI spellings to standard C++ ones, or None if not C++/CLI.

    The rewrite is **byte-length preserving** — dropped tokens are overwritten
    with spaces, never deleted, and ``gcnew`` becomes ``new`` plus padding — and
    line breaks inside a removed token are kept, so every offset, line and
    column still points at the same place in the file on disk and reported
    source locations stay accurate (#2876).
    """
    if not _CPP_CLI_MARKER_RE.search(source):
        return None
    out = _CPP_CLI_CLASS_RE.sub(_blank_keeping_newlines, source)
    out = re.sub(rb"\bgcnew\b", b"new  ", out)
    out = _CPP_CLI_SUFFIX_UNAMBIGUOUS_RE.sub(b" ", out)
    out = _CPP_CLI_SUFFIX_DECL_RE.sub(rb"\1 ", out)
    return _CPP_CLI_ATTR_RE.sub(_blank_keeping_newlines, out)


def extract_cpp(path: Path) -> dict:
    """Extract functions, classes, and includes from a .cpp/.cc/.cxx/.hpp file.

    C++/CLI sources are normalized to standard C++ first (#2876); see
    :func:`_normalize_cpp_cli`.

    Recovers doctest/Catch2 ``TEST_CASE("name")`` test cases that tree-sitter-cpp
    drops as ERROR nodes (issue #2594), mirroring the Spock fallback for Groovy.
    """
    try:
        source = path.read_bytes()
    except OSError:
        # Let _extract_generic report the read failure in its usual shape.
        return _augment_cpp_string_tests(path, _extract_generic(path, _CPP_CONFIG))
    result = _extract_generic(
        path, _CPP_CONFIG, source_override=_normalize_cpp_cli(source) or source
    )
    return _augment_cpp_string_tests(path, result)


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


# A language's own built-in throwable hierarchy, keyed by the interop family of
# the file that names it. `class FooApiException extends \Exception` in PHP means
# PHP's global `Exception`, so a same-named class defined in a file of ANOTHER
# family cannot be what it refers to (#2812). Scoped to built-in throwables on
# purpose: they are the names every language ships and every corpus subclasses,
# while a name a corpus commonly defines itself would suppress a real supertype
# edge. `_LANGUAGE_BUILTIN_GLOBALS` covers the adjacent call-target case and is
# deliberately separate — a flat set consulted at call sites, neither per-family
# nor consulted by supertype resolution.
_LANGUAGE_BUILTIN_BASE_CLASSES: dict[str, frozenset[str]] = {
    "php": frozenset({
        "Throwable", "Exception", "ErrorException", "Error", "TypeError",
        "ValueError", "ArgumentCountError", "ArithmeticError",
        "DivisionByZeroError", "RuntimeException", "LogicException",
        "InvalidArgumentException", "DomainException", "LengthException",
        "OutOfRangeException", "OutOfBoundsException", "RangeException",
        "OverflowException", "UnderflowException", "UnexpectedValueException",
        "BadFunctionCallException", "BadMethodCallException", "JsonException",
    }),
    "jvm": frozenset({
        "Throwable", "Exception", "RuntimeException", "Error",
        "IllegalArgumentException", "IllegalStateException",
        "UnsupportedOperationException", "IndexOutOfBoundsException",
        "NullPointerException", "IOException",
    }),
    "python": frozenset({
        "BaseException", "Exception", "ValueError", "TypeError", "KeyError",
        "IndexError", "RuntimeError", "NotImplementedError", "AttributeError",
        "OSError", "IOError", "StopIteration", "Warning", "UserWarning",
        "DeprecationWarning",
    }),
    "jsts": frozenset({
        "Error", "TypeError", "RangeError", "SyntaxError", "ReferenceError",
        "EvalError", "URIError", "AggregateError",
    }),
    "dotnet": frozenset({
        "Exception", "ApplicationException", "SystemException",
        "ArgumentException", "ArgumentNullException",
        "ArgumentOutOfRangeException", "InvalidOperationException",
        "NotImplementedException", "NotSupportedException",
    }),
    "ruby": frozenset({
        "Exception", "StandardError", "RuntimeError", "ArgumentError",
        "TypeError", "NameError", "NoMethodError", "IOError",
    }),
}

# Folded companion, for referrers whose language resolves identifiers
# case-insensitively (#1581) — PHP `extends \exception` names the same built-in
# as `extends \Exception`. Mirrors the `real_by_label` / `real_by_label_ci` pair.
_LANGUAGE_BUILTIN_BASE_CLASSES_CI: dict[str, frozenset[str]] = {
    family: frozenset(name.lower() for name in names)
    for family, names in _LANGUAGE_BUILTIN_BASE_CLASSES.items()
}


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

    def _names_own_builtin_base(edge: dict, stub_id: str, remapped_id: str) -> bool:
        r"""#2812: `class FooApiException extends \Exception` names PHP's own global
        built-in, so a same-named class defined in another language cannot be what
        it refers to — yet the bare name was scoped by nothing and the unique
        TypeScript `Exception` absorbed the stub, leaving a PHP class inheriting
        from a TS one.

        Decided per EDGE rather than per stub: one sourceless `Exception` stub
        collects referrers from every language that names it, and the TypeScript
        referrers must still rewire onto the TypeScript class.

        Deliberately narrower than a blanket family gate on the type path: a
        corpus really can declare its own `BookStore` in one language and subclass
        it from another (`test_extract_rewires_unique_inheritance_stub_to_real_definition`).
        """
        if edge.get("relation") not in _SUPERTYPE_RELATIONS:
            return False
        edge_fam = _lang_family(edge.get("source_file"))
        if edge_fam is None:
            return False
        label = str(by_id.get(stub_id, {}).get("label", "")).strip()
        if _lang_is_case_insensitive(edge.get("source_file")):
            builtins = _LANGUAGE_BUILTIN_BASE_CLASSES_CI.get(edge_fam, frozenset())
            label = label.lower()
        else:
            builtins = _LANGUAGE_BUILTIN_BASE_CLASSES.get(edge_fam, frozenset())
        if label not in builtins:
            return False
        target_fam = _lang_family(by_id.get(remapped_id, {}).get("source_file"))
        return target_fam is not None and target_fam != edge_fam
    for edge in edges:
        is_csharp_scoped_edge = (
            str(edge.get("source_file", "")).endswith((".cs", ".razor", ".cshtml"))
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
            ) and not _names_own_builtin_base(edge, str(target), remapped_target):
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


def _remap_objc_field_tables(per_file: list, mapping: dict) -> None:
    """Rewrite objc_field_types["tables"] KEYS through an id remap (#3150).

    The #2591 field->type tables are the one extractor bucket keyed BY class
    node id. The #1529 passes rewrote node ids, edge endpoints,
    raw_calls[].caller_nid and swift_extensions[].nid but not these keys, so
    whenever a common absolute prefix was stripped (always via
    `graphify update <dir>`) the table keys went stale, every
    field_types_by_class.get(cls) missed, and [self.<field> ...] sends
    resolved to nothing - #2591 was inert through the CLI.
    """
    for result in per_file:
        ft = result.get("objc_field_types") if isinstance(result, dict) else None
        tables = ft.get("tables") if isinstance(ft, dict) else None
        if not isinstance(tables, dict):
            continue
        if any(k in mapping for k in tables):
            ft["tables"] = {mapping.get(k, k): v for k, v in tables.items()}


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

    # A genuine Swift type is the target of a `contains` edge from its file node;
    # bare-reference shadow nodes (`let x: Foo`) carry a source_file but are NOT
    # contained, so excluding them keeps a stub from making a real type look
    # ambiguous — same predicate the Swift member-call resolver uses (#2538).
    contained = {e.get("target") for e in all_edges if e.get("relation") == "contains"}

    label_to_canonical: dict[str, list[str]] = {}
    for n in all_nodes:
        if n.get("id") in extension_nids:
            continue
        label = n.get("label")
        if not label:
            continue
        # The merge matches on label alone, so without a language gate
        # `extension Data` / `extension Store` — idiomatic Swift — would absorb a
        # same-named TypeScript or Python class in a polyglot repo and invent
        # cross-language edges. Restrict candidates to Swift's own family, which
        # keeps the intended Swift↔Objective-C folding, and skip builtin globals
        # the way the member-call resolvers do (#1726, #2147).
        if _lang_family(n.get("source_file")) != "native":
            continue
        if label in _LANGUAGE_BUILTIN_GLOBALS:
            continue
        if not (n.get("source_file") and n.get("id") in contained and _is_type_like_definition(n)):
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
    def _key_of(e: dict, src: str, tgt: str) -> tuple:
        return (src, tgt, e.get("relation"), e.get("source_file"), e.get("source_location"))

    rewritten: list[dict] = []
    seen_keys: set[tuple] = set()
    for e in all_edges:
        src0, tgt0 = e.get("source"), e.get("target")
        src = remap.get(src0, src0)
        tgt = remap.get(tgt0, tgt0)
        if src == src0 and tgt == tgt0:
            # Untouched by the merge — keep verbatim. The key below ignores
            # confidence/weight/context, so deduping edges this pass never
            # rewrote prunes legitimate parallel edges emitted elsewhere in the
            # pipeline; one Swift extension in a polyglot repo was enough to
            # silently drop unrelated edges from other languages (#2538).
            seen_keys.add(_key_of(e, src0, tgt0))
            rewritten.append(e)
            continue
        if src == tgt:
            continue
        e["source"] = src
        e["target"] = tgt
        key = _key_of(e, src, tgt)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        rewritten.append(e)
    all_edges[:] = rewritten


def _merge_csharp_partial_class_nodes(
    per_file: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
    paths: list[Path],
    root: Path,
) -> None:
    """Collapse C# `partial class Foo` halves split across files into ONE node
    (#2332), without crossing assembly boundaries (#2411).

    The per-file extractor mints class ids with the file stem, so each file
    declaring `partial class Foo` produces its own `Foo` node: members split
    across the halves and cross-half calls don't resolve (two candidate types
    make every receiver-typed lookup bail as ambiguous). Group partial-stamped
    type nodes by (assembly, namespace, label) — same-named types in different
    namespaces are distinct types, non-partial same-named types are separate
    declarations, and nested partials are excluded (their ids omit the
    enclosing type, so a same-named nested pair under different outers would
    falsely merge). The `partial` keyword only fuses declarations compiled into
    the SAME assembly, so the key also carries the nearest ancestor directory
    holding a `*.csproj`/`*.fsproj`/`*.vbproj` — same-named halves under
    different project dirs are genuinely distinct types and stay apart. Halves
    with NO project file on any ancestor (up to the scan root) all key to ""
    and still merge together, so single-project/snippet corpora behave exactly
    as before; the probe runs only for groups that are otherwise ambiguous.
    The canonical node is the sorted-first half by (source_file,
    source_location, id); every edge endpoint and raw-call caller is remapped
    onto it. Member node ids are left untouched — only the class-level nodes
    collapse.

    Must run BEFORE _disambiguate_colliding_node_ids / _rewire_unique_stub_nodes /
    _resolve_csharp_type_references and the resolver registry, so every later
    pass sees one definition per partial type.
    """
    groups: dict[tuple[str, str], list[dict]] = {}
    for n in all_nodes:
        if not str(n.get("source_file", "")).endswith(".cs"):
            continue
        if n.get("file_type") != "code":
            continue
        md = n.get("metadata") or {}
        if not md.get("is_partial") or md.get("is_nested_type"):
            continue
        label = n.get("label")
        if not label:
            continue
        groups.setdefault((str(md.get("namespace", "")), str(label)), []).append(n)

    if not any(len(members) >= 2 for members in groups.values()):
        return

    # Assembly probe (#2411). A node's `source_file` can be a bare filename at
    # this point (ambiguous across project dirs), so map nid -> scanned path
    # via per_file, which aligns 1:1 with `paths`.
    nid_to_path: dict[str, Path] = {}
    for result, path in zip(per_file, paths):
        for pn in result.get("nodes") or []:
            nid_to_path.setdefault(pn["id"], path)

    proj_exts = (".csproj", ".fsproj", ".vbproj")
    project_dirs: set[Path] = set()
    for p in paths:
        if p.suffix.lower() in proj_exts:
            try:
                project_dirs.add(p.resolve().parent)
            except OSError:
                pass
    try:
        stop = root.resolve()
    except OSError:
        stop = root
    dir_assembly: dict[Path, str] = {}

    def _assembly_of_dir(d: Path) -> str:
        """Nearest ancestor dir (self included) holding a project file, "" if
        none up to the scan root; memoized along the walked chain."""
        chain: list[Path] = []
        key = ""
        while True:
            cached = dir_assembly.get(d)
            if cached is not None:
                key = cached
                break
            chain.append(d)
            if d in project_dirs:
                key = str(d)
                break
            try:
                has_project = any(
                    c.suffix.lower() in proj_exts for c in d.iterdir()
                )
            except OSError:
                has_project = False
            if has_project:
                key = str(d)
                break
            if d == stop or d.parent == d:
                break
            d = d.parent
        for c in chain:
            dir_assembly[c] = key
        return key

    def _assembly_of_node(nid: str) -> str:
        path = nid_to_path.get(nid)
        if path is None:
            return ""
        try:
            d = path.resolve().parent
        except OSError:
            return ""
        return _assembly_of_dir(d)

    remap: dict[str, str] = {}
    for members in groups.values():
        if len(members) < 2:
            continue
        by_assembly: dict[str, list[dict]] = {}
        for n in members:
            by_assembly.setdefault(_assembly_of_node(n["id"]), []).append(n)
        for halves in by_assembly.values():
            if len(halves) < 2:
                continue
            halves.sort(key=lambda n: (
                str(n.get("source_file", "")),
                str(n.get("source_location", "")),
                str(n.get("id", "")),
            ))
            canonical_nid = halves[0]["id"]
            for other in halves[1:]:
                if other["id"] != canonical_nid:
                    remap[other["id"]] = canonical_nid

    if not remap:
        return

    all_nodes[:] = [n for n in all_nodes if n.get("id") not in remap]

    # Each half's file keeps a `contains` edge to the canonical type — multiple
    # files containing one node is the intended shape (same as the Swift
    # extension merge): the type owns the members, the files own their slice.
    # Self-loops are dropped, exact duplicates dedup.
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

    # raw_calls carry caller_nid, consumed by the member-call resolvers and the
    # cross-file call pass after this merge — a top-level raw call whose caller
    # is a merged-away class half must follow it onto the canonical node.
    for result in per_file:
        for rc in result.get("raw_calls", []) or []:
            cn = rc.get("caller_nid")
            if cn in remap:
                rc["caller_nid"] = remap[cn]


UNRESOLVED_CALLS_KEY = "unresolved_calls"
_MAX_PARKED_CALLS_PER_NODE = 64


def _park_unresolved_member_call(
    caller_node: dict | None,
    callee: str,
    receiver_type: str,
    lang: str,
    raw_call: dict,
) -> None:
    """Keep a member call whose receiver type is declared nowhere in this corpus.

    A single-repo build can only bind ``obj.method()`` when the receiver's type is
    declared in the same build, so a call into another repository is dropped with
    the receiver type already in hand and nothing about it reaches ``graph.json``
    — the one artifact ``merge-graphs`` and ``global add`` consume. Parking the
    pair on the caller node lets a merged graph finish the edge (#3152).

    The payload carries names only, never node ids: ids are rewritten by the
    remaps and again by the repo prefixing, and a stale id inside metadata would
    fail silently (#3150 was that bug). Names survive every rewrite.
    """
    if not caller_node or not callee or not receiver_type:
        return
    metadata = caller_node.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        return
    parked = metadata.setdefault(UNRESOLVED_CALLS_KEY, [])
    if not isinstance(parked, list) or len(parked) >= _MAX_PARKED_CALLS_PER_NODE:
        return
    callee, receiver_type = str(callee), str(receiver_type)
    for previous in parked:
        if (
            isinstance(previous, dict)
            and previous.get("callee") == callee
            and previous.get("receiver_type") == receiver_type
        ):
            return
    entry = {"callee": callee, "receiver_type": receiver_type, "lang": lang}
    location = raw_call.get("source_location")
    if location:
        entry["line"] = str(location)
    parked.append(entry)


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

    # #2561: pending factory bindings (`let x = Factory.make()`) are label-only —
    # resolve each against the factory method's marked plain return type
    # (`swift_plain_return` on the return_type references edge) and fold the
    # result into the declaring file's table so the raw-call loop below types
    # `x.method()` through the existing INFERRED path. Every step is
    # exactly-one guarded; any failure leaves the receiver untyped (no edge,
    # never a wrong one). setdefault: an explicit annotation wins.
    factory_by_file: dict[str, dict] = {}
    for result in per_file:
        tt = result.get("swift_type_table")
        if tt and tt.get("path") and tt.get("factory"):
            factory_by_file[tt["path"]] = tt["factory"]
    if factory_by_file:
        # method nid -> marked plain-return target nids (must be exactly one).
        return_targets_by_method: dict[str, set[str]] = {}
        for e in all_edges:
            if (e.get("relation") == "references"
                    and e.get("context") == "return_type"
                    and (e.get("metadata") or {}).get("swift_plain_return")):
                return_targets_by_method.setdefault(
                    e.get("source"), set()).add(e.get("target"))
        for path, pending in factory_by_file.items():
            # Copy before folding: the resolved label is corpus-dependent and
            # must not leak back into the per-file result.
            table = dict(type_table_by_file.get(path, {}))
            type_table_by_file[path] = table
            for receiver, bind in pending.items():
                try:
                    factory_type, factory_method = bind
                except (TypeError, ValueError):
                    continue
                if factory_type in _LANGUAGE_BUILTIN_GLOBALS:
                    continue
                factory_defs = type_def_nids.get(_key(factory_type), [])
                if len(factory_defs) != 1:
                    continue
                method_nid = method_index.get((factory_defs[0], _key(factory_method)))
                if method_nid is None:
                    continue
                targets = return_targets_by_method.get(method_nid, set())
                if len(targets) != 1:
                    continue
                tnode = node_by_id.get(next(iter(targets)))
                ret_label = str(tnode.get("label", "")) if tnode else ""
                if not ret_label or ret_label in _LANGUAGE_BUILTIN_GLOBALS:
                    continue
                if len(type_def_nids.get(_key(ret_label), [])) != 1:
                    continue
                table.setdefault(receiver, ret_label)

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
        # A builtin receiver type (Data, NSLock, DispatchQueue, ...) must not
        # resolve to a same-named user symbol — the cross-file CALL resolver and
        # the TS/Python member-call resolvers already skip these globals (#1726);
        # do the same for Swift (#2147).
        if type_name in _LANGUAGE_BUILTIN_GLOBALS:
            continue
        type_defs = type_def_nids.get(_key(type_name), [])
        if not type_defs:
            # Declared nowhere here — in a multi-repo setup that usually means "in
            # a repo this build does not contain", so park it for the merge
            # (#3152). This resolver shares `all_raw_calls` with every other
            # language and Swift raw_calls carry no `lang` tag, so the parked
            # entry's language comes from the declaring file's suffix.
            if str(rc.get("source_file", "")).lower().endswith(".swift"):
                _park_unresolved_member_call(
                    node_by_id.get(caller), callee, type_name, "swift", rc,
                )
            continue
        if len(type_defs) != 1:  # ambiguous -> bail (god-node guard)
            continue
        type_nid = type_defs[0]
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
    # Local alias bound by `as` on a specific import edge (#2082): `from pkg import
    # mod as alias` / `import pkg.mod as alias` bind `alias`, not `mod`'s own stem,
    # to the module in the importing file. Keyed by (importing file, target module)
    # so two files aliasing the same module differently each match their own.
    import_alias_by_filenode: dict[str, dict[str, str]] = {}
    for e in all_edges:
        if e.get("relation") in ("imports", "imports_from"):
            imported_by_filenode.setdefault(e.get("source"), set()).add(e.get("target"))
            alias = e.get("local_alias")
            if alias:
                import_alias_by_filenode.setdefault(e.get("source"), {})[e.get("target")] = _key(alias)

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
            # never match), then to the single callable that module contains. A
            # receiver also matches the local alias bound on that import edge
            # (#2082), so an aliased import resolves the same as the bare name.
            rkey = _key(receiver)
            caller_file = file_of_node.get(caller)
            file_aliases = import_alias_by_filenode.get(caller_file, {})
            mods = [t for t in imported_by_filenode.get(caller_file, ())
                    if t in contains_children
                    and (_module_stem_key(t) == rkey or file_aliases.get(t) == rkey)]
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
    owning a method with the callee name, and emits a ``calls`` edge — EXTRACTED
    when the receiver names the type in source (``Type.method()``), INFERRED when
    the type came from the table (the Swift/C#/Java tiering).

    Origin gate (#2553): a name-only match is not evidence the caller can even
    see the matched type. ``import type { Repo } from 'external-pkg'`` plus
    ``this.repo.save()`` must not fabricate an edge to an unrelated local
    ``class Repo`` in another file. The matched type must be origin-verified:
    defined in the caller's own file, a named import of the caller's file, or
    contained in a module the caller's file imports. Otherwise EMIT NOTHING —
    a false call edge is worse than a missing one (the C++ resolver's bar).
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

    # Origin maps (#2553), built like the Python resolver's module arm: key on
    # stable NODE ids, not source_file strings (raw_calls keep their original
    # pre-relativization paths, so a string join would miss under an explicit
    # cache_root). ``contains`` maps a node to its file node; a member call's
    # caller is usually a METHOD node, which hangs off its class via a ``method``
    # edge instead, so fold those through to the owning class's file.
    file_of_node: dict[str, str] = {}
    for e in all_edges:
        if e.get("relation") == "contains":
            file_of_node[e.get("target")] = e.get("source")
    for e in all_edges:
        if e.get("relation") == "method":
            owner_file = file_of_node.get(e.get("source"))
            if owner_file is not None:
                file_of_node.setdefault(e.get("target"), owner_file)
    # ``imports`` targets are the imported symbol nodes; ``imports_from`` targets
    # are module file nodes. A symbol id never collides with a file id, so one
    # set serves both origin checks below.
    imported_by_filenode: dict[str, set[str]] = {}
    for e in all_edges:
        if e.get("relation") in ("imports", "imports_from"):
            imported_by_filenode.setdefault(e.get("source"), set()).add(e.get("target"))

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
            type_qualified = True  # the receiver names the type in source
        else:
            type_qualified = False
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
        # Origin gate (#2553): the caller's file must actually see the matched
        # type — same file, a named import of the type, or a module import of
        # the type's file. Otherwise a third-party type name that happens to
        # collide with a local class fabricates an edge; emit nothing.
        caller_file = file_of_node.get(caller)
        type_file = file_of_node.get(type_nid)
        imported = imported_by_filenode.get(caller_file, set())
        if not (
            (caller_file is not None and caller_file == type_file)
            or type_nid in imported
            or (type_file is not None and type_file in imported)
        ):
            continue
        method_nid = method_index.get((type_nid, _key(callee)))
        if not method_nid:
            # Receiver typed, but the type has no such method. The old fallback
            # (a `references` edge to the type node) was another fabrication
            # vector; skip instead, matching the C# resolver.
            continue
        if method_nid == caller or (caller, method_nid) in existing_pairs:
            continue
        existing_pairs.add((caller, method_nid))
        # `Type.method()` names the receiver type explicitly in source —
        # EXTRACTED; a receiver typed via the constructor-injection/local table
        # is inference — INFERRED (the Swift/C#/Java ternary).
        all_edges.append({
            "source": caller,
            "target": method_nid,
            "relation": "calls",
            "context": "call",
            "confidence": "EXTRACTED" if type_qualified else "INFERRED",
            "confidence_score": 1.0 if type_qualified else 0.8,
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
            if not type_defs:
                # Declared nowhere here, which in a multi-repo setup usually means
                # "in a repo this build does not contain" (#3152). `Foo::bar()` is
                # also the shape of a namespace-qualified free function, so the
                # merge side's guards do the deciding: it acts only when exactly
                # one other repo declares a `Foo` owning exactly one `bar`.
                _park_unresolved_member_call(
                    node_by_id.get(caller), callee, receiver, "cpp", rc,
                )
                continue
            if len(type_defs) != 1:  # ambiguous -> bail (god-node guard)
                continue
            type_nid = type_defs[0]
            type_qualified = True
        else:
            # f.bar() / f->bar(): type the receiver via the file's local table.
            type_name = type_table_by_file.get(src_file, {}).get(receiver)
            if not type_name:
                continue
            type_defs = type_def_nids.get(_key(type_name), [])
            if not type_defs:
                _park_unresolved_member_call(
                    node_by_id.get(caller), callee, type_name, "cpp", rc,
                )
                continue
            if len(type_defs) != 1:  # ambiguous -> bail (god-node guard)
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
    (#1609), namespace-aware (#1620).

    The shared cross-file pass drops every ``is_member_call`` because a bare method
    name collides across the corpus — and for C# an in-file bare match silently
    mis-bound ``_server.Save()`` to an unrelated ``Cache.Save()``. The C# extractor
    records each member call's receiver and stamps ``receiver_type`` on the raw
    call from a METHOD-scoped ``name -> Type`` table of class fields/properties
    plus the declaring method's params/locals (#2299 — per-method like Java, so a
    name rebound in a different method never poisons this one; same-method
    conflicts and untypable rebindings are still POISONED, so a shadowing local of
    a different type produces no edge rather than a wrong one). This pass resolves
    the stamped type name with the same namespace/using/alias scoping machinery the
    type-reference pass uses (``CsharpNameResolver``), so a class name duplicated
    across namespaces still binds to the one in scope; only when scoping knows
    nothing about the name does it fall back to the corpus-wide unique bare-name
    match (the god-node guard). An untypable/ambiguous receiver is skipped — never
    a guess.

    Receiver typing, by precision tier:
      * ``this.M()`` — receiver is the caller's own enclosing class -> EXTRACTED.
      * ``base.M()`` — the caller's single resolvable base class -> EXTRACTED.
      * ``Type.M()`` (capitalized) — the type is named explicitly in source -> EXTRACTED.
      * ``recv.M()`` / ``this.recv.M()`` — ``recv`` typed via the extractor's
        method-scoped field/property/param/local table (``receiver_type`` on the
        raw call) -> INFERRED.

    A method not declared on the receiver's type is looked up through its
    ``inherits`` chain; a chain containing an unresolvable (out-of-corpus) base
    poisons the lookup — the method may live there, so no edge is emitted.

    Must run after id-disambiguation so node ids and caller_nids are final.
    """
    def _key(label: str) -> str:
        return re.sub(r"[^a-zA-Z0-9]+", "", str(label)).lower()

    contained = {e.get("target") for e in all_edges if e.get("relation") == "contains"}

    type_def_nids: dict[str, list[str]] = {}
    node_by_id: dict[str, dict] = {}
    for n in all_nodes:
        node_by_id[n.get("id")] = n
        if n.get("source_file") and n.get("id") in contained and _is_type_like_definition(n):
            type_def_nids.setdefault(_key(n.get("label", "")), []).append(n["id"])

    # Namespace/using/alias-aware simple-name resolution, shared with the C#
    # type-reference pass (which has already arbitrated inherits/implements/
    # references targets by the time the resolver registry runs).
    resolver = CsharpNameResolver(all_nodes, all_edges)

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

    # Base-class chain from `inherits` edges (C# files only). The type-reference
    # pass has already re-pointed each resolvable base to its real definition and
    # left unresolvable ones on dangling sourceless stubs — a stub target marks
    # the derived type's base chain as UNRESOLVED (poison: an inherited-member
    # lookup through it must bail, the member may be declared out of corpus).
    bases_of: dict[str, list[str]] = {}
    unresolved_base: set[str] = set()
    for e in all_edges:
        if e.get("relation") != "inherits":
            continue
        src_file = e.get("source_file")
        if not (isinstance(src_file, str) and src_file.endswith(".cs")):
            continue
        src, tgt = e.get("source"), e.get("target")
        if not (isinstance(src, str) and isinstance(tgt, str)):
            continue
        tnode = node_by_id.get(tgt)
        if tnode is None or not tnode.get("source_file"):
            unresolved_base.add(src)
        else:
            bucket = bases_of.setdefault(src, [])
            if tgt not in bucket:
                bucket.append(tgt)

    def _method_on_type_or_bases(type_nid: str, callee_key: str) -> str | None:
        """The method's definition on the type or its resolvable base chain.

        A type that declares the method directly wins (overrides shadow the
        base). Otherwise walk `inherits` upward; an unresolved base anywhere the
        walk actually reaches poisons the lookup (no edge), as does anything
        other than exactly one declaration found.
        """
        hits: set[str] = set()
        seen: set[str] = set()
        frontier = [type_nid]
        while frontier:
            nid = frontier.pop()
            if nid in seen:
                continue
            seen.add(nid)
            method_nid = method_index.get((nid, callee_key))
            if method_nid:
                hits.add(method_nid)
                continue  # an override shadows anything above it
            if nid in unresolved_base:
                return None  # the method may live on the out-of-corpus base
            frontier.extend(bases_of.get(nid, []))
        return next(iter(hits)) if len(hits) == 1 else None

    def _resolve_type_name_nid(type_name: str | None, caller_node: dict | None,
                               src_file: str) -> str | None:
        """Resolve a declared type name to exactly one definition node id.

        Namespace/using/alias scoping first (so `Svc` duplicated across
        namespaces binds to the one in scope); when scoping is decisive but
        ambiguous, bail. Only when scoping knows nothing about the name fall
        back to the corpus-wide unique bare-name match (which also covers
        nested types, absent from the scoped index).
        """
        if not type_name:
            return None
        if caller_node is not None:
            resolved, decisive = resolver.resolve_type_name(
                type_name, caller_node, src_file
            )
            if resolved:
                return resolved
            if decisive:
                return None
        type_defs = type_def_nids.get(_key(type_name), [])
        return type_defs[0] if len(type_defs) == 1 else None

    def _park_if_absent(type_name: str | None, caller_node: dict | None, rc: dict) -> None:
        """Park a call whose receiver type is declared nowhere in this corpus (#3152).

        ``_resolve_type_name_nid`` collapses "absent", "ambiguous" and "scoping was
        decisive" into one ``None``, and only the first is a cross-repo candidate,
        so re-check the bare-name index instead of trusting the ``None``.
        """
        if type_name and not type_def_nids.get(_key(type_name)):
            _park_unresolved_member_call(
                caller_node, rc.get("callee"), type_name, "csharp", rc,
            )

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
        caller_node = node_by_id.get(caller)
        if receiver == "this":
            type_nid = enclosing_type.get(caller)
            if not type_nid:
                continue
            type_qualified = True
        elif receiver == "base":
            enclosing = enclosing_type.get(caller)
            if not enclosing or enclosing in unresolved_base:
                continue
            bases = bases_of.get(enclosing, [])
            if len(bases) != 1:  # no base, or can't tell which — bail
                continue
            type_nid = bases[0]
            type_qualified = True
        elif receiver[:1].isupper():
            # Type.M() — the type is named explicitly (also covers a Pascal-cased
            # local whose name equals its type, resolved via the table below if the
            # explicit-type lookup misses).
            type_nid = _resolve_type_name_nid(receiver, caller_node, src_file)
            if not type_nid:
                type_name = rc.get("receiver_type")
                type_nid = _resolve_type_name_nid(type_name, caller_node, src_file)
                if not type_nid:
                    _park_if_absent(type_name or receiver, caller_node, rc)
                    continue
            type_qualified = True
        else:
            type_name = rc.get("receiver_type")
            if not type_name:
                continue
            type_nid = _resolve_type_name_nid(type_name, caller_node, src_file)
            if not type_nid:  # ambiguous or absent -> bail (god-node guard)
                _park_if_absent(type_name, caller_node, rc)
                continue
            type_qualified = False
        method_nid = _method_on_type_or_bases(type_nid, _key(callee))
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


def _bind_member_field_tables(
    per_file: list[dict],
    all_nodes: list[dict],
    *,
    lang: str,
) -> dict[str, dict[str, str]]:
    """Bind the exported per-file field tables (#3151) to class node ids.

    Entries are keyed by class label + source_file so they survive every id
    remap; here they are matched back to the one class node carrying that
    label (disambiguated by source_file basename when several share it).
    An entry that stays ambiguous binds nothing - guessing would attach a
    field table to the wrong class.
    """
    by_label: dict[str, list[dict]] = {}
    for n in all_nodes:
        if n.get("label") and n.get("source_file"):
            by_label.setdefault(str(n["label"]), []).append(n)
    bound: dict[str, dict[str, str]] = {}
    for result in per_file:
        for entry in (result.get("member_field_tables") or []):
            if not isinstance(entry, dict) or entry.get("lang") != lang:
                continue
            label, fields = entry.get("class_label"), entry.get("fields")
            if not label or not isinstance(fields, dict):
                continue
            candidates = by_label.get(str(label), [])
            if len(candidates) > 1:
                sf = str(entry.get("source_file") or "")
                exact = [n for n in candidates if str(n.get("source_file")) == sf]
                if len(exact) == 1:
                    candidates = exact
                else:
                    # the node's source_file may have been relativized since
                    # the entry was written; the basename still identifies it
                    base = os.path.basename(sf)
                    candidates = [
                        n for n in candidates
                        if os.path.basename(str(n.get("source_file"))) == base
                    ]
            if len(candidates) != 1:
                continue
            merged = bound.setdefault(candidates[0]["id"], {})
            for fname, tname in fields.items():
                if merged.get(fname) not in (None, tname):
                    merged.pop(fname, None)  # cross-shard conflict: no guess
                else:
                    merged[fname] = tname
    return bound


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
    # Inherited fields (#3151): a field declared on a superclass - possibly in
    # another file - types a `this.<field>` receiver in the subclass. Safe
    # because `this.` names a field by construction; no local can shadow it.
    # The per-file tables ride the results keyed by class label + source_file
    # (never node id, see #3150); bind each to its class node, ambiguity skips.
    inherits_bases: dict[str, list[str]] = {}
    for edge in all_edges:
        if edge.get("relation") == "inherits":
            inherits_bases.setdefault(edge["source"], []).append(edge["target"])
    class_fields = _bind_member_field_tables(per_file, all_nodes, lang="java")

    def _inherited_field_type(class_nid, field: str):
        seen: set = set()
        queue = [class_nid]
        while queue:
            cls = queue.pop(0)
            if not cls or cls in seen:
                continue
            seen.add(cls)
            hit = class_fields.get(cls, {}).get(field)
            if hit:
                return hit
            queue.extend(inherits_bases.get(cls, []))
        return None

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
                if not type_name and receiver.startswith("this."):
                    type_name = _inherited_field_type(
                        enclosing_type.get(caller), receiver[len("this."):]
                    )
                if not type_name:
                    continue
                type_defs = type_def_nids.get(key(type_name), [])
                if not type_defs:
                    # The type is declared nowhere in this corpus, which in a
                    # multi-repo setup usually means "in a repo this build does
                    # not contain" rather than "does not exist" — park it for the
                    # merge (#3152). An ambiguous name (>1 declaration) is a
                    # local ambiguity that merging only widens, so it stays
                    # dropped, exactly as the guard below already decided.
                    _park_unresolved_member_call(
                        node_by_id.get(caller), callee, type_name, "java", raw_call,
                    )
                    continue
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
      * ``[self.bar doIt]`` / ``[_ivarBar doIt]`` — the field typed via the class's
        ``@property``/ivar table (locals shadow fields for the bare-identifier
        form) -> INFERRED. Only the exact ``self.<field>`` receiver shape is
        captured; a dotted receiver like ``Foo.shared`` is never passed through,
        because ``_key`` would strip the dot and collide with a real ``FooShared``.
    An uninferable receiver is SKIPPED (no guess), so an ambiguous selector across
    classes never fans out. ``_merge_decl_def_classes`` folds each @interface/@impl
    pair into one node, so a paired class clears the single-definition guard.
    ``@protocol`` declarations are excluded from the receiver-type index: a protocol
    is a contract, not a message receiver, and ObjC keeps protocol and class names in
    separate namespaces, so a same-named pair used to both mis-bind a message to the
    protocol's declaration and, when a real class existed, trip the god-node guard.

    Must run after id-disambiguation so node ids and caller_nids are final.
    """
    type_table_by_file: dict[str, dict[str, str]] = {}
    for result in per_file:
        tt = result.get("objc_type_table")
        if tt and tt.get("path"):
            type_table_by_file[tt["path"]] = tt.get("table", {})

    # #1556: cross-file `field -> ClassName` tables merged per class nid (the
    # .h/.m pair share one id, preserved by _merge_decl_def_classes, so the header's
    # @property entries and the impl's ivar entries land in one table). A cross-file
    # conflict on the same (class, field) drops the entry — no guess.
    field_types_by_class: dict[str, dict[str, str]] = {}
    field_conflicts: set[tuple[str, str]] = set()
    for result in per_file:
        ft = result.get("objc_field_types")
        if not ft:
            continue
        for cls_nid, tbl in (ft.get("tables") or {}).items():
            merged = field_types_by_class.setdefault(cls_nid, {})
            for field, tname in tbl.items():
                if (cls_nid, field) in field_conflicts:
                    continue
                prev = merged.get(field)
                if prev is None:
                    merged[field] = tname
                elif prev != tname:
                    del merged[field]
                    field_conflicts.add((cls_nid, field))

    def _key(label: str) -> str:
        return re.sub(r"[^a-zA-Z0-9]+", "", str(label)).lower()

    contained = {e.get("target") for e in all_edges if e.get("relation") == "contains"}

    def _is_protocol_declaration(n: dict) -> bool:
        """A ``@protocol`` declaration, which the ObjC extractor labels ``<Name>``.

        A protocol is a contract, never a message receiver, so it must not be a
        receiver-typing candidate. It stays a valid target for `implements`; only
        this pass's type index excludes it.
        """
        label = str(n.get("label", "")).strip()
        return label.startswith("<") and label.endswith(">")

    type_def_nids: dict[str, list[str]] = {}
    node_by_id: dict[str, dict] = {}
    for n in all_nodes:
        node_by_id[n.get("id")] = n
        if (n.get("source_file") and n.get("id") in contained
                and _is_type_like_definition(n) and not _is_protocol_declaration(n)):
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
    # A @property declared on a superclass types [self.<field> ...] in the
    # subclass too (#3151): walk the inherits chain, nearest table first.
    _objc_bases: dict[str, list[str]] = {}
    for e in all_edges:
        if e.get("relation") == "inherits":
            _objc_bases.setdefault(e["source"], []).append(e["target"])

    def _field_type_up_chain(cls, receiver):
        seen: set = set()
        queue = [cls]
        while queue:
            c = queue.pop(0)
            if not c or c in seen:
                continue
            seen.add(c)
            hit = field_types_by_class.get(c, {}).get(receiver)
            if hit:
                return hit
            queue.extend(_objc_bases.get(c, []))
        return None

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
        if rc.get("receiver_kind") == "self_field":
            # `[self.bar doIt]`: the extractor stamped the BARE field name; type it
            # via the caller's own class's @property/ivar table. Checked before the
            # capitalized arm so a capitalized field never reads as a class name.
            cls = enclosing_type.get(caller)
            type_name = _field_type_up_chain(cls, receiver) if cls else None
            if not type_name:
                continue
            type_defs = type_def_nids.get(_key(type_name), [])
            if len(type_defs) != 1:  # ambiguous or absent -> bail (god-node guard)
                continue
            type_nid = type_defs[0]
            type_qualified = False
        elif receiver in ("self", "super"):
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
            # Locals shadow fields: the file's `Foo *f` local table first, then the
            # enclosing class's @property/ivar table (covers `[_ivarBar doIt]`).
            type_name = type_table_by_file.get(src_file, {}).get(receiver)
            if not type_name:
                cls = enclosing_type.get(caller)
                type_name = _field_type_up_chain(cls, receiver) if cls else None
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


def _kotlin_package_index(per_file: list[dict]) -> dict[str, list[dict]]:
    """Group per-file results by the Kotlin package they declare.

    ``kotlin_package`` is stamped by the generic engine from the file's
    ``package_header`` (see extractors/engine.py); every node in the file
    inherits it. Files with no package header contribute nothing.
    """
    pkg_results: dict[str, list[dict]] = {}
    for result in per_file:
        pkg = result.get("kotlin_package")
        if pkg:
            pkg_results.setdefault(pkg, []).append(result)
    return pkg_results


def _resolve_kotlin_import_targets(
    per_file: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> None:
    """Rewrite Kotlin ``imports`` edge targets from the bare last segment to the
    node the written FQN actually names (#2526).

    ``_import_kotlin`` emits ``file --imports--> _make_id(last_segment)`` with
    the full dotted path stamped as ``metadata.target_fqn``. That target dangles
    (node ids carry a file-stem prefix), so build pruned every Kotlin import and
    the import-evidence promotion in the shared call pass never fired. Here the
    per-file ``kotlin_package`` declarations index each package's importable
    (non-member) symbols by exact label; an edge whose ``target_fqn`` splits
    into a known package P plus a Name defined exactly ONCE in P is rewritten to
    that node id. The FQN is written verbatim in source, so the match is exact —
    confidence stays EXTRACTED. Anything else (external dependency, ambiguous
    name) is left untouched and dangles like other languages' external imports.

    Must run BEFORE the shared call pass builds its import-evidence index (it is
    invoked directly in extract(), not via the tail registry run).
    """
    pkg_results = _kotlin_package_index(per_file)
    if not pkg_results:
        return
    # package fqn -> {importable label -> [node ids]}. Member labels (leading
    # dot) are not importable as `P.Name`, and sourceless reference stubs are
    # not definitions; both are excluded so they can't shadow the real symbol.
    pkg_symbols: dict[str, dict[str, list[str]]] = {}
    for pkg, results in pkg_results.items():
        by_label = pkg_symbols.setdefault(pkg, {})
        for result in results:
            for n in result.get("nodes", []):
                if not n.get("source_file") or n.get("type") == "namespace":
                    continue
                label = str(n.get("label", ""))
                if not label or label.startswith("."):
                    continue
                by_label.setdefault(label.strip("()"), []).append(n["id"])
    for e in all_edges:
        if e.get("relation") != "imports":
            continue
        if not str(e.get("source_file", "")).endswith((".kt", ".kts")):
            continue
        fqn = (e.get("metadata") or {}).get("target_fqn", "")
        pkg, _, name = str(fqn).rpartition(".")
        if not pkg or not name:
            continue
        candidates = pkg_symbols.get(pkg, {}).get(name, [])
        if len(candidates) == 1:  # single-candidate guard: never fabricate
            e["target"] = candidates[0]


def _resolve_csharp_qualified_calls(
    per_file: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> None:
    """Resolve C# constructions that name their namespace (#2997).

    `new Infra.Data.Cache()` reaches the shared pass as the bare name `Cache`,
    so a second `Cache` in another namespace makes it ambiguous and it gets no
    edge, even though the source says which one it means. The reference paths
    (field, property, parameter, return) already honour the qualifier through
    `CsharpNameResolver`; this is the construction twin, built the way
    `_resolve_kotlin_qualified_calls` handles the same shape in Kotlin.

    The prefix must equal a declared namespace exactly. A partially qualified
    `new Data.Cache()` under `using Infra;` stays unresolved rather than
    guessing at the using directives in scope. Exactly one candidate produces an
    edge; zero or several leave the call alone. The pass is additive: an
    ambiguous bare name never had an edge to overwrite.
    """
    raw = [
        rc
        for result in per_file
        for rc in result.get("raw_calls", [])
        if rc.get("lang") == "csharp" and rc.get("qualified_prefix")
        and rc.get("callee") and rc.get("caller_nid")
    ]
    if not raw:
        return

    # (namespace, type name) -> nids, over sourced type declarations only, so a
    # sourceless stub minted for a dangling reference cannot win the match.
    by_namespace: dict[tuple[str, str], list[str]] = {}
    for n in all_nodes:
        if not n.get("_callable_class") or not n.get("source_file"):
            continue
        namespace = str((n.get("metadata") or {}).get("namespace") or "")
        label = str(n.get("label", "")).strip("()")
        if namespace and label:
            by_namespace.setdefault((namespace, label), []).append(n["id"])
    if not by_namespace:
        return

    # Scoped to `calls`: a method that both takes a type as a parameter and
    # constructs it already has a `references` edge to it, and that edge says
    # nothing about whether the construction was resolved.
    existing_pairs = {
        (e.get("source"), e.get("target"))
        for e in all_edges
        if e.get("relation") == "calls"
    }
    for rc in raw:
        candidates = by_namespace.get((rc["qualified_prefix"], rc["callee"]), [])
        if len(candidates) != 1:
            continue
        caller = rc["caller_nid"]
        tgt = candidates[0]
        if tgt == caller or (caller, tgt) in existing_pairs:
            continue
        existing_pairs.add((caller, tgt))
        all_edges.append({
            "source": caller,
            "target": tgt,
            "relation": "calls",
            "context": "call",
            "confidence": "EXTRACTED",  # the namespace is written verbatim in source
            "confidence_score": 1.0,
            "source_file": rc.get("source_file", ""),
            "source_location": rc.get("source_location"),
            "weight": 1.0,
        })


def _resolve_kotlin_qualified_calls(
    per_file: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> None:
    """Resolve Kotlin fully-qualified call expressions (#2550).

    ``com.example.nav.NavGraph()`` parses to a nested navigation_expression
    chain; the engine flattens it and stamps the raw_call with
    ``qualified_prefix="com.example.nav"`` + ``lang="kotlin"`` when EVERY chain
    segment is a plain identifier. The shared pass skips member calls, so these
    raw_calls produced no edge at all — this pass is strictly additive.

    Resolution, guarded by exactly-one-candidate at every step:
      * prefix == a declared package FQN P -> candidates are P's top-level
        callables (functions/classes the file node `contains`) named callee;
      * prefix == P + "." + TypeName where TypeName is a class/object declared
        in P -> candidates are that type's methods (`method` edges, `.callee()`
        label).
    Zero or 2+ candidates -> no edge. The FQN is written verbatim in source, so
    a unique match is EXTRACTED.
    """
    pkg_results = _kotlin_package_index(per_file)
    if not pkg_results:
        return
    raw = [
        rc
        for result in per_file
        for rc in result.get("raw_calls", [])
        if rc.get("lang") == "kotlin" and rc.get("qualified_prefix")
        and rc.get("callee") and rc.get("caller_nid")
    ]
    if not raw:
        return

    node_by_id: dict[str, dict] = {n.get("id"): n for n in all_nodes}
    contains_by_source: dict[str, list[str]] = {}
    methods_by_type: dict[str, list[str]] = {}
    for e in all_edges:
        rel = e.get("relation")
        if rel == "contains":
            contains_by_source.setdefault(e.get("source"), []).append(e.get("target"))
        elif rel == "method":
            methods_by_type.setdefault(e.get("source"), []).append(e.get("target"))

    # package fqn -> {name -> [top-level callable nids]} and
    # package fqn -> {name -> [top-level type nids]} (classes/objects).
    pkg_callables: dict[str, dict[str, list[str]]] = {}
    pkg_types: dict[str, dict[str, list[str]]] = {}
    for pkg, results in pkg_results.items():
        callables = pkg_callables.setdefault(pkg, {})
        types = pkg_types.setdefault(pkg, {})
        for result in results:
            file_nid = next(
                (n["id"] for n in result.get("nodes", [])
                 if n.get("source_file")
                 and n.get("label") == Path(str(n["source_file"])).name),
                None,
            )
            if file_nid is None:
                continue
            for tgt in contains_by_source.get(file_nid, []):
                n = node_by_id.get(tgt)
                if n is None or not n.get("source_file"):
                    continue
                name = str(n.get("label", "")).strip("()")
                if not name or name.startswith("."):
                    continue
                if n.get("_callable"):
                    callables.setdefault(name, []).append(tgt)
                if n.get("_callable_class"):
                    types.setdefault(name, []).append(tgt)

    existing_pairs = {(e.get("source"), e.get("target")) for e in all_edges}
    for rc in raw:
        prefix = rc["qualified_prefix"]
        callee = rc["callee"]
        caller = rc["caller_nid"]
        candidates: list[str] = []
        if prefix in pkg_callables:
            # `P.callee()` — a top-level function or class constructor in P.
            candidates = pkg_callables[prefix].get(callee, [])
        else:
            # `P.Type.callee()` — a method of a class/object declared in P.
            pkg, _, type_name = prefix.rpartition(".")
            type_nids = pkg_types.get(pkg, {}).get(type_name, []) if pkg else []
            if len(type_nids) == 1:
                wanted = f".{callee}"
                candidates = [
                    m for m in methods_by_type.get(type_nids[0], [])
                    if str(node_by_id.get(m, {}).get("label", "")).strip("()") == wanted
                ]
        if len(candidates) != 1:  # zero or ambiguous -> no edge (god-node guard)
            continue
        tgt = candidates[0]
        if tgt == caller or (caller, tgt) in existing_pairs:
            continue
        existing_pairs.add((caller, tgt))
        all_edges.append({
            "source": caller,
            "target": tgt,
            "relation": "calls",
            "context": "call",
            "confidence": "EXTRACTED",  # the FQN is written verbatim in source
            "confidence_score": 1.0,
            "source_file": rc.get("source_file", ""),
            "source_location": rc.get("source_location"),
            "weight": 1.0,
        })


# Kotlin import-target resolution runs EARLY (directly in extract(), before the
# shared call pass builds its import-evidence index) — registering it in the
# tail registry would rewrite the targets after promotion already read them.
# It still uses the registry's LanguageResolver/driver for the suffix gate and
# failure isolation.
_KOTLIN_IMPORT_TARGET_RESOLVER = LanguageResolver(
    "kotlin_import_targets", frozenset({".kt", ".kts"}), _resolve_kotlin_import_targets
)


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
# Kotlin fully-qualified call resolution (#2550): `com.pkg.Fn()` /
# `com.pkg.Object.method()` raw_calls the shared pass skips (member calls with
# no receiver). Runs in the tail registry like the other member-call resolvers;
# its sibling import-target pass runs earlier (see _KOTLIN_IMPORT_TARGET_RESOLVER).
register_language_resolver(
    LanguageResolver(
        "kotlin_qualified_calls", frozenset({".kt", ".kts"}), _resolve_kotlin_qualified_calls
    )
)
# C# qualified construction (#2997): `new A.B.Cache()` arrives as the bare name,
# so a colliding `Cache` elsewhere makes it ambiguous. Runs in the tail registry
# beside csharp_member_calls and matches the prefix against declared namespaces.
register_language_resolver(
    LanguageResolver(
        "csharp_qualified_calls", frozenset({".cs"}), _resolve_csharp_qualified_calls
    )
)
# C# member-level interface dispatch (#3003): a call through an injected
# dependency lands on the interface's method, so the implementation sits in the
# graph unreachable from the call site. Lives in graphify.csharp_dispatch;
# registered here as a consumer of the framework, like the Pascal resolver.
register_language_resolver(
    LanguageResolver(
        "csharp_interface_dispatch", frozenset({".cs"}), resolve_csharp_interface_dispatch
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
    # Prune noise/hidden dirs DURING traversal (not after) so the scan never
    # descends into node_modules/.venv/.git/build/..., and CAP the number of
    # directories visited. rglob("*.cs") used to walk the entire tree first,
    # which on a mis-resolved or huge root (e.g. a .xaml under a shared temp dir
    # or a giant monorepo, where _xaml_project_root climbs to a broad ancestor)
    # scanned millions of paths and effectively hung. A real .NET project sits
    # well under the cap; a runaway root is bounded to a fast, partial scan
    # instead of hanging.
    import os as _os
    _DIR_CAP = 20000
    cs_files: list[Path] = []
    visited = 0
    try:
        for dirpath, dirnames, filenames in _os.walk(root):
            dirnames[:] = [
                d for d in dirnames if not d.startswith(".") and not _is_noise_dir(d)
            ]
            for fn in filenames:
                if fn.endswith(".cs"):
                    cs_files.append(Path(dirpath) / fn)
            visited += 1
            if visited >= _DIR_CAP:
                break
    except OSError:
        return classes
    cs_files.sort()
    for cs_path in cs_files:
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
    ".cjs": extract_js,
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
    ".ml": extract_ocaml,
    ".mli": extract_ocaml,
    ".lisp": extract_commonlisp,
    ".cl": extract_commonlisp,
    ".lsp": extract_commonlisp,
    ".asd": extract_commonlisp,
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
    ".robot": extract_robot,
    ".resource": extract_robot,
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
    ".ml": "ocaml",
    ".mli": "ocaml",
    ".lisp": "commonlisp",
    ".cl": "commonlisp",
    ".lsp": "commonlisp",
    ".asd": "commonlisp",
    ".robot": "robot",
    ".resource": "robot",
}

# Substrings an extractor's error carries to classify why a dependency-backed
# file contributed nothing, used by the #1745 warning in extract(). A grammar
# that is present but fails to load (#2602) must not be reported as missing —
# the "install the extra" hint would be a no-op.
_DEP_MISSING_MARKER = "not installed"
_DEP_LOAD_FAILED_MARKER = "failed to load"


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

    # A one-worker pool buys no parallelism: it still pays process spawn plus an
    # IPC round trip per file, and it is the one residual case where the parent's
    # rebuild watchdog (os._exit) can orphan a worker that is mid-task. The
    # Windows post-commit hook exports GRAPHIFY_MAX_WORKERS=1, so this is the
    # default there. Hand the work back so the caller extracts sequentially in
    # this process instead (#2173).
    if max_workers == 1:
        return False

    # root anchors hash keys / node ids / XAML boundary; cache_location is where
    # the cache dir is written (defaults to root when not decoupled) (#1774).
    root_str = str(root)
    cache_loc_str = str(cache_location if cache_location is not None else root)
    work_items = [(idx, str(path), root_str, cache_loc_str) for idx, path in uncached_work]

    done_count = 0
    failed: list[int] = []  # positions into uncached_work whose future failed
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
                except concurrent.futures.process.BrokenProcessPool:
                    # #2444: a pool that dies while results are being consumed
                    # raises BrokenProcessPool from every pending future. It
                    # must reach the pool-level handler below (which returns
                    # False so the caller falls back to sequential), not be
                    # swallowed here per-future — that left the remaining
                    # per_file slots empty and silently dropped the files.
                    raise
                except Exception as exc:
                    pos = futures[future]
                    print(
                        f"  warning: worker failed for {work_items[pos][1]}: {exc}",
                        file=sys.stderr, flush=True,
                    )
                    failed.append(pos)
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
    if failed:
        # #2445: retry per-future failures once, in-process, instead of leaving
        # their per_file slots None (which the defensive fill downstream turned
        # into well-formed empties — silent data loss). This is bounded, not a
        # loop: _extract_sequential goes through _safe_extract, which converts
        # a second failure into an error-carrying result.
        _extract_sequential(
            [uncached_work[pos] for pos in failed],
            per_file, root, total_files, cache_location,
        )
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
    root: Path | None = None,
    parallel: bool = True,
    max_workers: int | None = None,
    resolution_context_nodes: list[dict] | None = None,
    resolution_context_edges: list[dict] | None = None,
) -> dict:
    """Extract AST nodes and edges from a list of code files.

    Two-pass process:
    1. Per-file structural extraction (classes, functions, imports)
    2. Cross-file import resolution: turns file-level imports into
       class-level INFERRED edges (DigestAuth --uses--> Response)

    Args:
        paths: files to extract from
        root: explicit anchor for source_file relativization, node ids, and
            symbol resolution. Pass the SCAN root whenever the cache lives
            somewhere else (`--out`); without it the anchor falls back to
            cache_root and every scanned file reads as out-of-root (#1941).
        cache_root: explicit root for graphify-out/cache/ (overrides the
            inferred common path prefix). Pass Path('.') when running on a
            subdirectory so the cache stays at ./graphify-out/cache/.
            Anchors ids/source_file only as a fallback when `root` is unset.
        parallel: if True and there are >= _PARALLEL_THRESHOLD uncached files,
            use ProcessPoolExecutor for multi-core extraction.
        max_workers: max subprocess count. Defaults to cpu_count (or the
            value of GRAPHIFY_MAX_WORKERS if set), bounded by len(uncached_work).
        resolution_context_nodes: read-only AST nodes from files that are NOT
            being extracted this run (an incremental rebuild's unchanged
            corpus, #2406). They extend the cross-file resolution indexes —
            the shared direct-call pass's label/file indexes, the
            indirect_call callable guard (via the persisted `_callable` /
            `_callable_class` markers, #2438), and the member-call resolvers
            run by `run_language_resolvers` (#2437) — so a changed caller can
            still bind `foo()`, `obj.method()`, or `submit(handler)` to an
            unchanged callee. They are never parsed, mutated, or returned;
            raw_calls come only from `paths`, so only edges sourced by the
            re-extracted files are emitted.
        resolution_context_edges: the `contains`/`method` edges of the same
            unchanged corpus (#2437). The member-call resolvers walk these to
            map a receiver type to the single class owning the called method;
            without them an unchanged callee's class never passes the
            single-definition guard. Read-only, same contract as
            resolution_context_nodes: they widen the resolvers' view but only
            fresh results are appended to the returned nodes/edges.
    """
    paths = [Path(p) for p in paths]
    anchor_root = Path(root) if root is not None else None
    _check_tree_sitter_version()
    _raise_recursion_limit()
    # Workspace package manifests/globs can change during watch or repeated extraction.
    _WORKSPACE_PACKAGE_CACHE.clear()
    # tsconfig/jsconfig compilerOptions are the same kind of state: keyed by
    # config path with no mtime component, so an edit to `paths` or `baseUrl`
    # was never observed again for the life of the process. `graphify watch`
    # and the MCP server both call extract() repeatedly in one process, so
    # every rebuild after the edit kept resolving through the stale alias map.
    # Clearing per run, not per file, leaves within-run caching intact.
    _TSCONFIG_ALIAS_CACHE.clear()
    _TSCONFIG_BASEURL_CACHE.clear()
    _XAML_CSHARP_CLASS_CACHE.clear()
    _MD_LINK_INDEX_CACHE.clear()

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
    # An explicit anchor wins. cache_root is only a fallback anchor: it happens to
    # equal the scan root for the no---out CLI path and for watch, but with --out it
    # is the OUTPUT dir, and letting it anchor made every scanned file "out-of-root"
    # -> _portable_out_of_root_sf() -> bare basename for the whole corpus (#1941).
    if anchor_root is not None:
        root = anchor_root
    elif cache_root is not None:
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
            # #2444: only re-extract what the pool didn't finish. A pool that
            # breaks mid-run has already filled some per_file slots; redoing
            # the whole batch would throw that work away.
            _extract_sequential(
                [(i, p) for (i, p) in uncached_work if per_file[i] is None],
                per_file, root, total, cache_location,
            )

    # Fill any remaining None slots. With the #2444/#2445 handling above this
    # is unreachable; the error marker keeps any regression loud (and out of
    # the caches/#1666 paths) instead of letting a dropped file masquerade as
    # a legitimately-empty one.
    for i in range(total):
        if per_file[i] is None:
            per_file[i] = {
                "nodes": [], "edges": [],
                "error": "internal: no extraction result produced",
            }

    # #1666: surface any source file an extractor accepted but that produced zero
    # nodes (not even a file node). Such a file is silently absent from the graph,
    # so affected/explain are blind to and through it with no other signal.
    _empty_sources: list[str] = []
    for i, _p in enumerate(paths):
        _res = per_file[i] or {}
        if _res.get("nodes") or _res.get("error") or _res.get("skipped"):
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

    # #2543: collect sources that must NOT be stamped as up-to-date in the
    # incremental manifest. Two cases:
    #   - extractor returned an error (missing optional extra, parse failure, …)
    #   - extractor exists but produced zero nodes (#1666 empty-source set)
    # The CLI drops these from the stamped file set and clears any prior
    # hashes so the next run retries them after the user installs the extra
    # (or the transient failure self-heals) without deleting graphify-out/.
    _failed_sources: list[str] = []
    _failed_seen: set[str] = set()
    for i, _p in enumerate(paths):
        _res = per_file[i] or {}
        _key = str(_p)
        if _res.get("error"):
            if _key not in _failed_seen:
                _failed_sources.append(_key)
                _failed_seen.add(_key)
            continue
        if _res.get("skipped"):
            # The extractor declined this file by design (data JSON, #1224), so
            # zero nodes is the intended outcome rather than a failure. Marking
            # it failed keeps it out of the incremental manifest and re-queues
            # it on every subsequent run, forever (#2879).
            continue
        if (not _res.get("nodes")) and _get_extractor(_p) is not None:
            if _key not in _failed_seen:
                _failed_sources.append(_key)
                _failed_seen.add(_key)

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
        if _DEP_MISSING_MARKER in _err or _DEP_LOAD_FAILED_MARKER in _err:
            _ext = _p.suffix.lower()
            _missing_dep_count[_ext] = _missing_dep_count.get(_ext, 0) + 1
            _missing_dep_error.setdefault(_ext, _err)
    for _ext, _n in sorted(_missing_dep_count.items(), key=lambda kv: (-kv[1], kv[0])):
        _extra = _EXTRA_FOR_EXTENSION.get(_ext)
        _err_text = _missing_dep_error[_ext]
        if _extra and _DEP_MISSING_MARKER in _err_text:
            # Genuinely absent optional extra — point the user at the install.
            _reason = _err_text.split(". ")[0]
            _hint = f' Install it with: pip install "graphifyy[{_extra}]"'
            _cause = "a dependency is missing"
        else:
            # Either no known extra, or the grammar is present but failed to
            # load (#2602): surface the real error and never suggest reinstall.
            _reason = _err_text
            _hint = ""
            _cause = ("a dependency is missing" if _DEP_MISSING_MARKER in _err_text
                      else "a dependency failed to load")
        print(
            f"  warning: {_n} {_ext} file(s) contributed nothing to the graph "
            f"because {_cause}: {_reason}.{_hint} (#1745)",
            file=sys.stderr, flush=True,
        )

    # #2551: a file the parser ACCEPTED but only with ERROR recovery (e.g. the
    # Kotlin grammar rejecting one-line `class C { val x }` bodies, or Luau
    # syntax the Lua grammar can't parse, #2520) extracts partially — sometimes
    # to nothing but the file node — with no other signal. Neither warning
    # above fires (nodes exist, no error marker), so surface it explicitly,
    # naming the first error line so the user can find the construct.
    _syntax_error_files: list[tuple[str, int | None]] = []
    for i, _p in enumerate(paths):
        _res = per_file[i] or {}
        _pe = _res.get("parse_errors")
        if not _pe:
            continue
        # #2610/#2599: gate the #2551 warning on plausible symbol loss.
        # tree-sitter-typescript sets has_error on tiny fully-recovered errors
        # (a `&` in a JSX string attr; a semicolon-less `in_*` interface
        # member) that extract completely — stay silent. Warn only when
        # nothing beyond the file node extracted, or an ERROR region
        # dissolved multiple lines (the genuine #2551 Kotlin one-line-body /
        # #2520 Luau case). `multiline_error` is absent from pre-fix cached
        # results, so those fall back to the file-node-only arm.
        if len(_res.get("nodes", [])) <= 1 or _pe.get("multiline_error"):
            _rel = os.path.relpath(str(_p), str(root)).replace("\\", "/")
            # Symbols recovered from the file, excluding its own file node. This
            # is what separates the two cases the warning otherwise blurs: a file
            # that contributed nothing but its file node is a total loss, while
            # one that yielded most of its symbols and lost an ERROR region is
            # partial. "May be partially extracted" rendered both identically.
            _kept = max(len(_res.get("nodes", [])) - 1, 0)
            _syntax_error_files.append((_rel, _pe.get("first_error_line"), _kept))
    if _syntax_error_files:
        def _describe_syntax_error(rel: str, line: "int | None", kept: int) -> str:
            _where = f"first error at line {line}" if line else "syntax error"
            _got = "no symbols extracted" if kept == 0 else f"{kept} symbol(s) extracted"
            return f"{rel} ({_where}, {_got})"

        _shown = ", ".join(
            _describe_syntax_error(*f) for f in _syntax_error_files[:5]
        )
        _more = (
            f" (+{len(_syntax_error_files) - 5} more)"
            if len(_syntax_error_files) > 5 else ""
        )
        # No issue reference here. This message used to end in "(#2551)" for
        # EVERY language, and #2551 is closed and Kotlin-specific ("bundled
        # grammar rejects one-line type bodies"). It was the only lead the
        # message offered, so a reader following it landed on a resolved problem
        # in another language and concluded their own was already tracked
        # (#2788). The file, the line and the symbol count are the actionable
        # part; a single hardcoded number cannot be right for every grammar.
        print(
            f"  warning: {len(_syntax_error_files)} file(s) had syntax errors and "
            f"may be partially extracted: {_shown}{_more}",
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
    # A target OUTSIDE the scan root (an out-of-root ProjectReference/.sln/bash
    # `source`/#include/relative import) can't be made relative to root; leaving
    # it absolute leaked the scan path including the OS username into a
    # committed graph.json (#1899). Fall back to a walk-up relative form, or the
    # bare basename when that would still embed foreign path segments (a
    # far-away or cross-drive target). Shared below by both the target_file
    # remap loop (edges with no node of their own, #2243) and the node-level
    # relativization pass further down (#1899/#2195).
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
    # Canonical stem plus every prefix form a file's symbol ids may appear
    # under, keyed by resolved path — consumed by the target_file-guided
    # barrel repoint below (#1983). Unlike prefix_remap this records ALL
    # in-root files, not just those whose prefix changed.
    stem_forms: dict[Path, tuple[str, list[str]]] = {}
    # Canonicalize edge-target files too, not just this batch's inputs (#2169).
    # On an incremental run `paths` is only the CHANGED files, so a changed
    # file's cross-file import/re-export edges keep absolute-path-derived
    # target ids the remap below never learns — they match no node in the
    # merged graph and silently dangle. The target_file stamp (set at edge
    # emit time) names each resolved target, so registering id_remap /
    # stem_forms for those in-root files as well lets the edge remap and the
    # target_file-guided repoint pass fix them exactly as on a full scan.
    remap_paths: list[Path] = list(paths)
    _remap_seen: set[Path] = set()
    for _p in paths:
        try:
            _remap_seen.add(_p.resolve())
        except (OSError, RuntimeError):
            pass
    for _e in all_edges:
        _tf = _e.get("target_file")
        if not _tf:
            continue
        _raw_tp = Path(_tf)
        try:
            _tp = _raw_tp.resolve()
        except (OSError, RuntimeError):
            continue
        if _tp in _remap_seen:
            # Already covered: either the target is in this batch (its input
            # form is the same form the extractors minted ids from, and the
            # per-path loop registers both that and the resolved form) or an
            # earlier stamped edge registered it. Re-appending it here would
            # re-run its per-path iteration AFTER later batch files and could
            # flip the last-writer of a colliding old-id key.
            continue
        _remap_seen.add(_tp)
        try:
            _tp.relative_to(root)
        except ValueError:
            # Out-of-root target: `_file_node_id` (used below for in-root
            # targets) needs a root-relative path, so it cannot help here.
            # No node stands for this target either (target_file-stamped
            # edges intentionally mint no stub node, #2195), so unlike an
            # out-of-root node the belt-and-braces pass below never learns
            # this id from anywhere — without registering it here the raw
            # scan-path slug survives in the edge forever (#2243). Give it
            # the same portable "ext_" id an out-of-root node would get; a
            # target that does not actually exist on disk stays dangling,
            # exactly as before.
            try:
                if _tp.is_file():
                    ext_new_id = _make_id("ext", _portable_out_of_root_sf(_tp))
                    id_remap[_make_id(str(_tp))] = ext_new_id
                    if _raw_tp != _tp:
                        id_remap[_make_id(str(_raw_tp))] = ext_new_id
                    # Bash entrypoint endpoints suffix the file-level id with
                    # "__entry" (script-invocation `calls` edges,
                    # extractors/bash.py); register the suffixed forms too so
                    # an out-of-root invoked script canonicalizes instead of
                    # keeping the absolute scan-path slug (#2243).
                    id_remap.setdefault(
                        _make_id(str(_tp)) + "__entry", ext_new_id + "__entry")
                    if _raw_tp != _tp:
                        id_remap.setdefault(
                            _make_id(str(_raw_tp)) + "__entry",
                            ext_new_id + "__entry")
            except OSError:
                pass
            continue
        try:
            if not _tp.is_file():
                # Speculatively-resolved target that doesn't exist (e.g. an
                # import of a not-yet-created sibling): keep its raw id
                # dangling, exactly as before, so no false canonical edge is
                # fabricated toward a nonexistent file.
                continue
        except OSError:
            continue
        remap_paths.append(_tp)
        # Also register the AS-STAMPED (unresolved) form. The edge target id
        # was minted from the stamped path exactly as written (e.g.
        # ``str(base / rel)`` for a Python relative import), which under a
        # symlinked root (macOS /tmp -> /private/tmp) or relative inputs
        # differs from the resolved form; the per-path loop below derives the
        # old ids from whichever Path it is given, so a missing form would
        # leave the edge target unmapped and dangling.
        if _raw_tp != _tp:
            _remap_seen.add(_raw_tp)
            remap_paths.append(_raw_tp)
    for path in remap_paths:
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
        # Bash entrypoint node ids append "__entry" to the file-level id
        # (extractors/bash.py), so a script-invocation edge endpoint minted
        # from an out-of-batch target path keeps a suffixed absolute-derived
        # id neither the plain id_remap key above nor the source_file-gated
        # prefix pass below (nodes only) can reach on an incremental run
        # (#2243). Register the suffixed forms, preserving the extension tail
        # exactly as the prefix remap yields for in-batch entry nodes
        # (`c.sh` -> `c_sh__entry`): new prefix + the tail of the minted id.
        for _old, _pref in ((old_id, old_pref), (old_id_abs, old_pref_abs)):
            if not _old.startswith(_pref):
                continue
            _entry_new = new_id + _old[len(_pref):] + "__entry"
            _entry_old = _old + "__entry"
            if _entry_old != _entry_new:
                id_remap.setdefault(_entry_old, _entry_new)
        if old_prefs:
            prefix_remap[path.resolve()] = old_prefs
        # Absolute form first: it is the longest, so prefix decomposition can
        # try forms in order without a shorter form shadowing it.
        stem_forms[path.resolve()] = (
            new_id, [old_pref_abs, old_pref, new_id]
        )
    if id_remap:
        for n in all_nodes:
            if n.get("id") in id_remap:
                n["id"] = id_remap[n["id"]]
        for e in all_edges:
            if e.get("source") in id_remap:
                e["source"] = id_remap[e["source"]]
            if e.get("target") in id_remap:
                e["target"] = id_remap[e["target"]]
        # raw_calls carry caller_nid, consumed by the cross-file call pass far
        # below (after this remap). A module-TOP-LEVEL indirect_call/callback
        # records the FILE-level id as its caller — the id minted from the
        # absolute input path that this very remap just rewrote on the file
        # node. Without rewriting the raw_calls too, the emitted
        # indirect_call edge keeps the machine-specific absolute-derived
        # source and matches no node in the graph (#2231). Mirrors the
        # sym_remap raw_calls rewrite in the prefix pass below.
        for rc in all_raw_calls:
            cn = rc.get("caller_nid")
            if cn in id_remap:
                rc["caller_nid"] = id_remap[cn]
        # swift_extensions[].nid is the same kind of id carrier as caller_nid
        # above (cache.py remaps both), consumed by _merge_swift_extensions far
        # below. Left stale it matches no node, so whether the extension merge
        # runs at all depends on the FORM of the paths handed to extract() —
        # relative input already yields the post-remap slug, absolute input does
        # not (#2538). Remap it here so both agree.
        for result in per_file:
            for ext in result.get("swift_extensions", []) or []:
                en = ext.get("nid")
                if en in id_remap:
                    ext["nid"] = id_remap[en]
        # objc_field_types["tables"] is keyed BY class node id - the one bucket
        # the #1529 rewrites missed (#3150).
        _remap_objc_field_tables(per_file, id_remap)
    if prefix_remap:
        sym_remap: dict[str, str] = {}
        edge_alias_candidates: dict[str, set[str]] = {}
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
            canonical_nid: str | None = None
            for old_pref, new_pref in entry:
                if nid.startswith(old_pref + "_"):
                    canonical_nid = new_pref + nid[len(old_pref):]
                    if canonical_nid != nid:
                        sym_remap[nid] = canonical_nid
                    break
                if nid.startswith(new_pref + "_"):
                    canonical_nid = nid
                    break
            if canonical_nid is None:
                continue
            # Named alias imports/re-exports can retain an absolute-prefixed target
            # when the symbol node is already canonical. Record every old form
            # so a redundant import edge or dangling re-export target can be fixed
            # without globally reinterpreting an id that another real node may own.
            for old_pref, new_pref in entry:
                if not canonical_nid.startswith(new_pref + "_"):
                    continue
                old_nid = old_pref + canonical_nid[len(new_pref):]
                if old_nid != canonical_nid:
                    edge_alias_candidates.setdefault(old_nid, set()).add(canonical_nid)
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
            # Same for swift_extensions[].nid (see the id_remap pass above).
            for result in per_file:
                for ext in result.get("swift_extensions", []) or []:
                    en = ext.get("nid")
                    if en in sym_remap:
                        ext["nid"] = sym_remap[en]
            _remap_objc_field_tables(per_file, sym_remap)
        if edge_alias_candidates:
            def _edge_key(edge: dict) -> str:
                # target_file is a transient stamp (#1814/#1983); exclude it
                # from twin identity or an alias edge (stamped) never matches
                # the canonical twin the shared resolver emits (unstamped).
                return json.dumps(
                    {k: v for k, v in edge.items() if k != "target_file"},
                    sort_keys=True, separators=(",", ":"), default=str,
                )
            edge_key_counts = Counter(_edge_key(edge) for edge in all_edges)
            owned_node_ids = {node.get("id") for node in all_nodes}
            deduped_edges: list[dict] = []
            for edge in all_edges:
                if edge.get("relation") == "re_exports":
                    candidates = edge_alias_candidates.get(edge.get("target", ""), set())
                    if len(candidates) == 1 and edge.get("target") not in owned_node_ids:
                        edge["target"] = next(iter(candidates))
                    deduped_edges.append(edge)
                    continue
                candidates = (
                    edge_alias_candidates.get(edge.get("target", ""), set())
                    if edge.get("relation") == "imports"
                    else set()
                )
                if len(candidates) == 1:
                    candidate = next(iter(candidates))
                    twin_key = _edge_key({**edge, "target": candidate})
                    # Drop only when the shared resolver emitted the exact
                    # canonical twin. Otherwise the target may be a legitimate
                    # owned node id.
                    if edge_key_counts[twin_key]:
                        if edge.get("target") in owned_node_ids:
                            edge_key_counts[twin_key] -= 1
                        continue
                deduped_edges.append(edge)
            all_edges[:] = deduped_edges

    # Repoint symbol-level alias edges that resolve THROUGH a barrel (#1983
    # follow-up). The candidates rewrite above learns old→canonical forms only
    # from symbols a file DEFINES; a barrel defines nothing, so a re-export or
    # named import that resolves to one keeps an absolute-prefixed, dangling
    # target no rewrite ever learns. Use the target_file stamp to decompose
    # such a target into (canonical file stem, symbol), follow the barrel's own
    # already-canonical re_exports edge to the defining symbol — iterating so
    # multi-hop barrel chains resolve one hop per pass — and, when no chain
    # leads to a real node, canonicalize the prefix anyway so a checkout path
    # never survives in an edge target.
    if stem_forms:
        owned_ids = {n.get("id") for n in all_nodes}

        def _decompose(target: str, tf: str) -> "tuple[str, str] | None":
            try:
                forms = stem_forms.get(Path(tf).resolve())
            except (OSError, RuntimeError):
                return None
            if not forms:
                return None
            canonical, prefixes = forms
            for pref in prefixes:
                if pref and target.startswith(pref + "_"):
                    return canonical, target[len(pref) + 1:]
            return None

        # (canonical file id, symbol) → set of owned targets, learned from
        # symbol-level re_exports edges that already point at a real node. A set
        # (not last-write-wins): when a barrel re-exports the SAME local name
        # from two different modules (`export {x} from './a'; export {x as y}
        # from './b'` — both key on local name `x`), the key becomes ambiguous
        # and must NOT be guessed, or we fabricate a wrong edge. Ambiguous keys
        # resolve to None so the edge falls to the dangling-canonical fallback
        # (dropped at build), while the shared resolver's correct edge survives.
        chain: dict[tuple[str, str], set] = {}

        def _resolve1(key) -> "str | None":
            targets = chain.get(key)
            return next(iter(targets)) if targets and len(targets) == 1 else None

        def _learn(e: dict) -> None:
            tf = e.get("target_file")
            if not tf or e.get("target") not in owned_ids:
                return
            dec = _decompose(e.get("target", ""), tf)
            if dec is not None:
                chain.setdefault((e.get("source"), dec[1]), set()).add(e["target"])

        for e in all_edges:
            if e.get("relation") == "re_exports":
                _learn(e)

        pending = [
            e for e in all_edges
            if e.get("relation") in ("re_exports", "imports")
            and e.get("target_file")
            and e.get("target") not in owned_ids
        ]
        for _ in range(8):  # bounded: each pass resolves one barrel hop
            progressed = False
            still: list[dict] = []
            for e in pending:
                dec = _decompose(e.get("target", ""), e["target_file"])
                resolved_target = _resolve1((dec[0], dec[1])) if dec else None
                if resolved_target is None:
                    still.append(e)
                    continue
                e["target"] = resolved_target
                if e.get("relation") == "re_exports":
                    # This barrel's edge now feeds the next hop. Learn it
                    # directly — decomposing the repointed target against this
                    # edge's own target_file would fail, since the target now
                    # carries the DEFINING file's stem, not the barrel's.
                    chain.setdefault((e.get("source"), dec[1]), set()).add(resolved_target)
                progressed = True
            pending = still
            if not progressed:
                break
        for e in pending:
            dec = _decompose(e.get("target", ""), e["target_file"])
            if dec is not None:
                e["target"] = f"{dec[0]}_{dec[1]}"

    # Repoint Python absolute imports onto the real file nodes under a nested
    # (src/) package root before the resolver/import-evidence passes run, so the
    # graph is identical regardless of scan root (#2072).
    _repoint_python_package_imports(paths, all_nodes, all_edges, root)
    _merge_swift_extensions(per_file, all_nodes, all_edges)
    _merge_csharp_partial_class_nodes(per_file, all_nodes, all_edges, paths, root)
    _disambiguate_colliding_node_ids(all_nodes, all_edges, all_raw_calls, root)
    _canonicalize_csharp_namespace_nodes(all_nodes, all_edges)
    # PHP namespace/use disambiguation must run BEFORE the unique-stub rewire:
    # the false merge (#1923) happens inside the rewire when a bare-name stub
    # matches a unique internal class from a different namespace.
    _php_exts = {".php", ".phtml", ".php3", ".php4", ".php5", ".php7", ".phps"}
    _php_sel = [
        (r, p) for r, p in zip(per_file, paths)
        if p.suffix.lower() in _php_exts and not p.name.lower().endswith(".blade.php")
    ]
    if _php_sel:
        try:
            _resolve_php_type_references(
                [r for r, _ in _php_sel], [p for _, p in _php_sel], all_nodes, all_edges
            )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("PHP type-reference resolution failed, skipping: %s", exc)
    # Java package/import disambiguation must likewise run BEFORE the rewire
    # (#2504): an EXTERNAL import (`org.springframework.stereotype.Component`)
    # leaves a bare `Component` stub that the rewire would collapse onto the only
    # internal class with that simple name, manufacturing a false hub. Parking
    # such references on an FQN-labeled stub first prevents the merge, and
    # import-exact resolution of internal references (#1318/#1744) still applies.
    _java_sel = [(r, p) for r, p in zip(per_file, paths) if p.suffix == ".java"]
    if _java_sel:
        try:
            _resolve_java_type_references(
                [r for r, _ in _java_sel], [p for _, p in _java_sel], all_nodes, all_edges
            )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Java type-reference resolution failed, skipping: %s", exc)
    # Resolve internal Go pkg.Type references exactly and park external ones
    # before the generic bare-label stub rewire can manufacture a collision.
    _go_sel = [(r, p) for r, p in zip(per_file, paths) if p.suffix == ".go"]
    if _go_sel:
        try:
            _resolve_go_type_references(
                [r for r, _ in _go_sel], [p for _, p in _go_sel],
                all_nodes, all_edges, root,
                resolution_context_nodes, resolution_context_edges,
            )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "Go type-reference resolution failed, skipping: %s", exc
            )
    # Cross-file Python import resolution and type-reference repointing (#3252)
    py_paths = [p for p in paths if p.suffix == ".py"]
    if py_paths:
        py_results = [r for r, p in zip(per_file, paths) if p.suffix == ".py"]
        try:
            cross_file_edges = _resolve_cross_file_imports(py_results, py_paths, all_nodes, all_edges)
            all_edges.extend(cross_file_edges)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Cross-file import resolution failed, skipping: %s", exc)
    _rewire_unique_stub_nodes(all_nodes, all_edges)

    # Cross-file Java import resolution
    java_paths = [p for p in paths if p.suffix == ".java"]
    if java_paths:
        java_results = [r for r, p in zip(per_file, paths) if p.suffix == ".java"]
        try:
            all_edges.extend(_resolve_cross_file_java_imports(java_results, java_paths))
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Java cross-file import resolution failed, skipping: %s", exc)

    # Cross-file C# type-reference resolution: re-point dangling inherits/implements/
    # references edges left on shadow stubs, disambiguating same-named types by the
    # referencing file's `using` directives + enclosing namespace (mirrors Java #1318).
    _DOTNET_TYPE_EXTS = {".cs", ".razor", ".cshtml"}
    cs_paths = [p for p in paths if p.suffix.lower() in _DOTNET_TYPE_EXTS]
    if cs_paths:
        cs_results = [r for r, p in zip(per_file, paths) if p.suffix.lower() in _DOTNET_TYPE_EXTS]
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

    # Cross-file Bash source-backed call resolution: a call to a function defined
    # in a file this one `source`s is left unresolved by the per-file extractor
    # (it only links calls to same-file functions, #2141). Match each bash raw_call
    # against functions in the sourced files and emit the calls edge — scoped to
    # the source relationship, so a call to an external command never binds to a
    # same-named function in an unsourced file. Runs after the id-remap passes
    # above so caller_nids and function node ids are final; dedups the source
    # edge the extractor already emitted via existing_edges.
    # Selecting by filename suffix alone missed extensionless scripts:
    # _SHEBANG_DISPATCH routes a `#!/usr/bin/env bash` file with no extension to
    # extract_bash, so its functions get indexed, but a suffix-only filter left it
    # out of this pass and calls into it never resolved (#2171). Select by shape
    # too — the bash extractor tags every node it emits with
    # metadata.language == "bash" — while keeping the suffix check so an empty
    # .sh file (no nodes to inspect) still participates.
    def _looks_like_bash(result: object) -> bool:
        if not isinstance(result, dict):
            return False
        nodes = result.get("nodes")
        if not isinstance(nodes, list):
            return False
        for n in nodes:
            if not isinstance(n, dict):
                continue
            md = n.get("metadata")
            if isinstance(md, dict) and md.get("language") == "bash":
                return True
        return False

    sh_pairs = [
        (r, p) for r, p in zip(per_file, paths)
        if p.suffix in (".sh", ".bash") or _looks_like_bash(r)
    ]
    if sh_pairs:
        sh_results = [r for r, _ in sh_pairs]
        sh_paths = [p for _, p in sh_pairs]
        try:
            all_edges.extend(
                resolve_bash_source_edges(sh_results, sh_paths, root, existing_edges=all_edges)
            )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Bash cross-file call resolution failed, skipping: %s", exc)

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
    # #2406: on an incremental rebuild only the CHANGED files are parsed, so
    # `all_nodes` alone cannot see a callee that lives in an unchanged file and
    # every changed->unchanged DIRECT call silently vanished (while the file-level
    # `imports` edge survived, because the JS/Python symbol-resolution pass
    # reads the import TARGET off disk instead of off the node list). Extend the
    # resolution indexes — and ONLY the indexes — with the caller-supplied
    # unchanged-corpus nodes. Fresh nodes win on id collision, nothing is
    # appended to `all_nodes`, and raw_calls still come solely from `paths`, so
    # the emitted edges remain sourced by the re-extracted files.
    #
    # Scope: this list feeds the shared direct-call loop below, the
    # indirect_call callable guard (#2438, via the persisted `_callable` /
    # `_callable_class` markers), and — together with resolution_context_edges —
    # the member-call resolvers run by run_language_resolvers (#2437).
    resolution_nodes = all_nodes
    if resolution_context_nodes:
        _fresh_ids = {n["id"] for n in all_nodes}
        resolution_nodes = all_nodes + [
            n for n in resolution_context_nodes
            if n.get("id") and n["id"] not in _fresh_ids
        ]
    for n in resolution_nodes:
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
    # stale when node ids were relativized/disambiguated above (#1566). Read from
    # `resolution_nodes`, not `all_nodes` (#2438): an unchanged callee's context node
    # carries the marker persisted in graph.json, so an incremental rebuild keeps
    # resolving callbacks into unchanged files while data symbols stay excluded.
    callable_nids = {n["id"] for n in resolution_nodes if n.get("_callable")}
    # Class defs are callable only via their constructor; they are frequently passed
    # as descriptive values (`select(Model)`, exception tuples), not invoked. Exclude
    # them from the indirect_call guard below to avoid false edges (#2137).
    class_nids = {n["id"] for n in resolution_nodes if n.get("_callable_class")}

    # Kotlin import targets (#2526): rewrite each `imports` edge from the bare
    # last-segment id to the node its written FQN names, via the per-file
    # package declarations. Runs HERE — after the id-remap/disambiguation passes
    # (ids are final) but before the import-evidence index just below reads the
    # edges — so genuine imported calls get promoted INFERRED -> EXTRACTED. The
    # tail registry run (run_language_resolvers below) would be too late.
    run_language_resolvers(
        paths, per_file, all_nodes, all_edges,
        resolvers=[_KOTLIN_IMPORT_TARGET_RESOLVER],
    )

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
    for n in resolution_nodes:
        sf = n.get("source_file")
        if sf and n.get("label") == Path(str(sf)).name:
            sf_to_file_nid.setdefault(str(sf), n["id"])
    nid_to_file_nid: dict[str, str] = {}
    # nid -> raw source_file string, for the ambiguous-name tie-breakers below
    # (test/non-test classification + path proximity). Kept separate from the
    # file-node-id map because tie-breaking compares the actual file paths.
    nid_to_source_file: dict[str, str] = {}
    for n in resolution_nodes:
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
    _go_module_cache: dict[Path, str | None] = {}
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
        # Bash calls are resolved only by resolve_bash_source_edges (run above),
        # which scopes resolution to the files a script actually `source`s. The
        # global name match here would bind a bash call to any same-named function
        # in an unsourced file (an INFERRED phantom edge) and would resolve calls
        # to external commands that merely share a name with a function elsewhere
        # in the corpus — exactly what #2141 must not do.
        if rc.get("language") == "bash":
            continue
        # A Go predeclared function is never a cross-file call: the extractor
        # already drops bare `append(s, x)` (extractors/go.py), so this is the
        # backstop for Go raw_calls minted on any other path. Language-gated
        # rather than folded into _LANGUAGE_BUILTIN_GLOBALS because `new`,
        # `close` and `delete` are ordinary method names elsewhere (#2296).
        if rc.get("language") == "go" and callee in _GO_PREDECLARED_FUNCS:
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
        # Imported Go selectors carry exact package evidence. External package
        # calls yield no internal candidate instead of binding by bare name.
        go_exact_import = False
        if rc.get("language") == "go" and rc.get("import_path"):
            import_path = str(rc["import_path"])
            candidates = [
                candidate for candidate in candidates
                if _go_import_path_for_file(
                    nid_to_source_file.get(candidate, ""), root, _go_module_cache
                ) == import_path
            ]
            if not candidates:
                continue
            go_exact_import = True
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
            has_import_evidence = go_exact_import or _has_import_evidence(tgt)
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
            if tgt != caller and (caller, tgt) not in call_like_pairs and tgt in callable_nids and tgt not in class_nids:
                call_like_pairs.add((caller, tgt))
                all_edges.append({
                    "source": caller,
                    "target": tgt,
                    "relation": "indirect_call",
                    "context": rc.get("context", "argument"),
                    "confidence": "INFERRED",
                    # 0.85, not 0.8: the rubric in references/extraction-spec.md
                    # is a discrete set {0.55, 0.65, 0.75, 0.85, 0.95} and 0.8 is
                    # not in it. Same tier, same meaning ("strong inference"),
                    # now a value the documented scale actually contains (#2813).
                    "confidence_score": 0.85,
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
                # 0.85 rather than 0.8 — the rubric's INFERRED set is discrete
                # and does not contain 0.8 (#2813).
                confidence_score = 0.85
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
    #
    # #2437: on an incremental rebuild the resolvers must also see the unchanged
    # corpus — its nodes (types/methods, from resolution_nodes above) and its
    # persisted contains/method edges (resolution_context_edges) — or the
    # single-definition guards bail on every changed->unchanged member call. Run
    # them over SCRATCH lists that include the context, then keep only the fresh
    # results: raw_calls come solely from `paths`, so nothing sourced by an
    # unchanged file is ever emitted, and the ambiguity guards count the same
    # candidates a full build would (the context is the whole unchanged corpus).
    if resolution_context_nodes or resolution_context_edges:
        _rl_nodes = list(resolution_nodes)
        _rl_edges = all_edges + list(resolution_context_edges or [])
        _n0, _e0 = len(_rl_nodes), len(_rl_edges)
        run_language_resolvers(paths, per_file, _rl_nodes, _rl_edges)
        all_nodes.extend(_rl_nodes[_n0:])
        all_edges.extend(_rl_edges[_e0:])
    else:
        run_language_resolvers(paths, per_file, all_nodes, all_edges)

    # Relativize source_file fields so paths are portable across machines (#555).
    # When the node's id was itself minted from the absolute path, remap it to a
    # portable id and rewrite the edge endpoints that reference it.
    # ``_portable_out_of_root_sf`` is defined above, by ``id_remap`` (#2243).
    ext_id_remap: dict[str, str] = {}
    # General backstop closing the absolute-id leak CLASS (#2231/#2243): any
    # producer that minted an id or edge endpoint as _make_id(<absolute path>)
    # and was reached by no earlier remap (module-top-level raw_calls before
    # #2231, unstamped edges, regex-rescue stubs #2195, ...) still leaks the
    # machine/scan-path slug here. Instead of pattern-matching only the item's
    # OWN id, LEARN the absolute-derived key forms (as-written and resolved)
    # of every file that appears in the batch from the nodes' source_file, map
    # them to the file's canonical id — _file_node_id(rel) in-root, the
    # #1899/#2250 "ext" recipe out-of-root — and rewrite every node id and
    # edge endpoint through that map. Only absolute-derived ids are renamed to
    # their canonical form; a key already owned by a real (differently-minted)
    # node is never remapped, so no edge is fabricated toward a node it did
    # not already reference.
    owned_ids = {n.get("id") for n in all_nodes}
    # sf string -> (relativized source_file, canonical id, absolute-derived
    # key forms). Cached so the path work (resolve() hits the filesystem)
    # runs once per file, not once per node.
    _sf_forms: dict[str, tuple[str, str, tuple[str, ...]]] = {}

    def _sf_entry(sf: str, sf_path: Path) -> tuple[str, str, tuple[str, ...]]:
        cached = _sf_forms.get(sf)
        if cached is not None:
            return cached
        try:
            rel = sf_path.relative_to(root)
        except ValueError:
            portable = _portable_out_of_root_sf(sf_path)
            canonical_id = _make_id("ext", portable)
            new_sf = portable
        else:
            # In-root: the same canonical repo-relative form the real file
            # node uses (_file_node_id), so the scan root can never leak into
            # a persisted id. Real file nodes were already remapped by the
            # #2169 pass, so only leftover absolute-derived ids match below
            # (belt-and-braces for #2195 regex-rescue stubs and friends).
            canonical_id = _file_node_id(rel)
            new_sf = rel.as_posix()
        try:
            sf_resolved = sf_path.resolve()
        except (OSError, RuntimeError):
            sf_resolved = sf_path
        # Learn the STEM (extension-dropped) forms too: symbol producers mint
        # compound ids as _make_id(_file_stem(path), name), so a node-less
        # absolute-derived endpoint arrives as <stem-key>_<symbol> and only
        # the stem prefix can identify the file it came from (#2262).
        keys = tuple({
            _make_id(str(sf_path)),
            _make_id(str(sf_resolved)),
            _make_id(_file_stem(sf_path)),
            _make_id(_file_stem(sf_resolved)),
        })
        entry = (new_sf, canonical_id, keys)
        _sf_forms[sf] = entry
        return entry

    for item in all_nodes + all_edges:
        sf = item.get("source_file")
        if sf:
            sf_path = Path(sf)
            if sf_path.is_absolute():
                new_sf, canonical_id, keys = _sf_entry(str(sf), sf_path)
                if "id" in item:
                    for key in keys:
                        if key == canonical_id or key in ext_id_remap:
                            continue
                        if key in owned_ids and item.get("id") != key:
                            # The key is a real node's id minted some other way —
                            # renaming it (or edges onto it) would corrupt the graph.
                            # The node that owns it registers it itself when its own
                            # id IS the absolute-derived form (#2195 stub).
                            continue
                        ext_id_remap[key] = canonical_id
                item["source_file"] = new_sf
            elif "\\" in sf:
                # No id remap needed here (an id is minted independently of
                # this string), but the raw source_file itself can still
                # carry a native `\` separator on Windows — every extractor
                # sets it via plain str(path), and only this absolute branch
                # runs it through as_posix(). A relative path caller (the
                # documented extract(paths) entry point with no root, or
                # python -m graphify.extract <file>...) got whichever
                # separator convention that one extractor happened to use,
                # diverging from the canonical POSIX form every other path
                # (explicit root, the CLI, which always passes one) produces.
                # That fragments string equality lookups keyed on
                # source_file (build._norm_source_file,
                # analyze.find_import_cycles, the semantic cache key) into
                # two spellings of one file (#2625).
                item["source_file"] = sf.replace("\\", "/")
        df = item.get("definition_file")
        if df:
            df_path = Path(df)
            if df_path.is_absolute():
                new_df, _, _ = _sf_entry(str(df), df_path)
                item["definition_file"] = new_df

    if ext_id_remap:
        # Bash entrypoint ids are the file-level id + "__entry"
        # (extractors/bash.py); rewrite the suffixed form of any learned key
        # the same way so a script-invocation endpoint can't keep the slug.
        _ENTRY = "__entry"

        def _canon(nid: str) -> str:
            if nid in ext_id_remap:
                return ext_id_remap[nid]
            if nid.endswith(_ENTRY) and nid[: -len(_ENTRY)] in ext_id_remap:
                return ext_id_remap[nid[: -len(_ENTRY)]] + _ENTRY
            if nid not in owned_ids:
                # Node-less suffixed-compound endpoint (#2262): an id minted
                # as _make_id(<absolute stem>, <symbol>) by a producer that
                # never materialized the node. No node ever registers it, so
                # rewrite by longest learned prefix: the endpoint stays
                # dangling (no node is fabricated) but becomes
                # machine-portable. Ids owned by real nodes are never
                # touched (guard above), and only absolute-path-derived
                # prefixes are in ext_id_remap, so ordinary ids can't match.
                idx = nid.rfind("_")
                while idx > 0:
                    canonical = ext_id_remap.get(nid[:idx])
                    if canonical is not None:
                        return canonical + nid[idx:]
                    idx = nid.rfind("_", 0, idx)
            return nid

        for n in all_nodes:
            if n.get("id"):
                n["id"] = _canon(n["id"])
        for e in all_edges:
            if e.get("source"):
                e["source"] = _canon(e["source"])
            if e.get("target"):
                e["target"] = _canon(e["target"])

    # origin_file is an internal disambiguation hint (#1462): the colliding-id pass
    # above reads it to keep same-named cross-file stubs distinct, after which nothing
    # consumes it. Drop it from the returned nodes so it never ships into graph.json as
    # an absolute, machine-specific path — the same "no absolute paths in output"
    # contract that relativizes source_file just above (#555, #932). The per-file AST
    # cache keeps its own copy, which is what the colliding-id pass reads on a cache hit.
    for n in all_nodes:
        n.pop("origin_file", None)
    # `_callable` / `_callable_class` are deliberately NOT popped (#2438): they
    # persist into graph.json — the same underscore-provenance precedent as
    # `_origin` below — so an incremental rebuild can hand them back as
    # resolution context and the indirect_call callable guard keeps working for
    # targets in unchanged files. Callability is never inferred from a persisted
    # label (that would reintroduce the #1566/#2137 data-symbol false positives);
    # a graph written before the markers existed simply fails closed until its
    # files are re-extracted.

    # local_alias is a transient import-resolution hint (#2082), same shape as
    # target_file (#1814): it exists only so the module arm of
    # _resolve_python_member_calls (run above via run_language_resolvers) can
    # match an aliased receiver against the import edge it came from. Nothing
    # reads it after that pass runs, so drop it here rather than let an internal
    # local variable name ship into graph.json. Popped post-resolution, unlike
    # target_file (which _disambiguate_colliding_node_ids pops earlier in the
    # pipeline) — local_alias must survive until run_language_resolvers has run,
    # so it cannot be popped at that earlier point without breaking the fix.
    for e in all_edges:
        e.pop("local_alias", None)

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

    # Canonicalize source_file to POSIX on every node AND edge (#2625).
    #
    # Extractors build source_file from the Path they were handed, so a run
    # given RELATIVE inputs keeps the native separator on Windows. Only the
    # relativizing branch of _sf_entry above ever calls as_posix(), so a single
    # extraction could emit `src\lib\content.ts` and `src/pages/index.astro`
    # side by side. source_file is compared as a STRING downstream
    # (build._norm_source_file keying, _derive_prune_root, dedup, and
    # analyze.find_import_cycles, which matches an edge's source_file against a
    # node's by equality), so two spellings are two different files — the
    # fragmentation of #683, and the reason the CLI path (which passes an
    # explicit root) looked correct while the library entry point did not.
    #
    # Safe as a final pass: ids are minted through make_id, which collapses
    # every non-word character — `\` and `/` alike — to `_`, so canonicalizing
    # the separator here cannot desync an id from its source_file.
    #
    # PurePath is the NATIVE flavour on purpose: on POSIX a backslash is a legal
    # filename character and must be left alone, so this only rewrites paths on
    # the platform where `\` is actually a separator.
    for _item in (*all_nodes, *all_edges):
        _sf = _item.get("source_file")
        if _sf and "\\" in str(_sf):
            _item["source_file"] = PurePath(_sf).as_posix()
        _df = _item.get("definition_file")
        if _df and "\\" in str(_df):
            _item["definition_file"] = PurePath(_df).as_posix()

    return {
        "nodes": all_nodes,
        "edges": all_edges,
        "input_tokens": 0,
        "output_tokens": 0,
        # Surfaces failed/empty AST sources to the CLI so the incremental
        # manifest does not freeze them as processed (#2543). Callers that
        # only read nodes/edges ignore this key.
        "failed_sources": _failed_sources,
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
                if not _is_noise_dir(d, dp)  # pass parent so "env"/"*_env" is marker-gated (#2058)
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
            if not _is_noise_dir(d, dp)  # pass parent so "env"/"*_env" is marker-gated (#2058)
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
