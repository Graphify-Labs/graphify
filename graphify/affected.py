from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from itertools import chain
from pathlib import Path
from typing import Iterable, Iterator
import unicodedata

import networkx as nx


DEFAULT_AFFECTED_RELATIONS = (
    "calls",
    "indirect_call",
    "references",
    "imports",
    "imports_from",
    # `import('…')` — emitted by the Svelte/Astro/Vue rescue passes and (since
    # #2575) by plain JS/TS too. Omitting it made every dynamic import
    # invisible to blast-radius traversal even where the edge WAS in the
    # graph, and dynamic import is precisely how codebases break require
    # cycles, so the missing edges sat under the most load-bearing modules.
    "dynamic_import",
    "re_exports",
    "inherits",
    "extends",
    "implements",
    "uses",
    "mixes_in",
    "embeds",
    "requires",
)


@dataclass(frozen=True)
class AffectedHit:
    node_id: str
    depth: int
    via_relation: str
    # The traversed edge's location — the actual call/import/reference SITE in
    # this node's file, not the node's own definition line (#BUG1). Defaults keep
    # existing constructors/tests working; None falls back to the node's def line.
    via_file: "str | None" = None
    via_location: "str | None" = None


class SeedResolutionError(LookupError):
    """The `affected` query named no node, or several; the message says which."""


# Cap on the candidates an ambiguity message lists; a short substring query
# can tie hundreds of nodes.
_MAX_LISTED_CANDIDATES = 20


def _node_label(graph: nx.Graph, node_id: str) -> str:
    data = graph.nodes[node_id]
    return str(data.get("label") or node_id)


def _owned_pairs(edges: Iterable[tuple]) -> Iterator[tuple[str, str]]:
    """(owner, member) for each `method`/`contains` edge among `edges`.

    The owner is the edge's stored source: its `_src`/`_tgt` markers where
    present, else arc order. An undirected graph (`build_from_json`'s default)
    keeps direction only in the markers, so reading arc order there reversed
    ownership whenever the member node was inserted before its owner. Markers
    that do not name the edge's own endpoints are ignored, as in serve.py.
    """
    for u, v, data in edges:
        if str(data.get("relation", "")) not in ("method", "contains"):
            continue
        src, tgt = data.get("_src", u), data.get("_tgt", v)
        if {src, tgt} != {u, v}:
            src, tgt = u, v
        if src != tgt:
            yield str(src), str(tgt)


class _Ownership:
    """Owner and member lookups over `method`/`contains` edges, for seed
    resolution. (`affected_nodes` keeps its own member seeding unchanged.)

    A DiGraph is read per node, from that node's own edges. An undirected
    graph's arc order is not its direction, and its fallback order comes from
    a whole-graph edge pass, so it is indexed from one such pass on first use.
    Scanning every edge per lookup made a qualified seed cost (matching
    members x edges): 17 s for 4,000 edges.
    """

    def __init__(self, graph: nx.Graph) -> None:
        self._graph = graph
        self._index: dict[str, list[tuple[str, str]]] | None = None

    def _pairs(self, node_id: str) -> list[tuple[str, str]]:
        graph = self._graph
        if isinstance(graph, nx.DiGraph):
            return list(_owned_pairs(
                chain(graph.out_edges(node_id, data=True), graph.in_edges(node_id, data=True))
            ))
        if self._index is None:
            self._index = {}
            for pair in _owned_pairs(graph.edges(data=True)):
                for end in pair:
                    self._index.setdefault(end, []).append(pair)
        return self._index.get(node_id, [])

    def members(self, node_id: str) -> list[str]:
        """Nodes `node_id` owns through one `method`/`contains` edge."""
        return [member for owner, member in self._pairs(node_id) if owner == node_id]

    def owners(self, node_id: str) -> list[str]:
        """Nodes that own `node_id` through one `method`/`contains` edge."""
        return [owner for owner, member in self._pairs(node_id) if member == node_id]


def _format_location(data: dict) -> str:
    source_file = data.get("source_file") or "-"
    source_location = data.get("source_location")
    if source_location:
        return f"{source_file}:{source_location}"
    return str(source_file)


def _bare_name(label: str) -> str:
    """Lowercased label with the callable decoration (trailing "()") removed."""
    label = _normalize_label(label)
    return label[:-2] if label.endswith("()") else label


