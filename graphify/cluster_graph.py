"""Cluster graphs: link multiple repos' graphs into one connected graph.

A *cluster* is a directory holding a ``cluster.json`` (or optional YAML spec)
spec that names member repos and declares the cross-repo contracts between
them (API calls, shared resources, mirrored files, dependencies). Building a
cluster composes each member's ``graphify-out/graph.json`` under a
``repo_tag::`` namespace (the same mechanism as merge-graphs and the global
graph) and then resolves the declared links into real edges — the piece the
other multi-repo commands don't do.

Not to be confused with ``graphify/cluster.py`` (community detection). Docs
use "repo cluster" for this feature and "community detection" for that one.

Portability: member identity is the git ``url``; local paths are resolved
per machine (``cluster.local.json`` override → spec ``path`` hint → origin-
remote auto-discovery under ``search_roots``), so one committed spec works
across machines with different checkout layouts.

Output is a standard node-link ``graph.json`` under the cluster directory's
``graphify-out/``, so every existing command (query, path, explain, affected,
export) works on a cluster via ``cd <cluster-dir>`` or ``--graph``.
"""
from __future__ import annotations

import json
import hashlib
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

import networkx as nx

from .ids import normalize_id

SPEC_NAMES = ("cluster.json", "cluster.yaml", "cluster.yml")
LOCAL_NAMES = ("cluster.local.json", "cluster.local.yaml", "cluster.local.yml")
SCHEMA_VERSION = 1

# Pseudo repo tag for synthetic hub nodes; reserved, never a member tag.
CLUSTER_TAG = "cluster"

_TAG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

# Direct (point-to-point) link types and the edge relation they produce.
DIRECT_LINK_RELATIONS = {
    "api_call": "calls_api",
    "mirrored_file": "mirrors",
    "depends_on": "depends_on",
    "references": "references",
}
LINK_TYPES = (*DIRECT_LINK_RELATIONS, "shared_resource")

_ON_MISSING = ("warn", "create", "error")
_GRAPH_MODES = ("simple", "multi")


class ClusterSpecError(ValueError):
    """The cluster spec is invalid or a declared link cannot be applied."""


class AmbiguousSelectorError(ClusterSpecError):
    """A node selector matched more than one node."""


@dataclass
class ClusterMember:
    tag: str
    url: str = ""
    path: str = ""          # optional local hint, may use ~; relative to cluster dir
    graph: str = ""         # optional graph.json override, relative to the repo


@dataclass
class ClusterLink:
    type: str
    name: str = ""
    kind: str = ""                          # shared_resource only
    from_: dict | None = None               # selector {repo, file|label|id}
    to: dict | None = None
    referents: list[dict] = field(default_factory=list)  # shared_resource only
    on_missing: str = ""                    # per-link override of defaults
    direction: str = ""                     # "" (from->to) or "both"
    note: str = ""


@dataclass
class ClusterSpec:
    name: str
    members: list[ClusterMember] = field(default_factory=list)
    links: list[ClusterLink] = field(default_factory=list)
    on_missing: str = "warn"
    auto_externals: bool = True
    auto_packages: bool = False
    graph_mode: str = "simple"
    spec_path: Path | None = None

    def tags(self) -> set[str]:
        return {m.tag for m in self.members}


@dataclass
class LinkReport:
    edges_added: int = 0
    auto_package_edges: int = 0
    hubs_added: int = 0
    nodes_created: list[str] = field(default_factory=list)
    resolved: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Spec load / save
# ---------------------------------------------------------------------------

def _read_structured(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ClusterSpecError(f"{path}: could not read file ({exc})") from exc
    if path.suffix == ".json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ClusterSpecError(
                f"{path}: invalid JSON at line {exc.lineno}, column {exc.colno} "
                f"({exc.msg})"
            ) from exc
    else:
        try:
            import yaml
        except ImportError:
            raise ClusterSpecError(
                f"{path.name} requires pyyaml (`pip install pyyaml`), "
                f"or use the JSON spec form ({path.stem}.json)."
            )
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ClusterSpecError(f"{path}: invalid YAML ({exc})") from exc
    if not isinstance(data, dict):
        raise ClusterSpecError(f"{path}: expected a mapping at the top level")
    return data


def find_spec_file(cluster_dir: Path) -> Path | None:
    for name in SPEC_NAMES:
        p = cluster_dir / name
        if p.is_file():
            return p
    return None


def _parse_selector(raw, *, where: str) -> dict:
    if not isinstance(raw, dict) or "repo" not in raw:
        raise ClusterSpecError(f"{where}: selector must be a mapping with a 'repo' key, got {raw!r}")
    keys = [k for k in ("id", "file", "label") if raw.get(k)]
    if len(keys) != 1:
        raise ClusterSpecError(
            f"{where}: selector needs exactly one of id/file/label, got {sorted(raw)}"
        )
    return {"repo": str(raw["repo"]), keys[0]: str(raw[keys[0]])}


def validate_member_tag(tag: str, *, where: str = "cluster spec") -> None:
    """Validate a member tag before it is persisted or used as a namespace."""
    if not _TAG_RE.match(tag):
        raise ClusterSpecError(
            f"{where}: member tag {tag!r} is invalid "
            f"(letters/digits/._- only, must not contain '::')"
        )
    if tag == CLUSTER_TAG:
        raise ClusterSpecError(
            f"{where}: member tag '{CLUSTER_TAG}' is reserved for synthetic hub nodes"
        )


