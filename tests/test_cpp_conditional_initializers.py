"""Bounded static branch views recover C++ expression directives without cpp."""
from copy import deepcopy
import json
import subprocess
from pathlib import Path

import pytest

from graphify import extract

pytest.importorskip("tree_sitter_cpp")


def _extract(tmp_path, source):
    path = tmp_path / "conditional.cpp"
    path.write_bytes(source.encode("utf-8") if isinstance(source, str) else source)
    return path, extract.extract_cpp(path)


def _coverage(result):
    return result["nodes"][0]["metadata"]["cpp_conditional_recovery"]


def test_initializer_recovery_preserves_bytes_and_locations(tmp_path, monkeypatch):
    source = ("// \u00e9 byte offsets\r\nnamespace Demo {\r\nint values[] = {\r\n1,\r\n"
              "#ifndef NDEBUG\r\n2,\r\n#endif\r\n3\r\n};\r\nvoid After() {}\r\n}\r\n").encode()
    generic = extract._extract_generic
    parsed = []

    def capture(path, config, **kwargs):
        parsed.append(kwargs["source_override"])
        return generic(path, config, **kwargs)

    monkeypatch.setattr(extract, "_extract_generic", capture)
    _, result = _extract(tmp_path, source)
    assert not result.get("parse_errors")
    assert next(n for n in result["nodes"] if n["label"] == "After()")["source_location"] == "L10"
    recovery = _coverage(result)
    assert recovery["status"] == "recovered"
    assert recovery["variant_count"] == 2
    assert recovery["recovered_from"]["first_error_line"]
    assert recovery["conditions_evaluated"] is False
    assert recovery["combinations_enumerated"] is False
    group = recovery["groups"][0]
    assert group["line"] == 5
    branch = group["branches"][0]
    assert source[branch["start_byte"]:branch["end_byte"]] == b"\r\n2,\r\n"
    assert branch["start_line"] == branch["end_line"] == 6
    assert len(parsed) == 3  # Original plus the present and absent branch views.
    for view in parsed:
        assert len(view) == len(source)
        assert [i for i, c in enumerate(view) if c in b"\r\n"] == [
            i for i, c in enumerate(source) if c in b"\r\n"]
        assert all(before == after or after == ord(" ") for before, after in zip(source, view))


def test_alternatives_are_parsed_separately_and_keep_call_provenance(tmp_path):
    _, result = _extract(tmp_path, """int First(); int Second(); void Run() {
int values[] = {
#if FEATURE
First()
#else
Second()
#endif
};
}
void After() {}
""")
    assert not result.get("parse_errors")
    calls = {c["callee"]: c for c in result["raw_calls"]}
    assert {"First", "Second"} <= calls.keys()
    assert calls["First"]["source_location"] == "L4"
    assert calls["Second"]["source_location"] == "L6"
    assert calls["First"]["metadata"]["cpp_conditions"] == [{"group_line": 3, "branch": 0}]
    assert calls["Second"]["metadata"]["cpp_conditions"] == [{"group_line": 3, "branch": 1}]
    assert _coverage(result)["variant_count"] == 2
    # Flattening these alternatives would produce invalid `First() Second()`.


def test_valid_cpp_keeps_existing_call_pair_deduplication(tmp_path):
    _, result = _extract(tmp_path, "void First() {}\nvoid Run() {\nFirst();\nFirst();\n}\n")
    calls = [e for e in result["edges"] if e["relation"] == "calls"]
    assert len(calls) == 1
    assert calls[0]["source_location"] == "L3"


