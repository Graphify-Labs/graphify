"""Clojure structural extractor."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from graphify.extractors.base import _make_id

# Separators that always *mean* "_" in a Clojure name, so rewriting them loses
# nothing: kebab-case words, namespace dots, and the alias slash. `_` itself is
# not idiomatic inside a Clojure symbol, which is what makes the mapping safe.
_BENIGN_SEPARATORS = str.maketrans({"-": "_", ".": "_", "/": "_"})


def _clojure_id(*parts: str) -> str:
    """Build a canonical ID that preserves the distinctions Clojure makes.

    ``normalize_id`` casefolds and collapses every non-word run to ``_``, which
    erases two things Clojure treats as significant: symbol case (``Foo`` vs
    ``foo``) and the sigils that separate a predicate or mutating name from its
    plain counterpart — ``live?``/``live``, ``save!``/``save``, ``x*``/``x``.
    Both pairs are ordinary in real code (``live?``/``live`` in one namespace is
    what first tripped this), and an ID built by normalization alone fuses them
    into a single node, so two different definitions collide.

    Only the separators in ``_BENIGN_SEPARATORS`` are treated as
    information-preserving. Any *other* divergence between the exact name and
    its normalized form means the ID cannot round-trip, so the exact name is
    pinned with a short digest. Names that normalize faithfully — the common
    case, including every kebab-case function and dotted namespace — keep their
    readable ID, so only the genuinely ambiguous ones pay for the disambiguation.
    """
    node_id = _make_id(*parts)
    # Mirror make_id's join (per-part strip, falsy parts dropped) and
    # normalize_id's trailing collapse/strip, but rewrite ONLY the benign
    # separators. Whatever still differs from node_id is information that
    # normalization destroyed — including case, which node_id casefolds away.
    joined = "_".join(p.strip("_.") for p in parts if p)
    faithful = joined.translate(_BENIGN_SEPARATORS)
    faithful = re.sub(r"_+", "_", faithful).strip("_")
    if faithful == node_id:
        return node_id
    digest = hashlib.sha1(
        "\0".join(parts).encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()[:8]
    return _make_id(node_id, "sym", digest)


def extract_clojure(path: Path) -> dict:
    """Extract Clojure namespaces, definitions, dependencies, and local calls."""
    try:
        import tree_sitter_clojure_orchard as tsclojure
        from tree_sitter import Language, Parser
    except ImportError:
        return {
            "nodes": [],
            "edges": [],
            "error": "tree-sitter-clojure-orchard not installed",
        }

    try:
        source = path.read_bytes()
        root = Parser(Language(tsclojure.language())).parse(source).root_node
    except Exception as exc:
        return {"nodes": [], "edges": [], "error": str(exc)}

    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    nodes_by_id: dict[str, dict] = {}
    edges_by_key: dict[tuple[str, str, str, str | None], dict] = {}
    unconditional_node_ids: set[str] = set()
    unconditional_edge_keys: set[tuple[str, str, str, str | None]] = set()
    namespace_nid: str | None = None
    namespace_name: str | None = None
    function_bodies: list[tuple[str, list[Any], str | None]] = []
    definition_ids_by_name: dict[str, str] = {}
    type_implementation_forms: list[tuple[str, Any, str | None]] = []
    defmethod_implementations: list[tuple[str, str, int, str | None]] = []

    definition_heads = frozenset({
        "def",
        "defonce",
        "defn",
        "defn-",
        "defmacro",
        "defmulti",
        "defmethod",
        "defprotocol",
        "defrecord",
        "deftype",
    })
    callable_heads = frozenset({"defn", "defn-", "defmacro", "defmethod"})
    type_heads = frozenset({"defprotocol", "defrecord", "deftype"})
    skipped_call_heads = frozenset({
        ".",
        "..",
        "and",
        "case",
        "catch",
        "comment",
        "cond",
        "cond->",
        "cond->>",
        "def",
        "defmacro",
        "defmethod",
        "defmulti",
        "defn",
        "defn-",
        "defonce",
        "defprotocol",
        "defrecord",
        "deftype",
        "do",
        "doseq",
        "fn",
        "for",
        "if",
        "import",
        "let",
        "loop",
        "ns",
        "or",
        "quote",
        "recur",
        "require",
        "try",
        "when",
        "when-let",
        "when-not",
    })

    def node_text(node: Any) -> str:
        return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    def named_children(node: Any) -> list[Any]:
        return [child for child in node.children if child.is_named]

    def form_values(node: Any) -> list[Any]:
        return list(node.children_by_field_name("value"))

    def symbol_text(node: Any) -> str:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return node_text(node)
        name = node_text(name_node)
        namespace_node = node.child_by_field_name("namespace")
        if namespace_node is None:
            return name
        return f"{node_text(namespace_node)}/{name}"

    def form_head(node: Any) -> str | None:
        if node.type != "list_lit":
            return None
        values = form_values(node)
        if not values or values[0].type not in {"sym_lit", "kwd_lit"}:
            return None
        return symbol_text(values[0]) if values[0].type == "sym_lit" else node_text(values[0])

    def first_symbol(children: list[Any], start: int = 0) -> tuple[str | None, Any | None]:
        for child in children[start:]:
            if child.type == "sym_lit":
                return symbol_text(child), child
        return None, None

    def add_reader_feature(item: dict, reader_feature: str | None) -> None:
        if reader_feature is None:
            return
        features = item.setdefault("reader_features", [])
        if reader_feature not in features:
            features.append(reader_feature)
            features.sort()

    def add_node(
        nid: str,
        label: str,
        line: int,
        reader_feature: str | None = None,
    ) -> None:
        existing = nodes_by_id.get(nid)
        if existing is not None:
            assert existing["label"] == label, (
                f"Clojure node ID collision: {nid!r} maps to both "
                f"{existing['label']!r} and {label!r}"
            )
            if reader_feature is None:
                unconditional_node_ids.add(nid)
                existing.pop("reader_features", None)
            elif nid not in unconditional_node_ids:
                add_reader_feature(existing, reader_feature)
            return
        node = {
            "id": nid,
            "label": label,
            "file_type": "code",
            "source_file": str_path,
            "source_location": f"L{line}",
        }
        if reader_feature is None:
            unconditional_node_ids.add(nid)
        else:
            add_reader_feature(node, reader_feature)
        nodes_by_id[nid] = node
        nodes.append(node)

    def add_edge(
        source_nid: str,
        target_nid: str,
        relation: str,
        line: int,
        context: str | None = None,
        reader_feature: str | None = None,
    ) -> None:
        key = (source_nid, target_nid, relation, context)
        existing = edges_by_key.get(key)
        if existing is not None:
            if reader_feature is None:
                unconditional_edge_keys.add(key)
                existing.pop("reader_features", None)
            elif key not in unconditional_edge_keys:
                add_reader_feature(existing, reader_feature)
            return
        edge = {
            "source": source_nid,
            "target": target_nid,
            "relation": relation,
            "confidence": "EXTRACTED",
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": 1.0,
        }
        if context:
            edge["context"] = context
        if reader_feature is None:
            unconditional_edge_keys.add(key)
        else:
            add_reader_feature(edge, reader_feature)
        edges_by_key[key] = edge
        edges.append(edge)

    file_nid = _make_id(str_path)
    add_node(file_nid, path.name, 1)

    def container_nid() -> str:
        return namespace_nid or file_nid

    def unquote_form(form: Any) -> Any:
        if form.type in {"quoting_lit", "syn_quoting_lit"}:
            values = form_values(form)
            return values[0] if values else form
        return form

    def add_require_form(
        require_form: Any,
        reader_feature: str | None = None,
    ) -> None:
        require_form = unquote_form(require_form)
        if require_form.type == "sym_lit":
            module_name, module_node = symbol_text(require_form), require_form
        elif require_form.type == "vec_lit":
            module_name, module_node = first_symbol(form_values(require_form))
        else:
            return
        if module_name is not None and module_node is not None:
            add_edge(
                container_nid(),
                _clojure_id(module_name),
                "imports_from",
                module_node.start_point[0] + 1,
                context="import",
                reader_feature=reader_feature,
            )

    def add_java_import_form(
        import_form: Any,
        reader_feature: str | None = None,
    ) -> None:
        import_form = unquote_form(import_form)
        if import_form.type == "sym_lit":
            import_symbols = [symbol_text(import_form)]
        else:
            import_symbols = [
                symbol_text(child)
                for child in form_values(import_form)
                if child.type == "sym_lit"
            ]
        if not import_symbols:
            return
        package = import_symbols[0]
        imported_names = import_symbols[1:] or [package]
        for imported_name in imported_names:
            target = (
                f"{package}.{imported_name}"
                if imported_name != package
                else package
            )
            add_edge(
                container_nid(),
                _make_id(target),
                "imports",
                import_form.start_point[0] + 1,
                context="import",
                reader_feature=reader_feature,
            )

    def conditional_branches(node: Any) -> list[tuple[str, Any]]:
        values = form_values(node)
        branches: list[tuple[str, Any]] = []
        for index in range(0, len(values) - 1, 2):
            feature_node = values[index]
            if feature_node.type != "kwd_lit":
                continue
            branches.append((node_text(feature_node), values[index + 1]))
        return branches

    def add_namespace_clause(
        clause: Any,
        reader_feature: str | None = None,
    ) -> None:
        if clause.type in {"read_cond_lit", "splicing_read_cond_lit"}:
            for feature, branch in conditional_branches(clause):
                add_namespace_clause(branch, feature)
            return
        if clause.type == "vec_lit":
            for value in form_values(clause):
                add_namespace_clause(value, reader_feature)
            return
        if clause.type != "list_lit":
            return
        clause_values = form_values(clause)
        if not clause_values:
            return
        clause_head = node_text(clause_values[0])
        if clause_head in {":require", ":require-macros", ":use"}:
            for require_form in clause_values[1:]:
                add_require_form(require_form, reader_feature)
        elif clause_head == ":import":
            for import_form in clause_values[1:]:
                add_java_import_form(import_form, reader_feature)

    def add_import_edges(ns_form: Any) -> None:
        for clause in form_values(ns_form)[2:]:
            add_namespace_clause(clause)

    def add_protocol_methods(
        protocol_nid: str,
        form: Any,
        reader_feature: str | None,
    ) -> None:
        for child in form_values(form)[2:]:
            method_name = form_head(child)
            if not method_name:
                continue
            line = child.start_point[0] + 1
            method_nid = _clojure_id(protocol_nid, method_name)
            add_node(method_nid, f".{method_name}()", line, reader_feature)
            add_edge(
                protocol_nid,
                method_nid,
                "method",
                line,
                reader_feature=reader_feature,
            )
            definition_ids_by_name.setdefault(method_name, method_nid)

    def body_nodes(head: str, children: list[Any]) -> list[Any]:
        if head == "defmethod":
            for index, child in enumerate(children[2:], start=2):
                if child.type == "vec_lit":
                    return children[index + 1:]
            return []
        for index, child in enumerate(children[2:], start=2):
            if child.type == "vec_lit":
                return children[index + 1:]
        return children[2:]

    def add_definition(
        form: Any,
        reader_feature: str | None = None,
    ) -> None:
        children = form_values(form)
        if len(children) < 2:
            return
        head = symbol_text(children[0])
        if head not in definition_heads:
            return
        name, name_node = first_symbol(children, 1)
        if name is None or name_node is None:
            return

        line = name_node.start_point[0] + 1
        if head == "defmethod":
            dispatch = node_text(children[2]) if len(children) > 2 else ""
            label = f"{name} {dispatch}".strip()
            node_id = _clojure_id(container_nid(), name, dispatch)
        elif head in type_heads:
            label = name
            node_id = _clojure_id(container_nid(), name)
        elif head in callable_heads or head == "defmulti":
            label = f"{name}()"
            node_id = _clojure_id(container_nid(), name)
        else:
            label = name
            node_id = _clojure_id(container_nid(), name)

        add_node(node_id, label, line, reader_feature)
        add_edge(
            container_nid(),
            node_id,
            "contains",
            line,
            reader_feature=reader_feature,
        )
        if head == "defprotocol":
            add_protocol_methods(node_id, form, reader_feature)
        elif head in {"defrecord", "deftype"}:
            type_implementation_forms.append((node_id, form, reader_feature))
        elif head == "defmethod":
            defmethod_implementations.append(
                (node_id, name, line, reader_feature)
            )
        if head != "defmethod":
            definition_ids_by_name.setdefault(name, node_id)
        if head in callable_heads:
            function_bodies.append((
                node_id,
                body_nodes(head, children),
                reader_feature,
            ))

    def walk_top_level(
        child: Any,
        reader_feature: str | None = None,
    ) -> None:
        nonlocal namespace_name, namespace_nid
        if child.type != "list_lit":
            if child.type in {"read_cond_lit", "splicing_read_cond_lit"}:
                for feature, branch in conditional_branches(child):
                    walk_top_level(branch, feature)
            elif child.type == "vec_lit":
                for value in form_values(child):
                    walk_top_level(value, reader_feature)
            return
        if form_head(child) == "ns":
            ns_children = form_values(child)
            if len(ns_children) > 1 and ns_children[1].type == "sym_lit":
                namespace_name = symbol_text(ns_children[1])
                namespace_nid = _clojure_id(namespace_name)
                line = ns_children[1].start_point[0] + 1
                add_node(namespace_nid, namespace_name, line)
                add_edge(file_nid, namespace_nid, "contains", line)
                add_import_edges(child)
            return
        if form_head(child) in {"require", "use"}:
            for require_form in form_values(child)[1:]:
                add_require_form(require_form, reader_feature)
            return
        if form_head(child) == "import":
            for import_form in form_values(child)[1:]:
                add_java_import_form(import_form, reader_feature)
            return
        add_definition(child, reader_feature)

    for child in named_children(root):
        walk_top_level(child)

    def method_body_nodes(children: list[Any]) -> list[Any]:
        for index, child in enumerate(children[1:], start=1):
            if child.type == "vec_lit":
                return children[index + 1:]
        return children[1:]

    for type_nid, form, reader_feature in type_implementation_forms:
        children = form_values(form)
        fields_index = next(
            (
                index
                for index, child in enumerate(children[2:], start=2)
                if child.type == "vec_lit"
            ),
            None,
        )
        if fields_index is None:
            continue
        for child in children[fields_index + 1:]:
            if child.type == "sym_lit":
                protocol_name = symbol_text(child)
                target_nid = definition_ids_by_name.get(
                    protocol_name.rsplit("/", 1)[-1],
                    _clojure_id(protocol_name),
                )
                add_edge(
                    type_nid,
                    target_nid,
                    "implements",
                    child.start_point[0] + 1,
                    reader_feature=reader_feature,
                )
                continue
            method_name = form_head(child)
            if method_name is None:
                continue
            line = child.start_point[0] + 1
            method_nid = _clojure_id(type_nid, method_name)
            add_node(method_nid, f".{method_name}()", line, reader_feature)
            add_edge(
                type_nid,
                method_nid,
                "method",
                line,
                reader_feature=reader_feature,
            )
            function_bodies.append((
                method_nid,
                method_body_nodes(form_values(child)),
                reader_feature,
            ))

    for method_nid, multimethod_name, line, reader_feature in defmethod_implementations:
        multimethod_nid = definition_ids_by_name.get(multimethod_name)
        if multimethod_nid is not None:
            add_edge(
                multimethod_nid,
                method_nid,
                "method",
                line,
                reader_feature=reader_feature,
            )

    seen_call_pairs: set[tuple[str, str, str | None]] = set()

    def callee_name(raw_head: str) -> str | None:
        if raw_head in skipped_call_heads or raw_head.startswith(":"):
            return None
        if "/" not in raw_head:
            return raw_head
        qualifier, name = raw_head.rsplit("/", 1)
        if namespace_name is not None and qualifier == namespace_name:
            return name
        return None

    def walk_calls(
        node: Any,
        caller_nid: str,
        reader_feature: str | None,
    ) -> None:
        if node.type in {
            "comment",
            "dis_expr",
            "quoting_lit",
            "syn_quoting_lit",
            "var_quoting_lit",
        }:
            return
        if node.type in {"read_cond_lit", "splicing_read_cond_lit"}:
            for feature, branch in conditional_branches(node):
                branch_feature = (
                    feature
                    if reader_feature is None
                    else reader_feature
                    if reader_feature == feature
                    else f"{reader_feature}&{feature}"
                )
                walk_calls(branch, caller_nid, branch_feature)
            return
        if node.type == "list_lit":
            raw_head = form_head(node)
            if raw_head in definition_heads or raw_head in {"comment", "quote"}:
                return
            if raw_head:
                name = callee_name(raw_head)
                target_nid = definition_ids_by_name.get(name or "")
                pair = (caller_nid, target_nid or "", reader_feature)
                if target_nid and target_nid != caller_nid and pair not in seen_call_pairs:
                    seen_call_pairs.add(pair)
                    add_edge(
                        caller_nid,
                        target_nid,
                        "calls",
                        node.start_point[0] + 1,
                        context="call",
                        reader_feature=reader_feature,
                    )
        for child in form_values(node) if node.type.endswith("_lit") else named_children(node):
            walk_calls(child, caller_nid, reader_feature)

    for caller_nid, bodies, reader_feature in function_bodies:
        for body in bodies:
            walk_calls(body, caller_nid, reader_feature)

    return {"nodes": nodes, "edges": edges, "raw_calls": []}
