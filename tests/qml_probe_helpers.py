"""Nonshipping QML-00 AST inspection and fresh-process offline probe helpers."""
from __future__ import annotations

from collections.abc import Iterator
from typing import overload

from tree_sitter import Node


def walk(root: Node) -> Iterator[Node]:
    """Visit every concrete node, including errors and missing syntax tokens."""
    pending = [root]
    while pending:
        node = pending.pop()
        yield node
        pending.extend(reversed(node.children))


def nodes(root: Node, kind: str) -> list[Node]:
    return [node for node in walk(root) if node.type == kind]


@overload
def text(node: Node) -> str: ...


@overload
def text(node: None) -> None: ...


def text(node: Node | None) -> str | None:
    if node is None:
        return None
    content = node.text
    assert content is not None, "Probe nodes retain their original parsed source"
    return content.decode("utf-8")


def field_text(node: Node, field: str) -> str | None:
    return text(node.child_by_field_name(field))


def point_at(source: bytes, offset: int) -> tuple[int, int]:
    """Calculate rows and byte columns independently from Tree-sitter nodes."""
    prefix = source[:offset]
    return prefix.count(b"\n"), offset - (prefix.rfind(b"\n") + 1)


# The child starts with isolated Python, an empty working/cache directory, and an
# audit hook installed before parser imports. This proves Python-network-free
# installed invocation, rather than claiming an OS-wide network sandbox.
OFFLINE_PROBE = r'''
import json
from pathlib import Path
import socket
import sys

def deny_external_execution(event, args):
    if event in {"socket.connect", "socket.getaddrinfo", "subprocess.Popen", "os.system"}:
        raise RuntimeError("QML-00 external execution denied")

sys.addaudithook(deny_external_execution)
try:
    socket.create_connection(("127.0.0.1", 9))
except RuntimeError:
    network_denied = True
else:
    raise AssertionError("network guard did not reject the control attempt")

from tree_sitter import Language, Parser
from tree_sitter_language_pack import get_binding, get_parser

fixtures = Path(sys.argv[1])
results = {}
for name, filename in (("qmljs", "Main.qml"), ("qmldir", "qmldir")):
    parser = Parser(Language(get_binding(name)))
    source = (fixtures / filename).read_bytes()
    root = parser.parse(source).root_node
    results[name] = {"has_error": root.has_error, "end_byte": root.end_byte, "size": len(source)}
try:
    get_parser("qml_probe_missing_grammar")
except LookupError:
    unavailable = "LookupError"
else:
    raise AssertionError("missing grammar unexpectedly succeeded")
print(json.dumps({"network_denied": network_denied, "unavailable": unavailable, "results": results}))
'''
