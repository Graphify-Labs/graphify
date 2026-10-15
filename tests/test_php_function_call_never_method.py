"""A PHP function-call site never binds to a METHOD node cross-file (#52).

In PHP a bare ``name(...)`` (``function_call_expression``) can only invoke a
global or namespaced *function*.  Reaching a method requires ``$obj->m()``,
``Class::m()`` or first-class-callable syntax.  The shared cross-file pass in
``extract()`` matched by normalized label, and the label index strips the
member marker (``.event()`` -> ``event``), so Laravel's ``event(...)`` helper
bound to whatever class happened to declare an ``event()`` METHOD — 848
incoming ``calls`` edges on a single test method in the measured corpus.

Refusal is language-semantic, not a heuristic: methods are simply not
candidates at a function-call site.  Real global functions still resolve, and
no other language's candidate filtering changes (Ruby/Python bare calls keep
today's behavior — implicit-self dispatch makes a method a plausible target
there).
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract

CALLER = (
    "<?php\nnamespace App;\n"
    "class Caller {\n"
    "    public function handle(): void { event(new Thing()); }\n"
    "}\n"
)
# Same call site, spelled in a different case: PHP resolves function names
# case-insensitively, so this one only ever matches through the folded index.
CALLER_FOLDED = (
    "<?php\nnamespace App;\n"
    "class Caller {\n"
    "    public function handle(): void { EVENT(new Thing()); }\n"
    "}\n"
)
# The decoy: a class METHOD named `event`, labeled `.event()`.
DECOY_METHOD = (
    "<?php\nnamespace App;\n"
    "class Decoy {\n"
    "    public function event(): void { }\n"
    "}\n"
)
# The legitimate target: a global FUNCTION named `event`, labeled `event()`.
GLOBAL_FUNCTION = (
    "<?php\nnamespace App;\n"
    "function event(mixed $e): void { }\n"
)
# Same function, declared in a different case: labeled `Event()`, so it keys as
# `Event` exact-case and only as `event` in the folded index.
GLOBAL_FUNCTION_FOLDED = (
    "<?php\nnamespace App;\n"
    "function Event(mixed $e): void { }\n"
)
# Laravel's other bare helper, whose name collides with a CLASS by case alone:
# `Report` keys as `Report` exact-case and as `report` in the folded index.
CALLER_REPORT = (
    "<?php\nnamespace App;\n"
    "class Caller {\n"
    "    public function handle(): void { report($e); }\n"
    "}\n"
)
DECOY_REPORT_METHOD = (
    "<?php\nnamespace App;\n"
    "class Decoy {\n"
    "    public function report(): void { }\n"
    "}\n"
)
CLASS_REPORT = "<?php\nnamespace App\\Lib;\nclass Report { }\n"


def _extract(tmp_path: Path, files: dict[str, str]):
    """Extract ``files`` (name -> source) and return (result, {(src, tgt): edge})."""
    paths = []
    for name, body in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        paths.append(path)
    result = extract(paths, cache_root=tmp_path / "graphify-out")
    calls = {
        (edge["source"], edge["target"]): edge
        for edge in result["edges"]
        if edge.get("relation") == "calls"
    }
    return result, calls


def _find(result: dict, label: str, id_contains: str) -> str:
    nid = next(
        (
            node["id"]
            for node in result["nodes"]
            if node.get("label") == label and id_contains in node["id"]
        ),
        None,
    )
    assert nid is not None, f"no node {label}/{id_contains}"
    return nid


def test_function_call_does_not_bind_to_method(tmp_path):
    """`event(...)` + a class method `event()` elsewhere -> no `calls` edge."""
    result, calls = _extract(tmp_path, {
        "app/Caller.php": CALLER,
        "app/Decoy.php": DECOY_METHOD,
    })
    caller = _find(result, ".handle()", "caller")
    method = _find(result, ".event()", "decoy")
    assert (caller, method) not in calls


def test_function_call_still_binds_to_global_function(tmp_path):
    """The legitimate global-function resolution must not regress."""
    result, calls = _extract(tmp_path, {
        "app/Caller.php": CALLER,
        "app/helpers.php": GLOBAL_FUNCTION,
    })
    caller = _find(result, ".handle()", "caller")
    function = _find(result, "event()", "helpers")
    assert (caller, function) in calls


def test_function_wins_when_method_and_function_both_exist(tmp_path):
    """With both candidates present the call binds to the function, never the method."""
    result, calls = _extract(tmp_path, {
        "app/Caller.php": CALLER,
        "app/Decoy.php": DECOY_METHOD,
        "app/helpers.php": GLOBAL_FUNCTION,
    })
    caller = _find(result, ".handle()", "caller")
    method = _find(result, ".event()", "decoy")
    function = _find(result, "event()", "helpers")
    assert (caller, method) not in calls
    assert (caller, function) in calls


def test_case_insensitive_path_does_not_bind_to_method(tmp_path):
    """`EVENT(...)` matches `.event()` only via the folded index — still refused."""
    result, calls = _extract(tmp_path, {
        "app/Caller.php": CALLER_FOLDED,
        "app/Decoy.php": DECOY_METHOD,
    })
    caller = _find(result, ".handle()", "caller")
    method = _find(result, ".event()", "decoy")
    assert (caller, method) not in calls


def test_case_insensitive_path_still_binds_to_global_function(tmp_path):
    """PHP is case-insensitive: `EVENT(...)` still resolves to `function event()`."""
    result, calls = _extract(tmp_path, {
        "app/Caller.php": CALLER_FOLDED,
        "app/helpers.php": GLOBAL_FUNCTION,
    })
    caller = _find(result, ".handle()", "caller")
    function = _find(result, "event()", "helpers")
    assert (caller, function) in calls


def test_case_insensitive_function_wins_over_method(tmp_path):
    """Folded path, both candidates: the function is picked, the method refused."""
    result, calls = _extract(tmp_path, {
        "app/Caller.php": CALLER_FOLDED,
        "app/Decoy.php": DECOY_METHOD,
        "app/helpers.php": GLOBAL_FUNCTION,
    })
    caller = _find(result, ".handle()", "caller")
    method = _find(result, ".event()", "decoy")
    function = _find(result, "event()", "helpers")
    assert (caller, method) not in calls
    assert (caller, function) in calls


def test_case_mismatched_function_resolves_when_method_shadows_exact_key(tmp_path):
    """The folded index is retried after the refusal, not skipped.

    `event(...)` finds the METHOD `.event()` on the exact-case key, so the
    folded fallback never fires on its own; refusing that sole candidate must
    not lose `function Event()`, which PHP's case-insensitive function lookup
    makes the real target and which only exists under the folded key.
    """
    result, calls = _extract(tmp_path, {
        "app/Caller.php": CALLER,
        "app/Decoy.php": DECOY_METHOD,
        "app/helpers.php": GLOBAL_FUNCTION_FOLDED,
    })
    caller = _find(result, ".handle()", "caller")
    method = _find(result, ".event()", "decoy")
    function = _find(result, "Event()", "helpers")
    assert (caller, method) not in calls
    assert (caller, function) in calls


def test_function_call_does_not_bind_to_class_through_folded_retry(tmp_path):
    """A CLASS is no more invocable by `name(...)` than a method is.

    `report($e)` with a `.report()` method holding the exact-case key: the
    refusal empties that list, and the folded retry then reaches the
    capitalized `class Report` — a candidate the exact-case path never offered.
    """
    result, calls = _extract(tmp_path, {
        "app/Caller.php": CALLER_REPORT,
        "app/Decoy.php": DECOY_REPORT_METHOD,
        "app/Report.php": CLASS_REPORT,
    })
    caller = _find(result, ".handle()", "caller")
    method = _find(result, ".report()", "decoy")
    klass = _find(result, "Report", "report")
    assert (caller, klass) not in calls
    assert (caller, method) not in calls


def test_function_call_does_not_bind_to_class_unshadowed(tmp_path):
    """`foo(...)` + only `class Foo` cross-file -> no edge (no method involved)."""
    result, calls = _extract(tmp_path, {
        "app/Caller.php": (
            "<?php\nnamespace App;\n"
            "class Caller {\n"
            "    public function handle(): void { foo(); }\n"
            "}\n"
        ),
        "app/Foo.php": "<?php\nnamespace App\\Lib;\nclass Foo { }\n",
    })
    caller = _find(result, ".handle()", "caller")
    klass = _find(result, "Foo", "foo")
    assert (caller, klass) not in calls


def test_function_call_does_not_bind_to_interface_enum_or_trait(tmp_path):
    """Interfaces, enums and traits mint declaration nodes since #47 — same refusal."""
    result, calls = _extract(tmp_path, {
        "app/Caller.php": (
            "<?php\nnamespace App;\n"
            "class Caller {\n"
            "    public function handle(): void { notify(); status(); describes(); }\n"
            "}\n"
        ),
        "app/Types.php": (
            "<?php\nnamespace App\\Lib;\n"
            "interface Notify { }\n"
            "enum Status { }\n"
            "trait Describes { }\n"
        ),
    })
    caller = _find(result, ".handle()", "caller")
    for label in ("Notify", "Status", "Describes"):
        assert (caller, _find(result, label, "types")) not in calls


