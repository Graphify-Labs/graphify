"""JS extractor. Moved verbatim from graphify/extract.py."""
from __future__ import annotations

import os
import re
from pathlib import Path

from graphify.extractors.models import LanguageConfig
from graphify.extractors.engine import _extract_generic
from graphify.extractors.base import _make_id, _file_stem, _read_text, _shorten_rationale_label
from graphify.extractors.resolution import (
    _resolve_js_import_target,
    _resolve_js_module_path,
    _resolve_tsconfig_alias,
    _load_tsconfig_aliases,
    _load_tsconfig_base_url,
)


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
        if "import(" not in src:  # cheap bail — most files have none
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
            r"""(?<!\w)import\(\s*(?:'([^'\n]+)'|"([^"\n]+)"|`([^`$\n]+)`)\s*\)""",
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
        _rescue_js_dynamic_imports(path, result)
    return result
