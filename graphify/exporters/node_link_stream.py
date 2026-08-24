"""node_link_stream — bounded-memory reader for node-link ``graph.json`` files.

``graphify export neo4j|falkordb --push`` used to ``json.loads`` the whole
``graph.json`` and rebuild a NetworkX graph before pushing. A push never needs
the graph object — it only iterates nodes, then edges — but the load itself was
the memory wall: on a 1.87GB ``graph.json`` the pusher peaked at ~5.3GB RSS and
was OOM-killed during loading on a 7.6GB box.

A node-link file has a known shape: a top-level JSON object whose ``"nodes"``
and ``"links"`` (or legacy ``"edges"``, #738) keys hold arrays of small
objects. This module reads exactly that, incrementally:

- :func:`scan_node_link` makes one fast pass over the file recording the
  absolute byte offset of each array of interest (plus the ``multigraph``
  flag), skipping values with a regex-driven scanner that never materializes
  them.
- :func:`iter_node_link_array` then seeks to an offset and yields the array's
  elements one at a time.

Peak memory is one array element plus a fixed read buffer, regardless of file
size. Stdlib-only on purpose: ``ijson`` is not a graphify dependency, and the
target shape is narrow enough that a dedicated scanner beats adding one.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_READ_CHUNK = 1 << 16  # 64 KiB per read; memory bound is this plus one element
_WS = b" \t\r\n"
# Structural bytes that matter while skipping a container at C speed. Every
# other byte (scalars, commas, colons, string contents) is irrelevant to the
# nesting depth, so the regex engine can race past it.
_STRUCT = re.compile(rb'["\[\]{}]')
# A bare scalar (number / true / false / null) ends at a comma, a closing
# bracket/brace, or whitespace.
_SCALAR_END = re.compile(rb"[,\]}\s]")


class _Cursor:
    """Forward-only buffered cursor over a binary file handle.

    ``base + pos`` is the absolute byte offset in the file; :meth:`compact`
    drops consumed bytes so the buffer stays at chunk scale unless a single
    JSON value (one node/link object) is larger than a chunk.
    """

    __slots__ = ("_fh", "buf", "pos", "base", "eof")

    def __init__(self, fh, base: int = 0):
        self._fh = fh
        self.buf = b""
        self.pos = 0
        self.base = base
        self.eof = False

    def fill(self) -> bool:
        chunk = self._fh.read(_READ_CHUNK)
        if not chunk:
            self.eof = True
            return False
        self.buf += chunk
        return True

    def compact(self) -> None:
        if self.pos:
            self.base += self.pos
            self.buf = self.buf[self.pos:]
            self.pos = 0

    def tell(self) -> int:
        return self.base + self.pos

    def peek(self) -> int | None:
        while self.pos >= len(self.buf):
            if not self.fill():
                return None
        return self.buf[self.pos]

    def skip_ws(self) -> int | None:
        """Advance past whitespace; return the next byte without consuming it."""
        while True:
            while self.pos < len(self.buf):
                c = self.buf[self.pos]
                if c in _WS:
                    self.pos += 1
                else:
                    return c
            if not self.fill():
                return None


def _malformed(path: Path, cur: _Cursor, why: str) -> ValueError:
    return ValueError(
        f"{path} is not valid node-link JSON near byte {cur.tell()}: {why} "
        f"(a graph.json written by graphify is a top-level object whose "
        f'"nodes" and "links" keys hold arrays)'
    )


def _skip_string(cur: _Cursor, path: Path, *, can_compact: bool) -> None:
    """Skip a JSON string; the cursor sits on the opening quote."""
    cur.pos += 1
    while True:
        idx = cur.buf.find(b'"', cur.pos)
        while idx == -1:
            # Keep any trailing backslash run in the buffer: it may escape a
            # quote arriving in the next chunk, and compaction must not drop
            # it or the parity count below would miss it.
            end = len(cur.buf)
            trailing = 0
            while end - 1 - trailing >= cur.pos and cur.buf[end - 1 - trailing] == 0x5C:
                trailing += 1
            cur.pos = end - trailing
            if can_compact:
                cur.compact()
            if not cur.fill():
                raise _malformed(path, cur, "unterminated string")
            idx = cur.buf.find(b'"', cur.pos)
        # A quote preceded by an odd run of backslashes is escaped. The run is
        # always in the buffer: nothing compacts between segments of one string.
        j = idx - 1
        backslashes = 0
        while j >= 0 and cur.buf[j] == 0x5C:  # "\\"
            backslashes += 1
            j -= 1
        cur.pos = idx + 1
        if backslashes % 2 == 0:
            return


def _skip_container(cur: _Cursor, path: Path, *, can_compact: bool) -> None:
    """Skip an object/array; the cursor sits on the opening brace/bracket.

    With ``can_compact`` the consumed prefix is dropped whenever the buffer is
    exhausted, so skipping a multi-GB array costs a fixed-size buffer. Without
    it (parse mode) the bytes are retained for the caller to slice.
    """
    depth = 0
    while True:
        m = _STRUCT.search(cur.buf, cur.pos)
        if m is None:
            cur.pos = len(cur.buf)
            if can_compact:
                cur.compact()
            if not cur.fill():
                raise _malformed(path, cur, "unterminated value")
            continue
        cur.pos = m.start()
        c = cur.buf[cur.pos]
        if c == 0x22:  # '"'
            _skip_string(cur, path, can_compact=can_compact)
        else:
            cur.pos += 1
            if c in (0x7B, 0x5B):  # "{" "["
                depth += 1
            else:  # "}" "]"
                depth -= 1
                if depth == 0:
                    return
                if depth < 0:
                    raise _malformed(path, cur, "unbalanced brackets")


def _skip_scalar(cur: _Cursor) -> None:
    """Skip a bare scalar (number / true / false / null); EOF ends it."""
    while True:
        m = _SCALAR_END.search(cur.buf, cur.pos)
        if m is not None:
            cur.pos = m.start()
            return
        cur.pos = len(cur.buf)
        if not cur.fill():
            return


def _skip_value(cur: _Cursor, path: Path) -> None:
    c = cur.peek()
    if c is None:
        raise _malformed(path, cur, "unexpected end of file")
    if c == 0x22:
        _skip_string(cur, path, can_compact=True)
    elif c in (0x7B, 0x5B):
        _skip_container(cur, path, can_compact=True)
    else:
        _skip_scalar(cur)


def _parse_value(cur: _Cursor, path: Path):
    """Parse one JSON value at the cursor, holding only its bytes in memory."""
    c = cur.peek()
    if c is None:
        raise _malformed(path, cur, "unexpected end of file")
    start = cur.pos
    start_abs = cur.tell()
    if c == 0x22:
        _skip_string(cur, path, can_compact=False)
    elif c in (0x7B, 0x5B):
        _skip_container(cur, path, can_compact=False)
    else:
        _skip_scalar(cur)
    raw = cur.buf[start:cur.pos]
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ValueError(
            f"{path} is not valid node-link JSON near byte {start_abs}: {e}"
        ) from e


class NodeLinkScan:
    """Byte offsets of the arrays a DB push needs, plus the multigraph flag."""

    __slots__ = ("nodes_offset", "links_offset", "edges_offset", "multigraph")

    def __init__(self):
        self.nodes_offset: int | None = None
        self.links_offset: int | None = None
        self.edges_offset: int | None = None
        self.multigraph = False

    @property
    def edge_array_offset(self) -> int | None:
        """Offset of the edge array — "links" wins over legacy "edges" (#738)."""
        return self.links_offset if self.links_offset is not None else self.edges_offset


def scan_node_link(path: Path) -> NodeLinkScan:
    """One fast pass over ``path`` locating the "nodes"/"links"/"edges" arrays.

    Values are skipped, never materialized, so this is I/O-bound with a
    fixed-size buffer even on a multi-GB file.
    """
    scan = NodeLinkScan()
    with open(path, "rb") as fh:
        cur = _Cursor(fh)
        c = cur.skip_ws()
        if c is None:
            raise _malformed(path, cur, "the file is empty")
        if c != 0x7B:  # "{"
            raise _malformed(path, cur, "expected a top-level JSON object")
        cur.pos += 1
        c = cur.skip_ws()
        if c is None:
            raise _malformed(path, cur, "unterminated top-level object")
        if c == 0x7D:  # "}"
            return scan
        while True:
            c = cur.skip_ws()
            if c != 0x22:
                raise _malformed(path, cur, "expected an object key")
            key = _parse_value(cur, path)
            c = cur.skip_ws()
            if c != 0x3A:  # ":"
                raise _malformed(path, cur, f'expected ":" after key {key!r}')
            cur.pos += 1
            if cur.skip_ws() is None:
                raise _malformed(path, cur, f"missing value for key {key!r}")
            if key == "nodes":
                scan.nodes_offset = cur.tell()
                _skip_value(cur, path)
            elif key == "links":
                scan.links_offset = cur.tell()
                _skip_value(cur, path)
            elif key == "edges":
                scan.edges_offset = cur.tell()
                _skip_value(cur, path)
            elif key == "multigraph":
                scan.multigraph = bool(_parse_value(cur, path))
            else:
                _skip_value(cur, path)
            cur.compact()
            c = cur.skip_ws()
            if c == 0x2C:  # ","
                cur.pos += 1
                continue
            if c == 0x7D:
                return scan
            raise _malformed(path, cur, 'expected "," or "}" in the top-level object')


def iter_node_link_array(path: Path, offset: int):
    """Yield each element of the JSON array starting at absolute byte ``offset``.

    Memory held at any moment: one element plus the read buffer.
    """
    with open(path, "rb") as fh:
        fh.seek(offset)
        cur = _Cursor(fh, base=offset)
        c = cur.skip_ws()
        if c != 0x5B:  # "["
            raise _malformed(path, cur, "expected an array")
        cur.pos += 1
        c = cur.skip_ws()
        if c is None:
            raise _malformed(path, cur, "unterminated array")
        if c == 0x5D:  # "]"
            return
        while True:
            cur.skip_ws()
            yield _parse_value(cur, path)
            cur.compact()
            c = cur.skip_ws()
            if c == 0x2C:
                cur.pos += 1
                continue
            if c == 0x5D:
                return
            raise _malformed(path, cur, 'expected "," or "]" in array')
