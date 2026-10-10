"""`this.X = function` members in every enclosing-function form (#3408).

#1322's fix captured `this.X = fn` only when the enclosing function was a
function *declaration*. Function-expression forms — assigned to a const, an
arrow, an IIFE, or a callback argument (the AngularJS service pattern) —
silently dropped every member, leaving e.g. an AngularJS frontend opaque
below file level.
"""

from graphify.extract import extract


def _labels(tmp_path, monkeypatch, source):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app.js").write_text(source, encoding="utf-8")
    r = extract([tmp_path / "app.js"], cache_root=tmp_path)
    return r, sorted(n.get("label", "") for n in r["nodes"])


FIVE_FORMS = (
    "function DeclFn(){ this.inDecl = function(){ return 1; }; }\n"
    "const AnonToConst = function(){ this.inAnonConst = function(){ return 2; }; };\n"
    "const ArrowToConst = () => { this.inArrow = function(){ return 3; }; };\n"
    "callIt(function(){ this.inCallbackArg = function(){ return 4; }; });\n"
    "(function(){ this.inIIFE = function(){ return 5; }; })();\n"
)


def test_every_enclosing_form_keeps_this_members(tmp_path, monkeypatch):
    _, labels = _labels(tmp_path, monkeypatch, FIVE_FORMS)
    for member in ("inDecl", "inAnonConst", "inArrow", "inCallbackArg", "inIIFE"):
        assert any(member in l for l in labels), (member, labels)


def test_const_function_members_are_methods_of_the_const(tmp_path, monkeypatch):
    """`const F = function(){ this.X = fn }` — X is a method owned by F."""
    r, _ = _labels(
        tmp_path, monkeypatch,
        "const Service = function(){ this.load = function(){ return 1; }; };\n",
    )
    method_edges = [
        (e["source"], e["target"]) for e in r["edges"] if e["relation"] == "method"
    ]
    assert any("service" in s and s + "_load" == t for s, t in method_edges), (
        method_edges
    )


def test_angular_service_registration_members_survive(tmp_path, monkeypatch):
    """The framework shape the issue measured at 87% file-node-only."""
    r, labels = _labels(
        tmp_path, monkeypatch,
        "angular.module('myApp').service('$thingService', function ($rootScope, $http) {\n"
        "\tthis.loadThing = function (id) { return $http.get(id); };\n"
        "\tthis.saveThing = function (thing) { return $http.post(thing); };\n"
        "});\n",
    )
    assert any("loadThing" in l for l in labels), labels
    assert any("saveThing" in l for l in labels), labels
    # Anonymous enclosing function: members hang off the file node, with
    # file-qualified ids (the #1077 phantom-god-node guard's requirement).
    contains = {
        (e["source"], e["target"]) for e in r["edges"] if e["relation"] == "contains"
    }
    file_nid = next(n["id"] for n in r["nodes"] if n.get("label") == "app.js")
    assert any(s == file_nid and t.endswith("loadthing") for s, t in contains), contains
    for n in r["nodes"]:
        if "loadthing" in n["id"]:
            assert n["id"].startswith("app"), n["id"]


def test_callback_locals_do_not_become_nodes(tmp_path, monkeypatch):
    """The #1077 guard is untouched: a const inside a callback stays local."""
    _, labels = _labels(
        tmp_path, monkeypatch,
        "callIt(function(){ const helper = new Set(); this.run = function(){ return helper; }; });\n",
    )
    assert any("run" in l for l in labels), labels
    assert not any(l == "helper" for l in labels), labels


def test_declaration_form_is_not_double_emitted(tmp_path, monkeypatch):
    """The declaration branch still owns its scan — one node, one method edge."""
    r, _ = _labels(
        tmp_path, monkeypatch,
        "function DeclFn(){ this.inDecl = function(){ return 1; }; }\n",
    )
    member_nodes = [n for n in r["nodes"] if "indecl" in n["id"]]
    assert len(member_nodes) == 1, member_nodes
    method_edges = [e for e in r["edges"]
                    if e["relation"] == "method" and "indecl" in e["target"]]
    assert len(method_edges) == 1, method_edges