def _label_names(label: str) -> tuple[str, ...]:
    """Bare names a node label answers to.

    A method label (".send()") also answers to its name without the leading
    ".", so "send" names it as it names the function "send()". Only the
    method shape (leading "." and trailing "()") loses the dot: a dotfile such
    as ".config" keeps it, so "Config()" still means the class `Config`.
    """
    bare = _bare_name(label)
    if bare.startswith(".") and _normalize_label(label).endswith("()"):
        return (bare, bare[1:])
    return (bare,)


def _normalize_label(label: str) -> str:
    return unicodedata.normalize("NFC", label).casefold()


def _as_repo_relative(query: str, root: Path | None = None) -> str:
    """Repo-relative form of a path query, for matching a stored `source_file`.

    The graph stores repo-relative paths, so `./src/x.py` and
    `/abs/repo/src/x.py` name the same file as `src/x.py` and yet matched
    nothing. `affected` then printed an empty list and exited 0 — a blast-radius
    tool answering "nothing depends on this" about a file with sixteen
    dependents, and indistinguishable from a genuine zero or a typo.

    An absolute path is anchored to `root` when given — the repo root derived
    from the graph's own location — so a seed resolves regardless of the caller's
    working directory (#2706: an absolute-path seed previously only matched when
    cwd happened to be the analysed repo root, which no editor or script can
    guarantee). `root` falls back to the current directory to preserve the prior
    behaviour when a caller has no graph location to derive it from.

    Non-path queries pass through unchanged: `Path("myFunc()").as_posix()` is
    `"myFunc()"`, so label resolution is untouched. An absolute path rooted
    outside `root` is left alone — no basename guessing.
    """
    path = Path(query)
    if path.is_absolute():
        anchor = root if root is not None else Path.cwd()
        try:
            return path.relative_to(anchor).as_posix()
        except ValueError:
            # Rooted outside the repo: nothing here can make it repo-relative,
            # so leave it alone rather than guess at a basename that would match
            # some unrelated file with the same name.
            return query
    return path.as_posix()


def _prefer_file_node(
    graph: nx.Graph,
    node_ids: list[str],
    query: str,
) -> str | None:
    """Return the file-level node when a source_file query matches many nodes."""
    query_basename = _normalize_label(Path(query).name)
    exact_file_nodes = [
        node_id
        for node_id in node_ids
        if str(graph.nodes[node_id].get("source_location", "")) == "L1"
        and _normalize_label(str(graph.nodes[node_id].get("label", ""))) == query_basename
    ]
    if len(exact_file_nodes) == 1:
        return exact_file_nodes[0]

    l1_nodes = [
        node_id
        for node_id in node_ids
        if str(graph.nodes[node_id].get("source_location", "")) == "L1"
    ]
    if len(l1_nodes) == 1:
        return l1_nodes[0]

    basename_nodes = [
        node_id
        for node_id in node_ids
        if _normalize_label(str(graph.nodes[node_id].get("label", ""))) == query_basename
    ]
    if len(basename_nodes) == 1:
        return basename_nodes[0]

    return None


def _label_matches(graph: nx.Graph, name: str, node_ids: Iterable[str]) -> list[str]:
    """Nodes among `node_ids` labeled `name`: exact label first, else bare name.

    Source-backed nodes come first in both, so a sourceless stub that matches
    exactly (`Handle`, left by a `handler: Handle` annotation) cannot hide the
    real definition that matches by bare name (`handle()`).
    """
    node_ids = list(node_ids)
    name_lower = _normalize_label(name)
    exact = [
        node_id
        for node_id in node_ids
        if _normalize_label(str(graph.nodes[node_id].get("label", ""))) == name_lower
    ]
    bare = _named_ids(graph, name, node_ids)
    return _source_backed(graph, exact) or _source_backed(graph, bare) or exact or bare


def _named_ids(graph: nx.Graph, name: str, node_ids: Iterable[str]) -> list[str]:
    """Nodes among `node_ids` whose label names `name`, exactly or by bare name."""
    name_bare = _bare_name(name)
    return [
        node_id
        for node_id in node_ids
        if name_bare in _label_names(str(graph.nodes[node_id].get("label", "")))
    ]


def _bare_name_matches(graph: nx.Graph, query: str) -> list[str]:
    query_bare = _bare_name(query)
    return [
        str(node_id)
        for node_id, data in graph.nodes(data=True)
        if query_bare in _label_names(str(data.get("label", "")))
    ]


def _source_backed(graph: nx.Graph, node_ids: list[str]) -> list[str]:
    return [
        node_id
        for node_id in node_ids
        if str(graph.nodes[node_id].get("source_file") or "").strip()
    ]


