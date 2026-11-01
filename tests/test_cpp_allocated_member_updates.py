"""INC-QML-101: actual allocated member proof survives refresh and failed publication."""
from __future__ import annotations

from collections import Counter
import errno
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import pytest

import graphify
from graphify.extract import extract
from graphify.paths import load_node_link_graph
from graphify.watch import _rebuild_code
from tests.test_qt_final_incremental_parity import endpoints, manual_update, normalized, run, unrelated
from tests.test_qt_semantic_correction_updates import products


def project(root, *, invokable=True, ordinary=False):
    marker = "Q_INVOKABLE " if invokable else ""
    header = root / "native.hpp"
    header.write_bytes(("\ufeff// π allocated source\nclass Hpp;\n"
                        "class Hpp : public QObject { Q_OBJECT QML_NAMED_ELEMENT(Widget)\n"
                        f"public: {marker}void ping() {{}}\n}};\n"
                        + ("void ping() {}\n" if ordinary else "")).encode())
    qml = root / "Main.qml"
    qml.write_text("import Public.Allocated 1.0\nWidget { function run() { ping() } }", encoding="utf-8")
    cmake = root / "CMakeLists.txt"
    cmake.write_text("qt_add_qml_module(app URI Public.Allocated VERSION 1.0 QML_FILES Main.qml SOURCES native.hpp)", encoding="utf-8")
    (root / "keep.py").write_text("def helper():return 1\n\ndef retained():return helper()\n", encoding="utf-8")
    return header, qml, cmake


def calls(graph):
    return [(source, target, data) for source, target, data in graph.edges(data=True)
            if data.get("context") == "qml_js_call"]


def full_fields(graph):
    """Compare all attributes; only unpromised legacy undirected orientation is canonicalized."""
    return ({identity: json.dumps(data, sort_keys=True, ensure_ascii=False)
             for identity, data in graph.nodes(data=True)},
            Counter((*endpoints(graph, source, target, data), json.dumps(data, sort_keys=True, ensure_ascii=False))
                    for source, target, data in graph.edges(data=True)))


# The output setting is read before imports. A new process retains the actual
# same-root raw CLI/watch owner without moving a potentially open accepted tree.
# Static code plus literal argv keeps analyzed source/CWD outside the harness.
_COLD_PROGRAM = """
import json
from pathlib import Path
import sys
package_parent, root_text, operation, identity_text = sys.argv[1:]
sys.path.insert(0, package_parent)
import graphify
assert Path(graphify.__file__).resolve() == Path(package_parent, "graphify", "__init__.py").resolve()
from graphify.paths import GRAPHIFY_OUT
root = Path(root_text).resolve()
output = Path(GRAPHIFY_OUT).resolve()
Path(identity_text).write_text(json.dumps({
    "package_file": str(Path(graphify.__file__).resolve()),
    "analysis_root": str(root), "output": str(output),
    "output_existed": output.exists(), "isolated": bool(sys.flags.isolated),
    "operation": operation,
}), encoding="utf-8")
if operation == "manual":
    import graphify.__main__ as entrypoint
    entrypoint._check_skill_version = lambda *_: None
    entrypoint._refresh_stale_skills = lambda: None
    sys.argv = ["graphify", "update", str(root), "--no-cluster"]
    entrypoint.main()
elif operation == "watch":
    from graphify.watch import _rebuild_code
    sys.exit(0 if _rebuild_code(root, no_cluster=True) else 1)
else:
    raise ValueError("unsupported cold-reference operation")
"""