def load_spec(cluster_dir: Path) -> ClusterSpec:
    cluster_dir = Path(cluster_dir)
    spec_path = find_spec_file(cluster_dir)
    if spec_path is None:
        raise ClusterSpecError(
            f"no cluster spec found in {cluster_dir} "
            f"(expected one of: {', '.join(SPEC_NAMES)}). Run `graphify cluster init` first."
        )
    data = _read_structured(spec_path)

    version = data.get("schema_version", SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        raise ClusterSpecError(
            f"{spec_path.name}: schema_version {version} is not supported "
            f"(this graphify understands version {SCHEMA_VERSION})"
        )

    raw_members = data.get("members", [])
    if not isinstance(raw_members, list):
        raise ClusterSpecError(f"{spec_path.name}: members must be a list")

    raw_links = data.get("links", [])
    if not isinstance(raw_links, list):
        raise ClusterSpecError(f"{spec_path.name}: links must be a list")

    defaults = data.get("defaults", {})
    if not isinstance(defaults, dict):
        raise ClusterSpecError(f"{spec_path.name}: defaults must be a mapping")

    auto = data.get("auto_links", {})
    if not isinstance(auto, dict):
        raise ClusterSpecError(f"{spec_path.name}: auto_links must be a mapping")
    for key in ("externals", "packages"):
        if key in auto and not isinstance(auto[key], bool):
            raise ClusterSpecError(
                f"{spec_path.name}: auto_links.{key} must be a boolean"
            )

    members: list[ClusterMember] = []
    seen_tags: set[str] = set()
    for i, m in enumerate(raw_members):
        if not isinstance(m, dict) or not m.get("tag"):
            raise ClusterSpecError(f"{spec_path.name}: members[{i}] needs a 'tag'")
        tag = str(m["tag"])
        validate_member_tag(tag, where=spec_path.name)
        if tag in seen_tags:
            raise ClusterSpecError(f"{spec_path.name}: duplicate member tag {tag!r}")
        seen_tags.add(tag)
        members.append(ClusterMember(
            tag=tag,
            url=str(m.get("url") or ""),
            path=str(m.get("path") or ""),
            graph=str(m.get("graph") or ""),
        ))

    on_missing = str(defaults.get("on_missing") or "warn")
    if on_missing not in _ON_MISSING:
        raise ClusterSpecError(
            f"{spec_path.name}: defaults.on_missing must be one of {_ON_MISSING}, got {on_missing!r}"
        )

    links: list[ClusterLink] = []
    for i, raw in enumerate(raw_links):
        where = f"{spec_path.name}: links[{i}]"
        if not isinstance(raw, dict) or not raw.get("type"):
            raise ClusterSpecError(f"{where} needs a 'type'")
        ltype = str(raw["type"])
        if ltype not in LINK_TYPES:
            raise ClusterSpecError(f"{where}: unknown type {ltype!r} (known: {', '.join(LINK_TYPES)})")
        link_missing = str(raw.get("on_missing") or "")
        if link_missing and link_missing not in _ON_MISSING:
            raise ClusterSpecError(f"{where}: on_missing must be one of {_ON_MISSING}")
        link_direction = str(raw.get("direction") or "")
        if link_direction and link_direction != "both":
            raise ClusterSpecError(
                f"{where}: direction must be \"both\" or omitted (default: "
                f"from -> to), got {link_direction!r}"
            )
        link = ClusterLink(
            type=ltype,
            name=str(raw.get("name") or ""),
            kind=str(raw.get("kind") or ""),
            on_missing=link_missing,
            direction=link_direction,
            note=str(raw.get("note") or ""),
        )
        if ltype == "shared_resource":
            if not link.name:
                raise ClusterSpecError(f"{where}: shared_resource needs a 'name'")
            referents = raw.get("referents") or []
            if not isinstance(referents, list) or not referents:
                raise ClusterSpecError(f"{where}: shared_resource needs a non-empty 'referents' list")
            link.referents = [
                _parse_selector(r, where=f"{where}.referents[{j}]") for j, r in enumerate(referents)
            ]
        else:
            link.from_ = _parse_selector(raw.get("from"), where=f"{where}.from")
            link.to = _parse_selector(raw.get("to"), where=f"{where}.to")
        for sel in ([link.from_, link.to] if link.from_ else []) + link.referents:
            if sel and sel["repo"] not in seen_tags:
                raise ClusterSpecError(
                    f"{where}: selector references unknown member {sel['repo']!r}"
                )
        links.append(link)

    graph_mode = str(data.get("graph_mode") or "simple")
    if graph_mode not in _GRAPH_MODES:
        raise ClusterSpecError(
            f"{spec_path.name}: graph_mode must be one of {_GRAPH_MODES}, "
            f"got {graph_mode!r}"
        )
    return ClusterSpec(
        name=str(data.get("name") or cluster_dir.name),
        members=members,
        links=links,
        on_missing=on_missing,
        auto_externals=bool(auto.get("externals", True)),
        auto_packages=bool(auto.get("packages", False)),
        graph_mode=graph_mode,
        spec_path=spec_path,
    )


def spec_to_dict(spec: ClusterSpec) -> dict:
    """Serializable form of the spec (used by init/add/remove)."""
    members = []
    for m in spec.members:
        entry: dict = {"tag": m.tag}
        if m.url:
            entry["url"] = m.url
        if m.path:
            entry["path"] = m.path
        if m.graph:
            entry["graph"] = m.graph
        members.append(entry)
    links = []
    for l in spec.links:
        entry = {"type": l.type}
        for key, val in (
            ("name", l.name), ("kind", l.kind), ("from", l.from_), ("to", l.to),
            ("referents", l.referents or None), ("on_missing", l.on_missing),
            ("direction", l.direction), ("note", l.note),
        ):
            if val:
                entry[key] = val
        links.append(entry)
    return {
        "schema_version": SCHEMA_VERSION,
        "name": spec.name,
        "graph_mode": spec.graph_mode,
        "members": members,
        "links": links,
        "defaults": {"on_missing": spec.on_missing},
        "auto_links": {"externals": spec.auto_externals, "packages": spec.auto_packages},
    }


def save_spec(spec: ClusterSpec, cluster_dir: Path) -> Path:
    """Write the spec back, preserving existing YAML but creating JSON."""
    from .paths import write_text_atomic

    cluster_dir = Path(cluster_dir)
    target = spec.spec_path or find_spec_file(cluster_dir)
    data = spec_to_dict(spec)
    if target is None:
        target = cluster_dir / "cluster.json"
    if target.suffix == ".json":
        write_text_atomic(target, json.dumps(data, indent=2) + "\n")
    else:
        import yaml
        write_text_atomic(target, yaml.safe_dump(data, sort_keys=False, default_flow_style=False))
    spec.spec_path = target
    return target


def load_local_config(cluster_dir: Path) -> dict:
    """Machine-local overrides: {"paths": {tag: path}, "search_roots": [...]}"""
    for name in LOCAL_NAMES:
        p = Path(cluster_dir) / name
        if p.is_file():
            data = _read_structured(p)
            data["_path"] = p
            return data
    return {}


def save_local_config(cluster_dir: Path, cfg: dict) -> Path:
    from .paths import write_text_atomic

    cfg = {k: v for k, v in cfg.items() if not k.startswith("_")}
    target = None
    for name in LOCAL_NAMES:
        p = Path(cluster_dir) / name
        if p.is_file():
            target = p
            break
    if target is None:
        target = Path(cluster_dir) / "cluster.local.json"
    if target.suffix == ".json":
        write_text_atomic(target, json.dumps(cfg, indent=2) + "\n")
    else:
        import yaml
        write_text_atomic(target, yaml.safe_dump(cfg, sort_keys=False, default_flow_style=False))
    return target


# ---------------------------------------------------------------------------
# Member path resolution (URL is identity, path is machine-local)
# ---------------------------------------------------------------------------

def normalize_git_url(url: str) -> str:
    """Canonical `host/org/repo` form so https/ssh/.git variants compare equal."""
    u = url.strip()
    if not u:
        return ""
    u = re.sub(r"\.git/?$", "", u)
    m = re.match(r"^(?:ssh://)?(?:[\w.-]+@)?([\w.-]+)[:/](.+)$", u) if "://" not in u or u.startswith("ssh://") else None
    if m:
        return f"{m.group(1)}/{m.group(2)}".casefold().rstrip("/")
    m = re.match(r"^[a-z][a-z0-9+.-]*://(?:[\w.-]+@)?([\w.-]+)/(.+)$", u, re.I)
    if m:
        return f"{m.group(1)}/{m.group(2)}".casefold().rstrip("/")
    return u.casefold().rstrip("/")


def origin_url(repo_dir: Path) -> str | None:
    """The `origin` remote URL of a checkout, read from .git/config (no subprocess).

    Handles worktree-style `.git` files via their `gitdir:` pointer.
    """
    git = Path(repo_dir) / ".git"
    if git.is_file():
        try:
            pointer = git.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if not pointer.startswith("gitdir:"):
            return None
        gitdir = Path(pointer.split(":", 1)[1].strip())
        if not gitdir.is_absolute():
            gitdir = (repo_dir / gitdir).resolve()
        common = gitdir / "commondir"
        if common.is_file():
            rel = common.read_text(encoding="utf-8").strip()
            gitdir = (gitdir / rel).resolve()
        config = gitdir / "config"
    else:
        config = git / "config"
    if not config.is_file():
        return None
    in_origin = False
    try:
        lines = config.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in lines:
        s = line.strip()
        if s.startswith("["):
            in_origin = s.replace("'", '"') == '[remote "origin"]'
        elif in_origin:
            key, sep, value = s.partition("=")
            if sep and key.strip() == "url":
                return value.strip()
    return None


def _expand(path_str: str, cluster_dir: Path) -> Path:
    p = Path(path_str).expanduser()
    if not p.is_absolute():
        p = Path(cluster_dir) / p
    # normpath (not resolve) collapses `../` segments without dereferencing
    # symlinks — a member checked out behind a symlink should keep the path
    # the user wrote.
    return Path(os.path.normpath(p))


def resolve_member_path(
    member: ClusterMember, cluster_dir: Path, local_cfg: dict
) -> tuple[Path | None, list[str]]:
    """Resolve a member to a local checkout. Returns (path or None, warnings).

    Order: cluster.local.* override → spec `path` hint → auto-discovery by
    matching each candidate dir's origin remote against the member `url`.
    Whenever a path resolves and both URLs are known, a mismatch is a warning
    (guards against same-named dirs pointing at a different repo).
    """
    warnings: list[str] = []
    want = normalize_git_url(member.url)

    def _check(path: Path, source: str) -> Path:
        if want:
            found = origin_url(path)
            if found and normalize_git_url(found) != want:
                warnings.append(
                    f"{member.tag}: {source} {path} has origin {found!r}, "
                    f"but the spec declares {member.url!r}"
                )
        return path

    override = (local_cfg.get("paths") or {}).get(member.tag)
    if override:
        p = _expand(str(override), cluster_dir)
        if p.is_dir():
            return _check(p, "local override"), warnings
        warnings.append(f"{member.tag}: local override path does not exist: {p}")

    if member.path:
        p = _expand(member.path, cluster_dir)
        if p.is_dir():
            return _check(p, "spec path"), warnings

    if want:
        roots = [_expand(str(r), cluster_dir) for r in (local_cfg.get("search_roots") or [])]
        roots.append(Path(cluster_dir).resolve().parent)
        seen: set[Path] = set()
        for root in roots:
            if root in seen or not root.is_dir():
                continue
            seen.add(root)
            try:
                children = sorted(c for c in root.iterdir() if c.is_dir())
            except OSError:
                continue
            for child in children:
                found = origin_url(child)
                if found and normalize_git_url(found) == want:
                    return child, warnings

    return None, warnings


def member_graph_path(member: ClusterMember, repo_dir: Path) -> Path:
    from .paths import GRAPHIFY_OUT_NAME

    rel = member.graph or f"{GRAPHIFY_OUT_NAME}/graph.json"
    return Path(repo_dir) / rel


# ---------------------------------------------------------------------------
# Compose + link
# ---------------------------------------------------------------------------

def compose_members(
    spec: ClusterSpec, resolved: dict[str, Path]
) -> tuple[nx.Graph, dict[str, dict]]:
    """Union all member graphs under repo_tag:: namespaces.

    ``resolved`` maps member tag -> repo checkout dir. Returns the composed
    graph and per-member stats. Externals dedup-by-label follows
    ``spec.auto_externals``.
    """
    from .build import (
        load_graph_json,
        merge_prefixed_into,
        prefix_graph_for_global,
        promote_to_multidigraph,
    )

    # Composed directed in BOTH modes: the composed graph is re-serialized, and
    # an undirected round-trip re-emits edge endpoints by node insertion order,
    # silently flipping caller/callee (#760). Members load directed so their
    # stored source/target order is what the cluster graph.json persists.
    G: nx.Graph = nx.MultiDiGraph() if spec.graph_mode == "multi" else nx.DiGraph()
    stats: dict[str, dict] = {}
    cid_base = 0
    for member in spec.members:
        gp = member_graph_path(member, resolved[member.tag])
        if not gp.is_file():
            raise ClusterSpecError(
                f"member '{member.tag}' has no graph at {gp}. "
                f"Run `graphify extract .` (or your usual build) in {resolved[member.tag]} first."
            )
        try:
            member_graph = load_graph_json(
                gp, preserve_type=spec.graph_mode == "multi", directed=True
            )
        except ValueError as exc:
            raise ClusterSpecError(
                f"member '{member.tag}' has an unreadable graph at {gp} ({exc}). "
                f"Re-run `graphify extract . --force` in {resolved[member.tag]} to rebuild it."
            ) from exc
        source_multigraph = member_graph.is_multigraph()
        if spec.graph_mode == "multi":
            if not source_multigraph:
                print(
                    f"[graphify cluster] warning: member '{member.tag}' is a simple "
                    "graph; re-extract it with --multigraph to recover parallel relations",
                    file=sys.stderr,
                )
            member_graph = promote_to_multidigraph(member_graph)
        prefixed = prefix_graph_for_global(member_graph, member.tag)
        cid_base = _renumber_member_communities(prefixed, cid_base)
        total = prefixed.number_of_nodes()
        if spec.auto_externals:
            added = merge_prefixed_into(G, prefixed)
        else:
            G = nx.compose(G, prefixed)
            added = total
        stats[member.tag] = {
            "graph_path": str(gp),
            "node_count": total,
            "edge_count": prefixed.number_of_edges(),
            "externals_merged": total - added,
            "source_multigraph": source_multigraph,
        }
    return G, stats


def _renumber_member_communities(H: "nx.Graph", next_cid: int) -> int:
    """Remap one member's community ids onto a cluster-global range, in place.

    Every member numbers its communities from 0, so composing them verbatim
    merges unrelated "community 0" groups across repos in every consumer that
    groups by the integer (MCP get_community, NODE lines, explain). Ids are
    assigned in node order (deterministic: node_link_graph preserves the
    member graph.json's order). Placeholder names ("Community N") track the
    new id; real LLM-assigned names are preserved. Returns the next free id.
    """
    mapping: dict = {}
    for _, data in H.nodes(data=True):
        cid = data.get("community")
        if cid is None:
            continue
        if cid not in mapping:
            mapping[cid] = next_cid
            next_cid += 1
        if data.get("community_name") == f"Community {cid}":
            data["community_name"] = f"Community {mapping[cid]}"
        data["community"] = mapping[cid]
    return next_cid


def _selector_str(sel: dict) -> str:
    key = next(k for k in ("id", "file", "label") if k in sel)
    return f"{sel['repo']}:{key}={sel[key]}"


def _norm_source_file(sf: str) -> str:
    # removeprefix, not lstrip: lstrip("./") strips *characters*, eating the
    # dot off ".env" / ".github/..." and aliasing them onto unrelated paths.
    p = PurePosixPath(sf.replace("\\", "/")).as_posix()
    return p.removeprefix("./").lstrip("/")


def resolve_selector(
    nodes_by_repo: dict[str, list[tuple[str, dict]]], sel: dict
) -> str | None:
    """Resolve a spec selector to a composed-graph node id, or None.

    Selectors never reference raw prefixed ids, so users are insulated from
    ID normalization: `id` matches the member-local id, `file` suffix-matches
    source_file (preferring the file node when a file contains many symbols),
    `label` matches exactly and then case/punctuation-insensitively.
    """
    candidates = nodes_by_repo.get(sel["repo"], [])

    if "id" in sel:
        want = sel["id"]
        matches = [n for n, d in candidates if d.get("local_id") == want]
        if not matches:
            want_n = normalize_id(want)
            matches = [n for n, d in candidates if d.get("local_id") == want_n]
    elif "file" in sel:
        rel = _norm_source_file(sel["file"])
        matches = [
            n for n, d in candidates
            if d.get("source_file")
            and (_norm_source_file(d["source_file"]) == rel
                 or _norm_source_file(d["source_file"]).endswith("/" + rel))
        ]
        if len(matches) > 1:
            # Prefer the file-level node. Two signals, strongest first:
            # 1. The file-node ID spec (#1504): the node's local_id equals
            #    normalize_id(<path minus extension>) — deterministic and holds
            #    for both AST and LLM extractions regardless of labeling.
            # 2. Label == the file's basename (AST file nodes; LLM graphs may
            #    relabel file nodes descriptively, so this is the fallback).
            by_id = dict(candidates)
            stem = rel.rsplit(".", 1)[0] if "." in rel.rsplit("/", 1)[-1] else rel
            spec_ids = {normalize_id(stem)}
            # A shorter selector path (suffix match) can't reproduce the full
            # repo-relative id, so also accept any matched node whose own
            # source_file round-trips to its local_id.
            for n in matches:
                sf = _norm_source_file(by_id[n].get("source_file", ""))
                base = sf.rsplit("/", 1)[-1]
                sf_stem = sf.rsplit(".", 1)[0] if "." in base else sf
                if by_id[n].get("local_id") == normalize_id(sf_stem):
                    spec_ids.add(by_id[n]["local_id"])
            id_nodes = [n for n in matches if by_id[n].get("local_id") in spec_ids]
            if len(id_nodes) == 1:
                matches = id_nodes
            else:
                def _label_is_basename(n: str) -> bool:
                    label = by_id[n].get("label") or ""
                    sf = _norm_source_file(by_id[n].get("source_file", ""))
                    return bool(label) and (sf == label or sf.endswith("/" + label))

                file_nodes = [n for n in matches if _label_is_basename(n)]
                if len(file_nodes) == 1:
                    matches = file_nodes
    else:
        want = sel["label"]
        want_n = normalize_id(want)
        matches = [n for n, d in candidates if d.get("label") == want]
        if not matches:
            matches = [n for n, d in candidates if normalize_id(d.get("label") or "") == want_n]
        if not matches:
            # External-library nodes dedupe by label onto the FIRST member that
            # references them, keeping that member's `repo` attr — a selector
            # naming any other referencing member would silently break when the
            # spec's member order changes. Externals are cluster-wide by
            # construction, so label selectors fall back to matching them
            # regardless of repo attribution.
            externals = [
                (n, d)
                for bucket in nodes_by_repo.values()
                for n, d in bucket
                if not d.get("source_file") and d.get("label")
            ]
            matches = [n for n, d in externals if d["label"] == want]
            if not matches:
                matches = [n for n, d in externals if normalize_id(d["label"]) == want_n]
            if matches:
                candidates = externals  # keep the ambiguity listing resolvable

    if not matches:
        return None
    if len(matches) > 1:
        by_id = dict(candidates)
        listing = ", ".join(
            f"{n} ({by_id[n].get('source_file', '?')})" for n in sorted(matches)[:8]
        )
        raise AmbiguousSelectorError(
            f"selector {_selector_str(sel)} matches {len(matches)} nodes: {listing}"
            + (" …" if len(matches) > 8 else "")
        )
    return matches[0]


def _hub_id(kind: str, name: str) -> str:
    return f"{CLUSTER_TAG}::{normalize_id(kind or 'resource')}_{normalize_id(name)}"


def apply_spec_links(G: nx.Graph, spec: ClusterSpec, *, dry_run: bool = False) -> LinkReport:
    """Turn declared links into edges (and hub/concept nodes) on the composed graph."""
    report = LinkReport()
    spec_file = spec.spec_path.name if spec.spec_path else "cluster.json"

    nodes_by_repo: dict[str, list[tuple[str, dict]]] = {}
    for n, d in G.nodes(data=True):
        nodes_by_repo.setdefault(d.get("repo", ""), []).append((n, d))

    # Simple mode rejects occupied pairs to prevent NetworkX overwrites. Multi
    # mode permits distinct keyed relations and rejects only an exact duplicate
    # declared-link identity.
    occupied_pairs: dict[tuple[str, str], str] = {}
    for u, v, data in G.edges(data=True):
        pair = (min(u, v), max(u, v))
        relation = data.get("relation") or "unknown"
        occupied_pairs[pair] = f"existing relation {relation!r}"
    declared_identities: set[tuple[str, str, str, str]] = set()

    def _resolve(link: ClusterLink, sel: dict, link_label: str) -> str | None:
        try:
            node = resolve_selector(nodes_by_repo, sel)
        except AmbiguousSelectorError as exc:
            report.errors.append(f"{link_label}: {exc}")
            return None
        if node is not None:
            return node
        mode = link.on_missing or spec.on_missing
        desc = _selector_str(sel)
        if mode == "error":
            report.errors.append(f"{link_label}: no node matches {desc}")
        elif mode == "create":
            key = next(k for k in ("id", "file", "label") if k in sel)
            concept = f"{sel['repo']}::concept_{normalize_id(sel[key])}"
            if not dry_run and concept not in G:
                G.add_node(
                    concept,
                    label=sel[key],
                    file_type="concept",
                    source_file="",
                    repo=sel["repo"],
                    local_id=concept.split("::", 1)[1],
                    origin="cluster_spec",
                )
                nodes_by_repo.setdefault(sel["repo"], []).append((concept, G.nodes[concept]))
            report.nodes_created.append(concept)
            return concept
        else:
            report.warnings.append(f"{link_label}: no node matches {desc}; link skipped")
        return None

    def _add_edge(
        u: str, v: str, link: ClusterLink, relation: str, link_label: str
    ) -> bool:
        if u == v:
            report.warnings.append(f"link '{link.name or link.type}' resolved to a self-loop; skipped")
            return False
        pair = (min(u, v), max(u, v))
        if G.is_multigraph():
            identities = [(u, v, relation, link.name or link.type)]
            if link.direction == "both":
                identities.append((v, u, relation, link.name or link.type))
            if any(identity in declared_identities for identity in identities):
                report.errors.append(f"{link_label}: duplicate declared cluster relation")
                return False
            declared_identities.update(identities)
        else:
            prior = occupied_pairs.get(pair)
            if prior is not None:
                report.errors.append(
                    f"{link_label}: cannot add relation {relation!r} between {u} and {v}; "
                    f"the pair already has {prior}. Simple cluster graphs allow only "
                    f"one relation per node pair"
                )
                return False
            occupied_pairs[pair] = f"{link_label} relation {relation!r}"
        # direction: "both" materializes as a real reverse edge — traversal
        # (affected's in_edges, query BFS) reads topology, not attrs, so a
        # metadata-only flag would silently traverse one way. The declared
        # link owns the unordered pair: its own reverse edge is exempt from
        # the one-relation-per-pair guard, a separate reverse link is not.
        endpoint_pairs = [(u, v)] + ([(v, u)] if link.direction == "both" else [])
        if not dry_run:
            for src, tgt in endpoint_pairs:
                attrs = {
                    "relation": relation,
                    "confidence": "EXTRACTED",
                    "confidence_score": 1.0,
                    "weight": 1.0,
                    "source_file": spec_file,
                    "origin": "cluster_spec",
                    "_src": src,
                    "_tgt": tgt,
                }
                if link.name:
                    attrs["link_name"] = link.name
                if link.direction == "both":
                    attrs["direction"] = "both"
                if link.note:
                    attrs["note"] = link.note
                if G.is_multigraph():
                    from .build import stable_edge_key

                    attrs["context"] = link.name or link.type
                    G.add_edge(src, tgt, key=stable_edge_key(src, tgt, attrs), **attrs)
                else:
                    G.add_edge(src, tgt, **attrs)
        report.edges_added += len(endpoint_pairs)
        return True

    for i, link in enumerate(spec.links):
        link_label = f"links[{i}] ({link.name or link.type})"
        if link.type == "shared_resource":
            hub = _hub_id(link.kind, link.name)
            resolved = [
                node for sel in link.referents
                if (node := _resolve(link, sel, link_label)) is not None
            ]
            if not resolved:
                report.warnings.append(f"{link_label}: no referents resolved; hub not created")
                continue
            if not dry_run and hub not in G:
                G.add_node(
                    hub,
                    label=link.name,
                    file_type="concept",
                    source_file="",
                    repo=CLUSTER_TAG,
                    local_id=hub.split("::", 1)[1],
                    resource_kind=link.kind or "resource",
                    origin="cluster_spec",
                )
            report.hubs_added += 1
            for node in resolved:
                _add_edge(node, hub, link, "uses", link_label)
            report.resolved.append(
                f"{link_label}: hub {hub} <- {len(resolved)}/{len(link.referents)} referents"
            )
        else:
            assert link.from_ is not None and link.to is not None  # enforced by load_spec
            src = _resolve(link, link.from_, link_label)
            tgt = _resolve(link, link.to, link_label)
            if src is None or tgt is None:
                continue
            relation = DIRECT_LINK_RELATIONS[link.type]
            if _add_edge(src, tgt, link, relation, link_label):
                report.resolved.append(f"{link_label}: {src} -[{relation}]-> {tgt}")

    return report


def apply_auto_package_links(
    G: nx.Graph,
    spec: ClusterSpec,
    report: LinkReport | None = None,
    *,
    dry_run: bool = False,
) -> LinkReport:
    """Link package definitions to unique providers in other member repos."""
    report = report or LinkReport()
    package_nodes = sorted(
        (
            (node, data)
            for node, data in G.nodes(data=True)
            if data.get("type") == "package"
        ),
        key=lambda item: str(item[0]),
    )
    providers: dict[str, list[tuple[str, dict]]] = {}
    stale_repos: set[str] = set()
    for node, data in package_nodes:
        key = data.get("package_key")
        if isinstance(key, str) and key:
            providers.setdefault(key, []).append((node, data))
        if "dependency_keys" not in data:
            stale_repos.add(str(data.get("repo") or "unknown"))

    for repo in sorted(stale_repos):
        report.warnings.append(
            f"member '{repo}' has package nodes without dependency metadata; "
            "re-run `graphify extract --force` in that member to enable "
            "auto_links.packages"
        )

    occupied = {
        (min(str(u), str(v)), max(str(u), str(v))) for u, v in G.edges()
    }
    spec_file = spec.spec_path.name if spec.spec_path else "cluster.json"
    for source, data in package_nodes:
        source_repo = data.get("repo")
        dep_keys = data.get("dependency_keys")
        if not isinstance(dep_keys, list):
            continue
        for dep_key in sorted({str(key) for key in dep_keys if key}):
            candidates = [
                (node, provider)
                for node, provider in providers.get(dep_key, [])
                if provider.get("repo") != source_repo
            ]
            if not candidates:
                continue
            if len(candidates) > 1:
                listing = ", ".join(str(node) for node, _data in candidates)
                report.warnings.append(
                    f"package dependency {dep_key!r} from {source} has "
                    f"{len(candidates)} cross-repo providers ({listing}); skipped"
                )
                continue
            target, _provider = candidates[0]
            pair = (min(str(source), str(target)), max(str(source), str(target)))
            if pair in occupied:
                report.warnings.append(
                    f"package dependency {dep_key!r} from {source} is already "
                    "connected by a member or declared link; automatic link skipped"
                )
                continue
            occupied.add(pair)
            if not dry_run:
                attrs = {
                    "relation": "depends_on",
                    "confidence": "EXTRACTED",
                    "confidence_score": 1.0,
                    "weight": 1.0,
                    "source_file": spec_file,
                    "origin": "cluster_auto_package",
                    "package_key": dep_key,
                    "_src": source,
                    "_tgt": target,
                }
                if G.is_multigraph():
                    from .build import stable_edge_key

                    G.add_edge(
                        source, target,
                        key=stable_edge_key(source, target, attrs),
                        **attrs,
                    )
                else:
                    G.add_edge(source, target, **attrs)
            report.edges_added += 1
            report.auto_package_edges += 1
            report.resolved.append(
                f"auto package: {source} -[depends_on]-> {target} ({dep_key})"
            )
    return report


# ---------------------------------------------------------------------------
# Build orchestration
# ---------------------------------------------------------------------------

def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:16]


