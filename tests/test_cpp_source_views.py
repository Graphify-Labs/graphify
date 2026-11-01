"""INC-QML-83: original declaration bytes never replace parsed type inference."""
from __future__ import annotations

from typing import cast

import pytest

from graphify.extract import _CPP_CONFIG, _extract_generic, extract_cpp
import graphify.extract as extraction
from graphify.watch import _rebuild_code
from tests.test_qt_final_incremental_parity import clean, manual_update, normalized, published, run
from tests.test_qt_semantic_correction_updates import products
from graphify.extractors.cpp_source_views import source_view_failure


@pytest.mark.parametrize("newline", [b"\n", b"\r\n"])
def test_req_qml022_ac06_explicit_original_view_owns_free_signature_without_reread(tmp_path, newline):
    """An aligned compatibility operator change must not rewrite source signature identity."""
    path = tmp_path / "api.cpp"
    source = (b"\xef\xbb\xbf// caf\xc3\xa9\nint work(int *value){return 1;}\n").replace(b"\n", newline)
    path.write_bytes(source)
    expected = next(node for node in extract_cpp(path)["nodes"] if node["label"] == "work()")
    parsed = source.replace(b"*value", b"&value")
    # The actual engine receives both explicit same-read views; only its parser
    # sees '&', while function/source-proof ownership retains original '*'.
    result = _extract_generic(path, _CPP_CONFIG, source_override=parsed, cpp_original_source=source)
    body = next(node for node in result["nodes"] if node["label"] == "work()")
    assert body["id"] == expected["id"]
    assert body["metadata"]["cpp_function"] == expected["metadata"]["cpp_function"]
    span = body["metadata"]["cpp_function"]["span"]
    assert b"*value" in source[span["start_byte"]:span["end_byte"]]


@pytest.mark.parametrize("original", [b"int work(){return 1;}\nextra", "text", b"int work(){\nreturn 1;}"])
def test_req_qml022_ac06_misaligned_original_view_is_structured_failure(tmp_path, original):
    """Length, type and physical-newline disagreement reject rather than lending a normalized fact."""
    path = tmp_path / "api.cpp"
    parsed = b"int work(){return 1;}\n"
    path.write_bytes(parsed)
    result = _extract_generic(path, _CPP_CONFIG, source_override=parsed, cpp_original_source=original)
    assert result == {"nodes": [], "edges": [], "error": "CPP_SOURCE_VIEW_MISMATCH"}


def test_req_qml022_ac06_nonbyte_parsed_view_is_the_same_integrity_failure(tmp_path):
    """Two same-length buffers still reject when the supplied parser view is not bytes."""
    path = tmp_path / "api.cpp"
    # Deliberately violate the public byte contract; cast preserves the runtime
    # str so production validation, rather than static typing, rejects it.
    bad_view: object = "int work();"
    result = _extract_generic(path, _CPP_CONFIG, source_override=cast(bytes, bad_view), cpp_original_source=b"int work();")
    assert result == {"nodes": [], "edges": [], "error": "CPP_SOURCE_VIEW_MISMATCH"}


@pytest.mark.parametrize("delimiter", ["\x7f", "\x85", "\u2028", "\u2029"])
def test_req_qml022_ac06_integrity_diagnostic_does_not_publish_filename_delimiters(tmp_path, delimiter):
    """A source display name is not authority to inject diagnostic separators."""
    path = tmp_path / ("unsafe" + delimiter + ".cpp")
    result = source_view_failure({"nodes": [], "edges": [], "error": "CPP_SOURCE_VIEW_MISMATCH"}, path)
    assert result["diagnostics"][0]["source_file"] == result["qt_failures"][0]["source_file"] == ""
    assert result["diagnostics"][0]["code"] == "CPP_SOURCE_VIEW_MISMATCH"


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_source_view_integrity_failure_retains_published_cohort_and_recovers(tmp_path, monkeypatch, operation):
    """The actual invalid compatibility seam must fail hard even for an ordinary C++ corpus."""
    path = tmp_path / "api.cpp"
    path.write_text("int work(){return 1;}")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    before = products(tmp_path)
    path.write_text("int renamed(){return 2;}")
    with monkeypatch.context() as scope:
        # Force only the external compatibility-view boundary to return an
        # invalid length; production validation/diagnostics/writers remain real.
        scope.setattr(extraction, "_normalize_cpp_export_macros", lambda source: source + b" ")
        rejected = extract_cpp(path)
        assert rejected["error"] == "CPP_SOURCE_VIEW_MISMATCH"
        assert rejected["qt_failures"][0]["code"] == "CPP_SOURCE_VIEW_MISMATCH"
        assert rejected["diagnostics"][0]["severity"] == "error"
        assert rejected["diagnostics"][0]["owner"] == "cpp_source_views"
        if operation == "manual":
            with pytest.raises(SystemExit) as failure:
                manual_update(tmp_path, monkeypatch)
            assert failure.value.code == 1
        else:
            assert not _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True)
    assert products(tmp_path) == before
    assert normalized(published(tmp_path)) == normalized(initial)
    recovered = run(tmp_path, monkeypatch, operation, [path])
    assert any(data["label"] == "renamed()" for _, data in recovered.nodes(data=True))
    assert normalized(recovered) == normalized(clean(tmp_path, tmp_path / ".recovered"))
