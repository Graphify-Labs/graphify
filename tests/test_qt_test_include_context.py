"""INC-QML-78: only caller-admitted forward header chains lend QtTest context."""
from __future__ import annotations

import pytest

from graphify.extract import extract, extract_cpp
from graphify.extractors.qt_cpp_facts import qt_metadata
from tests.qt_analysis_helpers import sites

FILES = {
    "framework.hpp": "#ifndef PUBLIC_FRAMEWORK_HPP\n#define PUBLIC_FRAMEWORK_HPP\n#include <QtTest>\n#endif\n",
    "fixture.hpp": '#include "framework.hpp"\n',
    "checks.hpp": '#include "fixture.hpp"\nclass Checks { public: void run(){QFETCH(int,state);QTRY_COMPARE(state,2);} };\n',
    "main.cpp": '#include "checks.hpp"\n',
}


def write_project(root, overrides=None):
    """Use neutral source headers; a Qt SDK and corpus execution are irrelevant."""
    return [write_source(root, name, source) for name, source in {**FILES, **(overrides or {})}.items()]


def write_source(root, name, source):
    path = root / name
    path.write_bytes(source.encode())
    return path


def test_req_qml022_ac03_admitted_literal_chain_shared_before_generic_and_qt_facts(tmp_path):
    """Three forward include edges preserve original body facts and a bounded witness."""
    paths = write_project(tmp_path)
    result = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not result.get("qml_failures") and not result.get("failed_sources")
    data = sites(result, "test_data")
    assert len(data) == len(sites(result, "test_assertion")) == 1
    md = qt_metadata(data[0])
    assert md["status"] == "source_only" and md["sdk_header"] == "QtTest"
    assert {item["source_file"] for item in md["include_witnesses"]} == {"checks.hpp", "fixture.hpp", "framework.hpp"}
    assert all(len(item["source_sha256"]) == 64 for item in md["include_witnesses"])
    assert len([node for node in result["nodes"] if node["label"] == ".run()" and node.get("_callable")]) == 1
    # A direct caller supplied no accepted include cohort, so cannot discover it.
    assert extract_cpp(tmp_path / "checks.hpp").get("parse_errors")


@pytest.mark.parametrize("missing", ["fixture.hpp", "framework.hpp"])
def test_req_qml022_ac06_partial_extraction_never_discovers_unprovided_header(tmp_path, missing):
    """Existing disk files outside the explicit list remain unavailable input."""
    paths = [path for path in write_project(tmp_path) if path.name != missing]
    result = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not sites(result, "test_data") and not sites(result, "test_assertion")


@pytest.mark.parametrize("header", [
    '#if UNKNOWN\n#include <QtTest>\n#endif\n',
    '#include "fixture.hpp"\n#include <QtTest>\n',
    '#include <QtTest>\n#undef QFETCH\n',
    '#include <QtTest>\n#define QFETCH(t,n) forged\n',
    '#include <QtTest>\n#undef QFETCH\nvoid QFETCH(int,int);\n',
    '#include FRAMEWORK_HEADER\n',
])
def test_req_qml022_ac06_unknown_cyclic_overridden_context_never_lends_typed_authority(tmp_path, header):
    """Rejected chain semantics cannot silently admit an opaque local binder."""
    paths = write_project(tmp_path, {"framework.hpp": header})
    result = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not sites(result, "test_data")


def test_req_qml022_ac06_include_after_the_macro_is_not_forward_source_context(tmp_path):
    """File visibility does not move an actual include before its source occurrence."""
    paths = write_project(tmp_path, {"checks.hpp": 'class Checks{public:void run(){QFETCH(int,state);}};\n#include "fixture.hpp"\n'})
    result = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not sites(result, "test_data")


@pytest.mark.parametrize("rewrite", ["#undef QFETCH", "#define QFETCH(t,n) altered"])
def test_req_qml022_ac06_conditional_header_interference_cannot_leave_direct_sdk_authority(tmp_path, rewrite):
    """A conditional header may alter macros but never supplies positive context."""
    paths = write_project(tmp_path, {"checks.hpp": '#include <QTest>\n#if FEATURE\n#include "override.hpp"\n#endif\nclass Checks{public:void run(){QFETCH(int,state);}};\n'})
    paths.append(write_source(tmp_path, "override.hpp", rewrite + "\n"))
    result = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not sites(result, "test_data")


