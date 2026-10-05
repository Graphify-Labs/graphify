"""QML-owned overlays for already accepted JS files; ordinary JS facts stay intact."""
from __future__ import annotations

import hashlib
from pathlib import Path

from graphify.extractors.qml_ast import failure
from graphify.extractors.qml_expressions import ExpressionCollector
from graphify.extractors.qml_facts import FactBuilder, field, qml_metadata, text
from graphify.extractors.qml_js_scopes import FUNCTIONS, local_declarations, reassigned_names
from graphify.extractors.qml_script_syntax import parse_script
from graphify.qml_resolution_types import relative_reference


def _literal(node, source):
    value = text(node, source)
    return value[1:-1] if value[:1] in {"'", '"'} and value[-1:] == value[:1] and "\\" not in value else ""


def _exports(program, source):
    """Explicit module exports control importer visibility; locals stay file-owned."""
    exports = {}
    for statement in program.named_children:
        if statement.type != "export_statement":
            continue
        if statement.child_by_field_name("source"):
            # Re-exports require an explicit module-export graph, not a local
            # same-name fallback. This profile leaves them unavailable.
            continue
        declaration = statement.child_by_field_name("declaration")
        if declaration:
            if declaration.type in FUNCTIONS:
                name = field(declaration, "name", source)
                exports.setdefault(name, []).append("default" if text(statement, source).startswith("export default") else name)
            else:
                for declarator in declaration.named_children:
                    if declarator.type == "variable_declarator":
                        from graphify.extractors.qml_js_scopes import bound_names
                        for name in bound_names(declarator.child_by_field_name("name"), source):
                            exports.setdefault(name, []).append(name)
        for clause in statement.named_children:
            if clause.type == "export_clause":
                for specifier in clause.named_children:
                    name = field(specifier, "name", source)
                    alias = field(specifier, "alias", source) or name
                    exports.setdefault(name, []).append(alias)
    return exports


def _script_imports(facts, program, directives, owner):
    for directive in directives:
        if directive["kind"] != "import":
            continue
        node = facts.add("script_import", directive["qualifier"], program, owner,
                         semantic_key=str(directive["start_byte"]), script_file=facts.relative_file,
                         value=directive["value"], qualifier=directive["qualifier"], import_kind="namespace")
        node["label"] = "QML script import: " + directive["qualifier"]
        node["source_location"] = f'L{directive["row"] + 1}'
        # The directive is masked only for parsing; preserve the original source span.
        md = qml_metadata(node)
        md["span"] = {"start_byte": directive["start_byte"], "end_byte": directive["end_byte"],
                      "start_row": directive["row"], "start_column": 0,
                      "end_row": directive["row"], "end_column": directive["end_byte"] - directive["start_byte"]}
        from graphify.extractors.qml_facts import encode_metadata
        node["metadata"]["qml"] = encode_metadata({k: v for k, v in md.items() if k != "raw_values"})
    for statement in program.named_children:
        if statement.type != "import_statement":
            continue
        value = _literal(statement.child_by_field_name("source"), facts.source)
        for clause in statement.named_children:
            if clause.type != "import_clause":
                continue
            for binding in clause.named_children:
                if binding.type == "namespace_import":
                    names = [(text(binding.named_children[-1], facts.source), "namespace", "")]
                elif binding.type == "identifier":
                    names = [(text(binding, facts.source), "named", "default")]
                elif binding.type == "named_imports":
                    names = [(field(s, "alias", facts.source) or field(s, "name", facts.source),
                              "named", field(s, "name", facts.source)) for s in binding.named_children]
                else:
                    names = []
                for name, kind, exported in names:
                    node = facts.add("script_import", name, binding, owner,
                              semantic_key=f"{binding.start_byte}:{name}", script_file=facts.relative_file,
                              value=value, qualifier=name, import_kind=kind, exported_name=exported)
                    node["label"] = "QML script import: " + name


