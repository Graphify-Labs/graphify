"""ArkTS (.ets) and HarmonyOS project-config support.

ArkTS is TypeScript plus the ``struct`` keyword for UI components and a set of
HarmonyOS decorators. ``extract.extract_ets`` rewrites ``struct`` to ``class ``
(same byte length, so AST line/column info is unchanged), runs the shared
TypeScript extractor, then calls :func:`enrich_arkts` here to add the
HarmonyOS semantics. :func:`extract_harmony_config` parses ``module.json5``,
``router_map.json``, ``oh-package.json5`` and ``build-profile.json5``.

IDs follow the v8 scheme: every file-scoped ID is prefixed with
``_file_stem(path)`` exactly like the AST nodes it decorates, so enrichment
edges land on the nodes ``_extract_generic`` produced and survive the
extract() id-remap pass.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from graphify.extractors.base import _file_stem, _make_id

# ── ArkTS (.ets) support ─────────────────────────────────────────────────────
#
# ArkTS is HarmonyOS's UI language — a strict superset of TypeScript with two
# non-TS syntactic additions:
#   1. The `struct` keyword for UI components: `@Component struct Foo { ... }`
#   2. A rich decorator system with V1/V2 families covering state management,
#      composition, observation, persistence, and styling.
#
# Decorators are already valid TypeScript syntax (experimentalDecorators), so
# tree-sitter-typescript handles them fine. Only `struct` needs preprocessing:
# we substitute `struct` → `class ` (both 6 chars — keeps byte offsets stable,
# so line numbers in AST match the original .ets file).
#
# After AST extraction we post-process the original source text to emit:
#   • arkts_component nodes (@Component/@ComponentV2 struct) — distinct from
#     plain classes so the graph can reason about UI components specifically
#   • arkts_decorator nodes for component-level decorators (@Entry, @Preview, …)
#   • arkts_state nodes for every reactive field (@State/@Prop/@Link/@Local/…)
#   • arkts_lifecycle nodes for lifecycle methods (aboutToAppear/onPageShow/…)
#   • arkts_resource nodes for `$r("app.xxx.yyy")` references
#   • arkts_provide_key nodes connecting @Provide("k") ↔ @Consume("k") across
#     components (cross-component state flow)
#
# And edges:
#   • decorates:         decorator  → struct
#   • contains_state:    struct     → reactive field
#   • has_lifecycle:     struct     → lifecycle method
#   • watches:           @Watch     → target method (same struct)
#   • monitors:          @Monitor   → target expression literal
#   • observes:          @ObservedV2 class → @Trace field
#   • uses_component:    parent struct → child UI component (from build() body)
#   • references_resource: struct   → resource
#   • provides / consumes: struct   → arkts_provide_key node
#   • storage_binds:     @StorageLink/@StorageProp → AppStorage key
#   • local_storage_binds: @LocalStorageLink/@LocalStorageProp → LocalStorage key
#
# These give the knowledge graph real HarmonyOS semantics instead of plain TS.

_ARKTS_COMPONENT_DECORATORS = frozenset({
    "Component", "ComponentV2", "Entry", "Preview", "CustomDialog",
    "Reusable", "ReusableV2",
})

_ARKTS_STATE_DECORATORS = frozenset({
    # V1 reactive decorators
    "State", "Prop", "Link", "Provide", "Consume", "Observed", "ObjectLink",
    "StorageLink", "StorageProp", "LocalStorageLink", "LocalStorageProp",
    "Watch", "BuilderParam", "Require",
    # V2 reactive decorators
    "ObservedV2", "Local", "Param", "Event", "Once", "Trace", "Monitor", "Computed",
    "Provider", "Consumer",
})

_ARKTS_BUILDER_DECORATORS = frozenset({
    "Builder", "Styles", "Extend", "AnimatableExtend", "Concurrent",
})

# Subset of state decorators whose string argument names a provide/consume key.
# Includes both V1 (Provide/Consume) and V2 (Provider/Consumer).
_ARKTS_PROVIDE_DECORATORS = frozenset({"Provide", "Provider"})
_ARKTS_CONSUME_DECORATORS = frozenset({"Consume", "Consumer"})

# Subset that binds to AppStorage or LocalStorage by a string key
_ARKTS_STORAGE_DECORATORS = frozenset({"StorageLink", "StorageProp"})
_ARKTS_LOCAL_STORAGE_DECORATORS = frozenset({"LocalStorageLink", "LocalStorageProp"})

# Lifecycle methods in ArkTS Components (V1 and V2)
_ARKTS_LIFECYCLE_METHODS = frozenset({
    "aboutToAppear", "aboutToDisappear",
    "aboutToReuse", "aboutToRecycle", "aboutToReappear",
    "onPageShow", "onPageHide", "onBackPress",
    "onDidBuild", "pageTransition",
    # Ability lifecycle (UIAbility / EntryAbility)
    "onCreate", "onDestroy",
    "onWindowStageCreate", "onWindowStageDestroy",
    "onWindowFocusChanged", "onForeground", "onBackground",
})

# Match a decorator line: @Name, @Name(...), or @Name({ ...  (multi-line start)
# We capture the name; balancing parens/braces is handled in _enrich_arkts.
_ETS_DECORATOR_RE = re.compile(r"^\s*@(\w+)\b")
# Match a struct/class head that is the declaration being decorated
_ETS_STRUCT_HEAD_RE = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:struct|class)\s+(\w+)")
# Match a decorated field: `@State foo: Type = ...` or `@Local foo =`.
# Also matches decorated getters: `@Computed get total(): T { ... }`.
_ETS_DECORATED_FIELD_RE = re.compile(
    r"^\s*@(\w+)\s*(?:\([^)]*\))?\s+"
    r"(?:private\s+|public\s+|protected\s+|readonly\s+|static\s+)*"
    r"(?:get\s+|set\s+)?"
    r"(\w+)\s*[:=?(]"  # allow `(` so decorated getters like @Computed get total() match
)

# Capitalized-identifier + "(" — used to find UI component usages inside build() bodies.
# This matches both built-in containers (Column, Row, NavDestination, ForEach, Text, Button,
# Image, List, Scroll, Stack, Flex, Grid, …) and user-defined components.
_ETS_UI_COMPONENT_CALL_RE = re.compile(r"\b([A-Z]\w+)\s*\(")
# Resource references: $r("app.string.xxx") / $r("app.color.xxx") / $r("app.media.xxx") etc.
_ETS_RESOURCE_REF_RE = re.compile(r"""\$r\s*\(\s*["']((?:app|sys)\.[\w.]+)["']\s*\)""")
# Raw file references: $rawfile("path")
_ETS_RAWFILE_REF_RE = re.compile(r"""\$rawfile\s*\(\s*["']([^"']+)["']\s*\)""")
# @Watch('methodName') / @Watch("methodName") — the string arg names a method in the same struct
_ETS_WATCH_ARG_RE = re.compile(r"""@Watch\s*\(\s*["'](\w+)["']\s*\)""")
# @Monitor('field' | 'field1','field2' | 'nested.path') — V2 multi-target observation
_ETS_MONITOR_ARG_RE = re.compile(r"""@Monitor\s*\(\s*((?:["'][^"']+["']\s*,?\s*)+)\)""")
# @Provide('key') / @Consume('key') / @Provider('key') / @Consumer('key')
_ETS_PROVIDE_CONSUME_ARG_RE = re.compile(
    r"""@(Provide|Consume|Provider|Consumer)\s*\(\s*["'](\w+)["']\s*\)"""
)
# @StorageLink('key') / @StorageProp('key') / @LocalStorageLink('key') / @LocalStorageProp('key')
_ETS_STORAGE_ARG_RE = re.compile(
    r"""@(Storage(?:Link|Prop)|LocalStorage(?:Link|Prop))\s*\(\s*["'](\w+)["']\s*\)"""
)
# @ObservedV2 class head on preceding line → @Trace fields inside — handled structurally
_ETS_CLASS_HEAD_RE = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?class\s+(\w+)")
# Method definition inside a struct body: "methodName(" possibly with modifiers
_ETS_METHOD_DEF_RE = re.compile(
    r"^\s*(?:private\s+|public\s+|protected\s+|static\s+|async\s+|override\s+)*"
    r"(\w+)\s*\([^)]*\)\s*(?::\s*[\w<>|\[\]\s]+)?\s*\{?$"
)

# Names that look like UI components but are actually not (chained style methods, operators).
# Chained property calls like .fontSize(12) start with '.', so our `\b[A-Z]` regex already
# filters those. What remains are statements or type annotations. We skip a small blocklist
# of things that frequently appear capitalized-paren but aren't UI components.
_ETS_NOT_UI_COMPONENTS = frozenset({
    # Math / util constructors that show up in UI but aren't components
    "Date", "Array", "Map", "Set", "Promise", "JSON", "Math", "Number", "String",
    "Object", "Boolean", "RegExp", "Symbol", "Error", "URL", "URLSearchParams",
    "Uint8Array", "Int8Array", "Float32Array", "Float64Array",
    # Common DSL "marker" calls that take props/style but aren't composition targets
    # (kept minimal — we err on the side of recognizing too many rather than too few)
})


def _find_struct_ranges(lines: list[str]) -> list[dict]:
    """Find (struct_or_class, start_line, end_line, open_brace_line) for each
    top-level struct/class in the source.

    Uses naive brace counting; good enough for ArkTS where strings rarely span
    multiple lines and template literals are uncommon. Returns lines 1-indexed.
    """
    ranges: list[dict] = []
    stack: list[dict] = []  # Currently-open structs; we only keep 1 at a time (ArkTS disallows nested structs)
    depth = 0
    # crude string tracking to avoid counting braces inside strings
    for idx, line in enumerate(lines):
        lineno = idx + 1
        # Strip inline // comments (not inside strings — still crude)
        code = re.sub(r"//.*$", "", line)

        # Detect new struct/class head on this line, only when not already inside one
        m = _ETS_STRUCT_HEAD_RE.match(code)
        if m and (not stack):
            stack.append({
                "name": m.group(1),
                "kind": "struct" if re.match(r"^\s*(?:export\s+)?(?:default\s+)?struct", code) else "class",
                "head_line": lineno,
                "depth_at_entry": depth,
            })

        # Count braces on this line, honoring strings (simple rule: ignore chars in "..."/'...')
        in_single = False
        in_double = False
        in_template = False
        escape = False
        for ch in code:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if in_single:
                if ch == "'":
                    in_single = False
                continue
            if in_double:
                if ch == '"':
                    in_double = False
                continue
            if in_template:
                if ch == "`":
                    in_template = False
                continue
            if ch == "'":
                in_single = True; continue
            if ch == '"':
                in_double = True; continue
            if ch == "`":
                in_template = True; continue
            if ch == "{":
                depth += 1
                # First { after entering struct is the body-open brace
                if stack and stack[-1].get("open_line") is None and depth == stack[-1]["depth_at_entry"] + 1:
                    stack[-1]["open_line"] = lineno
            elif ch == "}":
                depth -= 1
                # Closing the struct body
                if stack and depth == stack[-1]["depth_at_entry"]:
                    entry = stack.pop()
                    ranges.append({
                        "name": entry["name"],
                        "kind": entry["kind"],
                        "head_line": entry["head_line"],
                        "open_line": entry.get("open_line", entry["head_line"]),
                        "close_line": lineno,
                    })
    return ranges


def _containing_struct(struct_ranges: list[dict], lineno: int) -> dict | None:
    """Return the innermost struct range whose body contains the given line."""
    for r in struct_ranges:
        if r["open_line"] <= lineno <= r["close_line"]:
            return r
    return None


def enrich_arkts(source_text: str, path: Path, result: dict) -> None:
    """Post-process extraction result with ArkTS-specific semantic nodes/edges.

    Mutates ``result`` in place. Done in multiple passes over the original
    source text so that the AST-derived node IDs remain authoritative.
    """
    str_path = str(path)
    file_nid = _make_id(str(path))
    stem = _file_stem(path)
    nodes = result["nodes"]
    edges = result["edges"]
    seen = {n["id"] for n in nodes}
    # Index AST-derived class/struct nodes so enrichment can upgrade their node_type
    ast_struct_ids: set[str] = set()
    for n in nodes:
        # Class nodes have IDs like "stem_classname" from _extract_generic
        if "." not in (n.get("label") or "") and not n.get("node_type"):
            ast_struct_ids.add(n["id"])
    node_by_id = {n["id"]: n for n in nodes}

    def add_node(nid: str, label: str, line: int, node_type: str) -> None:
        if nid in seen:
            # Upgrade node_type if already present without type
            existing = node_by_id.get(nid)
            if existing and not existing.get("node_type"):
                existing["node_type"] = node_type
            return
        seen.add(nid)
        n = {
            "id": nid,
            "label": label,
            "file_type": "code",
            "node_type": node_type,
            "source_file": str_path,
            "source_location": f"L{line}",
        }
        nodes.append(n)
        node_by_id[nid] = n

    def add_edge(src: str, tgt: str, relation: str, line: int,
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

    lines = source_text.splitlines()
    struct_ranges = _find_struct_ranges(lines)

    # ── Pass 1: walk lines, detect decorators + fields + methods ──────────────
    pending: list[tuple[str, int]] = []  # queued decorators waiting for their target
    paren_depth = 0                       # for multi-line decorator args

    # Track @Trace fields per class so we can link to an enclosing @ObservedV2 class
    observed_v2_class: str | None = None        # most recent @ObservedV2 class name
    observed_v2_line: int = 0                   # line of its declaration
    # Collect per-struct @Watch bindings: list of (struct_name, deco_line, target_method_name)
    pending_watches: list[tuple[str, int, str]] = []

    for idx, raw_line in enumerate(lines):
        lineno = idx + 1
        stripped = raw_line.rstrip()
        stripped_lead = stripped.lstrip()

        # Inside multi-line decorator args: update depth, don't parse
        if paren_depth > 0:
            paren_depth += raw_line.count("(") - raw_line.count(")")
            if paren_depth < 0:
                paren_depth = 0
            continue

        # Skip blanks and comments
        if not stripped_lead or stripped_lead.startswith("//") or stripped_lead.startswith("*") or stripped_lead.startswith("/*"):
            continue

        # Case 1: decorated-field on one line → "@State foo: T = ..."
        m_field = _ETS_DECORATED_FIELD_RE.match(stripped)
        if m_field:
            deco_name, field_name = m_field.group(1), m_field.group(2)
            containing = _containing_struct(struct_ranges, lineno)
            _emit_field_decorator(
                add_node, add_edge, stripped, file_nid, stem, path,
                deco_name, field_name, lineno, containing, observed_v2_class, observed_v2_line,
            )
            # @Watch('method') on a decorated field → queue the watch binding
            if deco_name == "Watch" and containing:
                for wm in _ETS_WATCH_ARG_RE.finditer(stripped):
                    pending_watches.append((containing["name"], lineno, wm.group(1)))
            continue

        # Case 2: standalone decorator line
        m_deco = _ETS_DECORATOR_RE.match(stripped)
        if m_deco:
            deco_name = m_deco.group(1)
            rest = stripped[m_deco.end():]
            paren_depth = rest.count("(") - rest.count(")")
            if paren_depth < 0:
                paren_depth = 0
            pending.append((deco_name, lineno))
            # Capture Watch/Monitor/Provide/Consume/Storage args for later binding
            if "(" in stripped:
                full_line = raw_line  # use original line for arg regex
                for m in _ETS_WATCH_ARG_RE.finditer(full_line):
                    pending_watches.append(("__pending__", lineno, m.group(1)))
            continue

        # Case 3: class/struct head — consume pending decorators
        m_cls = _ETS_CLASS_HEAD_RE.match(stripped)
        m_struct = _ETS_STRUCT_HEAD_RE.match(stripped)
        head = m_struct or m_cls
        if head and pending:
            name = head.group(1)
            target_nid = _make_id(stem, name)
            is_component = False
            for deco_name, deco_line in pending:
                if deco_name in _ARKTS_COMPONENT_DECORATORS:
                    is_component = True
                    deco_nid = _make_id(stem, name, f"@{deco_name}")
                    add_node(deco_nid, f"@{deco_name}", deco_line, "arkts_decorator")
                    add_edge(deco_nid, target_nid, "decorates", deco_line)
                elif deco_name == "ObservedV2":
                    observed_v2_class = name
                    observed_v2_line = lineno
                    # Mark the class as observed
                    if target_nid in node_by_id:
                        node_by_id[target_nid]["node_type"] = "arkts_observed_v2"
                elif deco_name == "Observed":
                    if target_nid in node_by_id:
                        node_by_id[target_nid]["node_type"] = "arkts_observed"
            # Upgrade struct type → arkts_component. ArkTS-only syntax inside a
            # build() body can make the TypeScript grammar drop the whole class,
            # so mint the component node (anchored to the file) when the AST
            # missed it; otherwise every edge hanging off it is a phantom.
            if is_component and target_nid in node_by_id:
                node_by_id[target_nid]["node_type"] = "arkts_component"
            elif is_component:
                add_node(target_nid, name, lineno, "arkts_component")
                add_edge(file_nid, target_nid, "contains", lineno)
            # Link pending Watch bindings to this struct's future methods
            for i, (tag, l, method_name) in enumerate(pending_watches):
                if tag == "__pending__":
                    pending_watches[i] = (name, l, method_name)
            pending.clear()
            continue

        # Case 4: field after pending decorator on previous line
        if pending:
            field_match = re.match(
                r"^\s*(?:private\s+|public\s+|protected\s+|readonly\s+)*(\w+)\s*[:=?]",
                stripped,
            )
            if field_match:
                field_name = field_match.group(1)
                containing = _containing_struct(struct_ranges, lineno)
                for deco_name, deco_line in pending:
                    _emit_field_decorator(
                        add_node, add_edge, stripped, file_nid, stem, path,
                        deco_name, field_name, deco_line, containing,
                        observed_v2_class, observed_v2_line,
                    )
                pending.clear()
                continue

        # Case 5: method definition — check if it's a lifecycle method
        m_method = _ETS_METHOD_DEF_RE.match(stripped)
        if m_method:
            method_name = m_method.group(1)
            if method_name in _ARKTS_LIFECYCLE_METHODS:
                containing = _containing_struct(struct_ranges, lineno)
                if containing:
                    struct_nid = _make_id(stem, containing["name"])
                    method_nid = _make_id(stem, containing["name"], method_name)
                    # The AST already links struct -> method with a `method` edge, and
                    # build.py keeps the structural member edge when a pair collapses,
                    # so a parallel `has_lifecycle` edge would be dropped. Type the
                    # node instead; add the edge only when the AST missed the method.
                    if method_nid in node_by_id:
                        node_by_id[method_nid]["node_type"] = "arkts_lifecycle"
                    else:
                        add_node(method_nid, f".{method_name}()", lineno, "arkts_lifecycle")
                        add_edge(struct_nid, method_nid, "has_lifecycle", lineno)
            # Resolve pending @Watch bindings for methods in the current struct
            containing = _containing_struct(struct_ranges, lineno)
            if containing:
                for i, (bound_struct, deco_line, target_method) in enumerate(pending_watches):
                    if bound_struct == containing["name"] and target_method == method_name:
                        watch_nid = _make_id(stem, containing["name"], f"@Watch:{target_method}")
                        method_nid = _make_id(stem, containing["name"], method_name)
                        add_node(watch_nid, f"@Watch('{target_method}')", deco_line, "arkts_watch")
                        add_edge(watch_nid, method_nid, "watches", deco_line)
                        pending_watches[i] = ("", -1, "")

        # Any non-matching line clears pending
        pending.clear()

    # ── Pass 2: UI composition from build() bodies ────────────────────────────
    _enrich_ui_composition(lines, struct_ranges, stem, str_path, add_node, add_edge)

    # ── Pass 3: resource references anywhere in the file ──────────────────────
    _enrich_resources(source_text, struct_ranges, stem, str_path, add_node, add_edge)

    # ── Pass 4: Provide/Consume cross-component keys ─────────────────────────
    _enrich_provide_consume(source_text, struct_ranges, stem, str_path, add_node, add_edge)

    # ── Pass 5: Storage bindings ─────────────────────────────────────────────
    _enrich_storage_bindings(source_text, struct_ranges, stem, str_path, add_node, add_edge)

    # ── Pass 6: Monitor targets ──────────────────────────────────────────────
    _enrich_monitors(source_text, struct_ranges, stem, str_path, add_node, add_edge)


def _emit_field_decorator(add_node, add_edge, stripped, file_nid, stem, path,
                           deco_name, field_name, lineno, containing,
                           observed_v2_class, observed_v2_line):
    """Emit a reactive-state node + edges for a single @Decorator field."""
    if deco_name not in _ARKTS_STATE_DECORATORS:
        return
    str_path = str(path)
    state_nid = _make_id(stem, f"@{deco_name}", field_name)
    add_node(state_nid, f"@{deco_name} {field_name}", lineno, "arkts_state")
    # Link to containing struct if we can find it; else to file
    if containing:
        struct_nid = _make_id(stem, containing["name"])
        add_edge(struct_nid, state_nid, "contains_state", lineno)
    else:
        add_edge(file_nid, state_nid, "contains_state", lineno)
    # @Trace field inside @ObservedV2 class → observes edge from class
    if deco_name == "Trace" and containing and containing.get("kind") == "class":
        class_nid = _make_id(stem, containing["name"])
        add_edge(class_nid, state_nid, "observes", lineno)


def _enrich_ui_composition(lines, struct_ranges, stem, str_path, add_node, add_edge) -> None:
    """For each struct, find build() body and emit uses_component edges."""
    for sr in struct_ranges:
        # Scan struct body for a `build(` method followed by `{`
        body_text = "\n".join(lines[sr["open_line"]: sr["close_line"]])
        build_match = re.search(r"\bbuild\s*\(\s*\)\s*\{", body_text)
        if not build_match:
            continue
        # Find build() body by brace counting, starting from the line containing the match
        # Compute starting line in original file
        prefix = body_text[: build_match.start()]
        build_open_offset = build_match.end()  # position right after the '{'
        build_start_lineno_in_body = prefix.count("\n")
        build_start_line = sr["open_line"] + build_start_lineno_in_body + 1  # 1-indexed

        depth = 1  # we already entered `{`
        body_lines: list[tuple[int, str]] = []
        # Scan from build_open_offset in body_text until matching close
        i = build_open_offset
        current_line = build_start_line
        line_buffer = ""
        end_line = sr["close_line"]
        while i < len(body_text) and depth > 0:
            ch = body_text[i]
            if ch == "\n":
                body_lines.append((current_line, line_buffer))
                current_line += 1
                line_buffer = ""
            else:
                line_buffer += ch
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end_line = current_line
                    break
            i += 1

        # Collect UI component calls
        seen_in_build: set[str] = set()
        parent_nid = _make_id(stem, sr["name"])
        for lno, bl in body_lines:
            # Strip inline // comments
            code_only = re.sub(r"//.*$", "", bl)
            # Strip chained property calls: anything starting with "." is a style call
            # But our regex uses \b which won't match after "."
            for m in _ETS_UI_COMPONENT_CALL_RE.finditer(code_only):
                comp_name = m.group(1)
                if comp_name in _ETS_NOT_UI_COMPONENTS:
                    continue
                # Dedup per-struct to avoid noise from every ForEach iteration
                if comp_name in seen_in_build:
                    continue
                seen_in_build.add(comp_name)
                comp_nid = _make_id(stem, sr["name"], "uses", comp_name)
                add_node(comp_nid, comp_name, lno, "arkts_ui_component_usage")
                add_edge(parent_nid, comp_nid, "uses_component", lno)


def _enrich_resources(source_text, struct_ranges, stem, str_path, add_node, add_edge) -> None:
    """Find $r('app.xxx.yyy') / $rawfile('...') refs, create arkts_resource nodes."""
    emitted_edges: set[tuple[str, str, int]] = set()
    for m in _ETS_RESOURCE_REF_RE.finditer(source_text):
        resource_key = m.group(1)       # e.g. "app.color.color_16DB99"
        lineno = source_text.count("\n", 0, m.start()) + 1
        resource_nid = _make_id("resource", resource_key)
        add_node(resource_nid, f"$r({resource_key})", lineno, "arkts_resource")
        containing = _containing_struct(struct_ranges, lineno)
        if containing:
            struct_nid = _make_id(stem, containing["name"])
            key = (struct_nid, resource_nid, 0)  # dedup per struct, any line
            if key in emitted_edges:
                continue
            emitted_edges.add(key)
            add_edge(struct_nid, resource_nid, "references_resource", lineno)
    for m in _ETS_RAWFILE_REF_RE.finditer(source_text):
        resource_key = m.group(1)
        lineno = source_text.count("\n", 0, m.start()) + 1
        resource_nid = _make_id("rawfile", resource_key)
        add_node(resource_nid, f"$rawfile({resource_key})", lineno, "arkts_resource")
        containing = _containing_struct(struct_ranges, lineno)
        if containing:
            struct_nid = _make_id(stem, containing["name"])
            key = (struct_nid, resource_nid, 0)
            if key in emitted_edges:
                continue
            emitted_edges.add(key)
            add_edge(struct_nid, resource_nid, "references_resource", lineno)


def _enrich_provide_consume(source_text, struct_ranges, stem, str_path, add_node, add_edge) -> None:
    """Emit synthetic key nodes for @Provide/@Consume/@Provider/@Consumer cross-component flow."""
    for m in _ETS_PROVIDE_CONSUME_ARG_RE.finditer(source_text):
        deco_name, key = m.group(1), m.group(2)
        start = m.start()
        lineno = source_text.count("\n", 0, start) + 1
        containing = _containing_struct(struct_ranges, lineno)
        if not containing:
            continue
        struct_nid = _make_id(stem, containing["name"])
        key_nid = _make_id("provide_key", key)
        add_node(key_nid, f"Provide<{key}>", lineno, "arkts_provide_key")
        if deco_name in _ARKTS_PROVIDE_DECORATORS:
            add_edge(struct_nid, key_nid, "provides", lineno)
        else:
            add_edge(struct_nid, key_nid, "consumes", lineno)


def _enrich_storage_bindings(source_text, struct_ranges, stem, str_path, add_node, add_edge) -> None:
    """Emit synthetic storage key nodes for @StorageLink / @LocalStorageLink bindings."""
    for m in _ETS_STORAGE_ARG_RE.finditer(source_text):
        deco_name, key = m.group(1), m.group(2)
        start = m.start()
        lineno = source_text.count("\n", 0, start) + 1
        containing = _containing_struct(struct_ranges, lineno)
        if not containing:
            continue
        struct_nid = _make_id(stem, containing["name"])
        if deco_name.startswith("LocalStorage"):
            key_nid = _make_id("local_storage_key", key)
            add_node(key_nid, f"LocalStorage<{key}>", lineno, "arkts_local_storage_key")
            add_edge(struct_nid, key_nid, "local_storage_binds", lineno)
        else:
            key_nid = _make_id("app_storage_key", key)
            add_node(key_nid, f"AppStorage<{key}>", lineno, "arkts_app_storage_key")
            add_edge(struct_nid, key_nid, "storage_binds", lineno)


def _enrich_monitors(source_text, struct_ranges, stem, str_path, add_node, add_edge) -> None:
    """@Monitor('path1', 'path2', ...) — attach monitor targets as monitors edges."""
    for m in _ETS_MONITOR_ARG_RE.finditer(source_text):
        args_blob = m.group(1)
        # Extract individual string literals
        targets = re.findall(r"""["']([^"']+)["']""", args_blob)
        start = m.start()
        lineno = source_text.count("\n", 0, start) + 1
        containing = _containing_struct(struct_ranges, lineno)
        if not containing:
            continue
        struct_nid = _make_id(stem, containing["name"])
        for target_expr in targets:
            monitor_nid = _make_id(stem, containing["name"], "monitor", target_expr)
            add_node(monitor_nid, f"@Monitor('{target_expr}')", lineno, "arkts_monitor_target")
            add_edge(struct_nid, monitor_nid, "monitors", lineno)

#
# Parses module.json5, oh-package.json5, router_map.json, build-profile.json5
# into structured graph nodes/edges. Gives the KG real HarmonyOS project
# semantics: abilities, permissions, routes, HAR dependencies.


_JSON5_LINE_COMMENT_RE = re.compile(r"""(?m)(?<!:)//[^\n]*""")
_JSON5_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_JSON5_TRAILING_COMMA_RE = re.compile(r",(\s*[\]}])")


def _parse_json5(text: str) -> dict | list | None:
    """Parse a JSON5-ish document (comments + trailing commas allowed).

    No external dependency — just strips the two non-JSON features HarmonyOS
    config files use and hands the rest to json.loads. Returns None on failure.
    """
    try:
        # Strip // comments (but keep URL schemes like "https://…")
        t = _JSON5_LINE_COMMENT_RE.sub("", text)
        # Strip /* ... */ block comments
        t = _JSON5_BLOCK_COMMENT_RE.sub("", t)
        # Drop trailing commas before ] or }
        t = _JSON5_TRAILING_COMMA_RE.sub(r"\1", t)
        return json.loads(t)
    except Exception:
        return None


def _extract_module_json5(data: dict, path: Path, stem: str, str_path: str,
                           nodes: list, edges: list, seen: set) -> None:
    """module.json5 → harmony_module + harmony_ability + harmony_permission nodes."""
    mod = data.get("module") or {}
    mod_name = mod.get("name") or stem
    mod_nid = _make_id("harmony_module", mod_name)
    if mod_nid not in seen:
        seen.add(mod_nid)
        nodes.append({
            "id": mod_nid,
            "label": f"module:{mod_name}",
            "file_type": "code",
            "node_type": "harmony_module",
            "source_file": str_path,
            "source_location": "L1",
            "module_type": mod.get("type", ""),
        })

    # Abilities
    for a in (mod.get("abilities") or []):
        a_name = a.get("name") or ""
        if not a_name:
            continue
        a_nid = _make_id("harmony_ability", mod_name, a_name)
        if a_nid not in seen:
            seen.add(a_nid)
            nodes.append({
                "id": a_nid,
                "label": f"Ability:{a_name}",
                "file_type": "code",
                "node_type": "harmony_ability",
                "source_file": str_path,
                "source_location": "L1",
                "srcEntry": a.get("srcEntry", ""),
                "launchType": a.get("launchType", ""),
            })
        edges.append({
            "source": mod_nid, "target": a_nid, "relation": "declares_ability",
            "confidence": "EXTRACTED", "source_file": str_path,
            "source_location": "L1", "weight": 1.0,
        })

    # extensionAbilities
    for a in (mod.get("extensionAbilities") or []):
        a_name = a.get("name") or ""
        if not a_name:
            continue
        a_nid = _make_id("harmony_extension_ability", mod_name, a_name)
        if a_nid not in seen:
            seen.add(a_nid)
            nodes.append({
                "id": a_nid,
                "label": f"ExtensionAbility:{a_name}",
                "file_type": "code",
                "node_type": "harmony_extension_ability",
                "source_file": str_path,
                "source_location": "L1",
                "type": a.get("type", ""),
            })
        edges.append({
            "source": mod_nid, "target": a_nid, "relation": "declares_extension_ability",
            "confidence": "EXTRACTED", "source_file": str_path,
            "source_location": "L1", "weight": 1.0,
        })

    # Permissions
    for p in (mod.get("requestPermissions") or []):
        p_name = p.get("name") if isinstance(p, dict) else p
        if not p_name:
            continue
        p_nid = _make_id("harmony_permission", p_name)
        if p_nid not in seen:
            seen.add(p_nid)
            nodes.append({
                "id": p_nid,
                "label": p_name,
                "file_type": "code",
                "node_type": "harmony_permission",
                "source_file": str_path,
                "source_location": "L1",
            })
        edges.append({
            "source": mod_nid, "target": p_nid, "relation": "requires_permission",
            "confidence": "EXTRACTED", "source_file": str_path,
            "source_location": "L1", "weight": 1.0,
        })


_ROUTER_MAP_MODULE_DEPTH = 5  # <module>/src/main/resources/base/profile/router_map.json
_ETS_ENTRY_STRUCT_RE = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?struct\s+(\w+)", re.MULTILINE)


def _route_page_node_id(router_map: Path, page_source: str, route_name: str) -> str:
    """Node ID of the page struct a route points at.

    ``pageSourceFile`` is relative to the module directory. Resolve it against
    the module that owns this router_map.json and key the ID with the same
    ``_file_stem`` the .ets extractor used, so the edge lands on the real
    struct node. The struct name is read from the page file (first ``struct``
    declaration); the route name is only a fallback when the file is absent.
    """
    parents = router_map.parents
    module_dir = parents[_ROUTER_MAP_MODULE_DEPTH] if len(parents) > _ROUTER_MAP_MODULE_DEPTH else router_map.parent
    page_path = module_dir / page_source
    struct_name = route_name
    try:
        match = _ETS_ENTRY_STRUCT_RE.search(page_path.read_text(encoding="utf-8", errors="replace"))
        if match:
            struct_name = match.group(1)
    except OSError:
        pass
    return _make_id(_file_stem(page_path), struct_name)


def _extract_router_map(data: dict | list, path: Path, stem: str, str_path: str,
                         nodes: list, edges: list, seen: set) -> None:
    """router_map.json → harmony_route nodes + route_maps_to edges to page components."""
    routes = data.get("routerMap") if isinstance(data, dict) else data
    if not isinstance(routes, list):
        return
    for r in routes:
        if not isinstance(r, dict):
            continue
        r_name = r.get("name") or ""
        page_source = r.get("pageSourceFile") or ""
        if not r_name:
            continue
        r_nid = _make_id("harmony_route", r_name)
        if r_nid not in seen:
            seen.add(r_nid)
            nodes.append({
                "id": r_nid,
                "label": f"Route:{r_name}",
                "file_type": "code",
                "node_type": "harmony_route",
                "source_file": str_path,
                "source_location": "L1",
                "page_source_file": page_source,
                "build_function": r.get("buildFunction", ""),
            })
        if page_source:
            page_nid = _route_page_node_id(path, page_source, r_name)
            edges.append({
                "source": r_nid, "target": page_nid, "relation": "route_maps_to",
                "confidence": "INFERRED", "source_file": str_path,
                "source_location": "L1", "weight": 1.0,
            })


def _extract_oh_package(data: dict, path: Path, stem: str, str_path: str,
                         nodes: list, edges: list, seen: set) -> None:
    """oh-package.json5 → harmony_package + harmony_dependency nodes."""
    name = data.get("name") or stem
    pkg_nid = _make_id("harmony_package", name)
    if pkg_nid not in seen:
        seen.add(pkg_nid)
        nodes.append({
            "id": pkg_nid,
            "label": f"Package:{name}",
            "file_type": "code",
            "node_type": "harmony_package",
            "source_file": str_path,
            "source_location": "L1",
            "version": data.get("version", ""),
            "main": data.get("main", ""),
        })
    for dep_section in ("dependencies", "devDependencies", "dynamicDependencies"):
        deps = data.get(dep_section) or {}
        for dep_name, dep_version in deps.items():
            d_nid = _make_id("harmony_dependency", dep_name)
            if d_nid not in seen:
                seen.add(d_nid)
                nodes.append({
                    "id": d_nid,
                    "label": dep_name,
                    "file_type": "code",
                    "node_type": "harmony_dependency",
                    "source_file": str_path,
                    "source_location": "L1",
                    "version": str(dep_version),
                })
            rel = {
                "dependencies": "depends_on",
                "devDependencies": "dev_depends_on",
                "dynamicDependencies": "dynamic_depends_on",
            }[dep_section]
            edges.append({
                "source": pkg_nid, "target": d_nid, "relation": rel,
                "confidence": "EXTRACTED", "source_file": str_path,
                "source_location": "L1", "weight": 1.0,
            })


def _extract_build_profile(data: dict, path: Path, stem: str, str_path: str,
                            nodes: list, edges: list, seen: set) -> None:
    """build-profile.json5 → harmony_build_profile with module targets as sub-nodes."""
    profile_nid = _make_id("harmony_build_profile", stem, path.parent.name)
    if profile_nid not in seen:
        seen.add(profile_nid)
        nodes.append({
            "id": profile_nid,
            "label": f"BuildProfile:{path.parent.name}",
            "file_type": "code",
            "node_type": "harmony_build_profile",
            "source_file": str_path,
            "source_location": "L1",
        })
    for m in (data.get("modules") or []):
        if not isinstance(m, dict):
            continue
        m_name = m.get("name") or ""
        if not m_name:
            continue
        m_nid = _make_id("harmony_module", m_name)
        if m_nid not in seen:
            seen.add(m_nid)
            nodes.append({
                "id": m_nid,
                "label": f"module:{m_name}",
                "file_type": "code",
                "node_type": "harmony_module",
                "source_file": str_path,
                "source_location": "L1",
            })
        edges.append({
            "source": profile_nid, "target": m_nid, "relation": "configures_module",
            "confidence": "EXTRACTED", "source_file": str_path,
            "source_location": "L1", "weight": 1.0,
        })


def extract_harmony_config(path: Path) -> dict:
    """Extract nodes/edges from HarmonyOS project config files.

    Dispatches by filename — module.json5 / router_map.json / oh-package.json5
    / build-profile.json5 each have a different schema.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    data = _parse_json5(text)
    if data is None:
        return {"nodes": [], "edges": [], "error": "Failed to parse JSON5"}

    nodes: list[dict] = []
    edges: list[dict] = []
    seen: set[str] = set()
    str_path = str(path)
    # Only a fallback display name / global-ID component (package or module
    # without a "name", build profile). Use the bare file stem, never the
    # path-derived _file_stem: these IDs are global, so a path here would leak
    # the checkout location into labels and make IDs differ per checkout.
    stem = path.stem

    # File node so edges always have a rooted anchor
    file_nid = _make_id(str_path)
    seen.add(file_nid)
    nodes.append({
        "id": file_nid,
        "label": path.name,
        "file_type": "code",
        "node_type": "harmony_config",
        "source_file": str_path,
        "source_location": "L1",
    })

    name = path.name
    # router_map.json may be a bare route list; the other three are objects.
    if name == "router_map.json":
        _extract_router_map(data, path, stem, str_path, nodes, edges, seen)
    elif not isinstance(data, dict):
        pass
    elif name == "module.json5":
        _extract_module_json5(data, path, stem, str_path, nodes, edges, seen)
    elif name == "oh-package.json5":
        _extract_oh_package(data, path, stem, str_path, nodes, edges, seen)
    elif name == "build-profile.json5":
        _extract_build_profile(data, path, stem, str_path, nodes, edges, seen)

    # Link every top-level harmony_* node back to the file for traceability
    for n in nodes:
        if n["id"] == file_nid:
            continue
        edges.append({
            "source": file_nid, "target": n["id"], "relation": "contains",
            "confidence": "EXTRACTED", "source_file": str_path,
            "source_location": "L1", "weight": 0.5,
        })

    return {"nodes": nodes, "edges": edges}


