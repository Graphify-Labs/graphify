"""graphify ci-select: Graph-informed CI test selection.

Uses the graphify knowledge graph to determine which CI tests to run
for a given set of code changes. BFS traversal up to N hops from changed
files, then maps reachable nodes to CI job names via a test-jobs.yaml mapping.
"""
from __future__ import annotations

import fnmatch
import json
import subprocess
import sys
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import networkx as nx


@dataclass
class TestPlan:
    must_run: list[str] = field(default_factory=list)
    should_run: list[str] = field(default_factory=list)
    skip: list[str] = field(default_factory=list)
    cross_repo: list[dict[str, Any]] = field(default_factory=list)
    reasoning: str = ""
    confidence: float = 1.0
    graph_paths: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_plan": {
                "must_run": self.must_run,
                "should_run": self.should_run,
                "skip": self.skip,
                "cross_repo": self.cross_repo,
            },
            "reasoning": self.reasoning,
            "confidence": self.confidence,
            "graph_paths": self.graph_paths,
            "warnings": self.warnings,
        }


def load_graph(graph_path: str | Path) -> nx.Graph:
    """Load a graphify graph.json into a NetworkX graph."""
    from networkx.readwrite import json_graph

    path = Path(graph_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Graph file not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if "links" not in raw and "edges" in raw:
        raw = dict(raw, links=raw["edges"])
    raw = {**raw, "directed": True}
    try:
        return json_graph.node_link_graph(raw, edges="links")
    except TypeError:
        return json_graph.node_link_graph(raw)


def parse_diff_files(diff_text: str) -> list[str]:
    """Extract changed file paths from a unified diff."""
    files: list[str] = []
    for line in diff_text.splitlines():
        if line.startswith("diff --git"):
            # diff --git a/path/to/file b/path/to/file
            parts = line.split()
            if len(parts) >= 4:
                path = parts[3]
                if path.startswith("b/"):
                    path = path[2:]
                if path not in files:
                    files.append(path)
        elif line.startswith("+++ b/"):
            path = line[6:]
            if path not in files:
                files.append(path)
    return files


def load_test_jobs(yaml_path: str | Path) -> dict[str, dict[str, Any]]:
    """Load test-jobs.yaml mapping file.

    Returns dict of job_name -> {"graph_patterns": [...], "description": "..."}
    """
    path = Path(yaml_path)
    if not path.exists():
        return {}

    try:
        import yaml  # type: ignore[import-untyped]
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except ImportError:
        data = _parse_simple_yaml(path.read_text(encoding="utf-8"))

    if not isinstance(data, dict):
        return {}

    # The YAML has repo_name -> jobs -> job_name -> {graph_patterns, description}
    # Flatten to just job_name -> config
    jobs: dict[str, dict[str, Any]] = {}
    for _repo_key, repo_val in data.items():
        if isinstance(repo_val, dict) and "jobs" in repo_val:
            for job_name, job_config in repo_val["jobs"].items():
                jobs[job_name] = job_config
        elif isinstance(repo_val, dict):
            for job_name, job_config in repo_val.items():
                if isinstance(job_config, dict):
                    jobs[job_name] = job_config
    return jobs


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Minimal YAML-like parser for test-jobs.yaml format.

    Only handles the specific nested-dict + list-of-strings structure we use.
    Falls back gracefully when pyyaml is unavailable.
    """
    import re

    result: dict[str, Any] = {}
    stack: list[tuple[int, dict]] = [(-1, result)]

    for line in text.splitlines():
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(line) - len(stripped)

        # Pop stack to find parent at correct indent level
        while len(stack) > 1 and stack[-1][0] >= indent:
            stack.pop()

        parent = stack[-1][1]

        # List item: "- value"
        if stripped.startswith("- "):
            val = stripped[2:].strip().strip('"').strip("'")
            if isinstance(parent, dict):
                for k in reversed(list(parent.keys())):
                    if parent[k] is None or isinstance(parent[k], list):
                        if parent[k] is None:
                            parent[k] = []
                        parent[k].append(val)
                        break
            continue

        # Key-value or key-only
        m = re.match(r"^([^:]+):\s*(.*)", stripped)
        if m:
            key = m.group(1).strip()
            value = m.group(2).strip().strip('"').strip("'")
            if value:
                parent[key] = value
            else:
                new_dict: dict[str, Any] = {}
                parent[key] = new_dict
                stack.append((indent, new_dict))

    return result


def find_nodes_for_file(
    G: nx.Graph, file_path: str, repo: str
) -> list[str]:
    """Find graph nodes that correspond to a given file path.

    Tries multiple matching strategies:
    1. Exact source_file match (with repo prefix)
    2. Exact source_file match (without repo prefix)
    3. source_file ends with the path
    """
    candidates: list[str] = []
    repo_prefixed = f"{repo}/{file_path}"

    for node_id, data in G.nodes(data=True):
        source_file = data.get("source_file", "")
        if not source_file:
            continue
        if source_file == repo_prefixed or source_file == file_path:
            candidates.append(node_id)
        elif source_file.endswith("/" + file_path):
            candidates.append(node_id)

    return candidates


def bfs_reachable(
    G: nx.Graph, seeds: list[str], max_depth: int = 3
) -> dict[str, int]:
    """BFS from seed nodes, returning reachable node_id -> depth.

    Traverses both incoming and outgoing edges (undirected BFS on a
    directed graph) to find all structurally connected code.
    """
    visited: dict[str, int] = {}
    queue: deque[tuple[str, int]] = deque()

    for seed in seeds:
        if seed not in visited:
            visited[seed] = 0
            queue.append((seed, 0))

    while queue:
        current, depth = queue.popleft()
        if depth >= max_depth:
            continue

        neighbors: set[str] = set()
        for _, target in G.out_edges(current):
            neighbors.add(str(target))
        for source, _ in G.in_edges(current):
            neighbors.add(str(source))

        for neighbor in neighbors:
            if neighbor not in visited:
                visited[neighbor] = depth + 1
                queue.append((neighbor, depth + 1))

    return visited


def match_patterns(
    file_paths: list[str], patterns: list[str]
) -> int:
    """Count how many file paths match any of the glob patterns."""
    count = 0
    for fp in file_paths:
        for pat in patterns:
            if fnmatch.fnmatch(fp, pat):
                count += 1
                break
    return count


def find_neighbors_summary(G: nx.Graph, node_ids: list[str]) -> str:
    """Summarize what a set of nodes connects to."""
    labels: list[str] = []
    seen: set[str] = set()
    for nid in node_ids:
        for _, target in G.out_edges(nid):
            target = str(target)
            if target not in seen:
                seen.add(target)
                data = G.nodes.get(target, {})
                label = data.get("label", target)
                labels.append(str(label))
    if len(labels) > 3:
        return f"{', '.join(labels[:3])} (+{len(labels) - 3} more)"
    return ", ".join(labels) if labels else "(no connections)"


def ci_select(
    graph_path: str | Path,
    changed_files: list[str],
    repo: str,
    test_jobs_path: str | Path | None = None,
    max_depth: int = 3,
) -> TestPlan:
    """Main entry point: determine which CI tests to run.

    Args:
        graph_path: Path to graph.json
        changed_files: List of repo-relative file paths that changed
        repo: Repository name (e.g. "fulfillment-service")
        test_jobs_path: Path to test-jobs.yaml mapping file
        max_depth: BFS traversal depth (default 3)

    Returns:
        TestPlan with categorized test jobs
    """
    plan = TestPlan()

    if not changed_files:
        plan.confidence = 1.0
        plan.reasoning = "No files changed."
        return plan

    # Load graph
    G = load_graph(graph_path)

    # Find seed nodes for changed files
    all_seeds: list[str] = []
    unknown_files: list[str] = []
    file_to_nodes: dict[str, list[str]] = {}

    for f in changed_files:
        nodes = find_nodes_for_file(G, f, repo)
        if nodes:
            all_seeds.extend(nodes)
            file_to_nodes[f] = nodes
        else:
            unknown_files.append(f)

    # Confidence calculation
    if not all_seeds:
        plan.confidence = 0.0
        plan.reasoning = (
            f"None of the {len(changed_files)} changed files have graph nodes. "
            "Falling back to full test suite."
        )
        plan.warnings.append(
            f"Unknown files: {', '.join(unknown_files[:10])}"
            + (
                f" (and {len(unknown_files) - 10} more)"
                if len(unknown_files) > 10
                else ""
            )
        )
        return plan

    if unknown_files:
        known_ratio = len(file_to_nodes) / len(changed_files)
        plan.confidence = max(0.3, known_ratio * 0.9)
        plan.warnings.append(
            f"{len(unknown_files)} changed file(s) not in graph: "
            + ", ".join(unknown_files[:5])
            + (
                f" (and {len(unknown_files) - 5} more)"
                if len(unknown_files) > 5
                else ""
            )
        )
    else:
        plan.confidence = 0.9

    # BFS traversal from seed nodes
    reachable = bfs_reachable(G, all_seeds, max_depth=max_depth)

    # Collect source files of reachable nodes
    reachable_files: list[str] = []
    cross_repo_files: dict[str, list[str]] = {}

    for node_id in reachable:
        data = G.nodes.get(node_id, {})
        source_file = data.get("source_file", "")
        if not source_file:
            continue

        parts = source_file.split("/", 1)
        if len(parts) == 2:
            node_repo = parts[0]
            node_file = parts[1]
        else:
            node_repo = repo
            node_file = source_file

        if node_repo == repo:
            if node_file not in reachable_files:
                reachable_files.append(node_file)
        else:
            cross_repo_files.setdefault(node_repo, [])
            if node_file not in cross_repo_files[node_repo]:
                cross_repo_files[node_repo].append(node_file)

    # Load test jobs mapping
    jobs: dict[str, dict[str, Any]] = {}
    if test_jobs_path:
        jobs = load_test_jobs(test_jobs_path)

    if not jobs:
        plan.reasoning = (
            f"BFS from {len(all_seeds)} seed nodes reached {len(reachable)} nodes "
            f"across {len(reachable_files)} files in {repo}. "
            f"No test-jobs.yaml mapping found -- cannot map to CI jobs."
        )
        if cross_repo_files:
            for cr_repo, cr_files in cross_repo_files.items():
                plan.cross_repo.append(
                    {
                        "repo": cr_repo,
                        "files_affected": len(cr_files),
                        "tests": [],
                    }
                )
        for f, nodes in list(file_to_nodes.items())[:5]:
            plan.graph_paths.append(
                f"{f} -> {find_neighbors_summary(G, nodes)}"
            )
        return plan

    # Map reachable files to CI jobs
    all_matchable = list(set(reachable_files + changed_files))
    job_match_counts: dict[str, int] = {}

    for job_name, job_config in jobs.items():
        patterns = job_config.get("graph_patterns", [])
        if isinstance(patterns, str):
            patterns = [patterns]
        count = match_patterns(all_matchable, patterns)
        job_match_counts[job_name] = count

    # Categorize: 3+ matches = must_run, 1-2 = should_run, 0 = skip
    all_job_names = list(jobs.keys())
    for job_name in all_job_names:
        count = job_match_counts.get(job_name, 0)
        if count >= 3:
            plan.must_run.append(job_name)
        elif count >= 1:
            plan.should_run.append(job_name)
        else:
            plan.skip.append(job_name)

    # Cross-repo analysis
    if cross_repo_files:
        for cr_repo, cr_files in cross_repo_files.items():
            cr_tests: list[str] = []
            cr_mapping_path = None
            if test_jobs_path:
                parent = Path(test_jobs_path).parent.parent
                candidate = parent / cr_repo / "test-jobs.yaml"
                if candidate.exists():
                    cr_mapping_path = candidate

            if cr_mapping_path:
                cr_jobs = load_test_jobs(cr_mapping_path)
                for cj_name, cj_config in cr_jobs.items():
                    cr_patterns = cj_config.get("graph_patterns", [])
                    if isinstance(cr_patterns, str):
                        cr_patterns = [cr_patterns]
                    if match_patterns(cr_files, cr_patterns) > 0:
                        cr_tests.append(cj_name)

            plan.cross_repo.append(
                {
                    "repo": cr_repo,
                    "tests": cr_tests,
                    "files_affected": len(cr_files),
                }
            )

    # Build reasoning
    reasoning_parts = [
        f"BFS from {len(all_seeds)} seed nodes (depth {max_depth}) "
        f"reached {len(reachable)} nodes.",
    ]
    if plan.must_run:
        reasoning_parts.append(f"Must run: {', '.join(plan.must_run)}.")
    if plan.should_run:
        reasoning_parts.append(f"Should run: {', '.join(plan.should_run)}.")
    if plan.skip:
        reasoning_parts.append(f"Skip: {', '.join(plan.skip)}.")
    if plan.cross_repo:
        for cr in plan.cross_repo:
            reasoning_parts.append(
                f"Cross-repo impact on {cr['repo']}: "
                f"{cr['files_affected']} files affected."
            )
    plan.reasoning = " ".join(reasoning_parts)

    # Graph paths for traceability
    for f, nodes in list(file_to_nodes.items())[:5]:
        summary = find_neighbors_summary(G, nodes)
        plan.graph_paths.append(f"{f} -> {summary}")

    # Confidence adjustment
    if plan.confidence >= 0.5 and not plan.must_run and not plan.should_run:
        plan.confidence = min(plan.confidence, 0.6)
        plan.warnings.append(
            "No jobs matched despite valid graph nodes -- "
            "verify test-jobs.yaml patterns"
        )

    return plan


def cli_main(argv: list[str] | None = None) -> None:
    """CLI entry point for ``graphify ci-select``."""
    args = argv if argv is not None else sys.argv[2:]

    graph_path = "graphify-out/graph.json"
    repo = ""
    diff_cmd = ""
    files_str = ""
    test_jobs = ""
    max_depth = 3

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--graph" and i + 1 < len(args):
            graph_path = args[i + 1]
            i += 2
        elif arg.startswith("--graph="):
            graph_path = arg.split("=", 1)[1]
            i += 1
        elif arg == "--repo" and i + 1 < len(args):
            repo = args[i + 1]
            i += 2
        elif arg.startswith("--repo="):
            repo = arg.split("=", 1)[1]
            i += 1
        elif arg == "--diff-cmd" and i + 1 < len(args):
            diff_cmd = args[i + 1]
            i += 2
        elif arg.startswith("--diff-cmd="):
            diff_cmd = arg.split("=", 1)[1]
            i += 1
        elif arg == "--files" and i + 1 < len(args):
            files_str = args[i + 1]
            i += 2
        elif arg.startswith("--files="):
            files_str = arg.split("=", 1)[1]
            i += 1
        elif arg == "--test-jobs" and i + 1 < len(args):
            test_jobs = args[i + 1]
            i += 2
        elif arg.startswith("--test-jobs="):
            test_jobs = arg.split("=", 1)[1]
            i += 1
        elif arg == "--depth" and i + 1 < len(args):
            try:
                max_depth = int(args[i + 1])
            except ValueError:
                print("error: --depth must be an integer", file=sys.stderr)
                sys.exit(1)
            i += 2
        elif arg.startswith("--depth="):
            try:
                max_depth = int(arg.split("=", 1)[1])
            except ValueError:
                print("error: --depth must be an integer", file=sys.stderr)
                sys.exit(1)
            i += 1
        elif arg == "--diff" and i + 1 < len(args):
            diff_path = args[i + 1]
            i += 2
            if diff_path == "-":
                diff_text = sys.stdin.read()
            else:
                diff_text = Path(diff_path).read_text(encoding="utf-8")
            files_str = ",".join(parse_diff_files(diff_text))
        elif arg.startswith("--diff="):
            diff_path = arg.split("=", 1)[1]
            i += 1
            if diff_path == "-":
                diff_text = sys.stdin.read()
            else:
                diff_text = Path(diff_path).read_text(encoding="utf-8")
            files_str = ",".join(parse_diff_files(diff_text))
        else:
            i += 1

    if not repo:
        print("error: --repo is required", file=sys.stderr)
        sys.exit(1)

    # Get changed files
    changed_files: list[str] = []
    if diff_cmd:
        try:
            result = subprocess.run(
                diff_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            changed_files = parse_diff_files(result.stdout)
        except subprocess.TimeoutExpired:
            print("error: diff command timed out", file=sys.stderr)
            sys.exit(1)
    elif files_str:
        changed_files = [f.strip() for f in files_str.split(",") if f.strip()]
    else:
        if not sys.stdin.isatty():
            diff_text = sys.stdin.read()
            changed_files = parse_diff_files(diff_text)
        else:
            print(
                "error: provide changed files via --diff-cmd, --diff, "
                "--files, or stdin",
                file=sys.stderr,
            )
            sys.exit(1)

    # Auto-detect test-jobs.yaml if not specified
    if not test_jobs:
        candidates = [
            Path(repo) / "test-jobs.yaml",
            Path("test-jobs.yaml"),
        ]
        for c in candidates:
            if c.exists():
                test_jobs = str(c)
                break

    plan = ci_select(
        graph_path=graph_path,
        changed_files=changed_files,
        repo=repo,
        test_jobs_path=test_jobs or None,
        max_depth=max_depth,
    )

    print(json.dumps(plan.to_dict(), indent=2))
