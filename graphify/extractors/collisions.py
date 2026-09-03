"""Same-file symbol-id collision handling, shared by the AST extractors.

Node ids are aggressively normalized (``ids.py``): casefolded to a fixpoint,
punctuation collapsed, leading/trailing underscores stripped. That recipe is
deliberate — it is the contract that lets three independent producers (the
AST extractor, the semantic LLM subagents, the graph builder) mint the same
id for the same symbol (#811, #550, #1033, #1104, #2614) — and it means
DISTINCT declared names in one file can normalize to one id: ``Session`` vs
``session()``, ``_get_connection`` vs ``get_connection``, ``visit_TEXT`` vs
``visit_text``. The per-file ``seen_ids`` guard then kept whichever
definition came first and silently dropped every later one; the loser's
structural edge and body calls were mis-attributed to the survivor (#3302).

The Go extractor already solved this for its function/method declarations
(#2779): census the raw declared names that share a plain id, keep the plain
id on ONE canonical member, and give every other member a salt derived from
its raw name — deterministic, order-independent, and stable across runs
because the salt depends only on the name. This module lifts that mechanism
out of ``go.py`` so every extractor can use it.

Two rules carried over from #2779, both load-bearing:

- **Exactly one member keeps the plain id** (or none — see the all-salted
  branch). The semantic tier can only ever emit the plain lowercase id (the
  node-ID spec in ``llm.py`` has no channel for case or underscores), and
  ``build_from_json`` reconciles stored/LLM edge endpoints through
  ``normalize_id``; both land on the plain id, so it must stay bound to the
  member those references actually mean.
- **The assignment must not depend on declaration order.** Ids feed
  incremental updates and cross-file edges cached in graph.json; reordering
  two definitions in a file must not swap their ids.

A re-definition of the SAME raw name (``@overload`` stubs, ``if PY2:`` /
``else:`` conditional defs, ``#[cfg(...)]``-gated variants, C# partial
halves, Swift same-file extensions) is one symbol with several definition
sites, not a collision — it stays a single node, exactly as before.

Only class-like and function-like definition nodes participate. File nodes,
``type=module``/``namespace`` anchors (the #1327 exemption), member/field
nodes, and the sourceless reference stubs of ``ensure_named_node`` (#1402)
keep their first-wins behavior untouched.

How the extractors use it — the mint-pass loop
----------------------------------------------

An extractor cannot know the full collision group up front without
re-implementing its own id-derivation logic as a pre-scan (namespace stacks,
class nesting, decorated wrappers...), which is how id-recipe drift starts.
Instead the node walk runs inside ``SymbolCollisionCensus.passes()``:

1. The first walk assigns provisionally: the first writer keeps the plain
   id, a later definition with a DIFFERENT raw name gets the salted id.
2. ``passes()`` then settles the census. If the canonical member of every
   group already holds the plain id (collision-free files — virtually all —
   trivially qualify), the loop ends after one walk.
3. Otherwise the final assignment is pinned and the walk RE-RUNS from
   scratch, so ids derived from a re-assigned id (a method id embeds its
   class's id) are re-minted from the canonical form rather than patched
   afterwards. Re-derivation cannot miss a registry the way a post-hoc
   id-rewrite of every nid-keyed structure could.

The loop is bounded (``_MAX_MINT_PASSES``); a pass that changes nothing ends
it, and derivation chains (class id -> method id) shift group keys at most
once per nesting level, so real inputs settle in one or two walks.
"""
from __future__ import annotations

import hashlib
from collections.abc import Callable, Container, Iterator

__all__ = [
    "SymbolCollisionCensus",
    "canonical_raw_name",
    "collision_salt",
    "exported_canonical_raw_name",
    "raw_symbol_name",
    "salted_symbol_id",
]

# Node walks re-run only while the census keeps re-pinning, which shifts a
# group's key at most once per derivation level (class -> method). The cap is
# a termination guard for pathological inputs (e.g. a non-participating node
# squatting on a pinned plain id); when it trips, the last walk's assignment
# stands — every id it handed out is still unique and deterministic, the
# canonical member may just not hold the plain id.
_MAX_MINT_PASSES = 4


def raw_symbol_name(label: str) -> str:
    """The raw declared name behind a node label.

    Labels wrap the declared name in presentation markers only — ``name()``
    for functions, ``.name()`` for members — so this is the exact inverse the
    call-graph pass already uses to build ``label_to_nid``.
    """
    return label.strip("()").lstrip(".")


def collision_salt(raw_name: str) -> str:
    """Deterministic per-name salt: first 6 hex chars of sha1(raw_name).

    Name-derived on purpose. A line-number salt churns on every edit above
    the definition; a document-order suffix renumbers siblings on insert.
    The name only changes when the symbol itself is renamed — which SHOULD
    move the id. Same shape and truncation as the two existing salts (the
    path salt in ``_disambiguate_colliding_node_ids`` #1522, the case salt
    in Go's #2779), accepting the same ~2^-24 per-pair truncation bound.
    """
    return hashlib.sha1(raw_name.encode("utf-8"), usedforsecurity=False).hexdigest()[:6]


def salted_symbol_id(plain_nid: str, raw_name: str) -> str:
    """The id a non-canonical collision-group member gets."""
    # Deferred import keeps this module importable from base.py contexts.
    from graphify.extractors.base import _make_id

    return _make_id(plain_nid, collision_salt(raw_name))


