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

import os
from pathlib import Path
from typing import Any

from graphify.extractors.base import _file_stem, _make_id, active_scan_root
from graphify.ids import normalize_id

_YAML_MAX_BYTES = 1_048_576  # 1 MiB
_MAX_PAIRS = 500
_GHA_BASH_SHELLS = frozenset({"bash", "sh", "zsh", "ksh", "dash"})
_UNSET = object()

# Built lazily by _permissive_loader() once PyYAML is known to be importable
# (the module stays import-optional, so this cannot be a module-level class).
_permissive_loader_cls: Any = None


def _construct_permissive(loader: Any, tag_suffix: str, node: Any) -> Any:
    """Build a plain value for an unrecognized ``!`` tag (#5071).

    CloudFormation/SAM intrinsic functions (``!Ref``, ``!Sub``, ``!GetAtt``,
    ``!Equals``, ...) are short, local tags SafeLoader has no constructor
    for, so ``safe_load_all`` raised ``ConstructorError`` and the whole file
    produced zero nodes. The intrinsic itself is never evaluated here, only
    the tagged value's own shape: a scalar tag becomes its scalar value, a
    sequence tag its list, and a mapping tag its dict, exactly as if the tag
    were absent.
    """
    import yaml  # type: ignore
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    return None


def _permissive_loader() -> Any:
    """A ``yaml.SafeLoader`` subclass that also accepts any unknown ``!`` tag.

    Adds no safety-relevant behavior over ``SafeLoader``: it only widens which
    tags construct a plain value, never which types a value can construct
    into, so a ``!!python/...`` tag still raises exactly as it does under
    plain ``safe_load_all``.
    """
    global _permissive_loader_cls
    if _permissive_loader_cls is None:
        import yaml  # type: ignore

        class _PermissiveSafeLoader(yaml.SafeLoader):
            pass

        _PermissiveSafeLoader.add_multi_constructor("!", _construct_permissive)
        _permissive_loader_cls = _PermissiveSafeLoader
    return _permissive_loader_cls
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


def _github_workflow_repo_root(path: Path) -> Path | None:
    """Return the repository root when *path* lies under ``.github/workflows/``."""
    parts = [p.casefold() for p in path.parts]
    for idx in range(len(parts) - 3, -1, -1):
        if parts[idx] == ".github" and parts[idx + 1] == "workflows":
            steps_up = len(parts) - idx
            return path.parents[steps_up - 1]
    return None


def _composite_action_repo_root(path: Path) -> Path | None:
    """Return the anchor root when *path* is an ``action.yml`` / ``action.yaml``."""
    if path.name.casefold() not in ("action.yml", "action.yaml"):
        return None
    parts = [p.casefold() for p in path.parts]
    for idx in range(len(parts) - 2, -1, -1):
        if parts[idx] == ".github":
            steps_up = len(parts) - idx
            return path.parents[steps_up - 1]
    return active_scan_root() or path.parent


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
    if _github_workflow_repo_root(path) is not None:
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
            # Per the YAML merge spec, an earlier map in a ``<<: [a, b]`` sequence
            # overrides a later one. Because the dict below is last-write-wins, feed
            # the sources in reverse so the earliest keeps the final value/line —
            # matching PyYAML's ``flatten_mapping`` (which reverses the submerge).
            for src in reversed(sources):
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


def _scalar_str(node: Any) -> str | None:
    """Return the string value of a string ScalarNode, else None."""
    import yaml  # type: ignore

    if isinstance(node, yaml.ScalarNode) and node.tag == "tag:yaml.org,2002:str":
        return node.value
    return None


def _run_defaults(mapping_node: Any) -> tuple[object, object]:
    """Return ``(shell, working_directory)`` from ``defaults.run``, using ``_UNSET`` when absent."""
    import yaml  # type: ignore

    if not isinstance(mapping_node, yaml.MappingNode):
        return _UNSET, _UNSET
    top = {k: v for k, _kn, v in _mapping_pairs(mapping_node)}
    defaults_node = top.get("defaults")
    if not isinstance(defaults_node, yaml.MappingNode):
        return _UNSET, _UNSET
    defaults_map = {k: v for k, _kn, v in _mapping_pairs(defaults_node)}
    run_node = defaults_map.get("run")
    if not isinstance(run_node, yaml.MappingNode):
        return _UNSET, _UNSET
    run_map = {k: v for k, _kn, v in _mapping_pairs(run_node)}
    shell_val = _scalar_str(run_map["shell"]) if "shell" in run_map else _UNSET
    wd_val = _scalar_str(run_map["working-directory"]) if "working-directory" in run_map else _UNSET
    return shell_val, wd_val