@pytest.mark.parametrize("group_count", [3, 8])
def test_repeated_conditional_calls_preserve_each_site_without_adding_symbols(tmp_path, group_count):
    lines = ["int First() { return 1; }", "int Second() { return 2; }", "void Run() {"]
    expected_calls = set()
    for index in range(group_count):
        group_line = len(lines) + 2
        lines.extend([
            f"int values_{index}[] = {{", f"#if FEATURE_{index}", "First()",
            "#else", "Second()", "#endif", "};",
        ])
        expected_calls.update({
            ("First()", f"L{group_line + 1}", group_line, 0),
            ("Second()", f"L{group_line + 3}", group_line, 1),
        })
    lines.extend(["}", "void After() {}"])
    path = tmp_path / "conditional.cpp"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    results = [extract.extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
               for _ in range(2)]
    assert results[0] == results[1]
    for result in results:
        assert sorted(n["label"] for n in result["nodes"]) == [
            "After()", "First()", "Run()", "Second()", "conditional.cpp",
        ]
        nodes = {n["id"]: n for n in result["nodes"]}
        assert len(nodes) == 5
        recovery = next(n for n in nodes.values() if n["label"] == "conditional.cpp")["metadata"]["cpp_conditional_recovery"]
        assert recovery["status"] == "recovered"
        assert recovery["variant_count"] == group_count + 1
        calls = [e for e in result["edges"] if e["relation"] == "calls"]
        assert len(calls) == 2 * group_count
        assert {nodes[e["source"]]["label"] for e in calls} == {"Run()"}
        assert {(nodes[e["target"]]["label"], e["source_location"],
                 e["metadata"]["cpp_conditions"][0]["group_line"],
                 e["metadata"]["cpp_conditions"][0]["branch"]) for e in calls} == expected_calls
        assert all(len(e["metadata"]["cpp_conditions"]) == 1 for e in calls)


def test_nested_conditionals_cover_each_branch_with_ancestor_provenance(tmp_path):
    _, result = _extract(tmp_path, """int One(); int Two(); int Three(); void Run() {
int values[] = {
#if OUTER
#if INNER
One(),
#else
Two(),
#endif
#else
Three(),
#endif
0};
}
""")
    assert not result.get("parse_errors")
    calls = {c["callee"]: c for c in result["raw_calls"]}
    assert {"One", "Two", "Three"} <= calls.keys()
    assert calls["Two"]["metadata"]["cpp_conditions"] == [
        {"group_line": 3, "branch": 0}, {"group_line": 4, "branch": 1}]
    assert calls["Three"]["metadata"]["cpp_conditions"] == [{"group_line": 3, "branch": 1}]
    assert _coverage(result)["variant_count"] == 3


def test_argument_conditionals_recover_calls_without_flattening(tmp_path):
    _, result = _extract(tmp_path, """int First(); int Second(); void Consume(int);
void Run() { Consume(
#if FEATURE
First()
#else
Second()
#endif
); }
""")
    assert not result.get("parse_errors")
    assert {"Consume", "First", "Second"} <= {c["callee"] for c in result["raw_calls"]}
    assert _coverage(result)["status"] == "recovered"


def test_comments_strings_and_raw_strings_do_not_create_directives(tmp_path):
    source = '''const char* raw = u8R"tag(
#if RAW_STRING
#else
)tag";
/*
#ifndef COMMENT
#endif
*/
const char* escaped = "continued\\
#if STRING";
const char character = '#'; // #ifdef LINE_COMMENT
int values[] = {
#ifndef REAL
1,
#endif
0};
'''
    _, result = _extract(tmp_path, source)
    assert not result.get("parse_errors")
    groups = _coverage(result)["groups"]
    assert len(groups) == 1
    assert groups[0]["branches"][0]["directive"] == "#ifndef REAL"


@pytest.mark.parametrize("directives", [
    "#if FLAG\n1,\n",  # Missing endif.
    "#if FLAG\n1,\n#else\n2,\n#else\n3,\n#endif\n",
    "#if FLAG\n1,\n#else\n2,\n#elif OTHER\n3,\n#endif\n",
    "#ifdef FLAG EXTRA\n1,\n#endif\n",
    "#if FLAG\n1,\n#endif EXTRA\n",
    "#if )\n1,\n#endif\n",
    "#if FLAG &&\n1,\n#endif\n",
    "#if defined(\n1,\n#endif\n",
])
def test_malformed_conditionals_retain_original_parse_errors(tmp_path, directives):
    _, result = _extract(tmp_path, "int values[] = {\n" + directives + "0};\n")
    assert result.get("parse_errors")
    assert _coverage(result)["status"] == "unrecovered"
    assert _coverage(result)["recovered_from"] == result["parse_errors"]


def test_unrelated_syntax_errors_are_not_hidden(tmp_path):
    _, result = _extract(tmp_path, """int values[] = {
#if FLAG
1,
#endif
0};
void Broken( {
""")
    assert result.get("parse_errors")
    assert _coverage(result)["status"] == "unrecovered"
    assert _coverage(result)["reason"] == "a branch view still has parse errors"


