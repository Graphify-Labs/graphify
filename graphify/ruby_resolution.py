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


def _ruby_raw_calls(per_file: list[dict]) -> list[dict]:
    calls: list[dict] = []
    for result in per_file:
        if not isinstance(result, dict):
            continue
        for rc in result.get("raw_calls", []):
            if not isinstance(rc, dict):
                continue
            sf = str(rc.get("source_file", ""))
            if sf.endswith(".rb"):
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
            class_def_nids.setdefault(_key(cnode.get("label", "")), []).append(str(src))
        tnode = node_by_id.get(tgt)
        if tnode is not None:
            method_index[(str(src), _key(tnode.get("label", "")))] = str(tgt)
    for k in list(class_def_nids):
        class_def_nids[k] = sorted(set(class_def_nids[k]))

    existing_pairs = {(e.get("source"), e.get("target")) for e in all_edges}

    def _unique_class(name: str) -> str | None:
        nids = class_def_nids.get(_key(name), [])
        return nids[0] if len(nids) == 1 else None

    def _emit(caller: str, target: str, rc: dict[str, Any]) -> None:
        if not caller or not target or caller == target:
            return
        if (caller, target) in existing_pairs:
            return
        existing_pairs.add((caller, target))
        all_edges.append({
            "source": caller,
            "target": target,
            "relation": "calls",
            "context": "call",
            "confidence": "EXTRACTED",
            "confidence_score": 1.0,
            "source_file": rc.get("source_file", ""),
            "source_location": rc.get("source_location"),
            "weight": 1.0,
        })

    for rc in _ruby_raw_calls(per_file):
        if not rc.get("is_member_call"):
            continue
        caller = str(rc.get("caller_nid", ""))
        callee = rc.get("callee")
        if not caller or not callee:
            continue

        # `Processor.new` -> instantiation edge to the class.
        receiver = rc.get("receiver")
        if callee == "new" and receiver and str(receiver)[:1].isupper():
            class_nid = _unique_class(str(receiver))
            if class_nid is not None:
                _emit(caller, class_nid, rc)
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