def _prefer_source_backed(graph: nx.Graph, hits: list[str], query: str) -> list[str]:
    """`hits` without sourceless stubs when any source-backed node is among them.

    A tier that matched only stubs yields to the real definitions with the
    query's bare name: the stub `Send` (id `send`, left by a `send: Send`
    annotation) must not answer for the real `send` methods.
    """
    if hits and not _source_backed(graph, hits):
        hits = _source_backed(graph, _bare_name_matches(graph, query)) or hits
    return _source_backed(graph, hits) or hits


def _is_path(graph: nx.Graph, text: str, root: Path | None) -> bool:
    """Is the left half of a `::` query a path?

    Yes when it has a path separator or names a file in the graph, exactly or
    after normalization, even when that matches several files (see
    `_path_files`), spaces or not: `my pkg/client.py`. Otherwise only a file
    suffix without whitespace counts, so a docstring label such as
    `Registers a function. .. versionadded:: 0.11` stays prose.
    """
    if "/" in text or "\\" in text or _path_files(graph, text, root):
        return True
    return not any(char.isspace() for char in text) and bool(Path(text).suffix)


def _path_files(graph: nx.Graph, path: str, root: Path | None) -> dict[str, list[str]]:
    """The files `path` names (compared in repo-relative form), each with its
    nodes.

    The exact spelling wins: on Linux `a.py` and `A.py` are two files, and so
    are `caf\u00e9.py` and `cafe\u0301.py` (composed and decomposed). When any
    node has the exact path, only that file is returned. Otherwise every file
    that matches after case and Unicode normalization is returned. One such
    file is what a wrong-case path on Windows or macOS means. Several are a
    tie that the caller must report, not settle.
    """
    query_path = _as_repo_relative(path, root)
    query_key = _normalize_label(query_path)
    by_file: dict[str, list[str]] = {}
    for node_id, data in graph.nodes(data=True):
        source_file = str(data.get("source_file") or "")
        if source_file and _normalize_label(source_file) == query_key:
            by_file.setdefault(source_file, []).append(str(node_id))
    if query_path in by_file:
        return {query_path: by_file[query_path]}
    return by_file


def _split_qualified(query: str) -> tuple[str, bool, str, str]:
    """`query` as (path, has `::`, owner, member); owner is "" for a plain symbol.

    The path is kept exactly as typed: on Linux ` a.py` and `a.py` are two
    files, so trimming it could name the other one. Only the symbol half is
    trimmed, since labels do not start or end with spaces.
    """
    path_part, sep, symbol = query.partition("::")
    if not sep:
        path_part, symbol = "", query
    symbol = symbol.strip()
    owner, _, member = symbol.rpartition(".")
    return path_part, bool(sep), owner, member if owner else symbol


def _owns_members(
    graph: nx.Graph, ownership: _Ownership, name: str, node_ids: list[str]
) -> bool:
    return any(ownership.members(node_id) for node_id in _named_ids(graph, name, node_ids))


def _nested_qualifier(graph: nx.Graph, query: str, ownership: _Ownership) -> str | None:
    """`Inner.run` for an `Outer.Inner.run` query that walks two ownership
    levels. Only one owner level is supported, so the caller refuses it
    instead of guessing. An owner whose own label is dotted (`Outer.Inner`,
    owning `.run()`) is one level and is not this case, but only when that
    node really owns a member with the requested name: a heading
    `# Outer.Inner` that owns nothing (or only other sections) does not lift
    the refusal. None when the owner part is not dotted, a segment is not an
    identifier (a Markdown heading such as `Changelog.0.28.1 (6th December,
    2024)`), the owner part as a whole owns the member, or its first segment
    names nothing that owns members."""
    _, _, owner, member = _split_qualified(query)
    if "." not in owner:
        return None
    segments = [*owner.split("."), member.removesuffix("()")]
    if not all(segment.isidentifier() for segment in segments):
        return None
    node_ids = [str(node_id) for node_id in graph.nodes]
    member_bare = _bare_name(member)
    if any(
        member_bare in _label_names(str(graph.nodes[member_id].get("label", "")))
        for owner_id in _named_ids(graph, owner, node_ids)
        for member_id in ownership.members(owner_id)
    ):
        return None
    if not _owns_members(graph, ownership, owner.split(".", 1)[0], node_ids):
        return None
    return f"{owner.rsplit('.', 1)[-1]}.{member}"


