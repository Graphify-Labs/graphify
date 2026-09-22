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
CACHE_METADATA_VERSION = 1
EXTRACTION_IDENTITY_VERSION = 1
EXTRACTION_OPTIONS = ("code-only", "no-cluster", "force")
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
        required = ("case_id", "pr", "url", "title", "category", "head_sha", "merge_base_sha", "changed_file_count", "changed_files", "github_changed_files")
        if not isinstance(case, dict) or any(not case.get(key) for key in required):
            raise ValueError("case is missing required fields")
        if not case.get("reported_base_sha") and not case.get("base_sha"):
            raise ValueError("case is missing required fields")
        if not isinstance(case["case_id"], str) or case["case_id"] in ids:
            raise ValueError("duplicate case ID")
        if not isinstance(case["pr"], int) or case["pr"] in prs:
            raise ValueError("duplicate PR")
        if any(not isinstance(case[key], str) or len(case[key]) != 40 or any(c not in "0123456789abcdef" for c in case[key]) for key in ("head_sha", "merge_base_sha")):
            raise ValueError("malformed base/head SHA")
        reported_base_sha = case.get("reported_base_sha", case.get("base_sha"))
        if not isinstance(reported_base_sha, str) or len(reported_base_sha) != 40 or any(c not in "0123456789abcdef" for c in reported_base_sha):
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


def _reported_base(case: dict[str, Any]) -> str:
    """Return the GitHub-reported base, accepting v1's legacy spelling."""
    return case.get("reported_base_sha", case.get("base_sha", ""))


def _git(*args: str, capture: bool = True) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], check=True, text=True, stdout=subprocess.PIPE if capture else None, stderr=subprocess.PIPE if capture else None).stdout.strip()