def cluster_out_dir(cluster_dir: Path) -> Path:
    from .paths import GRAPHIFY_OUT

    out = Path(GRAPHIFY_OUT)
    return out if os.path.isabs(GRAPHIFY_OUT) else Path(cluster_dir) / out


def _manifest_path(out_dir: Path) -> Path:
    return out_dir / "cluster-manifest.json"


def resolve_all_members(
    spec: ClusterSpec, cluster_dir: Path, local_cfg: dict
) -> tuple[dict[str, Path], list[str], list[str]]:
    """Resolve every member. Returns (tag -> dir, warnings, errors)."""
    resolved: dict[str, Path] = {}
    warnings: list[str] = []
    errors: list[str] = []
    for member in spec.members:
        path, w = resolve_member_path(member, cluster_dir, local_cfg)
        warnings.extend(w)
        if path is None:
            hint = f"graphify cluster locate {member.tag} /path/to/checkout"
            errors.append(
                f"member '{member.tag}' could not be resolved to a local checkout"
                + (f" (url: {member.url})" if member.url else "")
                + f". Fix: {hint}"
            )
        else:
            resolved[member.tag] = path
    return resolved, warnings, errors


def _render_report(spec: ClusterSpec, stats: dict, report: LinkReport, built_at: str) -> str:
    lines = [
        f"# Cluster report: {spec.name}",
        "",
        f"Built: {built_at}",
        "",
        "## Members",
        "",
        "| tag | nodes | edges | externals merged |",
        "|---|---|---|---|",
    ]
    for tag, s in stats.items():
        lines.append(f"| {tag} | {s['node_count']} | {s['edge_count']} | {s['externals_merged']} |")
    lines += [
        "",
        "## Links",
        "",
        f"- edges added: {report.edges_added}",
        f"- automatic package edges: {report.auto_package_edges}",
        f"- shared-resource hubs: {report.hubs_added}",
    ]
    if report.resolved:
        lines += [""] + [f"- {r}" for r in report.resolved]
    if report.nodes_created:
        lines += ["", "### Created concept nodes (on_missing: create)", ""]
        lines += [f"- {n}" for n in report.nodes_created]
    if report.warnings:
        lines += ["", "### Warnings", ""] + [f"- {w}" for w in report.warnings]
    if report.errors:
        lines += ["", "### Errors", ""] + [f"- {e}" for e in report.errors]
    return "\n".join(lines) + "\n"