def _qualified_scope(
    graph: nx.Graph, query: str, root: Path | None, ownership: _Ownership
) -> str | None:
    """How strictly `query` is scoped by its own qualifier.

    "path" for a `::` whose left half is a path (see `_is_path`): only that
    file can answer it. "chain" for an `Outer.Inner.run` chain (see
    `_nested_qualifier`), which is refused. "owner" for a dotted query whose
    owner part names a node that owns members (a dotted owner label such as
    `Outer.Inner` included): the owner's members answer it first, and no
    substring match can. None for everything else, such as a namespace (the
    Ruby label `Billing::Invoice::Line`, queried as `Invoice::Line`) or a
    file name such as `index.ts` next to an unrelated `index()` function.
    """
    path_part, sep, owner, member = _split_qualified(query)
    if sep:
        if path_part and (owner or member) and _is_path(graph, path_part, root):
            return "path"
        return None
    if not owner:
        return None
    if _nested_qualifier(graph, query, ownership):
        return "chain"
    node_ids = [str(node_id) for node_id in graph.nodes]
    if _owns_members(graph, ownership, owner, node_ids):
        return "owner"
    return None


def _qualified_matches(
    graph: nx.Graph, query: str, root: Path | None, ownership: _Ownership
) -> list[str]:
    """Nodes named by `Class.member`, `path::symbol` or `path::Class.member`.

    `path` restricts the named node itself (see `_path_files`). `Class`
    must own the member through a `method`/`contains` edge (the same
    ownership `affected_nodes` seeds from, #1669), so two same-named methods
    are told apart by their real owner and never by label text alone. Only
    owners of a member that has the requested name, in the requested file,
    are eligible: an unrelated `class Handle` elsewhere must not outrank the
    `handle()` that owns `send()` in `pkg.py`. Inherited members are not
    followed: name the defining class.

    When several owners carry the name, each keeps its own best-named member
    and all of them are returned, so the caller reports a tie. The member's
    label decoration never ranks one owner over another: a Markdown `# Client`
    heading with a `## send` section must not outrank the class `Client`
    whose method is labeled `.send()`, nor the other way round. Nothing in
    graphify's seed lookups (`explain`, `path`, `query`, `affected`) prefers
    code nodes over document nodes, so neither does this.

    A path that matches several files only after normalization (`my client.py`
    and `My Client.py` for `MY CLIENT.PY`) is a tie between files. The hits
    are returned when they span at least two of those files, so they are
    listed as a tie. Otherwise the result is a miss: the symbol may exist in
    one file only, but which file was meant is still not known.
    """
    path_part, sep, owner, member = _split_qualified(query)
    if sep and not (path_part and (owner or member)):
        return []
    if not sep and not owner:
        return []
    files = _path_files(graph, path_part, root) if sep else {}
    candidates = (
        [node_id for nodes in files.values() for node_id in nodes] if sep
        else [str(node_id) for node_id in graph.nodes]
    )
    named = _named_ids(graph, member, candidates)
    if owner:
        # Group the named members by owner once: one owner lookup per member,
        # however many owners share the name.
        by_owner: dict[str, list[str]] = {}
        for node_id in named:
            for owner_id in ownership.owners(node_id):
                by_owner.setdefault(owner_id, []).append(node_id)
        picked: set[str] = set()
        for owner_id in _label_matches(graph, owner, sorted(by_owner)):
            picked.update(_label_matches(graph, member, by_owner[owner_id]))
        hits = [node_id for node_id in named if node_id in picked]
    else:
        hits = _label_matches(graph, member, named)
    if len(files) > 1:
        spanned = {str(graph.nodes[node_id].get("source_file") or "") for node_id in hits}
        if len(spanned) < 2:
            return []
    return hits


def _name_tiers(graph: nx.Graph, query: str, root: Path | None) -> Iterator[list[str]]:
    """Candidate lists for `query` by exact label, bare name and source path,
    most specific first (computed lazily)."""
    query_lower = _normalize_label(query)
    yield [
        str(node_id)
        for node_id, data in graph.nodes(data=True)
        if _normalize_label(str(data.get("label", ""))) == query_lower
    ]
    # Callable labels are decorated ("name()", ".method()"), so a bare "name"
    # query falls through exact matching and then ties with any "name*" sibling
    # in the contains pass. Match on the undecorated name before giving up.
    yield _bare_name_matches(graph, query)
    # Compare paths in repo-relative form. Only this tier is path-shaped; the
    # label tiers above keep the query verbatim.
    query_path = _normalize_label(_as_repo_relative(query, root))
    exact_source_matches = [
        str(node_id)
        for node_id, data in graph.nodes(data=True)
        if _normalize_label(str(data.get("source_file", ""))) in (query_lower, query_path)
    ]
    if len(exact_source_matches) > 1:
        preferred_file_node = _prefer_file_node(
            graph, exact_source_matches, _as_repo_relative(query, root)
        )
        if preferred_file_node is not None:
            exact_source_matches = [preferred_file_node]
    yield exact_source_matches


