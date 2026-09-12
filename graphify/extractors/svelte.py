"""Svelte 5 extractor for Graphify (Airpipe fork).

Replaces the stock ``extract_svelte`` in ``graphify/extract.py``, which fed the
WHOLE ``.svelte`` file to the tree-sitter-javascript parser. Svelte markup is not
valid JS, so the parse produced a top-level ERROR node, no declaration was ever
reached, and a 280-line component collapsed into a single file node (measured
baseline on airpipe-web: 2.79 nodes per .svelte file, and those were almost all
import stubs — the real symbol count was ~0).

Design (v1), after review by Grok 4.5 and Kimi k3:

* **Region scanner, not a naive regex split.** ``<script>``/``<style>`` are HTML
  raw-text elements, so their content genuinely ends at the first ``</script``.
  The hard part is finding the OPENING tag without being fooled by HTML comments
  or quoted attribute values, so :func:`_scan_regions` is a real scanner.
* **Script blocks are parsed with tree-sitter-typescript** at their true byte
  offset, so every reported line number points at the original file.
* **Only declarations that are named and referable become nodes.** Both reviewers
  independently warned that node count is the wrong KPI and that emitting a node
  per ``const x = 1`` makes the graph worse. Scalar locals, loop variables and
  anonymous ``$effect`` callbacks are therefore NOT nodes; the calls made inside
  an ``$effect`` body are attributed to the component instead, which keeps the
  information without the anonymous noise.
* **Rune variants are attributes, not node types** (``$state.raw`` and ``$state``
  are one kind with ``rune`` recording the exact form), so the graph does not
  fragment across spellings.
* **Component usage edges use relation ``uses``**, not ``renders``. This is not
  cosmetic: ``affected.DEFAULT_AFFECTED_RELATIONS`` does not contain ``renders``,
  so a ``renders`` edge would be invisible to ``graphify affected`` — the single
  most important query for a frontend graph. The semantics survive in
  ``context`` (``renders`` / ``renders_dynamic``).

Known and deliberate limits (documented, not hidden):

* Dynamic components (``<svelte:component this={X}>``, ``<Foo />`` where ``Foo``
  is a variable) are emitted with ``confidence: "INFERRED"`` and context
  ``renders_dynamic``.
* Template call detection resolves an identifier ONLY when it matches a symbol
  declared or imported in the same file. That trades recall for precision: an
  unknown name is dropped rather than guessed.
* No cross-repo / HTTP-boundary edges. A ``fetch('/api/...')`` in a component is
  not linked to the backend route that serves it.
"""
from __future__ import annotations

import re
from pathlib import Path

from graphify.extractors.base import (
    _LANGUAGE_BUILTIN_GLOBALS,
    _file_stem,
    _make_id,
    _read_text,
)
from graphify.extractors.resolution import _resolve_js_import_target

EXTRACTOR_VERSION = "airpipe-svelte-1.1.0"

# Runes that BIND a value to a name. The dict maps the callee text to the node
# kind; the exact spelling is kept on the node as `rune` so `$state` and
# `$state.raw` stay one kind instead of fragmenting the graph (Kimi #5).
_BINDING_RUNES = {
    "$state": "state",
    "$state.raw": "state",
    "$derived": "derived",
    "$derived.by": "derived",
    "$props": "props",
    "$props.id": "state",
    "$bindable": "state",
}

# Runes that are statements rather than bindings. Their bodies are walked for
# calls (attributed to the component) but they do NOT become nodes: both
# reviewers flagged anonymous effect nodes as pure noise.
_STATEMENT_RUNES = {"$effect", "$effect.pre", "$effect.root", "$effect.tracking", "$inspect"}

# Svelte template block keywords and special elements — never component targets.
_TEMPLATE_KEYWORDS = frozenset({
    "if", "else", "each", "await", "then", "catch", "key", "snippet",
    "render", "const", "html", "debug", "attach",
})

_SVELTE_SPECIAL = frozenset({
    "svelte:head", "svelte:window", "svelte:document", "svelte:body",
    "svelte:options", "svelte:fragment", "svelte:boundary", "svelte:self",
    "svelte:element",
})

