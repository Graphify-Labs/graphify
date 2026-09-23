"""Tests for issue #1862: indirect_call (callback-by-name) resolution must be
lexical-scope-aware, matching the #3405 fix already applied to direct `calls`.

Without this fix, a callback passed by name from one function resolves to a
same-named nested function defined in a SIBLING function's scope, because the
cross-file fallback in extract.py matches purely by bare label across the
whole corpus with no scope information.

The enclosing-scope walk also skips an intermediate function that does not bind
the name, then either resolves a module-level callable or honors a farther
parameter/local shadow.
"""
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


def test_python_indirect_call_enclosing_parameter_shadows_module(tmp_path: Path):
    """A closure reference to an outer parameter must not bind to a same-named
    module function.
    """
    f = tmp_path / "test_enclosing_parameter.py"
    f.write_text(
        "def callback():\n"
        "    return 'module'\n"
        "\n"
        "def dispatch(fn):\n"
        "    return fn()\n"
        "\n"
        "def outer(callback):\n"
        "    def caller():\n"
        "        return dispatch(callback)\n"
        "    return caller()\n"
    )
    result = extract([f], root=tmp_path)
    by_label_id = {}
    for node in result["nodes"]:
        by_label_id.setdefault(node["label"], []).append(node["id"])

    outer_id = by_label_id["outer()"][0]
    caller_id = next(i for i in by_label_id["caller()"] if i.startswith(outer_id))
    module_callback_id = next(
        i for i in by_label_id["callback()"] if not i.startswith(outer_id)
    )
    indirect_edges = {
        (edge["source"], edge["target"])
        for edge in result["edges"]
        if edge["relation"] == "indirect_call"
    }

    assert (caller_id, module_callback_id) not in indirect_edges


def test_python_indirect_call_skips_unrelated_enclosing_scope(tmp_path: Path):
    """An intermediate function that binds neither the name nor a same-named
    nested callable must not stop the enclosing-scope walk. Once that chain is
    exhausted, the reference resolves to the module-level callable.

    def target():
        return 1

    def dispatch(fn):
        return fn()

    def outer():
        def middle():
            def caller():
                return dispatch(target)
            return caller()
        return middle()
    """
    f = tmp_path / "test_skip_unrelated_scope.py"
    f.write_text(
        "def target():\n"
        "    return 1\n"
        "\n"
        "def dispatch(fn):\n"
        "    return fn()\n"
        "\n"
        "def outer():\n"
        "    def middle():\n"
        "        def caller():\n"
        "            return dispatch(target)\n"
        "        return caller()\n"
        "    return middle()\n"
    )
    result = extract([f], root=tmp_path)
    by_label_id = {}
    for node in result["nodes"]:
        by_label_id.setdefault(node["label"], []).append(node["id"])

    outer_id = by_label_id["outer()"][0]
    middle_id = next(i for i in by_label_id["middle()"] if i.startswith(outer_id))
    caller_id = next(i for i in by_label_id["caller()"] if i.startswith(middle_id))
    target_id = by_label_id["target()"][0]
    indirect_edges = {
        (edge["source"], edge["target"])
        for edge in result["edges"]
        if edge["relation"] == "indirect_call"
    }

    assert (caller_id, target_id) in indirect_edges


def test_python_indirect_call_enclosing_shadow_past_unrelated_scope(tmp_path: Path):
    """A parameter on a grandparent scope still shadows a module function when
    the intermediate function does not bind that name.

    def callback():
        return "module"

    def dispatch(fn):
        return fn()

    def outer(callback):
        def middle():
            def caller():
                return dispatch(callback)
            return caller()
        return middle()
    """
    f = tmp_path / "test_shadow_past_unrelated_scope.py"
    f.write_text(
        "def callback():\n"
        "    return 'module'\n"
        "\n"
        "def dispatch(fn):\n"
        "    return fn()\n"
        "\n"
        "def outer(callback):\n"
        "    def middle():\n"
        "        def caller():\n"
        "            return dispatch(callback)\n"
        "        return caller()\n"
        "    return middle()\n"
    )
    result = extract([f], root=tmp_path)
    by_label_id = {}
    for node in result["nodes"]:
        by_label_id.setdefault(node["label"], []).append(node["id"])

    outer_id = by_label_id["outer()"][0]
    middle_id = next(i for i in by_label_id["middle()"] if i.startswith(outer_id))
    caller_id = next(i for i in by_label_id["caller()"] if i.startswith(middle_id))
    module_callback_id = next(
        i for i in by_label_id["callback()"] if not i.startswith(outer_id)
    )
    indirect_edges = {
        (edge["source"], edge["target"])
        for edge in result["edges"]
        if edge["relation"] == "indirect_call"
    }

    assert (caller_id, module_callback_id) not in indirect_edges


def test_python_indirect_call_method_bare_name_is_not_a_sibling_method(tmp_path: Path):
    """A bare name inside a method is not a class-scope lookup. It must not bind
    to a sibling method. A same-named module function remains the target.
    """
    sibling = tmp_path / "method_sibling.py"
    sibling.write_text(
        "def dispatch(fn):\n"
        "    return fn()\n"
        "\n"
        "class C:\n"
        "    def helper(self):\n"
        "        return 1\n"
        "    def run(self):\n"
        "        return dispatch(helper)\n"
    )
    both = tmp_path / "method_and_module.py"
    both.write_text(
        "def helper():\n"
        "    return 'module'\n"
        "\n"
        "def dispatch(fn):\n"
        "    return fn()\n"
        "\n"
        "class C:\n"
        "    def helper(self):\n"
        "        return 1\n"
        "    def run(self):\n"
        "        return dispatch(helper)\n"
    )
    sibling_result = extract([sibling], root=tmp_path)
    sibling_edges = {
        (edge["source"], edge["target"])
        for edge in sibling_result["edges"]
        if edge["relation"] == "indirect_call"
    }
    run_id = next(n["id"] for n in sibling_result["nodes"] if n["label"] == ".run()")
    helper_id = next(n["id"] for n in sibling_result["nodes"] if n["label"] == ".helper()")
    assert (run_id, helper_id) not in sibling_edges

    both_result = extract([both], root=tmp_path)
    by_label = {}
    for node in both_result["nodes"]:
        by_label.setdefault(node["label"], []).append(node["id"])
    module_helper = by_label["helper()"][0]
    method_helper = by_label[".helper()"][0]
    run_both = by_label[".run()"][0]
    both_edges = {
        (edge["source"], edge["target"])
        for edge in both_result["edges"]
        if edge["relation"] == "indirect_call"
    }
    assert (run_both, module_helper) in both_edges
    assert (run_both, method_helper) not in both_edges
