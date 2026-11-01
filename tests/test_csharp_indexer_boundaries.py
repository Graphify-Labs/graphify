"""INC-QML-90: signature, ownership and bounded indexer metadata contracts."""
from __future__ import annotations

import base64

from tree_sitter import Language, Parser
import tree_sitter_c_sharp

from graphify.extract import extract_csharp
from graphify.extractors.csharp_indexers import describe_indexer
from tests.test_csharp_indexers import indexers


def descriptions(source):
    raw = source.encode()
    tree = Parser(Language(tree_sitter_c_sharp.language())).parse(raw).root_node
    values, pending = [], [tree]
    while pending:
        node = pending.pop()
        pending.extend(reversed(node.named_children))
        if node.type == "indexer_declaration":
            value = describe_indexer(node, raw)
            if value is not None:
                values.append(value)
    return values


def test_req_qml022_ac02_source_signature_ignores_layout_but_preserves_literal_case_and_interface():
    """Actual type tokens, rather than names/defaults/body text, form the source identity."""
    first, = descriptions("class H{int IMap.this[int key=1]=>0;}")
    same, = descriptions("class H{string IMap /* layout */ .this[ int renamed=2]=>null;}")
    other, = descriptions("class H{int Other.this[int key]=>0;}")
    upper, lower = descriptions("class H{int this[Widget key]=>0; int this[widget key]=>0;}")
    assert first.signature_key == same.signature_key
    assert first.signature_key != other.signature_key
    assert upper.signature_key != lower.signature_key


def test_req_qml022_ac02_return_parameter_types_and_params_share_existing_type_reference_owner(tmp_path):
    """Source AST types feed existing class references, with generic parameters kept out of fake stubs."""
    path = tmp_path / "Members.cs"
    path.write_text("class Key{} class Widget{} class Holder<T>{"
                    "public System.Collections.Generic.List<Widget> this[Key key, params T[] rest]=>null;}", encoding="utf-8")
    result = extract_csharp(path)
    member, = indexers(result)
    md = member["metadata"]["csharp_member"]
    assert md["parameter_count"] == 2 and md["parameters"][1]["modifiers"] == ["params"]
    owner = next(n["id"] for n in result["nodes"] if n["label"] == "Holder")
    names = {n["id"]: n["label"] for n in result["nodes"]}
    refs = {(names[e["target"]], e.get("context")) for e in result["edges"]
            if e["source"] == owner and e["relation"] == "references"}
    assert ("Widget", "generic_arg") in refs and ("Key", "param_type") in refs
    assert "T" not in {label for label, _ in refs}


def test_req_qml022_ac02_conditional_duplicate_and_nested_source_owners_remain_distinct(tmp_path):
    """Same-signature alternatives survive separately and cannot borrow a neighboring containing type."""
    path = tmp_path / "Members.cs"
    path.write_text("class Holder{\n#if FIRST\npublic int this[int key]=>0;\n#else\n"
                    "public int this[int other]=>1;\n#endif\n"
                    "class Nested{public int this[int key]=>2;}}", encoding="utf-8")
    result = extract_csharp(path)
    values = indexers(result)
    assert len(values) == len({n["id"] for n in values}) == 3
    owners = {n["id"]: n["label"] for n in result["nodes"] if n.get("_callable_class")}
    bindings = {n["id"]: next(e["source"] for e in result["edges"]
                if e["target"] == n["id"] and e["relation"] == "defines") for n in values}
    assert sorted(owners[owner] for owner in bindings.values()) == ["Holder", "Holder", "Nested"]
    assert sum(n["metadata"]["csharp_member"]["conditional"] for n in values) == 2


def test_req_qml022_ac02_large_literal_and_parameter_list_remain_explicit_unknowns():
    """Bounded metadata retains the declaration/count/span without truncating an authoritative type."""
    long_type = "名" * 129
    value, = descriptions("class H{public " + long_type + " this[int key]=>null;}")
    assert value.metadata["type_status"] == "unsupported"
    assert value.metadata["declared_type"] == value.metadata["declared_type_b64"] == ""
    parameters = ",".join("int p" + str(i) for i in range(51))
    many, = descriptions("class H{public int this[" + parameters + "]=>0;}")
    assert many.metadata["parameter_count"] == 51 and len(many.metadata["parameters"]) == 50
    assert many.metadata["parameters_status"] == "unsupported"
    assert many.label == "this[<source signature>]"
    assert all(base64.b64decode(p["declared_type_b64"], validate=True) == b"int" for p in many.metadata["parameters"])


def test_req_qml022_ac02_partial_source_does_not_invent_missing_this_or_parameters(tmp_path):
    """A valid adjacent declaration survives; incomplete syntax cannot synthesize an indexer name."""
    path = tmp_path / "Members.cs"
    path.write_text("class Holder{public int this[int key]=>0; public int this[ =>0;}", encoding="utf-8")
    result = extract_csharp(path)
    assert len(indexers(result)) == 1
    assert not descriptions("class Holder{public int this[]=>0;}")
