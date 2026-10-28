"""C# extension-method declaration facts and primitive receiver typing (#4828).

The member-call resolvers can only bind a call to an extension method if the
declaration carries the join key: which type the `this` parameter extends. These
tests pin that the extractor records it (and keeps recording it in a way the
resolver can consume), and that a primitive receiver type is stamped so
`this string` can ever match.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from graphify.extract import extract, extract_csharp


def _extract(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        result = extract([Path(n) for n in files], cache_root=Path(tempfile.mkdtemp()))
        per_file = {n: extract_csharp(Path(n)) for n in files}
    finally:
        os.chdir(old)
    return result, per_file


def _line_of(text: str, marker: str) -> str:
    hits = [i for i, line in enumerate(text.splitlines(), start=1) if marker in line]
    assert len(hits) == 1, (marker, hits)
    return f"L{hits[0]}"


def _meta_by_line(result, source_file: str, text: str, marker: str) -> dict:
    line = _line_of(text, marker)
    hits = [
        n for n in result["nodes"]
        if n.get("source_file") == source_file and n.get("source_location") == line
    ]
    assert len(hits) == 1, (source_file, line, [n.get("label") for n in hits])
    return hits[0].get("metadata") or {}


def _call(per_file, callee: str, source_file: str, line: str) -> dict:
    hits = [
        rc for rc in per_file[source_file].get("raw_calls", [])
        if rc.get("callee") == callee and rc.get("source_location") == line
    ]
    assert len(hits) == 1, (callee, source_file, line, hits)
    return hits[0]


def test_this_parameter_records_the_extended_type(tmp_path):
    ext = (
        "namespace Ext {\n"
        "  public static class StringExtensions {\n"
        "    public static string Mask(this string s, char m = '*') { return s; } // D1\n"
        "  }\n"
        "}\n"
    )
    result, _per_file = _extract(tmp_path, {"Ext.cs": ext})
    meta = _meta_by_line(result, "Ext.cs", ext, "// D1")
    assert meta["extension"] is True
    assert meta["extended_type"] == "string"
    assert meta["extended_type_arity"] == 0
    assert "extended_is_type_param" not in meta
    # Parameter arity keeps its #4584 meaning; the extension call is one short.
    assert meta["arity"] == 2
    assert meta["min_arity"] == 0


def test_generic_extended_type_keeps_name_and_arity(tmp_path):
    src = (
        "namespace App {\n"
        "  public class Box<T> { }\n"
        "  public static class BoxExt {\n"
        "    public static void Fill(this Box<int> b) { } // D1\n"
        "  }\n"
        "}\n"
    )
    result, _per_file = _extract(tmp_path, {"Box.cs": src})
    meta = _meta_by_line(result, "Box.cs", src, "// D1")
    assert meta["extended_type"] == "Box"
    assert meta["extended_type_arity"] == 1


def test_qualified_this_parameter_keeps_only_the_simple_name(tmp_path):
    src = (
        "namespace App {\n"
        "  public class Widget { }\n"
        "  public static class WExt {\n"
        "    public static void Paint(this App.Widget w) { } // D1\n"
        "  }\n"
        "}\n"
    )
    result, _per_file = _extract(tmp_path, {"W.cs": src})
    meta = _meta_by_line(result, "W.cs", src, "// D1")
    assert meta["extended_type"] == "Widget"


def test_open_generic_extension_is_marked_as_a_type_parameter(tmp_path):
    src = (
        "public class T { }\n"
        "public static class TExt {\n"
        "  public static void Go(this T t) { } // D1\n"
        "}\n"
        "public static class GenExt {\n"
        "  public static void Go<T>(this T t) { } // D2\n"
        "}\n"
    )
    result, _per_file = _extract(tmp_path, {"Gen.cs": src})
    concrete = _meta_by_line(result, "Gen.cs", src, "// D1")
    generic = _meta_by_line(result, "Gen.cs", src, "// D2")
    # Both carry the same name, so only this flag can tell them apart.
    assert concrete["extended_type"] == "T"
    assert "extended_is_type_param" not in concrete
    assert generic["extended_type"] == "T"
    assert generic["extended_is_type_param"] is True


def test_object_extension_is_recorded_as_the_wildcard_type(tmp_path):
    src = (
        "public static class ObjExt {\n"
        "  public static object GetValue(this object o) { return o; } // D1\n"
        "}\n"
    )
    result, _per_file = _extract(tmp_path, {"O.cs": src})
    meta = _meta_by_line(result, "O.cs", src, "// D1")
    assert meta["extended_type"] == "object"
    assert "extended_is_type_param" not in meta


def test_ordinary_method_has_no_extension_facts(tmp_path):
    src = "public class C {\n  public void M(int a) { } // D1\n}\n"
    result, _per_file = _extract(tmp_path, {"C.cs": src})
    meta = _meta_by_line(result, "C.cs", src, "// D1")
    assert "extension" not in meta
    assert "extended_type" not in meta


def test_primitive_receiver_types_are_stamped(tmp_path):
    ext = (
        "namespace Ext {\n"
        "  public static class Exts {\n"
        "    public static string Mask(this string s) { return s; }\n"
        "  }\n"
        "}\n"
    )
    svc = (
        "using Ext;\n"
        "public class Svc {\n"
        "  public string A(string s) { return s.Mask(); } // E1\n"
        "  public string B(long v) { return v.ToString(); } // E2\n"
        "}\n"
    )
    _result, per_file = _extract(tmp_path, {"Ext.cs": ext, "Svc.cs": svc})
    mask = _call(per_file, "Mask", "Svc.cs", _line_of(svc, "// E1"))
    assert mask["receiver"] == "s"
    assert mask["receiver_type"] == "string"
    tostring = _call(per_file, "ToString", "Svc.cs", _line_of(svc, "// E2"))
    assert tostring["receiver_type"] == "long"


def test_primitive_receiver_is_not_parked_as_cross_repo(tmp_path):
    ext = (
        "namespace Ext {\n"
        "  public static class Exts {\n"
        "    public static string Mask(this string s) { return s; }\n"
        "  }\n"
        "}\n"
    )
    svc = (
        "using Ext;\n"
        "public class Svc {\n"
        "  public string A(string s) { return s.Mask(); }\n"
        "}\n"
    )
    result, per_file = _extract(tmp_path, {"Ext.cs": ext, "Svc.cs": svc})
    caller_nid = per_file["Svc.cs"]["raw_calls"][0]["caller_nid"]
    caller = next(n for n in result["nodes"] if n["id"] == caller_nid)
    assert "unresolved_calls" not in (caller.get("metadata") or {}), (
        "a `string` receiver has no cross-repo declaration to wait for"
    )


def test_chained_receiver_is_still_untyped(tmp_path):
    """The remaining gap, pinned so a future chained-receiver fix is deliberate."""
    ext = (
        "namespace Ext {\n"
        "  public static class Exts {\n"
        "    public static string Mask(this string s) { return s; }\n"
        "  }\n"
        "}\n"
    )
    svc = (
        "using Ext;\n"
        "public class Svc {\n"
        "  public string B(long v) { return v.ToString().Mask(); } // E1\n"
        "}\n"
    )
    _result, per_file = _extract(tmp_path, {"Ext.cs": ext, "Svc.cs": svc})
    chained = _call(per_file, "Mask", "Svc.cs", _line_of(svc, "// E1"))
    assert chained.get("receiver") is None
    assert chained.get("receiver_type") is None
    assert chained.get("receiver_chain") is None
    assert chained.get("receiver_call") is None
