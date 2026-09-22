"""Structural extraction for Clojure / ClojureScript / EDN source files.

Backed by the ``clojure`` grammar bundled in ``tree-sitter-language-pack``.
That grammar is deliberately minimal: it knows lists, vectors, maps, symbols
and literals but has no notion of ``defn`` or ``ns``. All structure below comes
from inspecting the head symbol of each top-level list form, the same way the
Common Lisp extractor works.

Per file this emits the namespace (``ns`` form), every ``def*`` form as a node
(functions, macros, multimethods, vars, protocols, records, types), protocol
method signatures, record/type method implementations, Java ``:import`` targets,
``contains`` / ``implements`` edges, and intra-file ``calls`` edges. Calls into
other namespaces (``alias/fn``, ``:refer``-ed symbols) and ``:require`` targets
are recorded as raw entries and resolved across files by
``resolve_clojure_namespaces`` once every file has been extracted.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from tree_sitter import Node

from graphify.extractors.base import _file_stem, _make_id, _read_text

# Head symbols that define a callable.
_FN_DEFINERS: dict[str, str] = {
    "defn": "function",
    "defn-": "function",
    "definline": "function",
    "defmacro": "macro",
    "defmulti": "multimethod",
}

# Head symbols that define a plain value binding (callable only when the value
# is itself an `fn` form — see `_value_is_fn`).
_VAR_DEFINERS = frozenset({"def", "defonce", "defdynamic"})

# Head symbols that define a type-like thing.
_TYPE_DEFINERS: dict[str, str] = {
    "defrecord": "record",
    "deftype": "type",
    "defstruct": "struct",
}

# Symbols that start with "def" but are not definitions (denylist for the
# def-prefix heuristic that catches custom definers such as `deftest`).
_NOT_DEFINERS = frozenset({
    "default", "defaults", "define", "defer", "deferred", "deflate",
    "def-", "definterface",
})

# Head symbols that never count as calls to user code.
_SPECIAL_FORMS = frozenset({
    # Clojure special forms
    "def", "if", "do", "let", "let*", "quote", "var", "fn", "fn*", "loop",
    "loop*", "recur", "throw", "try", "catch", "finally", "monitor-enter",
    "monitor-exit", "new", "set!", "letfn", "letfn*", "case*", ".", "&",
    # namespace / definer forms handled structurally
    "ns", "in-ns", "comment", "declare",
    "defn", "defn-", "defmacro", "defmulti", "defmethod", "definline",
    "defonce", "defprotocol", "defrecord", "deftype", "defstruct",
    "extend-protocol", "extend-type", "extend", "reify", "proxy",
    # the most common core macros / control flow
    "when", "when-not", "when-let", "when-some", "when-first", "if-not",
    "if-let", "if-some", "cond", "condp", "case", "and", "or", "not",
    "->", "->>", "as->", "some->", "some->>", "cond->", "cond->>", "doto",
    "..", "doseq", "dotimes", "while", "for", "binding", "with-open",
    "with-out-str", "with-redefs", "locking", "lazy-seq", "delay", "future",
    "assert", "with-meta", "time", "dosync", "io!",
    # literals that parse as symbols
    "true", "false", "nil",
})

# Kinds a cross-namespace call may resolve to. Record/type method
# implementations (`method`) are deliberately absent: several records in one
# namespace usually implement the same protocol method, and a call names the
# protocol signature (`protocol_method`), not one implementation.
_CALLABLE_KINDS = frozenset({
    "function", "macro", "multimethod", "protocol_method", "var", "definition",
})

_TYPE_KINDS = frozenset({"record", "type", "struct"})

# Forms whose second element is a binding vector (`[name value ...]`).
_BINDING_FORMS = frozenset({
    "let", "let*", "loop", "loop*", "for", "doseq", "dotimes", "binding",
    "with-open", "with-local-vars", "if-let", "when-let", "if-some", "when-some",
    "when-first", "as->",
})

# Forms whose parameters (a vector, or one per arity list) follow the head.
_FN_FORMS = frozenset({
    "fn", "fn*", "defn", "defn-", "defmacro", "defmethod", "definline",
    "deftest", "bound-fn",
})

# Forms that host protocol / interface method implementations inline:
# `(reify P (m [this] ...))`, `(proxy [Class] [args] (m [x] ...))`.
_IMPL_HOSTS = frozenset({
    "reify", "proxy", "extend-protocol", "extend-type", "deftype", "defrecord",
    "specify", "specify!",
})


def _binding_symbols(node: Node, source: bytes, into: set[str]) -> None:
    """Collect every symbol a binding/destructuring form introduces."""
    if node.type == "sym_lit":
        parts = _sym_parts(node, source)
        if parts is not None and parts[0] is None and parts[1] not in {"&", "_"}:
            into.add(parts[1])
        return
    if node.type == "vec_lit":
        for child in _values(node):
            _binding_symbols(child, source, into)
        return
    if node.type == "map_lit":
        # `{:keys [a b] :as m x :x}` — keys of the map bind (except keyword
        # options, whose values bind instead).
        values = _values(node)
        index = 0
        while index < len(values):
            key = values[index]
            value = values[index + 1] if index + 1 < len(values) else None
            if key.type == "kwd_lit":
                if value is not None:
                    _binding_symbols(value, source, into)
            else:
                _binding_symbols(key, source, into)
            index += 2


def _local_bindings(items: list[Node], source: bytes) -> set[str]:
    """Names bound anywhere inside a definition body.

    Form-level rather than exactly scoped: a parameter or `let` name shadows
    a same-named top-level def for the whole form, which trades a few missed
    edges in unusual code for never mistaking `(handler req)` on a `handler`
    parameter for a call to a `handler` function.
    """
    bound: set[str] = set()
    # The items of a definition body start with its own parameter vector (or
    # one `([params] body)` clause per arity) — those have no symbol head.
    for item in items:
        if item.type == "vec_lit":
            _binding_symbols(item, source, bound)
            break
        if item.type == "list_lit":
            clause = _values(item)
            if clause and clause[0].type == "vec_lit":
                _binding_symbols(clause[0], source, bound)
    stack = list(items)
    while stack:
        node = stack.pop()
        if node.type in {"quoting_lit", "comment", "dis_expr"}:
            continue
        if node.type in {"list_lit", "anon_fn_lit"}:
            head = _head_symbol(node, source)
            values = _values(node)
            if head is not None and head[0] is None:
                name = head[1]
                if name in _FN_FORMS:
                    # optional fn name, then either a params vector or arity lists
                    for value in values[1:]:
                        if value.type == "vec_lit":
                            _binding_symbols(value, source, bound)
                            break
                        if value.type == "list_lit":
                            arity = _values(value)
                            if arity and arity[0].type == "vec_lit":
                                _binding_symbols(arity[0], source, bound)
                elif name in _BINDING_FORMS and len(values) > 1 and values[1].type == "vec_lit":
                    pairs = _values(values[1])
                    for target in pairs[0::2]:
                        _binding_symbols(target, source, bound)
                elif name == "letfn" and len(values) > 1 and values[1].type == "vec_lit":
                    for fn_form in _values(values[1]):
                        if fn_form.type == "list_lit":
                            fn_values = _values(fn_form)
                            if fn_values:
                                _binding_symbols(fn_values[0], source, bound)
                elif name == "catch" and len(values) > 2:
                    _binding_symbols(values[2], source, bound)
                elif name in _IMPL_HOSTS:
                    for value in values[1:]:
                        if value.type == "list_lit":
                            impl = _values(value)
                            if len(impl) > 1 and impl[1].type == "vec_lit":
                                _binding_symbols(impl[1], source, bound)
        stack.extend(node.named_children)
    return bound

_SUFFIXES = frozenset({".clj", ".cljs", ".cljc", ".edn"})


# Clojure symbols routinely carry operator characters (`<!!`, `>!!`, `foo?`,
# `foo!`, `->Record`, `+`, `*ns*`) that the generic ``_make_id`` strips, which
# would collapse distinct definitions onto one node id. Map them to readable
# tokens first, the way the Common Lisp extractor does.
_CLJ_CHAR_MAP = {
    "=": "_eq", "<": "_lt", ">": "_gt", "?": "_p", "!": "_bang",
    "+": "_plus", "*": "_star", "/": "_slash", "%": "_pct", "&": "_amp",
    "'": "_quote", "#": "_hash", "$": "_dollar", "|": "_pipe", "~": "_tilde",
    "^": "_caret", ":": "_colon",
}


def _clj_id(*parts: str) -> str:
    return _make_id(*("".join(_CLJ_CHAR_MAP.get(c, c) for c in part) for part in parts))


def _values(node: Node) -> list[Node]:
    """Named children of a collection literal, minus metadata / comment nodes."""
    return [
        child for child in node.named_children
        if child.type not in {"comment", "dis_expr", "meta_lit", "old_meta_lit"}
    ]


def _sym_parts(node: Node, source: bytes) -> tuple[str | None, str] | None:
    """Return ``(namespace, name)`` for a ``sym_lit`` node, else ``None``."""
    if node.type != "sym_lit":
        return None
    ns: str | None = None
    name: str | None = None
    for child in node.children:
        if child.type == "sym_ns":
            ns = _read_text(child, source)
        elif child.type == "sym_name":
            name = _read_text(child, source)
    if name is None:
        text = _read_text(node, source)
        # Strip any leading ^meta reader forms the grammar folded into the symbol.
        name = text.split()[-1] if text.split() else text
    return ns, name


def _sym_name(node: Node | None, source: bytes) -> str | None:
    if node is None:
        return None
    parts = _sym_parts(node, source)
    if parts is None:
        return None
    ns, name = parts
    return f"{ns}/{name}" if ns else name


def _head_symbol(node: Node, source: bytes) -> tuple[str | None, str] | None:
    """Head symbol of a list / anonymous-fn form, or ``None``."""
    if node.type not in {"list_lit", "anon_fn_lit"}:
        return None
    values = _values(node)
    if not values:
        return None
    return _sym_parts(values[0], source)


def _unquote(node: Node) -> Node:
    """Unwrap ``'form`` / ``` `form ``` to the quoted form."""
    if node.type in {"quoting_lit", "syn_quoting_lit"}:
        inner = node.child_by_field_name("value")
        if inner is not None:
            return inner
        values = _values(node)
        if values:
            return values[-1]
    return node