def test_class_refusal_keeps_the_real_function_reachable(tmp_path):
    """With method + class + `function Report()` all present, the function wins."""
    result, calls = _extract(tmp_path, {
        "app/Caller.php": CALLER_REPORT,
        "app/Decoy.php": DECOY_REPORT_METHOD,
        "app/Report.php": CLASS_REPORT,
        "app/helpers.php": "<?php\nnamespace App;\nfunction Report(mixed $e): void { }\n",
    })
    caller = _find(result, ".handle()", "caller")
    method = _find(result, ".report()", "decoy")
    klass = _find(result, "Report", "app_report")
    function = _find(result, "Report()", "helpers")
    assert (caller, method) not in calls
    assert (caller, klass) not in calls
    assert (caller, function) in calls


def test_other_languages_keep_binding_bare_calls_to_methods(tmp_path):
    """Scope guard: the refusal is PHP-only (Ruby has implicit-self dispatch)."""
    result, calls = _extract(tmp_path, {
        "a.rb": "class A\n  def caller\n    event()\n  end\nend\n",
        "b.rb": "class B\n  def event\n  end\nend\n",
    })
    caller = _find(result, ".caller()", "_a_a_caller")
    method = _find(result, ".event()", "_b_b_event")
    assert (caller, method) in calls
