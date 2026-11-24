"""同文件 Go 调用必须区分接收者方法与包级函数。"""
from __future__ import annotations

import importlib.util

import pytest

from graphify.extract import extract

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("tree_sitter_go") is None,
    reason="tree_sitter_go not installed",
)


def _targets(tmp_path, source, caller="Use()", siblings=None):
    path = tmp_path / "app.go"
    path.write_text("package demo\n" + source, encoding="utf-8")
    paths = [path]
    for name, body in (siblings or {}).items():
        sibling = tmp_path / name
        sibling.write_text("package demo\n" + body, encoding="utf-8")
        paths.append(sibling)
    result = extract(paths, root=tmp_path, cache_root=tmp_path / "cache", parallel=False)
    nodes = {node["id"]: node for node in result["nodes"]}
    owners = {
        edge["target"]: nodes[edge["source"]]["label"]
        for edge in result["edges"]
        if edge["relation"] == "method"
    }
    return [
        (owners.get(edge["target"]), nodes[edge["target"]]["label"], edge["confidence"])
        for edge in result["edges"]
        if edge["relation"] == "calls" and nodes[edge["source"]]["label"] == caller
    ]


@pytest.mark.parametrize("reverse", [False, True])
def test_same_named_methods_follow_the_receiver_in_either_declaration_order(tmp_path, reverse):
    methods = ["func (*A) apply() {}\n", "func (*B) apply() {}\n"]
    if reverse:
        methods.reverse()
    source = "type A struct{}\ntype B struct{}\n" + "".join(methods)
    source += "func Use(a *A) { a.apply() }\n"
    assert _targets(tmp_path, source) == [("A", ".apply()", "INFERRED")]


def test_a_unique_method_on_another_type_does_not_answer_the_receiver(tmp_path):
    source = (
        "type A struct{}\ntype B struct{}\n"
        "func (*B) apply() {}\n"
        "func Use(a *A) { a.apply() }\n"
    )
    assert _targets(tmp_path, source) == []


def test_an_unknown_receiver_does_not_bind_a_unique_local_method(tmp_path):
    source = (
        "type B struct{}\nfunc (*B) apply() {}\n"
        "func Use(a Missing) { a.apply() }\n"
    )
    assert _targets(tmp_path, source) == []


@pytest.mark.parametrize("reverse", [False, True])
def test_a_bare_function_call_never_selects_a_same_named_method(tmp_path, reverse):
    declarations = ["func apply() {}\n", "func (*B) apply() {}\n"]
    if reverse:
        declarations.reverse()
    source = "type B struct{}\n" + "".join(declarations) + "func Use() { apply() }\n"
    assert _targets(tmp_path, source) == [(None, "apply()", "EXTRACTED")]


def test_an_imported_selector_never_selects_a_local_function(tmp_path):
    source = 'import "fmt"\nfunc Println() {}\nfunc Use() { fmt.Println() }\n'
    assert _targets(tmp_path, source) == []


def test_each_function_keeps_its_receiver_type_in_the_same_file(tmp_path):
    source = (
        "type A struct{}\ntype B struct{}\n"
        "func (*A) apply() {}\nfunc (*B) apply() {}\n"
        "func Other(a *B) { a.apply() }\n"
        "func Use(a *A) { a.apply() }\n"
    )
    assert _targets(tmp_path, source) == [("A", ".apply()", "INFERRED")]


def test_a_field_on_the_methods_own_receiver_selects_its_declared_type(tmp_path):
    source = (
        "type A struct{}\ntype B struct{}\ntype App struct { value *A }\n"
        "func (*A) apply() {}\nfunc (*B) apply() {}\n"
        "func (app *App) Use() { app.value.apply() }\n"
    )
    assert _targets(tmp_path, source, caller=".Use()") == [("A", ".apply()", "INFERRED")]