def _runs_on_is_windows(node: Any) -> bool:
    """True when ``runs-on`` explicitly selects a Windows runner."""
    import yaml  # type: ignore

    if isinstance(node, yaml.ScalarNode):
        val = _scalar_str(node)
        return bool(val and val.strip().casefold().startswith("windows"))
    if isinstance(node, yaml.SequenceNode):
        for item in node.value:
            val = _scalar_str(item)
            if val and val.strip().casefold().startswith("windows"):
                return True
    return False


def _is_bash_shell(shell_val: object, *, default_is_bash: bool) -> bool:
    """True when *shell_val* selects a bash-compatible shell (or is unset when default is bash)."""
    if shell_val is _UNSET:
        return default_is_bash
    if not isinstance(shell_val, str):
        return False
    cleaned = shell_val.strip()
    if not cleaned or "$" in cleaned or "\0" in cleaned:
        return False
    tokens = cleaned.split()
    if not tokens:
        return False
    exe = Path(tokens[0]).name.casefold()
    if exe == "env" and len(tokens) > 1:
        exe = Path(tokens[1]).name.casefold()
    return exe in _GHA_BASH_SHELLS


def _resolve_run_dir(repo_root: Path, wd_val: object, ceiling: Path) -> Path | None:
    """Safely resolve a workflow step's working directory within *ceiling*."""
    from graphify.extractors.bash import _resolve_safe

    if wd_val is _UNSET:
        resolved = _resolve_safe(repo_root, ceiling)
        return resolved if resolved is not None and resolved.is_dir() else None
    if not isinstance(wd_val, str):
        return None
    wd = wd_val.strip()
    if not wd or wd.startswith(("/", "\\")) or "$" in wd or "\0" in wd:
        return None
    resolved = _resolve_safe(repo_root / wd, ceiling)
    return resolved if resolved is not None and resolved.is_dir() else None