def test_branch_view_limit_fails_before_trying_variants(tmp_path, monkeypatch):
    monkeypatch.setattr(extract, "_CPP_CONDITIONAL_VARIANT_LIMIT", 2)
    original_generic = extract._extract_generic
    calls = []

    def capture(*args, **kwargs):
        calls.append(1)
        return original_generic(*args, **kwargs)

    monkeypatch.setattr(extract, "_extract_generic", capture)
    _, result = _extract(tmp_path, """int values[] = {
#if FIRST
1,
#endif
#if SECOND
2,
#endif
0};
""")
    assert result.get("parse_errors")
    assert _coverage(result)["reason"] == "branch-view limit exceeded"
    assert len(calls) == 1


@pytest.mark.parametrize("source,reason,parse_count", [
    ("""int values[] {
#if FLAG
[]{ struct Local {}; return 1; }(),
#else
[]{ struct Local {}; return 2; }(),
#endif
0};
""", "branch views have conflicting symbol identities", 3),
    ("int values[] {\n" + "#if FLAG\n1,\n#endif\n" * 129 + "0};\n",
     "conditional-group limit exceeded", 1),
])
def test_rejected_recovery_preserves_the_entire_original_result(
    tmp_path, monkeypatch, source, reason, parse_count,
):
    generic = extract._extract_generic
    parsed = []

    def capture(*args, **kwargs):
        result = generic(*args, **kwargs)
        parsed.append(deepcopy(result))
        return result

    monkeypatch.setattr(extract, "_extract_generic", capture)
    _, result = _extract(tmp_path, source)
    coverage = _coverage(result)
    assert coverage["status"] == "unrecovered"
    assert coverage["reason"] == reason
    assert result["parse_errors"] == parsed[0]["parse_errors"]
    assert len(parsed) == parse_count
    expected = parsed[0]
    expected["nodes"][0].setdefault("metadata", {})["cpp_conditional_recovery"] = coverage
    assert result == expected


def test_include_paths_are_never_opened_and_no_preprocessor_runs(tmp_path, monkeypatch):
    secret = tmp_path / "secret.hpp"
    secret.write_text("HOST_SECRET_SENTINEL")
    path = tmp_path / "conditional.cpp"
    source = (f'#include "{secret.as_posix()}"\n#include "../secret.hpp"\n'
              'int values[] = {\n#if FLAG\n1,\n#endif\n0};\n')
    path.write_text(source)
    read_bytes = Path.read_bytes
    opened = []

    def guarded_read(p):
        opened.append(p)
        assert p == path
        return read_bytes(p)

    def no_process(*args, **kwargs):
        pytest.fail("C++ conditional recovery must not invoke a process")

    monkeypatch.setattr(Path, "read_bytes", guarded_read)
    monkeypatch.setattr(subprocess, "run", no_process)
    result = extract.extract_cpp(path)
    assert not result.get("parse_errors")
    assert opened and set(opened) == {path}
    assert "HOST_SECRET_SENTINEL" not in json.dumps(result)


def test_valid_nonexpression_conditionals_keep_existing_extraction(tmp_path):
    _, result = _extract(tmp_path, """#ifdef FLAG
void First() {}
#else
void Second() {}
#endif
""")
    assert not result.get("parse_errors")
    assert {"First()", "Second()"} <= {n["label"] for n in result["nodes"]}
    assert not result["nodes"][0].get("metadata", {}).get("cpp_conditional_recovery")


def test_digit_separators_do_not_open_character_literals(tmp_path):
    _, result = _extract(tmp_path, """int values[] = {1'000, 0xAB'CD, 0x1.A'Bp0,
#if FLAG
2,
#endif
3};
char later = 'x';
void After() {}
""")
    assert not result.get("parse_errors")
    assert _coverage(result)["groups"][0]["branches"][0]["directive"] == "#if FLAG"
    assert next(n for n in result["nodes"] if n["label"] == "After()")["source_location"] == "L7"


def test_spliced_line_comments_hide_directive_looking_lines(tmp_path):
    source = ("int values[] = {\n// continued comment \\\n#if PHANTOM\n1,\n"
              "// another continued comment \\\n#endif\n#ifndef REAL\n2,\n#endif\n0};\n")
    groups, problem = extract._cpp_conditional_groups(source.encode())
    assert problem is None
    assert len(groups) == 1
    assert groups[0]["branches"][0]["directive"] == "#ifndef REAL"
    _, result = _extract(tmp_path, source)
    assert not result.get("parse_errors")
    assert len(_coverage(result)["groups"]) == 1


