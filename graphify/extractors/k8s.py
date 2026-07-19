"""Kubernetes / Helm-values / ArgoCD-GitOps YAML extractor.

Covers the manifests that are VALID YAML: plain k8s objects, ArgoCD
Application/ApplicationSet/AppProject, External Secrets, and Helm `values*.yaml`.
Helm *templates* (charts/*/templates/*.yaml) are deliberately out of scope — Go
template directives (`{{- if .Values.x }}`) make them unparseable as YAML, so
they are left to a later pass rather than parsed lossily here.

Known gaps (deliberate, so the graph does not overstate what it knows):

- An ApplicationSet's git generator yields a `generates_from` edge to the glob
  it scans (`gitops/apps/*.yaml`), NOT to the files that glob matches. Resolving
  it would mean globbing the filesystem from inside a single-file extractor,
  which breaks per-file caching and determinism. The glob edge still shows which
  registry each environment reads — the fan-out is one `ls` away.
- Registry-style YAML that carries neither `apiVersion` nor `kind` (an ArgoCD
  fleet entry is often just `app: <name>`) is indistinguishable from arbitrary
  config, so it stays on the document path.
- Objects are addressed `<kind>.<name>` globally, so same-named objects in
  different clusters or namespaces (one `AppProject.platform` per environment)
  collapse into a single node.
"""
from __future__ import annotations

import re
from pathlib import Path

from graphify.extractors.base import _make_id

# A k8s/ArgoCD manifest is identified by content, not by extension: `.yaml` is a
# DOC extension and must STAY one for ordinary YAML (CI configs, front-matter,
# docs data), which belongs on the LLM path. Only files carrying both
# `apiVersion:` and `kind:` at the start of a line are rerouted to the AST path.
# Mirrors manifest_ingest.is_package_manifest_path, which routes package
# manifests (apm.yml, pyproject.toml) to CODE for the same reason (#1377).
_APIVERSION_RE = re.compile(r"^apiVersion:\s*\S", re.MULTILINE)
_KIND_RE = re.compile(r"^kind:\s*\S", re.MULTILINE)

# Only the head of the file is sniffed — detect() calls this for every YAML in
# the corpus, so it must stay cheap. A manifest declares both keys in its first
# document; 8 KiB clears even a heavily commented one.
_SNIFF_BYTES = 8192


def is_k8s_manifest_path(path: Path) -> bool:
    """True if `path` is a YAML file whose content looks like a k8s manifest."""
    if path.suffix.lower() not in (".yaml", ".yml"):
        return False
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            head = fh.read(_SNIFF_BYTES)
    except OSError:
        return False
    return bool(_APIVERSION_RE.search(head) and _KIND_RE.search(head))

# Injected into every mapping by _LineLoader so nodes get a real source_location.
# Skipped during the walk so it never looks like a reference field.
_LINE_KEY = "__graphify_line__"

# Scalar-valued reference fields: `key: <name>` -> an object of a fixed kind.
# Bare `name:` is deliberately absent — it identifies the enclosing object
# rather than referencing another one, and treating it as a ref would make
# every manifest point at itself.
_SCALAR_REFS: dict[str, tuple[str, str]] = {
    "project": ("AppProject", "references"),
    "serviceAccountName": ("ServiceAccount", "references"),
    "secretName": ("Secret", "references"),
    "claimName": ("PersistentVolumeClaim", "references"),
    "ingressClassName": ("IngressClass", "references"),
    "storageClassName": ("StorageClass", "references"),
    "priorityClassName": ("PriorityClass", "references"),
}

# Mapping-valued reference fields: `key: {name: <n>}`, optionally carrying its
# own `kind:` (secretStoreRef/storeRef pick ClusterSecretStore vs SecretStore
# that way). A None default means "read the kind from the mapping itself".
_MAPPING_REFS: dict[str, tuple[str | None, str]] = {
    "secretRef": ("Secret", "references"),
    "secretKeyRef": ("Secret", "references"),
    "configMapRef": ("ConfigMap", "references"),
    "configMapKeyRef": ("ConfigMap", "references"),
    "serviceAccountRef": ("ServiceAccount", "references"),
    "secretStoreRef": (None, "references"),
    "storeRef": (None, "references"),
}