def check_member_ref_conflicts(
    spec: ClusterSpec, resolved: dict[str, Path], cluster_dir: Path
) -> None:
    """Raise when a member's marker shows a *different* cluster owns this name.

    A git-URL mismatch proves a genuine collision (two distinct remotes, same
    cluster name). For URL-less clusters, identity is best-effort: an existing
    ref that carries a URL always owns the name, and two URL-less clusters
    collide when the old ref's ``dir_hint`` resolves to a different existing
    cluster directory bearing the same name. A stale/unresolvable ``dir_hint``
    alone never errors — hints are machine- and layout-dependent, and a moved
    cluster directory is the common benign cause (write_member_refs warns and
    refreshes the hint). Runs in build_cluster BEFORE any output is written,
    on every build path including the unchanged-inputs skip, so a real
    conflict fails cleanly and keeps failing until resolved.
    """
    from .cluster_ref import load_cluster_refs
    from .paths import GRAPHIFY_OUT_NAME

    new_url = normalize_git_url(origin_url(cluster_dir) or "")
    for member in spec.members:
        repo_dir = resolved.get(member.tag)
        if repo_dir is None:
            continue
        refs = load_cluster_refs(Path(repo_dir) / GRAPHIFY_OUT_NAME)
        old = next((r for r in refs if r["cluster_name"] == spec.name), None)
        if old is None:
            continue
        old_url = normalize_git_url(str(old.get("cluster_url") or ""))
        if new_url:
            if old_url and old_url != new_url:
                raise ClusterSpecError(
                    f"member '{member.tag}' already belongs to a different cluster "
                    f"named '{spec.name}' ({old.get('cluster_url')}); cluster "
                    f"names must be unique per member"
                )
            continue
        if old_url:
            raise ClusterSpecError(
                f"member '{member.tag}' already belongs to a cluster named "
                f"'{spec.name}' tracked at {old.get('cluster_url')}, and this "
                f"cluster directory has no origin remote to prove it is the same "
                f"one. Rename this cluster, or add the matching remote."
            )
        hint = str(old.get("dir_hint") or "")
        if hint:
            candidate = Path(os.path.normpath(Path(repo_dir) / hint))
            try:
                is_other = (
                    find_spec_file(candidate) is not None
                    and load_spec(candidate).name == spec.name
                    and candidate.resolve() != Path(cluster_dir).resolve()
                )
            except Exception:
                is_other = False
            if is_other:
                raise ClusterSpecError(
                    f"member '{member.tag}' already belongs to a cluster named "
                    f"'{spec.name}' at {candidate}; cluster names must be unique "
                    f"per member. Rename one of the clusters."
                )


