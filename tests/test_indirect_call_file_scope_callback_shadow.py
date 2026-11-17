"""A parameter of a file-scope anonymous callback must shadow same-named
functions elsewhere in the corpus (#4448).

#3124 walks the body of a closure passed in a module-level call statement
(`items.forEach(function (value) { ... })`, AngularJS `.controller(...)`,
`it("...", () => { ... })`) under the file node, but did not register the
closure's own params/locals for that walk. A parameter passed on as a call
argument was then resolved against the corpus-wide label index and became an
`indirect_call` from the file to any function named like it. Inside a named
function the same code was already handled (#2241, #2568).
"""
from __future__ import annotations

from graphify.extract import extract

_TARGET = {"b.js": "function value(x) { return x; }\n"}


def _indirect(tmp_path, a_js: str):
    files = {"a.js": a_js, **_TARGET}
    for name, body in files.items():
        (tmp_path / name).write_text(body)
    r = extract([tmp_path / n for n in files],
                cache_root=tmp_path / "graphify-out", parallel=False)
    lbl = {n["id"]: n["label"] for n in r["nodes"]}
    return {(lbl.get(e["source"]), lbl.get(e["target"])) for e in r["edges"]
            if e["relation"] == "indirect_call"}


def test_callback_param_passed_to_a_member_call_is_not_a_reference(tmp_path):
    assert _indirect(tmp_path, "items.forEach(function (value) { s.on(value); });\n") == set()


def test_callback_param_passed_to_a_bare_call_is_not_a_reference(tmp_path):
    assert _indirect(tmp_path, "items.forEach(function (value) { emit(value); });\n") == set()


def test_param_of_a_nested_file_scope_callback_is_not_a_reference(tmp_path):
    src = "m.c(function (s) { items.forEach(function (value) { s.on(value); }); });\n"
    assert _indirect(tmp_path, src) == set()


def test_arrow_callback_params_are_not_references(tmp_path):
    src = "items.forEach((value) => emit(value));\nitems.map(value => emit(value));\n"
    assert _indirect(tmp_path, src) == set()


def test_callback_var_is_not_a_reference(tmp_path):
    src = "items.forEach(function () { var value = 1; emit(value); });\n"
    assert _indirect(tmp_path, src) == set()


def test_unbound_name_inside_a_file_scope_callback_still_resolves(tmp_path):
    assert _indirect(tmp_path, "items.forEach(function (x) { emit(value); });\n") == {("a.js", "value()")}


def test_a_sibling_callbacks_param_does_not_shadow(tmp_path):
    src = "m.c(function (value) { emit(1); }, function () { emit(value); });\n"
    assert _indirect(tmp_path, src) == {("a.js", "value()")}


def test_param_of_a_callback_inside_a_test_block_is_not_a_reference(tmp_path):
    # The inner arrow is itself an expression statement inside the `it`
    # callback, so the #3124 branch tracks it as its own body too.
    src = (
        "describe('d', () => {\n"
        "  it('t', async () => {\n"
        "    intercept((value) => respond(value, 1));\n"
        "  });\n"
        "});\n"
    )
    assert _indirect(tmp_path, src) == set()


# #5217: a closure passed in a call statement NESTED inside another function is
# also tracked as its own body by the #3124 branch, so a name it captures from
# an enclosing function or block must shadow too, not only its own params.


def test_param_captured_from_an_enclosing_function_is_not_a_reference(tmp_path):
    src = (
        "m.c(function ($scope, confirm) {\n"
        "  $scope.remove = function (value) {\n"
        "    confirm({ buttons: { ok: { action: function () { del(value); } } } });\n"
        "  };\n"
        "});\n"
    )
    assert _indirect(tmp_path, src) == set()


def test_arrow_param_captured_two_levels_down_is_not_a_reference(tmp_path):
    src = (
        "m.c(function ($scope) {\n"
        "  $scope.load = function (rows) {\n"
        "    rows.forEach((value) => {\n"
        "      if (value) { setTimeout(function () { show(value); }); }\n"
        "    });\n"
        "  };\n"
        "});\n"
    )
    assert _indirect(tmp_path, src) == set()