def cold_reference(root, monkeypatch, operation):
    """Publish cold raw evidence beside the corpus; accepted output is never moved.

    The same analysis root preserves IDs and source provenance. An isolated child
    selects the parent's admitted package explicitly and honors GRAPHIFY_OUT
    before imports. Logs and outputs remain inspectable on both success/failure.
    """
    assert operation in {"manual", "watch"}
    root = root.resolve()
    output = root / "graphify-out"
    retained = Path(tempfile.mkdtemp(prefix="allocated-member-products-", dir=root.parent)).resolve()
    reference, identity_path = retained / "cold-reference", retained / "identity.json"
    assert output.is_dir() and not reference.exists() and retained.parent == root.parent
    before = {str(path.relative_to(output)): path.read_bytes()
              for path in output.rglob("*") if path.is_file()}
    package_file = Path(graphify.__file__).resolve()
    command = [sys.executable, "-I", "-X", "utf8", "-c", _COLD_PROGRAM,
               str(package_file.parent.parent), str(root), operation, str(identity_path)]
    env = dict(os.environ, GRAPHIFY_OUT=str(reference), GRAPHIFY_NO_AUTO_REFRESH="1", GRAPHIFY_NO_TIPS="1")
    try:
        with (retained / "child.log").open("wb") as log:
            child = subprocess.run(command, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT)
        child.check_returncode()
        identity = json.loads(identity_path.read_text(encoding="utf-8"))
        assert identity == {"package_file": str(package_file), "analysis_root": str(root),
                            "output": str(reference), "output_existed": False,
                            "isolated": True, "operation": operation}
        return load_node_link_graph(reference / "graph.json")
    finally:
        assert {str(path.relative_to(output)): path.read_bytes()
                for path in output.rglob("*") if path.is_file()} == before


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_allocated_member_cpp_and_qml_updates_remove_stale_endpoint_then_recover(tmp_path, monkeypatch, operation):
    """C++-only removal and later QML-only repair use fresh proof rather than the old salted method."""
    header, qml, _ = project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    assert len(calls(initial)) == 1
    old_target = calls(initial)[0][1]
    header.write_bytes(header.read_bytes().replace(b"ping", b"pong"))
    removed = run(tmp_path, monkeypatch, operation, [header])
    assert not calls(removed) and old_target not in removed
    qml.write_bytes(qml.read_bytes().replace(b"ping", b"pong"))
    recovered = run(tmp_path, monkeypatch, operation, [qml])
    assert len(calls(recovered)) == 1 and calls(recovered)[0][1] != old_target
    assert full_fields(recovered) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    assert unrelated(initial) == unrelated(recovered)
    before = products(tmp_path)
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(recovered)
    assert products(tmp_path) == before


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_allocated_member_graph_write_failure_retains_products_and_retries(tmp_path, monkeypatch, operation):
    """A real graph replacement error cannot commit refreshed allocator/member evidence early."""
    header, _, _ = project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    assert len(calls(initial)) == 1
    before = products(tmp_path)
    header.write_bytes(header.read_bytes().replace(b"void ping() {}", b"void ping() {} int added;"))
    replace = os.replace

    def failure(source, target):
        if Path(target).resolve() == (tmp_path / "graphify-out/graph.json").resolve():
            raise OSError(errno.EIO, "isolated allocated-member publication failure")
        return replace(source, target)

    with monkeypatch.context() as scoped:
        scoped.setattr(os, "replace", failure)
        if operation == "manual":
            with pytest.raises(SystemExit) as rejected:
                manual_update(tmp_path, monkeypatch)
            assert rejected.value.code == 1
        else:
            assert not _rebuild_code(tmp_path, changed_paths=[header], no_cluster=True)
    assert products(tmp_path) == before
    recovered = run(tmp_path, monkeypatch, operation, [header])
    assert len(calls(recovered)) == 1
    assert full_fields(recovered) == full_fields(cold_reference(tmp_path, monkeypatch, operation))


def test_req_qml022_ac02_noninvokable_member_cannot_borrow_same_named_global_callable(tmp_path):
    """Correct source stamping leaves native exposure and own-metaobject gates authoritative."""
    paths = project(tmp_path, invokable=False, ordinary=True)
    result = extract(list(paths), root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not result["failed_sources"] and not result.get("qml_failures")
    assert not any(edge.get("context") == "qml_js_call" for edge in result["edges"])