def test_an_unknown_local_does_not_borrow_another_functions_parameter_type(tmp_path):
    source = (
        "type A struct{}\ntype B struct{}\n"
        "func (*A) apply() {}\nfunc (*B) apply() {}\n"
        "func Other(x *A) {}\nfunc NewB() *B { return &B{} }\n"
        "func Use() { x := NewB(); x.apply() }\n"
    )
    assert _targets(tmp_path, source) == [(None, "NewB()", "EXTRACTED")]


@pytest.mark.parametrize("binding", ["var x *B", "var x = &B{}"])
def test_a_package_variable_does_not_borrow_a_functions_parameter_type(tmp_path, binding):
    source = (
        "type A struct{}\ntype B struct{}\n"
        "func (*A) apply() {}\nfunc (*B) apply() {}\n"
        "func Other(x *A) {}\n" + binding + "\nfunc Use() { x.apply() }\n"
    )
    assert _targets(tmp_path, source) == [("B", ".apply()", "INFERRED")]


@pytest.mark.parametrize("binding", ["x := NewB()", "var x = NewB()"])
def test_an_unknown_local_shadows_a_typed_package_variable(tmp_path, binding):
    source = (
        "type A struct{}\ntype B struct{}\n"
        "func (*A) apply() {}\nfunc (*B) apply() {}\n"
        "var x *A\nfunc NewB() *B { return &B{} }\n"
        "func Use() { " + binding + "; x.apply() }\n"
    )
    assert _targets(tmp_path, source) == [(None, "NewB()", "EXTRACTED")]


def test_a_qualified_parameter_does_not_borrow_a_local_type(tmp_path):
    source = (
        'import "example.org/other"\n'
        "type A struct{}\nfunc (*A) apply() {}\n"
        "func Other(x *A) {}\nfunc Use(x *other.A) { x.apply() }\n"
    )
    assert _targets(tmp_path, source) == []


def test_a_field_owner_beats_another_structs_same_named_field(tmp_path):
    source = (
        "type A struct{}\ntype B struct{}\n"
        "func (*A) apply() {}\nfunc (*B) apply() {}\n"
        "type Other struct { value *A }\ntype App struct { value *B }\n"
        "func (s *App) Use() { s.value.apply() }\n"
    )
    assert _targets(tmp_path, source, caller=".Use()") == [("B", ".apply()", "INFERRED")]


@pytest.mark.parametrize("reverse", [False, True])
def test_a_direct_call_takes_priority_over_a_method_value(tmp_path, reverse):
    statements = ["Register(a.apply)", "a.apply()"]
    if reverse:
        statements.reverse()
    source = (
        "type A struct{}\nfunc (*A) apply() {}\nfunc Register(f func()) {}\n"
        "func Use(a *A) { " + "; ".join(statements) + " }\n"
    )
    assert set(_targets(tmp_path, source)) == {
        (None, "Register()", "EXTRACTED"), ("A", ".apply()", "INFERRED"),
    }


@pytest.mark.parametrize("expression", ["T.apply(t)", "(*T).apply(&t)"])
def test_an_explicit_method_expression_resolves_its_receiver_type(tmp_path, expression):
    source = (
        "type T struct{}\nfunc (T) apply() {}\n"
        "func Use(t T) { " + expression + " }\n"
    )
    assert _targets(tmp_path, source) == [("T", ".apply()", "INFERRED")]


@pytest.mark.parametrize("binding", ["", "x := &Box[int]{}; ", "var x *Box[int]; "])
def test_a_generic_receiver_keeps_its_base_type(tmp_path, binding):
    source = (
        "type Box[T any] struct{}\nfunc (*Box[T]) apply() {}\n"
        + ("func Use(x *Box[int]) { x.apply() }\n" if not binding
           else "func Use() { " + binding + "x.apply() }\n")
    )
    assert _targets(tmp_path, source) == [("Box", ".apply()", "INFERRED")]


