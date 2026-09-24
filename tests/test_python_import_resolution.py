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


def test_absolute_package_import_targets_package_init(tmp_path: Path):
    """Absolute package imports must not leave dotted-name dangling edges (#3723)."""
    files = [
        _write(tmp_path / "pkg/__init__.py", ""),
        _write(tmp_path / "pkg/sub/__init__.py", ""),
        _write(tmp_path / "pkg/sub/thing.py", "def run():\n    return 1\n"),
        _write(tmp_path / "pkg/consumer.py", "from pkg import sub\n"),
        _write(tmp_path / "user.py", "from pkg.sub import thing\n"),
    ]

    result = extract(files, cache_root=tmp_path)

    consumer = _node_id(result, "consumer.py", "pkg/consumer.py")
    user = _node_id(result, "user.py", "user.py")
    import_targets = {
        edge["target"]
        for edge in result["edges"]
        if edge["relation"] == "imports_from"
        and edge["source"] in {consumer, user}
    }

    assert {"pkg_init", "pkg_sub_init"} <= import_targets
    assert "pkg" not in import_targets
    assert "pkg_sub" not in import_targets


def test_plain_absolute_import_targets_package_module(tmp_path: Path):
    package_init = _write(tmp_path / "pkg/__init__.py", "")
    subpackage_init = _write(tmp_path / "pkg/sub/__init__.py", "")
    consumer_path = _write(tmp_path / "app.py", "import pkg.sub\n")

    result = extract(
        [package_init, subpackage_init, consumer_path],
        cache_root=tmp_path,
        root=tmp_path,
        parallel=False,
    )

    consumer = _node_id(result, "app.py", "app.py")
    subpackage = _node_id(result, "__init__.py", "pkg/sub/__init__.py")
    assert _has_edge(result, consumer, subpackage, "imports")


def test_nested_plain_import_target_is_stamped_for_incremental_remap(tmp_path: Path):
    """A changed importer can target an unchanged module outside its batch."""
    _write(tmp_path / "src/pkg/__init__.py", "")
    target = _write(tmp_path / "src/pkg/sub/__init__.py", "")
    app_path = _write(tmp_path / "src/pkg/app.py", "import pkg.sub\n")

    result = extract(
        [app_path], cache_root=tmp_path / "cache", root=tmp_path, parallel=False
    )

    app = next(
        node["id"] for node in result["nodes"] if node.get("label") == "app.py"
    )
    target_id = "src_pkg_sub_init"
    assert _has_edge(result, app, target_id, "imports")
    assert target.is_file()


def test_absolute_import_does_not_resolve_above_scan_root(tmp_path: Path):
    scan_root = tmp_path / "scan"
    source = _write(
        scan_root / "app.py",
        "from outside_pkg import thing\nimport outside_pkg\n",
    )
    _write(tmp_path / "outside_pkg/__init__.py", "")
    _write(tmp_path / "outside_pkg/thing.py", "def run():\n    return 1\n")

    result = extract(
        [source], cache_root=tmp_path / "cache", root=scan_root, parallel=False
    )

    app = _node_id(result, "app.py", "app.py")
    targets = {
        (edge["relation"], edge["target"])
        for edge in result["edges"]
        if edge["source"] == app
        and edge["relation"] in ("imports", "imports_from")
    }
    assert targets == {
        ("imports", "outside_pkg"),
        ("imports_from", "outside_pkg"),
    }


def test_absolute_from_import_keeps_namespace_package_submodule_edge(tmp_path: Path):
    namespace_package = tmp_path / "namespace_pkg"
    namespace_package.mkdir()
    submodule = _write(
        namespace_package / "subspace/worker.py", "def run():\n    return 1\n"
    )
    consumer_path = _write(
        tmp_path / "app.py", "from namespace_pkg.subspace import worker\n"
    )

    result = extract(
        [consumer_path, submodule], cache_root=tmp_path, root=tmp_path, parallel=False
    )

    consumer = _node_id(result, "app.py", "app.py")
    worker = _node_id(result, "worker.py", "namespace_pkg/subspace/worker.py")
    assert _has_edge(result, consumer, worker, "imports_from")


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


