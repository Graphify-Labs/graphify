"""Regression coverage for members declared in a Java enum body.

A Java enum wraps its fields, constructors and methods in an
``enum_body_declarations`` node, nested under ``enum_body`` after the constant
list. The generic walker recurses into a class body preserving the enclosing
type as the parent scope, but an unknown wrapper node normally resets that
scope to ``None`` (an unknown wrapper usually IS a scope boundary). That reset
orphaned every enum method, field and constructor onto the file instead of the
enum: the type looked like a bare list of constants and the calls made inside
those bodies were dropped from the call graph.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def _extract(tmp_path: Path, src: str) -> dict:
    path = tmp_path / "Planet.java"
    path.write_text(src, encoding="utf-8")
    return extract([path], cache_root=tmp_path / "graphify-out", root=tmp_path)


def _methods_of(result: dict, type_label: str) -> set[str]:
    by_id = {n["id"]: n for n in result["nodes"]}
    type_ids = {nid for nid, n in by_id.items() if n.get("label") == type_label}
    return {
        by_id[e["target"]]["label"]
        for e in result["edges"]
        if e.get("relation") == "method" and e.get("source") in type_ids
    }


_ENUM_SRC = (
    "public enum Planet {\n"
    "    EARTH(5.976e+24), MARS(6.421e+23);\n"
    "\n"
    "    private final double mass;\n"
    "\n"
    "    Planet(double mass) { this.mass = mass; }\n"
    "\n"
    "    public double surfaceGravity() {\n"
    "        return 6.67300E-11 * mass;\n"
    "    }\n"
    "\n"
    "    public double weight(double other) {\n"
    "        return other * surfaceGravity();\n"
    "    }\n"
    "}\n"
)


def test_enum_method_and_constructor_attach_to_the_enum(tmp_path: Path) -> None:
    result = _extract(tmp_path, _ENUM_SRC)
    methods = _methods_of(result, "Planet")
    # Constructor and both instance methods hang off the enum, not the file.
    assert ".Planet()" in methods
    assert ".surfaceGravity()" in methods
    assert ".weight()" in methods

    # None of them leaked onto the file as a top-level function.
    file_ids = {
        n["id"] for n in result["nodes"] if str(n.get("label", "")).endswith(".java")
    }
    file_contained = {
        e["target"]
        for e in result["edges"]
        if e.get("relation") == "contains" and e.get("source") in file_ids
    }
    by_id = {n["id"]: n for n in result["nodes"]}
    leaked = {
        by_id[t]["label"]
        for t in file_contained
        if by_id[t]["label"] in {"surfaceGravity()", "weight()", "Planet()"}
    }
    assert leaked == set(), f"enum members leaked onto the file: {leaked}"


def test_call_between_enum_methods_is_captured(tmp_path: Path) -> None:
    """``weight`` calls ``surfaceGravity`` — the body is now a walked scope."""
    result = _extract(tmp_path, _ENUM_SRC)
    by_id = {n["id"]: n for n in result["nodes"]}
    weight_ids = {nid for nid, n in by_id.items() if n.get("label") == "weight()" or n.get("label") == ".weight()"}
    sg_ids = {nid for nid, n in by_id.items() if n.get("label") in ("surfaceGravity()", ".surfaceGravity()")}
    assert any(
        e.get("relation") == "calls"
        and e.get("source") in weight_ids
        and e.get("target") in sg_ids
        for e in result["edges"]
    ), "call from one enum method to another was dropped"


def test_enum_constants_still_emit_case_of_edges(tmp_path: Path) -> None:
    """The constant list is untouched by the body-scope fix."""
    result = _extract(tmp_path, _ENUM_SRC)
    by_id = {n["id"]: n for n in result["nodes"]}
    planet_ids = {nid for nid, n in by_id.items() if n.get("label") == "Planet"}
    cases = {
        by_id[e["target"]]["label"]
        for e in result["edges"]
        if e.get("relation") == "case_of" and e.get("source") in planet_ids
    }
    assert cases == {"EARTH", "MARS"}