def _overlay(path: Path, root: Path):
    source, program, directives = parse_script(path)
    facts = FactBuilder(path, root, source)
    library = any(item["kind"] == "pragma" for item in directives)
    owner = facts.add("script_file", path.name, program, script_file=facts.relative_file,
                      pragma_library=library, script_profile="module" if path.suffix.lower() == ".mjs" else "classic")
    owner["label"] = "QML script: " + path.name
    _script_imports(facts, program, directives, owner)
    exported, declarations, reassigned = _exports(program, source), [], reassigned_names(program, source)
    for statement in program.named_children:
        declaration = statement.child_by_field_name("declaration") if statement.type == "export_statement" else statement
        if declaration is None:
            continue
        if declaration.type in FUNCTIONS:
            declarations.append((field(declaration, "name", source), declaration))
        elif declaration.type in {"lexical_declaration", "variable_declaration"}:
            for variable in declaration.named_children:
                if variable.type != "variable_declarator":
                    continue
                function = variable.child_by_field_name("value")
                if function is not None and function.type in FUNCTIONS:
                    from graphify.extractors.qml_js_scopes import bound_names
                    declarations.extend((name, function) for name in bound_names(variable.child_by_field_name("name"), source))
    collector, environment = ExpressionCollector(facts), {}
    for name, syntax in declarations:
        key = hashlib.sha256(f'{name}:{syntax.start_byte}'.encode()).hexdigest()
        node = facts.add("qml_script_function", name, syntax, owner, semantic_key=key,
                         script_file=facts.relative_file, static_callable=name not in reassigned,
                         export_names=exported.get(name, []) if path.suffix.lower() == ".mjs" else [name])
        node["label"] = "QML script: " + (name or "default")
        environment[name] = node["id"] if name not in reassigned else ""
        collector.functions[syntax.start_byte, owner["id"]] = node
    # Top-level values also shadow names; no QML document's IDs leak into a script.
    for name, _ in local_declarations(program, source):
        environment.setdefault(name, "")
    for (_, syntax), node in zip(declarations, [n for n in facts.nodes if qml_metadata(n).get("kind") == "qml_script_function"]):
        collector.function_body(syntax, node, environment)
    for statement in program.named_children:
        if statement.type not in {"import_statement", "export_statement"} | FUNCTIONS:
            collector.scan(statement, owner, environment)
    return {"nodes": facts.nodes, "edges": facts.edges}


def collect_qml_scripts(paths, per_file, *, root: Path) -> None:
    """Only enrich accepted imports, including accepted literal script dependencies.

    Never discover paths, load network resources or alter shared JS extraction.
    Failures attach to the owning accepted result so publication safety can reject.
    """
    if not any(qml_metadata(node).get("kind") in {"import", "export"}
               for result in per_file if result for node in result.get("nodes", [])):
        return
    accepted = {}
    anchor = Path(root).resolve()
    for path, result in zip(paths, per_file):
        if not result or Path(path).suffix.lower() not in {".js", ".mjs"}:
            continue
        try:
            relative = Path(path).resolve().relative_to(anchor).as_posix()
        except ValueError:
            continue
        accepted[relative] = Path(path), result
    wanted = set()
    for path, result in zip(paths, per_file):
        if not result:
            continue
        try:
            source = Path(path).resolve().relative_to(anchor).as_posix()
        except ValueError:
            continue
        for node in result.get("nodes", []):
            md = qml_metadata(node)
            if md.get("kind") == "import" and md.get("import_kind") == "script":
                target = relative_reference(source, md.get("value") or "")
                if target in accepted:
                    wanted.add(target)
            elif md.get("kind") == "export" and md.get("export_kind") == "script":
                target = relative_reference(source, md.get("target_path") or "")
                if target in accepted:
                    wanted.add(target)
    visited = set()
    while wanted - visited:
        name = sorted(wanted - visited)[0]
        visited.add(name)
        path, result = accepted[name]
        if len(visited) > 256:
            result.setdefault("qml_failures", []).append({"code": "QML_SCRIPT_LIMIT", "source_file": name})
            return
        try:
            overlay = _overlay(path, Path(root))
        except Exception as exc:
            failed = failure(path, Path(root), exc)
            result.setdefault("qml_failures", []).extend(failed["qml_failures"])
            result.setdefault("diagnostics", []).extend(failed["diagnostics"])
            continue
        result.setdefault("nodes", []).extend(overlay["nodes"])
        result.setdefault("edges", []).extend(overlay["edges"])
        for node in overlay["nodes"]:
            md = qml_metadata(node)
            if md.get("kind") == "script_import":
                target = relative_reference(name, md.get("value") or "")
                if target in accepted:
                    wanted.add(target)
