"""C++ nested types and C++/CLI keep their symbols (#2876)."""
from pathlib import Path

import pytest

from graphify.extract import _normalize_cpp_cli, extract_cpp

pytest.importorskip("tree_sitter_cpp")


def _labels(path: Path) -> list[str]:
    return [n["label"] for n in extract_cpp(path)["nodes"]]


def test_nested_cpp_class_is_extracted(tmp_path):
    # A nested type is a field_declaration whose `type` field IS the
    # class_specifier; the member-variable branch used to consume it and return
    # before the walk could descend, dropping Inner with no parse error.
    p = tmp_path / "nested.h"
    p.write_text(
        "namespace N {\n"
        "    class Outer\n"
        "    {\n"
        "    public:\n"
        "        class Inner\n"
        "        {\n"
        "        public:\n"
        "            static void Method() { }\n"
        "        };\n"
        "    };\n"
        "}\n"
    )
    result = extract_cpp(p)
    assert result.get("parse_errors") is None
    assert [n["label"] for n in result["nodes"]] == [
        "nested.h", "Outer", "Inner", ".Method()",
    ]
    # Inner is contained by Outer, not by the file (#2040).
    outer = next(n["id"] for n in result["nodes"] if n["label"] == "Outer")
    inner = next(n["id"] for n in result["nodes"] if n["label"] == "Inner")
    assert any(
        e["source"] == outer and e["target"] == inner and e["relation"] == "contains"
        for e in result["edges"]
    )


def test_nested_type_declared_with_an_instance(tmp_path):
    """`class Inner { } inst;` declares both a type and a member."""
    p = tmp_path / "both.h"
    p.write_text(
        "class Outer\n"
        "{\n"
        "public:\n"
        "    class Inner { int x; } inst;\n"
        "};\n"
    )
    labels = _labels(p)
    assert "Inner" in labels
    assert "inst" in labels


def test_cpp_cli_class_body_survives(tmp_path):
    p = tmp_path / "cli.h"
    p.write_text(
        "namespace N {\n"
        "    public ref class Wrapper\n"
        "    {\n"
        "    public:\n"
        "        static void Init() { }\n"
        '        static System::String^ Name() { return gcnew System::String(""); }\n'
        "    };\n"
        "}\n"
    )
    result = extract_cpp(p)
    assert result.get("parse_errors") is None
    labels = [n["label"] for n in result["nodes"]]
    assert "Wrapper" in labels
    assert ".Init()" in labels
    assert ".Name()" in labels
    # recovery no longer invents a `Wrapper()` free function or a `public` node
    assert "Wrapper()" not in labels
    assert "public" not in labels


def test_cli_normalization_preserves_byte_offsets(tmp_path):
    src = (
        '[assembly:AssemblyVersion("1.0")];\n'
        "public ref struct S { void F(System::Object^ o, int% n) { gcnew S(); } };\n"
    ).encode()
    out = _normalize_cpp_cli(src)
    assert out is not None
    assert len(out) == len(src)
    # every line still starts at the same offset
    assert [i for i, b in enumerate(src) if b == 0x0A] == [
        i for i, b in enumerate(out) if b == 0x0A
    ]
    assert b"ref struct" not in out
    assert b"gcnew" not in out
    assert b"assembly" not in out


def test_plain_cpp_is_not_rewritten(tmp_path):
    src = b"int f(int a, int b) { return (a ^ b) % 7; }\n"
    assert _normalize_cpp_cli(src) is None


def test_operators_survive_in_a_cli_file(tmp_path):
    """The `^`/`%` rewrite only touches the suffix spelling, not the operators."""
    src = b"ref class C { int f(int a, int b) { return (a ^ b) % 7; } };\n"
    out = _normalize_cpp_cli(src)
    assert out is not None
    assert b"(a ^ b) % 7" in out
