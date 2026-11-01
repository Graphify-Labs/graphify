"""INC-QML-106: competing or conditional bodies cannot acquire canonical proof."""
from __future__ import annotations

from copy import deepcopy

import pytest

from graphify.extract import extract_cpp
from graphify.extractors.cpp_member_identity import canonicalize_cpp_members, member_fact
from tests.cpp_same_unit_helpers import class_node, members, source


def extracted(root, raw):
    path = root / "panel.cpp"
    path.write_bytes(raw.encode())
    result = extract_cpp(path)
    assert not result.get("error")
    return result


@pytest.mark.parametrize("declaration,definition", [
    ("const &", "const &"), ("const", "const"), ("&", "&"), ("&&", "&&"),
])
def test_req_qml022_ac02_same_unit_exact_cv_reference_signature_joins(tmp_path, declaration, definition):
    """Original suffix qualifiers govern a unique pair, without parameter guessing."""
    raw = source().replace("void run();", f"void run() {declaration};").replace(
        "Panel::run() {", f"Panel::run() {definition} {{")
    result = extracted(tmp_path, raw)
    canonicalize_cpp_members(result["nodes"], result["edges"], result.get("raw_calls", []))
    (node, fact), = members(result)
    assert fact["role"] == "declaration" and node["definition_file"] == str(tmp_path / "panel.cpp")


@pytest.mark.parametrize("case", ["overload", "duplicate_prototype", "duplicate_body", "parameter_mismatch",
                                   "cv_mismatch", "ref_mismatch", "foreign_owner", "conditional_body", "conditional_prototype"])
def test_req_qml022_ac06_same_unit_unproved_or_competing_pair_stays_separate(tmp_path, case):
    """A real source declaration remains distinct when its implementation is unproved."""
    raw = source()
    if case == "overload":
        raw = raw.replace("void run();", "void run(int); void run(double);").replace(
            "void Panel::run() { helper(); }", "void Panel::run(int){}\nvoid Panel::run(double){}")
    elif case == "duplicate_prototype":
        raw = raw.replace("void run();", "void run(); void run();")
    elif case == "duplicate_body":
        raw += "void Panel::run() {}\n"
    elif case == "parameter_mismatch":
        raw = raw.replace("void run();", "void run(int);").replace("Panel::run()", "Panel::run(double)")
    elif case == "cv_mismatch":
        raw = raw.replace("void run();", "void run() const;")
    elif case == "ref_mismatch":
        raw = raw.replace("void run();", "void run() &;").replace("Panel::run()", "Panel::run() &&")
    elif case == "foreign_owner":
        raw = raw.replace("Panel::run()", "Other::run()")
    elif case == "conditional_body":
        raw = raw.replace("void Panel::run() { helper(); }", "#if FEATURE\nvoid Panel::run() { helper(); }\n#endif")
    else:
        raw = raw.replace("Q_INVOKABLE void run();", "#if FEATURE\nQ_INVOKABLE void run();\n#endif")
    result = extracted(tmp_path, raw)
    canonicalize_cpp_members(result["nodes"], result["edges"], result.get("raw_calls", []))
    assert not any(node.get("definition_file") for node, _ in members(result))
    assert not any(fact.get("bound_owner_b64") for _, fact in members(result))


def test_req_qml022_ac02_same_unit_include_guard_and_inline_special_members_remain_source_owned(tmp_path):
    """A literal whole-file guard is transparent; constructors/destructors keep their roles."""
    raw = "#ifndef OWNED_HEADER\n#define OWNED_HEADER\n" + source(declarations="Panel() {}\n~Panel() {}") + "#endif\n"
    result = extracted(tmp_path, raw)
    constructor = [node for node in result["nodes"] if node.get("metadata", {}).get("cpp_constructor")]
    assert constructor and all(node["_callable"] for node in constructor)
    destructor, = [node for node in result["nodes"] if node["label"] == ".~Panel()"]
    assert destructor["_callable"] and not member_fact(destructor)
    canonicalize_cpp_members(result["nodes"], result["edges"], result.get("raw_calls", []))
    (node, fact), = members(result)
    assert node["definition_file"] == str(tmp_path / "panel.cpp") and not fact["ambiguous"]


def test_req_qml022_ac02_same_unit_callback_return_method_does_not_borrow_return_parameters(tmp_path):
    """Nearest declared function owns its signature; the callback field stays data."""
    raw = source().replace("void run();", "void (*run())(int);").replace(
        "void Panel::run() { helper(); }", "void (*Panel::run())(int) { return nullptr; }").replace(
        "public:\n", "public:\nvoid (*callback)(int);\n")
    result = extracted(tmp_path, raw)
    callback, = [node for node in result["nodes"] if node["label"] == "callback"]
    assert not callback.get("_callable") and not member_fact(callback)
    assert len(members(result)) == 2
    canonicalize_cpp_members(result["nodes"], result["edges"], result.get("raw_calls", []))
    (node, _), = members(result)
    assert node["definition_file"] == str(tmp_path / "panel.cpp")


@pytest.mark.parametrize("shape", ["free", "method", "data"])
def test_req_qml022_ac06_parenthesized_name_and_callback_data_roles_remain_distinct(tmp_path, shape):
    """Callback recovery preserves preexisting parenthesized names and noncallable data."""
    raw = {"free": "void (ordinary)() {}", "method": "class Panel{public:void (ordinary)() {}};",
           "data": "class Panel{public:void (*ordinary)(int);};"}[shape]
    result = extracted(tmp_path, raw)
    (node,) = [node for node in result["nodes"] if "ordinary" in node["label"]]
    assert bool(node.get("_callable")) is (shape != "data")
    if shape == "data":
        assert node["metadata"]["cpp_declarator"]["kind"] == "field" and not member_fact(node)
    else:
        assert node["label"] == ("ordinary()" if shape == "free" else ".ordinary()")


def test_req_qml022_ac06_same_unit_fold_remaps_only_identity_slots_and_is_idempotent(tmp_path):
    """Actual producer IDs propagate through all explicit caller slots, never literal payloads."""
    result = extracted(tmp_path, source())
    declaration, = [node for node, fact in members(result) if fact["role"] == "declaration"]
    definition, = [node for node, fact in members(result) if fact["role"] == "definition"]
    old, actual = definition["id"], declaration["id"]
    calls = result["raw_calls"]
    assert any(call.get("caller_nid") == old for call in calls)
    observed = {"source": old, "caller_nid": old, "literal": old}
    calls.append(observed)
    canonicalize_cpp_members(result["nodes"], result["edges"], calls)
    assert observed == {"source": actual, "caller_nid": actual, "literal": old}
    assert not any(edge.get(key) == old for edge in result["edges"] for key in ("source", "target"))
    assert not any(call.get("caller_nid") == old for call in calls)
    assert class_node(result)["id"] != actual
    snapshot = deepcopy(result)
    canonicalize_cpp_members(result["nodes"], result["edges"], calls)
    assert result == snapshot
