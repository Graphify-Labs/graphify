"""Dart extractor. Moved verbatim from graphify/extract.py."""
from __future__ import annotations

import html
import re

from pathlib import Path
from graphify.extractors.base import _file_stem, _make_id


# ── Dartdoc (`///`) ───────────────────────────────────────────────────────────
# The comment-stripping pass in extract_dart() deletes every `//`-prefixed line
# before a single symbol is extracted, and `///` is just a special case of `//`.
# For a Dart corpus that throws away the richest human-authored statement of what
# an API is for and how it is used — 14.4k doc blocks in Flutter's own
# `src/material` alone. These helpers recover it from the RAW source, before the
# stripping runs, so the existing passes keep operating on comment-free text.

_DARTDOC_LINE = re.compile(r"^[ \t]*///[ \t]?(.*)$")

# Type-shaped declarations a doc block can precede. Mirrors the class pattern used
# by section 1 so both agree on what counts as a declaration.
_DARTDOC_TYPE_DECL = re.compile(
    r"^\s*(?:(?:abstract|sealed|base|interface|final|mixin)\s+)*"
    r"(?:class|mixin|enum|extension\s+type|extension|typedef)\s+(\w+)"
)
# A constructor is the one declaration whose name IS the enclosing type, with no
# return type in front: `Foo(`, `const Foo(`, `factory Foo.fromJson(`, `Foo._(`.
# The `type == enclosing type` check at the call site is what keeps a widget
# constructor CALL inside a build method (`Padding(`) from matching.
_DARTDOC_CONSTRUCTOR_DECL = re.compile(
    r"^\s*(?:(?:const|factory|external)\s+)*"
    r"(?P<type>[A-Z]\w*)(?:\.(?P<name>\w+))?\s*\("
)
# Inside a constructor's parameter list, `this.x` / `super.x` forwards to a field
# that already has its own node, so a doc above it documents that field.
_DARTDOC_FORWARDED_PARAM = re.compile(r"^\s*(?:required\s+)?(?:this|super)\.(\w+)")
# Any other parameter: the last identifier before the end of the declaration,
# once a default value has been cut off (a default can itself contain commas and
# identifiers — `= EdgeInsets.only(left: 1, right: 2)` — and the parameter name is
# always to its left). The trailing class covers `field, {`, where the brace opens
# the named-parameter group. Only consulted when the line is known to sit inside a
# parameter list.
_DARTDOC_PARAM_NAME = re.compile(r"(\w+)\s*[,;)}\]{\s]*$")
# Everything else (methods, fields, getters, top-level functions/variables): the
# declared name is the last identifier before the first `(`, `=`, `;` or `{`.
_DARTDOC_MEMBER_DECL = re.compile(r"(\w+)\s*[(=;{]")
_DARTDOC_LIBRARY_DECL = re.compile(r"^\s*library\b")

# Line-level dartdoc directives (`@docImport 'x.dart';`, `@nodoc`) carry no prose
# and must never leak into the doc text.
_DARTDOC_LINE_DIRECTIVE = re.compile(r"^\s*@\w+")
# Inline directives: {@template id}, {@macro id}, {@tool dartpad}, {@youtube ...}.
_DARTDOC_INLINE_DIRECTIVE = re.compile(r"\{@[^}]*\}")
_DARTDOC_TEMPLATE = re.compile(r"\{@template\s+([^\s}]+)\}")
_DARTDOC_MACRO = re.compile(r"\{@macro\s+([^\s}]+)\}")
# The runnable example a {@tool} block points at, e.g.
# `** See code in examples/api/lib/material/scaffold/scaffold.0.dart **`.
_DARTDOC_SAMPLE = re.compile(r"\*\*\s*See code in (\S+)\s*\*\*")
# The curated cross-reference list dartdoc convention puts at the end of a block.
_DARTDOC_SEE_ALSO = re.compile(r"^See also:\s*$", re.MULTILINE)
_DARTDOC_SEE_ALSO_ENTRY = re.compile(r"^\s*\*\s+\[([A-Za-z_]\w*)", re.MULTILINE)
# Dartdoc renders inline HTML, and generated files lean on it — every one of the
# ~8.8k icon constants in Flutter's icons.dart is documented as an <i> tag. Strip
# the markup so the text reads as prose. The tag-name charset excludes ":" so
# dartdoc's <https://...> autolinks survive.
_DARTDOC_HTML_TAG = re.compile(r"</?[a-zA-Z][\w-]*(?:\s[^>\n]*)?>")
# `[Foo]` / `[Foo.bar]` inside prose is a dartdoc reference, not a markdown link.
_DARTDOC_REF = re.compile(r"\[([^\]\n]+)\]")
# A control character in a node attribute breaks the HTML export (#2897).
_DARTDOC_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

# Blanked before counting brackets for structural context: string literals and
# trailing `//` comments, whose brackets are not code. Doc lines start with `///`
# so they are already excluded.
_DARTDOC_LINE_NOISE = re.compile(
    r"'''[\s\S]*?'''"
    r'|"""[\s\S]*?"""'
    r"|'(?:\\.|[^'\\])*'"
    r'|"(?:\\.|[^"\\])*"'
    r"|//.*$"
)

