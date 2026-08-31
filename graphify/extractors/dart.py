"""Dart extractor. Moved verbatim from graphify/extract.py."""
from __future__ import annotations

import re

from pathlib import Path
from graphify.extractors.base import _file_stem, _make_id


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
        nodes.append({"id": file_nid, "label": path.name, "file_type": "code",
                      "source_file": str(path), "source_location": None})
    edges = []
    defined: set[str] = set()

    def add_node(nid: str, label: str, ftype: str = "code", source_file: str | None = str(path)) -> None:
        if nid not in defined:
            nodes.append({"id": nid, "label": label, "file_type": ftype,
                          "source_file": source_file, "source_location": None})
            defined.add(nid)

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

    return {"nodes": nodes, "edges": edges}
