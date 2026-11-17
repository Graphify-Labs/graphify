"""Java overloaded methods each get their own node (#5251).

Before this fix every overload of a method minted the same node id (the id
had no parameter types), so only the first declaration survived: callers of
a later overload were silently credited to the first one, and `affected`
returned a superset of the methods a change could actually break.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def _extract(tmp_path: Path, files: dict[str, str]) -> dict:
    paths = []
    for name, body in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        paths.append(path)
    return extract(paths, cache_root=tmp_path / "graphify-out")


def _calls(result: dict) -> set[tuple[str, str]]:
    return {
        (edge["source"], edge["target"])
        for edge in result["edges"]
        if edge.get("relation") == "calls"
    }


def _find_by_signature(result: dict, label: str, id_contains: str, signature: str) -> str:
    return next(
        node["id"] for node in result["nodes"]
        if node.get("label") == label and id_contains in node["id"]
        and (node.get("metadata") or {}).get("signature") == signature
    )


def test_overloaded_methods_get_one_node_each(tmp_path: Path):
    result = _extract(tmp_path, {
        "mini/Svc.java": (
            "class Svc {\n"
            "  void run(String s) {}\n"
            "  void run(int i) {}\n"
            "  void run(String s, int i) {}\n"
            "}\n"
        ),
    })
    run_nodes = [n for n in result["nodes"] if n.get("label") == ".run()"]
    assert len(run_nodes) == 3
    signatures = {(n.get("metadata") or {}).get("signature") for n in run_nodes}
    assert signatures == {"String", "int", "String,int"}


def test_non_overloaded_method_is_unaffected(tmp_path: Path):
    result = _extract(tmp_path, {
        "mini/Svc.java": "class Svc {\n  void run(String s) {}\n}\n",
    })
    run_nodes = [n for n in result["nodes"] if n.get("label") == ".run()"]
    assert len(run_nodes) == 1
    assert run_nodes[0]["id"].endswith("mini_svc_svc_run")


def test_receiver_qualified_call_resolves_the_literal_typed_overload(tmp_path: Path):
    result = _extract(tmp_path, {
        "mini/Svc.java": (
            "class Svc {\n"
            "  void run(String s) {}\n"
            "  void run(int i) {}\n"
            "}\n"
        ),
        "mini/Caller.java": (
            "class Caller {\n"
            "  void use() {\n"
            "    Svc svc = new Svc();\n"
            "    svc.run(\"hi\");\n"
            "    svc.run(5);\n"
            "  }\n"
            "}\n"
        ),
    })
    calls = _calls(result)
    use = next(n["id"] for n in result["nodes"] if n.get("label") == ".use()")
    run_string = _find_by_signature(result, ".run()", "svc", "String")
    run_int = _find_by_signature(result, ".run()", "svc", "int")
    assert (use, run_string) in calls
    assert (use, run_int) in calls


def test_inherited_overloaded_method_call_resolves_across_files(tmp_path: Path):
    result = _extract(tmp_path, {
        "mini/Base.java": (
            "class Base {\n"
            "  void run(String s) {}\n"
            "  void run(int i) {}\n"
            "}\n"
        ),
        "mini/Sub.java": (
            "class Sub extends Base {\n"
            "  void use() {\n"
            "    run(\"hi\");\n"
            "    run(5);\n"
            "  }\n"
            "}\n"
        ),
    })
    calls = _calls(result)
    use = next(n["id"] for n in result["nodes"] if n.get("label") == ".use()")
    run_string = _find_by_signature(result, ".run()", "base", "String")
    run_int = _find_by_signature(result, ".run()", "base", "int")
    assert (use, run_string) in calls
    assert (use, run_int) in calls


def test_net_shrink_from_removing_one_overload_is_not_lost(tmp_path: Path):
    """A deleted overload really does shrink the graph by one node, not zero,
    now that each overload is counted separately."""
    before = _extract(tmp_path / "before", {
        "mini/Svc.java": (
            "class Svc {\n"
            "  void run(String s) {}\n"
            "  void run(int i) {}\n"
            "}\n"
        ),
    })
    after = _extract(tmp_path / "after", {
        "mini/Svc.java": "class Svc {\n  void run(String s) {}\n}\n",
    })
    before_count = sum(1 for n in before["nodes"] if n.get("label") == ".run()")
    after_count = sum(1 for n in after["nodes"] if n.get("label") == ".run()")
    assert before_count == 2
    assert after_count == 1
