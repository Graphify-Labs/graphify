"""Cross-file resolver for Django URL route declarations.

``extract._stamp_django_url_routes`` mints raw_calls stamped with the route
facts of a ``urls.py`` file (``route_pattern`` / ``route_target`` /
``route_kind``, keys from :mod:`graphify.http_endpoints`). This pass composes
them across files: an ``include("api.urls")`` prefixes every ``path()`` stamp
in the one corpus file whose path ends ``api/urls.py`` (recursively for nested
includes, depth-capped, cycle-safe), each composed pattern mints-or-joins one
shared ``http_endpoint`` node, and the view the route names — resolved through
the urls.py's own import edges, never a bare same-name guess — gets a
``serves`` edge.

Fail-closed everywhere (house rule: a guessed relation is worse than a missing
one): a ``route_target`` module with zero or several candidate files, an
``include`` whose module string matches zero or several corpus files, a view
name that is absent or ambiguous, and a ``re_path`` regex all mint at most an
endpoint node plus a name-only fact parked on it (``unresolved_view`` /
``unresolved_route``) and NO edge. Only stamps from the current per-file batch
are read, so every emitted edge is sourced by a freshly extracted file (the
incremental contract of the resolver registry).
"""
from __future__ import annotations

import posixpath

from .http_endpoints import (
    HTTP_RELATION_SERVES,
    KEY_ROUTE_KIND,
    KEY_ROUTE_PATTERN,
    KEY_ROUTE_TARGET,
    ROUTE_KIND_INCLUDE,
    ROUTE_KIND_PATH,
    ROUTE_KIND_RE_PATH,
    edge_key_index,
    endpoint_edge,
    find_or_mint_endpoint,
    normalize_pattern,
    park_endpoint_meta,
)

_MAX_INCLUDE_DEPTH = 8


def _posix(source_file: object) -> str:
    return str(source_file or "").replace("\\", "/")


def _member_of(label: object) -> str:
    """`devices()` / `.devices()` -> `devices`; any other label stays itself
    (a label without the call parens is a data/class node, never a view)."""
    text = str(label or "").strip()
    if text.startswith("."):
        text = text[1:]
    if text.endswith("()"):
        text = text[:-2]
    return text


def _is_file_node(node: dict) -> bool:
    """A corpus file node carries the file's basename as label (the shape both
    `_extract_generic` and the id remap leave on it); def/class nodes never do."""
    sf = node.get("source_file")
    if not sf:
        return False
    return str(node.get("label", "")) == posixpath.basename(_posix(sf))


def _module_suffix(module: str) -> str | None:
    """`api.urls` -> `api/urls.py` (dots to posix separators)."""
    parts = [part for part in module.split(".") if part]
    if not parts:
        return None
    return "/".join(parts) + ".py"


def _has_corpus_suffix(sf: str, suffix: str) -> bool:
    """`sf` is the suffix or ends with `<separator><suffix>` — a leading
    segment boundary, so `wapi/urls.py` does NOT match `api/urls.py`."""
    return sf == suffix or sf.endswith("/" + suffix)