def canonical_raw_name(members: dict[str, str]) -> str | None:
    """Default canonical-member preference: which raw name keeps the plain id.

    ``members`` maps each raw declared name in the group to its kind
    (``"class"`` or ``"function"``). Returns the winning raw name, or None
    when no rule singles one out — then EVERY member is salted, so an
    ambiguous reference resolves to nothing rather than to an arbitrary
    winner (#2779's documented all-salted branch).

    1. The unique member with the fewest leading underscores. ``_foo``/
       ``foo`` and ``__foo``/``_foo`` give the public spelling the plain id —
       that is where by-name references, docs, and semantic-tier ids land.
    2. Else the unique class-like member among that tie. ``class Session`` vs
       ``def session()``: the class keeps the plain id it already holds in
       existing graphs (it is the member that survived first-wins in the
       overwhelmingly common declaration order), so nothing stored re-points.
    3. Else None: ``visit_TEXT``/``visit_text``, ``Run``/``RUN``.
    """

    def _underscores(name: str) -> int:
        return len(name) - len(name.lstrip("_"))

    fewest = min(_underscores(name) for name in members)
    tied = [name for name in members if _underscores(name) == fewest]
    if len(tied) == 1:
        return tied[0]
    class_like = [name for name in tied if members[name] == "class"]
    if len(class_like) == 1:
        return class_like[0]
    return None


def exported_canonical_raw_name(members: dict[str, str]) -> str | None:
    """Go's #2779 preference: the unique EXPORTED member keeps the plain id.

    Only exported symbols are reachable across packages, so cross-package
    edges (and edges cached in graph.json from files an incremental rebuild
    does not touch) target the exported one — keeping its id stable means
    adding/removing an unexported sibling never re-points them. Shipped Go
    ids must not move, so Go keeps this rule instead of the default.
    """
    exported = [name for name in members if name[:1].isupper()]
    if len(exported) == 1:
        return exported[0]
    return None


class SymbolCollisionCensus:
    """Per-file census of definition ids, driving the mint-pass loop.

    One instance per extracted file. The extractor's ``add_node`` calls
    :meth:`assign` for every class-like/function-like definition; the walk
    itself runs inside ``for _ in census.passes():`` and is re-run only when
    settling the census changed an assignment (see the module docstring).
    """

    def __init__(
        self, preference: Callable[[dict[str, str]], str | None] = canonical_raw_name
    ) -> None:
        self._preference = preference
        # plain id -> {raw name -> (effective id, kind)}; rebuilt every pass.
        self._groups: dict[str, dict[str, tuple[str, str]]] = {}
        # (plain id, raw name) -> settled final id; carried across passes.
        self._pins: dict[tuple[str, str], str] = {}

    def passes(self) -> Iterator[int]:
        """Yield once per node walk; stop as soon as the assignment settles.

        The caller must reset every per-walk structure (nodes, edges,
        seen ids, ...) at the top of the loop body — a pass replays the walk
        in full.
        """
        for attempt in range(_MAX_MINT_PASSES):
            self._groups = {}
            yield attempt
            if self._settle():
                return

    def assign(
        self, plain_nid: str, raw_name: str, kind: str, taken: Container[str]
    ) -> tuple[str, bool]:
        """Pick the effective id for one definition mint.

        Returns ``(effective_id, already_present)``. ``already_present`` is
        True when the definition collapses onto an existing node (a
        re-definition of the same raw name, or first-wins against a
        non-participating occupant) — the caller must then NOT create a node
        and use the returned id for edges and body attribution, exactly as it
        would for a fresh one.

        ``taken`` is the extractor's ``seen_ids`` — every id already handed
        out this pass, participating or not.
        """
        group = self._groups.setdefault(plain_nid, {})
        member = group.get(raw_name)
        if member is not None:
            # Same raw name declared again: one symbol, several definition
            # sites — deliberately ONE node (splitting would fabricate a node
            # per @overload stub / cfg branch / conditional re-definition).
            return member[0], True
        pinned = self._pins.get((plain_nid, raw_name))
        if pinned is not None and pinned not in taken:
            group[raw_name] = (pinned, kind)
            return pinned, False
        if plain_nid not in taken:
            group[raw_name] = (plain_nid, kind)
            return plain_nid, False
        if not group:
            # The plain id is held by a NON-participating node (file node,
            # namespace anchor, member node, sourceless stub): keep the
            # pre-existing first-wins behavior for that boundary untouched.
            return plain_nid, True
        salted = salted_symbol_id(plain_nid, raw_name)
        if salted in taken:
            # sha1[:6] truncation collision inside one scope (~2^-24 per
            # pair): fail soft to the old collapse rather than cascading.
            return salted, True
        group[raw_name] = (salted, kind)
        return salted, False

    def _settle(self) -> bool:
        """Pin the final assignment; True when this pass already matched it.

        Runs after a full walk, when every group member is known. The
        preference re-picks the canonical member per group — this is what
        makes the outcome independent of declaration order: the first walk's
        first-writer-keeps-plain is only ever provisional.
        """
        settled = True
        for plain_nid, group in self._groups.items():
            if len(group) < 2:
                continue
            canonical = self._preference(
                {raw: kind for raw, (_effective, kind) in group.items()}
            )
            for raw, (effective, _kind) in group.items():
                final = (
                    plain_nid if raw == canonical else salted_symbol_id(plain_nid, raw)
                )
                self._pins[(plain_nid, raw)] = final
                if final != effective:
                    settled = False
        return settled
