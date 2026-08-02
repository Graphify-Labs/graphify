"""Roxygen block parsing for the R extractor.

Roxygen documentation lives in `#'` comment lines directly above the object it
documents, so it is invisible to the AST — tree-sitter reports the whole block as
a run of `comment` nodes with no link to the binding below. The tags carry
relationships nothing else in R does:

  * ``@seealso`` and ``@inheritParams`` name functions that the documented one
    never calls, which is exactly what a call graph structurally cannot find
  * ``@template`` names a file under ``man-roxygen/`` that is otherwise an
    orphan — nothing sources it, roxygen splices it at document time
  * ``@family`` groups functions that belong together
  * ``@export`` marks the public API, which is otherwise indistinguishable from
    an internal helper

Blocks are matched to code by line: roxygen requires the block to sit directly
above its object, so the block ending on line N documents the definition starting
on line N+1. Parsing is line-oriented for the same reason — it is how roxygen
itself reads them.
"""
from __future__ import annotations

import re

# `\link{fn}`, `\code{\link{fn}}`, `\link[pkg]{fn}` — the three forms roxygen
# accepts for a cross-reference. The optional `[pkg]` is dropped: a reference into
# another package cannot resolve inside this corpus anyway.
_LINK_RE = re.compile(r"\\link(?:\[[^\]]*\])?\{([^}]+)\}")
# A bare name in a @seealso that uses no \link markup at all.
_BARE_NAME_RE = re.compile(r"^[A-Za-z.][A-Za-z0-9._]*$")
_TAG_RE = re.compile(r"^\s*@(\w+)\s*(.*)$")
_ROXY_RE = re.compile(r"^\s*#'\s?(.*)$")


def _names_from_seealso(body: str) -> list[str]:
    """Function names referenced by a @seealso body, in order."""
    names = _LINK_RE.findall(body)
    if names:
        return [n.strip() for n in names if n.strip()]
    # No markup: accept only a clean comma-separated name list, never prose.
    parts = [p.strip().rstrip("()") for p in body.replace("\n", " ").split(",")]
    return [p for p in parts if _BARE_NAME_RE.match(p)]


def parse_blocks(source_text: str) -> dict[int, dict]:
    """Map a 1-based line number to the roxygen tags documenting it.

    The key is the line the documented object starts on — the line directly after
    the block's last `#'` — so a caller with a definition's line can look its
    documentation up without tracking comment nodes.
    """
    lines = source_text.splitlines()
    blocks: dict[int, dict] = {}
    buffer: list[str] = []
    start = 0
    for idx, raw in enumerate(lines, start=1):
        match = _ROXY_RE.match(raw)
        if match:
            if not buffer:
                start = idx
            buffer.append(match.group(1))
            continue
        if buffer:
            blocks[idx] = _parse_tags(buffer, start)
            buffer = []
    if buffer:  # block at end of file documents nothing
        buffer = []
    return blocks


def _parse_tags(body_lines: list[str], start_line: int) -> dict:
    """Split a block's lines into tags, folding continuation lines into the tag."""
    tags: dict[str, list[str]] = {}
    current = None
    for line in body_lines:
        tag = _TAG_RE.match(line)
        if tag:
            current = tag.group(1)
            tags.setdefault(current, []).append(tag.group(2))
        elif current is not None:
            tags[current][-1] += "\n" + line
    seealso: list[str] = []
    for body in tags.get("seealso", []):
        seealso.extend(_names_from_seealso(body))
    # @inheritParams takes exactly one function name, no markup.
    inherits = [b.strip() for b in tags.get("inheritParams", []) if b.strip()]
    templates = [b.strip().split()[0] for b in tags.get("template", []) if b.strip()]
    families = [b.strip() for b in tags.get("family", []) if b.strip()]
    return {
        "line": start_line,
        "exported": "export" in tags,
        "seealso": seealso,
        "inherit_params": inherits,
        "templates": templates,
        "families": families,
        "has_docs": bool(tags),
    }