def _line_loader():
    """SafeLoader that records each mapping's 1-based start line.

    PyYAML drops position information during construction, so without this every
    node would have to share the file's L1. Constructed lazily because pyyaml is
    an optional extra.
    """
    import yaml

    class _LineLoader(yaml.SafeLoader):
        pass

    def _construct_mapping(loader, node, deep=False):
        mapping = yaml.SafeLoader.construct_mapping(loader, node, deep=deep)
        mapping[_LINE_KEY] = node.start_mark.line + 1
        return mapping

    _LineLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
    )
    return _LineLoader


def extract_k8s(path: Path) -> dict:
    """Extract Kubernetes/ArgoCD objects and the references between them.

    Nodes: one per YAML document carrying `apiVersion` + `kind`, addressed
    `<kind>.<metadata.name>` (e.g. `Application.web-api-dev`), plus the
    file itself and referenced-but-undeclared objects (a `project: platform` in one
    file resolves to the `AppProject.platform` declared in another).

    Edges: `contains` (file -> object), `references` (the _SCALAR_REFS /
    _MAPPING_REFS table), `in_namespace`, `deploys_to` (Application ->
    destination namespace), `deploys_chart` (Application -> spec.source.path),
    `generates_from` (ApplicationSet -> its git generator's files/directories
    globs) and `produces` (ExternalSecret -> the Secret it materializes).

    Node IDs are scoped GLOBALLY by `<kind>.<name>`, not per-file or per-
    directory, because that is how Kubernetes itself resolves a reference: an
    ApplicationSet's `project: platform` means the AppProject named `platform`,
    wherever it is declared. Global scoping is what lets those cross-file edges
    survive the per-file extraction merge. Known limitation: same-named objects
    in different clusters or namespaces (three `AppProject.platform` files, one
    per env) collapse into one node.

    Helm templates are NOT handled — see the module docstring.
    """
    try:
        import yaml
    except ImportError:
        return {"nodes": [], "edges": [], "error": "pyyaml not installed. Run: pip install 'graphifyy[k8s]'"}

    try:
        loader = _line_loader()
        source = path.read_text(encoding="utf-8", errors="replace")
        docs = list(yaml.load_all(source, Loader=loader))
    except Exception as e:
        # Helm templates and other non-YAML land here; an unparseable file
        # yields nothing rather than aborting the whole extraction run.
        return {"nodes": [], "edges": [], "error": str(e)}

    str_path = str(path)
    file_nid = _make_id(str_path)

    nodes: list[dict] = [{"id": file_nid, "label": path.name, "file_type": "code",
                          "source_file": str_path, "source_location": None}]
    edges: list[dict] = []
    seen_ids: set[str] = {file_nid}
    seen_edges: set[tuple[str, str, str]] = set()

    def _addr_id(address: str) -> str:
        return _make_id("k8s", address)

    def _add_node(address: str, line: int, *, declared: bool) -> str:
        """Add (or reuse) a node for `address`. `declared` marks a real
        definition in this file, which also earns a `contains` edge from it;
        a reference-only target gets a node so the edge has somewhere to land,
        and the file that declares it will fill in the location on merge."""
        nid = _addr_id(address)
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({"id": nid, "label": address, "file_type": "code",
                          "source_file": str_path if declared else "",
                          "source_location": f"L{line}" if declared else None})
        if declared:
            _add_edge(file_nid, address, "contains", line)
        return nid

    def _add_edge(src: str, address: str, relation: str, line: int) -> None:
        tgt = _addr_id(address)
        if src == tgt:
            return
        key = (src, tgt, relation)
        if key in seen_edges:
            return
        seen_edges.add(key)
        edges.append({"source": src, "target": tgt, "relation": relation,
                      "confidence": "EXTRACTED", "source_file": str_path,
                      "source_location": f"L{line}", "weight": 1.0})

    def _ref(owner: str, kind: str, name, relation: str, line: int) -> None:
        if not isinstance(name, str) or not name.strip():
            return
        address = f"{kind}.{name.strip()}"
        _add_node(address, line, declared=False)
        _add_edge(owner, address, relation, line)

    def _line_of(mapping, fallback: int) -> int:
        if isinstance(mapping, dict):
            got = mapping.get(_LINE_KEY)
            if isinstance(got, int):
                return got
        return fallback

    def _walk(value, owner: str, line: int) -> None:
        """Recursively scan a document for reference fields.

        Depth-agnostic on purpose: an ApplicationSet nests a whole Application
        spec under `spec.template.spec`, so matching on key NAME rather than a
        fixed path picks those up with no ApplicationSet-specific code (DRY).
        """
        if isinstance(value, list):
            for item in value:
                _walk(item, owner, line)
            return
        if not isinstance(value, dict):
            return

        here = _line_of(value, line)

        for key, val in value.items():
            if key == _LINE_KEY:
                continue
            kline = _line_of(val, here)

            if key in _SCALAR_REFS and isinstance(val, str):
                kind, relation = _SCALAR_REFS[key]
                _ref(owner, kind, val, relation, kline)
            elif key in _MAPPING_REFS and isinstance(val, dict):
                kind, relation = _MAPPING_REFS[key]
                _ref(owner, kind or val.get("kind", "Secret"), val.get("name"), relation, kline)
            elif key == "destination" and isinstance(val, dict):
                # ArgoCD Application/ApplicationSet target cluster+namespace.
                _ref(owner, "Namespace", val.get("namespace"), "deploys_to", kline)
            elif key in ("source", "sources") and isinstance(val, (dict, list)):
                for src in (val if isinstance(val, list) else [val]):
                    if isinstance(src, dict) and isinstance(src.get("path"), str):
                        _path_ref(owner, src["path"], "deploys_chart", _line_of(src, kline))
            elif key == "git" and isinstance(val, dict):
                # ApplicationSet git generator — `files:`/`directories:` globs are
                # the registry an AppSet fans out over. This is the edge that
                # makes "which apps reach prod?" answerable.
                for bucket in ("files", "directories"):
                    for entry in val.get(bucket) or []:
                        if isinstance(entry, dict) and isinstance(entry.get("path"), str):
                            _path_ref(owner, entry["path"], "generates_from", _line_of(entry, kline))
            elif key == "target" and isinstance(val, dict) and isinstance(val.get("name"), str):
                # ExternalSecret materializes a Secret of this name.
                _ref(owner, "Secret", val["name"], "produces", kline)

            _walk(val, owner, kline)

    def _path_ref(owner: str, raw: str, relation: str, line: int) -> None:
        """Reference to a repo path (a chart dir, or a generator glob).

        Kept as its own `path.<value>` address rather than resolved to a file
        node: a generator path is usually a glob (`gitops/apps/*.yaml`) and a
        chart path is often templated (`charts/{{.app}}`), so neither maps to a
        single real file. Naming them keeps the relationship queryable.
        """
        raw = raw.strip()
        if not raw:
            return
        address = f"path.{raw}"
        _add_node(address, line, declared=False)
        _add_edge(owner, address, relation, line)

    for doc in docs:
        if not isinstance(doc, dict):
            continue
        kind = doc.get("kind")
        meta = doc.get("metadata")
        if not isinstance(kind, str) or not kind.strip() or not doc.get("apiVersion"):
            continue
        name = meta.get("name") if isinstance(meta, dict) else None
        if not isinstance(name, str) or not name.strip():
            continue

        line = _line_of(doc, 1)
        address = f"{kind.strip()}.{name.strip()}"
        owner = _add_node(address, line, declared=True)

        if isinstance(meta, dict) and isinstance(meta.get("namespace"), str):
            _ref(owner, "Namespace", meta["namespace"], "in_namespace", _line_of(meta, line))

        _walk(doc.get("spec"), owner, line)

    return {"nodes": nodes, "edges": edges}
