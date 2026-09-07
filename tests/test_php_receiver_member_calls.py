"""PHP member calls resolve through the receiver's declared type.

The shared cross-file pass skips member calls, and PHP recorded no receiver at all, so
`$greeter->greet()` on a receiver whose class lives in another file produced no edge —
the PHP twin of the Swift gap in #1356. Each case below pins one source of the
receiver's type, and the negative cases pin what must stay unresolved: an untyped
parameter, a union type, a longer chain, and an ambiguous class name.
"""
from __future__ import annotations

import importlib

import pytest

from graphify.extract import extract

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("tree_sitter_php") is None,
    reason="tree_sitter_php not installed",
)

GREETER = "<?php\nclass Greeter {\n    public function greet(): void {}\n}\n"


def _calls(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    result = extract([tmp_path / n for n in files],
                     cache_root=tmp_path / "graphify-out", parallel=False)
    label = {n["id"]: n["label"] for n in result["nodes"]}
    calls = {(label.get(e["source"]), label.get(e["target"])): e
             for e in result["edges"] if e["relation"] == "calls"}
    return calls, result


def _greet_edge(calls: dict) -> dict | None:
    return next((e for (src, tgt), e in calls.items()
                 if src and "run" in src and tgt == ".greet()"), None)


def test_a_typed_property_types_the_receiver(tmp_path):
    calls, _ = _calls(tmp_path, {
        "Greeter.php": GREETER,
        "App.php": "<?php\nclass App {\n    private Greeter $greeter;\n"
                   "    public function run(): void { $this->greeter->greet(); }\n}\n",
    })
    edge = _greet_edge(calls)
    assert edge is not None, calls
    # The type came from the table, never from the call site: `$greeter` names a
    # variable, so there is no spelling of this call that would be exact.
    assert edge["confidence"] == "INFERRED"


def test_a_promoted_constructor_parameter_types_the_receiver(tmp_path):
    # Constructor promotion declares no property, so nothing else in the walk ever
    # names the receiver's type.
    calls, _ = _calls(tmp_path, {
        "Greeter.php": GREETER,
        "App.php": "<?php\nclass App {\n"
                   "    public function __construct(private Greeter $greeter) {}\n"
                   "    public function run(): void { $this->greeter->greet(); }\n}\n",
    })
    assert _greet_edge(calls) is not None, calls


def test_a_typed_parameter_types_the_receiver(tmp_path):
    calls, _ = _calls(tmp_path, {
        "Greeter.php": GREETER,
        "App.php": "<?php\nclass App {\n"
                   "    public function run(Greeter $greeter): void { $greeter->greet(); }\n}\n",
    })
    assert _greet_edge(calls) is not None, calls


def test_a_new_binding_types_an_unannotated_local(tmp_path):
    calls, _ = _calls(tmp_path, {
        "Greeter.php": GREETER,
        "App.php": "<?php\nclass App {\n    public function run(): void {\n"
                   "        $greeter = new Greeter();\n        $greeter->greet();\n    }\n}\n",
    })
    assert _greet_edge(calls) is not None, calls


def test_a_nullable_property_type_still_names_one_class(tmp_path):
    calls, _ = _calls(tmp_path, {
        "Greeter.php": GREETER,
        "App.php": "<?php\nclass App {\n    private ?Greeter $greeter = null;\n"
                   "    public function run(): void { $this->greeter->greet(); }\n}\n",
    })
    assert _greet_edge(calls) is not None, calls


def test_an_untyped_parameter_resolves_to_nothing(tmp_path):
    calls, _ = _calls(tmp_path, {
        "Greeter.php": GREETER,
        "App.php": "<?php\nclass App {\n"
                   "    public function run($greeter): void { $greeter->greet(); }\n}\n",
    })
    assert _greet_edge(calls) is None, calls


def test_a_union_typed_receiver_resolves_to_nothing(tmp_path):
    # `Greeter|Other` names no one class, and binding the first arm would be a guess.
    calls, _ = _calls(tmp_path, {
        "Greeter.php": GREETER,
        "Other.php": "<?php\nclass Other {\n    public function greet(): void {}\n}\n",
        "App.php": "<?php\nclass App {\n"
                   "    public function run(Greeter|Other $greeter): void "
                   "{ $greeter->greet(); }\n}\n",
    })
    assert _greet_edge(calls) is None, calls


def test_a_longer_chain_resolves_to_nothing(tmp_path):
    # `$this->a->b->greet()` types neither `a` nor `b` as the receiver.
    calls, _ = _calls(tmp_path, {
        "Greeter.php": GREETER,
        "App.php": "<?php\nclass App {\n    private Greeter $greeter;\n"
                   "    public function run(): void { $this->greeter->inner->greet(); }\n}\n",
    })
    assert _greet_edge(calls) is None, calls


def test_two_classes_of_the_same_name_resolve_to_neither(tmp_path):
    # The single-definition guard: guessing one of two `Greeter`s is worse than
    # leaving the call unresolved.
    calls, _ = _calls(tmp_path, {
        "a/Greeter.php": GREETER,
        "b/Greeter.php": GREETER,
        "App.php": "<?php\nclass App {\n    private Greeter $greeter;\n"
                   "    public function run(): void { $this->greeter->greet(); }\n}\n",
    })
    assert _greet_edge(calls) is None, calls


def test_the_first_binding_of_a_name_wins(tmp_path):
    # The table is flat per file, so a parameter named like a property has to lose:
    # otherwise `other`'s signature would redirect the property's own calls.
    calls, result = _calls(tmp_path, {
        "Greeter.php": GREETER,
        "Other.php": "<?php\nclass Other {\n    public function greet(): void {}\n}\n",
        "App.php": "<?php\nclass App {\n    private Greeter $greeter;\n"
                   "    public function run(): void { $this->greeter->greet(); }\n"
                   "    public function other(Other $greeter): void { $greeter->greet(); }\n}\n",
    })
    source_of = {n["id"]: str(n.get("source_file") or "") for n in result["nodes"]}
    label_of = {n["id"]: n["label"] for n in result["nodes"]}
    run_targets = {source_of[e["target"]] for e in result["edges"]
                   if e["relation"] == "calls"
                   and "run" in str(label_of.get(e["source"]))
                   and label_of.get(e["target"]) == ".greet()"}
    assert len(run_targets) == 1, run_targets
    assert run_targets.pop().endswith("Greeter.php")


def test_a_static_call_keeps_its_own_path(tmp_path):
    # `Helper::format()` is a scoped call, not a member call, and still binds.
    calls, _ = _calls(tmp_path, {
        "Helper.php": "<?php\nclass Helper {\n    public static function format(): void {}\n}\n",
        "App.php": "<?php\nclass App {\n"
                   "    public function run(): void { Helper::format(); }\n}\n",
    })
    assert any(src and "run" in src and tgt == "Helper" for src, tgt in calls), calls


def test_a_class_from_another_language_never_answers_a_php_receiver(tmp_path):
    # The declaration index is corpus-wide, so a same-named Java class would both answer
    # the receiver and hide that no PHP file declares it — the call belongs to the merge.
    calls, result = _calls(tmp_path, {
        "App.php": "<?php\nclass App {\n    private Greeter $greeter;\n"
                   "    public function run(): void { $this->greeter->greet(); }\n}\n",
        "Greeter.java": "public class Greeter { public void greet() {} }\n",
    })
    assert _greet_edge(calls) is None, calls
    parked = [(n.get("metadata") or {}).get("unresolved_calls") for n in result["nodes"]
              if "run" in str(n["label"]) and n.get("metadata")]
    assert parked == [[{"callee": "greet", "receiver_type": "Greeter",
                        "lang": "php", "line": "L4"}]], parked
