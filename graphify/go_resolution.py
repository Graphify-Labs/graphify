"""Type-aware cross-file resolution for Go member calls (#3368).

Go has no syntax marking a call as "through a struct field" or "through a
typed parameter" — `p.uploader.UploadProfile()` and `fmt.Println()` are the
same AST shape, a `selector_expression` call. The Go extractor tells them
apart by whether the receiver is a known package alias, but a member call
(the ``uploader.UploadProfile`` case) still reached `raw_calls` with nothing
to resolve it: the shared cross-file pass, `resolve_cross_file_raw_calls`,
drops every member call unconditionally — a bare method name alone collides
across the corpus, the same conservative default every language with this
gap uses — and Go had no language-specific resolver to answer it instead, so
typed-receiver calls (parameters, struct fields, and chains of both) produced
no `calls` edge at all.

This resolver walks the receiver's dotted chain (`p.uploader`, `b.Start`,
`p.cfg.OutputDirFn`) segment by segment through two tables the extractor
builds while parsing each file:

  * ``go_local_types``   — caller_nid -> {name: declared type's node id},
    from the caller's own receiver and parameters.
  * ``go_struct_fields`` — type_nid -> {field name: declared type's node id},
    from that type's own field declarations.

Both tables only ever hold a *bare*, same-package type (see
`graphify.extractors.go._go_bare_local_type`); a chain step that isn't in the
table stops resolution there — never a guess. Once the chain bottoms out at a
type, the final segment is looked up as that type's method, the same
(type_nid, method_name) -> method_nid index C#'s and Ruby's resolvers build
from `method` edges.

Deliberately narrower than the issue's full proposal:

  * A package-qualified receiver or field type (`uploader.IProfileUploader`,
    `*redis_rate.Limiter`) is out of scope: resolving it needs the
    cross-package qualified-type machinery `_resolve_go_type_references`
    already owns, not a second copy of it. Follow-up work.
  * A local variable's inferred type (`x := &Foo{}`) is not tracked — only a
    parameter, receiver, or field with an explicit declared type carries one.
  * Go has no `implements` keyword, so a call that reaches an interface
    method still stops there. Comparing method sets to find which structs
    satisfy which interfaces, and following `interface_dispatch`'s pattern
    from there, is the dispatch half of #3368 and is separate follow-up work.

Confidence is INFERRED (0.85, "strong inference"): the receiver's type is
proven structurally, but the call site itself never names it — the same tier
C#'s `recv.M()` case uses.
"""
from __future__ import annotations

from graphify.symbol_resolution import iter_raw_calls


def _merge_tables(per_file: list[dict], key: str) -> dict[str, dict[str, str]]:
    """Merge a per-file {outer: {inner: value}} table across the whole corpus.

    Outer keys are already full node ids (caller_nid or type_nid), so two
    files can only collide here by genuinely describing the same caller/type
    — an ordinary cross-file extend, not a cross-package one.
    """
    merged: dict[str, dict[str, str]] = {}
    for result in per_file:
        if not isinstance(result, dict):
            continue
        table = result.get(key)
        if not isinstance(table, dict):
            continue
        for outer_key, inner in table.items():
            if isinstance(inner, dict):
                merged.setdefault(outer_key, {}).update(inner)
    return merged


def _resolve_chain(
    member_receiver: str,
    caller_nid: str,
    local_types: dict[str, dict[str, str]],
    struct_fields: dict[str, dict[str, str]],
) -> str | None:
    """The type node id the dotted receiver chain bottoms out at, or ``None``.

    ``p`` resolves through the caller's own local-types table; each further
    segment (``.uploader``, then ``.anything_deeper``) resolves through the
    previous segment's struct-fields table. A miss at any step — the name
    isn't there, or it named a package-qualified/inferred type this pass
    doesn't track — stops the walk with no answer, rather than guessing.
    """
    segments = member_receiver.split(".")
    if not segments or not segments[0]:
        return None
    current_type = local_types.get(caller_nid, {}).get(segments[0])
    if current_type is None:
        return None
    for segment in segments[1:]:
        current_type = struct_fields.get(current_type, {}).get(segment)
        if current_type is None:
            return None
    return current_type


def resolve_go_member_calls(
    per_file: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> None:
    """Resolve Go member calls (``recv.Method()``) to the receiver's declared type.

    Additive and conservative: an untypable or ambiguous receiver, or a type
    that owns more than one method of the called name (never emitted by this
    extractor today, but not assumed), is left unresolved rather than guessed.
    """
    local_types = _merge_tables(per_file, "go_local_types")
    struct_fields = _merge_tables(per_file, "go_struct_fields")
    if not local_types:
        return

    node_by_id: dict[str, dict] = {
        str(n["id"]): n for n in all_nodes if n.get("id")
    }
    method_index: dict[tuple[str, str], str] = {}
    ambiguous: set[tuple[str, str]] = set()
    for e in all_edges:
        if e.get("relation") != "method":
            continue
        owner, method_nid = e.get("source"), e.get("target")
        if not owner or not method_nid:
            continue
        mnode = node_by_id.get(str(method_nid))
        if mnode is None or not str(mnode.get("source_file", "")).endswith(".go"):
            continue
        name = str(mnode.get("label", "")).strip("()").lstrip(".")
        if not name:
            continue
        key = (str(owner), name)
        method_nid_str = str(method_nid)
        if key in method_index and method_index[key] != method_nid_str:
            ambiguous.add(key)
        else:
            method_index[key] = method_nid_str

    existing_pairs = {(e.get("source"), e.get("target")) for e in all_edges}
    new_edges: list[dict] = []

    for rc in iter_raw_calls(per_file):
        if rc.get("language") != "go" or not rc.get("is_member_call"):
            continue
        member_receiver = rc.get("member_receiver")
        caller = rc.get("caller_nid")
        callee = rc.get("callee")
        if not member_receiver or not caller or not callee:
            continue
        target_type = _resolve_chain(str(member_receiver), str(caller), local_types, struct_fields)
        if target_type is None:
            continue
        key = (target_type, str(callee))
        if key in ambiguous:
            continue
        target = method_index.get(key)
        if target is None or target == caller or (caller, target) in existing_pairs:
            continue
        existing_pairs.add((caller, target))
        new_edges.append({
            "source": caller,
            "target": target,
            "relation": "calls",
            "context": "call",
            "confidence": "INFERRED",
            "confidence_score": 0.85,
            "source_file": rc.get("source_file", ""),
            "source_location": rc.get("source_location"),
            "weight": 1.0,
        })

    all_edges.extend(new_edges)
