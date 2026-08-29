"""ObjC property/ivar receivers must type through the class's field table (#1556).

`[self.bar doIt]` and `[_ivarBar doIt]` are the ordinary ways an ObjC object talks
to a collaborator held in a `@property` or ivar, but neither ever resolved: the
extractor's raw-call gate admitted only bare-identifier receivers (a
`field_expression` was dropped), and the receiver type table held only method-body
locals. The fix records a per-CLASS `field -> ClassName` table from bare capitalized
`@property` / ivar declarations and adds a resolver arm for the exact
`self.<field>` receiver shape plus a field-table fallback for bare identifiers.

PRECISION over recall, as everywhere in this resolver:

* only the exact `self.<field>` receiver is captured — `obj.prop`, chains, and
  `Foo.shared` stay dropped. Passing the DOTTED text through would let a
  capitalized `Foo.shared` enter the explicit-class arm, where `_key` strips the
  dot and collides with a real class `FooShared` (a fabricated edge);
* a `generic_specifier` (`NSArray<Bar *>`) or `typedefed_specifier` (`id<P>`)
  property never types a receiver;
* locals shadow fields for bare identifiers, conflicts drop the entry, and the
  single-definition god-node guard still gates the type lookup.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _label(result: dict, nid: str) -> str:
    for n in result["nodes"]:
        if n["id"] == nid:
            return n.get("label", "")
    return f"?{nid}"


def _call_edges(result: dict, relations=("calls",)):
    """{(source_label, relation, target_label, confidence)} for the given relations."""
    out = set()
    for e in result["edges"]:
        if e.get("relation") in relations:
            out.add((
                _label(result, e["source"]),
                e["relation"],
                _label(result, e["target"]),
                e.get("confidence"),
            ))
    return out


_BAR_H = "@interface Bar : NSObject\n- (void)doIt;\n@end\n"
_BAR_M = '#import "Bar.h"\n@implementation Bar\n- (void)doIt {}\n@end\n'


def test_objc_property_receiver_resolves(tmp_path: Path):
    # `[self.bar doIt]` with `@property Bar *bar` in Foo.h -> the field types the
    # receiver -> cross-file calls edge to Bar's -doIt (INFERRED).
    base = tmp_path / "src"
    _write(base / "Bar.h", _BAR_H)
    _write(base / "Bar.m", _BAR_M)
    _write(base / "Foo.h",
           '#import "Bar.h"\n@interface Foo : NSObject\n'
           "@property (nonatomic, strong) Bar *bar;\n- (void)viaProperty;\n@end\n")
    _write(base / "Foo.m",
           '#import "Foo.h"\n@implementation Foo\n'
           "- (void)viaProperty { [self.bar doIt]; }\n@end\n")
    result = extract(sorted(base.glob("*")), cache_root=tmp_path / "cache")

    calls = _call_edges(result)
    assert ("-viaProperty", "calls", "-doIt", "INFERRED") in calls


def test_objc_ivar_receiver_resolves(tmp_path: Path):
    # `[_ivarBar doIt]` with `Bar *_ivarBar;` in the @implementation ivar block ->
    # bare identifier falls back from the (empty) local table to the field table.
    base = tmp_path / "src"
    _write(base / "Bar.h", _BAR_H)
    _write(base / "Bar.m", _BAR_M)
    _write(base / "Foo.m",
           '#import "Bar.h"\n@implementation Foo {\n    Bar *_ivarBar;\n}\n'
           "- (void)viaIvar { [_ivarBar doIt]; }\n@end\n")
    result = extract(sorted(base.glob("*")), cache_root=tmp_path / "cache")

    calls = _call_edges(result)
    assert ("-viaIvar", "calls", "-doIt", "INFERRED") in calls


def test_objc_header_ivar_block_receiver_resolves(tmp_path: Path):
    # The `@interface Foo { Bar *_bar; }` ivar block records the same way.
    base = tmp_path / "src"
    _write(base / "Bar.h", _BAR_H)
    _write(base / "Bar.m", _BAR_M)
    _write(base / "Foo.h",
           '#import "Bar.h"\n@interface Foo : NSObject {\n    Bar *_bar;\n}\n'
           "- (void)viaIvar;\n@end\n")
    _write(base / "Foo.m",
           '#import "Foo.h"\n@implementation Foo\n'
           "- (void)viaIvar { [_bar doIt]; }\n@end\n")
    result = extract(sorted(base.glob("*")), cache_root=tmp_path / "cache")

    calls = _call_edges(result)
    assert ("-viaIvar", "calls", "-doIt", "INFERRED") in calls


def test_objc_dotted_class_receiver_fabricates_nothing(tmp_path: Path):
    """The no-fabrication decoy: `[Foo.shared doIt]` next to a REAL class FooShared.

    A naive widen that passed the dotted receiver text through would enter the
    explicit-class arm, where `_key("Foo.shared")` == `_key("FooShared")` — binding
    the call to an unrelated class at confidence 1.0. Only `self.<field>` is
    captured, so this receiver must yield ZERO edges from the caller.
    """
    base = tmp_path / "src"
    _write(base / "FooShared.h",
           "@interface FooShared : NSObject\n- (void)doIt;\n@end\n")
    _write(base / "FooShared.m",
           '#import "FooShared.h"\n@implementation FooShared\n- (void)doIt {}\n@end\n')
    _write(base / "Use.m",
           '#import "FooShared.h"\n@implementation Use\n'
           "- (void)go { [Foo.shared doIt]; }\n@end\n")
    result = extract(sorted(base.glob("*")), cache_root=tmp_path / "cache")

    from_go = [e for e in result["edges"]
               if e.get("relation") in ("calls", "references")
               and _label(result, e["source"]) == "-go"]
    assert from_go == []


def test_objc_local_shadows_property_field(tmp_path: Path):
    # A local `Baz *bar` shadows the class's `@property Bar *bar`; `[bar m]` must
    # resolve via the LOCAL's type (Baz's -m), never the property's (Bar's -m).
    base = tmp_path / "src"
    _write(base / "Bar.h", "@interface Bar : NSObject\n- (void)m;\n@end\n")
    _write(base / "Bar.m", '#import "Bar.h"\n@implementation Bar\n- (void)m {}\n@end\n')
    _write(base / "Baz.h", "@interface Baz : NSObject\n- (void)m;\n@end\n")
    _write(base / "Baz.m", '#import "Baz.h"\n@implementation Baz\n- (void)m {}\n@end\n')
    _write(base / "Foo.h",
           '#import "Bar.h"\n@interface Foo : NSObject\n'
           "@property (nonatomic, strong) Bar *bar;\n- (void)go;\n@end\n")
    _write(base / "Foo.m",
           '#import "Foo.h"\n#import "Baz.h"\n@implementation Foo\n'
           "- (void)go {\n  Baz *bar = [[Baz alloc] init];\n  [bar m];\n}\n@end\n")
    result = extract(sorted(base.glob("*")), cache_root=tmp_path / "cache")

    src_by_id = {n["id"]: n.get("source_file") for n in result["nodes"]}
    m_calls = [
        e for e in result["edges"]
        if e.get("relation") == "calls"
        and _label(result, e["source"]) == "-go"
        and _label(result, e["target"]) == "-m"
    ]
    assert len(m_calls) == 1
    assert Path(src_by_id[m_calls[0]["target"]]).name == "Baz.h"


def test_objc_ambiguous_field_type_emits_no_edge(tmp_path: Path):
    # Two in-corpus classes labelled Bar -> the property receiver's type lookup has
    # two candidates and the single-definition god-node guard bails: ZERO edges.
    base = tmp_path / "src"
    for d in ("a", "b"):
        _write(base / d / "Bar.h", _BAR_H)
        _write(base / d / "Bar.m", _BAR_M)
    _write(base / "Foo.h",
           '#import "a/Bar.h"\n@interface Foo : NSObject\n'
           "@property (nonatomic, strong) Bar *bar;\n- (void)go;\n@end\n")
    _write(base / "Foo.m",
           '#import "Foo.h"\n@implementation Foo\n- (void)go { [self.bar doIt]; }\n@end\n')
    result = extract(sorted(base.rglob("*.[hm]")), cache_root=tmp_path / "cache")

    from_go = [e for e in result["edges"]
               if e.get("relation") == "calls" and _label(result, e["source"]) == "-go"]
    assert from_go == []


def test_objc_generic_and_protocol_typed_properties_are_never_recorded(tmp_path: Path):
    # `NSArray<Bar *> *items` (generic_specifier) and `id<Locking> locker`
    # (typedefed_specifier) never enter the field table -> no edge, no guess.
    base = tmp_path / "src"
    _write(base / "Bar.h", _BAR_H)
    _write(base / "Bar.m", _BAR_M)
    _write(base / "Foo.h",
           '#import "Bar.h"\n@interface Foo : NSObject\n'
           "@property (nonatomic) NSArray<Bar *> *items;\n"
           "@property (nonatomic) id<Locking> locker;\n"
           "- (void)viaGeneric;\n- (void)viaProtocol;\n@end\n")
    _write(base / "Foo.m",
           '#import "Foo.h"\n@implementation Foo\n'
           "- (void)viaGeneric { [self.items doIt]; }\n"
           "- (void)viaProtocol { [self.locker doIt]; }\n@end\n")
    result = extract(sorted(base.glob("*")), cache_root=tmp_path / "cache")

    typed = [e for e in result["edges"]
             if e.get("relation") == "calls"
             and _label(result, e["source"]) in ("-viaGeneric", "-viaProtocol")]
    assert typed == []


def test_objc_local_receiver_and_alloc_reference_unchanged(tmp_path: Path):
    # The pre-existing paths still work next to the new ones: a `Foo *f` local
    # types `[f doThing]` (INFERRED) and `[[Foo alloc] init]` still emits the
    # `references` edge to the allocated type.
    base = tmp_path / "src"
    _write(base / "Foo.h", "@interface Foo : NSObject\n- (void)doThing;\n@end\n")
    _write(base / "Foo.m", '#import "Foo.h"\n@implementation Foo\n- (void)doThing {}\n@end\n')
    _write(base / "Bar.m",
           '#import "Foo.h"\n@implementation Bar\n'
           "- (void)viaLocal {\n  Foo *f = [[Foo alloc] init];\n  [f doThing];\n}\n@end\n")
    result = extract(sorted(base.glob("*")), cache_root=tmp_path / "cache")

    calls = _call_edges(result)
    assert ("-viaLocal", "calls", "-doThing", "INFERRED") in calls
    refs = _call_edges(result, relations=("references",))
    assert any(s == "-viaLocal" and t == "Foo" for s, _, t, _ in refs)
