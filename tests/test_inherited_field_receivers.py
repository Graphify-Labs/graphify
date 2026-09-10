"""Fields declared on a superclass type receivers in a subclass (#3151).

The `field -> TypeName` tables that type a `this.<field>` / `[self.<field> …]`
receiver were looked up by the declaring class only, with no walk up the
`inherits` chain — so a field declared on a superclass typed nothing in a
subclass and every member call through it was dropped, even though the
`inherits` edge sat in the same graph. Java failed even with parent and child
in one file; cross-file needed the tables at corpus level, which is why they
now ride the per-file results keyed by class label + source_file (never node
id — the id-keyed ObjC table is how #3150 happened).
"""
from __future__ import annotations

import io
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from graphify.extract import extract

try:
    from graphify.extract import _bind_member_field_tables
except ImportError:  # pre-fix tree
    _bind_member_field_tables = None

GREETER = ("package lib;\n"
           "public class Greeter {\n"
           "    public String greet(String who) { return \"hi \" + who; }\n"
           "}\n")


def _graph(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    with redirect_stdout(io.StringIO()):
        r = extract([tmp_path / n for n in files], cache_root=Path(tempfile.mkdtemp()),
                    root=tmp_path, parallel=False)
    labels = {n["id"]: n["label"] for n in r["nodes"]}
    calls = {(labels.get(e["source"]), labels.get(e["target"])): e
             for e in r["edges"] if e.get("relation") == "calls"}
    return calls, r


# ---------------------------------------------------------------------------
# Java
# ---------------------------------------------------------------------------

def test_java_same_file_inherited_field_types_the_receiver(tmp_path):
    """The issue's first repro: PBase declares the field, Pair extends it in
    the same file — and the call was still dropped."""
    calls, _ = _graph(tmp_path, {
        "src/lib/Greeter.java": GREETER,
        "src/lib/Pair.java": (
            "package lib;\n"
            "class PBase { protected Greeter greeter = new Greeter(); }\n"
            "public class Pair extends PBase {\n"
            "    void run() { this.greeter.greet(\"same-file-inherited\"); }\n"
            "}\n"),
    })
    assert (".run()", ".greet()") in calls


def test_java_cross_file_inherited_field_types_the_receiver(tmp_path):
    """The issue's second repro: `Direct.run` resolved, `Sub.run` did not —
    one call site out of two, differing only in where the field was declared."""
    calls, _ = _graph(tmp_path, {
        "src/lib/Greeter.java": GREETER,
        "src/lib/Base.java": "package lib;\npublic class Base { protected Greeter greeter = new Greeter(); }\n",
        "src/lib/Sub.java": (
            "package lib;\npublic class Sub extends Base {\n"
            "    void run() { this.greeter.greet(\"inherited-field\"); }\n}\n"),
        "src/lib/Direct.java": (
            "package lib;\npublic class Direct { private Greeter greeter = new Greeter();\n"
            "    void go() { this.greeter.greet(\"own-field\"); }\n}\n"),
    })
    assert (".go()", ".greet()") in calls, "the own-field case must keep working"
    assert (".run()", ".greet()") in calls, "the inherited-field case was the gap"


def test_java_grandparent_field_is_reachable_through_the_chain(tmp_path):
    calls, _ = _graph(tmp_path, {
        "src/lib/Greeter.java": GREETER,
        "src/lib/A.java": "package lib;\npublic class A { protected Greeter greeter = new Greeter(); }\n",
        "src/lib/B.java": "package lib;\npublic class B extends A { }\n",
        "src/lib/C.java": (
            "package lib;\npublic class C extends B {\n"
            "    void run() { this.greeter.greet(\"grandparent\"); }\n}\n"),
    })
    assert (".run()", ".greet()") in calls


def test_java_a_redeclared_field_uses_the_nearest_declaration(tmp_path):
    """Sub redeclares the field with another type; the subclass wins."""
    calls, _ = _graph(tmp_path, {
        "src/lib/Greeter.java": GREETER,
        "src/lib/Other.java": (
            "package lib;\npublic class Other {\n"
            "    public String greet(String who) { return who; }\n"
            "    public String shout(String who) { return who; }\n}\n"),
        "src/lib/Base.java": "package lib;\npublic class Base { protected Greeter helper = new Greeter(); }\n",
        "src/lib/Sub.java": (
            "package lib;\npublic class Sub extends Base {\n"
            "    protected Other helper = new Other();\n"
            "    void run() { this.helper.shout(\"x\"); }\n}\n"),
    })
    assert (".run()", ".shout()") in calls


def test_java_untyped_bare_receiver_still_produces_nothing(tmp_path):
    """A bare lowercase receiver with no known type must stay unresolved —
    only `this.`-prefixed receivers may consult the field tables, because a
    local can shadow a field but never `this.field`."""
    calls, _ = _graph(tmp_path, {
        "src/lib/Greeter.java": GREETER,
        "src/lib/Base.java": "package lib;\npublic class Base { protected Greeter mystery = new Greeter(); }\n",
        "src/lib/Sub.java": (
            "package lib;\npublic class Sub extends Base {\n"
            "    void run() { Object mystery = fetch(); }\n"
            "    Object fetch() { return null; }\n}\n"),
    })
    assert (".run()", ".greet()") not in calls


# ---------------------------------------------------------------------------
# C# (same-file half; the per-file tables merge up the local chain)
# ---------------------------------------------------------------------------

def test_csharp_same_file_inherited_field_types_the_receiver(tmp_path):
    calls, _ = _graph(tmp_path, {"src/S.cs": (
        "public class Greeter { public void Greet() { } }\n"
        "public class PBase { protected Greeter greeter = new Greeter(); }\n"
        "public class Pair : PBase {\n"
        "    public void Run() { this.greeter.Greet(); }\n"
        "}\n")})
    assert any(s == ".Run()" and t == ".Greet()" for (s, t) in calls), sorted(calls)


# ---------------------------------------------------------------------------
# Objective-C (corpus tables already merge across files; the chain walk was
# the missing half)
# ---------------------------------------------------------------------------

try:
    import tree_sitter_objc  # noqa: F401
    HAVE_OBJC = True
except ImportError:
    HAVE_OBJC = False


@pytest.mark.skipif(not HAVE_OBJC, reason="tree-sitter-objc not installed")
def test_objc_property_on_the_superclass_types_self_field(tmp_path, monkeypatch):
    files = {
        "src/Greeter.h": "#import <Foundation/Foundation.h>\n@interface Greeter : NSObject\n- (void)greet;\n@end\n",
        "src/Greeter.m": '#import "Greeter.h"\n@implementation Greeter\n- (void)greet { NSLog(@"hi"); }\n@end\n',
        "src/Base.h": ('#import <Foundation/Foundation.h>\n#import "Greeter.h"\n'
                       "@interface Base : NSObject\n@property (nonatomic, strong) Greeter *greeter;\n@end\n"),
        "src/Base.m": '#import "Base.h"\n@implementation Base\n@end\n',
        "src/Sub.h": ('#import "Base.h"\n@interface Sub : Base\n- (void)run;\n@end\n'),
        "src/Sub.m": '#import "Sub.h"\n@implementation Sub\n- (void)run { [self.greeter greet]; }\n@end\n',
    }
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    monkeypatch.chdir(tmp_path)  # relative paths: independent of the #3150 fix
    with redirect_stdout(io.StringIO()):
        r = extract([Path(n) for n in files], cache_root=Path(tempfile.mkdtemp()), parallel=False)
    labels = {n["id"]: n["label"] for n in r["nodes"]}
    calls = {(labels.get(e["source"]), labels.get(e["target"]))
             for e in r["edges"] if e.get("relation") == "calls"}
    assert ("-run", "-greet") in calls, sorted(calls)


# ---------------------------------------------------------------------------
# The table binder itself
# ---------------------------------------------------------------------------

@pytest.mark.skipif(_bind_member_field_tables is None, reason="pre-fix tree")
def test_binder_matches_by_label_and_disambiguates_by_file():
    nodes = [
        {"id": "a_base", "label": "Base", "source_file": "a/Base.java"},
        {"id": "b_base", "label": "Base", "source_file": "b/Base.java"},
        {"id": "c_only", "label": "Only", "source_file": "c/Only.java"},
    ]
    per_file = [{"member_field_tables": [
        {"lang": "java", "class_label": "Base", "source_file": "a/Base.java",
         "fields": {"g": "Greeter"}},
        {"lang": "java", "class_label": "Only", "source_file": "c/Only.java",
         "fields": {"h": "Helper"}},
        {"lang": "csharp", "class_label": "Only", "source_file": "c/Only.java",
         "fields": {"x": "Nope"}},  # other language: ignored
    ]}]
    bound = _bind_member_field_tables(per_file, nodes, lang="java")
    assert bound == {"a_base": {"g": "Greeter"}, "c_only": {"h": "Helper"}}


@pytest.mark.skipif(_bind_member_field_tables is None, reason="pre-fix tree")
def test_binder_skips_what_it_cannot_disambiguate():
    nodes = [
        {"id": "a_base", "label": "Base", "source_file": "a/Base.java"},
        {"id": "b_base", "label": "Base", "source_file": "b/Base.java"},
    ]
    per_file = [{"member_field_tables": [
        {"lang": "java", "class_label": "Base", "source_file": "elsewhere/Base.java",
         "fields": {"g": "Greeter"}},
    ]}]
    # both candidates share the basename -> still ambiguous -> bind nothing
    assert _bind_member_field_tables(per_file, nodes, lang="java") == {}