def write_member_refs(
    spec: ClusterSpec,
    resolved: dict[str, Path],
    cluster_dir: Path,
    built_at: str,
    *,
    only_missing: bool = False,
) -> int:
    """Upsert this cluster in each member's portable cluster-ref collection.

    The marker is committable (graphify-out/ travels with the member repo), so
    it carries no absolute paths — only the cluster's git URL, the member
    roster, and a machine-derived relative ``dir_hint`` that fails soft on
    other machines. ``only_missing`` (the skipped-rebuild path) backfills
    memberships for freshly cloned members without churning existing entries.
    A member whose ``graph`` field points outside graphify-out/ still gets its
    marker in graphify-out/ — that is where member-side readers look.
    Failures are warnings, never build errors; name collisions with a
    *different* cluster are ``check_member_ref_conflicts``'s job, which
    ``build_cluster`` runs before writing any output. Returns the count
    written.
    """
    from .cluster_ref import (
        CLUSTER_REF_NAME,
        CLUSTER_REF_VERSION,
        load_cluster_refs,
    )
    from .paths import GRAPHIFY_OUT_NAME, write_json_atomic

    roster = [{"tag": m.tag, "url": m.url} for m in spec.members]
    cluster_url = origin_url(cluster_dir) or ""
    pending: list[tuple[ClusterMember, Path, Path, list[dict], dict]] = []
    for member in spec.members:
        repo_dir = resolved.get(member.tag)
        if repo_dir is None:
            continue
        out_dir = Path(repo_dir) / GRAPHIFY_OUT_NAME
        target = out_dir / CLUSTER_REF_NAME
        existing = load_cluster_refs(out_dir)
        old = next((r for r in existing if r["cluster_name"] == spec.name), None)
        if only_missing and old is not None:
            continue
        try:
            dir_hint = os.path.relpath(Path(cluster_dir).resolve(), Path(repo_dir).resolve())
        except ValueError:  # Windows cross-drive
            dir_hint = ""
        ref = {
            "cluster_name": spec.name,
            "cluster_url": cluster_url,
            "self_tag": member.tag,
            "member_count": len(spec.members),
            "members": roster,
            "built_at": built_at,
            "dir_hint": dir_hint,
        }
        if old is not None:
            old_url = normalize_git_url(str(old.get("cluster_url") or ""))
            new_url = normalize_git_url(cluster_url)
            same_by_url = bool(old_url and new_url and old_url == new_url)
            if (
                not same_by_url
                and old.get("dir_hint") and dir_hint
                and os.path.normpath(str(old["dir_hint"])) != os.path.normpath(dir_hint)
            ):
                # A hint mismatch alone can't distinguish a moved cluster (or a
                # different checkout layout) from a same-named other cluster, so
                # it never blocks the build — genuine collisions are caught by
                # URL in check_member_ref_conflicts before any output is
                # written. Warn and refresh the entry: last build wins.
                print(
                    f"[graphify cluster] warning: member '{member.tag}' marker "
                    f"for cluster '{spec.name}' pointed at {old['dir_hint']}; "
                    f"updating it to this cluster's location",
                    file=sys.stderr,
                )
        pending.append((member, out_dir, target, existing, ref))

    written = 0
    for member, out_dir, target, existing, ref in pending:
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            refs = [r for r in existing if r["cluster_name"] != spec.name]
            refs.append(ref)
            refs.sort(key=lambda r: r["cluster_name"])
            write_json_atomic(
                target,
                {"version": CLUSTER_REF_VERSION, "clusters": refs},
                indent=2,
            )
            written += 1
        except OSError as exc:
            print(
                f"[graphify cluster] warning: could not write {CLUSTER_REF_NAME} "
                f"for member '{member.tag}' ({exc}); build continues",
                file=sys.stderr,
            )
    return written