def resolve_seed_candidates(
    graph: nx.Graph, query: str, root: Path | None = None
) -> list[str]:
    """Nodes `query` names: one id when it resolves, several when it is
    ambiguous, none when nothing matches. Never picks among ties.

    Tiers run most specific first, and the first with exactly one candidate
    wins. In every tier a source-backed definition outranks a sourceless
    stub. An exact node id comes first. A qualified query (see
    `_qualified_scope`) is then answered from the scope it names, before any
    unrestricted label match, so a Markdown heading `# Client.send` cannot
    stand in for the method. A `path::` query and a refused `Outer.Inner.run`
    chain stop there: a heading `# missing.py::Client.send` or
    `# Outer.Inner.run` must not answer them. A `Class.member` query whose
    class has no such member may still be answered by the label, bare-name
    and source-path tiers (a file named `CHANGELOG.md` next to a `Changelog`
    heading), but never by a substring. Only an unqualified query that no
    tier matched at all reaches the substring tier: a substring is weaker
    evidence than names that tied.
    """
    # A trailing path separator must not change a source-file match — serve's
    # _find_node tokenizes the path (which drops it), so strip it here for parity
    # (otherwise `affected "src/x.ts/"` returned None while `explain` resolved it).
    query = query.rstrip("/\\") or query
    ownership = _Ownership(graph)
    ambiguous: list[str] = []
    if query in graph:
        hits = _prefer_source_backed(graph, [query], query)
        if len(hits) == 1:
            return hits
        ambiguous = hits
    scope = _qualified_scope(graph, query, root, ownership)
    if scope:
        hits = _prefer_source_backed(graph, _qualified_matches(graph, query, root, ownership), query)
        if hits or scope != "owner":
            return hits if len(hits) == 1 else ambiguous or hits
    for hits in _name_tiers(graph, query, root):
        hits = _prefer_source_backed(graph, hits, query)
        if len(hits) == 1:
            return hits
        ambiguous = ambiguous or hits
    if ambiguous or scope:
        return ambiguous
    query_lower = _normalize_label(query)
    contains_matches = [
        str(node_id)
        for node_id, data in graph.nodes(data=True)
        if query_lower in _normalize_label(str(data.get("label", "")))
    ]
    return _source_backed(graph, contains_matches) or contains_matches


def resolve_seed(graph: nx.Graph, query: str, root: Path | None = None) -> str | None:
    """The one node `query` names, or None when it names none or several."""
    candidates = resolve_seed_candidates(graph, query, root)
    return candidates[0] if len(candidates) == 1 else None


def _ambiguous_seed_message(graph: nx.Graph, query: str, candidates: list[str]) -> str:
    lines = [f"Ambiguous seed {query}: {len(candidates)} nodes match."]
    for node_id in candidates[:_MAX_LISTED_CANDIDATES]:
        lines.append(
            f"- {_node_label(graph, node_id)} {_format_location(graph.nodes[node_id])}"
            f" (id: {node_id})"
        )
    if len(candidates) > _MAX_LISTED_CANDIDATES:
        lines.append(f"... and {len(candidates) - _MAX_LISTED_CANDIDATES} more")
    lines.append("Pass one of the ids above, or narrow the seed as Class.method or path::symbol.")
    return "\n".join(lines)


