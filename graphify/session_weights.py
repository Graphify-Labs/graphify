"""Optional experiential weighting for god nodes from a session memory layer.

Structural degree measures what the code is wired to; it says nothing about
what the developer actually works on. A file with 50 imports is a structural
hub, but a file the developer debugged across three sessions is an
experiential one. When a session memory layer (agentmemory) is running, its
per-file observation history can annotate and re-rank god nodes so the report
surfaces the abstractions that are both connected AND actively worked on.

Strictly opt-in: graphify never makes network calls unless
GRAPHIFY_SESSION_WEIGHTS is set. Set it to "1" to use the default
agentmemory address (http://localhost:3111) or to a full base URL. When the
memory server is unreachable, the report falls back to pure structural
ranking with a single stderr note; failure never changes exit codes or
output structure.
"""
from __future__ import annotations

import json
import math
import os
import sys
import urllib.error
import urllib.request

_DEFAULT_BASE_URL = "http://localhost:3111"
_TIMEOUT_SECONDS = 2.0
_MAX_FILES = 200


def session_weights_base_url() -> str | None:
    """Return the memory-layer base URL, or None when the feature is off."""
    raw = os.environ.get("GRAPHIFY_SESSION_WEIGHTS", "").strip()
    if not raw or raw in {"0", "false", "off"}:
        return None
    if raw in {"1", "true", "on"}:
        return _DEFAULT_BASE_URL
    return raw.rstrip("/")


def fetch_file_activity(
    files: list[str],
    base_url: str,
    timeout: float = _TIMEOUT_SECONDS,
) -> dict[str, dict]:
    """Query the memory layer for per-file session history.

    Returns {file: {"observations": int, "sessions": int}} for files with any
    recorded activity. Empty dict on any failure (connection refused, timeout,
    non-JSON, unexpected shape) - the caller treats that as "feature off".
    """
    if not files:
        return {}
    payload = json.dumps({"files": files[:_MAX_FILES]}).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/agentmemory/file-context",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    secret = os.environ.get("AGENTMEMORY_SECRET", "").strip()
    if secret:
        req.add_header("Authorization", f"Bearer {secret}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        print(f"graphify: session weights unavailable ({exc}); using structural ranking", file=sys.stderr)
        return {}

    activity: dict[str, dict] = {}
    for entry in body.get("files", []) if isinstance(body, dict) else []:
        if not isinstance(entry, dict):
            continue
        file = entry.get("file")
        observations = entry.get("observations")
        if not isinstance(file, str) or not isinstance(observations, list):
            continue
        if not observations:
            continue
        sessions = {
            o.get("sessionId")
            for o in observations
            if isinstance(o, dict) and o.get("sessionId")
        }
        activity[file] = {
            "observations": len(observations),
            "sessions": max(len(sessions), 1),
        }
    return activity


def apply_experiential_weights(
    god_node_list: list[dict],
    node_files: dict[str, str],
    activity: dict[str, dict],
) -> list[dict]:
    """Annotate god nodes with session activity and re-rank.

    Ranking key is degree * (1 + ln(1 + observations)) so structural weight
    still dominates, but a node the developer keeps coming back to outranks a
    same-degree node nobody has touched. Deterministic given the inputs;
    nodes without activity keep their structural order (stable sort).
    """
    if not activity:
        return god_node_list

    annotated: list[dict] = []
    for node in god_node_list:
        entry = dict(node)
        file = node_files.get(str(node.get("id", "")))
        stats = activity.get(file) if file else None
        if stats:
            entry["observations"] = stats["observations"]
            entry["sessions"] = stats["sessions"]
        annotated.append(entry)

    def rank(entry: dict) -> float:
        degree = float(entry.get("degree", 0))
        observations = float(entry.get("observations", 0))
        return degree * (1.0 + math.log1p(observations))

    annotated.sort(key=rank, reverse=True)
    return annotated
