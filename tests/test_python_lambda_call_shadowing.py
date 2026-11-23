"""Python lambda parameters shadow callable names only in their body."""

import json
from pathlib import Path

import pytest

from graphify.extract import extract, extract_python
from graphify.watch import _rebuild_code

_HANDLER = "def handler(*args): return 1\n"
_PROBE = """\
def accept(value=None): return value
def helper(): return 2
def dispatch(callback): return callback()

def passed():
    return lambda handler: accept(handler)

def invoked():
    return lambda handler: handler(helper(), accept(value=handler))

def nested():
    return lambda handler: (lambda value=accept(handler): handler())

def closure():
    def captured(): return 3
    return lambda handler: dispatch(captured)
"""
_CONTROLS = """\
def default_value():
    return lambda callback=(
        dispatch(callback)
    ): accept(callback)

def default_call():
    return lambda callback=(
        callback()
    ): callback()

def outside():
    return dispatch(callback)

def alias_call():
    return alias()

def relative_call():
    from .callbacks import support as local_alias
    return local_alias()
"""
_CALLBACKS = "def callback(): return 4\ndef support(): return 5\n"


def _write_corpus(root: Path, placement: str) -> tuple[Path, Path, str]:
    pkg = root / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").touch()
    (pkg / "callbacks.py").write_text(_CALLBACKS, encoding="utf-8")
    caller = pkg / "probe.py"
    caller_source = "from .callbacks import callback, support as alias\n\n" + _PROBE + _CONTROLS
    collision = caller if placement == "same" else pkg / "collision.py"
    caller.write_text(caller_source + (_HANDLER if collision == caller else ""), encoding="utf-8")
    if collision != caller:
        collision.write_text(_HANDLER, encoding="utf-8")
    return caller, collision, caller_source


def _call_edges(result: dict) -> set[tuple[str, str, str, str]]:
    nodes = {node["id"]: node for node in result["nodes"]}
    edges = result["edges"] if "edges" in result else result["links"]
    return {
        (
            nodes[edge.get("_src", edge["source"])]["label"],
            nodes[edge.get("_tgt", edge["target"])]["label"],
            Path(nodes[edge.get("_tgt", edge["target"])]["source_file"]).name,
            edge["relation"],
        )
        for edge in edges
        if edge["relation"] in ("calls", "indirect_call")
    }


def _check_calls(result: dict) -> None:
    edges = _call_edges(result)
    for caller in ("passed()", "invoked()", "nested()"):
        assert not any(source == caller and target == "handler()" for source, target, *_ in edges)
    assert edges >= {
        ("passed()", "accept()", "probe.py", "calls"),
        ("invoked()", "helper()", "probe.py", "calls"),
        ("invoked()", "accept()", "probe.py", "calls"),
        ("nested()", "accept()", "probe.py", "calls"),
        ("closure()", "captured()", "probe.py", "indirect_call"),
        ("default_value()", "callback()", "callbacks.py", "indirect_call"),
        ("default_call()", "callback()", "callbacks.py", "calls"),
        ("outside()", "callback()", "callbacks.py", "indirect_call"),
        ("alias_call()", "support()", "callbacks.py", "calls"),
        ("relative_call()", "support()", "callbacks.py", "calls"),
    }


@pytest.mark.parametrize("placement", ["same", "cross"])
def test_lambda_parameter_blocks_local_edges_and_corpus_candidates(tmp_path, placement):
    caller, _, caller_source = _write_corpus(tmp_path, placement)
    fragment = extract_python(caller, root=tmp_path)
    assert not any(target == "handler()" for _, target, *_ in _call_edges(fragment))
    assert not any(call["callee"] == "handler" for call in fragment["raw_calls"])
    lines = caller_source.splitlines()
    default_indirect = f"L{lines.index('        dispatch(callback)') + 1}"
    default_direct = f"L{lines.index('        callback()') + 1}"
    outside = f"L{lines.index('    return dispatch(callback)') + 1}"
    assert {
        (call["source_location"], bool(call.get("indirect")))
        for call in fragment["raw_calls"] if call["callee"] == "callback"
    } == {(default_indirect, True), (default_direct, False), (outside, True)}

    paths = sorted(tmp_path.rglob("*.py"))
    for _ in range(2):  # cold extraction, then the same per-file fragments from cache
        _check_calls(extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False))


@pytest.mark.parametrize("placement", ["same", "cross"])
def test_lambda_parameter_stays_shadowed_when_a_collision_is_removed_and_restored(tmp_path, placement):
    caller, collision, caller_source = _write_corpus(tmp_path, placement)

    def check_rebuild(changed_paths=None):
        assert _rebuild_code(tmp_path, changed_paths=changed_paths, no_cluster=True, acquire_lock=False)
        graph = json.loads((tmp_path / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
        _check_calls(graph)

    check_rebuild()
    caller.write_text(caller.read_text(encoding="utf-8") + "\n# Re-extract the caller.\n", encoding="utf-8")
    check_rebuild([caller])

    if collision == caller:
        caller.write_text(caller_source, encoding="utf-8")
    else:
        collision.unlink()
    check_rebuild([collision])

    collision.write_text((caller_source if collision == caller else "") + _HANDLER, encoding="utf-8")
    check_rebuild([collision])
    if collision != caller:
        caller.write_text(caller_source + "\n# Re-resolve against the restored file.\n", encoding="utf-8")
        check_rebuild([caller])


@pytest.mark.parametrize("placement", ["same", "cross"])
def test_lambda_shadowing_uses_python_identifier_identity(tmp_path, placement):
    caller = tmp_path / "probe.py"
    collision = caller if placement == "same" else tmp_path / "collision.py"
    source = """\
def accept(value): return value

def normalized_direct():
    return lambda ℎandler: handler()

def normalized_value():
    return lambda ℎandler: accept(handler)

class _Example:
    def private_direct(self):
        return lambda __handler: _Example__handler()

    def private_value(self):
        return lambda _Example__handler: accept(__handler)

    def genuine(self):
        return lambda __handler__: _Example__handler__()
"""
    definitions = """\
def handler(): return 1
def _Example__handler(): return 2
def __handler(): return 3
def _Example__handler__(): return 4
"""
    caller.write_text(source + (definitions if placement == "same" else ""), encoding="utf-8")
    if placement == "cross":
        collision.write_text(definitions, encoding="utf-8")
    paths = sorted(tmp_path.glob("*.py"))
    edges = _call_edges(extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False))
    assert edges == {
        ("normalized_value()", "accept()", "probe.py", "calls"),
        (".private_value()", "accept()", "probe.py", "calls"),
        (".genuine()", "_Example__handler__()", collision.name, "calls"),
    }
