from __future__ import annotations

from pathlib import Path

from graphify.extract import extract
from graphify.extractors.resolution import _resolve_python_module_path


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _node_id(result: dict, label: str, source_file: str) -> str:
    matches = [
        node["id"]
        for node in result["nodes"]
        if node.get("label") == label and node.get("source_file") == source_file
    ]
    assert len(matches) == 1
    return matches[0]


def _has_edge(result: dict, source: str, target: str, relation: str) -> bool:
    return any(
        edge["source"] == source
        and edge["target"] == target
        and edge["relation"] == relation
        for edge in result["edges"]
    )


def test_overdeep_relative_import_is_unresolved_not_fatal(tmp_path: Path):
    source = _write(
        tmp_path / "pkg" / "mod.py",
        "from ........................... import missing\n\n"
        "def ok():\n"
        "    return 1\n",
    )

    assert _resolve_python_module_path("", source, tmp_path, level=27) is None

    result = extract([source], cache_root=tmp_path)

    assert _node_id(result, "mod.py", "pkg/mod.py")
    assert _node_id(result, "ok()", "pkg/mod.py")


def test_ordinary_relative_import_still_resolves(tmp_path: Path):
    target = _write(tmp_path / "pkg" / "sibling.py", "def helper():\n    return 1\n")
    source = _write(tmp_path / "pkg" / "mod.py", "from .sibling import helper\n")

    assert _resolve_python_module_path("sibling", source, tmp_path, level=1) == target

    result = extract([source, target], cache_root=tmp_path)
    source_file = _node_id(result, "mod.py", "pkg/mod.py")
    target_symbol = _node_id(result, "helper()", "pkg/sibling.py")

    assert _has_edge(result, source_file, target_symbol, "imports")


def test_relative_subpackage_import_from_targets_package_init(tmp_path: Path):
    # `from ...graphs import build_graph` where `graphs/` is a package (a dir
    # with __init__.py, not a graphs.py module). The imports_from edge must
    # target the package's __init__.py file node, matching the companion
    # `imports` edge — not an absolute-scan-path slug for a nonexistent
    # graphs.py that dangles per-checkout (#2455).
    init = _write(tmp_path / "src/mypkg/__init__.py", "")
    api_init = _write(tmp_path / "src/mypkg/api/__init__.py", "")
    routes_init = _write(tmp_path / "src/mypkg/api/routes/__init__.py", "")
    graphs_init = _write(
        tmp_path / "src/mypkg/graphs/__init__.py",
        "def build_graph():\n    return {}\n",
    )
    health = _write(
        tmp_path / "src/mypkg/api/routes/health.py",
        "from ...graphs import build_graph\n",
    )

    result = extract(
        [init, api_init, routes_init, graphs_init, health], cache_root=tmp_path
    )

    health_file = _node_id(result, "health.py", "src/mypkg/api/routes/health.py")
    graphs_pkg = _node_id(result, "__init__.py", "src/mypkg/graphs/__init__.py")

    assert _has_edge(result, health_file, graphs_pkg, "imports_from")
    # No imports_from edge out of health may carry an unresolved absolute-path
    # slug (the pre-fix `<scan>_src_mypkg_graphs_py` target).
    health_targets = [
        e["target"]
        for e in result["edges"]
        if e["source"] == health_file and e["relation"] == "imports_from"
    ]
    assert all(t.endswith("graphs_init") for t in health_targets), health_targets


def test_python_package_reexport_resolves_import_and_call_to_origin_symbol(tmp_path: Path):
    origin = _write(tmp_path / "pkg/foo.py", "def Foo():\n    return 1\n")
    barrel = _write(tmp_path / "pkg/__init__.py", "from .foo import Foo as PublicFoo\n")
    consumer = _write(
        tmp_path / "app.py",
        "from pkg import PublicFoo\n\n"
        "def X():\n"
        "    return PublicFoo()\n",
    )

    result = extract([origin, barrel, consumer], cache_root=tmp_path)

    origin_file = _node_id(result, "foo.py", "pkg/foo.py")
    barrel_file = _node_id(result, "__init__.py", "pkg/__init__.py")
    consumer_file = _node_id(result, "app.py", "app.py")
    origin_symbol = _node_id(result, "Foo()", "pkg/foo.py")
    consumer_symbol = _node_id(result, "X()", "app.py")

    assert _has_edge(result, barrel_file, origin_file, "re_exports")
    assert _has_edge(result, consumer_file, origin_symbol, "imports")
    assert _has_edge(result, consumer_symbol, origin_symbol, "calls")


def test_python_parameter_return_and_generic_contexts(tmp_path: Path):
    model = tmp_path / "pkg" / "model.py"
    model.parent.mkdir(parents=True)
    model.write_text(
        "class Payload:\n"
        "    pass\n\n"
        "class Result:\n"
        "    pass\n",
        encoding="utf-8",
    )
    service = tmp_path / "pkg" / "service.py"
    service.write_text(
        "from .model import Payload, Result\n\n"
        "def process(item: Payload) -> Result:\n"
        "    return Result()\n\n"
        "def process_many(items: list[Payload]) -> Result:\n"
        "    return Result()\n",
        encoding="utf-8",
    )

    result = extract([model, service], cache_root=tmp_path)
    labels = {node["id"]: node["label"] for node in result["nodes"]}
    edges = [edge for edge in result["edges"] if edge.get("relation") == "references"]
    pairs = {
        (labels.get(e["source"], e["source"]), labels.get(e["target"], e["target"]), e.get("context"))
        for e in edges
    }

    assert ("process()", "Payload", "parameter_type") in pairs
    assert ("process()", "Result", "return_type") in pairs
    assert ("process_many()", "Payload", "generic_arg") in pairs
