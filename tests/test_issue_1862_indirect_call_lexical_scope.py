"""Tests for issue #1862: indirect_call (callback-by-name) resolution must be
lexical-scope-aware, matching the #3405 fix already applied to direct `calls`.

Without this fix, a callback passed by name from one function resolves to a
same-named nested function defined in a SIBLING function's scope, because the
cross-file fallback in extract.py matches purely by bare label across the
whole corpus with no scope information.
"""
import pytest
from pathlib import Path

from graphify.extract import extract


def test_python_indirect_call_sibling_scope_not_confused(tmp_path: Path):
    """Test 1 — Two sibling functions each define + pass a same-named nested
    callback. Each call must bind to its OWN lexical definition.

    def run_with_guard(fn):
        return fn()

    def test_alpha_scope():
        def read_then_mutate():
            return "alpha"
        return run_with_guard(read_then_mutate)

    def test_beta_scope():
        def read_then_mutate():
            return "beta"
        return run_with_guard(read_then_mutate)
    """
    f = tmp_path / "test_sibling_scope.py"
    f.write_text(
        "def run_with_guard(fn):\n"
        "    return fn()\n"
        "\n"
        "def test_alpha_scope():\n"
        "    def read_then_mutate():\n"
        "        return \"alpha\"\n"
        "    return run_with_guard(read_then_mutate)\n"
        "\n"
        "def test_beta_scope():\n"
        "    def read_then_mutate():\n"
        "        return \"beta\"\n"
        "    return run_with_guard(read_then_mutate)\n"
    )
    result = extract([f], root=tmp_path)
    by_label_id = {}
    for n in result["nodes"]:
        by_label_id.setdefault(n["label"], []).append(n["id"])

    alpha_scope_id = by_label_id["test_alpha_scope()"][0]
    beta_scope_id = by_label_id["test_beta_scope()"][0]
    read_then_mutate_ids = by_label_id["read_then_mutate()"]
    assert len(read_then_mutate_ids) == 2

    alpha_inner = next(i for i in read_then_mutate_ids if i.startswith(alpha_scope_id))
    beta_inner = next(i for i in read_then_mutate_ids if i.startswith(beta_scope_id))
    assert alpha_inner != beta_inner

    indirect_edges = {
        (e["source"], e["target"])
        for e in result["edges"]
        if e["relation"] == "indirect_call"
    }

    assert (alpha_scope_id, alpha_inner) in indirect_edges
    assert (beta_scope_id, beta_inner) in indirect_edges
    # The sibling's nested function must never be the resolved target (#1862).
    assert (alpha_scope_id, beta_inner) not in indirect_edges
    assert (beta_scope_id, alpha_inner) not in indirect_edges


def test_python_indirect_call_still_resolves_cross_file(tmp_path: Path):
    """Test 2 — A legitimate cross-file callback reference must still resolve.

    # helper.py
    def unique_only_here():
        pass

    # main.py
    from helper import unique_only_here
    def dispatch():
        run(unique_only_here)
    """
    helper = tmp_path / "helper.py"
    helper.write_text(
        "def unique_only_here():\n"
        "    pass\n"
    )
    main = tmp_path / "main.py"
    main.write_text(
        "from helper import unique_only_here\n"
        "\n"
        "def run(fn):\n"
        "    return fn()\n"
        "\n"
        "def dispatch():\n"
        "    return run(unique_only_here)\n"
    )
    result = extract([helper, main], root=tmp_path)
    by_label = {n["label"]: n for n in result["nodes"]}

    helper_id = by_label["unique_only_here()"]["id"]
    assert helper_id.startswith("helper")

    dispatch_id = by_label["dispatch()"]["id"]

    indirect_edges = {
        (e["source"], e["target"])
        for e in result["edges"]
        if e["relation"] == "indirect_call"
    }
    assert (dispatch_id, helper_id) in indirect_edges


def test_python_indirect_call_enclosing_scope_over_module(tmp_path: Path):
    """Test 3 — LEGB: an indirect reference inside a nested function must prefer
    its OWN enclosing lexical scope's same-named definition over a module-level
    definition with the same name (Python Language Reference, Execution model:
    Resolution of names).

    def read_then_mutate():
        pass  # module-level, must be shadowed

    def outer():
        def read_then_mutate():
            return "inner"
        def caller():
            return dispatch(read_then_mutate)
        return caller()

    def dispatch(fn):
        return fn()
    """
    f = tmp_path / "test_legb.py"
    f.write_text(
        "def read_then_mutate():\n"
        "    pass\n"
        "\n"
        "def dispatch(fn):\n"
        "    return fn()\n"
        "\n"
        "def outer():\n"
        "    def read_then_mutate():\n"
        "        return \"inner\"\n"
        "    def caller():\n"
        "        return dispatch(read_then_mutate)\n"
        "    return caller()\n"
    )
    result = extract([f], root=tmp_path)
    by_label_id = {}
    for n in result["nodes"]:
        by_label_id.setdefault(n["label"], []).append(n["id"])

    outer_id = by_label_id["outer()"][0]
    caller_id = next(i for i in by_label_id["caller()"] if i.startswith(outer_id))
    read_then_mutate_ids = by_label_id["read_then_mutate()"]
    assert len(read_then_mutate_ids) == 2
    module_level = next(i for i in read_then_mutate_ids if not i.startswith(outer_id))
    nested = next(i for i in read_then_mutate_ids if i.startswith(outer_id))

    indirect_edges = {
        (e["source"], e["target"])
        for e in result["edges"]
        if e["relation"] == "indirect_call"
    }
    assert (caller_id, nested) in indirect_edges
    assert (caller_id, module_level) not in indirect_edges
