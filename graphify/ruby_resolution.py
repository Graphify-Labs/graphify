"""Type-aware cross-file resolution for Ruby member calls.

Ruby has no type annotations and reuses method names heavily, so resolving
``obj.method()`` by globally-unique name is both lossy (drops on collision) and
unsafe (can attach to the wrong same-named method). This resolver instead uses
the receiver's *type*, inferred at extraction time from local
``var = ClassName.new`` bindings and carried on each member-call raw_call as
``receiver_type``.

It resolves three shapes, at EXTRACTED (1.0) confidence and only when the
target is certain (single owning class, single owned method) — bail otherwise:

  * ``Processor.new``          -> a ``calls`` edge to the ``Processor`` class
  * ``p.run`` where ``p`` is a ``Processor`` -> a ``calls`` edge to ``Processor#run``
  * bare ``run`` in a subclass -> promote the existing inferred edge when the
    same-kind method is uniquely proven by the extracted inheritance chain

Registered into graphify.resolver_registry and run by extract() after id
disambiguation, so node ids and raw_call caller_nids are final.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def _key(label: str) -> str:
    """Normalize a class/method label to a comparison key (drop punctuation)."""
    return re.sub(r"[^a-zA-Z0-9]+", "", str(label)).lower()


def _method_name(label: object) -> str:
    return str(label or "").strip("()").lstrip(".")


def _ruby_method_kind(node: dict | None) -> str | None:
    metadata = node.get("metadata") if isinstance(node, dict) else None
    if not isinstance(metadata, dict):
        return None
    kind = metadata.get("ruby_method_kind")
    return kind if kind in {"instance", "singleton"} else None


def _ruby_lookup_unsafe(node: dict | None) -> bool:
    metadata = node.get("metadata") if isinstance(node, dict) else None
    return isinstance(metadata, dict) and bool(
        metadata.get("ruby_lookup_unsafe") or metadata.get("ruby_reopened")
    )


# A Ruby class/module container node is labelled with a constant path, bare or
# ``::``-qualified (``Processor``, ``Billing::Rounding``); methods end in ``()``
# and files in ``.rb``. Lets us register method-less containers (a
# ``Class.new(StandardError)`` error class, an empty module) that have no
# `method` edge to be found by.
_BARE_CONST_RE = re.compile(r"^[A-Z][A-Za-z0-9_]*(?:::[A-Z][A-Za-z0-9_]*)*$")


def _ruby_raw_calls(per_file: list[dict]) -> list[dict]:
    calls: list[dict] = []
    for result in per_file:
        if not isinstance(result, dict):
            continue
        for rc in result.get("raw_calls", []):
            if not isinstance(rc, dict):
                continue
            sf = str(rc.get("source_file", ""))
            if sf.endswith((".rb", ".rake")):
                calls.append(rc)
    return calls


def resolve_ruby_member_calls(
    per_file: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> None:
    """Resolve Ruby ``Class.new`` and typed ``var.method`` calls by receiver type.

    Member-call resolution is additive. Inherited bare-call resolution only
    promotes an existing edge whose target is independently proven by ownership
    and ancestry; it never creates or redirects one.
    """
    node_by_id: dict[str, dict] = {
        str(node["id"]): node for node in all_nodes if node.get("id")
    }

    ruby_file_nodes = [
        node
        for node in all_nodes
        if str(node.get("source_file", "")).endswith((".rb", ".rake"))
        and node.get("label") == Path(str(node.get("source_file"))).name
    ]
    ruby_context_complete = bool(ruby_file_nodes) and all(
        isinstance(node.get("metadata"), dict)
        and node["metadata"].get("ruby_resolution_schema") == 1
        for node in ruby_file_nodes
    )
    unsafe_ruby_files = {
        str(node.get("source_file"))
        for node in ruby_file_nodes
        if _ruby_lookup_unsafe(node)
    }
    external_method_owners = {
        owner
        for node in ruby_file_nodes
        for metadata in [node.get("metadata")]
        if isinstance(metadata, dict)
        for owners in [metadata.get("ruby_external_method_owners", [])]
        if isinstance(owners, list)
        for owner in owners
        if isinstance(owner, str)
    }

    # class label key -> [class node ids]; (class_node_id, method_key) -> method id
    class_def_nids: dict[str, list[str]] = {}
    method_index: dict[tuple[str, str], str] = {}
    method_owners: dict[str, set[str]] = {}
    inheritance_edges: list[tuple[str, str, str | None, list[str] | None]] = []
    for e in all_edges:
        if e.get("relation") == "inherits":
            src, tgt = e.get("source"), e.get("target")
            if src and tgt:
                metadata = e.get("metadata")
                candidate_base = (
                    metadata.get("ruby_superclass_ref")
                    if isinstance(metadata, dict)
                    else None
                )
                raw_base = candidate_base if isinstance(candidate_base, str) else None
                candidate_scopes = (
                    metadata.get("ruby_lexical_scopes")
                    if isinstance(metadata, dict)
                    else None
                )
                lexical_scopes = (
                    candidate_scopes
                    if isinstance(candidate_scopes, list)
                    and all(isinstance(scope, str) for scope in candidate_scopes)
                    else None
                )
                inheritance_edges.append(
                    (str(src), str(tgt), raw_base, lexical_scopes)
                )
            continue
        if e.get("relation") != "method":
            continue
        src, tgt = e.get("source"), e.get("target")
        if not src or not tgt:
            continue
        src, tgt = str(src), str(tgt)
        cnode = node_by_id.get(src)
        if cnode is not None:
            class_source = str(cnode.get("source_file", ""))
            method_source = str(node_by_id.get(tgt, {}).get("source_file", ""))
            if not class_source.endswith((".rb", ".rake")) or not method_source.endswith(
                (".rb", ".rake")
            ):
                continue
            clabel = str(cnode.get("label", ""))
            class_def_nids.setdefault(_key(clabel), []).append(src)
            # A nested/compact declaration labels the node fully qualified
            # (`Billing::Processor`), but its receivers reference the bare last
            # segment (`Processor.new`), so index that too — the unique-match
            # guard below still bails on genuine collisions (#2302).
            if "::" in clabel:
                class_def_nids.setdefault(_key(clabel.split("::")[-1]), []).append(src)
        tnode = node_by_id.get(tgt)
        if tnode is not None:
            method_name = _method_name(tnode.get("label"))
            method_index[(src, method_name)] = tgt
            method_owners.setdefault(tgt, set()).add(src)
    # Also register class/module container nodes that own no `method` edge — a
    # method-less `Class.new(StandardError)` or an empty module — so a constant
    # receiver still resolves to a real node (#1640/#1634). External base stubs
    # carry an empty source_file, so the `.rb` filter keeps them out.
    for n in all_nodes:
        nid = n.get("id")
        sf = str(n.get("source_file", ""))
        label = str(n.get("label", ""))
        if nid and sf.endswith((".rb", ".rake")) and _BARE_CONST_RE.match(label):
            class_def_nids.setdefault(_key(label), []).append(str(nid))
            if "::" in label:
                class_def_nids.setdefault(_key(label.split("::")[-1]), []).append(str(nid))
    for k in list(class_def_nids):
        class_def_nids[k] = sorted(set(class_def_nids[k]))

    ruby_class_nids = {
        nid for nids in class_def_nids.values() for nid in nids
    }
    class_labels: dict[str, set[str]] = {}
    for nid in ruby_class_nids:
        label = str(node_by_id.get(nid, {}).get("label", ""))
        class_labels.setdefault(label, set()).add(nid)

    def _resolve_base(
        raw_base: str | None, lexical_scopes: list[str] | None
    ) -> str | None:
        """Resolve the extracted Ruby superclass reference in lexical order."""
        if not raw_base or lexical_scopes is None:
            return None
        reference = raw_base.removeprefix("::")
        ref_parts = [part for part in reference.split("::") if part]
        if not ref_parts:
            return None
        if raw_base.startswith("::"):
            lookup_scopes = [""]
        elif lexical_scopes:
            # A miss here is unsafe: Ruby searches inherited constants of the
            # innermost lexical owner before any root fallback, and that lookup
            # is not represented in the graph.
            lookup_scopes = lexical_scopes
        else:
            lookup_scopes = [""]
        for scope in lookup_scopes:
            candidate_label = "::".join(
                [*[part for part in scope.split("::") if part], *ref_parts]
            )
            candidates = class_labels.get(candidate_label, set())
            if len(candidates) == 1:
                return next(iter(candidates))
            if len(candidates) > 1:
                return None
            if scope and len(ref_parts) > 1:
                prefix_label = "::".join(
                    [
                        *[part for part in scope.split("::") if part],
                        *ref_parts[:-1],
                    ]
                )
                if class_labels.get(prefix_label):
                    # Ruby bound the qualified prefix in this nearer lexical
                    # scope.  Its inherited constants are not modelled, so do
                    # not retry the same prefix in an outer scope.
                    return None
        return None

    inheritance: dict[str, set[str]] = {}
    for source, edge_target, raw_base, lexical_scopes in inheritance_edges:
        if source not in ruby_class_nids:
            continue
        resolved = _resolve_base(raw_base, lexical_scopes)
        target_node = node_by_id.get(edge_target)
        target_label = str(target_node.get("label", "")) if target_node else ""
        target_source = str(target_node.get("source_file", "")) if target_node else ""
        raw_tail = str(raw_base or "").removeprefix("::").split("::")[-1]
        edge_matches_reference = bool(
            target_node
            and raw_tail
            and _key(target_label.split("::")[-1]) == _key(raw_tail)
        )
        # The structural target is independent evidence.  A normal unresolved
        # Ruby superclass remains a source-less last-segment stub after corpus
        # disambiguation, so accept that representation only when its label
        # agrees with the raw reference.  Conflicting edge/metadata pairs bail.
        if resolved is not None and (
            resolved == edge_target
            or (not target_source and edge_matches_reference)
        ):
            inheritance.setdefault(source, set()).add(resolved)

    methods_by_kind: dict[tuple[str, str, str], set[str]] = {}
    ambiguous_method_names: set[tuple[str, str]] = set()
    for method_nid, owners in method_owners.items():
        method_name = _method_name(node_by_id[method_nid].get("label"))
        method_kind = _ruby_method_kind(node_by_id.get(method_nid))
        if len(owners) != 1 or method_kind is None:
            ambiguous_method_names.update((owner, method_name) for owner in owners)
            continue
        owner = next(iter(owners))
        methods_by_kind.setdefault(
            (owner, method_name, method_kind),
            set(),
        ).add(method_nid)

    def _has_external_method_owner(label: str) -> bool:
        label_parts = tuple(part for part in label.split("::") if part)
        for raw_owner in external_method_owners:
            is_prefix = raw_owner.endswith("::*")
            owner_ref = raw_owner.removesuffix("::*") if is_prefix else raw_owner
            owner_parts = tuple(
                part for part in owner_ref.removeprefix("::").split("::") if part
            )
            if not owner_parts:
                continue
            if is_prefix:
                if owner_ref.startswith("::"):
                    if label_parts[: len(owner_parts)] == owner_parts:
                        return True
                elif any(
                    label_parts[index : index + len(owner_parts)] == owner_parts
                    for index in range(len(label_parts) - len(owner_parts) + 1)
                ):
                    return True
                continue
            if owner_ref.startswith("::") and label_parts == owner_parts:
                return True
            if not owner_ref.startswith("::") and label_parts[-len(owner_parts):] == owner_parts:
                return True
        return False

    def _segment_path(label: str) -> list[str]:
        return [s.strip().lower() for s in str(label).split("::") if s.strip()]

    # Fully-qualified and last-segment views of the same definitions, for the
    # scoped mixin lookup: `include Foo::Bar` must match a `Foo::Bar` label as a
    # whole path, never just its tail.
    fq_label_map: dict[tuple[str, ...], list[str]] = {}
    last_segment_map: dict[str, list[str]] = {}
    for nid in sorted({nid for nids in class_def_nids.values() for nid in nids}):
        segs = _segment_path(str(node_by_id.get(nid, {}).get("label", "")))
        if segs:
            fq_label_map.setdefault(tuple(segs), []).append(nid)
            last_segment_map.setdefault(segs[-1], []).append(nid)

    existing_pairs = {(e.get("source"), e.get("target")) for e in all_edges}

    def _unique_class(name: str) -> str | None:
        nids = class_def_nids.get(_key(name), [])
        return nids[0] if len(nids) == 1 else None

    def _class_by_const_path(raw: str) -> str | None:
        """Resolve a qualified constant receiver (``Billing::Processor``) to one class.

        Matches on the constant path rather than its tail: a class qualifies when its
        own label ends with the referenced segments, so ``Billing::Processor`` still
        finds an ``App::Billing::Processor`` while ``ActiveRecord::Base`` no longer
        binds to an unrelated ``Thing::Base`` (#3078). A leading ``::`` pins the
        reference to top level, so it must match the label whole. Ambiguous, or
        matching nothing in the corpus (the usual case for a framework constant) ->
        no edge, never a guess.
        """
        segs = tuple(_segment_path(raw))
        if not segs:
            return None
        if raw.strip().startswith("::"):
            nids = fq_label_map.get(segs, [])
            return nids[0] if len(nids) == 1 else None
        hits = {nid for path, nids in fq_label_map.items()
                if len(path) >= len(segs) and path[-len(segs):] == segs
                for nid in nids}
        return next(iter(hits)) if len(hits) == 1 else None

    def _emit(caller: str, target: str, rc: dict[str, Any],
              relation: str = "calls", context: str = "call") -> None:
        if not caller or not target or caller == target:
            return
        if (caller, target) in existing_pairs:
            return
        existing_pairs.add((caller, target))
        all_edges.append({
            "source": caller,
            "target": target,
            "relation": relation,
            "context": context,
            "confidence": "EXTRACTED",
            "confidence_score": 1.0,
            "source_file": rc.get("source_file", ""),
            "source_location": rc.get("source_location"),
            "weight": 1.0,
        })

    def _inherited_method(owner: str, name: str, kind: str) -> str | None:
        """Find one nearest same-kind method on one safe, acyclic base chain."""
        current = owner
        seen: set[str] = set()
        first = True
        while current not in seen:
            seen.add(current)
            node = node_by_id.get(current)
            label = str(node.get("label", "")) if node else ""
            if (
                current not in ruby_class_nids
                or len(class_labels.get(label, set())) != 1
                or _ruby_lookup_unsafe(node)
                or _has_external_method_owner(label)
            ):
                return None
            if (current, name) in ambiguous_method_names:
                return None
            candidates = methods_by_kind.get((current, name, kind), set())
            if candidates:
                if first or len(candidates) != 1:
                    return None
                return next(iter(candidates))
            bases = inheritance.get(current, set())
            if len(bases) != 1:
                return None
            current = next(iter(bases))
            first = False
        return None

    def _promote_inferred(caller: str, target: str, callee: str, rc: dict) -> None:
        """Promote exactly one matching edge in place; never create or repoint."""
        matches = [
            edge
            for edge in all_edges
            if edge.get("source") == caller
            and edge.get("target") == target
            and edge.get("relation") == "calls"
            and edge.get("context") == "call"
            and edge.get("confidence") == "INFERRED"
            and edge.get("source_file") == rc.get("source_file", "")
            and edge.get("source_location") == rc.get("source_location")
            and _method_name(node_by_id.get(target, {}).get("label")) == callee
        ]
        if len(matches) == 1:
            matches[0]["confidence"] = "EXTRACTED"
            matches[0]["confidence_score"] = 1.0

    # `include`/`extend`/`prepend <Const>` mixins (#1668): resolve the module
    # reference lexically, the way Ruby constant lookup works (#2302) — try the
    # reference under each enclosing scope of the including class, innermost
    # first, then top level (a leading `::` pins it to top level). A qualified
    # external like `ActiveSupport::Concern` matches no in-corpus path and
    # produces no edge; an unqualified reference with no lexical match falls
    # back to a globally unique last segment, under the same single-definition
    # god-node guard. Ambiguous at any step -> bail, no wrong edge.
    for rc in _ruby_raw_calls(per_file):
        if not rc.get("is_mixin"):
            continue
        caller = str(rc.get("caller_nid", ""))
        module_name = rc.get("callee")
        if not caller or not module_name:
            continue
        raw_ref = str(module_name)
        absolute = raw_ref.startswith("::")
        ref_segs = _segment_path(raw_ref)
        caller_node = node_by_id.get(caller)
        caller_segs = [] if absolute else _segment_path(
            str(caller_node.get("label", "")) if caller_node else "")
        target: str | None = None
        for i in range(len(caller_segs), -1, -1):
            nids = fq_label_map.get(tuple(caller_segs[:i] + ref_segs), [])
            if len(nids) == 1:
                target = nids[0]
                break
            if len(nids) > 1:
                break  # reopened/ambiguous definition: bail
        if target is None and len(ref_segs) == 1 and not absolute:
            nids = last_segment_map.get(ref_segs[0], [])
            if len(nids) == 1:
                target = nids[0]
        if target is not None:
            _emit(caller, target, rc, relation="mixes_in", context="mixin")

    # A Ruby bare call uses implicit `self`. The shared resolver has already
    # emitted a name-based INFERRED edge; only upgrade that exact edge when the
    # extracted method ownership and inheritance chain prove the same target.
    if ruby_context_complete:
        for rc in _ruby_raw_calls(per_file):
            if rc.get("is_mixin") or rc.get("is_member_call") is not False:
                continue
            caller = str(rc.get("caller_nid", ""))
            callee = str(rc.get("callee", ""))
            caller_kind = _ruby_method_kind(node_by_id.get(caller))
            owners = method_owners.get(caller, set())
            caller_file = str(node_by_id.get(caller, {}).get("source_file", ""))
            if (
                not caller
                or not callee
                or caller_kind is None
                or len(owners) != 1
                or caller_file in unsafe_ruby_files
            ):
                continue
            target = _inherited_method(next(iter(owners)), callee, caller_kind)
            if target is not None and target != caller:
                _promote_inferred(caller, target, callee, rc)

    for rc in _ruby_raw_calls(per_file):
        if not rc.get("is_member_call"):
            continue
        caller = str(rc.get("caller_nid", ""))
        callee = rc.get("callee")
        if not caller or not callee:
            continue

        # Constant receiver: `Processor.new` (instantiation) or `Service.call` /
        # `Model.where` (singleton / class method). The bare method name would
        # collide with unrelated same-named methods, so we resolve by the
        # receiver's class under the single-owning-class god-node guard.
        receiver = rc.get("receiver")
        # `lstrip(":")` so a top-level-pinned `::Processor.call` is still recognised
        # as a constant receiver now that the whole path is captured (#3078).
        if receiver and str(receiver).lstrip(":")[:1].isupper():
            recv_raw = str(receiver)
            class_nid = (_class_by_const_path(recv_raw) if "::" in recv_raw
                         else _unique_class(recv_raw))
            if class_nid is not None:
                if callee == "new":
                    _emit(caller, class_nid, rc)
                else:
                    # Emit to the singleton/instance method the class owns
                    # (`def self.call`, which the extractor indexes); otherwise
                    # to the class node itself, so inherited/dynamic class methods
                    # like ActiveRecord `where`/`find_by` still give correct
                    # blast-radius. An ambiguous receiver bails to nothing.
                    method_nid = method_index.get((class_nid, str(callee)))
                    _emit(caller, method_nid or class_nid, rc)
            continue

        # `p.run` where p's type is known -> edge to that class's method.
        receiver_type = rc.get("receiver_type")
        if not receiver_type:
            continue
        class_nid = _unique_class(str(receiver_type))
        if class_nid is None:
            continue
        method_nid = method_index.get((class_nid, str(callee)))
        if method_nid is None:
            continue
        _emit(caller, method_nid, rc)
