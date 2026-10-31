"""Regression for #4269: a qualified external annotation must not bind to an
unrelated private local class through the stub-rewire underscore collision.

`def read_body(response: httpx.Response)` names an external type. A private
`class _Response` defined in a test file used to absorb that reference because
the stub-rewire key stripped the leading underscore, making `_Response` and
`Response` compare equal. The result was a fabricated, EXTRACTED-confidence
edge from production code to test code.
"""
from __future__ import annotations

from pathlib import Path

from graphify.build import build_from_json
from graphify.extract import extract


def _edge_set(G):
    return {
        (d.get("relation"), d.get("_src", u), d.get("_tgt", v))
        for u, v, d in G.edges(data=True)
    }


def test_qualified_annotation_does_not_bind_to_private_local_class(tmp_path: Path) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "app" / "client.py").write_text(
        "import httpx\n\n\n"
        "def read_body(response: httpx.Response) -> bytes:\n"
        "    return response.content\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "test_fake.py").write_text(
        "class _Response:\n"
        '    """Stand-in for a urllib response."""\n\n'
        "    def read(self):\n"
        '        return b""\n',
        encoding="utf-8",
    )

    paths = [tmp_path / "app" / "client.py", tmp_path / "tests" / "test_fake.py"]
    res = extract(paths, root=tmp_path, parallel=False, cache_root=tmp_path / "graphify-cache")
    G = build_from_json(res, root=str(tmp_path), directed=True)
    edges = _edge_set(G)

    # The fabricated production -> test edge must be gone.
    assert ("references", "app_client_read_body", "tests_test_fake_response") not in edges, (
        f"httpx.Response annotation falsely bound to the private local _Response: {edges}"
    )
    # The private class must still exist as its own node, untouched.
    assert "tests_test_fake_response" in G


def test_bare_underscore_class_does_not_absorb_sibling_reference(tmp_path: Path) -> None:
    """Minimal rewire control: a sourceless `Thing` reference must not rewire to a
    located `_Thing`; underscores are identifier-significant."""
    (tmp_path / "producer.py").write_text(
        "import external\n\n\n"
        "def build(x: external.Thing) -> None:\n"
        "    return None\n",
        encoding="utf-8",
    )
    (tmp_path / "private.py").write_text(
        "class _Thing:\n"
        "    pass\n",
        encoding="utf-8",
    )
    paths = [tmp_path / "producer.py", tmp_path / "private.py"]
    res = extract(paths, root=tmp_path, parallel=False, cache_root=tmp_path / "graphify-cache")
    G = build_from_json(res, root=str(tmp_path), directed=True)
    edges = _edge_set(G)
    assert ("references", "producer_build", "private_thing") not in edges, (
        f"`external.Thing` reference falsely absorbed by the private `_Thing`: {edges}"
    )