def _check_self_composition(
    spec: ClusterSpec, resolved: dict[str, Path], cluster_dir: Path
) -> None:
    """Refuse a cluster that lists itself (or its own output) as a member.

    Composing reads each member's graphify-out/graph.json and writes the
    cluster's own graphify-out/graph.json; if those coincide, the build
    consumes its own prior output and overwrites it, and the next build
    re-prefixes already-prefixed ids (``a::a::x``), snowballing.
    """
    own_dir = Path(cluster_dir).resolve()
    own_graph = (cluster_out_dir(cluster_dir) / "graph.json").resolve()
    for member in spec.members:
        repo = resolved.get(member.tag)
        if repo is None:
            continue
        if (
            Path(repo).resolve() == own_dir
            or member_graph_path(member, repo).resolve() == own_graph
        ):
            raise ClusterSpecError(
                f"member '{member.tag}' resolves to the cluster directory itself "
                f"({repo}); a cluster cannot compose its own output. Remove it with "
                f"`graphify cluster remove {member.tag}`, or point it at the real "
                f"checkout with `graphify cluster locate {member.tag} <path>`."
            )


def build_cluster(
    cluster_dir: Path, *, force: bool = False, no_links: bool = False, write_refs: bool = True
) -> dict:
    """Compose member graphs and resolve links; write graph.json + manifest + report.

    Also writes a cluster-ref.json back-reference into each member's
    graphify-out/ (see write_member_refs) unless ``write_refs`` is False.
    Returns a summary dict: {name, nodes, edges, members, links: LinkReport,
    skipped, refs_written, out}.
    """
    from networkx.readwrite import json_graph as _jg
    from .paths import write_json_atomic, write_text_atomic

    cluster_dir = Path(cluster_dir)
    spec = load_spec(cluster_dir)
    if not spec.members:
        raise ClusterSpecError(
            "cluster has no members; add repos with `graphify cluster add <path>` "
            "(an empty build would write an empty graph.json)"
        )
    local_cfg = load_local_config(cluster_dir)
    resolved, warnings, errors = resolve_all_members(spec, cluster_dir, local_cfg)
    for w in warnings:
        print(f"[graphify cluster] warning: {w}", file=sys.stderr)
    if errors:
        raise ClusterSpecError("; ".join(errors))
    _check_self_composition(spec, resolved, cluster_dir)

    if write_refs:
        check_member_ref_conflicts(spec, resolved, cluster_dir)

    out_dir = cluster_out_dir(cluster_dir)
    graph_path = out_dir / "graph.json"
    manifest_path = _manifest_path(out_dir)

    spec_hash = _file_hash(spec.spec_path) if spec.spec_path else ""
    links_enabled = not no_links
    member_hashes = {}
    for member in spec.members:
        gp = member_graph_path(member, resolved[member.tag])
        member_hashes[member.tag] = _file_hash(gp) if gp.is_file() else ""

    if not force and graph_path.is_file() and manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}
        prior = {t: m.get("source_hash", "") for t, m in (manifest.get("members") or {}).items()}
        if (
            manifest.get("spec_hash") == spec_hash
            and prior == member_hashes
            and manifest.get("links_enabled") == links_enabled
            and manifest.get("graph_mode") == spec.graph_mode
        ):
            # Backfill markers for members that don't have one yet (e.g. a
            # freshly cloned checkout) without churning existing files.
            refs = 0
            if write_refs:
                refs = write_member_refs(
                    spec, resolved, cluster_dir,
                    manifest.get("built_at", ""), only_missing=True,
                )
            return {
                "name": spec.name,
                "skipped": True,
                "out": str(graph_path),
                "nodes": manifest.get("node_count", 0),
                "edges": manifest.get("edge_count", 0),
                "refs_written": refs,
            }

    G, stats = compose_members(spec, resolved)
    report = LinkReport() if no_links else apply_spec_links(G, spec)
    if not no_links and spec.auto_packages:
        apply_auto_package_links(G, spec, report)
    if report.errors:
        raise ClusterSpecError("link resolution failed: " + "; ".join(report.errors))
    for w in report.warnings:
        print(f"[graphify cluster] warning: {w}", file=sys.stderr)

    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        data = _jg.node_link_data(G, edges="links")
    except TypeError:
        data = _jg.node_link_data(G)
    # The graph is composed directed, so source/target already carry the true
    # direction; drop the _src/_tgt persistence markers like export.to_json.
    for link in data.get("links", data.get("edges", [])):
        link.pop("_src", None)
        link.pop("_tgt", None)
    write_json_atomic(graph_path, data, indent=2)

    built_at = datetime.now(timezone.utc).isoformat()
    manifest = {
        "version": 1,
        "name": spec.name,
        "built_at": built_at,
        "spec_hash": spec_hash,
        "links_enabled": links_enabled,
        "graph_mode": spec.graph_mode,
        "node_count": G.number_of_nodes(),
        "edge_count": G.number_of_edges(),
        "members": {
            tag: {
                "source_path": str(resolved[tag]),
                "graph_path": stats[tag]["graph_path"],
                "source_hash": member_hashes[tag],
                "node_count": stats[tag]["node_count"],
                "edge_count": stats[tag]["edge_count"],
            }
            for tag in stats
        },
    }
    write_json_atomic(manifest_path, manifest, indent=2)
    write_text_atomic(out_dir / "CLUSTER_REPORT.md", _render_report(spec, stats, report, built_at))

    refs = write_member_refs(spec, resolved, cluster_dir, built_at) if write_refs else 0

    return {
        "name": spec.name,
        "skipped": False,
        "out": str(graph_path),
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "members": stats,
        "links": report,
        "refs_written": refs,
    }


