"""`definition_file` is portable, like its sibling `source_file` (#3223).

The #2990 decl/def merge stamps `definition_file` from the implementation's
then-absolute `source_file` — and nothing ever relativized it. graph.json
shipped `"source_file": "src/Foo.h"` beside
`"definition_file": "/home/ci/build/.../src/Foo.cpp"`: a path no other
machine can open, leaking the build host's layout into every consumer,
including MCP `get_node`'s "Defined in:" line.
"""
from __future__ import annotations

import io
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

from graphify.build import build_from_json
from graphify.cache import _absolutize_source_files_in, _relativize_source_files_in
from graphify.extract import extract

FOO_H = "#pragma once\n\nclass Foo {\npublic:\n    int Bar(int x);\n};\n"
FOO_CPP = '#include "Foo.h"\n\nint Foo::Bar(int x) {\n    return x + 1;\n}\n'


def _decl_def_graph(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "Foo.h").write_text(FOO_H, encoding="utf-8")
    (src / "Foo.cpp").write_text(FOO_CPP, encoding="utf-8")
    with redirect_stdout(io.StringIO()):
        r = extract([src / "Foo.h", src / "Foo.cpp"], cache_root=Path(tempfile.mkdtemp()),
                    root=tmp_path, parallel=False)
    G = build_from_json({"nodes": r["nodes"], "edges": r["edges"], "hyperedges": []},
                        root=str(tmp_path))
    return G


def test_the_issues_repro_yields_a_relative_definition_file(tmp_path):
    G = _decl_def_graph(tmp_path)
    carriers = [(n, d) for n, d in G.nodes(data=True) if d.get("definition_file")]
    assert carriers, "the decl/def pair must produce a definition_file carrier"
    for _n, d in carriers:
        df = str(d["definition_file"]).replace("\\", "/")
        assert df == "src/Foo.cpp", df
        assert str(d.get("source_file", "")).replace("\\", "/") == "src/Foo.h"


def test_build_normalizes_a_prebuilt_absolute_definition_file(tmp_path):
    impl = tmp_path / "src" / "Foo.cpp"
    impl.parent.mkdir()
    impl.write_text(FOO_CPP, encoding="utf-8")
    G = build_from_json({
        "nodes": [{"id": "n", "label": "Bar", "file_type": "code",
                   "source_file": str(tmp_path / "src" / "Foo.h"),
                   "definition_file": str(impl)}],
        "edges": [], "hyperedges": [],
    }, root=str(tmp_path))
    d = G.nodes["n"]
    assert str(d["definition_file"]).replace("\\", "/") == "src/Foo.cpp"


def test_an_out_of_root_definition_file_is_left_alone(tmp_path):
    outside = tmp_path.parent / "elsewhere.cpp"
    G = build_from_json({
        "nodes": [{"id": "n", "label": "Bar", "file_type": "code",
                   "source_file": "src/Foo.h",
                   "definition_file": str(outside)}],
        "edges": [], "hyperedges": [],
    }, root=str(tmp_path))
    # out-of-root stays absolute; separators are normalized like source_file's
    assert Path(G.nodes["n"]["definition_file"]) == outside


def test_cache_round_trip_keeps_definition_file_portable(tmp_path):
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    f = root / "src" / "Foo.cpp"
    f.write_text(FOO_CPP, encoding="utf-8")
    payload = {"nodes": [{"id": "n", "source_file": str(root / "src" / "Foo.h"),
                          "definition_file": str(f)}],
               "edges": []}
    _relativize_source_files_in(payload, root)
    stored = payload["nodes"][0]
    assert stored["definition_file"] == "src/Foo.cpp"
    assert stored["source_file"] == "src/Foo.h"
    _absolutize_source_files_in(payload, root)
    restored = payload["nodes"][0]
    assert Path(restored["definition_file"]) == root / "src" / "Foo.cpp"
    assert Path(restored["source_file"]) == root / "src" / "Foo.h"
