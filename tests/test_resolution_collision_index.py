"""`_collision_aware` picks the same caller as before, without a scan per use.

The pass that credits a call inside ``_main`` to ``_main`` rather than ``main``
(#4994) scanned every node id for every resolved use fact, and on a hit
scanned every node again: O(uses x nodes). That alone ran for 50 minutes on
vscode without finishing. It now groups the salted ids by their plain id once.
These tests pin the answers to a copy of the old loop and check that the
number of passes over ``nodes`` no longer grows with the number of uses.
"""

from __future__ import annotations

import random
import re
from pathlib import Path

from graphify.extractors.models import _SymbolResolutionFacts, _SymbolUseFact
from graphify.extractors.resolution import _apply_symbol_resolution_facts, _js_source_path


def _old_collision_aware(nodes, root, source_id, file_path, line):
    """Verbatim copy of the pre-index loop, kept as the reference answer."""
    owned = {str(n.get("id")) for n in nodes}
    if not any(other.startswith(source_id + "_") for other in owned):
        return source_id
    candidates = [n for n in nodes if n.get("id") == source_id or (
        isinstance(n.get("id"), str)
        and n["id"].startswith(source_id + "_")
        and re.fullmatch(r"[0-9a-f]{6}", n["id"][len(source_id) + 1:]) is not None
        and _js_source_path(str(n.get("source_file") or ""), root) == file_path
    )]
    if len(candidates) < 2:
        return source_id

    def _start(node):
        try:
            return int(str(node.get("source_location") or "").removeprefix("L"))
        except ValueError:
            return 0

    enclosing = [n for n in candidates if _start(n) <= line]
    if not enclosing:
        return source_id
    return str(max(enclosing, key=_start)["id"])


class _CountingList(list):
    """A list that counts how many times it is iterated."""

    iterations = 0

    def __iter__(self):
        type(self).iterations += 1
        return super().__iter__()


def _build(tmp_path: Path, n_bases: int, n_uses: int, seed: int):
    """Many plain ids, each with salted siblings, children, duplicates and ties."""
    rng = random.Random(seed)
    files = [tmp_path / f"m{i}.py" for i in range(4)]
    nodes: list[dict] = []
    for f in files:
        # Same-file fallback target for the `inherits` uses below.
        nodes.append({"id": f"{f.stem}_target", "label": "Target",
                      "source_file": str(f), "source_location": "L1"})
    bases = [f"m_base{i}" for i in range(n_bases)]
    for base in bases:
        home = rng.choice(files)
        nodes.append({"id": base, "label": f"{base}()", "source_file": str(home),
                      "source_location": f"L{rng.randint(1, 400)}"})
        for _ in range(rng.randint(0, 3)):
            salt = "".join(rng.choice("0123456789abcdef") for _ in range(6))
            nodes.append({
                "id": f"{base}_{salt}",
                "label": f"_{base}()",
                # Mostly the same file; sometimes another file, which must not count.
                "source_file": str(home if rng.random() < 0.8 else rng.choice(files)),
                # Coarse lines so ties happen; sometimes unparsable.
                "source_location": rng.choice([f"L{rng.randint(1, 40) * 10}", "", "Lx"]),
            })
        if rng.random() < 0.3:
            # A child id: alphanumeric suffix, never a sibling spelling.
            nodes.append({"id": f"{base}_method", "label": ".method()",
                          "source_file": str(home), "source_location": "L5"})
        if rng.random() < 0.2:
            # Upper-case hex and 7 chars are not a salt either.
            nodes.append({"id": f"{base}_ABCDEF", "label": "x", "source_file": str(home),
                          "source_location": "L2"})
            nodes.append({"id": f"{base}_abcdef0", "label": "y", "source_file": str(home),
                          "source_location": "L3"})
        if rng.random() < 0.1:
            # A duplicate of the plain id, from another file.
            nodes.append({"id": base, "label": f"{base}()",
                          "source_file": str(rng.choice(files)), "source_location": "L7"})
    rng.shuffle(nodes)
    uses = [
        _SymbolUseFact(
            file_path=rng.choice(files),
            source_id=rng.choice(bases),
            local_name="Target",
            relation="inherits",
            context=f"c{i}",
            line=rng.randint(1, 420),
        )
        for i in range(n_uses)
    ]
    return files, nodes, uses


def _run(tmp_path, files, nodes, uses, node_list_type=list):
    nodes = node_list_type(dict(n) for n in nodes)
    edges: list[dict] = []
    facts = _SymbolResolutionFacts(uses=list(uses))
    _apply_symbol_resolution_facts(files, nodes, edges, tmp_path, facts)
    return edges


def test_same_caller_as_the_old_scan(tmp_path):
    for seed in range(5):
        files, nodes, uses = _build(tmp_path, n_bases=150, n_uses=600, seed=seed)
        edges = _run(tmp_path, files, nodes, uses)
        got = [(e["source"], e["context"]) for e in edges if e["relation"] == "inherits"]
        expected = [
            (_old_collision_aware(nodes, tmp_path, u.source_id, u.file_path.resolve(), u.line),
             u.context)
            for u in uses
        ]
        assert got == expected
        # The salted sibling is actually chosen for a good share of the uses.
        assert sum(1 for (src, _), u in zip(got, uses) if src != u.source_id) > 50


def test_passes_over_nodes_do_not_grow_with_uses(tmp_path):
    files, nodes, uses = _build(tmp_path, n_bases=100, n_uses=400, seed=7)

    def iterations(n_uses):
        _CountingList.iterations = 0
        _run(tmp_path, files, nodes, uses[:n_uses], node_list_type=_CountingList)
        return _CountingList.iterations

    assert iterations(400) == iterations(20)
