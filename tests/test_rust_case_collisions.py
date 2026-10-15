"""Rust file-level items whose names fold to one node id (#3302's rule, Rust shape).

``make_id`` casefolds, so ``fn ignore`` / ``struct Ignore`` (ripgrep's
``crates/ignore/src/dir.rs``) or ``fn e`` / ``fn E`` (``crates/regex/src/literal.rs``)
minted one id and walk() dropped whichever came second.
"""

from pathlib import Path

from graphify.extract import extract

_IGNORE_RS = (
    "pub struct Ignore {\n"
    "    parent: u32,\n"
    "}\n"
    "\n"
    "impl Ignore {\n"
    "    pub fn matched(&self) -> bool {\n"
    "        true\n"
    "    }\n"
    "}\n"
    "\n"
    "pub fn ignore() -> Ignore {\n"
    "    build()\n"
    "}\n"
    "\n"
    "fn build() -> Ignore {\n"
    "    Ignore { parent: 0 }\n"
    "}\n"
)


def _extract(tmp_path: Path, source: str, name: str = "dir.rs") -> dict:
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return extract([path], cache_root=tmp_path, root=tmp_path, parallel=False)


def _sourced(result: dict, label: str) -> list[dict]:
    return [n for n in result["nodes"] if n.get("label") == label and n.get("source_file")]


def _edges(result: dict, relation: str) -> set[tuple[str, str]]:
    by_id = {n["id"]: n["label"] for n in result["nodes"]}
    return {
        (by_id.get(e["source"], ""), by_id.get(e["target"], ""))
        for e in result["edges"]
        if e.get("relation") == relation
    }


def test_function_and_struct_differing_by_case_are_both_extracted(tmp_path: Path) -> None:
    result = _extract(tmp_path, _IGNORE_RS)
    struct = _sourced(result, "Ignore")
    func = _sourced(result, "ignore()")
    assert [n["source_location"] for n in struct] == ["L1"], struct
    assert [n["source_location"] for n in func] == ["L11"], func
    assert struct[0]["id"] != func[0]["id"]


def test_struct_keeps_its_id_and_methods_when_a_function_shares_it(tmp_path: Path) -> None:
    """The declared type keeps the plain id, so it and its methods do not move."""
    solo = _extract(tmp_path, _IGNORE_RS.replace("pub fn ignore() -> Ignore {\n    build()\n}\n", ""))
    solo_ids = {n["id"] for n in solo["nodes"] if n.get("label") in ("Ignore", ".matched()")}
    assert len(solo_ids) == 2

    result = _extract(tmp_path, _IGNORE_RS)
    ids = {n["id"] for n in result["nodes"] if n.get("label") in ("Ignore", ".matched()")}
    assert ids == solo_ids
    assert ("Ignore", ".matched()") in _edges(result, "method")


def test_salted_function_owns_its_own_body(tmp_path: Path) -> None:
    """The call inside ``ignore()`` is credited to ``ignore()``, not to the struct."""
    result = _extract(tmp_path, _IGNORE_RS)
    calls = _edges(result, "calls")
    assert ("ignore()", "build()") in calls, calls
    assert not any(src == "Ignore" for src, _ in calls), calls
    assert ("ignore()", "Ignore") in _edges(result, "references")


def test_type_keeps_the_plain_id_whatever_the_declaration_order(tmp_path: Path) -> None:
    forward = {(n["label"], n["id"]) for n in _extract(tmp_path, _IGNORE_RS)["nodes"]
               if n.get("source_file")}
    reordered = (
        "pub fn ignore() -> Ignore {\n"
        "    build()\n"
        "}\n"
        "\n"
        "fn build() -> Ignore {\n"
        "    Ignore { parent: 0 }\n"
        "}\n"
        "\n"
        "impl Ignore {\n"
        "    pub fn matched(&self) -> bool {\n"
        "        true\n"
        "    }\n"
        "}\n"
        "\n"
        "pub struct Ignore {\n"
        "    parent: u32,\n"
        "}\n"
    )
    backward = {(n["label"], n["id"]) for n in _extract(tmp_path, reordered)["nodes"]
                if n.get("source_file")}
    assert forward == backward


def test_case_only_functions_are_both_salted(tmp_path: Path) -> None:
    """With no declared type in the group, neither member keeps the plain id."""
    lower_src = "fn e(s: &str) -> u32 {\n    1\n}\n"
    plain = _sourced(_extract(tmp_path, lower_src, name="literal.rs"), "e()")[0]["id"]

    result = _extract(
        tmp_path, lower_src + "\nfn E(s: &str) -> u32 {\n    2\n}\n", name="literal.rs"
    )
    lower, upper = _sourced(result, "e()"), _sourced(result, "E()")
    assert len(lower) == 1 and len(upper) == 1
    assert lower[0]["id"] != upper[0]["id"]
    assert plain not in {lower[0]["id"], upper[0]["id"]}


def test_cfg_twins_still_share_one_node(tmp_path: Path) -> None:
    """``#[cfg]`` variants of one function are one symbol and keep the plain id."""
    twins = (
        "#[cfg(unix)]\n"
        "fn device_num(p: &str) -> u64 {\n    1\n}\n"
        "\n"
        "#[cfg(windows)]\n"
        "fn device_num(p: &str) -> u64 {\n    2\n}\n"
    )
    solo = _extract(tmp_path, twins, name="walk.rs")
    twin_nodes = _sourced(solo, "device_num()")
    assert [n["source_location"] for n in twin_nodes] == ["L2"]

    # A case-only sibling splits the group, but the twins stay one node.
    result = _extract(tmp_path, twins + "\nstruct Device_Num;\n", name="walk.rs")
    assert len(_sourced(result, "device_num()")) == 1
    assert len(_sourced(result, "Device_Num")) == 1
    assert _sourced(result, "Device_Num")[0]["id"] == twin_nodes[0]["id"]


def test_forward_reference_to_the_retained_type_lands_on_it(tmp_path: Path) -> None:
    """A reference above ``struct Ignore`` in a file that also has ``fn ignore``
    resolves to the struct even when another file declares an ``Ignore`` too,
    so the corpus-level rewire cannot fold a sourceless stub back onto it."""
    (tmp_path / "dir.rs").write_text(
        "fn before() -> Ignore {\n    ignore()\n}\n\n" + _IGNORE_RS, encoding="utf-8"
    )
    (tmp_path / "other.rs").write_text("pub struct Ignore;\n", encoding="utf-8")
    result = extract(sorted(tmp_path.glob("*.rs")), cache_root=tmp_path, root=tmp_path,
                     parallel=False)
    by_id = {n["id"]: n for n in result["nodes"]}
    before = next(n["id"] for n in result["nodes"] if n.get("label") == "before()")
    targets = [
        by_id[e["target"]] for e in result["edges"]
        if e.get("relation") == "references" and e.get("source") == before
    ]
    assert [(n["label"], Path(n["source_file"]).name if n.get("source_file") else "")
            for n in targets] == [("Ignore", "dir.rs")]

