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


def test_multiline_cli_attribute_keeps_line_numbers(tmp_path):
    """A removed token that spans lines must keep its line breaks.

    `[assembly:AssemblyVersion(\n    "1.0"\n)]` is ordinary formatting. Blanking
    its newlines preserved byte length but merged source lines, so every symbol
    below it reported a line number that was too low.
    """
    p = tmp_path / "cli.h"
    p.write_text(
        "[assembly:AssemblyVersion(\n"
        '    "1.0.0.0"\n'
        ")];\n"
        "namespace N {\n"
        "    public ref class Wrapper\n"
        "    {\n"
        "    public:\n"
        "        static void Init() { }\n"
        "    };\n"
        "}\n"
    )
    nodes = {n["label"]: n["source_location"] for n in extract_cpp(p)["nodes"]}
    assert nodes["Wrapper"] == "L5"
    assert nodes[".Init()"] == "L8"


def test_cli_normalization_preserves_line_breaks(tmp_path):
    src = (
        "[assembly:AssemblyVersion(\n"
        '    "1.0.0.0"\n'
        ")];\n"
        "namespace N {\n"
        "    public\n"          # access specifier split from the keyword
        "    ref class W { };\n"
        "}\n"
    ).encode()
    out = _normalize_cpp_cli(src)
    assert out is not None
    assert len(out) == len(src)
    assert [i for i, b in enumerate(src) if b == 0x0A] == [
        i for i, b in enumerate(out) if b == 0x0A
    ]
    assert b"ref class" not in out
    assert b"assembly" not in out


def test_attached_arithmetic_is_not_mistaken_for_a_handle(tmp_path):
    """`a% b` and `hash^ mask` are modulo and XOR, not CLI type suffixes.

    Attachment to the preceding token does not separate the two readings —
    `String^ s` and `a^ b` are lexically identical — so rewriting on
    attachment alone turned arithmetic into `a  b` and broke the statement.
    """
    p = tmp_path / "ops.h"
    p.write_text(
        "namespace N {\n"
        "    public ref class Hasher\n"
        "    {\n"
        "    public:\n"
        '        static System::String^ Name() { return gcnew System::String(""); }\n'
        "        static int Mix(int a, int b) { return a% b; }\n"
        "        static int Fold(int hash, int mask) { return hash^ mask; }\n"
        "        static void Track(System::Object^ o, int% n) { }\n"
        "    };\n"
        "}\n"
    )
    result = extract_cpp(p)
    assert result.get("parse_errors") is None
    labels = [n["label"] for n in result["nodes"]]
    for expected in ("Hasher", ".Name()", ".Mix()", ".Fold()", ".Track()"):
        assert expected in labels

    # The operator characters themselves survive in the parsed source.
    out = _normalize_cpp_cli(p.read_bytes())
    assert b"return a% b;" in out
    assert b"return hash^ mask;" in out


def test_screaming_case_constants_stay_arithmetic(tmp_path):
    """`MASK^ value` is XOR against a constant, not a `MASK^` handle.

    SCREAMING_CASE is the macro/constant convention and never a .NET type
    name, so a capitalized left side must also carry a lowercase letter. A
    lone capital stays a type position for generic parameters (`T^ x`).
    """
    p = tmp_path / "consts.h"
    p.write_text(
        '''namespace N {
    public ref class Hasher
    {
    public:
        static int Fold(int value) { return MASK^ value; }
        static int Trim(int value) { return LIMIT% value; }
        static System::Object^ Box(T^ item) { return gcnew System::Object(); }
    };
}
'''
    )
    out = _normalize_cpp_cli(p.read_bytes())
    assert b"return MASK^ value;" in out
    assert b"return LIMIT% value;" in out
    assert b"System::Object  Box(T  item)" in out

    result = extract_cpp(p)
    assert result.get("parse_errors") is None
    assert ".Fold()" in _labels(p)


@pytest.mark.parametrize("expr", [
    b"int m = a% b;",
    b"int x = hash^ mask;",
    b"int c = count% 2;",
    b"int d = (a ^ b) % 7;",
    b"int e = a^*p;",
    b"int f = a^&b;",
    b"x %= y;",
])
def test_arithmetic_forms_survive(expr):
    src = b"ref class C { void f() { " + expr + b" } };"
    out = _normalize_cpp_cli(src)
    assert out is not None
    assert expr in out, f"{expr!r} was rewritten"


@pytest.mark.parametrize("decl,rewritten", [
    (b"System::String^ s;", b"System::String  s;"),
    (b"List<int>^ items;", b"List<int>  items;"),
    (b"DataTable^ t;", b"DataTable  t;"),
    (b"int% n;", b"int  n;"),
    (b"void F(String^, int);", b"void F(String , int);"),
    (b"array<String^>^ a;", b"array<String >  a;"),
])
def test_cli_type_suffixes_are_still_rewritten(decl, rewritten):
    src = b"ref class C { " + decl + b" };"
    out = _normalize_cpp_cli(src)
    assert out is not None
    assert len(out) == len(src)
    assert rewritten in out
