"""INC-QML-101: member source proof follows the generic allocator's actual class identity."""
from __future__ import annotations

import base64
import copy

import pytest

from graphify.extract import extract_cpp
from graphify.extractors.cpp_class_proof import class_fact
from graphify.extractors.cpp_member_identity import augment_cpp_members, member_fact
from graphify.extractors.qt_cpp_syntax import read_cpp


def text(name="Hpp"):
    return ("\ufeff// π allocated member proof\n"
            f"class {name};\nclass {name} : public QObject {{ Q_OBJECT\n"
            "public: Q_INVOKABLE void ping() {}\n"
            "void (*callback)(int);\n};\n")


def method(result, name):
    return next(node for node in result["nodes"] if node.get("_callable") is True
                and str(node["label"]).lstrip(".").removesuffix("()") == name)


@pytest.mark.parametrize("newline", ["\n", "\r\n"], ids=["LF", "CRLF"])
@pytest.mark.parametrize("name", ["Hpp", "Backend"])
def test_req_qml022_ac02_member_fact_uses_allocated_owner_after_forward_and_file_collision(tmp_path, newline, name):
    """The collision case keeps exact owner/method proof; the ordinary allocation remains unchanged."""
    path = tmp_path / "native.hpp"
    source = text(name).replace("\n", newline).encode()
    path.write_bytes(source)
    result = extract_cpp(path)
    assert not result.get("parse_errors")
    owner = next(node for node in result["nodes"] if class_fact(node))
    member = method(result, "ping")
    fact = member_fact(member)
    assert fact and base64.b64decode(fact["owner_b64"]).decode() == name
    assert fact["role"] == "declaration" and not fact["ambiguous"]
    assert source[fact["span"]["start_byte"]:fact["span"]["end_byte"]] == b"void ping() {}"
    assert any(edge["source"] == owner["id"] and edge["target"] == member["id"]
               and edge["relation"] == "method" for edge in result["edges"])
    file = next(node for node in result["nodes"] if node.get("source_location") == "L1"
                and not node.get("_callable") and node.get("file_type") == "code")
    assert owner["id"] != file["id"]
    callback = next(node for node in result["nodes"] if node["label"] == "callback")
    assert not callback.get("_callable") and "cpp_member" not in callback.get("metadata", {})


def test_req_qml022_ac06_standalone_member_augmentation_retains_legacy_optional_index_default(tmp_path):
    """Callers without an allocator still receive the original noncolliding source facts."""
    path = tmp_path / "native.hpp"
    path.write_text(text("Backend"), encoding="utf-8")
    result = extract_cpp(path)
    expected = copy.deepcopy(member_fact(method(result, "ping")))
    assert expected
    for node in result["nodes"]:
        node.get("metadata", {}).pop("cpp_member", None)
    unit = read_cpp(path, tmp_path)
    augment_cpp_members(unit.tree, unit.source, result["nodes"], path)
    assert member_fact(method(result, "ping")) == expected


def test_req_qml022_ac02_qualified_owners_do_not_stamp_callback_data_or_borrow_sibling_method(tmp_path):
    """Equal basenames and nested callback declarators keep distinct allocated source owners."""
    path = tmp_path / "native.hpp"
    path.write_text("namespace First {" + text().removeprefix("\ufeff") + "}\n"
                    "namespace Second {" + text().removeprefix("\ufeff") + "}\n", encoding="utf-8")
    result = extract_cpp(path)
    members = [node for node in result["nodes"] if str(node["label"]).lstrip(".") == "ping()"]
    assert len(members) == 2
    owners = {base64.b64decode(member_fact(node)["owner_b64"]).decode() for node in members}
    assert owners == {"First::Hpp", "Second::Hpp"}
    assert len({node["id"] for node in members}) == 2
    callbacks = [node for node in result["nodes"] if node["label"] == "callback"]
    assert len(callbacks) == 2
    assert all(not node.get("_callable") and "cpp_member" not in node.get("metadata", {}) for node in callbacks)
