"""Tests for Phase 9C: JS/TS mixin factory and application fact collection (Pass 2)."""
from __future__ import annotations

from pathlib import Path
import pytest

from graphify.extract import extract
from graphify.extractors.base import _file_stem, _make_id
from graphify.extractors.models import _SymbolResolutionFacts
from graphify.extractors.resolution import _collect_js_symbol_resolution_facts


def _collect_facts_for_source(tmp_path: Path, filename: str, content: str) -> tuple[_SymbolResolutionFacts, Path]:
    file_path = tmp_path / filename
    file_path.write_text(content, encoding="utf-8")
    facts = _SymbolResolutionFacts()
    _collect_js_symbol_resolution_facts([file_path], facts)
    return facts, file_path


# --- Factory Detection Tests ---

def test_simple_factory(tmp_path):
    """1. Simple factory: exactly one factory fact, base_param_index=0, anonymous returned class."""
    facts, file_path = _collect_facts_for_source(
        tmp_path,
        "simple_factory.js",
        """
function mixin(Base) {
    return class extends Base {};
}
""",
    )
    assert len(facts.class_factories) == 1
    fact = facts.class_factories[0]
    stem = _file_stem(file_path)
    expected_factory_nid = _make_id(stem, "mixin")
    expected_returned_nid = _make_id(expected_factory_nid, "mixin@class")
    assert fact.factory_name == "mixin"
    assert fact.factory_nid == expected_factory_nid
    assert fact.returned_class_nid == expected_returned_nid
    assert fact.base_param_index == 0
    assert fact.line == 2


def test_named_returned_class(tmp_path):
    """2. Named returned class: returned_class_nid ends with the class name."""
    facts, file_path = _collect_facts_for_source(
        tmp_path,
        "named_return.js",
        """
function mixin(Base) {
    return class Shared extends Base {};
}
""",
    )
    assert len(facts.class_factories) == 1
    fact = facts.class_factories[0]
    stem = _file_stem(file_path)
    expected_factory_nid = _make_id(stem, "mixin")
    expected_returned_nid = _make_id(expected_factory_nid, "Shared")
    assert fact.factory_name == "mixin"
    assert fact.base_param_index == 0
    assert fact.returned_class_nid == expected_returned_nid


def test_multiple_parameters(tmp_path):
    """3. Multiple parameters: base_param_index accurately identifies the base parameter."""
    facts, _ = _collect_facts_for_source(
        tmp_path,
        "multi_params.js",
        """
function mixin(Config, Base) {
    return class extends Base {};
}
""",
    )
    assert len(facts.class_factories) == 1
    fact = facts.class_factories[0]
    assert fact.factory_name == "mixin"
    assert fact.base_param_index == 1


def test_typescript_parameter(tmp_path):
    """4. TypeScript parameter: type annotation does not interfere with parameter matching."""
    facts, file_path = _collect_facts_for_source(
        tmp_path,
        "ts_factory.ts",
        """
function mixin<T extends Ctor>(Base: T) {
    return class extends Base {};
}
""",
    )
    assert len(facts.class_factories) == 1
    fact = facts.class_factories[0]
    stem = _file_stem(file_path)
    expected_factory_nid = _make_id(stem, "mixin")
    expected_returned_nid = _make_id(expected_factory_nid, "mixin@class")
    assert fact.factory_name == "mixin"
    assert fact.base_param_index == 0
    assert fact.returned_class_nid == expected_returned_nid


def test_arrow_function_factory(tmp_path):
    """Arrow function factory assigned to const."""
    facts, file_path = _collect_facts_for_source(
        tmp_path,
        "arrow_factory.js",
        """
const mixin = (Base) => {
    return class extends Base {};
};
""",
    )
    assert len(facts.class_factories) == 1
    fact = facts.class_factories[0]
    stem = _file_stem(file_path)
    expected_factory_nid = _make_id(stem, "mixin")
    expected_returned_nid = _make_id(expected_factory_nid, "mixin@class")
    assert fact.factory_name == "mixin"
    assert fact.base_param_index == 0
    assert fact.returned_class_nid == expected_returned_nid