@pytest.mark.parametrize("outer_call", [False, True])
def test_a_block_binding_shadows_its_parameter_and_restores_it_afterward(tmp_path, outer_call):
    source = (
        "type A struct{}\ntype B struct{}\n"
        "func (*A) apply() {}\nfunc (*B) apply() {}\n"
        "func Use(x *A) { { x := &B{}; x.apply() }; "
        + ("x.apply()" if outer_call else "") + " }\n"
    )
    expected = {("B", ".apply()", "INFERRED")}
    if outer_call:
        expected.add(("A", ".apply()", "INFERRED"))
    assert set(_targets(tmp_path, source)) == expected


@pytest.mark.parametrize("outer_call", [False, True])
def test_an_unknown_block_binding_cannot_borrow_its_outer_type(tmp_path, outer_call):
    source = (
        "type A struct{}\ntype B struct{}\n"
        "func (*A) apply() {}\nfunc (*B) apply() {}\n"
        "func NewB() *B { return &B{} }\n"
        "func Use(x *A) { { x := NewB(); x.apply() }; "
        + ("x.apply()" if outer_call else "") + " }\n"
    )
    expected: set[tuple[str | None, str, str]] = {(None, "NewB()", "EXTRACTED")}
    if outer_call:
        expected.add(("A", ".apply()", "INFERRED"))
    assert set(_targets(tmp_path, source)) == expected


def test_a_range_binding_with_unknown_element_type_shadows_its_parameter(tmp_path):
    source = (
        "type A struct{}\ntype B struct{}\n"
        "func (*A) apply() {}\nfunc (*B) apply() {}\n"
        "func Use(x *A, xs []*B) { for _, x := range xs { x.apply() } }\n"
    )
    assert _targets(tmp_path, source) == []


@pytest.mark.parametrize("binding", ["var x *B", "var x = &B{}", "x := &B{}"])
@pytest.mark.parametrize("before", [False, True])
def test_a_local_binding_only_applies_after_its_declaration(tmp_path, binding, before):
    statements = "x.apply(); " + binding if before else binding + "; x.apply()"
    source = (
        "type A struct{}\ntype B struct{}\n"
        "func (*A) apply() {}\nfunc (*B) apply() {}\n"
        "var x *A\nfunc Use() { " + statements + " }\n"
    )
    assert _targets(tmp_path, source) == [
        ("A" if before else "B", ".apply()", "INFERRED"),
    ]


@pytest.mark.parametrize("unknown", [False, True])
@pytest.mark.parametrize("outer_call", [False, True])
def test_an_if_initializer_binding_stays_inside_the_if(tmp_path, unknown, outer_call):
    binding = "NewB()" if unknown else "&B{}"
    source = (
        "type A struct{}\ntype B struct{}\n"
        "func (*A) apply() {}\nfunc (*B) apply() {}\n"
        "func NewB() *B { return &B{} }\n"
        "func Use(x *A) { if x := " + binding + "; x != nil { x.apply() }; "
        + ("x.apply()" if outer_call else "") + " }\n"
    )
    expected: set[tuple[str | None, str, str]] = {(None, "NewB()", "EXTRACTED")} if unknown else {
        ("B", ".apply()", "INFERRED"),
    }
    if outer_call:
        expected.add(("A", ".apply()", "INFERRED"))
    assert set(_targets(tmp_path, source)) == expected


def test_a_range_binding_does_not_escape_the_loop(tmp_path):
    source = (
        "type A struct{}\ntype B struct{}\n"
        "func (*A) apply() {}\nfunc (*B) apply() {}\n"
        "func Use(x *A, xs []*B) { for _, x := range xs { x.apply() }; x.apply() }\n"
    )
    assert _targets(tmp_path, source) == [("A", ".apply()", "INFERRED")]


def test_a_bare_call_resolves_a_sibling_function_instead_of_a_local_method(tmp_path):
    source = "type B struct{}\nfunc (B) apply() {}\nfunc Use() { apply() }\n"
    assert _targets(tmp_path, source, siblings={"other.go": "func apply() {}\n"}) == [
        (None, "apply()", "INFERRED"),
    ]
