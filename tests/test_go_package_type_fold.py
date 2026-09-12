"""A Go package's type is one node even when its methods are spread across files.

``extract_go`` keys a type on its package directory, so every file declaring a method on
it mints the type again under the same id, and disambiguation then split those apart by
path — leaving one type fragmented into several partial nodes, each owning some of its
methods, which every single-definition guard downstream reads as an ambiguity. The fold
runs before disambiguation; the negative cases pin what must stay split, since the id
folds in the directory's name rather than its path and the package clause is not parsed.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from graphify.extract import extract

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("tree_sitter_go") is None,
    reason="tree_sitter_go not installed",
)


def _extract(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return extract([tmp_path / n for n in files],
                   cache_root=tmp_path / "graphify-out", parallel=False)


def _nodes(result, label: str) -> list[dict]:
    return [n for n in result["nodes"] if n["label"] == label]


def _edges_from(result, node_id: str, relation: str) -> set[str]:
    label = {n["id"]: n["label"] for n in result["nodes"]}
    return {label.get(e["target"], e["target"]) for e in result["edges"]
            if e["relation"] == relation and e["source"] == node_id}


def test_a_type_whose_methods_live_in_other_files_owns_all_of_them(tmp_path):
    result = _extract(tmp_path, {
        "svc/a.go": ("package svc\n\ntype Server struct{}\n\n"
                     "func Run(srv *Server) { srv.Close() }\n"),
        "svc/b.go": "package svc\n\nfunc (s *Server) Close() {}\n",
        "svc/c.go": "package svc\n\nfunc (s *Server) Save() {}\n",
    })
    servers = _nodes(result, "Server")
    assert len(servers) == 1, [n["id"] for n in servers]
    assert Path(str(servers[0]["source_file"])).name == "a.go"
    assert _edges_from(result, servers[0]["id"], "method") == {".Close()", ".Save()"}


def test_a_reference_to_the_type_reaches_the_node_that_owns_the_methods(tmp_path):
    result = _extract(tmp_path, {
        "svc/a.go": "package svc\n\ntype Server struct{}\n",
        "svc/b.go": "package svc\n\nfunc (s *Server) Close() {}\n",
        "svc/c.go": "package svc\n\nfunc Run(srv *Server) {}\n",
    })
    servers = _nodes(result, "Server")
    assert len(servers) == 1, [n["id"] for n in servers]
    refs = [e for e in result["edges"]
            if e["relation"] == "references" and e["target"] == servers[0]["id"]]
    assert refs, "the parameter type must reference the one Server node"
    assert _edges_from(result, servers[0]["id"], "method") == {".Close()"}


def test_the_declaring_file_survives_a_lower_sorting_method_file(tmp_path):
    result = _extract(tmp_path, {
        "svc/a.go": "package svc\n\nfunc (s *Server) Close() {}\n",
        "svc/z.go": "package svc\n\ntype Server struct{}\n",
    })
    servers = _nodes(result, "Server")
    assert len(servers) == 1, [n["id"] for n in servers]
    assert Path(str(servers[0]["source_file"])).name == "z.go"


def test_two_packages_sharing_a_directory_name_stay_split(tmp_path):
    result = _extract(tmp_path, {
        "a/svc/x.go": "package svc\n\ntype Server struct{}\n\nfunc (s *Server) Save() {}\n",
        "b/svc/y.go": "package svc\n\nfunc (s *Server) Close() {}\n",
    })
    assert len(_nodes(result, "Server")) == 2


def test_an_external_test_package_in_the_same_directory_stays_split(tmp_path):
    result = _extract(tmp_path, {
        "svc/a.go": "package svc\n\ntype Fixture struct{}\n\nfunc (f *Fixture) Save() {}\n",
        "svc/a_test.go": ("package svc_test\n\ntype Fixture struct{}\n\n"
                          "func (f *Fixture) Reset() {}\n"),
    })
    assert len(_nodes(result, "Fixture")) == 2


def test_a_function_and_a_method_of_the_same_name_are_untouched(tmp_path):
    # The fold only ever considers bare type labels, so a package whose helper and method
    # share a name keeps both nodes.
    result = _extract(tmp_path, {
        "svc/a.go": "package svc\n\ntype Server struct{}\n\nfunc Close() {}\n",
        "svc/b.go": "package svc\n\nfunc (s *Server) Close() {}\n",
    })
    assert len(_nodes(result, "Close()")) == 1
    assert len(_nodes(result, ".Close()")) == 1
