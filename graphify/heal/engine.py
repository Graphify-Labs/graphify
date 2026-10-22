import json
import re
import subprocess
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional
import networkx as nx

class FailureTarget(NamedTuple):
    test_file: str
    test_node: str
    error_message: str

def execute_and_capture_test_failure(test_cmd: str) -> List[FailureTarget]:
    """Runs the test suite and captures failing test signatures."""
    result = subprocess.run(
        test_cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    if result.returncode == 0:
        return []

    failures = []
    pattern = re.compile(r"FAILED\s+([^:]+)::([^\s]+)\s*(?:-\s*(.*))?")
    output = result.stdout + "\n" + result.stderr
    for line in output.splitlines():
        match = pattern.search(line)
        if match:
            failures.append(
                FailureTarget(
                    test_file=match.group(1).strip(),
                    test_node=match.group(2).strip(),
                    error_message=match.group(3).strip() if match.group(3) else "AssertionError"
                )
            )
    return failures

def build_nx_graph_from_graphify(graph_json_path: Path) -> nx.DiGraph:
    """Loads a Graphify graph.json into a NetworkX directed graph."""
    with open(graph_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return nx.node_link_graph(data, directed=True, multigraph=False)

def extract_blast_radius_subgraph(
    G: nx.DiGraph,
    target_file: str,
    depth: int = 2
) -> Dict:
    """Slices an ego-subgraph around the affected source file with path normalization."""
    target_p = Path(target_file).resolve()
    target_name = target_p.name

    seed_nodes = []
    for n, attrs in G.nodes(data=True):
        src_attr = attrs.get("source_file", "")
        if src_attr:
            src_p = Path(src_attr).resolve()
            if src_p == target_p or src_p.name == target_name:
                seed_nodes.append(n)
                continue
        node_str = str(n)
        if str(target_p) in node_str or target_name in node_str:
            seed_nodes.append(n)

    if not seed_nodes:
        return {}

    subgraph_nodes = set(seed_nodes)
    for seed in seed_nodes:
        subgraph_nodes.update(nx.single_source_shortest_path_length(G.reverse(), seed, cutoff=depth).keys())
        subgraph_nodes.update(nx.single_source_shortest_path_length(G, seed, cutoff=depth).keys())

    subgraph = G.subgraph(subgraph_nodes)
    return {
        "focal_file": target_file,
        "nodes": [
            {
                "id": str(n),
                "label": attrs.get("label", str(n)),
                "type": attrs.get("node_type", "symbol"),
                "file": attrs.get("source_file", "")
            }
            for n, attrs in subgraph.nodes(data=True)
        ],
        "relationships": [
            {
                "source": str(u),
                "target": str(v),
                "relation": attrs.get("relation", "CALLS")
            }
            for u, v, attrs in subgraph.edges(data=True)
        ]
    }

def build_healing_prompt(target: FailureTarget, graph_context: Dict, source_code: str) -> str:
    """Constructs the prompt containing failure details, graph topology, and source code."""
    nodes_lines = "\n".join(
        f"- {n['type']} '{n['label']}' ({n['file']})"
        for n in graph_context.get("nodes", [])
    ) or "No graph neighbors found."

    edges_lines = "\n".join(
        f"- {e['source']} --[{e['relation']}]--> {e['target']}"
        for e in graph_context.get("relationships", [])
    ) or "No direct relationships found."

    sections = [
        "### Task: Autonomous AST Code Remediation",
        "You are fixing a regression in a codebase indexed by an architectural knowledge graph.",
        "",
        "### Failing Test",
        f"Target: {target.test_file}::{target.test_node}",
        f"Error: {target.error_message}",
        "",
        "### Architectural Context (Blast Radius)",
        "Connected components:",
        nodes_lines,
        "",
        "Component relationships:",
        edges_lines,
        "",
        f"### Target File: {target.test_file}",
        "```python",
        source_code,
        "```",
        "",
        "Instructions:",
        "1. Fix the bug causing the failure without breaking dependent interfaces.",
        "2. Return ONLY the complete updated file content inside a single ```python code block.",
    ]
    return "\n".join(sections)

def extract_code_patch(llm_response: str) -> str:
    """Extracts raw code from an LLM response containing markdown fences."""
    pattern = re.compile(r"```(?:python)?\s*\n(.*?)\n```", re.DOTALL)
    match = pattern.search(llm_response)
    if match:
        return match.group(1).rstrip() + "\n"
    return llm_response.strip() + "\n"

def apply_patch_to_file(file_path: Path, new_code: str) -> None:
    """Overwrites the target file with the synthesized patch."""
    file_path.write_text(new_code, encoding="utf-8")
