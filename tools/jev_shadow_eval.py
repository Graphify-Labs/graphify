"""Reproducible, explicitly-live historical evaluation for the Jev sidecar."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from graphify.jev_shadow import JevShadowError, _fingerprint, call_typesafe, load_task, outbound_payload, sidecar

SCHEMA_VERSION = 1
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "eval" / "jev-shadow" / "cases-v1.json"


def _root(kind: str) -> Path:
    env = "XDG_CACHE_HOME" if kind == "cache" else "XDG_STATE_HOME"
    default = Path.home() / (".cache" if kind == "cache" else ".local/state")
    return Path(os.environ.get(env, default)) / "graphify" / "jev-eval"


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def load_manifest(path: Path) -> list[dict[str, Any]]:
    try:
        value = _json(path)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid manifest: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION or not isinstance(value.get("cases"), list):
        raise ValueError("unsupported manifest version")
    cases = value["cases"]
    ids, prs = set(), set()
    for case in cases:
        required = ("case_id", "pr", "url", "title", "category", "base_sha", "head_sha", "merge_base_sha", "changed_file_count", "changed_files", "github_changed_files")
        if not isinstance(case, dict) or any(not case.get(key) for key in required):
            raise ValueError("case is missing required fields")
        if not isinstance(case["case_id"], str) or case["case_id"] in ids:
            raise ValueError("duplicate case ID")
        if not isinstance(case["pr"], int) or case["pr"] in prs:
            raise ValueError("duplicate PR")
        if any(not isinstance(case[key], str) or len(case[key]) != 40 or any(c not in "0123456789abcdef" for c in case[key]) for key in ("base_sha", "head_sha", "merge_base_sha")):
            raise ValueError("malformed base/head SHA")
        if not isinstance(case["changed_file_count"], int) or case["changed_file_count"] <= 0:
            raise ValueError("invalid changed file count")
        if not isinstance(case["changed_files"], list) or not case["changed_files"] or any(not isinstance(p, str) or not p for p in case["changed_files"]):
            raise ValueError("empty or invalid changed file set")
        if case["changed_file_count"] != len(case["changed_files"]):
            raise ValueError("changed file count does not match changed file set")
        evidence = case["github_changed_files"]
        if not isinstance(evidence, list) or len(evidence) != case["changed_file_count"] or any(not isinstance(item, dict) or not isinstance(item.get("path"), str) or not item["path"] or not isinstance(item.get("status"), str) or not item["status"] for item in evidence):
            raise ValueError("invalid GitHub changed-file evidence")
        if {item["path"] for item in evidence} != set(case["changed_files"]):
            raise ValueError("GitHub evidence does not match changed file set")
        ids.add(case["case_id"]); prs.add(case["pr"])
    return cases


def _git(*args: str, capture: bool = True) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], check=True, text=True, stdout=subprocess.PIPE if capture else None, stderr=subprocess.PIPE if capture else None).stdout.strip()


def _ensure_object(sha: str) -> None:
    if subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", f"{sha}^{{commit}}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        for remote in ("origin", "upstream"):
            if subprocess.run(["git", "-C", str(ROOT), "fetch", remote, sha], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
                break
        else:
            raise RuntimeError(f"historical Git object is unavailable: {sha}")


def authoritative_changed_files(base_sha: str, head_sha: str) -> list[dict[str, Any]]:
    """Return the PR patch as merge-base-to-head paths and Git status."""
    _ensure_object(base_sha)
    _ensure_object(head_sha)
    merge_base = _git("merge-base", base_sha, head_sha)
    output = _git("diff", "--name-status", "--find-renames", merge_base, head_sha)
    changes: list[dict[str, Any]] = []
    for line in output.splitlines():
        fields = line.split("\t")
        if len(fields) < 2:
            raise ValueError(f"malformed Git name-status output: {line!r}")
        status = fields[0]
        paths = fields[1:] if status.startswith("R") or status.startswith("C") else fields[1:2]
        for path in paths:
            changes.append({"path": path, "status": status})
    return changes


def _case_identity(case: dict[str, Any]) -> str:
    return _fingerprint(case)


def _archive_record(record: dict[str, Any], case_id: str, reason: str) -> None:
    if not record:
        return
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    archived = dict(record)
    archived["archive_reason"] = reason
    _write(_root("state") / "history" / f"{stamp}-{case_id}.json", archived)


def _archive(sha: str, destination: Path) -> None:
    _ensure_object(sha)
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".tar") as file:
        subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar", "-o", file.name, sha], check=True)
        with tarfile.open(file.name) as archive:
            archive.extractall(destination, filter="data")


def _cache_key(evaluator_sha: str, base_sha: str) -> str:
    return _sha({"schema_version": SCHEMA_VERSION, "evaluator_sha": evaluator_sha, "base_sha": base_sha, "extract": ["code-only", "no-cluster", "force"]})


def _extract(base_sha: str, evaluator_sha: str) -> tuple[Path, bool]:
    cache = _root("cache") / _cache_key(evaluator_sha, base_sha)
    graph = cache / "graphify-out" / "graph.json"
    if graph.exists():
        return graph, True
    cache_root = _root("cache")
    cache_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="graphify-jev-eval-", dir=str(cache_root)))
    try:
        source, output = staging / "source", staging / "out"
        _archive(base_sha, source)
        subprocess.run([sys.executable, "-m", "graphify", "extract", str(source), "--code-only", "--no-cluster", "--force", "--out", str(output)], cwd=ROOT, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        generated = output / "graphify-out" / "graph.json"
        if not generated.exists():
            raise RuntimeError("current Graphify did not produce graph.json")
        cache.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(output, cache, dirs_exist_ok=True)
        return graph, False
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _task(case: dict[str, Any], base_present: list[str]) -> dict[str, Any]:
    return {"schema_version": 1, "case_id": case["case_id"], "objective": case["title"], "changed_files": base_present, "seed_nodes": []}


def _record_path(case_id: str) -> Path:
    return _root("state") / "cases" / f"{case_id}.json"


def prepare(cases: list[dict[str, Any]]) -> None:
    evaluator_sha = _git("rev-parse", "HEAD")
    for case in cases:
        previous = _read_record(case["case_id"])
        if previous:
            _archive_record(previous, case["case_id"], "SUPERSEDED_INVALID_PR_DIFF" if previous.get("evaluator_sha") == "0aed15bf9f59d75fa24b27aa48dfe8d2e1b6c540" else "SUPERSEDED_PREVIOUS_PREPARATION")
        record: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "case": case, "case_identity": _case_identity(case), "evaluator_sha": evaluator_sha, "prepare_status": "PREPARE_FAILED", "cache_hit": False, "historical_diff_method": "merge-base-to-head", "historical_provenance": "PR_PATCH_PROVENANCE_VERIFIED"}
        try:
            authoritative = authoritative_changed_files(case["base_sha"], case["head_sha"])
            merge_base_sha = _git("merge-base", case["base_sha"], case["head_sha"])
            actual_paths = {item["path"] for item in authoritative}
            if merge_base_sha != case["merge_base_sha"]:
                raise ValueError("manifest merge-base does not match historical Git ancestry")
            if len(authoritative) != case["changed_file_count"] or actual_paths != set(case["changed_files"]):
                raise ValueError("manifest changed files do not exactly match historical PR patch")
            record.update({"reported_base_sha": case["base_sha"], "head_sha": case["head_sha"], "merge_base_sha": merge_base_sha, "pr_changed_file_count": case["changed_file_count"], "pr_changed_files": case["changed_files"]})
            base_paths = set(_git("ls-tree", "-r", "--name-only", case["base_sha"]).splitlines())
            present = [path for path in case["changed_files"] if path in base_paths]
            missing = [path for path in case["changed_files"] if path not in base_paths]
            task = _task(case, present)
            if not present:
                record.update({"prepare_status": "PREPARE_UNRESOLVED", "reason": "no changed file exists in base snapshot", "base_present_changed_files": present, "base_missing_changed_files": missing})
            else:
                graph, hit = _extract(case["base_sha"], evaluator_sha)
                payload = outbound_payload(task, graph)
                seeds = [node["id"] for node in payload["state"]["candidates"]["nodes"] if node["source_file"] in present]
                if not seeds:
                    record.update({"prepare_status": "PREPARE_UNRESOLVED", "reason": "changed-file seeding matched no graph nodes", "base_present_changed_files": present, "base_missing_changed_files": missing})
                else:
                    graph_fingerprint = payload["state"]["graph_fingerprint"]
                    payload_path = _root("state") / "payloads" / f"{case['case_id']}.json"
                    _write(payload_path, payload)
                    record.update({"prepare_status": "PREPARED", "changed_file_status": authoritative, "base_present_changed_files": present, "base_missing_changed_files": missing, "task": task, "task_fingerprint": _fingerprint(task), "graph_path": str(graph), "graph_fingerprint": graph_fingerprint, "seed_node_ids": seeds, "candidate_node_count": len(payload["state"]["candidates"]["nodes"]), "candidate_edge_count": len(payload["state"]["candidates"]["edges"]), "node_cap_reached": len(payload["state"]["candidates"]["nodes"]) >= 40, "edge_cap_reached": len(payload["state"]["candidates"]["edges"]) >= 80, "question_count": len(payload["questions"]), "payload_path": str(payload_path), "payload_fingerprint": _sha(payload), "payload_graph_fingerprint": payload["state"]["graph_fingerprint"], "cache_hit": hit})
            record["changed_file_status"] = authoritative
        except JevShadowError as exc:
            # A graph with no deterministic changed-file seed is an expected,
            # evidence-bearing historical outcome, not a failed extraction.
            if "seeds matched no graph nodes" in str(exc):
                record.update({"prepare_status": "PREPARE_UNRESOLVED", "reason": "changed-file seeding matched no graph nodes"})
            else:
                record["error"] = type(exc).__name__ + ": " + str(exc)
        except Exception as exc:
            record["error"] = type(exc).__name__ + ": " + str(exc)
        _write(_record_path(case["case_id"]), record)


def _read_record(case_id: str) -> dict[str, Any] | None:
    path = _record_path(case_id)
    return _json(path) if path.exists() else None


def _stale_reasons(case: dict[str, Any], record: dict[str, Any], evaluator_sha: str) -> list[str]:
    reasons = []
    if record.get("evaluator_sha") != evaluator_sha:
        reasons.append("evaluator SHA changed")
    if record.get("case_identity") != _case_identity(case):
        reasons.append("manifest case changed")
    task = record.get("task")
    if not isinstance(task, dict) or record.get("task_fingerprint") != _fingerprint(task):
        reasons.append("task fingerprint changed")
    graph_path = Path(record["graph_path"]) if record.get("graph_path") else None
    payload_path = Path(record["payload_path"]) if record.get("payload_path") else None
    try:
        if not graph_path or hashlib.sha256(graph_path.read_bytes()).hexdigest() != record.get("graph_fingerprint"):
            reasons.append("graph fingerprint changed")
        payload = _json(payload_path) if payload_path else None
        if payload is None or _sha(payload) != record.get("payload_fingerprint"):
            reasons.append("payload fingerprint changed")
        if payload is None or payload.get("state", {}).get("graph_fingerprint") != record.get("payload_graph_fingerprint", record.get("graph_fingerprint")):
            reasons.append("payload graph fingerprint changed")
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        reasons.append("prepared evidence is unavailable")
    return reasons


def status(cases: list[dict[str, Any]]) -> None:
    totals = {"prepared": 0, "unresolved": 0, "stale": 0, "live-collected": 0, "failed": 0}
    evaluator_sha = _git("rev-parse", "HEAD")
    for case in cases:
        record = _read_record(case["case_id"])
        stale = bool(record and record.get("prepare_status") == "PREPARED" and _stale_reasons(case, record, evaluator_sha))
        value = "unresolved" if not record else ("stale" if stale else ("live-collected" if record.get("collection_status") == "LIVE_PASS" else {"PREPARED": "prepared", "PREPARE_UNRESOLVED": "unresolved"}.get(record.get("prepare_status"), "failed")))
        totals[value] += 1
        print(f"{case['case_id']}: {value}")
    print(json.dumps(totals, sort_keys=True))


def collect(cases: list[dict[str, Any],], live: bool) -> None:
    if not live:
        raise ValueError("collect requires --live; no TypeSafe call was made")
    key = os.environ.get("TYPESAFE_API_KEY")
    if not key:
        raise ValueError("TYPESAFE_API_KEY is required")
    evaluator_sha = _git("rev-parse", "HEAD")
    for case in cases:
        record = _read_record(case["case_id"])
        if not record or record.get("prepare_status") != "PREPARED":
            continue
        try:
            reasons = _stale_reasons(case, record, evaluator_sha)
            if reasons:
                record.update({"collection_status": "STALE", "stale_reasons": reasons})
                _write(_record_path(case["case_id"]), record)
                continue
            payload = _json(Path(record["payload_path"]))
            graph_path = Path(record["graph_path"])
            current = hashlib.sha256(graph_path.read_bytes()).hexdigest()
            if current != record["graph_fingerprint"] or _sha(payload) != record["payload_fingerprint"]:
                raise JevShadowError("prepared input fingerprint mismatch")
            response = call_typesafe(payload, key)
            derived = sidecar(payload, record["task"], graph_path, response)
            record.update({"collection_status": "LIVE_PASS", "request_model_alias": payload["model"], "returned_model": response["model"], "usage": response["usage"], "raw_answers": response["answers"], "result": derived, "collected_at": datetime.now(timezone.utc).isoformat()})
        except Exception as exc:
            record.update({"collection_status": "LIVE_FAILED", "error_category": type(exc).__name__, "error": str(exc)})
        _write(_record_path(case["case_id"]), record)


def report(cases: list[dict[str, Any]]) -> Path:
    rows, inputs, outputs, blast, nouls = [], 0, 0, {}, []
    for case in cases:
        record = _read_record(case["case_id"]) or {}
        result = record.get("result", {})
        judgments = result.get("graph_judgments", {})
        usage = record.get("usage", {})
        inputs += usage.get("input_tokens", 0); outputs += usage.get("output_tokens", 0)
        choice = judgments.get("blast_radius", {}).get("choice", "-")
        if choice != "-": blast[choice] = blast.get(choice, 0) + 1
        for key in ("consumer_discovery_needed", "test_evidence_discovery_needed"):
            if key in judgments: nouls.append(judgments[key].get("noul"))
        consumer = judgments.get("consumer_discovery_needed", {}).get("noul", "-")
        tests = judgments.get("test_evidence_discovery_needed", {}).get("noul", "-")
        state = "stale" if record.get("collection_status") == "STALE" else ("live-collected" if record.get("collection_status") == "LIVE_PASS" else record.get("prepare_status", "MISSING"))
        rows.append(f"| #{case['pr']} | {case['category']} | {state} | {record.get('candidate_node_count','-')} | {record.get('candidate_edge_count','-')} | {'yes' if record.get('node_cap_reached') else 'no'} | {'yes' if record.get('edge_cap_reached') else 'no'} | {record.get('question_count','-')} | {choice} | {consumer} | {tests} | {usage.get('input_tokens','-')}/{usage.get('output_tokens','-')} |")
    prepared = sum((_read_record(c["case_id"]) or {}).get("prepare_status") == "PREPARED" for c in cases)
    live = sum((_read_record(c["case_id"]) or {}).get("collection_status") == "LIVE_PASS" for c in cases)
    verified = all((_read_record(c["case_id"]) or {}).get("historical_provenance") == "PR_PATCH_PROVENANCE_VERIFIED" for c in cases)
    provenance = "PR-patch provenance verified 12/12" if verified and len(cases) == 12 else "PR-patch provenance unresolved"
    text = f"# Graphify Jev historical evaluation M1\n\n{provenance}. Current Graphify evaluated exact historical PR patch base snapshots; Jev received only title-derived objective and bounded structural metadata, never source or diff text. Results are descriptive evidence, not production policy.\n\n"
    unresolved = sum((_read_record(c["case_id"]) or {}).get("prepare_status") == "PREPARE_UNRESOLVED" for c in cases)
    node_caps = sum((_read_record(c["case_id"]) or {}).get("node_cap_reached", False) for c in cases)
    edge_caps = sum((_read_record(c["case_id"]) or {}).get("edge_cap_reached", False) for c in cases)
    failures = sum((_read_record(c["case_id"]) or {}).get("collection_status") == "LIVE_FAILED" for c in cases)
    text += f"Preparation: {prepared} prepared, {unresolved} unresolved. Live pass/fail: {live} pass / {failures} failed. Node-cap saturation: {node_caps}. Edge-cap saturation: {edge_caps}. Tokens: {inputs} input, {outputs} output. Blast-radius distribution: {json.dumps(blast, sort_keys=True)}. Noul observations: {json.dumps(nouls)}.\n\n"
    text += "| PR | Category | State | Nodes | Edges | Node cap? | Edge cap? | Questions | Blast radius | Consumer Noul | Test Noul | Tokens in/out |\n|---|---|---|---:|---:|---|---|---:|---|---:|---:|---|\n" + "\n".join(rows) + "\n"
    path = _root("state") / "reports" / "m1.md"; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text, encoding="utf-8")
    print(path); return path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "status", "collect", "report")); parser.add_argument("--live", action="store_true"); parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args(argv); cases = load_manifest(args.manifest)
    if args.command == "prepare": prepare(cases)
    elif args.command == "status": status(cases)
    elif args.command == "collect": collect(cases, args.live)
    else: report(cases)


if __name__ == "__main__": main()
