"""INC-QML-98: overridden emission prefixes reject without erasing source identity."""
from __future__ import annotations

import pytest

from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.extractors.qt_cpp_syntax import QtCppError, read_cpp
from graphify.watch import _rebuild_code
from tests.qt_analysis_helpers import analysis, sites
from tests.test_qt_explicit_emissions import assert_rejected_override
from tests.test_qt_final_incremental_parity import clean, normalized, run, unrelated
from tests.test_qt_semantic_correction_updates import products


@pytest.mark.parametrize("marker", ["emit", "Q_EMIT"])
@pytest.mark.parametrize("directive", ["define", "undef"])
def test_req_qml022_ac03_override_prefix_has_exact_bom_crlf_rejection_span(tmp_path, marker, directive):
    """Even a typed prefix cannot become a signal call; disk bytes own the diagnostic."""
    value = " ordinary" if directive == "define" else ""
    source = (f"\ufeff// café 雪\n#{directive} {marker}{value}\n"
              "struct ordinary { ordinary(int); };\n"
              "class Backend:public QObject{Q_OBJECT signals:void ready(int);"
              f"public:void run(){{{marker} ready(1);}}}};\n").replace("\n", "\r\n")
    assert_rejected_override(tmp_path, source)


@pytest.mark.parametrize("marker", ["emit", "Q_EMIT"])
def test_req_qml022_ac03_real_ordinary_function_and_call_preserve_original_bytes(tmp_path, marker):
    """A complete ordinary identifier after undef is neither rejected nor stripped as an annotation."""
    source = (f"\ufeff// café 雪\n#undef {marker}\n"
              "class Backend:public QObject{Q_OBJECT signals:void ready();public:"
              f"void {marker}(int value){{}}void run(){{{marker}(1);ready();}}}};\n").replace("\n", "\r\n")
    result = analysis(tmp_path, {"events.cpp": source})
    path = tmp_path / "events.cpp"
    unit = read_cpp(path, tmp_path)
    raw = source.encode()
    for token in (f"void {marker}(int value)".encode(), f"{marker}(1)".encode()):
        start = raw.index(token)
        assert unit.parsed_source[start:start + len(token)] == token
    assert not any(item["name"] == marker for item in unit.macros)
    selected = sites(result, "emission")
    assert len(selected) == 1 and qt_metadata(selected[0])["explicit_emit"] is False
    span = qt_metadata(selected[0])["span"]
    assert raw[span["start_byte"]:span["end_byte"]] == b"ready()"


@pytest.mark.parametrize("marker", ["emit", "Q_EMIT"])
def test_req_qml022_ac03_bom_immediately_before_undef_keeps_real_ordinary_identifier(tmp_path, marker):
    """The first-line BOM is source encoding, not a reason to rewrite the actual directive token."""
    source = (f"\ufeff#undef {marker}\r\nclass Backend:public QObject{{Q_OBJECT signals:void ready();public:"
              f"void {marker}(int value){{}}void run(){{{marker}(1);ready();}}}};\r\n")
    result = analysis(tmp_path, {"events.cpp": source})
    unit = read_cpp(tmp_path / "events.cpp", tmp_path)
    raw = source.encode()
    assert unit.parsed_source[:raw.index(b"\n") + 1] == raw[:raw.index(b"\n") + 1]
    assert f"{marker}(1)".encode() in unit.parsed_source
    (event,) = sites(result, "emission")
    assert qt_metadata(event)["explicit_emit"] is False and qt_metadata(event)["status"] == "resolved"


@pytest.mark.parametrize("marker", ["emit", "Q_EMIT"])
@pytest.mark.parametrize("directive", ["define", "undef"])
def test_req_qml022_ac03_first_bom_directive_cannot_restore_overridden_prefix_authority(tmp_path, marker, directive):
    """Recognizing first-line directives must still reject their unsupported later emission prefixes."""
    value = " ordinary" if directive == "define" else ""
    source = (f"\ufeff#{directive} {marker}{value}\r\nclass Backend:public QObject{{Q_OBJECT signals:void ready();"
              f"public:void run(){{{marker} ready();}}}};\r\n")
    assert_rejected_override(tmp_path, source)


