"""YAML structural extractor.

Deterministic, PyYAML-based extraction for ``.yaml``/``.yml`` files so that
config-heavy repositories (Helm charts, Kubernetes manifests, CI pipelines)
contribute nodes to code-only / AST-only runs (``graphify update``) instead of
being skipped entirely (#2214).

Mirrors ``extract_json`` in shape: a file node plus ``contains`` edges to
top-level (and nested) keys, with a pair/depth cap to keep data-heavy YAML from
exploding into orphan nodes. Like ``extract_json``'s ``_is_config_json`` gate,
data-shaped YAML (a top-level data array, an OpenAPI/Swagger spec, a flat
key:value data bundle) is skipped so it does not mint up to 500 orphan nodes
(the #1224/#2255 class of problem).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from graphify.extractors.base import _file_stem, _make_id
from graphify.ids import normalize_id

_YAML_MAX_BYTES = 1_048_576  # 1 MiB
_MAX_PAIRS = 500
_MAX_DEPTH = 6

# Config/manifest filenames worth structural extraction regardless of shape.
_CONFIG_YAML_NAMES = frozenset({
    "values.yaml", "values.yml", "chart.yaml", "chart.yml",
    "docker-compose.yaml", "docker-compose.yml", "compose.yaml", "compose.yml",
    "kustomization.yaml", "kustomization.yml", "skaffold.yaml", "skaffold.yml",
    "serverless.yaml", "serverless.yml", "mkdocs.yaml", "mkdocs.yml",
    ".gitlab-ci.yml", ".gitlab-ci.yaml", ".pre-commit-config.yaml",
    "cloudbuild.yaml", "cloudbuild.yml", "pubspec.yaml", "environment.yml",
    "action.yml", "action.yaml", "catalog-info.yaml", ".travis.yml",
    "appveyor.yml", "azure-pipelines.yml",
})
# Top-level keys that signal a config/manifest (k8s, CI, compose, ansible, helm).
_CONFIG_YAML_KEYS = frozenset({
    "apiversion", "kind", "metadata", "spec",            # k8s
    "services", "volumes", "networks",                    # compose
    "jobs", "steps", "stages", "on", "workflows", "pipeline",  # CI
    "hosts", "tasks", "roles",                            # ansible
    "name", "version", "dependencies", "scripts",         # generic
    "resources", "provider", "functions",                 # serverless
})


def _is_config_yaml(path: Path, data: Any, key_texts: set[str] | None = None) -> bool:
    """True if a YAML document is a recognized config/manifest worth extracting.

    Matches by filename first, then a ``.github/workflows`` path, then a
    top-level key probe. Skips clear data: a plain data array, an OpenAPI/Swagger
    spec, a JSON-Schema-in-YAML, and a flat all-scalar mapping with no config
    key (for example an i18n string bundle). Errs toward extracting (a mapping
    with any nested value is treated as config) so an arbitrarily-named real
    config is not silently dropped.

    ``key_texts`` are the top-level keys as written in the source. PyYAML
    resolves YAML 1.1 booleans, so the constructed key of a workflow's ``on:``
    is ``True``; the written spelling is what the key probe must see.
    """
    name = path.name.casefold()
    if name in _CONFIG_YAML_NAMES:
        return True
    if "/.github/workflows/" in path.as_posix().casefold():
        return True
    if isinstance(data, list):
        # A top-level sequence is config only when it is an ansible-style list of
        # plays/tasks; a plain data array is not.
        return any(
            isinstance(item, dict)
            and ({"hosts", "tasks", "roles"} & {str(k).casefold() for k in item})
            for item in data
        )
    if not isinstance(data, dict):
        return False
    keys = key_texts if key_texts is not None else {str(k).casefold() for k in data.keys()}
    if ("openapi" in keys or "swagger" in keys) and "paths" in keys:
        return False  # an API spec is data-heavy, not a config to walk (#2255-style)
    if "$schema" in keys and ({"$defs", "definitions", "$id"} & keys):
        return False  # a JSON schema in YAML clothing
    if keys & _CONFIG_YAML_KEYS:
        return True
    # A mapping with at least one nested value is config-like; a flat all-scalar
    # mapping with no config key is treated as a data bundle and skipped.
    return any(isinstance(v, (dict, list)) for v in data.values())


def _doc_label(doc: Any, index: int) -> str:
    """A stable label for one document of a multi-document YAML stream."""
    if isinstance(doc, dict):
        kind = doc.get("kind")
        if isinstance(kind, str) and kind:
            meta = doc.get("metadata")
            nm = meta.get("name") if isinstance(meta, dict) else None
            return f"{kind} {nm}" if isinstance(nm, str) and nm else kind
    return f"doc {index}"


_MERGE_TAG = "tag:yaml.org,2002:merge"


def _mapping_pairs(node: Any) -> list[tuple[str, Any, Any]]:
    """(key text, key node, value node) for a composed mapping, in the order the
    constructed dict would hold them.

    Keys come back as written (``on``, not the YAML 1.1 boolean ``True``) and
    carry their own line. A ``<<`` merge contributes its mapping's pairs first,
    and a repeated key keeps its first position but takes the last value and
    line, mirroring PyYAML's ``flatten_mapping`` plus dict insertion. A non-scalar key
    has no written name to label a node with and is skipped.
    """
    import yaml  # type: ignore

    merged: list[tuple[str, Any, Any]] = []
    explicit: list[tuple[str, Any, Any]] = []
    for key_node, value_node in node.value:
        if key_node.tag == _MERGE_TAG:
            sources = value_node.value if isinstance(value_node, yaml.SequenceNode) else [value_node]
            for src in sources:
                if isinstance(src, yaml.MappingNode):
                    merged.extend(_mapping_pairs(src))
        elif isinstance(key_node, yaml.ScalarNode):
            explicit.append((key_node.value, key_node, value_node))
    pairs: dict[str, tuple[str, Any, Any]] = {}
    for text, key_node, value_node in merged + explicit:
        # Reassigning keeps the dict position; the later key node (an explicit
        # override of a merged key) is the one whose line holds the value.
        pairs[text] = (text, key_node, value_node)
    return list(pairs.values())


def extract_yaml(path: Path) -> dict:
    """Extract structural nodes/edges from a ``.yaml``/``.yml`` file.

    Uses PyYAML ``safe_load_all`` (never ``load``; a ``!!python/...`` tag raises
    rather than executing) and walks every document in a multi-document stream.
    Returns an error payload when PyYAML is missing so callers degrade
    gracefully instead of crashing.
    """
    try:
        import yaml  # type: ignore
    except ImportError:
        return {"nodes": [], "edges": [],
                "error": "pyyaml not installed; install with `pip install pyyaml`"}

    try:
        with path.open("rb") as _f:
            raw = _f.read(_YAML_MAX_BYTES + 1)
        if len(raw) > _YAML_MAX_BYTES:
            return {"nodes": [], "edges": [], "error": "yaml file too large to index"}
        text = raw.decode("utf-8", errors="ignore")
        docs = list(yaml.safe_load_all(text))
        # The constructed values drive the config gate and document labels; the
        # composed node tree (same documents, same order, nothing constructed)
        # supplies keys as written and their lines, which construction discards.
        trees = list(yaml.compose_all(text, Loader=yaml.SafeLoader))
    except Exception as exc:  # noqa: BLE001 - surface any parse failure to caller
        return {"nodes": [], "edges": [], "error": str(exc)}

    structured = [(d, n) for d, n in zip(docs, trees) if isinstance(d, (dict, list))]
    if not structured:
        return {"nodes": [], "edges": [], "skipped": "scalar yaml"}

    def _top_keys(tree: Any) -> set[str] | None:
        if isinstance(tree, yaml.MappingNode):
            return {text.casefold() for text, _k, _v in _mapping_pairs(tree)}
        return None

    config_docs = [(d, n) for d, n in structured if _is_config_yaml(path, d, _top_keys(n))]
    if not config_docs:
        return {"nodes": [], "edges": [], "skipped": "data yaml (not a config/manifest)"}

    stem = _file_stem(path)
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()

    def add_node(nid: str, label: str, line: int = 1, file_type: str = "code") -> None:
        if nid and nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append(
                {"id": nid, "label": str(label), "file_type": file_type,
                 "source_file": str_path, "source_location": f"L{line}"}
            )

    def add_edge(src: str, tgt: str, relation: str, line: int = 1,
                 context: str | None = None) -> None:
        if not src or not tgt or src == tgt:
            return
        edge = {"source": src, "target": tgt, "relation": relation,
                "confidence": "EXTRACTED", "source_file": str_path,
                "source_location": f"L{line}", "weight": 1.0}
        if context:
            edge["context"] = context
        edges.append(edge)

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)

    pair_count = [0]

    def walk(node: Any, parent_nid: str, parent_key: str | None, depth: int) -> None:
        if depth > _MAX_DEPTH:
            return
        if isinstance(node, yaml.MappingNode):
            for key_str, key_node, val in _mapping_pairs(node):
                if pair_count[0] >= _MAX_PAIRS:
                    return
                pair_count[0] += 1
                if not normalize_id(key_str):
                    continue
                key_nid = _make_id(stem, *(([parent_key] if parent_key else []) + [key_str]))
                if not key_nid:
                    continue
                line = key_node.start_mark.line + 1
                add_node(key_nid, key_str, line)
                add_edge(parent_nid, key_nid, "contains", line)
                if isinstance(val, (yaml.MappingNode, yaml.SequenceNode)):
                    walk(val, key_nid, key_str, depth + 1)
        elif isinstance(node, yaml.SequenceNode):
            # Lists of scalars carry no key structure; only recurse into
            # structured items without minting index nodes (avoids explosion).
            for item in node.value:
                if isinstance(item, (yaml.MappingNode, yaml.SequenceNode)):
                    walk(item, parent_nid, parent_key, depth + 1)

    multi = len(config_docs) > 1
    for index, (doc, tree) in enumerate(config_docs):
        if multi:
            # Keep each document of a multi-document stream distinct (a k8s file
            # holding a Deployment and a Service must not merge their metadata).
            label = _doc_label(doc, index)
            doc_nid = _make_id(stem, f"doc{index}", label) or _make_id(stem, f"doc{index}")
            if not doc_nid:
                continue
            doc_line = tree.start_mark.line + 1
            add_node(doc_nid, label, doc_line)
            add_edge(file_nid, doc_nid, "contains", doc_line)
            walk(tree, doc_nid, label, 1)
        else:
            walk(tree, file_nid, None, 0)

    return {"nodes": nodes, "edges": edges}