def resolve_django_routes(
    per_file: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> None:
    """Compose Django url routes across files, mint endpoint nodes and serve
    edges. Mutates ``all_nodes`` / ``all_edges`` in place; idempotent (the
    duplicate-edge guard makes a second pass over the same batch a no-op)."""
    # Route stamps come only from the fresh per-file batch (urls.py extractions
    # mint them); context nodes contribute candidates, never stamps.
    stamps_by_file: dict[str, list[dict]] = {}
    for result in per_file:
        for rc in result.get("raw_calls") or []:
            kind = rc.get(KEY_ROUTE_KIND)
            if kind not in (ROUTE_KIND_PATH, ROUTE_KIND_RE_PATH, ROUTE_KIND_INCLUDE):
                continue
            if not rc.get("source_file"):
                continue
            if KEY_ROUTE_PATTERN not in rc:
                continue
            stamps_by_file.setdefault(_posix(rc["source_file"]), []).append(rc)
    if not stamps_by_file:
        return

    # Corpus indexes: file nodes (include targets and the urls.py's own anchor),
    # candidate modules per file (import edges carry the file node, a def node
    # for `from .views import devices`, or a foreign module sink id with no node
    # at all), and the function defs each file/module node contains.
    file_node_ids: dict[str, str] = {}
    node_by_id: dict[str, dict] = {}
    for node in all_nodes:
        if isinstance(node, dict) and node.get("id"):
            node_by_id[node["id"]] = node
            sf = _posix(node.get("source_file"))
            if sf and _is_file_node(node) and sf not in file_node_ids:
                file_node_ids[sf] = node["id"]
    import_targets: dict[str, list[str]] = {}
    contained_defs: dict[str, dict[str, list[str]]] = {}
    for edge in all_edges:
        if not isinstance(edge, dict):
            continue
        relation = edge.get("relation")
        if relation in ("imports", "imports_from"):
            import_targets.setdefault(str(edge.get("source")), []).append(str(edge.get("target")))
        elif relation == "contains":
            parent = contained_defs.setdefault(str(edge.get("source")), {})
            child = node_by_id.get(str(edge.get("target")))
            if child is not None:
                parent.setdefault(_member_of(child.get("label")), []).append(child["id"])

    # include composition: every include stamp maps its module literal to
    # EXACTLY ONE corpus file (posix suffix match); zero or >1 candidates fail
    # closed — the children keep composing from nothing above them.
    corpus_files = set(file_node_ids)
    include_into: dict[str, list[tuple[str, str]]] = {}
    for sf, stamps in stamps_by_file.items():
        for rc in stamps:
            if rc.get(KEY_ROUTE_KIND) != ROUTE_KIND_INCLUDE:
                continue
            target = rc.get(KEY_ROUTE_TARGET)
            suffix = _module_suffix(str(target)) if target else None
            if suffix is None:
                continue
            matches = sorted(csf for csf in corpus_files if _has_corpus_suffix(csf, suffix))
            if len(matches) == 1:
                entries = include_into.setdefault(matches[0], [])
                entry = (sf, str(rc.get(KEY_ROUTE_PATTERN) or ""))
                # The same urls.py listed twice in the batch must not read as
                # two conflicting include sites — collapse identical entries.
                if entry not in entries:
                    entries.append(entry)
    prefix_memo: dict[str, "list[str] | None"] = {}

    def _prefix_chain(sf: str, seen: frozenset) -> "list[str] | None":
        """Prefixes above one urls.py file, outermost first; None = ambiguous,
        cyclic or too deep (fail closed: compose from nothing)."""
        if sf in prefix_memo:
            return prefix_memo[sf]
        if sf in seen or len(seen) >= _MAX_INCLUDE_DEPTH:
            return None
        incoming = include_into.get(sf)
        if not incoming:
            return []  # a top-level urls.py (or a parent outside the batch)
        if len(incoming) > 1:
            return None
        parent_sf, pattern = incoming[0]
        parent_chain = _prefix_chain(parent_sf, seen | {sf})
        if parent_chain is None:
            return None
        chain = [*parent_chain, pattern]
        prefix_memo[sf] = chain
        return chain

    existing = edge_key_index(all_edges)
    for sf in sorted(stamps_by_file):
        urls_nid = file_node_ids.get(sf, "")
        for rc in stamps_by_file[sf]:
            kind = rc.get(KEY_ROUTE_KIND)
            if kind == ROUTE_KIND_INCLUDE:
                continue
            pattern = str(rc.get(KEY_ROUTE_PATTERN) or "")
            chain = _prefix_chain(sf, frozenset())
            # Compose outermost-first: every include pattern segment plus the
            # route itself, separator-normalized on both sides of the join —
            # `path("api/", include("api.urls"))` + `"devices"` → `api/devices`.
            composed = "/".join(
                part.strip("/") for part in [*(chain or []), pattern] if part.strip("/")
            )
            normalized, has_placeholder = normalize_pattern(composed)
            endpoint = find_or_mint_endpoint(
                all_nodes,
                normalized=normalized,
                has_placeholder=has_placeholder,
                source_file=sf,
                source_location=rc.get("source_location"),
                origin="backend",
            )
            if kind == ROUTE_KIND_RE_PATH:
                # A regex route normalizes to its literal shape only by luck;
                # park the untrusted raw pattern and never bind a view.
                park_endpoint_meta(endpoint, "unresolved_route", composed)
                continue
            target = rc.get(KEY_ROUTE_TARGET)
            if not target:
                continue  # route with no view written — nothing to bind, park nothing
            view_id = _resolve_view(
                str(target), urls_nid, node_by_id, import_targets, contained_defs,
            )
            if view_id is None:
                park_endpoint_meta(endpoint, "unresolved_view", str(target))
                continue
            key = (endpoint["id"], view_id, HTTP_RELATION_SERVES)
            if key in existing:
                continue
            existing.add(key)
            all_edges.append(endpoint_edge(
                source=endpoint["id"],
                target=view_id,
                relation=HTTP_RELATION_SERVES,
                source_file=sf,
                source_location=rc.get("source_location"),
            ))


def _resolve_view(
    target: str,
    urls_nid: str,
    node_by_id: dict[str, dict],
    import_targets: dict[str, list[str]],
    contained_defs: dict[str, dict[str, list[str]]],
) -> "str | None":
    """The node id of the view a route names, or None (fail closed).

    ``views.devices``: the module token must be imported by the urls.py itself
    (an ``imports``/``imports_from`` edge to a file node spelled ``views.py``
    or a module node spelled ``views``), and exactly one def with the member
    name must live under that module. A bare ``devices`` must be a def the
    urls.py imports (``from .views import devices``) or a corpus-unique visible
    function. Everything else — classes (``DeviceView`` labels carry no call
    parens), missing or duplicated names — resolves to nothing.
    """
    if not urls_nid:
        return None
    candidates: list[str] = []
    if "." in target:
        module_token, member = target.rsplit(".", 1)
        if not module_token or not member:
            return None
        for imported in import_targets.get(urls_nid, []):
            node = node_by_id.get(imported)
            if node is None:
                continue  # a foreign module sink id with no corpus node
            # `views.py` (file node) and `views` (module node) both spell the
            # module token; anything longer (a.b) finds no import edge target.
            if posixpath.splitext(str(node.get("label") or ""))[0] == module_token:
                candidates.extend(contained_defs.get(imported, {}).get(member, []))
    else:
        # A bare name: the urls.py imported that def itself (edge target is the
        # def node), else a unique def by that name anywhere in the corpus.
        for imported in import_targets.get(urls_nid, []):
            node = node_by_id.get(imported)
            if node is not None and _member_of(node.get("label")) == target:
                candidates.append(imported)
        if not candidates:
            for members in contained_defs.values():
                candidates.extend(members.get(target, []))
    unique = sorted(set(candidates))
    return unique[0] if len(unique) == 1 else None