def _extract_workflow_run_edges(
    path: Path,
    tree: Any,
    file_nid: str,
    repo_root: Path,
    *,
    is_composite_action: bool,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Parse qualifying GitHub Actions ``run:`` steps as bash and collect edges."""
    import yaml  # type: ignore
    from graphify.extractors.bash import _safe_to_probe, extract_bash_source

    if not isinstance(tree, yaml.MappingNode):
        return [], [], []

    abs_repo = Path(os.path.abspath(str(repo_root)))
    if not _safe_to_probe(abs_repo, None):
        return [], [], []
    scan_root = active_scan_root()
    if scan_root is not None:
        ceiling = scan_root
    else:
        try:
            ceiling = abs_repo.resolve()
        except OSError:
            return [], [], []
    if not _safe_to_probe(abs_repo, ceiling):
        return [], [], []

    top_map = {k: v for k, _kn, v in _mapping_pairs(tree)}
    wf_shell, wf_wd = _run_defaults(tree)

    step_groups: list[tuple[Any, bool, object, object]] = []
    if is_composite_action:
        runs_node = top_map.get("runs")
        if isinstance(runs_node, yaml.MappingNode):
            runs_map = {k: v for k, _kn, v in _mapping_pairs(runs_node)}
            using_val = _scalar_str(runs_map.get("using"))
            if using_val and using_val.strip().casefold() == "composite":
                steps_node = runs_map.get("steps")
                if isinstance(steps_node, yaml.SequenceNode):
                    step_groups.append((steps_node, False, _UNSET, _UNSET))
    else:
        jobs_node = top_map.get("jobs")
        if isinstance(jobs_node, yaml.MappingNode):
            for _job_name, _job_kn, job_node in _mapping_pairs(jobs_node):
                if not isinstance(job_node, yaml.MappingNode):
                    continue
                job_map = {k: v for k, _kn, v in _mapping_pairs(job_node)}
                steps_node = job_map.get("steps")
                if not isinstance(steps_node, yaml.SequenceNode):
                    continue
                job_shell, job_wd = _run_defaults(job_node)
                eff_default_shell = wf_shell if job_shell is _UNSET else job_shell
                eff_default_wd = wf_wd if job_wd is _UNSET else job_wd
                default_is_bash = not _runs_on_is_windows(job_map.get("runs-on"))
                step_groups.append((steps_node, default_is_bash, eff_default_shell, eff_default_wd))

    collected_edges: list[dict] = []
    collected_raw_calls: list[dict] = []
    collected_sources: list[dict] = []
    seen_edges: set[tuple[str, str, str, str]] = set()
    seen_raw: set[tuple[str, str, str]] = set()

    for steps_node, default_is_bash, group_shell, group_wd in step_groups:
        for step_node in steps_node.value:
            if not isinstance(step_node, yaml.MappingNode):
                continue
            step_map = {k: v for k, _kn, v in _mapping_pairs(step_node)}
            run_node = step_map.get("run")
            run_text = _scalar_str(run_node)
            if not isinstance(run_node, yaml.ScalarNode) or not run_text or not run_text.strip():
                continue
            step_shell = (_scalar_str(step_map["shell"]) if "shell" in step_map else group_shell)
            if not _is_bash_shell(step_shell, default_is_bash=default_is_bash):
                continue
            step_wd = (
                _scalar_str(step_map["working-directory"])
                if "working-directory" in step_map
                else group_wd
            )
            run_dir = _resolve_run_dir(abs_repo, step_wd, ceiling)
            if run_dir is None:
                continue
            line_offset = run_node.start_mark.line + (1 if run_node.style in ("|", ">") else 0)
            bash_res = extract_bash_source(
                run_text.encode("utf-8"),
                source_path=path,
                base_dir=run_dir,
                file_nid=file_nid,
                entry_nid=file_nid,
                scan_root=ceiling,
                line_offset=line_offset,
                include_declarations=False,
                initial_var_bases={"GITHUB_WORKSPACE": abs_repo},
                gha_mode=True,
            )
            if "error" in bash_res:
                continue
            for edge in bash_res.get("edges", []):
                ekey = (
                    str(edge.get("source", "")),
                    str(edge.get("target", "")),
                    str(edge.get("relation", "")),
                    str(edge.get("source_location", "")),
                )
                if ekey not in seen_edges:
                    seen_edges.add(ekey)
                    collected_edges.append(edge)
            for bs in bash_res.get("bash_sources", []):
                collected_sources.append(bs)
            for rc in bash_res.get("raw_calls", []):
                rkey = (
                    str(rc.get("caller_nid", "")),
                    str(rc.get("callee", "")),
                    str(rc.get("source_location", "")),
                )
                if rkey not in seen_raw:
                    seen_raw.add(rkey)
                    collected_raw_calls.append(rc)

    return collected_edges, collected_raw_calls, collected_sources


def extract_yaml(path: Path) -> dict:
    """Extract structural nodes/edges from a ``.yaml``/``.yml`` file.

    Uses a ``SafeLoader`` (never ``load``; a ``!!python/...`` tag raises
    rather than executing), widened to accept any unrecognized ``!`` tag as a
    plain scalar/sequence/mapping (#5071 — CloudFormation/SAM's ``!Ref``,
    ``!Equals``, etc. otherwise raise ``ConstructorError`` and the whole file
    produces zero nodes), and walks every document in a multi-document
    stream. Returns an error payload when PyYAML is missing so callers
    degrade gracefully instead of crashing.
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
        docs = list(yaml.load_all(text, Loader=_permissive_loader()))
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

    workflow_root = _github_workflow_repo_root(path)
    action_root = _composite_action_repo_root(path) if workflow_root is None else None
    bash_sources_all: list[dict] = []
    raw_calls_all: list[dict] = []

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
            gha_root = workflow_root or action_root
            if gha_root is not None:
                step_edges, step_raw_calls, step_sources = _extract_workflow_run_edges(
                    path,
                    tree,
                    file_nid,
                    gha_root,
                    is_composite_action=(workflow_root is None),
                )
                edges.extend(step_edges)
                bash_sources_all.extend(step_sources)
                raw_calls_all.extend(step_raw_calls)

    payload: dict[str, Any] = {"nodes": nodes, "edges": edges}
    if bash_sources_all:
        payload["bash_sources"] = bash_sources_all
        payload["raw_calls"] = raw_calls_all
    return payload