def test_enclosing_const_is_not_a_reference(tmp_path):
    src = (
        "m.c(function () {\n"
        "  const value = 1;\n"
        "  setTimeout(function () { show(value); });\n"
        "});\n"
    )
    assert _indirect(tmp_path, src) == set()


def test_enclosing_loop_binding_is_not_a_reference(tmp_path):
    src = (
        "m.c(function (xs) {\n"
        "  for (const value of xs) { setTimeout(function () { show(value); }); }\n"
        "});\n"
    )
    assert _indirect(tmp_path, src) == set()


def test_enclosing_catch_binding_is_not_a_reference(tmp_path):
    src = (
        "m.c(function () {\n"
        "  try { run(); } catch (value) { setTimeout(function () { show(value); }); }\n"
        "});\n"
    )
    assert _indirect(tmp_path, src) == set()


def test_unbound_name_in_a_nested_callback_still_resolves(tmp_path):
    src = (
        "m.c(function ($scope) {\n"
        "  $scope.load = function (rows) {\n"
        "    setTimeout(function () { show(value); });\n"
        "  };\n"
        "});\n"
    )
    assert _indirect(tmp_path, src) == {("a.js", "value()")}


def test_a_binding_in_a_sibling_scope_does_not_shadow_a_nested_callback(tmp_path):
    src = (
        "m.c(function ($scope) {\n"
        "  $scope.a = function (value) { save(1); };\n"
        "  $scope.b = function (rows) {\n"
        "    setTimeout(function () { show(value); });\n"
        "  };\n"
        "});\n"
    )
    assert _indirect(tmp_path, src) == {("a.js", "value()")}


# #5241: a `this.x = function (...) {}` member is its own node since #3408, so
# its body is walked on its own. Its params must shadow there, as they already
# do for the same function assigned to `$scope.x`.


def test_this_member_param_passed_to_a_bare_call_is_not_a_reference(tmp_path):
    src = "m.service('s', function () { this.d = function (value) { emit(value); }; });\n"
    assert _indirect(tmp_path, src) == set()


def test_this_member_param_passed_to_a_this_call_is_not_a_reference(tmp_path):
    src = "m.service('s', function () { this.e = function (value) { this.on(value); }; });\n"
    assert _indirect(tmp_path, src) == set()


def test_this_member_param_passed_to_an_alias_call_is_not_a_reference(tmp_path):
    src = (
        "m.service('s', function () {\n"
        "  var svc = this;\n"
        "  this.f = function (value) { return svc.pick(value); };\n"
        "});\n"
    )
    assert _indirect(tmp_path, src) == set()


def test_scope_member_param_is_not_a_reference(tmp_path):
    src = ("m.controller('c', function ($scope) "
           "{ $scope.g = function (value) { emit(value); }; });\n")
    assert _indirect(tmp_path, src) == set()


def test_this_member_in_a_named_constructor_param_is_not_a_reference(tmp_path):
    src = "function Svc() { this.d = function (value) { emit(value); }; }\n"
    assert _indirect(tmp_path, src) == set()


def test_name_captured_by_a_this_member_is_not_a_reference(tmp_path):
    src = "m.service('s', function (value) { this.d = function () { emit(value); }; });\n"
    assert _indirect(tmp_path, src) == set()


def test_unbound_name_in_a_this_member_still_resolves(tmp_path):
    src = "m.service('s', function () { this.d = function (x) { emit(value); }; });\n"
    assert _indirect(tmp_path, src) == {("d()", "value()")}


def test_this_member_in_a_function_expression_constructor_param_is_not_a_reference(tmp_path):
    src = "const Svc = function () { this.d = function (value) { emit(value); }; };\n"
    assert _indirect(tmp_path, src) == set()


def test_object_member_param_is_not_a_reference(tmp_path):
    src = (
        "m.service('s', function () {\n"
        "  var api = {};\n"
        "  api.d = function (value) { emit(value); };\n"
        "  return api;\n"
        "});\n"
    )
    assert _indirect(tmp_path, src) == set()


def test_this_arrow_member_param_is_not_a_reference(tmp_path):
    src = "m.service('s', function () { this.d = (value) => { emit(value); }; });\n"
    assert _indirect(tmp_path, src) == set()