def affected_nodes(
    graph: nx.Graph,
    seed: str,
    *,
    relations: Iterable[str] = DEFAULT_AFFECTED_RELATIONS,
    depth: int = 2,
) -> list[AffectedHit]:
    relation_set = set(relations)
    seen = {seed}
    queue: deque[tuple[str, int]] = deque([(seed, 0)])
    hits: list[AffectedHit] = []

    # #1669: seed the reverse walk with the root's own member nodes (one outward
    # `method`/`contains` hop). A caller can bind to a class's method node rather
    # than the class node itself (e.g. `Service.call` resolves to the `def
    # self.call` node, #1634), so those callers are unreachable from the class
    # otherwise. The member nodes are seeds only (not reported as hits), and
    # `method`/`contains` stay out of the general relation-filtered walk, so this
    # adds no forward noise anywhere else.
    if hasattr(graph, "out_edges"):
        member_edges = graph.out_edges(seed, data=True)
    else:
        member_edges = (
            (s, t, d) for s, t, d in graph.edges(data=True) if s == seed
        )
    for _s, member, data in member_edges:
        if str(data.get("relation", "")) not in ("method", "contains"):
            continue
        member = str(member)
        if member not in seen:
            seen.add(member)
            queue.append((member, 0))

    while queue:
        current, current_depth = queue.popleft()
        if current_depth >= depth:
            continue
        if hasattr(graph, "in_edges"):
            incoming = graph.in_edges(current, data=True)
        else:
            incoming = (
                (source, target, data)
                for source, target, data in graph.edges(data=True)
                if target == current
            )
        for source, _target, data in incoming:
            relation = str(data.get("relation", ""))
            if relation not in relation_set:
                continue
            source = str(source)
            if source in seen:
                continue
            seen.add(source)
            # Carry the matched edge's location (taken from the SAME edge dict
            # whose relation passed the filter, so relation and location stay
            # consistent) — that is the call/import/reference site in `source`'s
            # own file, which is where the user should click (#BUG1).
            hit = AffectedHit(
                source, current_depth + 1, relation,
                via_file=str(data.get("source_file") or "") or None,
                via_location=str(data.get("source_location") or "") or None,
            )
            hits.append(hit)
            queue.append((source, current_depth + 1))

    return hits


def format_affected(
    graph: nx.Graph,
    query: str,
    *,
    relations: Iterable[str] = DEFAULT_AFFECTED_RELATIONS,
    depth: int = 2,
    root: Path | None = None,
) -> str:
    """Report what a change to `query` affects.

    Raises SeedResolutionError when `query` names no node or several: printing
    that as a normal report let a typo or a tie read as "nothing depends on
    this".
    """
    relation_list = tuple(relations)
    candidates = resolve_seed_candidates(graph, query, root)
    if not candidates:
        message = f"No unique node match for {query}"
        nested = _nested_qualifier(graph, query, _Ownership(graph))
        if nested:
            message += (
                f"\nOnly one owner level is supported (Class.method). "
                f"Try {nested}, path::{nested}, or a node id."
            )
        path_part, sep, _, _ = _split_qualified(query)
        files = sorted(_path_files(graph, path_part, root)) if sep and path_part else []
        if len(files) > 1:
            message += (
                f"\nThe path matches {len(files)} files: "
                + ", ".join(repr(name) for name in files)
                + ". Spell one exactly."
            )
        raise SeedResolutionError(message)
    if len(candidates) > 1:
        raise SeedResolutionError(_ambiguous_seed_message(graph, query, candidates))
    seed = candidates[0]

    hits = affected_nodes(graph, seed, relations=relation_list, depth=depth)
    lines = [
        f"Affected nodes for {_node_label(graph, seed)}",
        f"Relations: {', '.join(relation_list)}",
        f"Depth: {depth}",
    ]
    if not hits:
        lines.append("No affected nodes found.")
        return "\n".join(lines)

    for hit in hits:
        data = graph.nodes[hit.node_id]
        if hit.via_location:
            # The relation SITE in this node's file (call/import/reference line),
            # labeled by [via_relation] so it's never mistaken for a def line.
            location = f"{hit.via_file or data.get('source_file') or '-'}:{hit.via_location}"
        else:
            location = _format_location(data)  # honest fallback: the node's own def line
        lines.append(
            f"- {_node_label(graph, hit.node_id)} [{hit.via_relation}] {location}"
        )
    return "\n".join(lines)


def load_graph(path: Path) -> nx.Graph:
    import json
    from networkx.readwrite import json_graph

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(
            f"Cannot read graph file {path}: {exc}. "
            "Re-run 'graphify extract' to regenerate it."
        ) from exc
    # Force directed so stored caller→callee direction survives the round-trip;
    # mirrors serve.py and __main__.py (#1174).
    raw = {**raw, "directed": True}
    # Normalize the edge key: graphify's `extract` output uses "edges" while
    # networkx's node_link_data default is "links". Without this, an edges-keyed
    # graph.json raises an uncaught KeyError: 'links' here — every other loader
    # (__main__.py) already normalizes this (#738; same class as #1198).
    if "links" not in raw and "edges" in raw:
        raw = dict(raw, links=raw["edges"])
    try:
        return json_graph.node_link_graph(raw, edges="links")
    except TypeError:
        return json_graph.node_link_graph(raw)
