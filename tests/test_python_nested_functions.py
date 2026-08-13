"""Regression tests: Python functions nested inside another function.

The generic walk's function branch returns without recursing into the body, so a
`def` inside another `def` got no node at all. Because walk_calls also stops at
`function_boundary_types`, every call in that inner body was dropped rather than
attributed to the outer function — a FastAPI endpoint whose whole implementation
lives in `async def generate()` showed up in the graph as a near-leaf with two or
three edges.

Python now emits a node per nested definition, owned by the function it lives in
(`contains`, id qualified by the owner so `outer.helper` stays distinct from a
module-level `helper`), and its calls are attributed to it. Languages whose idiom
is inline callbacks stay opt-out via `LanguageConfig.extract_nested_functions`.
"""
from pathlib import Path

from graphify.extract import _file_stem, _make_id, extract_python


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "mod.py"
    path.write_text(text, encoding="utf-8")
    return path


def _nid(path: Path, *parts: str) -> str:
    nid = _file_stem(path)
    for part in parts:
        nid = _make_id(nid, part)
    return nid


def _labels(result: dict) -> set[str]:
    return {n["label"] for n in result["nodes"]}


def _calls(result: dict, source: str) -> set[str]:
    by_id = {n["id"]: n for n in result["nodes"]}
    return {
        by_id.get(e["target"], {}).get("label", e["target"])
        for e in result["edges"]
        if e["source"] == source and e["relation"] == "calls"
    }


def test_nested_def_gets_a_node(tmp_path):
    path = _write(tmp_path, """
def outer():
    def inner():
        pass
    return inner
""")
    result = extract_python(path)
    assert "inner()" in _labels(result)


def test_nested_def_is_contained_by_its_owner_not_the_file(tmp_path):
    path = _write(tmp_path, """
def outer():
    def inner():
        pass
""")
    result = extract_python(path)
    outer = _nid(path, "outer")
    inner = _nid(path, "outer", "inner")
    contains = {
        (e["source"], e["target"])
        for e in result["edges"]
        if e["relation"] == "contains"
    }
    assert (outer, inner) in contains
    assert (_make_id(str(path)), inner) not in contains


def test_nested_id_does_not_collide_with_module_level_same_name(tmp_path):
    path = _write(tmp_path, """
def helper():
    pass

def outer():
    def helper():
        pass
""")
    result = extract_python(path)
    ids = {n["id"] for n in result["nodes"]}
    assert _nid(path, "helper") in ids
    assert _nid(path, "outer", "helper") in ids


def test_calls_in_a_nested_body_are_attributed_to_the_nested_def(tmp_path):
    path = _write(tmp_path, """
def target():
    pass

def outer():
    def inner():
        target()
""")
    result = extract_python(path)
    assert _calls(result, _nid(path, "outer", "inner")) == {"target()"}
    # ...and not to the enclosing function, which calls nothing itself.
    assert _calls(result, _nid(path, "outer")) == set()


def test_nesting_recurses_past_one_level(tmp_path):
    path = _write(tmp_path, """
def target():
    pass

def outer():
    def middle():
        def inner():
            target()
""")
    result = extract_python(path)
    assert _calls(result, _nid(path, "outer", "middle", "inner")) == {"target()"}


def test_def_nested_under_a_control_block_is_found(tmp_path):
    """The inner def sits under `if`/`try`, not directly in the body block."""
    path = _write(tmp_path, """
def target():
    pass

def outer(flag):
    if flag:
        def inner():
            target()
    return inner
""")
    result = extract_python(path)
    assert _calls(result, _nid(path, "outer", "inner")) == {"target()"}


def test_async_generator_inside_endpoint_keeps_its_calls(tmp_path):
    """The shape this fixes: a streaming endpoint delegating to an inner async def."""
    path = _write(tmp_path, """
def build_context():
    pass

def render(chunk):
    pass

async def chat_stream(request):
    async def generate():
        ctx = build_context()
        for chunk in ctx:
            render(chunk)
    return generate
""")
    result = extract_python(path)
    assert _calls(result, _nid(path, "chat_stream", "generate")) == {
        "build_context()", "render()",
    }


def test_method_local_def_is_owned_by_the_method(tmp_path):
    path = _write(tmp_path, """
def target():
    pass

class Service:
    def run(self):
        def step():
            target()
""")
    result = extract_python(path)
    run_nid = _make_id(_nid(path, "Service"), "run")
    assert _calls(result, _make_id(run_nid, "step")) == {"target()"}


def test_js_still_skips_nested_function_declarations(tmp_path):
    """extract_nested_functions is opt-in; JS/TS keeps its arrow-function handling."""
    from graphify.extract import extract_js

    path = tmp_path / "mod.js"
    path.write_text(
        "function outer() {\n  function inner() {}\n  return inner;\n}\n",
        encoding="utf-8",
    )
    result = extract_js(path)
    assert "inner()" not in _labels(result)