_IDENT_CALL_RE = re.compile(r"(?<![\w$.])([A-Za-z_$][\w$]*)\s*\(")
_SNIPPET_RE = re.compile(r"\{\s*#snippet\s+([A-Za-z_$][\w$]*)\s*\(")
_RENDER_RE = re.compile(r"\{\s*@render\s+([A-Za-z_$][\w$]*)")
_DYNAMIC_THIS_RE = re.compile(r"this\s*=\s*\{\s*([A-Za-z_$][\w$]*)")
_DYNAMIC_IMPORT_RE = re.compile(r"""import\(\s*['"]([^'"]+)['"]\s*\)""")


# ── region scanning ───────────────────────────────────────────────────────────

def _scan_regions(src: str) -> tuple[list[dict], str]:
    """Split a .svelte source into script regions plus a masked template.

    Returns ``(scripts, template)`` where each script is
    ``{"start", "end", "attrs", "module"}`` (byte-equivalent character offsets of
    the CONTENT, not the tags) and ``template`` is ``src`` with every script,
    style and comment region replaced by spaces of identical length — so offsets
    into ``template`` are still valid offsets into ``src``.

    A scanner rather than a regex, because ``<!-- <script> -->`` and
    ``attr="<script>"`` both defeat the naive pattern (Grok a.1, Kimi 3).
    """
    scripts: list[dict] = []
    mask = list(src)
    i = 0
    n = len(src)

    def blank(start: int, end: int) -> None:
        for k in range(start, min(end, n)):
            if mask[k] not in "\n\r":
                mask[k] = " "

    while i < n:
        ch = src[i]
        if ch != "<":
            i += 1
            continue
        # HTML comment — skip wholesale so tags inside it are never seen.
        if src.startswith("<!--", i):
            end = src.find("-->", i + 4)
            end = n if end == -1 else end + 3
            blank(i, end)
            i = end
            continue
        m = re.match(r"<\s*(script|style)\b", src[i:], re.IGNORECASE)
        if not m:
            i += 1
            continue
        kind = m.group(1).lower()
        # Walk the opening tag to its '>', respecting quoted attribute values so
        # a '>' inside an attribute does not close the tag early.
        j = i + m.end() - 1
        quote = ""
        while j < n:
            c = src[j]
            if quote:
                if c == quote:
                    quote = ""
            elif c in "\"'":
                quote = c
            elif c == ">":
                break
            j += 1
        if j >= n:
            break
        open_tag = src[i:j + 1]
        if open_tag.rstrip().endswith("/>"):  # self-closing, no content
            blank(i, j + 1)
            i = j + 1
            continue
        content_start = j + 1
        close = re.compile(r"</\s*" + kind + r"\s*>", re.IGNORECASE).search(src, content_start)
        content_end = close.start() if close else n
        region_end = close.end() if close else n
        if kind == "script":
            attrs = open_tag
            is_module = bool(
                re.search(r"\bmodule\b", attrs)
                or re.search(r"context\s*=\s*[\"']module[\"']", attrs)
            )
            scripts.append({
                "start": content_start,
                "end": content_end,
                "attrs": attrs,
                "module": is_module,
            })
        blank(i, region_end)
        i = region_end

    return scripts, "".join(mask)


# ── script parsing ────────────────────────────────────────────────────────────

def _ts_parser():
    import tree_sitter_typescript as tsts
    from tree_sitter import Language, Parser

    return Parser(Language(tsts.language_typescript()))


def _callee_text(call_node, source: bytes) -> str:
    fn = call_node.child_by_field_name("function")
    return _read_text(fn, source) if fn is not None else ""


def _pattern_names(node, source: bytes) -> list[str]:
    """Collect bound names from a destructuring pattern (object or array)."""
    out: list[str] = []
    if node is None:
        return out
    t = node.type
    if t in ("identifier", "shorthand_property_identifier_pattern"):
        out.append(_read_text(node, source))
        return out
    if t == "rest_pattern":
        for c in node.children:
            if c.is_named:
                out.extend(_pattern_names(c, source))
        return out
    if t in ("object_assignment_pattern", "assignment_pattern"):
        left = node.child_by_field_name("left") or (
            node.children[0] if node.children else None
        )
        out.extend(_pattern_names(left, source))
        return out
    if t == "pair_pattern":
        value = node.child_by_field_name("value")
        out.extend(_pattern_names(value, source))
        return out
    if t in ("object_pattern", "array_pattern"):
        for c in node.children:
            if c.is_named:
                out.extend(_pattern_names(c, source))
        return out
    return out


