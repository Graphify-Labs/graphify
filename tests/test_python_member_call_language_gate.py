"""The Python member-call pass binds Python callers to Python definitions only.

`_resolve_python_member_calls` walks every raw call of the corpus and folds labels
to bare alphanumerics, so before the gate a Swift `Inner.go()` bound a Python
`Inner`, a Python `Inner.go()` bound a Swift `Inner`, and `SwiftArray.make()`
bound a Swift node labelled `Swift.Array`. Python-to-Python edges, including a
file mapped to Python through `.graphifyrc`, must stay as they were.
"""

import pytest

from graphify.extract import _resolve_python_member_calls, extract
from graphify.rcfile import set_language_overrides


@pytest.fixture(autouse=True)
def reset_overrides():
    set_language_overrides(None)
    yield
    set_language_overrides(None)


def _class_with_method(prefix, class_label, source_file, method="go"):
    """File node, class node and one method node, with contains/method edges."""
    file_nid, class_nid, method_nid = prefix, f"{prefix}_cls", f"{prefix}_cls_{method}"
    nodes = [
        {"id": file_nid, "label": source_file, "source_file": source_file},
        {"id": class_nid, "label": class_label, "source_file": source_file},
        {"id": method_nid, "label": f".{method}()", "source_file": source_file},
    ]
    edges = [
        {"source": file_nid, "target": class_nid, "relation": "contains"},
        {"source": class_nid, "target": method_nid, "relation": "method"},
    ]
    return nodes, edges, method_nid


def _caller(prefix, source_file):
    file_nid, caller_nid = prefix, f"{prefix}_run"
    nodes = [
        {"id": file_nid, "label": source_file, "source_file": source_file},
        {"id": caller_nid, "label": "run()", "source_file": source_file},
    ]
    edges = [{"source": file_nid, "target": caller_nid, "relation": "contains"}]
    return nodes, edges, caller_nid


def _member_call(caller_nid, receiver, callee, source_file):
    return {"caller_nid": caller_nid, "receiver": receiver, "callee": callee,
            "is_member_call": True, "source_file": source_file, "source_location": "L2"}


def _resolve(caller_file, class_label, class_file, receiver="Inner"):
    c_nodes, c_edges, caller_nid = _caller("use", caller_file)
    k_nodes, k_edges, method_nid = _class_with_method("inner", class_label, class_file)
    nodes, edges = c_nodes + k_nodes, c_edges + k_edges
    raw = _member_call(caller_nid, receiver, "go", caller_file)
    _resolve_python_member_calls([{"raw_calls": [raw]}], nodes, edges)
    return [e for e in edges if e.get("relation") == "calls"
            and e["source"] == caller_nid and e["target"] == method_nid]


def test_swift_caller_does_not_bind_python_class():
    assert _resolve("app.swift", "Inner", "lib.py") == []


def test_python_caller_does_not_bind_swift_class():
    assert _resolve("use.py", "Inner", "inner.swift") == []


def test_python_caller_does_not_bind_folded_swift_extension_label():
    # `_key` folds `Swift.Array` to `swiftarray`, the same key as `SwiftArray`.
    assert _resolve("use.py", "Swift.Array", "ext.swift", receiver="SwiftArray") == []


def test_python_caller_still_binds_python_class():
    edges = _resolve("use.py", "Inner", "lib.py")
    assert len(edges) == 1
    assert edges[0]["confidence"] == "EXTRACTED"


def test_extensionless_caller_still_binds_python_class():
    # A shebang script has no suffix; its language is unknown here, so it passes.
    assert len(_resolve("bin/tool", "Inner", "lib.py")) == 1


def test_unknown_suffix_caller_still_binds_python_class():
    # No extractor owns `.unknown`, so its language is unknown and it passes.
    assert len(_resolve("use.unknown", "Inner", "lib.py")) == 1


def test_python_caller_still_binds_unknown_suffix_class():
    assert len(_resolve("use.py", "Inner", "lib.unknown")) == 1


def _calls(result):
    nodes = {n["id"]: n for n in result["nodes"]}
    return {(nodes[e["source"]].get("label"), nodes[e["source"]].get("source_file"),
             nodes[e["target"]].get("label"), nodes[e["target"]].get("source_file"))
            for e in result["edges"]
            if e["relation"] == "calls" and e["source"] in nodes and e["target"] in nodes}


LIB = "class Inner:\n    @staticmethod\n    def go():\n        return 1\n"
MAIN = "from lib import Inner\n\ndef use():\n    return Inner.go()\n"


def test_python_to_python_member_call_binds_in_mixed_corpus(tmp_path):
    (tmp_path / "lib.py").write_text(LIB)
    (tmp_path / "main.py").write_text(MAIN)
    # A distinct Swift class name: a second `Inner` would trip the pass's
    # single-definition guard and drop the Python edge, as before the gate.
    (tmp_path / "widget.swift").write_text("class Widget {\n    static func go() {}\n}\n")
    (tmp_path / "use.py").write_text("def run():\n    Widget.go()\n")
    paths = [tmp_path / name for name in ("lib.py", "main.py", "widget.swift", "use.py")]
    calls = _calls(extract(paths, root=tmp_path, cache_root=tmp_path))
    assert ("use()", "main.py", ".go()", "lib.py") in calls
    assert not any(src == "use.py" and dst == "widget.swift" for _, src, _, dst in calls)


def test_file_mapped_to_python_by_graphifyrc_still_binds(tmp_path):
    (tmp_path / ".graphifyrc").write_text("language.pyx=python\n")
    (tmp_path / "lib.pyx").write_text(LIB)
    (tmp_path / "main.pyx").write_text(MAIN)
    paths = [tmp_path / "lib.pyx", tmp_path / "main.pyx"]
    calls = _calls(extract(paths, root=tmp_path, cache_root=tmp_path))
    assert ("use()", "main.pyx", ".go()", "lib.pyx") in calls


def test_same_named_swift_class_does_not_block_python_binding(tmp_path):
    # Only Python classes count for the single-definition guard, so a Swift
    # `Inner` neither steals the call nor suppresses the Python edge.
    (tmp_path / "lib.py").write_text(LIB)
    (tmp_path / "main.py").write_text(MAIN)
    (tmp_path / "inner.swift").write_text("class Inner {\n    static func go() {}\n}\n")
    (tmp_path / "use.py").write_text("def run():\n    Inner.go()\n")
    paths = [tmp_path / name for name in ("lib.py", "main.py", "inner.swift", "use.py")]
    calls = _calls(extract(paths, root=tmp_path, cache_root=tmp_path))
    assert ("use()", "main.py", ".go()", "lib.py") in calls
    assert not any(src.endswith(".py") and dst == "inner.swift" for _, src, _, dst in calls)


def test_two_python_classes_with_the_same_name_still_bind_nothing():
    c_nodes, c_edges, caller_nid = _caller("use", "use.py")
    a_nodes, a_edges, _ = _class_with_method("a", "Inner", "a.py")
    b_nodes, b_edges, _ = _class_with_method("b", "Inner", "b.py")
    nodes, edges = c_nodes + a_nodes + b_nodes, c_edges + a_edges + b_edges
    raw = _member_call(caller_nid, "Inner", "go", "use.py")
    _resolve_python_member_calls([{"raw_calls": [raw]}], nodes, edges)
    assert not any(e.get("relation") == "calls" for e in edges)