def test_concise_arrow_factory(tmp_path):
    """Concise arrow function returning a class directly."""
    facts, file_path = _collect_facts_for_source(
        tmp_path,
        "concise_factory.js",
        """
const mixin = (Base) => class extends Base {};
""",
    )
    assert len(facts.class_factories) == 1
    fact = facts.class_factories[0]
    stem = _file_stem(file_path)
    expected_factory_nid = _make_id(stem, "mixin")
    expected_returned_nid = _make_id(expected_factory_nid, "mixin@class")
    assert fact.factory_name == "mixin"
    assert fact.base_param_index == 0
    assert fact.returned_class_nid == expected_returned_nid


def test_function_expression_factory(tmp_path):
    """Function expression factory assigned to const."""
    facts, file_path = _collect_facts_for_source(
        tmp_path,
        "fn_expr_factory.js",
        """
const mixin = function(Base) {
    return class extends Base {};
};
""",
    )
    assert len(facts.class_factories) == 1
    fact = facts.class_factories[0]
    stem = _file_stem(file_path)
    expected_factory_nid = _make_id(stem, "mixin")
    expected_returned_nid = _make_id(expected_factory_nid, "mixin@class")
    assert fact.factory_name == "mixin"
    assert fact.base_param_index == 0
    assert fact.returned_class_nid == expected_returned_nid


# --- Application Detection Tests ---

def test_variable_bound_application(tmp_path):
    """5. Variable-bound application: const Applied = mixin(Root);"""
    facts, file_path = _collect_facts_for_source(
        tmp_path,
        "var_bound.js",
        """
class Root {}
function mixin(Base) {
    return class extends Base {};
}
const Applied = mixin(Root);
""",
    )
    assert len(facts.factory_applications) == 1
    app = facts.factory_applications[0]
    stem = _file_stem(file_path)
    expected_target_nid = _make_id(stem, "Applied")
    assert app.target_nid == expected_target_nid
    assert app.factory_name == "mixin"
    assert app.arg_names == ("Root",)


def test_dynamic_heritage_application(tmp_path):
    """6. Dynamic class heritage: class Child extends mixin(Root) {}"""
    facts, file_path = _collect_facts_for_source(
        tmp_path,
        "dyn_heritage.js",
        """
class Root {}
function mixin(Base) {
    return class extends Base {};
}
class Child extends mixin(Root) {}
""",
    )
    assert len(facts.factory_applications) == 1
    app = facts.factory_applications[0]
    stem = _file_stem(file_path)
    expected_target_nid = _make_id(stem, "Child")
    assert app.target_nid == expected_target_nid
    assert app.factory_name == "mixin"
    assert app.arg_names == ("Root",)


def test_multi_argument_application(tmp_path):
    """Application with multiple simple identifier arguments."""
    facts, file_path = _collect_facts_for_source(
        tmp_path,
        "multi_args.js",
        """
const Applied = mixin(Config, Root);
""",
    )
    assert len(facts.factory_applications) == 1
    app = facts.factory_applications[0]
    stem = _file_stem(file_path)
    expected_target_nid = _make_id(stem, "Applied")
    assert app.target_nid == expected_target_nid
    assert app.factory_name == "mixin"
    assert app.arg_names == ("Config", "Root")


def test_ts_dynamic_heritage_application(tmp_path):
    """TypeScript dynamic class heritage application."""
    facts, file_path = _collect_facts_for_source(
        tmp_path,
        "ts_dyn.ts",
        """
class Root {}
class Child extends mixin(Root) {}
""",
    )
    assert len(facts.factory_applications) == 1
    app = facts.factory_applications[0]
    stem = _file_stem(file_path)
    expected_target_nid = _make_id(stem, "Child")
    assert app.target_nid == expected_target_nid
    assert app.factory_name == "mixin"
    assert app.arg_names == ("Root",)


# --- Negative Cases Tests ---