def _ensure_object(sha: str) -> None:
    if subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", f"{sha}^{{commit}}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        for remote in ("origin", "upstream"):
            if subprocess.run(["git", "-C", str(ROOT), "fetch", remote, sha], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
                break
        else:
            raise RuntimeError(f"historical Git object is unavailable: {sha}")


def canonicalize_changed_files(output: str) -> list[dict[str, Any]]:
    """Convert Git name-status output to the GitHub evidence vocabulary."""
    changes: list[dict[str, Any]] = []
    for line in output.splitlines():
        fields = line.split("\t")
        if len(fields) < 2:
            raise ValueError(f"malformed Git name-status output: {line!r}")
        code = fields[0]
        kind = code[:1]
        if kind == "M":
            if len(fields) != 2:
                raise ValueError(f"malformed modified name-status output: {line!r}")
            changes.append({"path": fields[1], "status": "modified"})
        elif kind == "A":
            if len(fields) != 2:
                raise ValueError(f"malformed added name-status output: {line!r}")
            changes.append({"path": fields[1], "status": "added"})
        elif kind == "D":
            if len(fields) != 2:
                raise ValueError(f"malformed deleted name-status output: {line!r}")
            changes.append({"path": fields[1], "status": "removed"})
        elif kind == "R":
            if len(fields) != 3:
                raise ValueError(f"malformed renamed name-status output: {line!r}")
            changes.append({"previous_path": fields[1], "path": fields[2], "status": "renamed"})
        else:
            raise ValueError(f"unsupported Git name-status code: {code!r}")
    return changes


def _evidence_key(item: dict[str, Any]) -> tuple[str, str, str]:
    return (item.get("status", ""), item.get("previous_path", ""), item.get("path", ""))


def verify_changed_file_evidence(derived: list[dict[str, Any]], expected: list[dict[str, Any]]) -> None:
    """Fail closed when Git and committed GitHub PR evidence disagree."""
    normalized_expected = []
    for item in expected:
        value = {"path": item["path"], "status": item["status"]}
        if item.get("previous_path") is not None:
            value["previous_path"] = item["previous_path"]
        normalized_expected.append(value)
    if len(derived) != len(normalized_expected):
        raise ValueError("GitHub changed-file count mismatch")
    if sorted(map(_evidence_key, derived)) != sorted(map(_evidence_key, normalized_expected)):
        raise ValueError("GitHub changed-file path/status/rename-source mismatch")


def authoritative_changed_files(base_sha: str, head_sha: str) -> list[dict[str, Any]]:
    """Return the PR patch as merge-base-to-head paths and Git status."""
    _ensure_object(base_sha)
    _ensure_object(head_sha)
    merge_base = _git("merge-base", base_sha, head_sha)
    output = _git("diff", "--name-status", "--find-renames", merge_base, head_sha)
    return canonicalize_changed_files(output)


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


def _extraction_paths(root: Path = ROOT) -> list[Path]:
    paths = [path for path in (root / "graphify").rglob("*") if path.is_file() and "__pycache__" not in path.parts and path.suffix not in {".pyc", ".pyo"}]
    paths.extend(path for path in (root / "pyproject.toml", root / "uv.lock") if path.is_file())
    return sorted(paths)


def _extraction_identity(root: Path = ROOT) -> str:
    """Identify inputs that can change historical Graphify extraction."""
    files = []
    for path in _extraction_paths(root):
        files.append({"path": path.relative_to(root).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    return _sha({"version": EXTRACTION_IDENTITY_VERSION, "options": EXTRACTION_OPTIONS, "files": files})


def _extraction_identity_at_commit(commit: str) -> str:
    """Compute the same inspectable identity for a historical evaluator commit."""
    names = _git("ls-tree", "-r", "--name-only", commit).splitlines()
    wanted = [name for name in names if name.startswith("graphify/") or name in {"pyproject.toml", "uv.lock"}]
    files = []
    for name in wanted:
        content = subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{name}"], check=True, stdout=subprocess.PIPE).stdout
        files.append({"path": name, "sha256": hashlib.sha256(content).hexdigest()})
    return _sha({"version": EXTRACTION_IDENTITY_VERSION, "options": EXTRACTION_OPTIONS, "files": files})


def _cache_key(extraction_identity: str, source_snapshot_sha: str) -> str:
    return _sha({"schema_version": SCHEMA_VERSION, "extraction_identity": extraction_identity, "source_snapshot_sha": source_snapshot_sha, "extract": EXTRACTION_OPTIONS})


def _graph_bytes_fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cache_metadata(cache: Path) -> Path:
    return cache / "cache-metadata.json"


def _valid_cache_hit(cache: Path, graph: Path, extraction_identity: str, source_snapshot_sha: str) -> bool:
    """Accept a cache only when its independently-written completion proof matches."""
    if not graph.is_file() or not _cache_metadata(cache).is_file():
        return False
    try:
        metadata = _json(_cache_metadata(cache))
        return (
            metadata.get("schema_version") == CACHE_METADATA_VERSION
            and metadata.get("status") == "COMPLETED"
            and metadata.get("source_snapshot_sha") == source_snapshot_sha
            and metadata.get("extraction_identity") == extraction_identity
            and metadata.get("graph_fingerprint") == _graph_bytes_fingerprint(graph)
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return False


def _valid_legacy_record(previous: dict[str, Any], source_snapshot_sha: str, extraction_identity: str) -> bool:
    """Validate retained pre-metadata evidence before adopting a legacy graph."""
    if previous.get("source_snapshot_sha") != source_snapshot_sha:
        return False
    if previous.get("prepare_status") != "PREPARED":
        return False
    old_identity = previous.get("evaluator_identity")
    if not old_identity and previous.get("evaluator_sha"):
        try:
            old_identity = _extraction_identity_at_commit(previous["evaluator_sha"])
        except (OSError, subprocess.CalledProcessError):
            old_identity = None
    graph = Path(previous.get("graph_path", ""))
    fingerprint = previous.get("graph_fingerprint")
    return bool(old_identity == extraction_identity and graph.is_file() and fingerprint and fingerprint == _graph_bytes_fingerprint(graph))


def _extract(source_snapshot_sha: str, extraction_identity: str, previous: dict[str, Any] | None = None) -> tuple[Path, bool]:
    cache = _root("cache") / _cache_key(extraction_identity, source_snapshot_sha)
    graph = cache / "graphify-out" / "graph.json"
    if _valid_cache_hit(cache, graph, extraction_identity, source_snapshot_sha):
        return graph, True
    if previous and _valid_legacy_record(previous, source_snapshot_sha, extraction_identity):
        return Path(previous["graph_path"]), True
    cache_root = _root("cache")
    cache_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="graphify-jev-eval-", dir=str(cache_root)))
    try:
        source, output = staging / "source", staging / "out"
        _archive(source_snapshot_sha, source)
        subprocess.run([sys.executable, "-m", "graphify", "extract", str(source), "--code-only", "--no-cluster", "--force", "--out", str(output)], cwd=ROOT, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        generated = output / "graphify-out" / "graph.json"
        if not generated.exists():
            raise RuntimeError("current Graphify did not produce graph.json")
        cache.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(output, cache, dirs_exist_ok=True)
        # The completion marker is written last. A graph left by an interrupted
        # copy is therefore never treated as a completed reusable extraction.
        _write(_cache_metadata(cache), {"schema_version": CACHE_METADATA_VERSION, "status": "COMPLETED", "source_snapshot_sha": source_snapshot_sha, "extraction_identity": extraction_identity, "graph_fingerprint": _graph_bytes_fingerprint(graph)})
        return graph, False
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _task(case: dict[str, Any], base_present: list[str]) -> dict[str, Any]:
    return {"schema_version": 1, "case_id": case["case_id"], "objective": case["title"], "changed_files": base_present, "seed_nodes": []}


def _record_path(case_id: str) -> Path:
    return _root("state") / "cases" / f"{case_id}.json"


def prepare(cases: list[dict[str, Any]]) -> None:
    evaluator_sha = _git("rev-parse", "HEAD")
    extraction_identity = _extraction_identity()
    for case in cases:
        previous = _read_record(case["case_id"])
        if previous:
            old_reported = previous.get("reported_base_sha", previous.get("case", {}).get("base_sha", _reported_base(case)))
            old_merge = previous.get("merge_base_sha", previous.get("case", {}).get("merge_base_sha"))
            old_source = previous.get("source_snapshot_sha")
            invalid_source = old_merge and ((old_source and old_source != old_merge) or (not old_source and old_reported != old_merge))
            reason = "SUPERSEDED_INVALID_SOURCE_SNAPSHOT" if invalid_source else "SUPERSEDED_PREVIOUS_PREPARATION"
            _archive_record(previous, case["case_id"], reason)
        reported_base_sha = _reported_base(case)
        record: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "case": case, "case_identity": _case_identity(case), "evaluator_sha": evaluator_sha, "evaluator_identity": extraction_identity, "prepare_status": "PREPARE_FAILED", "cache_hit": False, "reported_base_sha": reported_base_sha, "head_sha": case["head_sha"], "merge_base_sha": case["merge_base_sha"], "source_snapshot_sha": case["merge_base_sha"], "historical_diff_method": "merge-base-to-head", "historical_provenance": "UNVERIFIED"}
        try:
            authoritative = authoritative_changed_files(reported_base_sha, case["head_sha"])
            merge_base_sha = _git("merge-base", reported_base_sha, case["head_sha"])
            actual_paths = {item["path"] for item in authoritative}
            if merge_base_sha != case["merge_base_sha"]:
                raise ValueError("manifest merge-base does not match historical Git ancestry")
            verify_changed_file_evidence(authoritative, case["github_changed_files"])
            if actual_paths != set(case["changed_files"]):
                raise ValueError("manifest changed files do not exactly match historical PR patch")
            record.update({"merge_base_sha": merge_base_sha, "source_snapshot_sha": merge_base_sha, "pr_changed_file_count": case["changed_file_count"], "pr_changed_files": case["changed_files"], "changed_file_status": authoritative})
            record["historical_provenance"] = "PR_PATCH_PROVENANCE_VERIFIED"
            base_paths = set(_git("ls-tree", "-r", "--name-only", merge_base_sha).splitlines())
            present = [path for path in case["changed_files"] if path in base_paths]
            missing = [path for path in case["changed_files"] if path not in base_paths]
            task = _task(case, present)
            if not present:
                record.update({"prepare_status": "PREPARE_UNRESOLVED", "reason": "no changed file exists in base snapshot", "base_present_changed_files": present, "base_missing_changed_files": missing})
            else:
                graph, hit = _extract(merge_base_sha, extraction_identity, previous)
                payload = outbound_payload(task, graph)
                seeds = [node["id"] for node in payload["state"]["candidates"]["nodes"] if node["source_file"] in present]
                if not seeds:
                    record.update({"prepare_status": "PREPARE_UNRESOLVED", "reason": "changed-file seeding matched no graph nodes", "base_present_changed_files": present, "base_missing_changed_files": missing})
                else:
                    graph_fingerprint = payload["state"]["graph_fingerprint"]
                    payload_path = _root("state") / "payloads" / f"{case['case_id']}.json"
                    _write(payload_path, payload)
                    record.update({"prepare_status": "PREPARED", "base_present_changed_files": present, "base_missing_changed_files": missing, "task": task, "task_fingerprint": _fingerprint(task), "graph_path": str(graph), "graph_fingerprint": graph_fingerprint, "seed_node_ids": seeds, "candidate_node_count": len(payload["state"]["candidates"]["nodes"]), "candidate_edge_count": len(payload["state"]["candidates"]["edges"]), "node_cap_reached": len(payload["state"]["candidates"]["nodes"]) >= 40, "edge_cap_reached": len(payload["state"]["candidates"]["edges"]) >= 80, "question_count": len(payload["questions"]), "payload_path": str(payload_path), "payload_fingerprint": _sha(payload), "payload_graph_fingerprint": payload["state"]["graph_fingerprint"], "cache_hit": hit})
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


def _historical_provenance_verified(case: dict[str, Any], record: dict[str, Any] | None) -> bool:
    """Require current, complete historical evidence before reporting verification."""
    if not record or record.get("error") or record.get("historical_provenance") != "PR_PATCH_PROVENANCE_VERIFIED":
        return False
    if record.get("merge_base_sha") != case.get("merge_base_sha") or record.get("source_snapshot_sha") != case.get("merge_base_sha"):
        return False
    if record.get("pr_changed_file_count") != case.get("changed_file_count"):
        return False
    try:
        verify_changed_file_evidence(record.get("changed_file_status", []), case["github_changed_files"])
    except (TypeError, ValueError, KeyError):
        return False
    return {item.get("path") for item in record.get("changed_file_status", [])} == set(case.get("changed_files", []))


def _stale_reasons(case: dict[str, Any], record: dict[str, Any], evaluator_sha: str) -> list[str]:
    reasons = []
    if record.get("evaluator_identity") != _extraction_identity():
        reasons.append("extraction identity changed")
    if record.get("case_identity") != _case_identity(case):
        reasons.append("manifest case changed")
    if record.get("source_snapshot_sha") != record.get("merge_base_sha"):
        reasons.append("source snapshot is not merge base")
    if record.get("source_snapshot_sha") != case.get("merge_base_sha"):
        reasons.append("source snapshot differs from manifest merge base")
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


def _classification(case: dict[str, Any], record: dict[str, Any] | None) -> str:
    """Single current-evidence decision used by both status and report."""
    if not record:
        return "missing"
    if record.get("collection_status") == "LIVE_FAILED":
        return "failed"
    if record.get("prepare_status") == "PREPARE_UNRESOLVED":
        return "structurally unresolved"
    if record.get("prepare_status") != "PREPARED":
        return "failed"
    if _stale_reasons(case, record, _git("rev-parse", "HEAD")):
        return "stale"
    if record.get("collection_status") == "LIVE_PASS":
        return "live-collected"
    return "prepared"


def status(cases: list[dict[str, Any]]) -> None:
    totals = {"missing": 0, "structurally unresolved": 0, "prepared": 0, "stale": 0, "live-collected": 0, "failed": 0}
    for case in cases:
        value = _classification(case, _read_record(case["case_id"]))
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
            record["attempt_count"] = record.get("attempt_count", 0) + 1
            record["last_attempt_at"] = datetime.now(timezone.utc).isoformat()
            response = call_typesafe(payload, key)
            derived = sidecar(payload, record["task"], graph_path, response)
            record.update({"collection_status": "LIVE_PASS", "request_model_alias": payload["model"], "returned_model": response["model"], "usage": response["usage"], "raw_answers": response["answers"], "result": derived, "collected_at": datetime.now(timezone.utc).isoformat()})
        except Exception as exc:
            # Only failures after entering the transport boundary are
            # transport attempts. Earlier preparation/read/validation errors
            # must not be inferred to be attempts.
            record.update({"collection_status": "LIVE_FAILED", "error_category": type(exc).__name__, "error": str(exc)})
        _write(_record_path(case["case_id"]), record)


def report(cases: list[dict[str, Any]]) -> Path:
    rows, inputs, outputs, blast, nouls = [], 0, 0, {}, []
    for case in cases:
        record = _read_record(case["case_id"]) or {}
        state = _classification(case, record)
        result = record.get("result", {}) if state == "live-collected" else {}
        judgments = result.get("graph_judgments", {})
        usage = record.get("usage", {}) if state == "live-collected" else {}
        inputs += usage.get("input_tokens", 0); outputs += usage.get("output_tokens", 0)
        choice = judgments.get("blast_radius", {}).get("choice", "-")
        if choice != "-": blast[choice] = blast.get(choice, 0) + 1
        for key in ("consumer_discovery_needed", "test_evidence_discovery_needed"):
            if key in judgments: nouls.append(judgments[key].get("noul"))
        consumer = judgments.get("consumer_discovery_needed", {}).get("noul", "-")
        tests = judgments.get("test_evidence_discovery_needed", {}).get("noul", "-")
        rows.append(f"| #{case['pr']} | {case['category']} | {state} | {record.get('candidate_node_count','-')} | {record.get('candidate_edge_count','-')} | {'yes' if record.get('node_cap_reached') else 'no'} | {'yes' if record.get('edge_cap_reached') else 'no'} | {record.get('question_count','-')} | {choice} | {consumer} | {tests} | {usage.get('input_tokens','-')}/{usage.get('output_tokens','-')} |")
    classifications = [_classification(c, _read_record(c["case_id"])) for c in cases]
    prepared = classifications.count("prepared") + classifications.count("live-collected")
    live = classifications.count("live-collected")
    verified = all(_historical_provenance_verified(c, _read_record(c["case_id"])) for c in cases)
    provenance = "PR-patch provenance verified 12/12" if verified and len(cases) == 12 else "PR-patch provenance unresolved"
    divergence = sum(_reported_base(c) != c["merge_base_sha"] for c in cases)
    returned_models = sorted({(_read_record(c["case_id"]) or {}).get("returned_model") for c, state in zip(cases, classifications) if state == "live-collected" and (_read_record(c["case_id"]) or {}).get("returned_model")})
    history_dir = _root("state") / "history"
    superseded_invalid = sum((_json(path).get("archive_reason") == "SUPERSEDED_INVALID_SOURCE_SNAPSHOT") for path in history_dir.glob("*.json")) if history_dir.exists() else 0
    source_provenance = "historical source snapshot = merge-base" if verified else "historical source snapshot provenance unresolved"
    text = f"# Graphify Jev historical evaluation M1\n\n{provenance}; {source_provenance}. Reported-base/merge-base divergences: {divergence}. Current Graphify evaluated exact historical PR patch base snapshots; Jev received only title-derived objective and bounded structural metadata, never source or diff text. Results are descriptive evidence, not production policy.\n\n"
    unresolved = classifications.count("structurally unresolved")
    node_caps = sum((_read_record(c["case_id"]) or {}).get("node_cap_reached", False) for c in cases)
    edge_caps = sum((_read_record(c["case_id"]) or {}).get("edge_cap_reached", False) for c in cases)
    failures = classifications.count("failed")
    records = [(_read_record(c["case_id"]) or {}) for c in cases]
    attempted = [record for record in records if record.get("collection_status") in {"LIVE_PASS", "LIVE_FAILED"} or "result" in record]
    known_attempts = [record.get("attempt_count") for record in attempted]
    attempts = sum(value for value in known_attempts if isinstance(value, int))
    unknown_attempts = any(not isinstance(value, int) for value in known_attempts)
    attempt_text = str(attempts) if not unknown_attempts else f"{attempts} known; additional attempts unknown"
    text += f"Preparation: {prepared} prepared, {unresolved} structurally unresolved. Live pass/fail: {live} pass / {failures} failed. Actual TypeSafe attempts: {attempt_text}. Returned Jev models: {json.dumps(returned_models)}. Superseded invalid-source records: {superseded_invalid}. Node-cap saturation: {node_caps}. Edge-cap saturation: {edge_caps}. Tokens: {inputs} input, {outputs} output. Blast-radius distribution: {json.dumps(blast, sort_keys=True)}. Noul observations: {json.dumps(nouls)}.\n\n"
    text += "| PR | Category | State | Nodes | Edges | Node cap? | Edge cap? | Questions | Blast radius | Consumer Noul | Test Noul | Tokens in/out |\n|---|---|---|---:|---:|---|---|---:|---|---:|---:|---|\n" + "\n".join(rows) + "\n\n"
    text += "| PR | Reported base | Merge-base | Same? | Changed files | Evidence match |\n|---:|---|---|---|---:|---|\n"
    for case in cases:
        record = _read_record(case["case_id"]) or {}
        try:
            verify_changed_file_evidence(record.get("changed_file_status", []), case["github_changed_files"])
            evidence_ok = _historical_provenance_verified(case, record)
        except (TypeError, ValueError):
            evidence_ok = False
        text += f"| #{case['pr']} | {_reported_base(case)} | {case['merge_base_sha']} | {'yes' if _reported_base(case) == case['merge_base_sha'] else 'no'} | {case['changed_file_count']} | {'yes' if evidence_ok else 'no'} |\n"
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
