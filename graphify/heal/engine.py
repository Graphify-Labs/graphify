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
    """Runs the test suite and captures failing test signatures.
    
    Guards against silent failures: if the exit code is non-zero but no
    regex matches, captures the failure as a general suite error.
    """
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
    output = (result.stdout or "") + "\n" + (result.stderr or "")
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

    # Finding 3 fix: Non-zero exit with no matched FAILED lines must not read as success
    if not failures and result.returncode != 0:
        clean_err = (result.stderr or result.stdout or "Non-zero exit without pytest failure output").strip()
        first_line = clean_err.splitlines()[-1] if clean_err else "Command execution error"
        failures.append(
            FailureTarget(
                test_file="suite",
                test_node="execution_error",
                error_message=first_line
            )
        )

    return failures

def build_nx_graph_from_graphify(graph_json_path: Path) -> nx.DiGraph:
    """Loads a Graphify graph.json into a NetworkX directed graph."""
    with open(graph_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    G = nx.node_link_graph(data, directed=True, multigraph=False)
    if not G.is_directed():
        G = G.to_directed()
    return G

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
    is_directed = G.is_directed()

    # Finding 5 fix: Check is_directed before reversing
    for seed in seed_nodes:
        if is_directed:
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

def resolve_remediation_target(target_fail: FailureTarget, blast_slice: Dict) -> Path:
    """Finding 2 fix: Prioritizes patching implementation code over test harness."""
    test_path = Path(target_fail.test_file).resolve()
    
    # Check if graph slice contains a connected non-test implementation file
    candidates = []
    for n in blast_slice.get("nodes", []):
        f = n.get("file", "")
        if f:
            p = Path(f).resolve()
            if p.exists() and p != test_path and not p.name.startswith("test_") and "test" not in p.parts:
                candidates.append(p)

    if candidates:
        return candidates[0]
    return test_path

def build_healing_prompt(target: FailureTarget, graph_context: Dict, source_code: str, target_filename: str) -> str:
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
        f"### Target File Under Remediation: {target_filename}",
        "```python",
        source_code,
        "```",
        "",
        "Instructions:",
        "1. Fix the bug causing the failure without breaking dependent interfaces.",
        "2. Return ONLY the complete updated file content inside a single ```python code block.",
        "3. Do not return conversational explanations outside the code fence.",
    ]
    return "\n".join(sections)

def extract_code_patch(llm_response: str) -> str:
    """Finding 4 fix: Extracts code strictly from markdown fences; rejects raw prose."""
    pattern = re.compile(r"```(?:python)?\s*\n(.*?)\n```", re.DOTALL)
    match = pattern.search(llm_response)
    if match:
        clean_code = match.group(1).rstrip() + "\n"
        if clean_code.strip():
            return clean_code
    raise ValueError("LLM response did not contain a valid code block (rejected raw text to protect source files).")

def apply_patch_to_file(file_path: Path, new_code: str) -> None:
    """Overwrites the target file safely."""
    file_path.write_text(new_code, encoding="utf-8")