def test_spliced_non_directive_line_is_not_recovered(tmp_path):
    source = "int values[] = { \\\n#if PHANTOM\n1};\n"
    groups, problem = extract._cpp_conditional_groups(source.encode())
    assert groups == [] and problem is None
    _, result = _extract(tmp_path, source)
    assert result.get("parse_errors")
    assert not result["nodes"][0].get("metadata", {}).get("cpp_conditional_recovery")


def test_multiline_directive_preserves_original_body_offsets(tmp_path):
    source = b"int values[] = {\r\n#if defined(ONE) && \\\r\n defined(TWO)\r\n2,\r\n#endif\r\n0};\r\n"
    _, result = _extract(tmp_path, source)
    assert not result.get("parse_errors")
    branch = _coverage(result)["groups"][0]["branches"][0]
    assert branch["directive"] == "#if defined(ONE) && \\\r\n defined(TWO)"
    assert source[branch["start_byte"]:branch["end_byte"]] == b"\r\n2,\r\n"
    assert branch["start_line"] == branch["end_line"] == 4


@pytest.mark.parametrize("outer", [False, True])
def test_split_member_names_without_precise_guard_provenance_fail_closed(tmp_path, outer):
    source = """struct Worker { int First(){return 1;} int Second(){return 2;} };
void Consume(int);
void Run(Worker& w) { Consume(w.
#if FLAG
First
#else
Second
#endif
()); }
"""
    if outer:
        source = "#ifdef OUTER\n" + source + "#endif\n"
    _, result = _extract(tmp_path, source)
    assert result.get("parse_errors")
    assert _coverage(result)["status"] == "unrecovered"
    assert _coverage(result)["reason"] == "branch-spanning records lack source guard provenance"


@pytest.mark.parametrize("warm", [False, True])
@pytest.mark.parametrize("expression", ["w.Tick<int>()", "Fetch()"])
def test_later_resolver_edges_keep_the_callsite_conditions(tmp_path, warm, expression):
    header = tmp_path / "worker.hpp"
    header.write_text("int Fetch() { return 1; }\n"
                      "struct Worker { template<class T> int Tick() { return 1; } };", encoding="utf-8")
    caller = tmp_path / "use.cpp"
    caller.write_text('''#include "worker.hpp"
void Run(Worker& w) { int values[] = {
#if FEATURE
''' + expression + ''',
#else
0,
#endif
}; }
''', encoding="utf-8")
    result = extract.extract([header, caller], root=tmp_path, cache_root=tmp_path, parallel=False)
    cold_calls = [e for e in result["edges"] if e["relation"] == "calls"]
    if warm:
        result = extract.extract([caller, header], root=tmp_path, cache_root=tmp_path, parallel=False)
    calls = [e for e in result["edges"] if e["relation"] == "calls"]
    assert calls == cold_calls
    assert len(calls) == 1
    assert calls[0]["metadata"]["cpp_conditions"] == [{"group_line": 3, "branch": 0}]
    assert calls[0]["source_file"] == "use.cpp"
    assert calls[0]["source_location"] == "L4"
    if not warm:
        fresh = extract.extract(
            [caller], root=tmp_path, cache_root=tmp_path, parallel=False,
            resolution_context_nodes=[n for n in result["nodes"] if n.get("source_file") != "use.cpp"],
            resolution_context_edges=[e for e in result["edges"] if e.get("source_file") != "use.cpp"],
        )
        assert [e for e in fresh["edges"] if e["relation"] == "calls"] == calls


@pytest.mark.parametrize("coverage", [
    {"status": "unrecovered", "groups": [{"line": 1, "branches": [{"start_line": 2, "end_line": 4}]}]},
    {"status": "recovered", "groups": None},
    {"status": "recovered", "groups": [{"line": 1, "branches": [None, {"start_line": "2", "end_line": 4}]}]},
])
def test_unrecovered_or_malformed_cached_ranges_cannot_add_conditions(coverage):
    nodes = [{"source_file": "use.cpp", "metadata": {"cpp_conditional_recovery": coverage}}]
    edge = {"source_file": "use.cpp", "source_location": "L3"}
    extract._stamp_cpp_condition_provenance(nodes, [edge])
    assert "metadata" not in edge
