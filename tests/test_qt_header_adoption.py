"""REQ-QML-018-AC07: lexical header admission and original source authority."""
from __future__ import annotations

import pytest

from graphify.extract import _get_extractor, extract, extract_c, extract_cpp, extract_objc
from graphify.extractors.qt_cpp_facts import qt_metadata


@pytest.mark.parametrize("separator", ["\n", "\t", "\r\n", " /* comment */ "])
@pytest.mark.parametrize("prefix", ["", "\ufeff// λ\r\n"])
def test_req_qml018_ac07_whitespace_header_uses_cpp_source_authority(tmp_path, separator, prefix):
    """C++ class keywords survive whitespace while authoritative bytes stay original."""
    header = tmp_path / "backend.h"
    source = prefix + "class" + separator + "Backend : public QObject { Q_OBJECT };\r\n"
    header.write_bytes(source.encode("utf-8"))
    assert _get_extractor(header) is extract_cpp
    result = extract([header], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not result.get("qml_failures")
    classes = [node for node in result["nodes"] if qt_metadata(node).get("kind") == "class"]
    assert len(classes) == 1
    metadata = qt_metadata(classes[0])
    assert metadata["status"] == "resolved" and metadata["generic_target_id"]
    span = metadata["span"]
    assert header.read_bytes()[span["start_byte"]:span["end_byte"]].startswith(b"class")


@pytest.mark.parametrize("source", [
    '/* class Fake; namespace Ghost { } template public: :: */\nint value(void);',
    '// class Ghost;\nconst char *label = "namespace Fake { :: public:";\n',
    'const char *label = "class Fake";\nstruct Backend { int value; };\n',
    "struct Backend { int value; };\nint inspect(struct Backend *value);\n",
    'const char *label = R"mark(class Fake; namespace Shadow { })mark";\n',
    '// continued comment \\ \n class Fake;\nint value;'.replace("\\ ", "\\"),
    'const char *label = "escaped \\" class Fake";\n',
])
def test_req_qml018_ac07_inert_cpp_markers_keep_c_dispatch(tmp_path, source):
    """Quoted/commented keywords cannot authorize a parser change for C inputs."""
    header = tmp_path / "plain.h"
    header.write_bytes(source.encode())
    assert _get_extractor(header) is extract_c


@pytest.mark.parametrize("source", [
    "struct Backend final { int value; };\n",
    "namespace\nPublic { struct Backend { int value; }; }\n",
    "template\n<typename Value> struct Backend { Value value; };\n",
])
def test_req_qml018_ac07_additional_cpp_declarations(tmp_path, source):
    """Supported C++ declaration tokens select C++ without evaluating build metadata."""
    header = tmp_path / "native.h"
    header.write_bytes(source.encode())
    assert _get_extractor(header) is extract_cpp


def test_req_qml018_ac07_objective_c_retains_dispatch_priority(tmp_path):
    """The established Objective-C boundary wins when both source forms are present."""
    header = tmp_path / "view.h"
    header.write_bytes(b"@interface View\n@end\nclass Backend {};\n")
    assert _get_extractor(header) is extract_objc


def test_req_qml018_ac07_header_prefix_budget_and_digit_separators(tmp_path):
    """Markers outside the existing 256 KiB budget remain inconclusive; digits are lexical tokens."""
    header = tmp_path / "large.h"
    header.write_bytes(b" " * (256 * 1024) + b"class Backend {};\n")
    assert _get_extractor(header) is extract_c
    header.write_bytes(b"const long value = 1'000;\nclass\nBackend {};\n")
    assert _get_extractor(header) is extract_cpp
