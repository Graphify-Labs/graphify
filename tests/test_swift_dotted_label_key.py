"""Swift cross-file type resolution: a dotted stub never binds through the label key.

See docs/swift-cross-file-type-resolution-rfc.md. The generic stub rewire keys a label
by dropping every non-identifier character, so the dotted Swift stub
``MenuItem.ID`` shares the key ``MenuItemID`` with an unrelated
top-level ``enum MenuItemID``. A dotted Swift name binds only through
``_swift_lookup``; when that lookup knows no ``ID`` (status "external") the reference
stays on its stub.

The style follows tests/test_swift_type_resolution.py: write the files into
``tmp_path`` and call ``extract(files, cache_root=..., root=..., parallel=False)``.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from graphify.extract import extract


# ── helpers ───────────────────────────────────────────────────────────────────

def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _extract(files: list[Path], tmp_path: Path) -> dict:
    return extract(files, cache_root=tmp_path / "cache", root=tmp_path / "src", parallel=False)


def _sf(item: dict) -> str:
    return str(item.get("source_file") or "").replace("\\", "/")


def _by_id(result: dict) -> dict[str, dict]:
    return {n["id"]: n for n in result["nodes"]}


def _is_stub(result: dict, nid: str) -> bool:
    """A sourceless node: what an unresolved type reference leaves behind."""
    node = _by_id(result).get(nid)
    return node is not None and not _sf(node)


def _node(result: dict, label: str, suffix: str) -> str:
    """The id of the one sourced node ``label`` from ``suffix``."""
    found = [
        n["id"] for n in result["nodes"]
        if n.get("label") == label and _sf(n).endswith(suffix)
    ]
    assert len(found) == 1, f"expected one {label!r} in {suffix}, got {found}"
    return found[0]


def _targets(result: dict, source: str, relations=("references",)) -> set[str]:
    return {
        e["target"] for e in result["edges"]
        if e.get("source") == source and e.get("relation") in relations
    }


# ── regression ────────────────────────────────────────────────────────────────

_ITEM_WITHOUT_NESTED_ID = "struct MenuItem {\n    var name: String\n}\n"


@pytest.mark.parametrize(
    "item_source",
    [None, _ITEM_WITHOUT_NESTED_ID],
    ids=["item-undeclared", "item-without-nested-id"],
)
def test_dotted_member_type_does_not_bind_concatenated_type_name(
    tmp_path: Path, item_source: str | None,
):
    # `var id: MenuItem.ID` names a nested `ID` nobody declares. The label
    # key of its stub is `MenuItemID`, so the generic rewire bound it to the
    # unrelated top-level `enum MenuItemID`.
    base = tmp_path / "src"
    files = [
        _write(base / "Menu/Ids.swift", "enum MenuItemID {\n    case first\n}\n"),
        _write(base / "Menu/Row.swift", (
            "struct Row {\n"
            "    var id: MenuItem.ID\n"
            "}\n"
        )),
    ]
    if item_source is not None:
        files.append(_write(base / "Menu/MenuItem.swift", item_source))
    result = _extract(files, tmp_path)

    enum_id = _node(result, "MenuItemID", "Ids.swift")
    foreign = [
        e for e in result["edges"]
        if e.get("target") == enum_id and not _sf(e).endswith("Ids.swift")
    ]
    assert not foreign, f"no edge from another file may reach MenuItemID: {foreign}"

    row = _node(result, "Row", "Row.swift")
    targets = _targets(result, row)
    assert enum_id not in targets
    stubs = [
        t for t in targets
        if _by_id(result)[t].get("label") == "MenuItem.ID" and _is_stub(result, t)
    ]
    assert stubs, (
        "the reference must stay on a sourceless `MenuItem.ID` stub, got "
        f"{[_by_id(result)[t].get('label') for t in targets]}"
    )
