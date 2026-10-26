"""Optional, single-request Jev Decisions API boundary for the memory pilot."""

from __future__ import annotations

import itertools
import json
import math
import re
import subprocess
import sys
import urllib.request
from pathlib import Path, PurePosixPath

MODEL = "typesafe/jev-1.14"
ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
CHOICES = {"relevant", "unrelated", "insufficient_evidence"}
MAX_BODY_BYTES = 24 * 1024


def committed_excerpt(repo: Path, candidate: dict) -> str | None:
    """Read one code line from HEAD, never the mutable working tree."""
    source = candidate.get("source_file")
    if not isinstance(source, str):
        return None
    path = PurePosixPath(source)
    if (path.is_absolute() or ".." in path.parts
            or path.suffix not in {".py", ".ts", ".tsx", ".js", ".jsx"}):
        return None
    match = re.search(r"\bL(\d+)", str(candidate.get("source_location", "")))
    if not match or int(match.group(1)) < 1:
        return None
    try:
        source_text = subprocess.check_output(
            ["git", "show", f"HEAD:{source}"], cwd=repo,
        ).decode("utf-8")
        return source_text.splitlines()[int(match.group(1)) - 1][:300]
    except (subprocess.CalledProcessError, IndexError, UnicodeDecodeError):
        return None


def make_request(
    repo: Path, question: str, candidates: list[dict], observations: list[dict],
) -> tuple[dict, dict[str, tuple[str, str]]]:
    """Build one compact typed request and its local, non-transmitted pair map."""
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question is missing")
    if len(candidates) > 10 or len(observations) > 3:
        raise ValueError("Jev pilot exceeds candidate or observation limit")
    if (any(not isinstance(item, dict) or not isinstance(item.get("node_id"), str)
            for item in candidates)
            or any(not isinstance(item, dict) or not isinstance(item.get("id"), str)
                   or not isinstance(item.get("summary"), str) for item in observations)):
        raise ValueError("invalid Jev candidate or observation")
    if (len({item["node_id"] for item in candidates}) != len(candidates)
            or len({item["id"] for item in observations}) != len(observations)):
        raise ValueError("duplicate Jev candidate or observation")
    nodes = [
        {"id": item["node_id"], "label": item["label"], "type": item["type"],
         "excerpt": excerpt}
        for item in candidates if (excerpt := committed_excerpt(repo, item))
    ]
    redacted_obs = [
        {"id": item["id"], "summary": item["summary"][:300]}
        for item in observations
    ]
    pairs = [
        {"key": f"p{index:03d}", "node_id": node["id"], "observation_id": obs["id"]}
        for index, (node, obs) in enumerate(itertools.product(nodes, redacted_obs))
    ]
    pair_map = {pair["key"]: (pair["node_id"], pair["observation_id"]) for pair in pairs}
    payload = {
        "model": MODEL,
        "state": {"question": question, "nodes": nodes, "observations": redacted_obs,
                  "pairs": pairs},
        "questions": {
            pair["key"]: {
                "type": "choice",
                "instructions": f'Classify only pair {pair["key"]} in state.pairs using its node and observation references.',
                "criteria": {
                    "relevant": "The observation directly helps answer the question about this code node.",
                    "unrelated": "The observation concerns a different behavior or node.",
                    "insufficient_evidence": "The supplied excerpts do not establish relevance.",
                },
            }
            for pair in pairs
        },
    }
    if len(serialize_request(payload)) > MAX_BODY_BYTES:
        raise ValueError("Jev request exceeds 24 KiB")
    return payload, pair_map


def serialize_request(payload: dict) -> bytes:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def call_jev(payload: dict, api_key: str, *, timeout_s: int = 15) -> dict:
    """Send exactly one POST. The caller handles failures without retrying."""
    body = serialize_request(payload)
    if len(body) > MAX_BODY_BYTES:
        raise ValueError("Jev request exceeds 24 KiB")
    if not api_key:
        raise ValueError("project-scoped Jev key is missing")
    request = urllib.request.Request(
        ENDPOINT, data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        return json.load(response)


def parse_answers(response: dict, pair_map: dict[str, tuple[str, str]]) -> dict[tuple[str, str], dict]:
    """Reject the whole response unless every expected pair is well formed."""
    if not isinstance(response, dict):
        raise ValueError("invalid Jev response")
    raw = response.get("answers")
    usage = response.get("usage")
    cost = usage.get("cost") if isinstance(usage, dict) else None
    model = response.get("model")
    if (not isinstance(raw, dict) or set(raw) != set(pair_map)
            or not isinstance(model, str) or not model.startswith(MODEL)
            or isinstance(cost, bool) or not isinstance(cost, (int, float))
            or not math.isfinite(cost) or cost < 0):
        raise ValueError("incomplete Jev answer or missing actual cost")
    normalized = {}
    for key, item in raw.items():
        if not isinstance(item, dict) or item.get("type") != "choice":
            raise ValueError("invalid Jev choice answer")
        choice, probabilities = item.get("choice"), item.get("probabilities")
        if choice not in CHOICES or not isinstance(probabilities, dict) or set(probabilities) != CHOICES:
            raise ValueError("invalid Jev choice labels")
        if any(isinstance(value, bool) or not isinstance(value, (int, float))
               or not math.isfinite(value) or not 0 <= value <= 1
               for value in probabilities.values()):
            raise ValueError("invalid Jev probabilities")
        normalized[pair_map[key]] = {"choice": choice, "probability": probabilities[choice]}
    return normalized


def decide_once(
    payload: dict, pair_map: dict[str, tuple[str, str]], *, live: bool,
    approved: bool = False, max_requests: int = 0, api_key: str | None = None,
) -> tuple[dict[tuple[str, str], dict], str | None, float | None]:
    """Opt in to one paid call, returning baseline inputs on any uncertain outcome."""
    if not live or not pair_map:
        return {}, None, None
    if not approved or max_requests < 1:
        raise ValueError("live Jev requires approval flag and positive request cap")
    if not api_key:
        print("Jev key unavailable; using baseline", file=sys.stderr)
        return {}, None, None
    try:
        response = call_jev(payload, api_key)
        answers = parse_answers(response, pair_map)
    except (TimeoutError, OSError, ValueError, json.JSONDecodeError):
        print("Jev request failed or outcome uncertain; using baseline without retry", file=sys.stderr)
        return {}, None, None
    return answers, response["model"], float(response["usage"]["cost"])