def test_req_qml022_ac06_caller_snapshot_is_immutable_and_original_target_bytes_are_required(tmp_path):
    """Stale bytes and malformed typed witnesses reject at the actual read boundary."""
    from dataclasses import FrozenInstanceError, replace
    from graphify.extractors.qt_cpp_test_context import build_qt_test_contexts
    from graphify.extractors.qt_cpp_syntax import QtCppError, read_cpp
    paths = write_project(tmp_path)
    snapshot = build_qt_test_contexts(paths, root=tmp_path)
    path = tmp_path / "checks.hpp"
    context = snapshot.for_path(path)
    assert context is not None
    with pytest.raises(FrozenInstanceError):
        setattr(context, "source_sha256", "0" * 64)
    unit = read_cpp(path, tmp_path, qt_test_context=context)
    assert len(unit.qt_test_macros) == 2
    malformed = replace(context, activations=(replace(context.activations[0], witnesses=(None,)),))
    with pytest.raises(QtCppError) as error:
        read_cpp(path, tmp_path, qt_test_context=malformed)
    assert error.value.code == "QT_CPP_CONTEXT"
    path.write_bytes(path.read_bytes() + b"// changed\n")
    with pytest.raises(QtCppError) as error:
        read_cpp(path, tmp_path, qt_test_context=context)
    assert error.value.code == "QT_CPP_CONTEXT"


@pytest.mark.parametrize("before", [False, True])
def test_req_qml022_ac06_unknown_header_effect_is_forward_only(tmp_path, before):
    """Unknown generated/ordinary headers affect only later source occurrences."""
    from graphify.extractors.qt_cpp_test_context import build_qt_test_contexts
    from graphify.extractors.qt_cpp_syntax import QtCppError, read_cpp
    statement = 'void run(){QFETCH(int,state);QTRY_COMPARE(state,2);}\n'
    unknown = '#include "unprovided.hpp"\n'
    path = write_source(tmp_path, "checks.cpp", '#include <QTest>\n' + (unknown + statement if before else statement + unknown))
    snapshot = build_qt_test_contexts([path], root=tmp_path)
    if before:
        with pytest.raises(QtCppError) as error:
            read_cpp(path, tmp_path, qt_test_context=snapshot.for_path(path))
        assert error.value.code == "QT_CPP_SYNTAX"
    else:
        assert len(read_cpp(path, tmp_path, qt_test_context=snapshot.for_path(path)).qt_test_macros) == 2


def test_req_qml022_ac06_header_final_unknown_effect_blocks_only_its_later_parent(tmp_path):
    """Header-local earlier data remains observed; its final unknown effects reach callers."""
    from graphify.extractors.qt_cpp_test_context import build_qt_test_contexts
    from graphify.extractors.qt_cpp_syntax import QtCppError, read_cpp
    header = write_source(tmp_path, "framework.hpp", '#include <QTest>\nvoid own(){QFETCH(int,ownValue);}\n#include "unprovided.hpp"\n')
    parent = write_source(tmp_path, "parent.cpp", '#include "framework.hpp"\nvoid caller(){QFETCH(int,parentValue);}\n')
    snapshot = build_qt_test_contexts([header, parent], root=tmp_path)
    assert len(read_cpp(header, tmp_path, qt_test_context=snapshot.for_path(header)).qt_test_macros) == 1
    with pytest.raises(QtCppError) as error:
        read_cpp(parent, tmp_path, qt_test_context=snapshot.for_path(parent))
    assert error.value.code == "QT_CPP_SYNTAX"


@pytest.mark.parametrize("corruption", ["source", "hash", "span", "literal", "order", "sdk"])
def test_req_qml022_ac06_final_witness_integrity_rejects_well_typed_corruption(tmp_path, corruption):
    """Plausible typed snapshots cannot lend foreign, shifted or altered include provenance."""
    from dataclasses import replace
    from graphify.extractors.qt_cpp_test_context import build_qt_test_contexts, verify_test_contexts, QtTestContextError
    paths = write_project(tmp_path)
    snapshot = build_qt_test_contexts(paths, root=tmp_path)
    context = snapshot.for_path(tmp_path / "checks.hpp")
    activation = context.activations[0]
    witness = activation.witnesses[0]
    if corruption == "source":
        witness = replace(witness, source_file="missing.hpp")
    elif corruption == "hash":
        witness = replace(witness, source_sha256="0" * 64)
    elif corruption == "span":
        witness = replace(witness, span=(1, *witness.span[1:]))
    elif corruption == "literal":
        witness = replace(witness, include_literal="other.hpp")
    elif corruption == "order":
        activation = replace(activation, after=activation.after + 1)
    else:
        activation = replace(activation, sdk_header="QTest")
    activation = replace(activation, witnesses=(witness, *activation.witnesses[1:]))
    changed = replace(context, activations=(activation,))
    snapshot = replace(snapshot, contexts=tuple(changed if item is context else item for item in snapshot.contexts))
    with pytest.raises(QtTestContextError) as error:
        verify_test_contexts(snapshot, root=tmp_path)
    assert error.value.code == "QT_CPP_CONTEXT"
