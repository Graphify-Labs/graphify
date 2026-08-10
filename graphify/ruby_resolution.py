"""Type-aware cross-file resolution for Ruby member calls.

Ruby has no type annotations and reuses method names heavily, so resolving
``obj.method()`` by globally-unique name is both lossy (drops on collision) and
unsafe (can attach to the wrong same-named method). This resolver instead uses
the receiver's *type*, inferred at extraction time from local
``var = ClassName.new`` bindings and carried on each member-call raw_call as
``receiver_type``.

It resolves two shapes, both at EXTRACTED (1.0) confidence and only when the
target is certain (single owning class, single owned method) — bail otherwise:

  * ``Processor.new``          -> a ``calls`` edge to the ``Processor`` class
  * ``p.run`` where ``p`` is a ``Processor`` -> a ``calls`` edge to ``Processor#run``

Registered into graphify.resolver_registry and run by extract() after id
disambiguation, so node ids and raw_call caller_nids are final.
"""

from __future__ import annotations

import re
from typing import Any


def _key(label: str) -> str:
    """Normalize a class/method label to a comparison key (drop punctuation)."""
    return re.sub(r"[^a-zA-Z0-9]+", "", str(label)).lower()


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

    Purely additive: only emits edges the shared (name-based) call pass skips
    because they are member calls. Each emission requires a single owning class
    (god-node guard) so an ambiguous class name resolves to nothing rather than a
    wrong edge.
    """
    node_by_id: dict[str, dict] = {n.get("id"): n for n in all_nodes}

    # class label key -> [class node ids]; (class_node_id, method_key) -> method id
    class_def_nids: dict[str, list[str]] = {}
    method_index: dict[tuple[str, str], str] = {}
    for e in all_edges:
        if e.get("relation") != "method":
            continue
        src, tgt = e.get("source"), e.get("target")
        cnode = node_by_id.get(src)
        if cnode is not None:
            clabel = str(cnode.get("label", ""))
            class_def_nids.setdefault(_key(clabel), []).append(str(src))
            # A nested/compact declaration labels the node fully qualified
            # (`Billing::Processor`), but its receivers reference the bare last
            # segment (`Processor.new`), so index that too — the unique-match
            # guard below still bails on genuine collisions (#2302).
            if "::" in clabel:
                class_def_nids.setdefault(_key(clabel.split("::")[-1]), []).append(str(src))
        tnode = node_by_id.get(tgt)
        if tnode is not None:
            method_index[(str(src), _key(tnode.get("label", "")))] = str(tgt)
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
        if receiver and str(receiver)[:1].isupper():
            class_nid = _unique_class(str(receiver))
            if class_nid is not None:
                if callee == "new":
                    _emit(caller, class_nid, rc)
                else:
                    # Emit to the singleton/instance method the class owns
                    # (`def self.call`, which the extractor indexes); otherwise
                    # to the class node itself, so inherited/dynamic class methods
                    # like ActiveRecord `where`/`find_by` still give correct
                    # blast-radius. An ambiguous receiver bails to nothing.
                    method_nid = method_index.get((class_nid, _key(str(callee))))
                    _emit(caller, method_nid or class_nid, rc)
            continue

        # `p.run` where p's type is known -> edge to that class's method.
        receiver_type = rc.get("receiver_type")
        if not receiver_type:
            continue
        class_nid = _unique_class(str(receiver_type))
        if class_nid is None:
            continue
        method_nid = method_index.get((class_nid, _key(str(callee))))
        if method_nid is None:
            continue
        _emit(caller, method_nid, rc)