@pytest.mark.parametrize("marker", ["emit", "Q_EMIT"])
def test_req_qml022_ac03_only_initial_bom_can_admit_directive_whitespace(tmp_path, marker):
    """A signature inserted after source text is not reclassified as preprocessing whitespace."""
    path = tmp_path / "events.cpp"
    path.write_bytes((f"// preceding source\r\n\ufeff#undef {marker}\r\n"
                      "class Backend:public QObject{Q_OBJECT public:"
                      f"void {marker}(int value){{}}void run(){{{marker}(1);}}}};\r\n").encode())
    with pytest.raises(QtCppError) as rejected:
        read_cpp(path, tmp_path)
    assert rejected.value.code == "QT_CPP_SYNTAX"


@pytest.mark.parametrize("marker", ["emit", "Q_EMIT"])
def test_req_qml022_ac03_first_bom_continued_macro_body_stays_original_and_inert(tmp_path, marker):
    """Directive continuation payload bytes remain intact and cannot create an emission occurrence."""
    prefix = f"\ufeff#define UNUSED \\\r\n {marker} ready()\r\n"
    source = prefix + "class Backend:public QObject{Q_OBJECT signals:void ready();public:void run(){ready();}};\r\n"
    result = analysis(tmp_path, {"events.cpp": source})
    unit = read_cpp(tmp_path / "events.cpp", tmp_path)
    assert unit.parsed_source[:len(prefix.encode())] == prefix.encode()
    (event,) = sites(result, "emission")
    assert qt_metadata(event)["explicit_emit"] is False


@pytest.mark.parametrize("marker", ["emit", "Q_EMIT"])
def test_req_qml016_ac01_earlier_sdk_observation_survives_later_valid_ordinary_identifier(tmp_path, marker):
    """Later undef cannot revoke an earlier accepted emission when subsequent source is valid C++."""
    source = ("\ufeff// café 雪\nclass Backend:public QObject{Q_OBJECT public:"
              f"void run(){{{marker} missing(1);}}}};\n#undef {marker}\n"
              f"void {marker}(int value){{}}\nvoid later(){{{marker}(2);}}\n").replace("\n", "\r\n")
    result = analysis(tmp_path, {"events.cpp": source})
    (selected,) = sites(result, "emission")
    md = qt_metadata(selected)
    assert md["explicit_emit"] is True and md["status"] == "unavailable"
    assert not md["target_id"]
    span = md["span"]
    assert source.encode()[span["start_byte"]:span["end_byte"]] == b"missing(1)"


@pytest.mark.parametrize("operation", ["manual", "watch"])
@pytest.mark.parametrize("marker", ["emit", "Q_EMIT"])
def test_req_qml022_ac06_override_update_retains_publication_recovers_and_settles(tmp_path, monkeypatch, operation, marker):
    """Real warm updates reject unsupported prefixes before replacing accepted products, then recover exactly."""
    source = tmp_path / "events.cpp"
    original = ("class Backend:public QObject{Q_OBJECT signals:void ready();"
                f"public:void run(){{{marker} ready();}}}};\n").encode()
    source.write_bytes(original)
    (tmp_path / "keep.py").write_bytes(b"def helper():return 1\n\ndef retained():return helper()\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    assert normalized(initial) == normalized(clean(tmp_path, tmp_path / ".cold"))
    (tmp_path / "graphify-out/report.md").write_bytes(b"Previously accepted emission source\n")

    def saved():
        return {**products(tmp_path), "report.md": (tmp_path / "graphify-out/report.md").read_bytes()}

    before = saved()
    source.write_bytes(f"#define {marker} ordinary\n".encode() + original)
    for _ in range(2):
        if operation == "manual":
            with pytest.raises(SystemExit) as rejected:
                run(tmp_path, monkeypatch, operation, [source])
            assert rejected.value.code == 1
        else:
            assert not _rebuild_code(tmp_path, changed_paths=[source], no_cluster=True)
        assert saved() == before
    source.write_bytes(original)
    recovered = run(tmp_path, monkeypatch, operation, [source])
    assert normalized(recovered) == normalized(initial)
    assert unrelated(recovered) == unrelated(initial)
    assert normalized(recovered) == normalized(clean(tmp_path, tmp_path / ".recovered"))
    accepted = saved()
    run(tmp_path, monkeypatch, operation, [])
    assert saved() == accepted