def _value_is_fn(node: Node, source: bytes) -> bool:
    node = _unquote(node)
    if node.type == "anon_fn_lit":
        return True
    head = _head_symbol(node, source)
    if head is None:
        return False
    ns, name = head
    return ns is None and name in {"fn", "fn*", "partial", "comp", "memoize", "constantly", "juxt"}


def _descendants(node: Node) -> Iterable[Node]:
    for child in node.named_children:
        yield child
        yield from _descendants(child)


def _parse_libspecs(
    node: Node, source: bytes, prefix: str = ""
) -> list[dict[str, Any]]:
    """Parse one ``:require`` / ``:use`` entry into libspec dicts.

    Handles ``foo.bar``, ``[foo.bar :as fb :refer [x y]]``, ``[foo.bar :refer :all]``,
    string libspecs (``["react" :as react]`` in ClojureScript), and prefix lists
    ``[clojure [string :as str] set]`` / ``(clojure [string :as str])``.
    """
    node = _unquote(node)
    if node.type == "sym_lit":
        name = _sym_name(node, source) or ""
        return [{"namespace": f"{prefix}.{name}" if prefix else name, "alias": None, "refer": [], "refer_all": False}]
    if node.type == "str_lit":
        text = _read_text(node, source).strip('"')
        return [{"namespace": text, "alias": None, "refer": [], "refer_all": False}]
    if node.type not in {"vec_lit", "list_lit"}:
        return []
    values = _values(node)
    if not values:
        return []
    first = values[0]
    if first.type not in {"sym_lit", "str_lit"}:
        return []
    # Prefix list: second element is itself a libspec collection or a bare symbol
    # that is not a keyword option.
    rest = values[1:]
    if rest and rest[0].type != "kwd_lit":
        base = _sym_name(first, source) if first.type == "sym_lit" else _read_text(first, source).strip('"')
        full_prefix = f"{prefix}.{base}" if prefix else base
        specs: list[dict[str, Any]] = []
        for item in rest:
            specs.extend(_parse_libspecs(item, source, full_prefix or ""))
        return specs
    if first.type == "sym_lit":
        name = _sym_name(first, source) or ""
    else:
        name = _read_text(first, source).strip('"')
    if prefix:
        name = f"{prefix}.{name}"
    spec: dict[str, Any] = {"namespace": name, "alias": None, "refer": [], "refer_all": False}
    index = 0
    while index < len(rest):
        option = rest[index]
        arg = rest[index + 1] if index + 1 < len(rest) else None
        if option.type == "kwd_lit" and arg is not None:
            key = _read_text(option, source)
            if key in {":as", ":as-alias"}:
                spec["alias"] = _sym_name(arg, source)
            elif key in {":refer", ":only"}:
                if arg.type == "kwd_lit" and _read_text(arg, source) == ":all":
                    spec["refer_all"] = True
                elif arg.type in {"vec_lit", "list_lit"}:
                    spec["refer"] = [
                        n for n in (_sym_name(v, source) for v in _values(arg)) if n
                    ]
            elif key == ":refer-macros" and arg.type in {"vec_lit", "list_lit"}:
                spec["refer"].extend(
                    n for n in (_sym_name(v, source) for v in _values(arg)) if n
                )
            index += 2
        else:
            index += 1
    return [spec]


