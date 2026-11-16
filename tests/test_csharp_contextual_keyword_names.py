"""C# names the bundled grammar reads as contextual keywords (#5043).

A local, parameter or field named ``partial``, ``required``, ``async``,
``nint``, ``nuint`` or ``with`` is valid C# -- ``dotnet build`` accepts it --
but tree-sitter-c-sharp 0.23.5 reads the word as its keyword where a statement
starts with it (``partial |= x;``, ``required.Add(1);``) and ``with`` in
``var with = x;``. The statement becomes an ERROR. When it is the last
statement of an ``if`` block that an ``else`` block follows, the recovery
swallows the ``}`` and the rest of the file with it: only the file node is
extracted. 0.23.5 is the newest release, so there is no grammar bump to take.

The fix rewrites the occurrences to ``@name``, the same identifier to the
compiler, letting the ``@`` take the place of an adjacent blank. It must be
byte-length preserving: line and column numbers are reported straight from the
parsed buffer (the #2876 contract).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import tree_sitter_c_sharp as ts_c_sharp
from tree_sitter import Language, Parser

from graphify.extract import _escape_csharp_contextual_names, extract

_PARSER = Parser(Language(ts_c_sharp.language()))

# The reporter's shape: the local's compound assignment ends an `if` block that
# an `else` block follows, so the parse error swallows the whole namespace.
CASCADE = (
    "namespace Repro\n"
    "{\n"
    "    public sealed class Tilt\n"
    "    {\n"
    "        public bool Check(bool direction, bool full, Vector2 v)\n"
    "        {\n"
    "            bool partial = false;\n"
    "            if (direction)\n"
    "            {\n"
    "                partial |= v != Vector2.zero && !full;\n"
    "            }\n"
    "            else\n"
    "            {\n"
    "                full = v == Vector2.zero;\n"
    "            }\n"
    "            return After(partial, full);\n"
    "        }\n"
    "\n"
    "        private static bool After(bool partway, bool full)\n"
    "        {\n"
    "            return partway && !full;\n"
    "        }\n"
    "    }\n"
    "}\n"
)


def _has_error(source: bytes) -> bool:
    return _PARSER.parse(source).root_node.has_error


def _extract(tmp_path, files: dict[str, str]) -> dict:
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        return extract([Path(n) for n in files], cache_root=tmp_path / ".cache")
    finally:
        os.chdir(old)


def _methods(result: dict) -> dict[str, dict]:
    """Method nodes by bare name: `Tilt.Check()` and `.Check()` both give `Check`."""
    out = {}
    for node in result["nodes"]:
        label = str(node.get("label", ""))
        if label.endswith("()"):
            out[label[:-2].rsplit(".", 1)[-1]] = node
    return out


def _calls(result: dict) -> set[tuple[str, str]]:
    names = {}
    for node in result["nodes"]:
        label = str(node.get("label", ""))
        names[node["id"]] = label[:-2].rsplit(".", 1)[-1] if label.endswith("()") else label
    return {
        (names.get(e["source"], ""), names.get(e["target"], ""))
        for e in result["edges"] if e.get("relation") == "calls"
    }


def _changed_lines(before: bytes, after: bytes) -> set[int]:
    return {before.count(b"\n", 0, i) + 1 for i in range(len(before)) if before[i] != after[i]}


def test_the_rest_of_the_file_is_extracted(tmp_path, capsys):
    """The symptom: nothing but the file node, and a warning naming the namespace line."""
    assert _has_error(CASCADE.encode("utf-8")), "precondition: the grammar rejects the file"
    result = _extract(tmp_path, {"Tilt.cs": CASCADE})
    labels = {str(n.get("label", "")) for n in result["nodes"]}
    assert "Tilt" in labels, sorted(labels)
    assert {"Check", "After"} <= set(_methods(result)), sorted(labels)
    assert ("Check", "After") in _calls(result)
    assert "syntax errors" not in capsys.readouterr().err


def test_source_locations_are_not_shifted(tmp_path):
    """Every member still reports the line it has on disk."""
    on_disk = {}
    for i, line in enumerate(CASCADE.splitlines(), 1):
        for name in ("Check", "After"):
            if f" {name}(bool" in line:
                on_disk[name] = i
    methods = _methods(_extract(tmp_path, {"Tilt.cs": CASCADE}))
    # Presence first: without the fix these nodes do not exist at all.
    assert set(on_disk) <= set(methods), sorted(methods)
    for name, line in on_disk.items():
        assert methods[name].get("source_location") == f"L{line}", (name, methods[name])


def test_rewrite_is_byte_length_preserving():
    """Only the escaped words move; length, line breaks and every other byte hold."""
    src = CASCADE.encode("utf-8")
    out = _escape_csharp_contextual_names(src)
    assert out is not None
    assert len(out) == len(src)
    assert out.count(b"\n") == src.count(b"\n")
    assert not _has_error(out)
    assert _changed_lines(src, out) == {7, 10}
    assert out.splitlines()[6].strip() == b"bool @partial= false;"
    assert out.splitlines()[9].strip() == b"@partial|= v != Vector2.zero && !full;"


@pytest.mark.parametrize("word, body", [
    ("partial", "bool partial = false; partial |= x > 0;"),
    ("required", "var required = new System.Collections.Generic.List<int>(); required.Add(x);"),
    ("async", "int async = 1; async += x;"),
    ("async", "int async = 1; x = async * 2;"),
    ("nint", "int nint = 1; nint = x;"),
    ("nuint", "int nuint = 1; nuint |= 2;"),
    ("with", "var with = x; x = with;"),
])
def test_each_word_in_a_form_the_grammar_rejects(word, body):
    src = (
        "public class C\n{\n"
        f"    public void M(int x) {{ {body} }}\n"
        "    public void After() { }\n"
        "}\n"
    ).encode("utf-8")
    if not _has_error(src):
        pytest.skip(f"the bundled grammar now parses {body!r}")
    out = _escape_csharp_contextual_names(src)
    assert out is not None, body
    assert len(out) == len(src)
    assert not _has_error(out), out
    assert b"@" + word.encode() in out


def test_declaration_and_uses_share_one_spelling(tmp_path):
    """A call on the local still binds through its declared type.

    Escaping the use alone would leave `@required.Add()` on a local declared as
    `required`, and the receiver lookup would miss it.
    """
    src = (
        "namespace Shop\n"
        "{\n"
        "    public sealed class Basket\n"
        "    {\n"
        "        public void Add(int item) { }\n"
        "    }\n"
        "\n"
        "    public sealed class Till\n"
        "    {\n"
        "        public void Ring(bool open)\n"
        "        {\n"
        "            Basket required = new Basket();\n"
        "            if (open)\n"
        "            {\n"
        "                required.Add(1);\n"
        "            }\n"
        "            else\n"
        "            {\n"
        "                Close();\n"
        "            }\n"
        "        }\n"
        "\n"
        "        private void Close() { }\n"
        "    }\n"
        "}\n"
    )
    assert _has_error(src.encode("utf-8")), "precondition: the grammar rejects the file"
    calls = _calls(_extract(tmp_path, {"Shop.cs": src}))
    assert ("Ring", "Add") in calls, sorted(calls)
    assert ("Ring", "Close") in calls, sorted(calls)


def test_keyword_uses_are_never_touched():
    """`partial class`, `async` lambdas, `required` members, `with` and `nint` stay keywords."""
    src = (
        "using System;\n"
        "using System.Threading.Tasks;\n"
        "public partial class Shop\n"
        "{\n"
        "    public required int Count { get; init; }\n"
        "    partial void Hook();\n"
        "    public int Size => 1;\n"
        "    public async Task Run(Shop other, nint size)\n"
        "    {\n"
        "        Func<int, Task> f = async (v) => await other.Run(other, size);\n"
        "        var copy = other with { Count = 2 };\n"
        "        nint n = (nint)size + nint.MaxValue;\n"
        "        bool partial = false;\n"
        "        if (n > 0)\n"
        "        {\n"
        "            partial |= n > 1;\n"
        "        }\n"
        "        else\n"
        "        {\n"
        "            n = 0;\n"
        "        }\n"
        "    }\n"
        "}\n"
    ).encode("utf-8")
    assert _has_error(src), "precondition: the grammar rejects the file"
    out = _escape_csharp_contextual_names(src)
    assert out is not None
    assert not _has_error(out)
    assert _changed_lines(src, out) == {13, 16}


def test_word_the_grammar_reads_keeps_its_spelling():
    """Only the words the parse needs are escaped; `required` here parses as written."""
    src = CASCADE.replace(
        "        private static bool After",
        "        private static int Count(int required)\n"
        "        {\n"
        "            return required + 1;\n"
        "        }\n"
        "\n"
        "        private static bool After",
    ).encode("utf-8")
    out = _escape_csharp_contextual_names(src)
    assert out is not None
    assert b"@partial" in out
    assert b"@required" not in out


def test_file_that_already_parses_is_left_alone():
    """No error, no rewrite: a healthy file is never touched."""
    src = (
        "public class C\n{\n"
        "    public int M(int partial, int required)\n"
        "    {\n"
        "        var async = 1;\n"
        "        var y = Use(partial);\n"
        "        return y + required;\n"
        "    }\n"
        "    private static int Use(int v) { return v; }\n"
        "}\n"
    ).encode("utf-8")
    assert not _has_error(src)
    assert _escape_csharp_contextual_names(src) is None


def test_words_in_comments_and_strings_are_not_rewritten():
    src = CASCADE.replace(
        "            bool partial = false;\n",
        "            // partial = true; required.Add(1);\n"
        "            var note = \"partial = 1; required.Add(1);\";\n"
        "            /* async = 2; */\n"
        "            bool partial = false;\n",
    ).encode("utf-8")
    out = _escape_csharp_contextual_names(src)
    assert out is not None
    assert _changed_lines(src, out) == {10, 13}


def test_file_with_another_error_is_left_alone():
    """A rewrite that does not clear the file is dropped, so nothing changes."""
    src = CASCADE.replace("return partway && !full;", "return partway && ;").encode("utf-8")
    assert _escape_csharp_contextual_names(src) is None


def test_prior_ast_cache_is_not_reused(tmp_path, monkeypatch):
    """A cached pre-fix extraction (file node only) must not be served after the bump."""
    import graphify.cache as cache
    import graphify.extract as extract_module

    assert cache._AST_CACHE_SCHEMA > 47
    with monkeypatch.context() as old:
        old.setattr(cache, "_AST_CACHE_SCHEMA", 47)
        old.setattr(extract_module, "_escape_csharp_contextual_names", lambda source: None)
        before = _extract(tmp_path, {"Tilt.cs": CASCADE})
    assert not {"Check", "After"} & set(_methods(before))
    after = _extract(tmp_path, {"Tilt.cs": CASCADE})
    assert {"Check", "After"} <= set(_methods(after))
