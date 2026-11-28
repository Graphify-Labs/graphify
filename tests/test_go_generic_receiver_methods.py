"""A generic type's methods must attach to the type's own node (#3368).

`(b *Box[T]) Get()` reads its receiver's `type` field as `Box[T]` verbatim,
but the type declaration's own id is the bare `Box`: `type Box[T any] struct
{...}` captures `[T any]` as a separate `type_parameter_list`, never part of
the name. Without stripping the instantiation before the receiver's text
turns into an id, `Box`'s own node and the method's owner node were two
different, disconnected ids — `graphify explain Box` (or anything else
walking `method` edges from the type) found no methods at all, even though
`go_type_table`-based call resolution could still reach them through the
receiver's own-function `self_type` binding.
"""
from pathlib import Path

from graphify.extract import extract


def _method_owner(r, method_label: str) -> str | None:
    target = next(n["id"] for n in r["nodes"] if n["label"] == method_label)
    return next(
        (e["source"] for e in r["edges"]
         if e["relation"] == "method" and e["target"] == target),
        None,
    )


def test_generic_receiver_method_attaches_to_its_own_type(tmp_path):
    (tmp_path / "g.go").write_text(
        "package p\n"
        "type Box[T any] struct { val T }\n"
        "func (b *Box[T]) Get() T { return b.val }\n"
    )
    r = extract([tmp_path / "g.go"], cache_root=tmp_path, parallel=False)
    box_nid = next(n["id"] for n in r["nodes"] if n["label"] == "Box")
    assert _method_owner(r, ".Get()") == box_nid


def test_value_receiver_without_a_pointer_also_attaches_to_its_own_type(tmp_path):
    (tmp_path / "g.go").write_text(
        "package p\n"
        "type Box[T any] struct { val T }\n"
        "func (b Box[T]) Get() T { return b.val }\n"
    )
    r = extract([tmp_path / "g.go"], cache_root=tmp_path, parallel=False)
    box_nid = next(n["id"] for n in r["nodes"] if n["label"] == "Box")
    assert _method_owner(r, ".Get()") == box_nid


def test_a_generic_type_mints_exactly_one_callable_class_node(tmp_path):
    # Before the fix, the type declaration and the method's owner were two
    # separate `_callable_class` nodes ("Box" and "Box[T]"): the same type
    # appeared twice, once with no methods.
    (tmp_path / "g.go").write_text(
        "package p\n"
        "type Box[T any] struct { val T }\n"
        "func (b *Box[T]) Get() T { return b.val }\n"
        "func (b *Box[T]) Set(v T) { b.val = v }\n"
    )
    r = extract([tmp_path / "g.go"], cache_root=tmp_path, parallel=False)
    box_nodes = [n for n in r["nodes"] if n["label"].startswith("Box")]
    assert [n["label"] for n in box_nodes] == ["Box"]


def test_generic_receivers_concrete_field_chain_resolves_through_its_own_type(tmp_path):
    # A generic type can still have a field of a concrete, non-type-parameter
    # type; a call through it must resolve to the right target even though
    # "Print" is ambiguous corpus-wide (two types both declare it).
    (tmp_path / "box.go").write_text(
        "package p\n"
        "type Box[T any] struct {\n\tval T\n\tmeta *Metadata\n}\n"
        "func (b *Box[T]) Describe() { b.meta.Print() }\n"
    )
    (tmp_path / "metadata.go").write_text(
        "package p\ntype Metadata struct{}\nfunc (m *Metadata) Print() {}\n"
    )
    (tmp_path / "other.go").write_text(
        "package p\ntype Other struct{}\nfunc (o *Other) Print() {}\n"
    )
    r = extract(
        [tmp_path / "box.go", tmp_path / "metadata.go", tmp_path / "other.go"],
        cache_root=tmp_path, parallel=False,
    )
    label_of = {n["id"]: n["label"] for n in r["nodes"]}
    source_file_of = {n["id"]: str(n.get("source_file") or "") for n in r["nodes"]}
    calls = [
        e for e in r["edges"]
        if e["relation"] == "calls" and label_of.get(e["target"]) == ".Print()"
    ]
    assert len(calls) == 1
    assert source_file_of[calls[0]["target"]].endswith("metadata.go")
