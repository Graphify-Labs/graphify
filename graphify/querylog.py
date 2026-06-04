"""Query logging for graphify — append-only JSONL, fail-silent."""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_NODES_RE = re.compile(r"(\d+)\s+nodes?\s+found")


def _log_path() -> Path | None:
    if os.environ.get("GRAPHIFY_QUERY_LOG_DISABLE", "").lower() in ("1", "true", "yes"):
        return None
    override = os.environ.get("GRAPHIFY_QUERY_LOG", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".cache" / "graphify-queries.log"


def _log_responses() -> bool:
    return os.environ.get("GRAPHIFY_QUERY_LOG_RESPONSES", "").lower() in ("1", "true", "yes")


def nodes_from_result(result: str) -> int | None:
    m = _NODES_RE.search(result or "")
    return int(m.group(1)) if m else None


def log_query(
    *,
    kind: str,
    question: str,
    corpus: str,
    result: str | None = None,
    nodes_returned: int | None = None,
    duration_ms: float | None = None,
    **extra: Any,
) -> None:
    """Append one JSONL record to the query log. Never raises."""
    try:
        path = _log_path()
        if path is None:
            return
        if nodes_returned is None and result is not None:
            nodes_returned = nodes_from_result(result)
        rec: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "kind": kind,
            "question": question,
            "corpus": corpus,
            "nodes_returned": nodes_returned,
        }
        if result is not None:
            rec["result_chars"] = len(result)
        if duration_ms is not None:
            rec["duration_ms"] = round(duration_ms, 3)
        for k, v in extra.items():
            if v is not None:
                rec[k] = v
        if result is not None and _log_responses():
            rec["response"] = result
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass
