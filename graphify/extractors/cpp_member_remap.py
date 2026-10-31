"""Plan source-qualified member-ID rewrites before canonical mutation.

The caller supplies already validated declaration/body/class pairs. A globally
unique destination keeps the established recipe. A shared old ID needs original
body-file/site proof; unproved carriers retain the entire old-ID bucket, so this
boundary never drops its bodies and leaves newly dangling references behind.
"""
from __future__ import annotations

import re

from graphify.extractors.base import _make_id


def _line(carrier):
    value = carrier.get("source_location")
    if value is not None:
        # Source points cannot require an unbounded decimal conversion. A bad
        # explicit location also cannot borrow a contradictory legacy line.
        if isinstance(value, str) and len(value) <= 32 and re.fullmatch(r"L[1-9][0-9]*", value):
            return int(value[1:])
        return None
    value = carrier.get("line")
    return value if type(value) is int and value > 0 else None


def _destination(bucket, carrier, *, target=False):
    if len(bucket["targets"]) == 1:
        return next(iter(bucket["targets"]))
    file = carrier.get("target_file") if target else carrier.get("source_file")
    if target and file is None:
        # This exact extracted file containment is target provenance. A call's
        # source file alone can never stand in for its callee's owning file.
        file = carrier.get("source_file")
        if (type(file) is not str or not file or carrier.get("relation") != "contains"
                or carrier.get("confidence") != "EXTRACTED" or carrier.get("source") != _make_id(file)):
            return None
        contains = True
    else:
        contains = False
    if type(file) is not str or file not in bucket["files"]:
        return None
    targets, spans = bucket["files"][file]
    if len(targets) != 1:
        return None
    if target and not contains:
        return next(iter(targets))  # Explicit callee file, not caller provenance.
    line = _line(carrier)
    if line is None or not any(start <= line <= end and (not contains or line == start) for start, end in spans):
        return None
    return next(iter(targets))


def plan_member_remap(pairs, edges, raw_calls):
    """Return accepted pairs and explicit carrier assignments without mutation."""
    pairs = tuple(pairs)
    buckets = {}
    for body, declaration, _ in pairs:
        old, target, file = body["id"], declaration["id"], body["source_file"]
        span = body["metadata"]["cpp_member"]["span"]
        bucket = buckets.setdefault(old, {"targets": set(), "files": {}})
        bucket["targets"].add(target)
        targets, spans = bucket["files"].setdefault(file, (set(), set()))
        targets.add(target)
        spans.add((span["start_row"] + 1, span["end_row"] + 1))
    blocked = {identity for identity, bucket in buckets.items()
               if len(bucket["targets"]) > 1 and any(len(targets) != 1 for targets, _ in bucket["files"].values())}
    changes = []
    # Inspect every endpoint before changing any pair. Unknown multi-target
    # source/target carriers veto their complete bucket, never a convenient row.
    for carriers, keys in ((edges, ("source", "target")), (raw_calls, ("source", "caller_nid"))):
        for carrier in carriers:
            for key in keys:
                identity = carrier.get(key)
                bucket = buckets.get(identity) if isinstance(identity, str) else None
                if bucket is None:
                    continue
                target = _destination(bucket, carrier, target=carriers is edges and key == "target")
                if target is None:
                    blocked.add(identity)
                elif target != identity:
                    changes.append((identity, carrier, key, target))
    return (tuple(pair for pair in pairs if pair[0]["id"] not in blocked),
            tuple((carrier, key, target) for identity, carrier, key, target in changes if identity not in blocked))
