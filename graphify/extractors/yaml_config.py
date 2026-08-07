"""Yaml_config extractor. Docker Compose and GitHub Actions workflows."""
from __future__ import annotations


from pathlib import Path
from graphify.extractors.base import _file_stem, _make_id


# Filenames that are Docker Compose files by convention. Matched before the
# top-level key probe below, the same cheap-first order json_config uses.
_COMPOSE_PREFIXES = ("docker-compose", "compose")

# Step keys that carry a reference to another workflow/action rather than a
# shell command. `uses` is the only one today, but keeping the set makes the
# intent explicit at the call site.
_USES_KEYS = frozenset({"uses"})


def _descend(node, wanted: frozenset[str]):
    """Return the first descendant of *node* whose type is in *wanted*.

    YAML wraps every value in ``block_node``/``flow_node`` before the actual
    collection, and a document adds another layer, so callers would otherwise
    repeat the same two-or-three-step unwrap everywhere.
    """
    if node is None:
        return None
    if node.type in wanted:
        return node
    for child in node.children:
        if not child.is_named:
            continue
        if child.type in ("block_node", "flow_node", "document"):
            found = _descend(child, wanted)
            if found is not None:
                return found
        elif child.type in wanted:
            return child
    return None


_MAPPING_TYPES = frozenset({"block_mapping", "flow_mapping"})
_SEQUENCE_TYPES = frozenset({"block_sequence", "flow_sequence"})


def _mapping(node):
    return _descend(node, _MAPPING_TYPES)


def _pairs(node):
    """Yield ``(key, value_node, line)`` for each pair of the mapping at *node*.

    *node* may be the mapping itself or any wrapper around it. Pairs whose key
    is not a plain scalar (rare — a complex mapping key) are skipped rather
    than stringified, so they never mint a garbage node.
    """
    mapping = _mapping(node)
    if mapping is None:
        return
    for pair in mapping.children:
        if pair.type not in ("block_mapping_pair", "flow_pair"):
            continue
        key_node = pair.child_by_field_name("key")
        if key_node is None:
            continue
        key = _scalar_text(key_node)
        if not key:
            continue
        yield key, pair.child_by_field_name("value"), key_node.start_point[0] + 1


def _item_value(item):
    """The value inside a ``block_sequence_item``, without the ``- `` marker.

    ``item.text`` spans the marker too, so reading it directly yields ``"- api"``
    where the dependency is ``api``.
    """
    if item.type != "block_sequence_item":
        return item
    for child in item.children:
        if child.is_named:
            return child
    return item


def _scalar_text(node) -> str:
    """Text of the scalar at *node*, with one layer of quotes stripped."""
    if node is None:
        return ""
    text = node.text.decode("utf-8", errors="replace").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        text = text[1:-1]
    return text.strip()


def _string_items(node) -> list[tuple[str, int]]:
    """Scalars reachable from *node* as ``(text, line)``.

    Handles the three shapes a Compose/Actions dependency list takes: a bare
    scalar (``needs: build``), a sequence (``needs: [build, test]``), and a
    mapping whose KEYS are the dependencies (Compose's long-form
    ``depends_on: {db: {condition: ...}}``).
    """
    if node is None:
        return []
    seq = _descend(node, _SEQUENCE_TYPES)
    if seq is not None:
        items = []
        for item in seq.children:
            if item.type not in ("block_sequence_item", "flow_node"):
                continue
            text = _scalar_text(_item_value(item))
            # A sequence item wrapping a mapping is a step, not a name.
            if text and "\n" not in text and ":" not in text:
                items.append((text, item.start_point[0] + 1))
        return items
    mapping = _mapping(node)
    if mapping is not None:
        return [(key, line) for key, _value, line in _pairs(mapping)]
    text = _scalar_text(node)
    return [(text, node.start_point[0] + 1)] if text else []


def _sequence_items(node):
    """Yield the item nodes of the sequence at *node* (for step lists)."""
    seq = _descend(node, _SEQUENCE_TYPES)
    if seq is None:
        return
    for item in seq.children:
        if item.type in ("block_sequence_item", "flow_node"):
            yield item


def _top_level(root):
    """The document's top-level mapping, or None when the file is not a mapping."""
    for doc in root.children:
        if doc.type != "document":
            continue
        mapping = _mapping(doc)
        if mapping is not None:
            return mapping
    return _mapping(root)


def _kind(path: Path, top) -> str | None:
    """Classify a YAML file as ``compose``, ``workflow``, or None.

    None means "data YAML" — an OpenAPI spec, a k8s manifest, a fixture — which
    has no dependency structure this extractor models. Those return an empty
    result and stay with the semantic pass, exactly as _is_config_json leaves
    data JSON to it (#1224).
    """
    if top is None:
        return None
    keys = {key for key, _value, _line in _pairs(top)}
    name = path.name.casefold()
    parts = [p.casefold() for p in path.parts]

    if "jobs" in keys and ("on" in keys or "workflows" in parts):
        return "workflow"
    if "services" in keys:
        if name.startswith(_COMPOSE_PREFIXES) or "version" in keys or "networks" in keys or "volumes" in keys:
            return "compose"
        # A bare `services:` mapping whose values are mappings is still Compose
        # shaped; require the mapping so a `services: [a, b]` list in some
        # unrelated config does not get mistaken for one.
        for key, value, _line in _pairs(top):
            if key == "services" and _mapping(value) is not None:
                return "compose"
    return None


