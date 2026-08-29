"""ObjC receiver typing must not treat a ``@protocol`` as a message receiver (#1556).

The ObjC extractor labels a protocol declaration ``<Name>``, and the member-call
resolver's ``_key()`` strips the angle brackets — so a protocol and a class of the
same name collapse to one index key. ObjC keeps protocol and class names in separate
namespaces (``@protocol NSObject`` and ``@interface NSObject`` both exist in
Foundation), so same-named pairs are ordinary, and both outcomes were wrong:

* protocol only in the corpus -> ``[Reload reload]`` bound to the PROTOCOL's method
  declaration at confidence 1.0 (a WRONG edge, not just a missing one);
* protocol AND class -> two candidates tripped the single-definition god-node guard,
  so a call that should resolve produced NO edge.

Excluding protocols from the receiver-type index fixes both. Protocols remain valid
`implements` targets; only receiver typing ignores them.
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


def _edges(result: dict, relation: str):
    """{(source_label, target_label, confidence)} for edges of one relation."""
    return {
        (_label(result, e["source"]), _label(result, e["target"]), e.get("confidence"))
        for e in result["edges"]
        if e.get("relation") == relation
    }


def test_objc_protocol_only_receiver_emits_no_call_edge(tmp_path: Path):
    """No class named Reload exists, so `[Reload reload]` is untypable -> ZERO edges.

    The decoy is the protocol's own `-reload` declaration: it must NOT be the target.
    """
    base = tmp_path / "src"
    _write(base / "Reload.h",
           "@protocol Reload <NSObject>\n- (void)reload;\n@end\n")
    _write(base / "Use.h", '#import "Reload.h"\n@interface Use : NSObject\n- (void)go;\n@end\n')
    _write(base / "Use.m",
           '#import "Use.h"\n@implementation Use\n- (void)go { [Reload reload]; }\n@end\n')
    result = extract(sorted(base.glob("*")), cache_root=tmp_path / "cache")

    from_go = [e for e in result["edges"]
               if e.get("relation") == "calls" and _label(result, e["source"]) == "-go"]
    assert from_go == []


def test_objc_class_resolves_past_a_same_named_protocol(tmp_path: Path):
    """A protocol and a class may share a name; the class must still resolve.

    `[Locking lock]` resolves to the CLASS's `+lock`, never the protocol's `-lock`.
    """
    base = tmp_path / "src"
    _write(base / "Locking.h",
           "@protocol Locking <NSObject>\n- (void)lock;\n@end\n")
    _write(base / "LockingImpl.h",
           '#import "Locking.h"\n@interface Locking : NSObject\n+ (void)lock;\n@end\n')
    _write(base / "LockingImpl.m",
           '#import "LockingImpl.h"\n@implementation Locking\n+ (void)lock {}\n@end\n')
    _write(base / "Worker.h",
           '#import "LockingImpl.h"\n@interface Worker : NSObject\n- (void)run;\n@end\n')
    _write(base / "Worker.m",
           '#import "Worker.h"\n@implementation Worker\n- (void)run { [Locking lock]; }\n@end\n')
    result = extract(sorted(base.glob("*")), cache_root=tmp_path / "cache")

    calls = _edges(result, "calls")
    assert ("-run", "+lock", "EXTRACTED") in calls
    assert ("-run", "-lock", "EXTRACTED") not in calls


def test_objc_protocol_stays_a_valid_implements_target(tmp_path: Path):
    """The exclusion is scoped to receiver typing: adoption edges are unaffected."""
    base = tmp_path / "src"
    _write(base / "Reload.h",
           "@protocol Reload <NSObject>\n- (void)reload;\n@end\n")
    _write(base / "Widget.h",
           '#import "Reload.h"\n@interface Widget : NSObject <Reload>\n- (void)reload;\n@end\n')
    result = extract(sorted(base.glob("*")), cache_root=tmp_path / "cache")

    implements = {(s, t) for s, t, _ in _edges(result, "implements")}
    assert ("Widget", "<Reload>") in implements
