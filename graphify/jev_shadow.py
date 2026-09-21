"""Opt-in, sidecar-only TypeSafe Jev judgments for a bounded graph slice."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from graphify.paths import GRAPHIFY_OUT, write_json_atomic

QUESTION_SET_VERSION = "graphify-jev-v1"
MAX_NODES = 40
MAX_EDGES = 80
API_URL = "https://api.typesafe.ai/v1/systemone"


class JevShadowError(ValueError):
    """A fail-closed Jev shadow input, graph, or response error."""


@dataclass(frozen=True)
class _GraphSnapshot:
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    fingerprint: str


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def load_task(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JevShadowError(f"invalid task JSON: {exc}") from exc
    if not isinstance(value, dict) or set(value) - {"schema_version", "case_id", "objective", "changed_files", "seed_nodes"}:
        raise JevShadowError("task must be an object with only supported v1 fields")
    if value.get("schema_version") != 1:
        raise JevShadowError("task schema_version must be 1")
    for key in ("case_id", "objective"):
        if not isinstance(value.get(key), str) or not value[key].strip():
            raise JevShadowError(f"task {key} must be a non-empty string")
    for key in ("changed_files", "seed_nodes"):
        supplied = value.get(key, [])
        if not isinstance(supplied, list) or any(not isinstance(item, str) or not item for item in supplied):
            raise JevShadowError(f"task {key} must be an array of non-empty strings")
        value[key] = supplied
    if not value["changed_files"] and not value["seed_nodes"]:
        raise JevShadowError("task needs changed_files or seed_nodes")
    return value


def _nodes_edges(graph: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(graph, dict) or not isinstance(graph.get("nodes"), list):
        raise JevShadowError("graph must contain a nodes array")
    raw_edges = graph.get("links", graph.get("edges"))
    if not isinstance(raw_edges, list):
        raise JevShadowError("graph must contain links or edges array")
    nodes: list[dict[str, Any]] = []
    for raw in graph["nodes"]:
        if not isinstance(raw, dict) or raw.get("id") is None:
            raise JevShadowError("each graph node needs an id")
        nodes.append({
            "id": str(raw["id"]), "label": str(raw.get("label") or raw.get("name") or raw["id"]),
            "node_type": str(raw.get("node_type") or raw.get("type") or ""),
            "source_file": str(raw.get("source_file") or ""),
            "community": raw.get("community", raw.get("community_id", "")),
        })
    node_ids = {node["id"] for node in nodes}
    edges: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_edges):
        if not isinstance(raw, dict):
            continue
        source, target = str(raw.get("source", "")), str(raw.get("target", ""))
        if source in node_ids and target in node_ids:
            edges.append({"id": str(raw.get("id", f"edge_{index}")), "source": source, "target": target,
                          "relationship": str(raw.get("relation") or raw.get("type") or "relates"),
                          "provenance": str(raw.get("confidence") or raw.get("provenance") or "EXTRACTED")})
    return nodes, edges


def _read_graph_snapshot(graph_path: Path) -> tuple[dict[str, Any], str]:
    try:
        graph_bytes = graph_path.read_bytes()
        graph = json.loads(graph_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JevShadowError(f"invalid graph JSON: {exc}") from exc
    return graph, hashlib.sha256(graph_bytes).hexdigest()


def _candidate_slice_snapshot(graph_path: Path, task: dict[str, Any]) -> _GraphSnapshot:
    graph, fingerprint = _read_graph_snapshot(graph_path)
    nodes, edges = _nodes_edges(graph)
    node_map = {node["id"]: node for node in nodes}
    changed = set(task["changed_files"])
    explicit_seeds = set(task["seed_nodes"])
    unknown_seeds = explicit_seeds - node_map.keys()
    if unknown_seeds:
        raise JevShadowError("task seed_nodes contain unknown graph node ids")
    seeds = explicit_seeds | {node["id"] for node in nodes if node["source_file"] in changed}
    if not seeds:
        raise JevShadowError("task seeds matched no graph nodes")
    adjacent: dict[str, list[str]] = {node_id: [] for node_id in node_map}
    for edge in edges:
        adjacent[edge["source"]].append(edge["target"])
        adjacent[edge["target"]].append(edge["source"])
    selected: list[str] = []
    seen, queue = set(), deque(sorted(seed for seed in seeds if seed in node_map))
    while queue and len(selected) < MAX_NODES:
        node_id = queue.popleft()
        if node_id in seen:
            continue
        seen.add(node_id); selected.append(node_id)
        queue.extend(neighbor for neighbor in sorted(adjacent[node_id]) if neighbor not in seen)
    selected_set = set(selected)
    selected_edges = [edge for edge in edges if edge["source"] in selected_set and edge["target"] in selected_set][:MAX_EDGES]
    return _GraphSnapshot([node_map[node_id] for node_id in selected], selected_edges, fingerprint)


def candidate_slice(graph_path: Path, task: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    snapshot = _candidate_slice_snapshot(graph_path, task)
    return {"nodes": snapshot.nodes, "edges": snapshot.edges}


def outbound_payload(task: dict[str, Any], graph_path: Path) -> dict[str, Any]:
    snapshot = _candidate_slice_snapshot(graph_path, task)
    candidates = {"nodes": snapshot.nodes, "edges": snapshot.edges}
    state = {"case_id": task["case_id"], "objective": task["objective"], "changed_files": task["changed_files"], "candidates": candidates, "graph_fingerprint": snapshot.fingerprint}
    choices = {
        "localized": "A localized implementation area.", "multi_layer_feature": "Multiple layers of one feature.",
        "cross_cutting": "Multiple independent areas are materially involved.", "uncertain": "The bounded graph metadata is insufficient.",
    }
    roles = {key: key.replace("_", " ") for key in ("local_implementation", "feature_boundary", "shared_contract", "persistence_data_boundary", "external_boundary", "test_evidence", "documentation", "uncertain")}
    questions: dict[str, Any] = {
        "blast_radius": {"type": "choice", "instructions": "Classify the semantic blast radius for this task using `objective` and `candidates`.", "criteria": choices},
        "consumer_discovery_needed": {"type": "noul", "instructions": "Does this task likely need additional deterministic consumer or call-site discovery?"},
        "test_evidence_discovery_needed": {"type": "noul", "instructions": "Does this task likely need additional deterministic test-evidence discovery?"},
    }
    for node in candidates["nodes"]:
        key = node["id"]
        questions[f"node_relevant:{key}"] = {"type": "noul", "instructions": f"Is candidate node `{key}` materially relevant to this task?"}
        questions[f"node_role:{key}"] = {"type": "choice", "instructions": f"What semantic role does candidate node `{key}` have for this task?", "criteria": roles}
    for edge in candidates["edges"]:
        key = edge["id"]
        questions[f"edge_relevant:{key}"] = {"type": "noul", "instructions": f"Is candidate edge `{key}` materially relevant to this task or likely to need deterministic re-verification?"}
    return {"model": "jev-latest", "state": state, "questions": questions}


def _validated_response(payload: dict[str, Any], response: Any) -> dict[str, Any]:
    if not isinstance(response, dict) or not isinstance(response.get("model"), str) or not response["model"].strip() or not isinstance(response.get("usage"), dict) or not isinstance(response.get("answers"), dict):
        raise JevShadowError("TypeSafe response is missing model, usage, or answers")
    answers = response["answers"]
    if set(answers) != set(payload["questions"]):
        raise JevShadowError("TypeSafe response answers do not exactly match requested questions")
    for question_id, question in payload["questions"].items():
        answer = answers[question_id]
        if not isinstance(answer, dict) or answer.get("type") != question["type"]:
            raise JevShadowError(f"malformed answer for {question_id}")
        if question["type"] == "choice":
            confidence = answer.get("confidence")
            probabilities = answer.get("probabilities")
            if (answer.get("choice") not in question["criteria"] or not _valid_probability(confidence)
                    or not isinstance(probabilities, dict) or set(probabilities) != set(question["criteria"])
                    or any(not _valid_probability(value) for value in probabilities.values())):
                raise JevShadowError(f"malformed Choice answer for {question_id}")
        elif not _valid_probability(answer.get("noul")):
            raise JevShadowError(f"malformed Noul answer for {question_id}")
    return response


def _valid_probability(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1


def call_typesafe(payload: dict[str, Any], api_key: str) -> dict[str, Any]:
    request = urllib.request.Request(API_URL, data=json.dumps(payload).encode("utf-8"), headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=20) as result:
            return _validated_response(payload, json.loads(result.read().decode("utf-8")))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise JevShadowError(f"TypeSafe request failed: {getattr(exc, 'code', type(exc).__name__)}") from exc


def sidecar(payload: dict[str, Any], task: dict[str, Any], _graph_path: Path, response: dict[str, Any]) -> dict[str, Any]:
    answers = response["answers"]
    nodes = {node["id"]: node for node in payload["state"]["candidates"]["nodes"]}
    edges = {edge["id"]: edge for edge in payload["state"]["candidates"]["edges"]}
    return {"schema_version": 1, "provenance": "JEV_INFERRED", "question_set_version": QUESTION_SET_VERSION, "case_id": task["case_id"], "graph_fingerprint": payload["state"]["graph_fingerprint"], "task_fingerprint": _fingerprint(task), "model": response["model"], "usage": response["usage"], "graph_judgments": {key: answers[key] for key in ("blast_radius", "consumer_discovery_needed", "test_evidence_discovery_needed")}, "node_judgments": [{"node": nodes[node_id], "task_relevance": answers[f"node_relevant:{node_id}"], "semantic_role": answers[f"node_role:{node_id}"]} for node_id in nodes], "edge_judgments": [{"edge": edges[edge_id], "task_relevance_or_reverification": answers[f"edge_relevant:{edge_id}"]} for edge_id in edges]}


def run(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="graphify jev-shadow", description="Run opt-in Jev semantic judgments into a derived sidecar.")
    parser.add_argument("--task", required=True); parser.add_argument("--graph", default=str(Path(GRAPHIFY_OUT) / "graph.json")); parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        task, graph_path = load_task(Path(args.task)), Path(args.graph)
        payload = outbound_payload(task, graph_path)
        if args.dry_run:
            print(json.dumps(payload, indent=2, ensure_ascii=False)); return
        api_key = os.environ.get("TYPESAFE_API_KEY")
        if not api_key:
            raise JevShadowError("TYPESAFE_API_KEY is required for live jev-shadow runs")
        response = call_typesafe(payload, api_key)
        sidecar_value = sidecar(payload, task, graph_path, response)
        _, current_fingerprint = _read_graph_snapshot(graph_path)
        if current_fingerprint != payload["state"]["graph_fingerprint"]:
            raise JevShadowError("graph changed during live evaluation; refusing to write Jev sidecar")
        output = graph_path.parent / ".graphify_jev.json"
        write_json_atomic(output, sidecar_value, indent=2, ensure_ascii=False)
        print(f"Wrote derived Jev sidecar: {output}")
    except JevShadowError as exc:
        parser.error(str(exc))
