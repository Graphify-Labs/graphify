"""CLI for cluster graphs (multi-repo): `graphify cluster <subcommand>`.

Delegated from cli.dispatch_command in the same style as `graphify prs`.
For community detection on a single graph, see `cluster-only` / `--no-cluster`.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .cluster_graph import (
    ClusterMember,
    ClusterSpec,
    ClusterSpecError,
    build_cluster,
    check_cluster,
    cluster_out_dir,
    find_spec_file,
    load_local_config,
    load_spec,
    member_graph_path,
    normalize_git_url,
    origin_url,
    resolve_all_members,
    resolve_member_path,
    save_local_config,
    save_spec,
    validate_member_tag,
)

USAGE = """\
Usage: graphify cluster <subcommand>

Manage cluster graphs: link multiple repos' graphs into one connected graph.
(For community detection on a single graph, see `graphify cluster-only`.)

Subcommands:
  init [DIR] --name NAME       create a cluster spec skeleton
  add <repo-path-or-url> [--as TAG] [--dir DIR]
                               add a member repo to the spec
  remove <TAG> [--dir DIR]     remove a member from the spec
  locate <TAG> <PATH> [--dir DIR]
                               record a machine-local checkout path override
  build [--dir DIR] [--force] [--no-links] [--no-refs]
                               compose member graphs + resolve declared links
                               (writes a cluster-ref.json back-reference into
                               each member's graphify-out/ unless --no-refs)
  check [--dir DIR]            validate spec and dry-run link resolution
  status [--dir DIR]           members, resolution, staleness vs last build

The cluster graph is written to <DIR>/graphify-out/graph.json, so query/path/
explain/affected/export all work from inside the cluster directory (or via
--graph). Declare cross-repo links in cluster.json; see README for the format.
"""


def _fail(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def _take_flag_value(args: list[str], i: int, flag: str) -> tuple[str, int]:
    """Consume ``--flag VALUE`` or ``--flag=VALUE`` at args[i].

    A missing value (end of args, empty ``=`` form, or another ``--option``
    next) is a hard error — falling through would turn the next token (or the
    flag itself, in the caller's positional handling) into a positional and
    silently do the wrong thing, e.g. `cluster init --name` creating a
    directory literally named ``--name``.
    """
    a = args[i]
    if a.startswith(flag + "="):
        value = a.split("=", 1)[1]
        if not value:
            _fail(f"{flag} requires a value")
        return value, i + 1
    if i + 1 >= len(args) or args[i + 1].startswith("--"):
        _fail(f"{flag} requires a value")
    return args[i + 1], i + 2


def _parse_dir(args: list[str]) -> tuple[Path, list[str]]:
    """Pop --dir DIR (default: cwd) from args."""
    rest: list[str] = []
    cluster_dir = Path(".")
    i = 0
    while i < len(args):
        if args[i] == "--dir" or args[i].startswith("--dir="):
            value, i = _take_flag_value(args, i, "--dir")
            cluster_dir = Path(value)
        else:
            rest.append(args[i])
            i += 1
    return cluster_dir, rest


def _reject_unknown_flags(rest: list[str], usage: str) -> None:
    unknown = [a for a in rest if a.startswith("--")]
    if unknown:
        _fail(f"unknown option {unknown[0]!r} (usage: {usage})")


def _looks_like_url(s: str) -> bool:
    return "://" in s or (s.startswith("git@") and ":" in s)


def _cmd_init(args: list[str]) -> None:
    usage = "graphify cluster init [DIR] --name NAME"
    cluster_dir, rest = _parse_dir(args)
    name = ""
    positional: list[str] = []
    i = 0
    while i < len(rest):
        if rest[i] == "--name" or rest[i].startswith("--name="):
            name, i = _take_flag_value(rest, i, "--name")
        elif rest[i].startswith("--"):
            _fail(f"unknown option {rest[i]!r} (usage: {usage})")
        else:
            positional.append(rest[i])
            i += 1
    if len(positional) > 1:
        _fail(f"usage: {usage}")
    if positional:
        cluster_dir = Path(positional[0])
    cluster_dir.mkdir(parents=True, exist_ok=True)
    if find_spec_file(cluster_dir):
        _fail(f"a cluster spec already exists in {cluster_dir}")
    spec = ClusterSpec(name=name or cluster_dir.resolve().name)
    target = save_spec(spec, cluster_dir)

    # Keep machine-local files and build output out of a committed cluster dir.
    gitignore = cluster_dir / ".gitignore"
    wanted = ["cluster.local.*", "graphify-out/"]
    existing = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.is_file() else []
    missing = [w for w in wanted if w not in existing]
    if missing:
        from .paths import write_text_atomic
        write_text_atomic(gitignore, "\n".join(existing + missing) + "\n")

    print(f"Initialized cluster '{spec.name}' at {target}")
    print("Next: graphify cluster add <repo-path> [--as TAG]")


def _cmd_add(args: list[str]) -> None:
    usage = "graphify cluster add <repo-path-or-url> [--as TAG] [--dir DIR]"
    cluster_dir, rest = _parse_dir(args)
    tag = ""
    positional = []
    i = 0
    while i < len(rest):
        if rest[i] == "--as" or rest[i].startswith("--as="):
            tag, i = _take_flag_value(rest, i, "--as")
        elif rest[i].startswith("--"):
            _fail(f"unknown option {rest[i]!r} (usage: {usage})")
        else:
            positional.append(rest[i])
            i += 1
    if len(positional) != 1:
        _fail(f"usage: {usage}")
    target = positional[0]

    spec = load_spec(cluster_dir)
    if _looks_like_url(target):
        url, path = target, ""
        default_tag = normalize_git_url(url).rstrip("/").rsplit("/", 1)[-1]
    else:
        repo_dir = Path(target).expanduser()
        if not repo_dir.is_dir():
            _fail(f"not a directory: {repo_dir}")
        # Make the input independent of the invocation cwd without resolving
        # symlinks; member path resolution deliberately preserves user-written
        # symlinked checkout layouts.
        repo_dir = Path(os.path.abspath(repo_dir))
        if repo_dir == Path(os.path.abspath(cluster_dir)):
            _fail(
                "cannot add the cluster directory as its own member; a cluster "
                "composes OTHER repos' graphs (run this from the cluster dir "
                "and pass the member repo's path)"
            )
        url = origin_url(repo_dir) or ""
        try:
            # abspath (not resolve) on BOTH sides: the hint is later re-joined
            # against the unresolved cluster dir with normpath, so `..` hops
            # computed against a symlink-resolved base would land in the wrong
            # tree (e.g. macOS /tmp -> /private/tmp).
            path = os.path.relpath(repo_dir, os.path.abspath(cluster_dir))
        except ValueError:  # Windows cross-drive paths cannot be relative.
            path = str(repo_dir)
        default_tag = repo_dir.name
        if not url:
            print(
                f"warning: {repo_dir} has no origin remote; this member will only "
                f"resolve via its recorded path",
                file=sys.stderr,
            )
    tag = tag or default_tag
    if tag in spec.tags():
        _fail(f"member tag '{tag}' already exists (use --as to pick another)")
    try:
        validate_member_tag(tag, where=spec.spec_path.name if spec.spec_path else "cluster spec")
    except ClusterSpecError as exc:
        _fail(str(exc))

    spec.members.append(ClusterMember(tag=tag, url=url, path=path))
    save_spec(spec, cluster_dir)
    print(f"Added member '{tag}'" + (f" ({url})" if url else ""))


def _cmd_remove(args: list[str]) -> None:
    cluster_dir, rest = _parse_dir(args)
    _reject_unknown_flags(rest, "graphify cluster remove <TAG> [--dir DIR]")
    if len(rest) != 1:
        _fail("usage: graphify cluster remove <TAG> [--dir DIR]")
    tag = rest[0]
    spec = load_spec(cluster_dir)
    if tag not in spec.tags():
        _fail(f"no member with tag '{tag}'")
    referencing = [
        i for i, l in enumerate(spec.links)
        for sel in ([l.from_, l.to] if l.from_ else []) + l.referents
        if sel and sel["repo"] == tag
    ]
    if referencing:
        _fail(
            f"member '{tag}' is referenced by links {sorted(set(referencing))}; "
            f"remove or update those links first"
        )
    # Resolve before mutating the spec so this cluster's membership can be
    # removed from the member marker too; cleanup never blocks removal.
    member = next(m for m in spec.members if m.tag == tag)
    resolved_path, _warnings = resolve_member_path(member, cluster_dir, load_local_config(cluster_dir))
    spec.members = [m for m in spec.members if m.tag != tag]
    save_spec(spec, cluster_dir)
    print(f"Removed member '{tag}'")
    if resolved_path is not None:
        from .cluster_ref import (
            CLUSTER_REF_NAME,
            CLUSTER_REF_VERSION,
            load_cluster_refs,
        )
        from .paths import GRAPHIFY_OUT_NAME, write_json_atomic

        out_dir = resolved_path / GRAPHIFY_OUT_NAME
        marker = out_dir / CLUSTER_REF_NAME
        try:
            if marker.is_file():
                refs = [
                    ref for ref in load_cluster_refs(out_dir)
                    if ref["cluster_name"] != spec.name
                ]
                if refs:
                    write_json_atomic(
                        marker,
                        {"version": CLUSTER_REF_VERSION, "clusters": refs},
                        indent=2,
                    )
                    print(f"  also removed its '{spec.name}' membership")
                else:
                    marker.unlink()
                    print(f"  also removed its {CLUSTER_REF_NAME} marker")
        except OSError as exc:
            print(f"  note: could not remove {marker}: {exc}", file=sys.stderr)
    else:
        print(
            f"  note: could not resolve '{tag}' locally; its cluster-ref.json "
            f"(if any) was left in place",
            file=sys.stderr,
        )


def _cmd_locate(args: list[str]) -> None:
    cluster_dir, rest = _parse_dir(args)
    _reject_unknown_flags(rest, "graphify cluster locate <TAG> <PATH> [--dir DIR]")
    if len(rest) != 2:
        _fail("usage: graphify cluster locate <TAG> <PATH> [--dir DIR]")
    tag, path_str = rest
    spec = load_spec(cluster_dir)
    if tag not in spec.tags():
        _fail(f"no member with tag '{tag}'")
    path = Path(path_str).expanduser()
    if not path.is_dir():
        _fail(f"not a directory: {path}")
    member = next(m for m in spec.members if m.tag == tag)
    if member.url:
        found = origin_url(path)
        if found and normalize_git_url(found) != normalize_git_url(member.url):
            print(
                f"warning: {path} has origin {found!r}, but the spec declares "
                f"{member.url!r} for '{tag}'",
                file=sys.stderr,
            )
    cfg = load_local_config(cluster_dir)
    cfg.setdefault("paths", {})[tag] = str(path.resolve())
    target = save_local_config(cluster_dir, cfg)
    print(f"Recorded {tag} -> {path.resolve()} in {target.name}")


def _cmd_build(args: list[str]) -> None:
    cluster_dir, rest = _parse_dir(args)
    force = "--force" in rest
    no_links = "--no-links" in rest
    no_refs = "--no-refs" in rest
    unknown = [a for a in rest if a not in ("--force", "--no-links", "--no-refs")]
    if unknown:
        _fail(f"unknown arguments: {' '.join(unknown)}")
    summary = build_cluster(cluster_dir, force=force, no_links=no_links, write_refs=not no_refs)
    if summary["skipped"]:
        print(f"Cluster '{summary['name']}' unchanged; skipped (use --force to rebuild)")
        if summary.get("refs_written"):
            print(f"  cluster-refs: backfilled {summary['refs_written']} member marker(s)")
        return
    report = summary["links"]
    members = summary["members"]
    print(
        f"Cluster '{summary['name']}': {len(members)} members -> "
        f"{summary['nodes']} nodes, {summary['edges']} edges"
    )
    print(f"  links: {report.edges_added} edges, {report.hubs_added} shared-resource hubs")
    if report.auto_package_edges:
        print(f"  automatic package links: {report.auto_package_edges}")
    if report.nodes_created:
        print(f"  created {len(report.nodes_created)} concept nodes (on_missing: create)")
    if not no_refs:
        print(f"  cluster-refs: wrote {summary.get('refs_written', 0)} member marker(s)")
    print(f"Written to: {summary['out']}")
    print(f"Query it with: cd {cluster_dir} && graphify query \"...\"")


def _cmd_check(args: list[str]) -> None:
    cluster_dir, rest = _parse_dir(args)
    if rest:
        _fail(f"unknown arguments: {' '.join(rest)}")
    report, errors = check_cluster(cluster_dir)
    for r in report.resolved:
        print(f"  ok: {r}")
    for w in report.warnings:
        print(f"  warning: {w}")
    for e in errors:
        print(f"  error: {e}", file=sys.stderr)
    if errors:
        sys.exit(1)
    print(
        f"Spec OK: {report.edges_added} edges "
        f"({report.auto_package_edges} automatic package), "
        f"{report.hubs_added} hubs would be created"
    )


def _cmd_status(args: list[str]) -> None:
    cluster_dir, rest = _parse_dir(args)
    if rest:
        _fail(f"unknown arguments: {' '.join(rest)}")
    spec = load_spec(cluster_dir)
    local_cfg = load_local_config(cluster_dir)
    resolved, warnings, errors = resolve_all_members(spec, cluster_dir, local_cfg)

    manifest = {}
    manifest_path = cluster_out_dir(cluster_dir) / "cluster-manifest.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    built = manifest.get("members") or {}

    print(
        f"Cluster '{spec.name}' ({len(spec.members)} members, "
        f"{len(spec.links)} links, graph mode: {spec.graph_mode})"
    )
    from .cluster_graph import _file_hash
    for member in spec.members:
        path = resolved.get(member.tag)
        if path is None:
            print(f"  {member.tag}: UNRESOLVED" + (f" ({member.url})" if member.url else ""))
            continue
        gp = member_graph_path(member, path)
        if not gp.is_file():
            state = "no graph (run graphify extract there)"
        elif member.tag not in built:
            state = "not in last build"
        elif built[member.tag].get("source_hash") != _file_hash(gp):
            state = "stale (graph changed since last build)"
        else:
            state = f"ok ({built[member.tag].get('node_count', '?')} nodes)"
        print(f"  {member.tag}: {path} — {state}")
    for w in warnings:
        print(f"  warning: {w}", file=sys.stderr)
    for e in errors:
        print(f"  error: {e}", file=sys.stderr)
    if manifest:
        print(f"Last build: {manifest.get('built_at', '?')} — "
              f"{manifest.get('node_count', '?')} nodes, {manifest.get('edge_count', '?')} edges")
    sys.exit(1 if errors else 0)


def cmd_cluster(argv: list[str]) -> None:
    sub = argv[0] if argv else ""
    # Help tokens ANYWHERE in argv print USAGE and stop — `cluster init --help`
    # must never fall through to a handler and mkdir/init as a side effect.
    # (This dispatcher is exempted from __main__'s universal help guard so the
    # user gets the cluster USAGE instead of the generic pointer.)
    help_requested = sub in ("", "help") or any(
        a in ("-h", "--help", "-?") for a in argv
    )
    handlers = {
        "init": _cmd_init,
        "add": _cmd_add,
        "remove": _cmd_remove,
        "locate": _cmd_locate,
        "build": _cmd_build,
        "check": _cmd_check,
        "status": _cmd_status,
    }
    if help_requested:
        print(USAGE)
        sys.exit(0)
    handler = handlers.get(sub)
    if handler is None:
        print(USAGE, file=sys.stderr)
        sys.exit(1)
    try:
        handler(argv[1:])
    except ClusterSpecError as exc:
        _fail(str(exc))
