"""REQ-QML-018-AC02 valid Qt/C++ recovery keeps original bytes and safety failures."""
from __future__ import annotations

import pytest

from graphify.extract import extract, extract_cpp
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.extractors.qt_cpp_syntax import QtCppError, normalize_qt_cpp, read_cpp, source_span, walk


def write(root, source):
    path = root / "adapter.cpp"
    path.write_bytes(source)
    return path


def facade(root, path):
    result = extract([path], root=root, cache_root=root / ".probe-cache", parallel=False)
    assert not result["failed_sources"] and not result["qt_failures"] and not result["qml_failures"]
    return result


@pytest.mark.parametrize("parameter", [
    b"const Value &value = {}", b"Value value = { /* empty */ }", b"Value value = {\r\n}",
])
def test_req_qml018_ac02_empty_parameter_default_recovers_exact_declared_member(tmp_path, parameter):
    """A valid empty default has no evaluated expression to erase or fabricate."""
    source = b"class Value {}; class Adapter : public QObject { Q_OBJECT public: void accept(" + parameter + b"); };"
    path = write(tmp_path, source)
    unit = read_cpp(path, tmp_path)
    assert not unit.root.has_error and unit.source == source
    assert len(unit.parsed_source) == len(source)
    assert unit.parsed_source.count(b"\r\n") == source.count(b"\r\n")
    result = facade(tmp_path, path)
    members = [qt_metadata(node) for node in result["nodes"] if qt_metadata(node).get("raw_name") == "accept"
               and qt_metadata(node).get("kind") == "member"]
    assert len(members) == 1 and members[0]["generic_target_id"]
    assert members[0]["parameter_names"] == ["value"]
    assert members[0]["parameter_types"] == (["const Value&"] if parameter.startswith(b"const") else ["Value"])
    span = members[0]["span"]
    assert source[span["start_byte"]:span["end_byte"]] == b"void accept(" + parameter + b");"
    assert not extract_cpp(path).get("parse_errors")


@pytest.mark.parametrize("semicolon", [b"", b";"])
def test_req_qml018_ac02_unused_arguments_keep_evaluated_nested_calls(tmp_path, semicolon):
    """Qt's supplied semicolon is parser syntax; argument calls remain real calls."""
    source = (b"int helper(){ return 1; } int second(){ return 2; }\n"
              b"class Adapter : public QObject { Q_OBJECT public:\n"
              b" void accept(int value) {\n Q_UNUSED(helper())" + semicolon + b"\n"
              b" if (value) Q_UNUSED((second(), value))" + semicolon + b"\n }\n};\n")
    path = write(tmp_path, source)
    unit = read_cpp(path, tmp_path)
    assert unit.source == source and len(unit.parsed_source) == len(source)
    calls = [node for node in walk(unit.root) if node.type == "call_expression"]
    assert len(calls) == 2
    assert {unit.field(node, "function") for node in calls} == {"helper", "second"}
    assert {unit.source[node.start_byte:node.end_byte] for node in calls} == {b"helper()", b"second()"}
    result = facade(tmp_path, path)
    by_label = {node["label"]: node["id"] for node in result["nodes"]}
    member = next(qt_metadata(node) for node in result["nodes"] if qt_metadata(node).get("kind") == "member"
                  and qt_metadata(node).get("raw_name") == "accept")
    retained = [edge for edge in result["edges"] if edge["relation"] == "calls"
                and edge["source"] == member["generic_target_id"]
                and edge["target"] in {by_label["helper()"], by_label["second()"]}]
    assert {edge["source_location"] for edge in retained} == {"L4", "L5"}
    assert not any(edge.get("context") == "qt_signal_emit" for edge in result["edges"])
    assert all(node.get("label") != "Q_UNUSED()" for node in result["nodes"])
    direct = extract_cpp(path)
    assert not direct.get("parse_errors")
    assert not any(call["callee"] == "Q_UNUSED" for call in direct.get("raw_calls", []))


def test_req_qml018_ac02_bom_unicode_crlf_preserve_original_member_and_call_offsets(tmp_path):
    """Recovery changes only syntax bytes; BOM, Unicode and CRLF remain in place."""
    source = (b"\xef\xbb\xbf" + "// café ☃\r\n".encode()
              + b"int helper(){ return 1; }\r\nclass Value {};\r\n"
              b"class Adapter : public QObject { Q_OBJECT public:\r\n"
              b" void accept(const Value &value = {}) {\r\n Q_UNUSED(helper())\r\n }\r\n};\r\n")
    path = write(tmp_path, source)
    unit = read_cpp(path, tmp_path)
    assert unit.source == source and unit.parsed_source.startswith(b"\xef\xbb\xbf")
    assert [offset for offset, byte in enumerate(source) if byte in (10, 13)] == [
        offset for offset, byte in enumerate(unit.parsed_source) if byte in (10, 13)
    ]
    call = next(node for node in walk(unit.root) if node.type == "call_expression")
    offset = source.index(b"helper()", source.index(b"Q_UNUSED"))
    assert source_span(source, call.start_byte, call.end_byte) == source_span(source, offset, offset + 8)
    assert (call.start_point.row, call.start_point.column) == (5, 10)
    result = facade(tmp_path, path)
    member = next(qt_metadata(node) for node in result["nodes"] if qt_metadata(node).get("raw_name") == "accept")
    assert member["span"]["start_row"] == 4
    assert source[member["span"]["start_byte"]:member["span"]["end_byte"]].startswith(b"void accept(const Value &value = {})")