# Scalar/collection builtins are never worth a `references` edge — same list the
# type-lookup pass in section 7 filters on.
_DARTDOC_REF_NOISE = frozenset({
    "String", "int", "double", "bool", "num", "dynamic", "Object", "void",
    "List", "Map", "Set", "Iterable", "Future", "Stream", "Function", "Record",
    "Null", "Never",
})


def _parse_dartdoc(body: str) -> dict:
    """Split one raw dartdoc block into the parts worth putting in a graph.

    ``doc`` is the block's full prose — every paragraph, joined by blank lines,
    with directives removed, inline HTML stripped and `[refs]` unwrapped. It is
    deliberately NOT truncated: a consumer that wants the one-line summary takes
    ``doc.split("\\n\\n")[0]``, which is dartdoc's own convention for the first
    paragraph, and one that wants the whole explanation now has it.

    ``see_also`` is the curated cross-reference list; ``samples`` are the runnable
    example files a ``{@tool}`` block points at; ``templates`` and ``macros`` are
    the two halves of dartdoc's transclusion (`{@template id}` declares a reusable
    fragment, `{@macro id}` pastes it in — 714 macros resolving to 224 templates
    across Flutter's `src/material`, many living in another package entirely).
    """
    see_also: list[str] = []
    prose_source = body
    marker = _DARTDOC_SEE_ALSO.search(body)
    if marker:
        for name in _DARTDOC_SEE_ALSO_ENTRY.findall(body[marker.end():]):
            if name not in see_also:
                see_also.append(name)
        prose_source = body[:marker.start()]

    prose_lines = [
        line for line in prose_source.splitlines()
        if not _DARTDOC_LINE_DIRECTIVE.match(line)
    ]
    prose = "\n".join(prose_lines)
    prose = _DARTDOC_SAMPLE.sub("", prose)
    prose = _DARTDOC_INLINE_DIRECTIVE.sub("", prose)
    prose = _DARTDOC_HTML_TAG.sub("", prose)
    prose = html.unescape(prose)
    prose = _DARTDOC_REF.sub(r"\1", prose)
    prose = _DARTDOC_CONTROL.sub("", prose)

    paragraphs = [" ".join(p.split()) for p in re.split(r"\n\s*\n", prose) if p.strip()]

    return {
        "doc": "\n\n".join(paragraphs),
        "see_also": see_also,
        "samples": _DARTDOC_SAMPLE.findall(body),
        "templates": _DARTDOC_TEMPLATE.findall(body),
        "macros": _DARTDOC_MACRO.findall(body),
    }


def _dartdoc_constructor_label(type_name: str, ctor_name: str | None) -> str:
    """Node label for a constructor. The trailing `()` is what keeps an unnamed
    constructor's label from colliding with its class's."""
    return f"{type_name}.{ctor_name}()" if ctor_name else f"{type_name}()"


def _dartdoc_constructor_key(type_name: str, ctor_name: str | None) -> str:
    """ID fragment for a constructor. A name made only of underscores normalizes
    to nothing, which would collapse `Foo._()` onto the class node — or, for the
    bare `_`, onto the FILE node (#2738)."""
    if not ctor_name:
        return f"{type_name}.new"
    return f"{type_name}.{ctor_name}" if ctor_name.strip("_") else f"{type_name}.private"


def _dartdoc_structure(lines: list[str]) -> tuple[list, list]:
    """For every line, the type that encloses it and the constructor whose
    parameter list it sits in.

    Brace depth resolves the enclosing type, paren depth resolves the parameter
    list, both counted on lines with strings and trailing comments blanked out.
    """
    enclosing: list[str | None] = []
    param_of: list[tuple[str, str, str | None] | None] = []
    stack: list[tuple[int, str]] = []
    depth = 0
    current_ctor: tuple[str, str, str | None] | None = None
    paren_depth = 0

    for raw in lines:
        line = _DARTDOC_LINE_NOISE.sub("", raw)
        enclosing.append(stack[-1][1] if stack else None)
        param_of.append(current_ctor)

        type_match = _DARTDOC_TYPE_DECL.match(line)
        if type_match:
            stack.append((depth, type_match.group(1)))
        elif current_ctor is None and stack:
            ctor_match = _DARTDOC_CONSTRUCTOR_DECL.match(line)
            if ctor_match and ctor_match.group("type") == stack[-1][1]:
                current_ctor = (
                    _dartdoc_constructor_label(
                        ctor_match.group("type"), ctor_match.group("name")
                    ),
                    ctor_match.group("type"),
                    ctor_match.group("name"),
                )
                paren_depth = 0

        if current_ctor is not None:
            paren_depth += line.count("(") - line.count(")")
            if paren_depth <= 0:
                current_ctor = None
                paren_depth = 0

        depth += line.count("{") - line.count("}")
        while stack and depth <= stack[-1][0]:
            stack.pop()

    return enclosing, param_of