def _parse_imports(node: Node, source: bytes) -> list[str]:
    """Parse one ``:import`` entry: ``java.util.Date`` or ``(java.util Date UUID)``."""
    node = _unquote(node)
    if node.type == "sym_lit":
        return [_sym_name(node, source) or ""]
    if node.type in {"list_lit", "vec_lit"}:
        values = _values(node)
        if not values:
            return []
        package = _sym_name(values[0], source) or ""
        return [f"{package}.{_sym_name(v, source)}" for v in values[1:] if _sym_name(v, source)]
    return []


def resolve_clojure_namespaces(
    per_file: list[dict], all_nodes: list[dict], all_edges: list[dict]
) -> None:
    """Resolve ``:require`` targets and cross-namespace calls by namespace + name.

    A required namespace defined in the corpus gets an ``imports`` edge to every
    node that declares it (a ``.clj`` and ``.cljs`` half of the same namespace are
    both legitimate targets). One not defined anywhere here gets a single
    non-source-backed ``namespace`` node so external libraries are visible.
    Calls resolve only when exactly one definition matches (god-node guard).
    """
    namespaces: dict[str, list[str]] = {}
    callables: dict[tuple[str, str], list[str]] = {}
    types: dict[tuple[str, str], list[str]] = {}
    for node in all_nodes:
        metadata = node.get("metadata")
        if not isinstance(metadata, dict) or metadata.get("language") != "clojure":
            continue
        kind = metadata.get("kind")
        namespace = metadata.get("namespace")
        name = metadata.get("name")
        if not isinstance(namespace, str):
            continue
        if kind == "namespace" and node.get("source_file"):
            namespaces.setdefault(namespace, []).append(node["id"])
        elif kind in _CALLABLE_KINDS and isinstance(name, str):
            callables.setdefault((namespace, name), []).append(node["id"])
        elif kind in _TYPE_KINDS and isinstance(name, str):
            types.setdefault((namespace, name), []).append(node["id"])

    existing = {
        (edge.get("source"), edge.get("target"), edge.get("relation"))
        for edge in all_edges
    }
    external_ids = {node["id"] for node in all_nodes}

    def add_edge(source: str, target: str, relation: str, context: str, raw: dict) -> None:
        key = (source, target, relation)
        if source == target or key in existing:
            return
        existing.add(key)
        all_edges.append({
            "source": source,
            "target": target,
            "relation": relation,
            "context": context,
            "confidence": "EXTRACTED",
            "confidence_score": 1.0,
            "source_file": raw.get("source_file", ""),
            "source_location": raw.get("source_location"),
            "weight": 1.0,
        })

    for result in per_file:
        for raw in result.get("raw_calls", []):
            if raw.get("language") != "clojure":
                continue
            caller = raw.get("caller_nid")
            if not caller:
                continue
            if raw.get("kind") == "require":
                namespace = str(raw.get("namespace", ""))
                if not namespace:
                    continue
                targets = namespaces.get(namespace)
                if targets:
                    for target in targets:
                        add_edge(caller, target, "imports", "require", raw)
                    continue
                external_id = _clj_id("clojure", "namespace", namespace)
                if external_id not in external_ids:
                    external_ids.add(external_id)
                    all_nodes.append({
                        "id": external_id,
                        "label": namespace,
                        "file_type": "code",
                        "source_location": raw.get("source_location"),
                        "metadata": {
                            "language": "clojure",
                            "kind": "namespace",
                            "namespace": namespace,
                            "external": True,
                        },
                    })
                add_edge(caller, external_id, "imports", "require", raw)
                continue

            callee = str(raw.get("callee", ""))
            if not callee:
                continue
            candidate_namespaces: list[str] = []
            if raw.get("remote_namespace"):
                candidate_namespaces.append(str(raw["remote_namespace"]))
            candidate_namespaces.extend(str(n) for n in raw.get("refer_all", []) or [])
            # `alias/->Record` and `alias/map->Record` construct a record defined
            # in another namespace: a `references` edge to the record node.
            type_name = None
            if callee.startswith("map->"):
                type_name = callee[len("map->"):]
            elif callee.startswith("->") and len(callee) > 2:
                type_name = callee[2:]
            if type_name:
                type_candidates: list[str] = []
                for namespace in candidate_namespaces:
                    type_candidates.extend(types.get((namespace, type_name), []))
                if len(type_candidates) == 1 and type_candidates[0] != caller:
                    add_edge(caller, type_candidates[0], "references", "constructor", raw)
                continue
            candidates: list[str] = []
            for namespace in candidate_namespaces:
                candidates.extend(callables.get((namespace, callee), []))
            if len(candidates) != 1 or candidates[0] == caller:
                continue
            add_edge(caller, candidates[0], "calls", "remote_call", raw)