def test_dynamic_argument_rejected(tmp_path):
    """7. Dynamic argument: call expression in argument is rejected."""
    facts, _ = _collect_facts_for_source(
        tmp_path,
        "dyn_arg.js",
        """
const Applied = mixin(getBase());
""",
    )
    assert len(facts.factory_applications) == 0


def test_complex_expression_argument_rejected(tmp_path):
    """Complex expression in argument (logical OR, ternary, etc.) is rejected."""
    facts, _ = _collect_facts_for_source(
        tmp_path,
        "complex_args.js",
        """
const A = mixin(X || Y);
const B = mixin(flag ? X : Y);
const C = mixin(m1(Root));
""",
    )
    assert len(facts.factory_applications) == 0


def test_non_class_return_rejected(tmp_path):
    """8. Non-class return: function returning non-class is not a factory."""
    facts, _ = _collect_facts_for_source(
        tmp_path,
        "non_class_ret.js",
        """
function mixin(Base) {
    return Base;
}
""",
    )
    assert len(facts.class_factories) == 0


def test_multiple_returns_rejected(tmp_path):
    """9. Multiple returns: ambiguous control-flow is rejected (Rule A)."""
    facts, _ = _collect_facts_for_source(
        tmp_path,
        "multi_returns.js",
        """
function mixin(Base) {
    if (x) return class extends Base {};
    return class extends Base {};
}
""",
    )
    assert len(facts.class_factories) == 0


def test_multiple_returns_with_early_null_rejected(tmp_path):
    """Early return of null followed by class return is rejected (Rule A)."""
    facts, _ = _collect_facts_for_source(
        tmp_path,
        "early_null.js",
        """
function mixin(Base) {
    if (condition) return null;
    return class extends Base {};
}
""",
    )
    assert len(facts.class_factories) == 0


def test_returned_class_methods_do_not_count_as_multiple_returns(tmp_path):
    """Methods inside the returned class containing return statements do not disqualify the factory."""
    facts, _ = _collect_facts_for_source(
        tmp_path,
        "class_with_methods.js",
        """
function mixin(Base) {
    return class extends Base {
        foo() {
            return 42;
        }
        bar() {
            return "hello";
        }
    };
}
""",
    )
    assert len(facts.class_factories) == 1
    assert facts.class_factories[0].factory_name == "mixin"


def test_dynamic_returned_base_rejected(tmp_path):
    """10. Dynamic returned base: class extends getBase() is rejected (Rule C)."""
    facts, _ = _collect_facts_for_source(
        tmp_path,
        "dyn_base.js",
        """
function mixin(Base) {
    return class extends getBase() {};
}
""",
    )
    assert len(facts.class_factories) == 0


def test_member_expression_returned_base_rejected(tmp_path):
    """Class extends Foo.Bar is rejected (Rule C)."""
    facts, _ = _collect_facts_for_source(
        tmp_path,
        "member_base.js",
        """
function mixin(Base) {
    return class extends Foo.Bar {};
}
""",
    )
    assert len(facts.class_factories) == 0


def test_destructured_parameter_rejected(tmp_path):
    """11. Destructured parameter: function mixin({ Base }) is rejected (Rule D)."""
    facts, _ = _collect_facts_for_source(
        tmp_path,
        "destructured.js",
        """
function mixin({ Base }) {
    return class extends Base {};
}
""",
    )
    assert len(facts.class_factories) == 0


def test_regression_no_fabricate_inherits(tmp_path):
    """12. Regression: Ensure Pass 2 collection does not create an inherits edge to mixin."""
    src_file = tmp_path / "src" / "a.js"
    src_file.parent.mkdir(parents=True, exist_ok=True)
    src_file.write_text(
        """
class Animal {}
function mixin(base) {
    return class extends base {};
}
class Dog extends mixin(Animal) {}
""",
        encoding="utf-8",
    )
    result = extract([src_file], cache_root=tmp_path)
    inherits_edges = [
        e for e in result["edges"]
        if e["relation"] == "inherits" and "Dog" in e["source"]
    ]
    assert len(inherits_edges) == 0
