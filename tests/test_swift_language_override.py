"""Swift passes treat a file as Swift by its effective suffix.

A `.graphifyrc` `language.swifttpl=swift` override makes `.swifttpl` files
Swift, and `.SWIFT` is Swift too: each Swift-only pass (constructor scope,
type index, type references, dotted stubs) must see both the same way it
sees a plain `.swift` file.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract

_OVERRIDE = "language.swifttpl=swift\n"


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _run(files: list[Path], tmp_path: Path) -> dict:
    return extract(files, cache_root=tmp_path / "cache", root=tmp_path / "src", parallel=False)


def _nodes_by_file(result: dict, file: Path, label: str) -> list[str]:
    return [
        n["id"] for n in result["nodes"]
        if n.get("label") == label and str(n.get("source_file", "")).endswith(file.name)
    ]


def _targets(result: dict, source_nid: str, relation: str) -> set[str]:
    return {
        e["target"] for e in result["edges"]
        if e.get("source") == source_nid and e.get("relation") == relation
    }


def _stub_ids(result: dict, label: str) -> set[str]:
    return {
        n["id"] for n in result["nodes"]
        if n.get("label") == label and not n.get("source_file")
    }


def _single(nids: list[str]) -> str:
    assert len(nids) == 1, nids
    return nids[0]


def test_constructor_in_language_override_file_binds_lexical_type(tmp_path: Path):
    # `extension Outer { _ = Inner() }` in a remapped file sees `Outer.Inner`,
    # not the unrelated `Other.Inner`.
    base = tmp_path / "src"
    _write(base / ".graphifyrc", _OVERRIDE)
    defs = _write(base / "Defs.swift", "struct Outer { struct Inner {} }\n")
    other = _write(base / "Other.swift", "struct Other { struct Inner {} }\n")
    use = _write(base / "Use.swifttpl", "extension Outer {\n    func make() { _ = Inner() }\n}\n")
    result = _run([defs, other, use], tmp_path)

    calls = _targets(result, _single(_nodes_by_file(result, use, ".make()")), "calls")
    assert _single(_nodes_by_file(result, defs, "Inner")) in calls
    assert not calls & set(_nodes_by_file(result, other, "Inner"))


def test_constructor_in_language_override_file_skips_invisible_type(tmp_path: Path):
    # `Inner()` inside `Holder` cannot see `Outer.Inner`: no edge, no fallback.
    base = tmp_path / "src"
    _write(base / ".graphifyrc", _OVERRIDE)
    defs = _write(base / "Defs.swift", "struct Outer { struct Inner {} }\n")
    use = _write(base / "Use.swifttpl", "struct Holder {\n    func make() { _ = Inner() }\n}\n")
    result = _run([defs, use], tmp_path)

    calls = _targets(result, _single(_nodes_by_file(result, use, ".make()")), "calls")
    assert not calls & set(_nodes_by_file(result, defs, "Inner"))


def test_constructor_in_language_override_file_skips_extension_only_node(tmp_path: Path):
    # `External` is declared outside the corpus; `extension External` only adds
    # members. `External()` in a remapped file must not bind that extension node.
    base = tmp_path / "src"
    _write(base / ".graphifyrc", _OVERRIDE)
    ext = _write(base / "Ext.swift", "extension External {\n    func helper() {}\n}\n")
    use = _write(base / "Use.swifttpl", "func run() {\n    _ = External()\n}\n")
    result = _run([ext, use], tmp_path)

    ext_ids = set(_nodes_by_file(result, ext, "External"))
    assert ext_ids
    calls = _targets(result, _single(_nodes_by_file(result, use, "run()")), "calls")
    assert not calls & ext_ids


def test_language_override_file_types_are_indexed(tmp_path: Path):
    # A type declared in a remapped file is in the Swift type index.
    base = tmp_path / "src"
    _write(base / ".graphifyrc", _OVERRIDE)
    types = _write(base / "Types.swifttpl", "enum Shape { struct Point {} }\n")
    use = _write(base / "Use.swift", "struct Holder { let x: Shape.Point }\n")
    result = _run([types, use], tmp_path)

    refs = _targets(result, _single(_nodes_by_file(result, use, "Holder")), "references")
    assert _single(_nodes_by_file(result, types, "Point")) in refs
    assert not refs & _stub_ids(result, "Shape.Point")


def test_type_reference_from_language_override_file_binds(tmp_path: Path):
    # A reference written in a remapped file goes through the Swift lookup.
    base = tmp_path / "src"
    _write(base / ".graphifyrc", _OVERRIDE)
    types = _write(base / "Types.swift", "enum Shape { struct Point {} }\n")
    use = _write(base / "Use.swifttpl", "struct Holder { let x: Shape.Point }\n")
    result = _run([types, use], tmp_path)

    refs = _targets(result, _single(_nodes_by_file(result, use, "Holder")), "references")
    assert _single(_nodes_by_file(result, types, "Point")) in refs
    assert not refs & _stub_ids(result, "Shape.Point")


def test_dotted_stub_in_language_override_file_keeps_stub(tmp_path: Path):
    # `ShapePoint.ID` from a remapped file keeps its stub instead of
    # binding the unrelated `ShapePointID` by the dot-free label key.
    base = tmp_path / "src"
    _write(base / ".graphifyrc", _OVERRIDE)
    defs = _write(base / "Defs.swift", "struct ShapePointID {}\n")
    use = _write(base / "Use.swifttpl", "struct Holder { let x: ShapePoint.ID }\n")
    result = _run([defs, use], tmp_path)

    refs = _targets(result, _single(_nodes_by_file(result, use, "Holder")), "references")
    assert refs & _stub_ids(result, "ShapePoint.ID")
    assert not refs & set(_nodes_by_file(result, defs, "ShapePointID"))


def test_uppercase_swift_suffix_corpus_binds_type_reference(tmp_path: Path):
    # A corpus of `.SWIFT` files only, no override: the type-reference pass
    # still runs and the declaring file is still indexed.
    base = tmp_path / "src"
    types = _write(base / "Types.SWIFT", "enum Shape { struct Point {} }\n")
    use = _write(base / "Use.SWIFT", "struct Holder { let x: Shape.Point }\n")
    result = _run([types, use], tmp_path)

    refs = _targets(result, _single(_nodes_by_file(result, use, "Holder")), "references")
    assert _single(_nodes_by_file(result, types, "Point")) in refs
    assert not refs & _stub_ids(result, "Shape.Point")
