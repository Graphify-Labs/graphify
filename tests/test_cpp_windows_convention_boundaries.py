"""INC-QML-92: calling-convention recovery is a source profile, never macro guessing."""
from __future__ import annotations

import pytest

from graphify.extract import extract_cpp
from graphify.extractors.qt_cpp_syntax import QtCppError, normalize_qt_cpp, read_cpp

SDK = '#include <qt_windows.h>\n'
FUNCTION = 'BOOL CALLBACK callback(int value){return value;}\n'


@pytest.mark.parametrize("source", [
    FUNCTION,
    FUNCTION + SDK,
    '#include "qt_windows.h"\n' + FUNCTION,
    '#define CALLBACK __stdcall\n' + SDK + FUNCTION,
    SDK + '#undef CALLBACK\n' + FUNCTION,
    SDK + '#define WINAPI replacement\n' + FUNCTION,
    SDK + '#define Q_OS_WIN 1\n' + FUNCTION,
    SDK + '#include "unknown.hpp"\n' + FUNCTION,
    SDK + '#include HEADER_FROM_BUILD\n' + FUNCTION,
    SDK + 'void CALLBACK();\n' + FUNCTION,
    SDK + 'struct CALLBACK{};\n' + FUNCTION,
])
def test_req_qml022_ac06_missing_overridden_or_ambiguous_sdk_context_stays_rejected(tmp_path, source):
    """No body/name fallback replaces missing SDK, source writes or ordinary identifiers."""
    path = tmp_path / "callbacks.cpp"
    path.write_bytes(source.encode())
    assert normalize_qt_cpp(source.encode()) is None
    with pytest.raises(QtCppError) as caught:
        read_cpp(path, tmp_path)
    assert caught.value.code == "QT_CPP_SYNTAX"
    assert extract_cpp(path).get("parse_errors")


@pytest.mark.parametrize("guarded", [
    '#ifndef Q_OS_WIN\n' + SDK + FUNCTION + '#endif\n',
    '#ifdef OTHER_PLATFORM\n' + SDK + FUNCTION + '#endif\n',
    '#if defined(Q_OS_WIN)\n' + SDK + FUNCTION + '#endif\n',
    '#ifdef Q_OS_WIN\n#ifdef FEATURE\n' + SDK + FUNCTION + '#endif\n#endif\n',
    '#ifdef Q_OS_WIN\n' + SDK + '#else\n' + FUNCTION + '#endif\n',
    '#ifdef Q_OS_WIN\n' + SDK + '#endif\n#ifndef Q_OS_WIN\n' + FUNCTION + '#endif\n',
    '#ifdef Q_OS_WIN\n' + SDK + '#endif\n#undef Q_OS_WIN\n#ifdef Q_OS_WIN\n' + FUNCTION + '#endif\n',
])
def test_req_qml022_ac06_guard_equivalence_is_not_guessed(tmp_path, guarded):
    """Negative, compound, alternative and changed guard conditions carry no source witness."""
    path = tmp_path / "callbacks.cpp"
    path.write_bytes(guarded.encode())
    assert normalize_qt_cpp(guarded.encode()) is None
    with pytest.raises(QtCppError):
        read_cpp(path, tmp_path)


@pytest.mark.parametrize("source", [
    '#include "earlier.hpp"\n' + SDK + FUNCTION,
    SDK + FUNCTION + '#include "later.hpp"\n',
    '#ifdef Q_OS_WIN\n' + SDK + FUNCTION + '#endif\n',
    '#ifndef OWN_HEADER\n#define OWN_HEADER\n' + SDK + FUNCTION + '#endif\n',
    SDK + '#define CALLBACKÅ 1\n' + FUNCTION,
    SDK + '#define OPAQUE \\\n #undef CALLBACK\n' + FUNCTION,
])
def test_req_qml022_ac06_direct_sdk_source_boundary_and_later_unknown_include_are_explicit(tmp_path, source):
    """The direct header starts a source profile; a later include cannot alter earlier syntax."""
    path = tmp_path / "callbacks.cpp"
    path.write_bytes(source.encode())
    unit = read_cpp(path, tmp_path)
    assert not unit.tree.has_error
    assert not extract_cpp(path).get("parse_errors")


@pytest.mark.parametrize("body", [
    'long CALLBACK(int value){return value;} void invoke(){CALLBACK(1);}',
    'struct CALLBACK{}; CALLBACK value;',
    'struct Holder{int CALLBACK;int WINAPI;int APIENTRY;};',
    'struct Holder{int ÅCALLBACK;int CALLBACKÅ;};',
    'long CALLBACK;',
])
def test_req_qml022_ac06_ordinary_macro_spelling_remains_original_source(tmp_path, body):
    """Whole ordinary identifier declarations are not convention slots or hidden binders."""
    path = tmp_path / "callbacks.cpp"
    source = (SDK + body).encode()
    path.write_bytes(source)
    assert normalize_qt_cpp(source) is None
    assert read_cpp(path, tmp_path).parsed_source == source


def test_req_qml022_ac06_unrelated_malformed_source_keeps_final_qt_rejection(tmp_path):
    """A proven local repair composes, while the final whole-source gate remains strict."""
    path = tmp_path / "callbacks.cpp"
    source = (SDK + FUNCTION + 'void damaged(').encode()
    path.write_bytes(source)
    assert normalize_qt_cpp(source) is not None
    assert extract_cpp(path).get("parse_errors")
    with pytest.raises(QtCppError):
        read_cpp(path, tmp_path)


def test_req_qml022_ac06_macro_function_pointer_typedef_remains_explicitly_unsupported(tmp_path):
    """The profile repairs real declared functions, without widening pointer-type grammar."""
    path = tmp_path / "callbacks.cpp"
    path.write_text(SDK + 'typedef BOOL (CALLBACK *Handler)(int);')
    with pytest.raises(QtCppError):
        read_cpp(path, tmp_path)
    path.write_text('typedef BOOL (__stdcall *Handler)(int);')
    assert not read_cpp(path, tmp_path).tree.has_error


def test_req_qml022_ac06_owned_qml_annotation_payload_is_not_an_ordinary_convention_name(tmp_path):
    """A stringified QML export name is owned by its annotation, not a C++ binder."""
    path = tmp_path / "callbacks.cpp"
    path.write_text('#include <QObject>\n' + SDK
                    + 'class Owner:public QObject{Q_OBJECT QML_NAMED_ELEMENT(CALLBACK)};\n' + FUNCTION)
    unit = read_cpp(path, tmp_path)
    assert not unit.tree.has_error
    assert next(item for item in unit.macros if item["name"] == "QML_NAMED_ELEMENT")["args"] == ["CALLBACK"]
