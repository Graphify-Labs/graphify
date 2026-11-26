"""Resolve ADR/RFC citation stubs to the scanned decision document (#5227).

The JS/TS rationale pass turns a comment such as ``// See ADR-0007.`` into a
``cites`` edge to a ``docref_adr_0007`` stub, because one file cannot know
where the decision document lives. With the whole corpus in hand this pass
looks for the document that *is* ADR-0007:

* its title (first heading) starts with the id, in any spelling the extractor
  already normalizes (``ADR-0007: ...``, ``ADR 7 - ...``); or
* its file name starts with the number (``0007-use-postgres.md``) and it sits
  in a folder that holds decision records (``adr``, ``adrs``, ``decisions``,
  ``rfc``, ``rfcs``), the adr-tools layout.

A body mention never claims an id: ADR-0009 saying "Supersedes ADR-0007" is
not ADR-0007. When exactly one document claims the id, each ``cites`` edge
is redirected to that document's page node, stays ``cites`` (a citation is
not an implementation claim) and becomes INFERRED, since the document was
matched rather than named. The stub is dropped once nothing points at it.
Zero or several claimants leave the stub alone: an ambiguous match is a guess.
"""
from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any

_ID_RE = re.compile(r"^\s*(ADR|RFC)[- ]?0*(\d{1,5})\b", re.IGNORECASE)
_FILE_NUMBER_RE = re.compile(r"^0*(\d{1,5})[-_]")
DROP_FLAG = "_doc_ref_resolved"
_FOLDER_KIND = {
    "adr": "ADR", "adrs": "ADR", "decisions": "ADR",
    "rfc": "RFC", "rfcs": "RFC",
}


def _label(kind: str, num: str) -> str:
    """Same canonical form as extract._add_doc_ref."""
    kind = kind.upper()
    return f"{kind}-{num.zfill(4)}" if kind == "ADR" else f"{kind}-{num}"


def _line(node: dict[str, Any]) -> int:
    loc = str(node.get("source_location") or "")
    return int(loc[1:]) if loc[:1] == "L" and loc[1:].isdigit() else 1 << 30


def _claims(source_file: str, title: str | None) -> set[str]:
    out: set[str] = set()
    if title:
        m = _ID_RE.match(title)
        if m:
            out.add(_label(m.group(1), m.group(2)))
    path = PurePosixPath(source_file.replace("\\", "/"))
    m = _FILE_NUMBER_RE.match(path.name)
    # Only the immediate folder counts: paths may be absolute, and a checkout
    # under ~/adr/ must not turn every numbered file into a decision record.
    kind = _FOLDER_KIND.get(path.parent.name.lower())
    if m and kind:
        out.add(_label(kind, m.group(1)))
    return out


def resolve_doc_refs(per_file: list[dict], all_nodes: list[dict], all_edges: list[dict]) -> None:
    stubs = {n["id"]: n["label"] for n in all_nodes if n.get("file_type") == "doc_ref"}
    if not stubs:
        return

    pages: dict[str, str] = {}
    titles: dict[str, dict[str, Any]] = {}
    for n in all_nodes:
        sf = n.get("source_file")
        if not sf or n.get("file_type") != "document":
            continue
        kind = n.get("node_kind")
        if kind == "page":
            pages[sf] = n["id"]
        elif kind == "heading" and _line(n) < _line(titles.get(sf, {})):
            titles[sf] = n

    claimants: dict[str, set[str]] = {}
    for sf, page_id in pages.items():
        for label in _claims(sf, (titles.get(sf) or {}).get("label")):
            claimants.setdefault(label, set()).add(page_id)

    target = {sid: next(iter(claimants[label]))
              for sid, label in stubs.items() if len(claimants.get(label, ())) == 1}
    if not target:
        return

    for e in all_edges:
        if e.get("relation") == "cites" and e.get("target") in target:
            e["target"] = target[e["target"]]
            e["confidence"] = "INFERRED"
            e["confidence_score"] = 0.95

    # Flag, don't filter: on an incremental rebuild ``all_nodes`` is a scratch
    # copy whose removals never reach the real list, but the node dicts are
    # shared, so extract() drops flagged stubs after every resolver has run.
    still_used = {
        end for e in all_edges for end in (e.get("source"), e.get("target")) if end in target
    }
    for n in all_nodes:
        if n["id"] in target and n["id"] not in still_used:
            n[DROP_FLAG] = True
