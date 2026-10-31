"""INC-QML-74: C++ member initialization selects a grammar without relabeling C."""
from __future__ import annotations

import pytest

from graphify.cpp_header import is_cpp_header
from graphify.extract import _get_extractor, extract, extract_c, extract_cpp
from tests.test_qt_final_incremental_parity import clean, normalized, run, unrelated


@pytest.mark.parametrize("field,name", [
    ("bool ready = false;", "ready"),
    ("int count = 0;", "count"),
    ("const char *text = nullptr;", "text"),
    ("int values[2] = {1, 2};", "values"),
    ("int count{0};", "count"),
    ("void (*callback)(int) = nullptr;", "callback"),
])
def test_req_qml022_ac02_default_member_initializer_selects_cpp_and_keeps_field(tmp_path, field, name):
    """A C++-only field initializer is declaration evidence, not a type-name spelling guess."""
    path = tmp_path / "packet.h"
    path.write_text("struct Packet { " + field + " };\n", encoding="utf-8")
    assert is_cpp_header(path) and _get_extractor(path) is extract_cpp
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not result["failed_sources"]
    owner = next(node for node in result["nodes"] if node["label"] == "Packet")
    member = next(node for node in result["nodes"] if node["label"] == name)
    assert not member.get("_callable")
    assert any(edge["source"] == owner["id"] and edge["target"] == member["id"]
               and edge["relation"] == "defines" for edge in result["edges"])
    assert result == extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)


@pytest.mark.parametrize("body", [
    "struct Packet { int value; }; struct Packet packet = {.value = 1};",
    "int values[2] = {1, 2};",
    "struct Packet { int values[1 == 1]; };",
    "struct Packet { int value; }; int function(void) { int value = 1; return value; }",
    "struct Packet { void (*callback)(int); };",
    "struct Packet { enum { Ready = 1 } state; };",
    'struct Packet { const char *text; }; const char *text = "struct Fake { int value = 1; };";',
    "#define DEFAULT_MEMBER int value = 1;\nstruct Packet { int value; };",
])
def test_req_qml022_ac06_c_initializers_expressions_and_inert_fields_remain_c(tmp_path, body):
    """Aggregate objects, array comparisons, enum values and local assignments remain C inputs."""
    path = tmp_path / "packet.h"
    path.write_text(body, encoding="utf-8")
    assert is_cpp_header(path) is False
    assert _get_extractor(path) is extract_c


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_changed_struct_member_admission_matches_full_scan(tmp_path, monkeypatch, operation):
    """A real header edit removes source facts when its only C++ evidence disappears."""
    path = tmp_path / "packet.h"
    path.write_text("struct Packet { int count = 0; };\n", encoding="utf-8")
    (tmp_path / "keep.py").write_text("def helper(): return 7\n\ndef retained(): return helper()\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    identities = {identity for identity, data in initial.nodes(data=True) if data["label"] in {"Packet", "count"}}
    assert len(identities) == 2
    path.write_text("struct Packet { int count; };\n", encoding="utf-8")
    updated = run(tmp_path, monkeypatch, operation, [path])
    assert identities.isdisjoint(updated)
    assert normalized(updated) == normalized(clean(tmp_path, tmp_path / ".cold"))
    assert unrelated(initial) == unrelated(updated)
