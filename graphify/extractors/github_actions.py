"""GitHub Actions workflow extractor.

Scoped to GitHub Actions workflow YAML only (job nodes, ``needs``/``uses``
edges). Adapted from the tree-sitter-yaml traversal helpers and
workflow-shape extraction logic in Graphify-Labs/graphify PR #2541
(unmerged as of this writing), with attribution rather than a blind copy.
That PR also models Docker Compose services under the same extractor; the
Compose branch is deliberately not ported here -- this fork's need is
GitHub Actions specifically, and folding in a second, unrelated shape would
widen the surface this file has to stay correct for with no requirement to
justify it, plus that PR keeps YAML entirely in DOC_EXTENSIONS (registering
an extractor alone doesn't touch classification), so it never actually
solves running under ``graphify extract --code-only`` -- the reason this
file exists is to combine the extractor with a ``detect.classify_file``
carve-out (see ``is_github_actions_workflow_path`` below and its use in
``graphify/detect.py``) that makes recognized workflow YAML a code-equivalent
input, not just add a semantic-pass extractor.
"""
from __future__ import annotations

import re
from pathlib import Path

from graphify.extractors.base import _file_stem, _make_id

_JOBS_KEY_RE = re.compile(rb"(?m)^jobs\s*:")


def is_github_actions_workflow_path(path: Path) -> bool:
    """True if `path` sits directly inside a `.github/workflows/` directory
    with a .yml/.yaml extension.

    This is GitHub's own rule for what it treats as a workflow definition,
    valid or not (workflow files must live directly in `.github/workflows/`,
    not nested deeper) -- so it is a precise signal usable at classify_file()
    time. See `looks_like_workflow_shape` for the accompanying content check
    -- path alone is not enough (a non-workflow file can sit at this path
    too, e.g. a stray Docker Compose file).
    """
    if path.suffix.lower() not in (".yml", ".yaml"):
        return False
    return path.parent.name == "workflows" and path.parent.parent.name == ".github"


def looks_like_workflow_shape(path: Path) -> bool:
    """Cheap, tree-sitter-free content sniff: does the file have a top-level
    `jobs:` key?

    Used by classify_file() alongside `is_github_actions_workflow_path` so a
    file that merely *sits* in `.github/workflows/` but isn't actually
    workflow-shaped (a stray Docker Compose file, a schema doc, ...) falls
    through to DOCUMENT instead of being routed to CODE, extracted as empty
    by `extract_github_actions`, and then never reaching the semantic pass
    at all -- a real content-loss bug (the original design deferred all
    content validation to the extractor, which only prevents a *misclassified*
    file from producing garbage nodes, not from being misclassified in the
    first place). Deliberately a plain regex
    over a bounded byte prefix rather than a full tree-sitter parse: unlike
    `extract_github_actions`, classify_file() must keep working without the
    optional `[yaml]` extra installed, and this only needs to answer "is
    this even shaped like a workflow", not build real nodes/edges from it.
    """
    try:
        with path.open("rb") as fh:
            head = fh.read(65536)
    except OSError:
        return False
    return _JOBS_KEY_RE.search(head) is not None


# Step/job keys that carry a reference to another action or reusable workflow
# rather than a shell command.
_USES_KEYS = frozenset({"uses"})

_MAPPING_TYPES = frozenset({"block_mapping", "flow_mapping"})
_SEQUENCE_TYPES = frozenset({"block_sequence", "flow_sequence"})


def _descend(node, wanted: frozenset[str]):
    """Return the first descendant of *node* whose type is in *wanted*.

    YAML wraps every value in `block_node`/`flow_node` before the actual
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


def _mapping(node):
    return _descend(node, _MAPPING_TYPES)


def _scalar_text(node) -> str:
    """Text of the scalar at *node*, with one layer of quotes stripped."""
    if node is None:
        return ""
    text = node.text.decode("utf-8", errors="replace").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        text = text[1:-1]
    return text.strip()


def _pairs(node):
    """Yield `(key, value_node, line)` for each pair of the mapping at *node*.

    *node* may be the mapping itself or any wrapper around it. Pairs whose key
    is not a plain scalar (rare -- a complex mapping key) are skipped rather
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
    """The value inside a `block_sequence_item`, without the `- ` marker.

    `item.text` spans the marker too, so reading it directly yields `"- api"`
    where the real value is `api`.
    """
    if item.type != "block_sequence_item":
        return item
    for child in item.children:
        if child.is_named:
            return child
    return item