def extract_yaml(path: Path) -> dict:
    """Extract Docker Compose services and GitHub Actions jobs via tree-sitter.

    Nodes: Compose services, Actions jobs, and the actions/reusable workflows a
    job `uses`. Edges: `contains` (file -> service/job), `depends_on` (Compose
    `depends_on`/`extends`, Actions `needs`), and `uses` (job/step -> action).

    Definitions are file-scoped (`_make_id(stem, name)`) and carry a `contains`
    edge. Cross-file references — a `depends_on` naming a service an overlay
    file defines, or an `actions/checkout@v4` shared by every workflow — are
    minted as SOURCELESS stubs (`_make_id(name)`, no `contains`), the same
    pattern the SQL and Go extractors use (#2324, #1402), so
    `_rewire_unique_stub_nodes` can collapse them onto the real definition and
    an unresolved name still survives as a portable node instead of dangling.

    Data YAML (k8s manifests, OpenAPI specs, fixtures) returns an empty result
    and is left to the semantic pass.
    """
    # Lockfiles (pnpm-lock.yaml, conda envs) reach tens of MB and never carry a
    # `services`/`jobs` section, so parsing them is pure cost. Same ceiling and
    # same bounded read as extract_json, which reads one byte past the limit so
    # a file growing between stat and read cannot slip through (#1224).
    _YAML_MAX_BYTES = 1_048_576  # 1 MiB

    try:
        import tree_sitter_yaml as tsyaml
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree_sitter_yaml not installed. Run: pip install tree-sitter-yaml"}

    try:
        with path.open("rb") as fh:
            source = fh.read(_YAML_MAX_BYTES + 1)
        if len(source) > _YAML_MAX_BYTES:
            return {"nodes": [], "edges": [], "error": "yaml file too large to index"}
        language = Language(tsyaml.language())
        parser = Parser(language)
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    top = _top_level(root)
    kind = _kind(path, top)
    if kind is None:
        return {"nodes": [], "edges": []}

    str_path = str(path)
    stem = _file_stem(path)
    file_nid = _make_id(str_path)

    nodes: list[dict] = [{"id": file_nid, "label": path.name, "file_type": "code",
                          "source_file": str_path, "source_location": None}]
    edges: list[dict] = []
    seen_ids: set[str] = {file_nid}
    seen_edges: set[tuple[str, str, str]] = set()
    # name -> nid for the definitions in THIS file, so a local reference binds
    # to the real node instead of minting a stub next to it.
    local_nids: dict[str, str] = {}

    def _add_definition(name: str, line: int) -> str:
        nid = _make_id(stem, name)
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({"id": nid, "label": name, "file_type": "code",
                          "source_file": str_path, "source_location": f"L{line}"})
            edges.append({"source": file_nid, "target": nid, "relation": "contains",
                          "confidence": "EXTRACTED", "source_file": str_path,
                          "source_location": f"L{line}", "weight": 1.0})
        local_nids[name] = nid
        return nid

    def _ref_stub(name: str, *, external: bool = False) -> str:
        nid = _make_id(name)
        if nid not in seen_ids:
            seen_ids.add(nid)
            node = {"id": nid, "label": name, "file_type": "code",
                    "source_file": "", "source_location": "",
                    "origin_file": str_path}
            if external:
                # `actions/checkout@v4` referenced by ten workflows is ONE action,
                # not ten same-named symbols — the module-anchor case
                # _disambiguate_colliding_node_ids is explicitly exempt from
                # (#1327). Without the exemption each workflow's stub gets salted
                # with its own path and the shared action scatters into N nodes
                # instead of becoming the hub that makes "who uses this action"
                # answerable.
                node["type"] = "module"
            nodes.append(node)
        return nid

    def _add_edge(src: str, name: str, relation: str, line: int) -> None:
        tgt = local_nids.get(name) or _ref_stub(name, external=relation == "uses")
        if src == tgt:
            return
        key = (src, tgt, relation)
        if key in seen_edges:
            return
        seen_edges.add(key)
        edges.append({"source": src, "target": tgt, "relation": relation,
                      "confidence": "EXTRACTED", "source_file": str_path,
                      "source_location": f"L{line}", "weight": 1.0})

    section = "services" if kind == "compose" else "jobs"
    entries = [(key, value, line) for key, value, line in _pairs(top) if key == section]
    if not entries:
        return {"nodes": nodes, "edges": edges}

    # Pass 1: every definition first, so a forward reference (a service that
    # depends_on one declared later in the file) binds locally instead of
    # minting a stub that would then compete with the real node.
    members = [(name, body, line) for _k, value, _l in entries
               for name, body, line in _pairs(value)]
    for name, _body, line in members:
        _add_definition(name, line)

    # Pass 2: the references.
    for name, body, _line in members:
        owner = local_nids[name]
        for key, value, line in _pairs(body):
            if key in ("depends_on", "needs"):
                for dep, dep_line in _string_items(value):
                    _add_edge(owner, dep, "depends_on", dep_line)
            elif key == "extends":
                # `extends: {service: base}` — a mapping naming the base
                # service; `extends: base` shorthand is a bare scalar.
                target = ""
                for sub_key, sub_value, _sub_line in _pairs(value):
                    if sub_key == "service":
                        target = _scalar_text(sub_value)
                if not target:
                    target = _scalar_text(value)
                if target:
                    _add_edge(owner, target, "depends_on", line)
            elif key in _USES_KEYS:
                # Job-level `uses:` — a reusable workflow call.
                target = _scalar_text(value)
                if target:
                    _add_edge(owner, target, "uses", line)
            elif key == "steps":
                for item in _sequence_items(value):
                    for step_key, step_value, step_line in _pairs(item):
                        if step_key in _USES_KEYS:
                            target = _scalar_text(step_value)
                            if target:
                                _add_edge(owner, target, "uses", step_line)

    return {"nodes": nodes, "edges": edges}
