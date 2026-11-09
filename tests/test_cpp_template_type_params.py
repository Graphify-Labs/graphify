"""C++ template type parameters must not mint sourceless god nodes.

A `template<typename T>` binds `T` as a local name, not a corpus symbol. The
C++ type-ref pass appended the bare `T`/`K`/`V` identifiers used in a template
signature or member as type references and ran them through the sourceless-stub
path, so every template in the corpus collapsed its `T` onto one bare `t` node
— a god node (single-letter type params are not in the analyzer's builtin-noise
filter). C#, Java, TypeScript, Kotlin, Scala, and Go already exclude their type
parameters; C++ now matches.
"""
from pathlib import Path

from graphify.extract import extract


def _sourceless(r):
    return sorted({(n["id"], n.get("label")) for n in r["nodes"] if not n.get("source_file")})


def test_class_and_function_template_params_mint_no_stub(tmp_path):
    (tmp_path / "b.cpp").write_text(
        "template<typename T>\n"
        "class Box {\n"
        "    T value;\n"
        "public:\n"
        "    T get() { return value; }\n"
        "};\n"
        "template<typename K, typename V>\n"
        "V lookup(K key) { V v; return v; }\n"
    )
    r = extract([tmp_path / "b.cpp"], cache_root=tmp_path, parallel=False)
    assert _sourceless(r) == []
    assert not any(e.get("target") in ("t", "k", "v") for e in r["edges"])


def test_non_type_param_and_real_types_unaffected(tmp_path):
    # `N` is a non-type (value) template parameter, not a type; a genuine user
    # type in the signature still references.
    (tmp_path / "b.cpp").write_text(
        "struct User { int id; };\n"
        "template<typename T, int N>\n"
        "class Buffer {\n"
        "    T data[N];\n"
        "public:\n"
        "    User owner() { return User(); }\n"
        "};\n"
    )
    r = extract([tmp_path / "b.cpp"], cache_root=tmp_path, parallel=False)
    assert not any(e.get("target") == "t" for e in r["edges"])
    refs = {
        rn["label"]
        for e in r["edges"] if e.get("relation") == "references"
        for rn in r["nodes"] if rn["id"] == e["target"]
    }
    assert "User" in refs
