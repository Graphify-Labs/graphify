"""INC-QML-103: fixture growth cannot silently transform byte-owning sources."""
import pytest

from graphify.extract import _get_extractor, extract_cpp, extract_csharp
from tests.test_graph_invariance import _copy


@pytest.mark.parametrize("suffix", [".cs", ".cu", ".cuh", ".metal"])
def test_req_qml022_ac02_source_byte_admission_is_independent_of_checkout(tmp_path, suffix):
    """Literal LF native bytes stay exact while ordinary text still becomes CRLF."""
    source = tmp_path / "source"
    source.mkdir()
    raw = b"// original LF source\nclass Owner { int field; };\n"
    (source / ("owner" + suffix)).write_bytes(raw)
    (source / "ordinary.py").write_bytes(b"def value():\n    return 1\n")
    copied = _copy(source, tmp_path / "copy", crlf=True)
    assert sorted(path.name for path in copied.iterdir()) == ["ordinary.py", "owner" + suffix]
    assert (copied / ("owner" + suffix)).read_bytes() == raw
    assert (copied / "ordinary.py").read_bytes() == b"def value():\r\n    return 1\r\n"
    assert _get_extractor(copied / ("owner" + suffix)) is (extract_csharp if suffix == ".cs" else extract_cpp)
