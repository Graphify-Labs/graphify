"""C# cross-file resolution.

The config-driven C# *extractor* (``extract_csharp`` → ``_extract_generic``)
still lives in ``graphify/extract.py``; per ``extractors/MIGRATION.md`` the
config-driven languages cannot be ported one-by-one until the shared
``_extract_generic`` core moves as its own coordinated batch. This module is
the C# home for the parts that *are* cleanly separable — today, the cross-file
type-reference resolver below — and is where ``extract_csharp`` will land when
the core migration happens.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extractors.base import _read_text


def _resolve_csharp_type_references(
    per_file: list[dict],
    paths: list[Path],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> None:
    """Re-point dangling C# ``inherits``/``implements``/``references`` edges to the
    real definition, using the referencing file's ``using`` directives + enclosing
    namespace for exact disambiguation. Mirrors ``_resolve_java_type_references``.

    C# deltas from Java: a plain ``using N;`` is NAMESPACE-WIDE (resolve a bare ``T``
    by trying ``(N, T)`` for each open namespace and accepting only a UNIQUE hit — the
    god-node guardrail), while ``using X = N.T;`` is a single-type alias. ``global
    using`` is normalized (the ``global`` prefix stripped); ``using static N.T;`` is
    ignored (it imports members, not a namespace/type). The global namespace is keyed
    as the bare label (``""``). A file with MULTIPLE namespace blocks does not register
    its defs (which namespace each def belongs to needs source-range tracking) — deferred.

    Mutates ``all_nodes``/``all_edges`` in place. Runs after id-disambiguation and
    ``_rewire_unique_stub_nodes`` so target ids are final and only the ambiguous
    remainder is left on shadow stubs.
    """
    try:
        import tree_sitter_c_sharp as tscs
        from tree_sitter import Language, Parser
    except ImportError:
        return

    language = Language(tscs.language())
    parser = Parser(language)

    def _key(ns: str, label: str) -> str:
        return label if ns == "" else f"{ns}.{label}"

    own_ns_by_file: dict[str, list[str]] = {}
    scope_by_file: dict[str, list[str]] = {}
    aliases_by_file: dict[str, dict[str, str]] = {}
    for path, result in zip(paths, per_file):
        srcs = {n.get("source_file") for n in result.get("nodes", []) if n.get("source_file")}
        if not srcs:
            continue
        try:
            source = path.read_bytes()
            tree = parser.parse(source)
        except Exception:
            continue
        own_ns: list[str] = []
        usings: list[str] = []
        aliases: dict[str, str] = {}

        def walk(n) -> None:
            if n.type in ("namespace_declaration", "file_scoped_namespace_declaration"):
                nm = n.child_by_field_name("name")
                if nm is not None:
                    own_ns.append(_read_text(nm, source).strip())
            elif n.type == "using_directive":
                text = _read_text(n, source).strip().rstrip(";")
                if text.startswith("global "):
                    text = text[len("global "):].strip()
                if text.startswith("using"):
                    body = text[len("using"):].strip()
                    if body.startswith("static "):
                        pass  # `using static N.T;` imports members, not a type/namespace — skip
                    elif "=" in body:
                        lhs, rhs = body.split("=", 1)
                        if lhs.strip() and rhs.strip():
                            aliases[lhs.strip()] = rhs.strip()
                    elif body:
                        usings.append(body)
            for child in n.children:
                walk(child)

        walk(tree.root_node)
        scope = list(dict.fromkeys((own_ns or [""]) + usings + [""]))
        for s in srcs:
            own_ns_by_file[s] = own_ns
            scope_by_file[s] = scope
            aliases_by_file[s] = aliases

    fqn_to_id: dict[str, str] = {}
    for node in all_nodes:
        label = node.get("label", "")
        src = node.get("source_file", "")
        nid = node.get("id", "")
        if not (label and src and nid) or src not in own_ns_by_file:
            continue
        if not label[:1].isupper() or label.endswith(")") or label.endswith(".cs"):
            continue
        ns_list = own_ns_by_file.get(src, [])
        if len(ns_list) == 0:
            fqn_to_id.setdefault(_key("", label), nid)
        elif len(ns_list) == 1:
            fqn_to_id.setdefault(_key(ns_list[0], label), nid)
        # len > 1: skip (deferred)

    stub_label: dict[str, str] = {
        node["id"]: node.get("label", "")
        for node in all_nodes
        if node.get("id") and not node.get("source_file") and node.get("label", "")[:1].isupper()
    }
    if not stub_label:
        return

    REPOINT_RELATIONS = {"implements", "inherits", "references"}
    repointed_from: set[str] = set()
    for edge in all_edges:
        if edge.get("relation") not in REPOINT_RELATIONS:
            continue
        tgt = edge.get("target")
        label = stub_label.get(tgt)
        if not label:
            continue
        ref_file = edge.get("source_file", "")
        resolved = None
        alias_fqn = aliases_by_file.get(ref_file, {}).get(label)
        if alias_fqn:
            ns, _, simple = alias_fqn.rpartition(".")
            resolved = fqn_to_id.get(_key(ns, simple))
        if resolved is None:
            cands: list[str] = []
            for ns in scope_by_file.get(ref_file, []):
                hit = fqn_to_id.get(_key(ns, label))
                if hit and hit not in cands:
                    cands.append(hit)
            if len(cands) == 1:
                resolved = cands[0]
        if resolved and resolved != tgt:
            edge["target"] = resolved
            repointed_from.add(tgt)

    if not repointed_from:
        return

    still_referenced: set[str] = set()
    for edge in all_edges:
        still_referenced.add(edge.get("source"))
        still_referenced.add(edge.get("target"))
    all_nodes[:] = [
        node for node in all_nodes
        if node.get("id") not in repointed_from or node.get("id") in still_referenced
    ]