@pytest.mark.parametrize("argument", [b'""', b'"Q_UNUSED(fake())"', b'R"tag(x)tag"', b"1"])
def test_req_qml018_ac02_literal_unused_argument_is_a_real_expression(tmp_path, argument):
    """Quoted/raw literals are expression content, while their text stays inert."""
    source = b"void use(){ Q_UNUSED(" + argument + b") }"
    unit = read_cpp(write(tmp_path, source), tmp_path)
    assert unit.source == source and len(unit.parsed_source) == len(source)
    assert argument in unit.parsed_source and not unit.root.has_error
    assert not any(node.type == "call_expression" for node in walk(unit.root))
    result = facade(tmp_path, unit.path)
    assert not any(edge["relation"] == "calls" for edge in result["edges"])


@pytest.mark.parametrize("argument", [b"", b"/* no expression */"])
def test_req_qml018_ac02_empty_or_comment_only_unused_argument_is_not_recovered(tmp_path, argument):
    """A missing argument cannot become an invented cast value or valid statement."""
    source = b"void use(){ Q_UNUSED(" + argument + b") }"
    assert normalize_qt_cpp(source) is None
    with pytest.raises(QtCppError) as failure:
        read_cpp(write(tmp_path, source), tmp_path)
    assert failure.value.code == "QT_CPP_SYNTAX"


@pytest.mark.parametrize("source", [
    b"class A { void f(const T &value = {); };",
    b"class A { void f(const T &value = {} ; };",
    b"class A { void f(const T &value = {1}); };",
    b"void f(int value) { Q_UNUSED(helper(value) }",
    b"void f(int value) { Q_UNUSED(value) int broken = ; }",
])
def test_req_qml018_ac02_damaged_or_unsupported_syntax_still_rejects(tmp_path, source):
    """Recovering two valid forms must not hide unrelated or nonempty-default errors."""
    path = write(tmp_path, source)
    with pytest.raises(QtCppError) as failure:
        read_cpp(path, tmp_path)
    assert failure.value.code == "QT_CPP_SYNTAX"


@pytest.mark.parametrize("source", [
    b'// Q_UNUSED(helper())\n/* const T &x = {} */\nconst char *s="Q_UNUSED(helper())";',
    b'const char *s=R"tag(Q_UNUSED(helper()) const T &x = {})tag";',
    b"#define BODY(value) \\\n Q_UNUSED(helper(value))\nclass A {};",
    b"#define Q_UNUSED(value) value\nvoid f(int value){ Q_UNUSED(value); }",
    b"#undef Q_UNUSED\nvoid f(int value){ Q_UNUSED(value); }",
    b"void Q_UNUSED(int value) {} void f(){ Q_UNUSED(1); }",
    b"void f(){ object.Q_UNUSED(1); other::Q_UNUSED(2); }",
    b"int helper(); int f(){ return Q_UNUSED(helper()); }",
    b"int helper(); void f(){ int value = Q_UNUSED(helper()); }",
    b"void f(){ int value = {}; }",
])
def test_req_qml018_ac02_inert_definitions_and_ordinary_contexts_are_not_masked(source):
    """Lexical exclusion and expression-statement ownership guard false recovery."""
    assert normalize_qt_cpp(source) is None


def test_req_qml018_ac02_ordinary_cpp_default_and_named_function_keep_canonical_ids(tmp_path):
    """The core C++ facade retains ordinary symbols and calls without Qt facts."""
    source = b"class Value {}; void accept(const Value &value = {}) {}\nvoid helper(){}\nvoid use(){helper();}\n"
    path = write(tmp_path, source)
    direct = extract_cpp(path)
    assert not direct.get("parse_errors")
    result = facade(tmp_path, path)
    nodes = {node["label"]: node for node in result["nodes"]}
    assert nodes["accept()"]["id"] == "adapter_accept"
    assert nodes["helper()"]["id"] == "adapter_helper" and nodes["use()"]["id"] == "adapter_use"
    assert not any(qt_metadata(node) for node in result["nodes"])
    assert any(edge["relation"] == "calls" and edge["source"] == "adapter_use"
               and edge["target"] == "adapter_helper" for edge in result["edges"])


@pytest.mark.parametrize("number", [b"16'384", b"0xAB'CD", b"0b10'01", b"1.2'34e1'0"])
def test_req_qml018_ac02_numeric_separator_keeps_later_signal_ownership(tmp_path, number):
    """Numeric apostrophes cannot mask the remaining class as a character literal."""
    source = (b"// caf\xc3\xa9\r\nclass Adapter : public QObject { Q_OBJECT public:\r\n"
              b" static constexpr auto limit = " + number + b";\r\nsignals:\r\n"
              b" void ready();\r\n};\r\n")
    unit = read_cpp(write(tmp_path, source), tmp_path)
    assert unit.source == source and number in unit.code
    assert len(unit.code) == len(unit.parsed_source) == len(source)
    result = facade(tmp_path, unit.path)
    member = next(qt_metadata(node) for node in result["nodes"]
                  if qt_metadata(node).get("raw_name") == "ready")
    assert member["roles"] == ["signal"]
    span = member["span"]
    assert source[span["start_byte"]:span["end_byte"]] == b"void ready();"
    assert not extract_cpp(unit.path).get("parse_errors")


@pytest.mark.parametrize("number", [b"16''384", b"16'", b"0x'AB"])
def test_req_qml018_ac02_malformed_numeric_separators_remain_rejected(tmp_path, number):
    """Lexical number handling leaves the original token for parser validation."""
    source = b"class A : public QObject { Q_OBJECT public: int limit = " + number + b"; signals: void ready(); };"
    with pytest.raises(QtCppError) as failure:
        read_cpp(write(tmp_path, source), tmp_path)
    assert failure.value.code == "QT_CPP_SYNTAX"