def _string_items(node) -> list[tuple[str, int]]:
    """Scalars reachable from *node* as `(text, line)`.

    Handles the shapes a `needs`/`uses` value takes: a bare scalar
    (`needs: lint`), a sequence (`needs: [lint, test]` or the block-list
    form), or (defensively) a mapping's keys.
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


def _is_workflow(path: Path, top) -> bool:
    """True if *top* (the file's top-level mapping) looks like a GitHub
    Actions workflow: a `jobs:` mapping, plus either an `on:` key or the file
    living in `.github/workflows/`. `jobs:` alone is too generic a key to
    trust on its own (other tools use it too); requiring `on:` in addition
    handles a file recognized purely by content, while the path check covers
    a file scanned mid-edit that's momentarily missing `on:` but is
    unambiguously a workflow by where it lives."""
    if top is None:
        return False
    keys = {key for key, _value, _line in _pairs(top)}
    return "jobs" in keys and ("on" in keys or is_github_actions_workflow_path(path))


def extract_github_actions(path: Path) -> dict:
    """Extract job nodes and `needs`/`uses` edges from a GitHub Actions
    workflow YAML file via tree-sitter.

    Nodes: one per job, plus sourceless stub nodes for the actions/reusable
    workflows referenced via `uses`. Edges: `contains` (file -> job),
    `depends_on` (`needs`, scalar or list form), `uses` (job-level or
    step-level, to an action/reusable workflow).

    Job definitions are file-scoped (`_make_id(stem, name)`) with a
    `contains` edge from the file node. `uses` targets are sourceless stubs
    (`_make_id(name)`, no `contains`) marked `type=module` -- the same
    module-anchor exemption tree-sitter extractors elsewhere use (#1327) --
    so `actions/checkout@v4` pinned by ten workflows collapses into one hub
    node under `_disambiguate_colliding_node_ids` instead of scattering into
    ten path-salted duplicates.

    Any YAML that doesn't look like a workflow (`_is_workflow` returns
    False -- Helm values, k8s manifests, OpenAPI specs, or an unrelated file
    that happens to sit in `.github/workflows/`) returns an empty result and
    is left to the semantic pass, mirroring how `_is_config_json` leaves data
    JSON alone (#1224).
    """
    _YAML_MAX_BYTES = 1_048_576  # 1 MiB -- workflow files are small; this rejects junk

    try:
        import tree_sitter_yaml as tsyaml
        from tree_sitter import Language, Parser
    except ImportError as e:
        import importlib.util
        # An installed-but-broken grammar (e.g. a C extension built for a
        # different Python ABI, #2602) raises ImportError here too, same as
        # extractors/sql.py's identical distinction. Reporting that as "not
        # installed" sends the user to a no-op `pip install`, so check
        # whether the module actually resolves before deciding which error
        # to surface.
        if importlib.util.find_spec("tree_sitter_yaml") is None:
            return {"nodes": [], "edges": [], "error": "tree_sitter_yaml not installed. Run: pip install tree-sitter-yaml"}
        return {"nodes": [], "edges": [], "error": f"tree_sitter_yaml is installed but failed to load: {e}"}

    try:
        language = Language(tsyaml.language())
        parser = Parser(language)
    except Exception as e:
        # Same "installed but broken" case as the ImportError branch above,
        # just raised one call later (e.g. a tree-sitter ABI version
        # mismatch surfaces here, not at import time) -- keep the same
        # marker so extract.py's #1745 dependency warning classifies it
        # correctly instead of treating it as some other extraction error.
        return {"nodes": [], "edges": [], "error": f"tree_sitter_yaml is installed but failed to load: {e}"}

    try:
        with path.open("rb") as fh:
            source = fh.read(_YAML_MAX_BYTES + 1)
        if len(source) > _YAML_MAX_BYTES:
            return {"nodes": [], "edges": [], "error": "yaml file too large to index"}
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    top = _top_level(root)
    if not _is_workflow(path, top):
        return {"nodes": [], "edges": []}

    str_path = str(path)
    stem = _file_stem(path)
    file_nid = _make_id(str_path)

    nodes: list[dict] = [{"id": file_nid, "label": path.name, "file_type": "code",
                          "source_file": str_path, "source_location": None}]
    edges: list[dict] = []
    seen_ids: set[str] = {file_nid}
    seen_edges: set[tuple[str, str, str]] = set()
    # name -> nid for the jobs defined in THIS file, so a local `needs`
    # reference binds to the real node instead of minting a stub next to it.
    local_nids: dict[str, str] = {}

    def _add_job(name: str, line: int) -> str:
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

    def _ref_stub(name: str) -> str:
        nid = _make_id(name)
        if nid not in seen_ids:
            seen_ids.add(nid)
            # `actions/checkout@v4` referenced by ten workflows is ONE action,
            # not ten same-named symbols -- the module-anchor case
            # _disambiguate_colliding_node_ids is explicitly exempt from
            # (#1327). Without the exemption each workflow's stub gets salted
            # with its own path and the shared action scatters into N nodes
            # instead of becoming the hub that makes "who uses this action"
            # answerable.
            nodes.append({"id": nid, "label": name, "file_type": "code",
                          "source_file": "", "source_location": "",
                          "origin_file": str_path, "type": "module"})
        return nid

    def _add_edge(src: str, name: str, relation: str, line: int) -> None:
        tgt = local_nids.get(name) or _ref_stub(name)
        if src == tgt:
            return
        key = (src, tgt, relation)
        if key in seen_edges:
            return
        seen_edges.add(key)
        edges.append({"source": src, "target": tgt, "relation": relation,
                      "confidence": "EXTRACTED", "source_file": str_path,
                      "source_location": f"L{line}", "weight": 1.0})

    jobs_entries = [(key, value, line) for key, value, line in _pairs(top) if key == "jobs"]
    if not jobs_entries:
        return {"nodes": nodes, "edges": edges}

    # Pass 1: every job definition first, so a forward reference (a job that
    # `needs` one declared later in the file) binds locally instead of
    # minting a stub that would then compete with the real node.
    members = [(name, body, line) for _k, value, _l in jobs_entries
               for name, body, line in _pairs(value)]
    for name, _body, line in members:
        _add_job(name, line)

    # Pass 2: the references.
    for name, body, _line in members:
        owner = local_nids[name]
        for key, value, line in _pairs(body):
            if key == "needs":
                for dep, dep_line in _string_items(value):
                    _add_edge(owner, dep, "depends_on", dep_line)
            elif key in _USES_KEYS:
                # Job-level `uses:` -- a reusable workflow call.
                target = _scalar_text(value)
                if target:
                    _add_edge(owner, target, "uses", line)
            elif key == "steps":
                for item in _sequence_items(value):
                    for step_key, step_value, step_line in _pairs(item):
                        if step_key in _USES_KEYS:
                            step_target = _scalar_text(step_value)
                            if step_target:
                                _add_edge(owner, step_target, "uses", step_line)

    return {"nodes": nodes, "edges": edges}