def check_cluster(cluster_dir: Path) -> tuple[LinkReport, list[str]]:
    """Validate the spec and dry-run link resolution. Returns (report, errors).

    Errors cover unresolvable members, missing member graphs, and (per
    on_missing: error) unresolvable selectors — anything that would make
    ``build`` fail.
    """
    cluster_dir = Path(cluster_dir)
    spec = load_spec(cluster_dir)
    local_cfg = load_local_config(cluster_dir)
    resolved, warnings, errors = resolve_all_members(spec, cluster_dir, local_cfg)

    report = LinkReport(warnings=list(warnings), errors=list(errors))
    if not spec.members:
        report.errors.append(
            "cluster has no members; add repos with `graphify cluster add <path>`"
        )
        return report, report.errors
    try:
        _check_self_composition(spec, resolved, cluster_dir)
    except ClusterSpecError as exc:
        report.errors.append(str(exc))
    missing_graphs = [
        member.tag for member in spec.members
        if member.tag in resolved and not member_graph_path(member, resolved[member.tag]).is_file()
    ]
    for tag in missing_graphs:
        report.errors.append(
            f"member '{tag}' has no graph at {member_graph_path(next(m for m in spec.members if m.tag == tag), resolved[tag])}"
        )
    if report.errors:
        return report, report.errors

    try:
        G, _stats = compose_members(spec, resolved)
    except ClusterSpecError as exc:  # e.g. a corrupt member graph.json
        report.errors.append(str(exc))
        return report, report.errors
    # This graph exists only for validation, so materialize declared links in
    # memory. Auto-package precedence then sees the same occupied pairs as a
    # real build without writing any files.
    link_report = apply_spec_links(G, spec, dry_run=False)
    if spec.auto_packages:
        apply_auto_package_links(G, spec, link_report, dry_run=False)
    report.edges_added = link_report.edges_added
    report.auto_package_edges = link_report.auto_package_edges
    report.hubs_added = link_report.hubs_added
    report.nodes_created = link_report.nodes_created
    report.resolved = link_report.resolved
    report.warnings.extend(link_report.warnings)
    report.errors.extend(link_report.errors)
    return report, report.errors