def _collect_dartdoc(src: str) -> tuple[dict, dict, dict, list]:
    """Bind every dartdoc block to the declaration it documents.

    A block attaches to the first thing below it that is not more documentation,
    skipping the blank lines, annotations and plain `//` comments Dart allows in
    between — and it attaches at that declaration's own granularity:

    - above ``library;``            -> the file
    - above a class/mixin/enum/...  -> that type
    - above a constructor           -> that constructor
    - above a constructor parameter -> the field it forwards to (``this.x``), or
                                       the parameter itself
    - anything else                 -> that member (field, method, getter, ...)

    Returns ``(library_doc, by_label, constructors, parameters)``. ``by_label`` is
    keyed by the LABEL the node will carry, so ``add_node`` picks a doc up without
    knowing which pass created the node. A label declared twice in one file —
    ``build`` in two widget classes — already resolves to a single node, so the
    first block wins, matching the ID collision that already exists.
    """
    lines = src.splitlines()
    enclosing, param_of = _dartdoc_structure(lines)
    library_doc: dict = {}
    by_label: dict[str, dict] = {}
    constructors: dict[str, tuple[str, str | None]] = {}
    parameters: list[tuple[str, str]] = []
    total = len(lines)
    i = 0

    while i < total:
        if _DARTDOC_LINE.match(lines[i]) is None:
            i += 1
            continue
        block: list[str] = []
        while i < total:
            match = _DARTDOC_LINE.match(lines[i])
            if match is None:
                break
            block.append(match.group(1))
            i += 1
        j = i
        while j < total:
            stripped = lines[j].strip()
            if stripped and not stripped.startswith("@") and not stripped.startswith("//"):
                break
            j += 1
        if j >= total:
            continue

        declaration = lines[j]
        parsed = _parse_dartdoc("\n".join(block))

        if _DARTDOC_LIBRARY_DECL.match(declaration):
            if not library_doc:
                library_doc = parsed
            continue

        owner_ctor = param_of[j]
        if owner_ctor is not None:
            forwarded = _DARTDOC_FORWARDED_PARAM.match(declaration)
            name_match = forwarded or _DARTDOC_PARAM_NAME.search(
                declaration.split("=", 1)[0]
            )
            if name_match is None:
                continue
            ctor_label, ctor_type, ctor_name = owner_ctor
            constructors.setdefault(ctor_label, (ctor_type, ctor_name))
            parameters.append((ctor_label, name_match.group(1)))
            by_label.setdefault(name_match.group(1), parsed)
            continue

        type_match = _DARTDOC_TYPE_DECL.match(declaration)
        if type_match:
            by_label.setdefault(type_match.group(1), parsed)
            continue

        ctor_match = _DARTDOC_CONSTRUCTOR_DECL.match(declaration)
        if ctor_match and ctor_match.group("type") == enclosing[j]:
            label = _dartdoc_constructor_label(
                ctor_match.group("type"), ctor_match.group("name")
            )
            constructors.setdefault(
                label, (ctor_match.group("type"), ctor_match.group("name"))
            )
            by_label.setdefault(label, parsed)
            continue

        member_match = _DARTDOC_MEMBER_DECL.search(declaration)
        if member_match is not None:
            by_label.setdefault(member_match.group(1), parsed)

    return library_doc, by_label, constructors, parameters