def extract_clojure(path: Path) -> dict:
    try:
        from tree_sitter import Parser
        from tree_sitter_language_pack import get_language
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-language-pack not installed"}

    try:
        source = path.read_bytes()
        root = Parser(get_language("clojure")).parse(source).root_node
    except Exception as exc:
        return {"nodes": [], "edges": [], "error": f"Clojure grammar failed to load: {exc}"}

    source_file = str(path)
    stem = _file_stem(path)
    file_id = _make_id(source_file)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    raw_calls: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_edges: set[tuple[str, str, str]] = set()

    def line(node: Node) -> str:
        return f"L{node.start_point[0] + 1}"

    def add_node(
        nid: str,
        label: str,
        node: Node,
        *,
        kind: str,
        source_backed: bool = True,
        callable_node: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        if nid not in seen_ids:
            seen_ids.add(nid)
            details: dict[str, Any] = {"language": "clojure", "kind": kind}
            if metadata:
                details.update(metadata)
            item: dict[str, Any] = {
                "id": nid,
                "label": label,
                "file_type": "code",
                "source_location": line(node),
                "metadata": details,
            }
            if source_backed:
                item["source_file"] = source_file
            if callable_node:
                item["_callable"] = True
            nodes.append(item)
        return nid

    def add_edge(source_id: str, target_id: str, relation: str, node: Node) -> None:
        key = (source_id, target_id, relation)
        if not source_id or not target_id or source_id == target_id or key in seen_edges:
            return
        seen_edges.add(key)
        edges.append({
            "source": source_id,
            "target": target_id,
            "relation": relation,
            "confidence": "EXTRACTED",
            "source_file": source_file,
            "source_location": line(node),
            "weight": 1.0,
        })

    add_node(file_id, path.name, root, kind="file")

    if path.suffix.lower() == ".edn":
        # EDN is data, not code: the file node is all there is to say.
        return {"nodes": nodes, "edges": edges, "raw_calls": raw_calls}

    top_forms = [child for child in root.named_children if child.type == "list_lit"]

    # --- namespace -----------------------------------------------------------
    namespace = path.stem
    ns_id = file_id
    ns_form: Node | None = None
    for form in top_forms:
        head = _head_symbol(form, source)
        if head is None:
            continue
        head_ns, head_name = head
        if head_ns is None and head_name in {"ns", "in-ns"}:
            values = _values(form)
            if len(values) >= 2:
                name = _sym_name(_unquote(values[1]), source)
                if name:
                    namespace = name
                    ns_form = form
            break
    if ns_form is not None:
        ns_id = add_node(
            _clj_id(stem, "namespace", namespace),
            namespace,
            ns_form,
            kind="namespace",
            metadata={"namespace": namespace, "name": namespace},
        )
        add_edge(file_id, ns_id, "contains", ns_form)

    aliases: dict[str, str] = {}
    refers: dict[str, str] = {}
    refer_all: list[str] = []

    def record_libspecs(specs: list[dict[str, Any]], node: Node) -> None:
        for spec in specs:
            target_ns = spec["namespace"]
            if not target_ns:
                continue
            raw_calls.append({
                "kind": "require",
                "caller_nid": ns_id,
                "namespace": target_ns,
                "language": "clojure",
                "source_file": source_file,
                "source_location": line(node),
            })
            if spec["alias"]:
                aliases[spec["alias"]] = target_ns
            for name in spec["refer"]:
                refers[name] = target_ns
            if spec["refer_all"] and target_ns not in refer_all:
                refer_all.append(target_ns)

    def record_imports(class_names: list[str], node: Node) -> None:
        for class_name in class_names:
            if not class_name:
                continue
            target = add_node(
                _clj_id("clojure", "import", class_name),
                class_name,
                node,
                kind="class",
                source_backed=False,
                metadata={"name": class_name.rsplit(".", 1)[-1], "external": True},
            )
            add_edge(ns_id, target, "imports", node)

    if ns_form is not None:
        for clause in _values(ns_form)[2:]:
            if clause.type != "list_lit":
                continue
            clause_values = _values(clause)
            if not clause_values or clause_values[0].type != "kwd_lit":
                continue
            key = _read_text(clause_values[0], source)
            if key in {":require", ":use", ":require-macros"}:
                for entry in clause_values[1:]:
                    specs = _parse_libspecs(entry, source)
                    if key == ":use":
                        for spec in specs:
                            if not spec["refer"]:
                                spec["refer_all"] = True
                    record_libspecs(specs, clause)
            elif key == ":import":
                for entry in clause_values[1:]:
                    record_imports(_parse_imports(entry, source), clause)

    # Top-level `(require '[...])` / `(use '...)` / `(import '...)` calls.
    for form in top_forms:
        head = _head_symbol(form, source)
        if head is None or head[0] is not None:
            continue
        if head[1] in {"require", "use", "require-macros"}:
            for entry in _values(form)[1:]:
                specs = _parse_libspecs(entry, source)
                if head[1] == "use":
                    for spec in specs:
                        if not spec["refer"]:
                            spec["refer_all"] = True
                record_libspecs(specs, form)
        elif head[1] == "import":
            for entry in _values(form)[1:]:
                record_imports(_parse_imports(entry, source), form)

    # --- definitions ---------------------------------------------------------
    # name -> node id for everything callable or referenceable in this file
    local_defs: dict[str, str] = {}
    callable_ids: set[str] = set()
    types: dict[str, str] = {}
    protocols: dict[str, str] = {}
    bodies: list[tuple[list[Node], str]] = []
    pending_multimethods: list[tuple[str, Node, str]] = []
    pending_impls: list[tuple[str, str, Node]] = []  # (type_id, protocol name, node)

    def def_id(kind: str, name: str) -> str:
        return _clj_id(ns_id, kind, name)

    def define(
        name: str, node: Node, *, kind: str, callable_node: bool, metadata: dict[str, Any] | None = None
    ) -> str:
        details = {"namespace": namespace, "name": name}
        if metadata:
            details.update(metadata)
        nid = add_node(def_id(kind, name), name, node, kind=kind, callable_node=callable_node, metadata=details)
        add_edge(ns_id, nid, "contains", node)
        if callable_node:
            callable_ids.add(nid)
        return nid

    def define_impl_methods(owner_id: str, owner_name: str, items: list[Node]) -> None:
        """Protocol symbols and `(method [args] body)` impls inside a record/type/extend body."""
        current_protocol: str | None = None
        for item in items:
            if item.type == "sym_lit":
                current_protocol = _sym_name(item, source)
                if current_protocol:
                    pending_impls.append((owner_id, current_protocol, item))
                continue
            if item.type != "list_lit":
                continue
            impl_values = _values(item)
            if not impl_values or impl_values[0].type != "sym_lit":
                continue
            method_name = _sym_parts(impl_values[0], source)
            if method_name is None:
                continue
            method_label = method_name[1]
            method_id = add_node(
                _clj_id(owner_id, "method", method_label),
                f"{owner_name}/{method_label}",
                item,
                kind="method",
                callable_node=True,
                metadata={
                    "namespace": namespace,
                    "name": method_label,
                    "owner": owner_name,
                    "protocol": current_protocol,
                },
            )
            add_edge(owner_id, method_id, "contains", item)
            bodies.append((impl_values[1:], method_id))

    def process_definition(form: Node, head: tuple[str | None, str]) -> bool:
        """Register one `def*` form. Returns True when the form was consumed."""
        head_ns, head_name = head
        values = _values(form)
        args = values[1:]

        if head_ns is not None:
            # Namespaced custom definer (`helix/defnc`, `t/deftest`, `s/fdef`).
            if not head_name.startswith("def") or head_name in _NOT_DEFINERS or not args:
                return False
            name = _sym_name(args[0], source)
            if not name:
                return False
            custom_id = define(
                name, form, kind="definition", callable_node=True,
                metadata={"definer": f"{head_ns}/{head_name}"},
            )
            local_defs.setdefault(name, custom_id)
            bodies.append((args[1:], custom_id))
            return True

        if head_name == "defprotocol" and args:
            name = _sym_name(args[0], source)
            if not name:
                return True
            protocol_id = define(name, form, kind="protocol", callable_node=False)
            protocols[name] = protocol_id
            local_defs.setdefault(name, protocol_id)
            for sig in args[1:]:
                if sig.type != "list_lit":
                    continue
                sig_values = _values(sig)
                if not sig_values:
                    continue
                method_name = _sym_name(sig_values[0], source)
                if not method_name:
                    continue
                method_id = add_node(
                    _clj_id(protocol_id, "method", method_name),
                    method_name,
                    sig,
                    kind="protocol_method",
                    callable_node=True,
                    metadata={"namespace": namespace, "name": method_name, "protocol": name},
                )
                add_edge(protocol_id, method_id, "contains", sig)
                local_defs.setdefault(method_name, method_id)
                callable_ids.add(method_id)
            return True

        if head_name in _TYPE_DEFINERS and args:
            name = _sym_name(args[0], source)
            if not name:
                return True
            type_id = define(name, form, kind=_TYPE_DEFINERS[head_name], callable_node=False)
            types[name] = type_id
            local_defs.setdefault(name, type_id)
            # args[1] is the field vector; everything after it is protocol
            # symbols and method impls.
            define_impl_methods(type_id, name, args[2:])
            return True

        if head_name == "extend-protocol" and args:
            protocol_name = _sym_name(args[0], source)
            # (extend-protocol P Type1 (m ...) Type2 (m ...))
            current_type: str | None = None
            group: list[Node] = []

            def flush(owner_name: str | None, items: list[Node]) -> None:
                if not owner_name:
                    return
                owner_id = types.get(owner_name)
                if owner_id is None:
                    owner_id = add_node(
                        _clj_id("clojure", "type", owner_name),
                        owner_name,
                        form,
                        kind="type",
                        source_backed=False,
                        metadata={"name": owner_name, "external": True},
                    )
                if protocol_name:
                    pending_impls.append((owner_id, protocol_name, form))
                define_impl_methods(owner_id, owner_name, items)

            for item in args[1:]:
                if item.type == "sym_lit":
                    flush(current_type, group)
                    current_type = _sym_name(item, source)
                    group = []
                else:
                    group.append(item)
            flush(current_type, group)
            return True

        if head_name == "extend-type" and args:
            type_name = _sym_name(args[0], source)
            if not type_name:
                return True
            owner_id = types.get(type_name)
            if owner_id is None:
                owner_id = add_node(
                    _clj_id("clojure", "type", type_name),
                    type_name,
                    form,
                    kind="type",
                    source_backed=False,
                    metadata={"name": type_name, "external": True},
                )
            define_impl_methods(owner_id, type_name, args[1:])
            return True

        if head_name == "defmethod" and len(args) >= 2:
            multi_name = _sym_name(args[0], source)
            if not multi_name:
                return True
            dispatch = _read_text(args[1], source).strip()
            method_id = add_node(
                _clj_id(ns_id, "defmethod", multi_name, dispatch),
                f"{multi_name} {dispatch}",
                form,
                kind="method",
                callable_node=True,
                metadata={"namespace": namespace, "name": multi_name, "dispatch": dispatch},
            )
            add_edge(ns_id, method_id, "contains", form)
            pending_multimethods.append((multi_name, form, method_id))
            bodies.append((args[2:], method_id))
            return True

        if head_name in _FN_DEFINERS and args:
            name = _sym_name(args[0], source)
            if not name:
                return True
            fn_id = define(name, form, kind=_FN_DEFINERS[head_name], callable_node=True,
                           metadata={"private": head_name == "defn-"} if head_name == "defn-" else None)
            local_defs[name] = fn_id
            bodies.append((args[1:], fn_id))
            return True

        if head_name in _VAR_DEFINERS and args:
            name = _sym_name(args[0], source)
            if not name:
                return True
            value = args[-1] if len(args) >= 2 else None
            is_fn = value is not None and _value_is_fn(value, source)
            var_id = define(name, form, kind="var", callable_node=is_fn)
            local_defs[name] = var_id
            bodies.append((args[1:], var_id))
            return True

        if head_name.startswith("def") and head_name not in _NOT_DEFINERS and args:
            # Custom definer (deftest, defspec, defroutes, defstate, ...).
            name = _sym_name(args[0], source)
            if not name:
                return True
            custom_id = define(
                name, form, kind="definition", callable_node=True,
                metadata={"definer": head_name},
            )
            local_defs.setdefault(name, custom_id)
            bodies.append((args[1:], custom_id))
            return True


        return False

    def _is_definer_head(head: tuple[str | None, str] | None) -> bool:
        return (
            head is not None
            and head[1].startswith("def")
            and head[1] not in _NOT_DEFINERS
        )

    def nested_definitions(form: Node) -> list[Node]:
        """`def*` forms wrapped in a top-level `when` / `if` / `do` / `let` ..."""
        found: list[Node] = []
        stack = list(reversed(_values(form)[1:]))
        while stack:
            node = stack.pop()
            if node.type in {"quoting_lit", "syn_quoting_lit", "comment", "dis_expr"}:
                continue
            if node.type == "list_lit":
                head = _head_symbol(node, source)
                if head is not None and head[0] is None and head[1] == "comment":
                    continue
                if _is_definer_head(head):
                    found.append(node)
                    continue
            stack.extend(reversed(node.named_children))
        return found

    skip_spans: set[tuple[int, int]] = set()

    for form in top_forms:
        head = _head_symbol(form, source)
        if head is None:
            continue
        if head[0] is None and head[1] in {
            "ns", "in-ns", "require", "use", "import", "require-macros", "comment",
        }:
            continue
        if process_definition(form, head):
            continue
        # Not a definition itself: pick up `(when debug? (defn ...))`-style
        # nested definitions, then attribute the wrapper's remaining calls to
        # the namespace so nothing is silently dropped.
        for nested in nested_definitions(form):
            nested_head = _head_symbol(nested, source)
            if nested_head is not None and process_definition(nested, nested_head):
                skip_spans.add((nested.start_byte, nested.end_byte))
        if ns_form is not None:
            bodies.append(([form], ns_id))

    for multi_name, form, method_id in pending_multimethods:
        target = local_defs.get(multi_name)
        if target is not None:
            add_edge(method_id, target, "implements", form)
        else:
            raw_calls.append({
                "caller_nid": method_id,
                "callee": multi_name,
                "remote_namespace": None,
                "refer_all": [refers[multi_name]] if multi_name in refers else list(refer_all),
                "language": "clojure",
                "source_file": source_file,
                "source_location": line(form),
            })

    for owner_id, protocol_name, node in pending_impls:
        protocol_ns, _, bare = protocol_name.rpartition("/")
        target = protocols.get(protocol_name) if not protocol_ns else None
        if target is None and not protocol_ns and protocol_name in refers:
            protocol_ns = refers[protocol_name]
        if target is not None:
            add_edge(owner_id, target, "implements", node)
            continue
        if protocol_ns:
            resolved_ns = aliases.get(protocol_ns, protocol_ns)
            label = bare or protocol_name
        else:
            resolved_ns = None
            label = protocol_name
        # Not defined here: a non-source-backed protocol node keeps the
        # implements edge visible (java.lang.Object, clojure.lang.IFn, ...).
        ghost = add_node(
            _clj_id("clojure", "protocol", resolved_ns or "", label),
            f"{resolved_ns}/{label}" if resolved_ns else label,
            node,
            kind="protocol_ref",
            source_backed=False,
            metadata={"name": label, "namespace": resolved_ns, "external": True},
        )
        add_edge(owner_id, ghost, "implements", node)

    # --- calls ----------------------------------------------------------------
    def record_call(
        head: tuple[str | None, str], caller_id: str, node: Node, bound: set[str]
    ) -> None:
        sym_ns, name = head
        if sym_ns is None:
            if name in _SPECIAL_FORMS or name.startswith(".") or name.endswith("."):
                return
            if name in bound:
                return
            bare = name
            if name.startswith("map->"):
                bare = name[len("map->"):]
            elif name.startswith("->") and len(name) > 2:
                bare = name[2:]
            if bare != name:
                target = types.get(bare)
                if target is not None:
                    add_edge(caller_id, target, "references", node)
                return
            target = local_defs.get(name)
            if target is not None:
                add_edge(caller_id, target, "calls", node)
                return
            if name in refers:
                raw_calls.append({
                    "caller_nid": caller_id,
                    "callee": name,
                    "remote_namespace": refers[name],
                    "refer_all": [],
                    "language": "clojure",
                    "source_file": source_file,
                    "source_location": line(node),
                })
            elif refer_all:
                raw_calls.append({
                    "caller_nid": caller_id,
                    "callee": name,
                    "remote_namespace": None,
                    "refer_all": list(refer_all),
                    "language": "clojure",
                    "source_file": source_file,
                    "source_location": line(node),
                })
            return
        # Java static call (`Math/abs`) or class-qualified constructor.
        if sym_ns[:1].isupper() and sym_ns not in aliases and "." not in sym_ns:
            return
        remote_ns = aliases.get(sym_ns, sym_ns)
        if remote_ns == namespace:
            target = local_defs.get(name)
            if target is not None:
                add_edge(caller_id, target, "calls", node)
            return
        raw_calls.append({
            "caller_nid": caller_id,
            "callee": name,
            "remote_namespace": remote_ns,
            "refer_all": [],
            "language": "clojure",
            "source_file": source_file,
            "source_location": line(node),
        })

    def implement_inline(node: Node, caller_id: str, head_name: str, stack: list[Node]) -> None:
        """`(reify P (m [this] body))` / `(proxy [C] [args] (m [x] body))` inside a body.

        Protocol symbols become `implements` edges from the enclosing definition;
        method impl heads are definitions, not calls, so only their bodies are
        pushed for walking.
        """
        values = _values(node)[1:]
        if head_name == "proxy":
            # (proxy [Class Iface ...] [ctor-args] impls...)
            if values and values[0].type == "vec_lit":
                for sym in _values(values[0]):
                    parts = _sym_parts(sym, source)
                    if parts is not None and parts[0] is None and parts[1] in protocols:
                        add_edge(caller_id, protocols[parts[1]], "implements", sym)
                values = values[1:]
            if values and values[0].type == "vec_lit":
                stack.append(values[0])
                values = values[1:]
        elif head_name in {"extend-type", "deftype", "defrecord", "specify", "specify!"}:
            values = values[1:]  # type / target expression
            if head_name in {"deftype", "defrecord"} and values and values[0].type == "vec_lit":
                values = values[1:]  # fields
        elif head_name == "extend-protocol":
            if values:
                parts = _sym_parts(values[0], source)
                if parts is not None and parts[0] is None and parts[1] in protocols:
                    add_edge(caller_id, protocols[parts[1]], "implements", values[0])
                values = values[1:]
        for item in values:
            if item.type == "sym_lit":
                parts = _sym_parts(item, source)
                if parts is not None and parts[0] is None and parts[1] in protocols:
                    add_edge(caller_id, protocols[parts[1]], "implements", item)
                continue
            if item.type == "list_lit":
                impl = _values(item)
                start = 2 if len(impl) > 1 and impl[1].type == "vec_lit" else 1
                stack.extend(reversed(impl[start:]))
                continue
            stack.append(item)

    def walk_body(items: list[Node], caller_id: str) -> None:
        bound = _local_bindings(items, source)
        stack = list(reversed(items))
        while stack:
            node = stack.pop()
            if node.type in {"quoting_lit", "comment", "dis_expr", "str_lit", "regex_lit"}:
                continue
            if (node.start_byte, node.end_byte) in skip_spans:
                continue
            if node.type in {"list_lit", "anon_fn_lit"}:
                head = _head_symbol(node, source)
                if head is not None:
                    if head[0] is None and head[1] in _IMPL_HOSTS:
                        implement_inline(node, caller_id, head[1], stack)
                        continue
                    record_call(head, caller_id, node, bound)
            elif node.type == "sym_lit":
                # Higher-order use: (map helper xs), `str/join` passed as a value,
                # or `#'foo` var refs.
                parts = _sym_parts(node, source)
                if (
                    parts is not None
                    and parts[0] is None
                    and parts[1] in local_defs
                    and parts[1] not in bound
                ):
                    target = local_defs[parts[1]]
                    if target != caller_id and not (parts[1] in types or parts[1] in protocols):
                        relation = "calls" if target in callable_ids else "references"
                        add_edge(caller_id, target, relation, node)
            stack.extend(reversed(node.named_children))

    for items, caller_id in bodies:
        walk_body(items, caller_id)

    clean_edges = [
        edge for edge in edges
        if edge["source"] in seen_ids and edge["target"] in seen_ids
    ]
    return {"nodes": nodes, "edges": clean_edges, "raw_calls": raw_calls}


CLOJURE_SUFFIXES = _SUFFIXES
