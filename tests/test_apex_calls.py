"""Tests for the tree-sitter Apex path: calls, and the regex fallback."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from graphify.extract import extract
from graphify.extractors.apex import (
    _extract_apex_ast,
    _extract_apex_regex,
    extract_apex,
)

_needs_grammar = pytest.mark.skipif(
    importlib.util.find_spec("tree_sitter_language_pack") is None,
    reason="tree-sitter-language-pack not installed (optional [apex] extra)",
)


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _calls(result: dict) -> set[tuple[str, str]]:
    by_id = {n["id"]: n for n in result["nodes"]}
    return {(by_id[e["source"]]["label"], by_id[e["target"]]["label"])
            for e in result["edges"] if e["relation"] == "calls"}


SERVICE = """public with sharing class Svc {
    public static void run() {
        helper();
    }
    private static void helper() {}
}
"""


@_needs_grammar
def test_same_file_call_becomes_an_edge(tmp_path: Path):
    result = extract_apex(_write(tmp_path / "Svc.cls", SERVICE))
    assert (".run()", ".helper()") in _calls(result)


@_needs_grammar
def test_regex_fallback_finds_no_calls(tmp_path: Path):
    """The point of the grammar: the regex path cannot produce calls at all."""
    f = _write(tmp_path / "Svc.cls", SERVICE)
    assert _calls(_extract_apex_regex(f)) == set()
    assert _calls(_extract_apex_ast(f))


@_needs_grammar
def test_cross_file_call_reaches_the_real_method(tmp_path: Path):
    caller = _write(tmp_path / "classes/Caller.cls",
                    "public class Caller {\n"
                    "    void go() { Callee.work(); }\n"
                    "}\n")
    callee = _write(tmp_path / "classes/Callee.cls",
                    "public class Callee {\n"
                    "    public static void work() {}\n"
                    "}\n")
    result = extract([caller, callee], cache_root=tmp_path)

    by_id = {n["id"]: n for n in result["nodes"]}
    hits = [e for e in result["edges"]
            if e["relation"] == "calls"
            and by_id.get(e["target"], {}).get("label") == ".work()"]
    assert hits, "no calls edge onto Callee.work"
    target = by_id[hits[0]["target"]]
    assert Path(target["source_file"]).name == "Callee.cls"


@_needs_grammar
def test_a_local_variable_is_not_a_call(tmp_path: Path):
    """Negative control: naming a variable after a method is not a call.

    The regex path had no notion of scope, so anything shaped like `name(` read
    as a call site. `helper` here is only ever assigned and returned.
    """
    result = extract_apex(_write(
        tmp_path / "Svc.cls",
        "public class Svc {\n"
        "    public static String run() {\n"
        "        String helper = 'x';\n"
        "        return helper;\n"
        "    }\n"
        "    private static void helper() {}\n"
        "}\n"))
    assert (".run()", ".helper()") not in _calls(result)


@_needs_grammar
def test_a_commented_out_call_is_not_a_call(tmp_path: Path):
    """Negative control: a call inside a comment must not produce an edge."""
    result = extract_apex(_write(
        tmp_path / "Svc.cls",
        "public class Svc {\n"
        "    public static void run() {\n"
        "        // helper();\n"
        "    }\n"
        "    private static void helper() {}\n"
        "}\n"))
    assert _calls(result) == set()


@_needs_grammar
def test_dml_in_a_comment_is_not_dml(tmp_path: Path):
    """Negative control: the word `merge` in prose is not a DML statement."""
    result = extract_apex(_write(
        tmp_path / "Svc.cls",
        "public class Svc {\n"
        "    // Merge variable used by the callout\n"
        "    private static final String TOKEN = 'x';\n"
        "}\n"))
    assert "merge" not in {n["label"] for n in result["nodes"]}


@_needs_grammar
def test_modifier_order_and_inheritance(tmp_path: Path):
    result = extract_apex(_write(
        tmp_path / "Sub.cls",
        "public abstract with sharing class Sub extends Base implements Iface {\n"
        "}\n"))
    by_id = {n["id"]: n for n in result["nodes"]}
    rels = {(e["relation"], by_id[e["target"]]["label"]) for e in result["edges"]}
    assert "Sub" in {n["label"] for n in result["nodes"]}
    assert ("extends", "Base") in rels
    assert ("implements", "Iface") in rels


@_needs_grammar
def test_referenced_types_stay_sourceless(tmp_path: Path):
    result = extract_apex(_write(
        tmp_path / "Sub.cls",
        "public class Sub extends Base {\n"
        "    void m() {\n"
        "        List<Account> a = [SELECT Id FROM Account];\n"
        "    }\n"
        "}\n"))
    by_label = {n["label"]: n for n in result["nodes"]}
    assert by_label["Base"]["source_file"] == ""
    assert by_label["Account"]["source_file"] == ""
    assert by_label["Sub"]["source_file"].endswith("Sub.cls")


@_needs_grammar
def test_soql_and_dml_survive_the_ast_path(tmp_path: Path):
    """Parity guard: the AST path must keep what the regex path found."""
    result = extract_apex(_write(
        tmp_path / "Svc.cls",
        "public class Svc {\n"
        "    void m() {\n"
        "        List<Account> a = [SELECT Id FROM Account];\n"
        "        insert a;\n"
        "    }\n"
        "}\n"))
    labels = {n["label"] for n in result["nodes"]}
    assert {"Account", "insert"} <= labels


@_needs_grammar
def test_trigger_records_its_sobject(tmp_path: Path):
    result = extract_apex(_write(
        tmp_path / "T.trigger",
        "trigger T on Account (before insert) { Svc.run(); }\n"))
    by_id = {n["id"]: n for n in result["nodes"]}
    assert ("uses", "Account") in {
        (e["relation"], by_id[e["target"]]["label"]) for e in result["edges"]}


def test_missing_grammar_falls_back_to_regex(tmp_path: Path, monkeypatch):
    """With the extra absent, Apex must still extract — just without calls.

    Simulated by making the grammar import fail, which is what an install
    without the [apex] extra looks like.
    """
    import builtins
    real_import = builtins.__import__

    def _no_grammar(name, *args, **kwargs):
        if name.startswith("tree_sitter_language_pack"):
            raise ImportError("simulated: extra not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_grammar)
    f = _write(tmp_path / "Svc.cls", SERVICE)
    assert _extract_apex_ast(f) is None
    result = extract_apex(f)
    assert "Svc" in {n["label"] for n in result["nodes"]}
    assert _calls(result) == set()


@_needs_grammar
def test_constructor_call_is_a_call(tmp_path: Path):
    """`new Other()` is a call site; its callee sits in a different AST field."""
    result = extract_apex(_write(
        tmp_path / "Svc.cls",
        "public class Svc {\n"
        "    void run() { Other o = new Other(); }\n"
        "}\n"))
    assert "Other" in {n["label"] for n in result["nodes"]}
    by_id = {n["id"]: n for n in result["nodes"]}
    assert ".run()" in {by_id[e["source"]]["label"] for e in result["edges"]
                        if e["relation"] == "calls"} or any(
        rc.get("callee") == "Other" for rc in (result.get("raw_calls") or []))


@_needs_grammar
def test_calls_are_attributed_to_the_calling_method(tmp_path: Path):
    """Each call must hang off the method it is written in, not its sibling."""
    result = extract_apex(_write(
        tmp_path / "Svc.cls",
        "public class Svc {\n"
        "    void first() { alpha(); }\n"
        "    void second() { beta(); }\n"
        "    void alpha() {}\n"
        "    void beta() {}\n"
        "}\n"))
    calls = _calls(result)
    assert (".first()", ".alpha()") in calls
    assert (".second()", ".beta()") in calls
    assert (".first()", ".beta()") not in calls
    assert (".second()", ".alpha()") not in calls


def test_engine_failure_falls_back_to_regex(tmp_path: Path, monkeypatch):
    """A grammar that loads but fails must fall back, not return a stub result."""
    from graphify.extractors import engine

    monkeypatch.setattr(
        engine, "_extract_generic",
        lambda *a, **k: {"nodes": [], "edges": [], "error": "simulated failure"})
    f = _write(tmp_path / "Svc.cls", SERVICE)
    assert _extract_apex_ast(f) is None
    assert "Svc" in {n["label"] for n in extract_apex(f)["nodes"]}


@_needs_grammar
def test_collection_method_is_not_a_cross_file_call(tmp_path: Path):
    """Negative control: `rows.add(x)` must not bind to a user method named add.

    Cross-file calls resolve by bare name, so one class defining `add()` would
    otherwise collect an edge from every class that appends to a list.
    """
    lib = _write(tmp_path / "classes/Mock.cls",
                 "public class Mock {\n"
                 "    public Mock add(String s) { return this; }\n"
                 "}\n")
    user = _write(tmp_path / "classes/User.cls",
                  "public class User {\n"
                  "    void run() {\n"
                  "        List<String> rows = new List<String>();\n"
                  "        rows.add('x');\n"
                  "    }\n"
                  "}\n")
    result = extract([lib, user], cache_root=tmp_path)
    by_id = {n["id"]: n for n in result["nodes"]}
    offenders = [e for e in result["edges"]
                 if e["relation"] == "calls"
                 and by_id.get(e["target"], {}).get("label") == ".add()"
                 and "User.cls" in str(e.get("source_file", ""))]
    assert not offenders, f"list.add() bound to Mock.add: {offenders}"


@_needs_grammar
def test_a_class_still_calls_its_own_collection_named_method(tmp_path: Path):
    """The filter must not cost a real same-file call to a method named `add`."""
    result = extract_apex(_write(
        tmp_path / "Mock.cls",
        "public class Mock {\n"
        "    public Mock get(String s) { return add('GET', s); }\n"
        "    public Mock add(String verb, String s) { return this; }\n"
        "}\n"))
    assert (".get()", ".add()") in _calls(result)


@_needs_grammar
def test_collection_constructor_is_not_a_call(tmp_path: Path):
    """Negative control: `new List<Account>()` is not a dependency."""
    result = extract_apex(_write(
        tmp_path / "Svc.cls",
        "public class Svc {\n"
        "    void run() { List<Account> rows = new List<Account>(); }\n"
        "}\n"))
    assert "List" not in {n["label"] for n in result["nodes"]}


@_needs_grammar
def test_unparsable_file_falls_back_to_regex(tmp_path: Path):
    """tree-sitter is error-tolerant, so a broken parse must be caught explicitly.

    It returns a tree containing ERROR nodes rather than raising, so without a
    check the extractor would hand back a confidently wrong AST instead of
    letting the regex path degrade predictably.
    """
    f = _write(tmp_path / "Broken.cls",
               "public class Broken { void m() { if ( { } }} ### garbage\n")
    assert _extract_apex_ast(f) is None
    assert "Broken" in {n["label"] for n in extract_apex(f)["nodes"]}


@_needs_grammar
def test_valid_file_does_not_fall_back(tmp_path: Path):
    """Guard the other direction: the error check must not reject good Apex."""
    assert _extract_apex_ast(_write(tmp_path / "Svc.cls", SERVICE)) is not None


@_needs_grammar
def test_rest_verbs_are_entry_points(tmp_path: Path):
    """A @HttpGet method is reachable from outside Apex, so the file contains it.

    Without this a @RestResource class looks dead: nothing in the corpus calls
    it, because the caller is an HTTP client.
    """
    result = extract_apex(_write(
        tmp_path / "Api.cls",
        "@RestResource(urlMapping='/api/*')\n"
        "global with sharing class Api {\n"
        "    @HttpGet\n"
        "    global static String fetch() { return null; }\n"
        "}\n"))
    by_id = {n["id"]: n for n in result["nodes"]}
    file_nid = next(n["id"] for n in result["nodes"] if n["label"] == "Api.cls")
    contained = {by_id[e["target"]]["label"] for e in result["edges"]
                 if e["relation"] == "contains" and e["source"] == file_nid}
    assert ".fetch()" in contained