def test_issue_3777_package_module_collision_phantom_cycle_absent(tmp_path: Path):
    from graphify.analyze import find_import_cycles
    from graphify.build import build_from_json

    nettacker_py = _write(
        tmp_path / "nettacker.py",
        "from nettacker.main import run\n\ndef cli():\n    run()\n",
    )
    init_py = _write(tmp_path / "nettacker/__init__.py", "")
    main_py = _write(
        tmp_path / "nettacker/main.py",
        "from nettacker.core.app import Nettacker\n\ndef run():\n    return Nettacker()\n",
    )
    app_py = _write(
        tmp_path / "nettacker/core/app.py",
        "from nettacker import logger\n\nclass Nettacker:\n    def start(self):\n        logger.log_info('start')\n",
    )
    logger_py = _write(
        tmp_path / "nettacker/logger.py",
        "def log_info(msg):\n    print(msg)\n",
    )

    result = extract(
        [nettacker_py, init_py, main_py, app_py, logger_py],
        cache_root=tmp_path,
        root=tmp_path,
    )

    app_file = _node_id(result, "app.py", "nettacker/core/app.py")
    logger_file = _node_id(result, "logger.py", "nettacker/logger.py")
    nettacker_file = _node_id(result, "nettacker.py", "nettacker.py")

    assert _has_edge(result, app_file, logger_file, "imports_from")
    assert not _has_edge(result, app_file, nettacker_file, "imports_from")

    graph = build_from_json(result)
    assert find_import_cycles(graph) == []


def test_issue_3777_nested_module_package_collision_resolves_to_submodule(tmp_path: Path):
    from graphify.analyze import find_import_cycles
    from graphify.build import build_from_json

    runner_py = _write(
        tmp_path / "pkg/runner.py",
        "from pkg.runner.step import run\n\ndef start():\n    run()\n",
    )
    init_py = _write(tmp_path / "pkg/runner/__init__.py", "")
    step_py = _write(
        tmp_path / "pkg/runner/step.py",
        "from pkg.runner import helper\n\ndef run():\n    helper.work()\n",
    )
    helper_py = _write(
        tmp_path / "pkg/runner/helper.py",
        "def work():\n    pass\n",
    )

    result = extract(
        [runner_py, init_py, step_py, helper_py],
        cache_root=tmp_path,
        root=tmp_path,
    )

    step_file = _node_id(result, "step.py", "pkg/runner/step.py")
    helper_file = _node_id(result, "helper.py", "pkg/runner/helper.py")
    runner_file = _node_id(result, "runner.py", "pkg/runner.py")

    assert _has_edge(result, step_file, helper_file, "imports_from")
    assert not _has_edge(result, step_file, runner_file, "imports_from")

    graph = build_from_json(result)
    assert find_import_cycles(graph) == []


def test_issue_3777_namespace_package_submodule_import(tmp_path: Path):
    sub = _write(tmp_path / "ns/sub.py", "def helper():\n    pass\n")
    consumer = _write(tmp_path / "ns/consumer.py", "from ns import sub\n")

    result = extract([sub, consumer], cache_root=tmp_path, root=tmp_path)

    consumer_file = _node_id(result, "consumer.py", "ns/consumer.py")
    sub_file = _node_id(result, "sub.py", "ns/sub.py")

    assert _has_edge(result, consumer_file, sub_file, "imports_from")


def test_issue_3777_standalone_module_import_unaffected(tmp_path: Path):
    standalone = _write(tmp_path / "standalone.py", "def fn():\n    return 42\n")
    consumer = _write(tmp_path / "consumer.py", "from standalone import fn\n")

    result = extract([standalone, consumer], cache_root=tmp_path, root=tmp_path)

    consumer_file = _node_id(result, "consumer.py", "consumer.py")
    standalone_file = _node_id(result, "standalone.py", "standalone.py")
    fn_symbol = _node_id(result, "fn()", "standalone.py")

    assert _has_edge(result, consumer_file, standalone_file, "imports_from")
    assert _has_edge(result, consumer_file, fn_symbol, "imports")