def extract_dart(path: Path) -> dict:
    """Extract classes, mixins, functions, imports, generic calls, and annotations from a .dart file using regex."""
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"error": f"cannot read {path}"}

    # Remove inline and multi-line comments while leaving string literals untouched to prevent stripping URLs/paths inside strings
    comment_string_pattern = re.compile(
        r'"""(?:\\.|[\s\S])*?"""'
        r"|'''(?:\\.|[\s\S])*?'''"
        r'|"(?:\\.|[^"\\])*"'
        r"|'(?:\\.|[^'\\])*'"
        r"|/\*[\s\S]*?\*/"
        r"|//[^\n]*"
    )
    def _comment_replace(match: re.Match) -> str:
        token = match.group(0)
        if token.startswith("/"):
            return ""
        return token
    src_clean = comment_string_pattern.sub(_comment_replace, src)

    # Recover the dartdoc the stripping above just deleted. Read from `src`,
    # not `src_clean`, and keep every later pass on the comment-free text.
    (library_doc, dartdoc_by_label,
     dartdoc_constructors, dartdoc_parameters) = _collect_dartdoc(src)

    stem = _file_stem(path)
    file_nid = _make_id(str(path))

    # Check if this is a part-of file and redirect to parent
    part_of_match = re.search(r"^\s*part\s+of\s+['\"]([^'\"]+)['\"]", src_clean, re.MULTILINE)
    is_part = False
    if part_of_match:
        parent_ref = part_of_match.group(1)
        if parent_ref.endswith(".dart"):
            try:
                parent_path = (path.parent / parent_ref).resolve()
                if parent_path.exists():
                    stem = _file_stem(parent_path)
                    file_nid = _make_id(str(parent_path))
                    is_part = True
            except Exception:
                pass

    nodes = []
    if not is_part:
        file_node = {"id": file_nid, "label": path.name, "file_type": "code",
                     "source_file": str(path), "source_location": None}
        if library_doc.get("doc"):
            file_node["doc"] = library_doc["doc"]
        nodes.append(file_node)
    edges = []
    defined: set[str] = set()
    node_by_id: dict[str, dict] = {}

    def add_node(nid: str, label: str, ftype: str = "code", source_file: str | None = str(path)) -> None:
        # Only a symbol DECLARED here can carry this file's dartdoc. Nodes minted
        # for referenced external types pass source_file=None, and a name collision
        # with a local symbol must not hand them its doc.
        doc = dartdoc_by_label.get(label, {}).get("doc") if source_file is not None else None
        if nid not in defined:
            node = {"id": nid, "label": label, "file_type": ftype,
                    "source_file": source_file, "source_location": None}
            if doc:
                node["doc"] = doc
            nodes.append(node)
            node_by_id[nid] = node
            defined.add(nid)
        elif doc:
            # An earlier pass already created this node under a different label
            # that carried no doc. IDs are normalized, so `_field` and `field`
            # are one node; without this the doc for the second label is dropped.
            node_by_id[nid].setdefault("doc", doc)

    def add_edge(src_id: str, tgt_id: str, relation: str, weight: float = 1.0, context: str | None = None) -> None:
        edge = {"source": src_id, "target": tgt_id, "relation": relation,
                "confidence": "EXTRACTED", "confidence_score": 1.0,
                "source_file": str(path), "source_location": None, "weight": weight}
        if context:
            edge["context"] = context
        edges.append(edge)

    def _split_types(text: str) -> list[str]:
        parts = []
        current = []
        depth = 0
        for char in text:
            if char == "<":
                depth += 1
                current.append(char)
            elif char == ">":
                depth -= 1
                current.append(char)
            elif char == "," and depth == 0:
                parts.append("".join(current).strip())
                current = []
            else:
                current.append(char)
        if current:
            parts.append("".join(current).strip())
        return [p for p in parts if p]

    def _find_matching_brace(text: str, start_pos: int) -> int:
        brace_count = 0
        in_double_quote = False
        in_single_quote = False
        escape = False

        first_brace = text.find("{", start_pos)
        if first_brace == -1:
            return len(text)

        brace_count = 1
        i = first_brace + 1
        n = len(text)
        while i < n:
            char = text[i]
            if escape:
                escape = False
                i += 1
                continue
            if char == "\\":
                escape = True
                i += 1
                continue
            if text[i:i+3] == '"""' and not in_single_quote:
                i += 3
                end = text.find('"""', i)
                i = end + 3 if end != -1 else n
                continue
            if text[i:i+3] == "'''" and not in_double_quote:
                i += 3
                end = text.find("'''", i)
                i = end + 3 if end != -1 else n
                continue
            if char == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
            elif char == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
            elif not in_double_quote and not in_single_quote:
                if char == "{":
                    brace_count += 1
                elif char == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        return i + 1
            i += 1
        return len(text)

    # 1. Classes, mixins, and enums declarations (with inheritance, mixins, interfaces, and generics)
    # Supports multiple combined modifiers (e.g., abstract base class, mixin class) without capturing "class" as a name
    class_pattern = r"^\s*(?:(?:abstract|sealed|base|interface|final|mixin)\s+)*(?:class|mixin|enum|extension\s+type)\s+(\w+)"
    for m in re.finditer(class_pattern, src_clean, re.MULTILINE):
        class_name = m.group(1)
        class_nid = _make_id(stem, class_name)
        add_node(class_nid, class_name)
        add_edge(file_nid, class_nid, "defines")

        # Manually parse extends/on, with, and implements in header to handle nested generics brackets balanced
        start_idx = m.end()
        rest = src_clean[start_idx : start_idx + 500]

        # Skip class generic parameters
        if rest.lstrip().startswith("<"):
            offset = rest.find("<")
            depth = 1
            i = offset + 1
            while i < len(rest) and depth > 0:
                if rest[i] == "<": depth += 1
                elif rest[i] == ">": depth -= 1
                i += 1
            rest = rest[i:]

        # Skip primary constructor (e.g. extension type MyExt(int id))
        if rest.lstrip().startswith("("):
            offset = rest.find("(")
            depth = 1
            i = offset + 1
            while i < len(rest) and depth > 0:
                if rest[i] == "(": depth += 1
                elif rest[i] == ")": depth -= 1
                i += 1
            rest = rest[i:]

        header_end = rest.find("{")
        if header_end == -1:
            header_end = rest.find(";")
        if header_end == -1:
            header_end = len(rest)
        header = rest[:header_end]

        base_class = None
        generics = None
        mixins_list = []
        interfaces_list = []

        # Parse extends or on
        extends_m = re.search(r"^\s*(?:extends|on)\s+([a-zA-Z0-9_.]+)", header)
        if extends_m:
            base_class = extends_m.group(1)
            rest_header = header[extends_m.end():]
            if rest_header.strip().startswith("<"):
                start_idx = rest_header.find("<")
                depth = 1
                i = start_idx + 1
                while i < len(rest_header) and depth > 0:
                    if rest_header[i] == "<":
                        depth += 1
                    elif rest_header[i] == ">":
                        depth -= 1
                        if depth == 0:
                            generics = rest_header[start_idx + 1 : i]
                            break
                    i += 1
                if generics is not None:
                    header = rest_header[i + 1:]
                else:
                    header = rest_header
            else:
                header = rest_header

        # Parse with
        with_m = re.search(r"^\s*with\s+", header)
        if with_m:
            rest_header = header[with_m.end():]
            impl_idx = rest_header.find("implements")
            if impl_idx != -1:
                mixins_str = rest_header[:impl_idx]
                header = rest_header[impl_idx:]
            else:
                mixins_str = rest_header
                header = ""
            mixins_list = _split_types(mixins_str)

        # Parse implements
        impl_m = re.search(r"^\s*implements\s+", header)
        if impl_m:
            interfaces_list = _split_types(header[impl_m.end():])

        # Map extends inheritance relation
        if base_class:
            base_nid = _make_id(base_class)
            add_node(base_nid, base_class, source_file=None)
            add_edge(class_nid, base_nid, "inherits")

            # Map generic type arguments (e.g. MyBloc extends Bloc<MyEvent, MyState>)
            if generics:
                for gen in _split_types(generics):
                    gen_clean = gen.split("<")[0].strip()
                    if gen_clean not in {"String", "int", "double", "bool", "num", "dynamic", "Object", "void"}:
                        gen_nid = _make_id(gen_clean)
                        add_node(gen_nid, gen_clean, source_file=None)
                        add_edge(class_nid, gen_nid, "references")

        # Map mixins
        for mixin in mixins_list:
            mixin_clean = mixin.split("<")[0].strip()
            mixin_nid = _make_id(mixin_clean)
            add_node(mixin_nid, mixin_clean, source_file=None)
            add_edge(class_nid, mixin_nid, "mixes_in")

        # Map interfaces
        for interface in interfaces_list:
            interface_clean = interface.split("<")[0].strip()
            interface_nid = _make_id(interface_clean)
            add_node(interface_nid, interface_clean, source_file=None)
            add_edge(class_nid, interface_nid, "implements")

        # Extract class body for precise framework dependencies and event handling
        start_idx = m.start()
        brace_pos = src_clean.find("{", start_idx)
        semi_pos = src_clean.find(";", start_idx)

        has_body = brace_pos != -1
        if has_body and semi_pos != -1 and semi_pos < brace_pos:
            has_body = False

        if has_body:
            end_pos = _find_matching_brace(src_clean, start_idx)
            class_body = src_clean[brace_pos:end_pos]

            # Bloc event registration: on<MyEvent>()
            for em in re.finditer(r"\bon<(\w+)>\s*\(", class_body):
                event_name = em.group(1)
                event_nid = _make_id(event_name)
                add_node(event_nid, event_name, source_file=None)
                add_edge(class_nid, event_nid, "calls", context="bloc_event")

            # Bloc state emissions: emit(MyState) or yield MyState
            for sm in re.finditer(r"\b(?:emit|yield)\s*\(?\s*(?:const\s+)?([A-Z]\w*)\b", class_body):
                state_name = sm.group(1)
                if state_name not in {"String", "List", "Map", "Set", "Future", "Stream", "Object"}:
                    state_nid = _make_id(state_name)
                    add_node(state_nid, state_name, source_file=None)
                    add_edge(class_nid, state_nid, "calls", context="emit_state")

            # Bloc event additions: widget.add(MyEvent()) or bloc.add(MyEvent())
            for am in re.finditer(r"\b(?:\w*[Bb]loc\w*|context\.read<\w+>\(\))\.add\(\s*(?:const\s+)?([A-Z]\w*)\b", class_body):
                event_name = am.group(1)
                if event_name not in {"String", "List", "Map", "Set", "Future", "Stream", "Object"}:
                    event_nid = _make_id(event_name)
                    add_node(event_nid, event_name, source_file=None)
                    add_edge(class_nid, event_nid, "calls", context="bloc_add_event")

            # Riverpod provider references: ref.watch(provider)
            for rm in re.finditer(r"\bref\.(?:watch|read|listen)\s*\(\s*(\w+)\b", class_body):
                provider_name = rm.group(1)
                provider_nid = _make_id(provider_name)
                add_node(provider_nid, provider_name, source_file=None)
                add_edge(class_nid, provider_nid, "references", context="riverpod_reference")

            # Widget to Bloc references: BlocBuilder<MyBloc, ...>
            for bm in re.finditer(r"\bBloc(?:Builder|Listener|Consumer|Provider|Selector)\s*<\s*([a-zA-Z0-9_]+)\b", class_body):
                bloc_name = bm.group(1)
                if bloc_name not in {"String", "int", "double", "bool", "num", "dynamic", "Object", "void"}:
                    bloc_nid = _make_id(bloc_name)
                    add_node(bloc_nid, bloc_name, source_file=None)
                    add_edge(class_nid, bloc_nid, "references", context="bloc_widget_binding")

            # context.read<MyBloc>() or BlocProvider.of<MyBloc>(context)
            for lm in re.finditer(r"\b(?:read|watch|select|of)\s*<([a-zA-Z0-9_]+)>", class_body):
                bloc_name = lm.group(1)
                if bloc_name not in {"String", "int", "double", "bool", "num", "dynamic", "Object", "void"}:
                    bloc_nid = _make_id(bloc_name)
                    add_node(bloc_nid, bloc_name, source_file=None)
                    add_edge(class_nid, bloc_nid, "references", context="bloc_lookup")

    # 2. Annotations mapping (class, mixin, enum, or function level annotations)
    # Support: @riverpod, @Riverpod(...), @injectable, @singleton, @RoutePage(), @HiveType(typeId: 0), @RestApi()
    # Matches `@annotation` and links it to the next class/mixin/enum/function declaration in the file
    annotation_pattern = r"@(\w+)(?:\([^)]*\))?"
    for am in re.finditer(annotation_pattern, src_clean):
        annotation_name = am.group(1)
        if annotation_name in {"override", "deprecated", "required", "protected", "mustCallSuper"}:
            continue
        annotation_pos = am.end()
        intervening_text = src_clean[annotation_pos : annotation_pos + 300]

        class_m = re.search(r"^\s*(?:(?:abstract|sealed|base|interface|final|mixin)\s+)*(?:class|mixin|enum|extension\s+type)\s+(\w+)", intervening_text, re.MULTILINE)
        func_m = re.search(r"^\s*(?:factory\s+|static\s+|async\s+|external\s+|abstract\s+)?(?:\([^)]+\)|[a-zA-Z0-9_<>,.?]+)(?:\s+[a-zA-Z0-9_<>,.?]+){0,3}\s+(\w+)\s*\(", intervening_text, re.MULTILINE)

        target_nid = None
        target_name = None
        target_type = None

        if class_m and func_m:
            if class_m.start() < func_m.start():
                target_name = class_m.group(1)
                target_type = "class"
                target_nid = _make_id(stem, target_name)
            else:
                target_name = func_m.group(1)
                target_type = "function"
                target_nid = _make_id(stem, target_name)
        elif class_m:
            target_name = class_m.group(1)
            target_type = "class"
            target_nid = _make_id(stem, target_name)
        elif func_m:
            target_name = func_m.group(1)
            target_type = "function"
            target_nid = _make_id(stem, target_name)

        if target_nid and target_name:
            actual_intervening = intervening_text[:min(class_m.start() if class_m else 300, func_m.start() if func_m else 300)]
            if ";" not in actual_intervening and "}" not in actual_intervening and "{" not in actual_intervening:
                annotation_nid = _make_id("annotation", annotation_name.lower())
                add_node(annotation_nid, f"@{annotation_name}", ftype="concept", source_file=None)
                add_edge(target_nid, annotation_nid, "configures")

                # Riverpod specific provider generation mapping (supports camelCase class and functional providers)
                if annotation_name.lower() == "riverpod":
                     if target_type == "class":
                         provider_name = target_name[0].lower() + target_name[1:] + "Provider" if len(target_name) > 1 else target_name.lower() + "Provider"
                     else:
                         provider_name = target_name + "Provider"
                     provider_nid = _make_id(provider_name)
                     add_node(provider_nid, provider_name, ftype="concept", source_file=str(path))
                     add_edge(target_nid, provider_nid, "defines", context="riverpod_provider")

    # 2.5 Typedefs (Type Aliases)
    typedef_pattern = r"^\s*typedef\s+(\w+)\s*(?:<[^>]+>)?\s*=\s*([a-zA-Z0-9_<>,.?\s]+);"
    for m in re.finditer(typedef_pattern, src_clean, re.MULTILINE):
        typedef_name = m.group(1)
        target_type = m.group(2).split("<")[0].split(".")[-1].strip()
        if target_type not in {"String", "int", "double", "bool", "num", "dynamic", "Object", "List", "Map", "Set", "void", "Function"}:
            typedef_nid = _make_id(stem, typedef_name)
            add_node(typedef_nid, typedef_name)
            add_edge(file_nid, typedef_nid, "defines")
            target_nid = _make_id(target_type)
            add_node(target_nid, target_type, source_file=None)
            add_edge(typedef_nid, target_nid, "references", context="typedef")

    # 3. Extensions (extension MyExt on MyClass)
    ext_pattern = r"^\s{0,4}extension\s+(\w+)?(?:<[^>]+>)?\s+on\s+(\w+)"
    for m in re.finditer(ext_pattern, src_clean, re.MULTILINE):
        ext_name = m.group(1) or f"{stem}_anonymous_extension"
        target_class = m.group(2)

        ext_nid = _make_id(stem, ext_name)
        label = m.group(1) or f"Extension on {target_class}"
        add_node(ext_nid, label)
        add_edge(file_nid, ext_nid, "defines")

        target_nid = _make_id(target_class)
        add_node(target_nid, target_class, source_file=None)
        add_edge(ext_nid, target_nid, "extends")

    # 4. Top-level and class-level variable declarations (generic variables, records, late, and destructuring)
    # Restrict indentation to 0-2 spaces to avoid matching local variables inside functions or switch expressions
    var_pattern = r"^\s{0,2}(?:late\s+)?(?:(?:final|const|var)\s+)?(?:\([^)]+\)\s+|([a-zA-Z0-9_<>,.?]+(?:\s+[a-zA-Z0-9_<>,.?]+){0,3})\s+)?(?:(\w+)|(?:\w+\s*)?\(([^)]+)\))\s*(?:=|$|;)"
    for m in re.finditer(var_pattern, src_clean, re.MULTILINE):
        var_type = m.group(1)
        single_name = m.group(2)
        destructured_names = m.group(3)

        if not re.match(r"^\s*(?:late|final|const|var)\b", m.group(0)) and not var_type:
            continue

        if single_name:
            if single_name not in {"if", "for", "while", "switch", "catch", "return"}:
                var_nid = _make_id(stem, single_name)
                add_node(var_nid, single_name)
                add_edge(file_nid, var_nid, "defines")

                if var_type and var_type not in {"String", "int", "double", "bool", "num", "dynamic", "Object", "List", "Map", "Set", "void"}:
                    clean_type = var_type.split("<")[0].split(".")[-1].strip()
                    type_nid = _make_id(clean_type)
                    add_node(type_nid, clean_type, source_file=None)
                    add_edge(file_nid, type_nid, "references", context="variable_type")
        elif destructured_names:
            for name in [n.strip() for n in destructured_names.split(",") if n.strip()]:
                if ":" in name:
                    name = name.split(":")[-1].strip()
                if re.match(r"^[a-zA-Z_]\w*$", name) and not re.match(r"^[A-Z]", name):
                    if name not in {"if", "for", "while", "switch", "catch", "return"}:
                        var_nid = _make_id(stem, name)
                        add_node(var_nid, name)
                        add_edge(file_nid, var_nid, "defines")

    # 5. Top-level and member functions/methods (supports typed/generic/record return types and Riverpod/Bloc references)
    # Restrict indentation to 0-2 spaces to avoid matching nested local functions or methods inside multiline switch statements
    method_pattern = r"^\s{0,2}(?:factory\s+|static\s+|async\s+|external\s+|abstract\s+)?(?:\([^)]+\)|[a-zA-Z0-9_<>,.?]+)(?:\s+[a-zA-Z0-9_<>,.?]+){0,3}\s+(\w+(?:\.\w+)?)\s*\("
    for m in re.finditer(method_pattern, src_clean, re.MULTILINE):
        raw_name = m.group(1)
        name = raw_name.split(".")[-1]
        if name in {"if", "for", "while", "switch", "catch", "return", "void", "dynamic", "final", "const", "get", "set"}:
            continue
        if re.match(r"^[A-Z]", name):
            continue
        nid = _make_id(stem, name)
        add_node(nid, name)
        add_edge(file_nid, nid, "defines")

        # Get function body using matching brace to extract Riverpod reference patterns
        start_idx = m.start()
        brace_pos = src_clean.find("{", start_idx)
        semi_pos = src_clean.find(";", start_idx)
        arrow_pos = src_clean.find("=>", start_idx)

        has_body = brace_pos != -1
        if has_body and semi_pos != -1 and semi_pos < brace_pos:
            has_body = False
        if has_body and arrow_pos != -1 and arrow_pos < brace_pos:
            has_body = False

        if has_body:
            end_pos = _find_matching_brace(src_clean, start_idx)
            func_body = src_clean[brace_pos:end_pos]

            # Extract Riverpod provider references: ref.watch(provider)
            for rm in re.finditer(r"\bref\.(?:watch|read|listen)\s*\(\s*(\w+)\b", func_body):
                provider_name = rm.group(1)
                provider_nid = _make_id(provider_name)
                add_node(provider_nid, provider_name, source_file=None)
                add_edge(nid, provider_nid, "references", context="riverpod_reference")

            # Extract Bloc event additions: widget.add(MyEvent()) or bloc.add(MyEvent())
            for am in re.finditer(r"\b(?:\w*[Bb]loc\w*|context\.read<\w+>\(\))\.add\(\s*(?:const\s+)?([A-Z]\w*)\b", func_body):
                event_name = am.group(1)
                if event_name not in {"String", "List", "Map", "Set", "Future", "Stream", "Object"}:
                    event_nid = _make_id(event_name)
                    add_node(event_nid, event_name, source_file=None)
                    add_edge(nid, event_nid, "calls", context="bloc_add_event")

            # context.read<MyBloc>() or BlocProvider.of<MyBloc>(context)
            for lm in re.finditer(r"\b(?:read|watch|select|of)\s*<([a-zA-Z0-9_]+)>", func_body):
                bloc_name = lm.group(1)
                if bloc_name not in {"String", "int", "double", "bool", "num", "dynamic", "Object", "void"}:
                    bloc_nid = _make_id(bloc_name)
                    add_node(bloc_nid, bloc_name, source_file=None)
                    add_edge(nid, bloc_nid, "references", context="bloc_lookup")

            # Universal Navigation Patters (GoRouter, AutoRoute, Navigator)
            for nm in re.finditer(r"\b(?:go|push|goNamed|pushNamed|replace|replaceNamed)\s*\(\s*(?:context\s*,\s*)?['\"]([a-zA-Z0-9_/?=&%-]+)['\"]", func_body):
                route_path = nm.group(1)
                route_nid = _make_id("route", route_path.replace("/", "_").replace("?", "_").replace("=", "_").replace("&", "_"))
                add_node(route_nid, f"Route {route_path}", ftype="concept", source_file=None)
                add_edge(nid, route_nid, "navigates", context="route_path")

            for cm in re.finditer(r"\b(?:go|push|goNamed|pushNamed|replace|replaceNamed)\s*\(\s*(?:context\s*,\s*)?([A-Z][a-zA-Z0-9_]*\.[a-zA-Z0-9_]+)", func_body):
                route_const = cm.group(1)
                route_nid = _make_id("route", route_const.replace(".", "_"))
                add_node(route_nid, route_const, ftype="concept", source_file=None)
                add_edge(nid, route_nid, "navigates", context="route_const")

            for om in re.finditer(r"\b(?:push|replace)\s*\(\s*(?:context\s*,\s*)?.*?\b([A-Z]\w*(?:Route|Screen|Page))\b", func_body):
                route_class = om.group(1)
                route_nid = _make_id(route_class)
                add_node(route_nid, route_class, source_file=None)
                add_edge(nid, route_nid, "navigates", context="route_object")

    # 6. Imports and Exports
    for m in re.finditer(r"""^\s*import\s+['"]([^'"]+)['"]""", src_clean, re.MULTILINE):
        pkg = m.group(1)
        tgt_nid = _make_id(pkg)
        add_node(tgt_nid, pkg, source_file=None)
        add_edge(file_nid, tgt_nid, "imports")

    for m in re.finditer(r"""^\s*export\s+['"]([^'"]+)['"]""", src_clean, re.MULTILINE):
        pkg = m.group(1)
        tgt_nid = _make_id(pkg)
        add_node(tgt_nid, pkg, source_file=None)
        add_edge(file_nid, tgt_nid, "exports")

    # 7. Generic Invocations / Type Lookups (Universal Dependency Lookup)
    # Matches any method call with type parameters: methodName<Type>() or object.methodName<Type>()
    # Automatically extracts GetIt, Injectable, Riverpod, Provider, BlocProvider, and InheritedWidget type lookups!
    generic_call_pattern = r"\b\w+<([a-zA-Z0-9_.]+(?:<[a-zA-Z0-9_.,\s<>]+>)?)\s*>\s*\("
    type_blacklist = {"String", "int", "double", "bool", "num", "dynamic", "Object", "List", "Map", "Set", "Future", "Stream", "void"}
    for m in re.finditer(generic_call_pattern, src_clean):
        type_name = m.group(1).split(".")[-1].strip()
        clean_name = type_name.split("<")[0].strip()
        if clean_name not in type_blacklist:
            target_nid = _make_id(clean_name)
            add_node(target_nid, clean_name, source_file=None)
            add_edge(file_nid, target_nid, "references", context="type_lookup")

    # 8. Dartdoc-declared API surface
    # A documented constructor and its documented parameters are API surface the
    # author chose to describe, but no earlier pass mints a node for either: the
    # method pass skips any name starting uppercase (so every constructor), and
    # parameter lists are never walked. Create them here — only when a doc block
    # points at them, so this stays proportional to the documentation rather than
    # minting a node for every constructor in the corpus.
    dartdoc_nid_by_label: dict[str, str] = {}
    for ctor_label, (ctor_type, ctor_name) in dartdoc_constructors.items():
        type_nid = _make_id(stem, ctor_type)
        if type_nid not in defined:
            continue
        ctor_nid = _make_id(stem, _dartdoc_constructor_key(ctor_type, ctor_name))
        if ctor_nid in (type_nid, file_nid):
            continue
        add_node(ctor_nid, ctor_label)
        add_edge(type_nid, ctor_nid, "contains", context="dartdoc_constructor")
        dartdoc_nid_by_label[ctor_label] = ctor_nid

    for ctor_label, param_label in dartdoc_parameters:
        ctor_nid = dartdoc_nid_by_label.get(ctor_label)
        if ctor_nid is None:
            continue
        param_nid = _make_id(stem, param_label)
        if param_nid in (ctor_nid, file_nid):
            continue
        # A `this.x` parameter forwards to a field that already has a node, so
        # this reuses it rather than declaring a second owner for the same prop —
        # hence `references`, not `contains`.
        add_node(param_nid, param_label)
        add_edge(ctor_nid, param_nid, "references", context="dartdoc_parameter")

    # 9. Dartdoc cross-references
    # Only the parts a human curated as a relation become edges. `See also:` is an
    # explicit "these belong together" list; a {@tool} block names the runnable file
    # that shows how to use the symbol; {@template}/{@macro} is dartdoc's own
    # transclusion, so linking them makes reused documentation traversable across
    # files and packages. Inline `[Foo]` mentions in prose are deliberately NOT
    # emitted: on Flutter's src/material they add ~6.6k edges (+16%) that mostly
    # restate relations the AST passes above already found.
    # Every edge is tagged `context="dartdoc_*"` so a doc-stated relation stays
    # distinguishable from one proven by code (#2270).
    def add_dartdoc_edges(owner_nid: str, doc: dict) -> None:
        for name in doc["see_also"]:
            if name in _DARTDOC_REF_NOISE:
                continue
            if name[:1].isupper():
                target_nid = _make_id(name)          # a type: resolve globally
            else:
                target_nid = _make_id(stem, name)    # a top-level function declared here
                if target_nid not in defined:
                    continue                         # a bare member ref resolves to nothing
            if target_nid == owner_nid:
                continue
            add_node(target_nid, name, source_file=None)
            add_edge(owner_nid, target_nid, "references", context="dartdoc_see_also")

        for sample in doc["samples"]:
            sample_nid = _make_id(sample)
            add_node(sample_nid, sample, source_file=None)
            add_edge(owner_nid, sample_nid, "references", context="dartdoc_sample")

        for template_id in doc["templates"]:
            template_nid = _make_id("dartdoc", template_id)
            add_node(template_nid, f"{{@template {template_id}}}", ftype="concept")
            add_edge(owner_nid, template_nid, "defines", context="dartdoc_template")

        for macro_id in doc["macros"]:
            template_nid = _make_id("dartdoc", macro_id)
            add_node(template_nid, f"{{@template {macro_id}}}", ftype="concept", source_file=None)
            add_edge(owner_nid, template_nid, "references", context="dartdoc_macro")

    if not is_part and library_doc:
        add_dartdoc_edges(file_nid, library_doc)
    for owner_label, doc in dartdoc_by_label.items():
        owner_nid = dartdoc_nid_by_label.get(owner_label) or _make_id(stem, owner_label)
        if owner_nid in defined:
            add_dartdoc_edges(owner_nid, doc)

    return {"nodes": nodes, "edges": edges}