def _prop_entries(node, source: bytes) -> list[tuple[str, str]]:
    """Collect ``(public_name, local_name)`` pairs from a ``$props()`` pattern.

    A renamed prop (``let { class: className } = $props()``) exposes ``class`` as
    the component's public API while the script refers to ``className``. The node
    must be labelled with the public name — that is what a caller writes — so the
    two names are tracked separately.
    """
    out: list[tuple[str, str]] = []
    if node is None or node.type != "object_pattern":
        return [(n, n) for n in _pattern_names(node, source)]
    for c in node.children:
        if not c.is_named:
            continue
        if c.type == "pair_pattern":
            key = c.child_by_field_name("key")
            value = c.child_by_field_name("value")
            public = _read_text(key, source) if key is not None else None
            if public:
                # A hyphenated prop must be written as a quoted key
                # (`"data-slot": slot`). The prop is named data-slot; the quotes
                # are syntax, not part of the name.
                public = public.strip("\"'`")
            locals_ = _pattern_names(value, source)
            if public:
                out.append((public, locals_[0] if locals_ else public))
            continue
        for n in _pattern_names(c, source):
            out.append((n, n))
    return out


def extract_svelte(path: Path) -> dict:
    """Extract components, props, runes, functions, snippets and usage from .svelte."""
    try:
        parser = _ts_parser()
    except Exception as e:  # pragma: no cover - dependency guard
        return {"nodes": [], "edges": [], "error": f"tree-sitter-typescript unavailable: {e}"}

    try:
        raw_src = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:  # pragma: no cover
        return {"nodes": [], "edges": [], "error": str(e)}

    str_path = str(path)
    stem = _file_stem(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()
    raw_calls: list[dict] = []

    # local name -> node id, for resolving template/script references
    symbols: dict[str, str] = {}
    # local name -> (module specifier, target node id, resolved path, exported name)
    # The exported name differs from the local one for aliased imports
    # (`import { formatOre as fmt }`) and is what the DEFINING file named its
    # node, so it is what a symbol-level edge must target.
    imported: dict[str, tuple[str, str, "Path | None", "str | None"]] = {}

    def symbol_target(local_name: str) -> "tuple[str, str] | None":
        """Symbol-level target for an imported callee: (node_id, target_file).

        A bare callee name cannot be resolved across the corpus — this repo has
        eleven distinct `formatOre()` definitions — but the import statement says
        exactly which module this one came from. Symbol node ids are
        `make_id(<file stem>, <name>)` across every extractor, so the id can be
        reconstructed. A wrong guess simply dangles and is dropped at build time,
        while the file-level `imports_from` edge still records the dependency.
        """
        entry = imported.get(local_name)
        if entry is None:
            return None
        _spec, _nid, tpath, exported = entry
        if tpath is None or not exported:
            return None
        return _make_id(_file_stem(tpath), exported), str(tpath)

    def add_node(nid: str, label: str, line: int, kind: str, **extra) -> None:
        if nid in seen_ids:
            return
        seen_ids.add(nid)
        node = {
            "id": nid,
            "label": label,
            "file_type": "code",
            "source_file": str_path,
            "source_location": f"L{line}",
            "kind": kind,
        }
        node.update({k: v for k, v in extra.items() if v is not None})
        nodes.append(node)

    def add_edge(src: str, tgt: str, relation: str, line: int, *,
                 context: str | None = None, confidence: str = "EXTRACTED",
                 target_file: str | None = None) -> None:
        edge = {
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": confidence,
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": 1.0,
        }
        if context:
            edge["context"] = context
        if target_file:
            edge["target_file"] = target_file
        edges.append(edge)

    file_nid = _make_id(str_path)
    component_name = path.stem
    add_node(file_nid, path.name, 1, "component", component=component_name)

    # nid -> (name, kind) of whichever declaration claimed it first, so a
    # case-collision can be detected rather than silently dropping a symbol.
    owned: dict[str, tuple[str, str]] = {}

    def declare(name: str, line: int, kind: str, label: str | None = None,
                local: str | None = None, **extra) -> str:
        # graphify's make_id CASEFOLDS, so `type State` and `let state` in the
        # same file both hash to ...\_state and the second declaration would be
        # swallowed by add_node's seen_ids guard — a silent symbol loss, not a
        # merge. Disambiguate with the kind when a different symbol owns the id.
        nid = _make_id(stem, name)
        if owned.get(nid, (name, kind)) != (name, kind):
            nid = _make_id(stem, name, kind)
        owned.setdefault(nid, (name, kind))
        add_node(nid, label or name, line, kind, **extra)
        add_edge(file_nid, nid, "contains", line, context=kind)
        # The template/script refer to the LOCAL binding (`class: className` is
        # used as `className`), while the node is labelled with the public name.
        symbols.setdefault(local or name, nid)
        return nid

    scripts, template = _scan_regions(raw_src)

    # Function bodies to sweep for calls, as (owner_nid, node, source_bytes).
    # (owner, node, source, line_offset). The offset is essential: tree-sitter
    # line numbers are relative to the SCRIPT BLOCK, and a file with a
    # `<script module>` block first puts the instance script several lines down.
    # Without it every call site in such a file is reported at the wrong line.
    bodies: list[tuple[str, object, bytes, int]] = []

    for block in scripts:
        body_text = raw_src[block["start"]:block["end"]]
        source = body_text.encode("utf-8")
        # Line offset so reported lines refer to the ORIGINAL file.
        line_offset = raw_src.count("\n", 0, block["start"])
        scope = "module" if block["module"] else "instance"
        try:
            root = parser.parse(source).root_node
        except Exception:
            continue

        def L(node) -> int:
            return node.start_point[0] + 1 + line_offset

        def handle_import(node) -> None:
            src_node = node.child_by_field_name("source")
            if src_node is None:
                return
            spec = _read_text(src_node, source).strip("'\"`")
            if not spec:
                return
            resolved = _resolve_js_import_target(spec, str_path)
            if resolved is None:
                return
            target_nid, target_path = resolved
            add_edge(
                file_nid, target_nid, "imports_from", L(node), context="import",
                target_file=str(target_path) if target_path is not None else None,
            )
            # Map every local binding to the module so template usage of an
            # aliased import (`import { Foo as Bar }`) still resolves (Kimi 3).
            for child in node.children:
                if child.type != "import_clause":
                    continue
                for c in child.children:
                    # Default and namespace imports carry no exported symbol name
                    # that maps to a node in the target file, so they stay
                    # file-level (exported name = None).
                    if c.type == "identifier":  # default import
                        imported[_read_text(c, source)] = (spec, target_nid, target_path, None)
                    elif c.type == "namespace_import":
                        for nc in c.children:
                            if nc.type == "identifier":
                                imported[_read_text(nc, source)] = (spec, target_nid, target_path, None)
                    elif c.type == "named_imports":
                        for spec_node in c.children:
                            if spec_node.type != "import_specifier":
                                continue
                            alias = spec_node.child_by_field_name("alias")
                            name_node = spec_node.child_by_field_name("name")
                            local = alias if alias is not None else name_node
                            if local is not None and name_node is not None:
                                imported[_read_text(local, source)] = (
                                    spec, target_nid, target_path,
                                    _read_text(name_node, source),
                                )

        def handle_declarator(dec, exported: bool, kw: str) -> None:
            name_node = dec.child_by_field_name("name")
            value = dec.child_by_field_name("value")
            if name_node is None:
                return
            callee = _callee_text(value, source) if (
                value is not None and value.type == "call_expression"
            ) else ""

            # let { a, b } = $props()  →  one node per prop (the component API).
            if name_node.type == "object_pattern" and callee == "$props":
                for public, local in _prop_entries(name_node, source):
                    declare(public, L(dec), "prop", scope=scope, rune="$props",
                            local=local,
                            local_name=local if local != public else None)
                return

            rune_kind = _BINDING_RUNES.get(callee)
            if name_node.type == "identifier":
                nm = _read_text(name_node, source)
                if rune_kind:
                    declare(nm, L(dec), rune_kind, scope=scope, rune=callee,
                            exported=exported or None)
                elif value is not None and value.type in (
                    "arrow_function", "function_expression", "function",
                ):
                    nid = declare(nm, L(dec), "function", label=f"{nm}()",
                                  scope=scope, exported=exported or None)
                    bodies.append((nid, value, source, line_offset))
                elif exported:
                    # Only exported plain values are worth a node; local scalars
                    # are the noise both reviewers told us to skip.
                    declare(nm, L(dec), "constant", scope=scope, exported=True)
                else:
                    # Not a node, but still referable in the template — bind the
                    # name to the component so template calls have an anchor.
                    symbols.setdefault(nm, file_nid)
                return

            # Destructured runes: `let { a, b } = $derived(...)`.
            if rune_kind and name_node.type in ("object_pattern", "array_pattern"):
                for pname in _pattern_names(name_node, source):
                    declare(pname, L(dec), rune_kind, scope=scope, rune=callee)

        def walk_top(node, exported: bool = False) -> None:
            t = node.type
            if t == "import_statement":
                handle_import(node)
                return
            if t == "export_statement":
                decl = node.child_by_field_name("declaration")
                if decl is not None:
                    walk_top(decl, exported=True)
                return
            if t == "function_declaration":
                nm_node = node.child_by_field_name("name")
                if nm_node is not None:
                    nm = _read_text(nm_node, source)
                    nid = declare(nm, L(node), "function", label=f"{nm}()",
                                  scope=scope, exported=exported or None)
                    body = node.child_by_field_name("body")
                    if body is not None:
                        bodies.append((nid, body, source, line_offset))
                return
            if t == "class_declaration":
                nm_node = node.child_by_field_name("name")
                if nm_node is not None:
                    declare(_read_text(nm_node, source), L(node), "class",
                            scope=scope, exported=exported or None)
                return
            if t in ("lexical_declaration", "variable_declaration"):
                kw = _read_text(node.children[0], source) if node.children else "let"
                for dec in node.children:
                    if dec.type == "variable_declarator":
                        handle_declarator(dec, exported, kw)
                return
            if t in ("interface_declaration", "type_alias_declaration", "enum_declaration"):
                nm_node = node.child_by_field_name("name")
                if nm_node is not None:
                    declare(_read_text(nm_node, source), L(node), "type",
                            scope=scope, exported=exported or None)
                return
            if t == "expression_statement":
                # Top-level `$effect(() => ...)`: no node (anonymous = noise), but
                # sweep the body so what the effect DOES still reaches the graph.
                child = node.children[0] if node.children else None
                if child is not None and child.type == "call_expression":
                    if _callee_text(child, source) in _STATEMENT_RUNES:
                        bodies.append((file_nid, child, source, line_offset))
                return

        for child in root.children:
            walk_top(child)

    # ── template pass ─────────────────────────────────────────────────────────
    def line_of(pos: int) -> int:
        return raw_src.count("\n", 0, pos) + 1

    # Snippets are declarations, so register them before resolving {@render}.
    snippet_names: set[str] = set()
    for m in _SNIPPET_RE.finditer(template):
        name = m.group(1)
        snippet_names.add(name)
        declare(name, line_of(m.start()), "snippet", label=f"{name}()")

    def component_target(root_name: str) -> tuple[str, str, str] | None:
        """Resolve a template identifier to (target_nid, context, confidence)."""
        if root_name in imported:
            _spec, target_nid, _p, _exported = imported[root_name]
            return target_nid, "renders", "EXTRACTED"
        if root_name in symbols:
            # A prop or local holding a component — real, but not statically a file.
            return symbols[root_name], "renders_dynamic", "INFERRED"
        return None

    seen_uses: set[tuple[str, str]] = set()

    def emit_use(root_name: str, pos: int, context: str | None = None) -> None:
        hit = component_target(root_name)
        if hit is None:
            return
        target_nid, ctx, conf = hit
        if target_nid == file_nid and root_name not in imported:
            # A local that is not a component resolved back to the component
            # node — no information, drop it. A genuine self-import is different:
            # `import Self from './ChainTree.svelte'` used as `<Self />` is a
            # RECURSIVE component, and the self-edge is exactly what records that.
            return
        # Dedupe per (target, context, IDENTIFIER). Keying on the target alone
        # collapses distinct components that share a barrel module — `Alert`,
        # `AlertTitle` and `AlertDescription` all resolve to alert/index.js, so
        # only the first would ever be recorded.
        key = (target_nid, context or ctx, root_name)
        if key in seen_uses:
            return
        seen_uses.add(key)
        target_file = None
        if root_name in imported and imported[root_name][2] is not None:
            target_file = str(imported[root_name][2])
        edge_line = line_of(pos)
        add_edge(file_nid, target_nid, "uses", edge_line,
                 context=context or ctx, confidence=conf, target_file=target_file)
        # Record the identifier as written in the template. `<Table.Root>` resolves
        # to a file whose stem is `index`, so without this the edge cannot be
        # traced back to the name a reader actually sees.
        edges[-1]["symbol"] = root_name

    # Brace depth per offset. Inside a `{...}` expression a `<` is the less-than
    # OPERATOR, not a tag: `{#if i < railSteps.length}` otherwise reads as a
    # component named `railSteps.length`. Svelte block tags open and close their
    # own brace, so real markup always sits at depth 0.
    # Plain brace counting, deliberately NOT string- or comment-aware.
    #
    # A lexer that skips strings and comments inside expressions sounds more
    # correct and measures worse. Its mistakes are not local: one miscount pins
    # the depth above zero and silently drops every remaining component in the
    # file. Real templates break it constantly — an apostrophe in markup text
    # (`Don't`), an apostrophe inside a comment within an expression
    # (`class={cn('x', // the CRM's own scope`), or a regex literal whose escaped
    # slashes read as a comment (`replace(/^https?:\/\//, '')`).
    #
    # Counting braces alone can only be fooled by a brace inside a string, whose
    # cost is one local misjudgement. Measured over 455 real components across
    # two apps: naive counting balanced in every single file; the lexer did not.
    depth_at: list[int] = []
    depth = 0
    for ch in template:
        depth_at.append(depth)
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
    # Self-check: if the braces do not balance, this file contains something the
    # counter cannot account for. Skipping tags on a wrong depth would drop real
    # components, so drop the filter instead and accept the rarer false positive.
    if depth != 0:
        depth_at = [0] * len(template)

    # Component tags: PascalCase or dotted namespaces (`<Table.Root>`), plus the
    # deprecated `<svelte:component this={X}>`.
    for m in re.finditer(r"<\s*([A-Za-z_$][\w$]*(?:\.[\w$]+)*|svelte:component)", template):
        if depth_at[m.start()] > 0:
            continue
        tag = m.group(1)
        if tag in _SVELTE_SPECIAL:
            continue
        if tag == "svelte:component":
            tail = template[m.end():m.end() + 400]
            dm = _DYNAMIC_THIS_RE.search(tail)
            if dm:
                emit_use(dm.group(1), m.start(), context="renders_dynamic")
            continue
        root_name = tag.split(".")[0]
        # Lowercase, undotted tags are intrinsic HTML elements.
        if "." not in tag and not root_name[:1].isupper():
            continue
        emit_use(root_name, m.start())

    # {@render snippet()} — snippet invocation, and prop-passed children.
    for m in _RENDER_RE.finditer(template):
        name = m.group(1)
        if name in symbols and symbols[name] != file_nid:
            add_edge(file_nid, symbols[name], "calls", line_of(m.start()),
                     context="render_snippet")

    # Calls in template expressions: resolved ONLY against names this file
    # declares or imports, so an unknown identifier is dropped, never guessed.
    seen_tpl_calls: set[str] = set()
    for m in _IDENT_CALL_RE.finditer(template):
        name = m.group(1)
        if name in _TEMPLATE_KEYWORDS or name in _LANGUAGE_BUILTIN_GLOBALS:
            continue
        # `{#snippet foo(...)}` is a DEFINITION, not a call site — the invocation
        # is already covered by the `{@render foo(...)}` pass above.
        if name in snippet_names:
            continue
        if name in seen_tpl_calls:
            continue
        target = symbols.get(name)
        if target is not None and target != file_nid:
            seen_tpl_calls.add(name)
            add_edge(file_nid, target, "calls", line_of(m.start()),
                     context="template_call")
        elif name in imported:
            seen_tpl_calls.add(name)
            sym = symbol_target(name)
            if sym is not None:
                add_edge(file_nid, sym[0], "calls", line_of(m.start()),
                         context="template_call", target_file=sym[1])
            else:
                spec, target_nid, tpath, _exported = imported[name]
                add_edge(file_nid, target_nid, "calls", line_of(m.start()),
                         context="template_call",
                         target_file=str(tpath) if tpath is not None else None)

    # ── dynamic imports ───────────────────────────────────────────────────────
    # `import('./X.svelte')` is how SvelteKit lazy-loads, and it appears both in
    # script bodies (nested inside functions, so a top-level walk misses it) and
    # in markup like `{#await import('./X.svelte')}`, which no JS parser sees at
    # all. Scanned over the RAW source for that reason. Relation name kept as
    # upstream's `dynamic_import` for compatibility.
    seen_dynamic: set[str] = set()
    for m in _DYNAMIC_IMPORT_RE.finditer(raw_src):
        spec = m.group(1)
        if not spec or spec in seen_dynamic:
            continue
        seen_dynamic.add(spec)
        resolved = _resolve_js_import_target(spec, str_path)
        if resolved is None:
            continue
        target_nid, target_path = resolved
        add_edge(file_nid, target_nid, "dynamic_import", line_of(m.start()),
                 context="import",
                 target_file=str(target_path) if target_path is not None else None)

    # ── call sweep inside function bodies ─────────────────────────────────────
    seen_call_pairs: set[tuple[str, str]] = set()

    def walk_calls(node, owner_nid: str, source: bytes, line_offset: int = 0) -> None:
        if node.type == "call_expression":
            fn = node.child_by_field_name("function")
            callee = None
            is_member = False
            if fn is not None:
                if fn.type == "identifier":
                    callee = _read_text(fn, source)
                elif fn.type == "member_expression":
                    prop = fn.child_by_field_name("property")
                    obj = fn.child_by_field_name("object")
                    obj_txt = _read_text(obj, source) if obj is not None else ""
                    is_member = obj_txt not in imported
                    if prop is not None:
                        callee = _read_text(prop, source)
            if callee and callee not in _LANGUAGE_BUILTIN_GLOBALS:
                target = symbols.get(callee)
                if target is not None and target != owner_nid and target != file_nid:
                    pair = (owner_nid, target)
                    if pair not in seen_call_pairs:
                        seen_call_pairs.add(pair)
                        edges.append({
                            "source": owner_nid, "target": target, "relation": "calls",
                            "context": "call", "confidence": "EXTRACTED",
                            "source_file": str_path, "weight": 1.0,
                            "source_location": f"L{node.start_point[0] + 1 + line_offset}",
                        })
                elif callee in imported:
                    sym = symbol_target(callee)
                    if sym is not None:
                        target_nid, tfile = sym
                    else:
                        _spec, target_nid, tpath, _exported = imported[callee]
                        tfile = str(tpath) if tpath is not None else None
                    pair = (owner_nid, target_nid)
                    if pair not in seen_call_pairs:
                        seen_call_pairs.add(pair)
                        edge = {
                            "source": owner_nid, "target": target_nid, "relation": "calls",
                            "context": "call", "confidence": "EXTRACTED",
                            "source_file": str_path, "weight": 1.0,
                            "source_location": f"L{node.start_point[0] + 1 + line_offset}",
                        }
                        if tfile is not None:
                            edge["target_file"] = tfile
                        edges.append(edge)
                else:
                    raw_calls.append({
                        "caller_nid": owner_nid,
                        "callee": callee,
                        "is_member_call": is_member,
                        "source_file": str_path,
                        "source_location": f"L{node.start_point[0] + 1 + line_offset}",
                    })
        for child in node.children:
            walk_calls(child, owner_nid, source, line_offset)

    for owner_nid, body, source, line_offset in bodies:
        walk_calls(body, owner_nid, source, line_offset)

    # Drop edges whose endpoints never materialised, mirroring go.py. Import and
    # cross-file `uses`/`calls` edges keep their stamped target for the
    # canonicalization pass in extract().
    keep_relations = ("imports", "imports_from", "dynamic_import", "uses", "calls")
    clean_edges = [
        e for e in edges
        if e["source"] in seen_ids and (e["target"] in seen_ids or e["relation"] in keep_relations)
    ]

    return {"nodes": nodes, "edges": clean_edges, "raw_calls": raw_calls}
