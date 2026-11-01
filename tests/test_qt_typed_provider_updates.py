"""REQ-QML-018-AC03--AC06: typed providers through real accepted updates."""
from __future__ import annotations

import pytest

from graphify.cache import cache_dir
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.watch import _rebuild_code
from tests.qt_adoption_fixture import sources
from tests.test_qt_final_incremental_parity import clean, normalized, run, unrelated


PRODUCTS = ("graph.json", "manifest.json", ".qt_analysis.json", ".graphify_root")


def corpus(root):
    """A public qmake module supplies the engine load; declaration facts supply APIs."""
    files = sources(root)
    beginning = files["access.cpp"].split('engine.load(QUrl("')[0]
    files["access.cpp"] = beginning + 'engine.loadFromModule("Public.Tools", "Main"); }\n'
    files["tools.pro"] = 'QML_IMPORT_NAME = Public.Tools\nQML_IMPORT_VERSION = 1.0\n'
    files["tools.pro"] += 'HEADERS += $$PWD/native.h\nQML_FILES += $$PWD/Main.qml\n'
    files["keep.py"] = 'def helper(): return 7\n\ndef retained(): return helper()\n'
    for name, text in files.items():
        (root / name).write_bytes(text.encode())


def facts(graph, kind):
    return {identity: qt_metadata(node) for identity, node in graph.nodes(data=True)
            if qt_metadata(node).get("kind") == kind}


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml018_ac05_cpp_qml_metadata_and_signal_updates_match_clean_rebuild(tmp_path, monkeypatch, operation):
    """Real provider/property/signal and metadata mutations retire stale accepted sites."""
    corpus(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    assert len(facts(initial, "context_subscription")) == 2
    assert normalized(initial) == normalized(clean(tmp_path, tmp_path / ".cold"))
    assert normalized(clean(tmp_path, tmp_path / ".cold")) == normalized(initial)
    preserved = unrelated(initial)
    header, qml, build = (tmp_path / name for name in ("native.h", "Main.qml", "tools.pro"))
    original_header, original_qml, original_build = header.read_bytes(), qml.read_bytes(), build.read_bytes()

    # C++-only return-type loss rejects the factory without a name-based fallback.
    header.write_bytes(original_header.replace(b"Backend *makeBackend()", b"Unknown *makeBackend()"))
    rejected = run(tmp_path, monkeypatch, operation, [header])
    assert not facts(rejected, "context_binding")
    assert normalized(rejected) == normalized(clean(tmp_path, tmp_path / ".unknown-return"))
    header.write_bytes(original_header)
    assert normalized(run(tmp_path, monkeypatch, operation, [header])) == normalized(initial)

    # A declared child API rename invalidates unchanged QML service paths.
    header.write_bytes(original_header.replace(b"Service* service READ service", b"Service* child READ service"))
    no_child = run(tmp_path, monkeypatch, operation, [header])
    assert not facts(no_child, "context_subscription")
    assert normalized(no_child) == normalized(clean(tmp_path, tmp_path / ".child-rename"))
    qml.write_bytes(original_qml.replace(b"backend.service", b"backend.child"))
    rebound = run(tmp_path, monkeypatch, operation, [qml])
    assert len(facts(rebound, "context_subscription")) == 2
    assert normalized(rebound) == normalized(clean(tmp_path, tmp_path / ".qml-rebind"))

    # Both subscription forms lose a removed signal, retaining ordinary calls.
    header.write_bytes(header.read_bytes().replace(b"signals: void ready();", b""))
    no_signal = run(tmp_path, monkeypatch, operation, [header])
    assert not facts(no_signal, "context_subscription")
    assert facts(no_signal, "context_access")
    assert normalized(no_signal) == normalized(clean(tmp_path, tmp_path / ".signal-removed"))
    header.write_bytes(original_header)
    qml.write_bytes(original_qml)
    assert normalized(run(tmp_path, monkeypatch, operation, [header, qml])) == normalized(initial)

    # Metadata-only URI changes invalidate the source-established loaded scope.
    build.write_bytes(original_build.replace(b"Public.Tools", b"Public.Other"))
    no_component = run(tmp_path, monkeypatch, operation, [build])
    assert not facts(no_component, "context_binding")
    assert normalized(no_component) == normalized(clean(tmp_path, tmp_path / ".module-removed"))
    build.write_bytes(original_build)
    final = run(tmp_path, monkeypatch, operation, [build])
    assert normalized(final) == normalized(initial) and unrelated(final) == preserved
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(final)


@pytest.mark.parametrize("operation", ["manual", "watch"])
@pytest.mark.parametrize("failure", ["cpp", "qml", "resolver"])
def test_req_qml018_ac06_parser_and_resolver_failure_preserve_then_recover(tmp_path, monkeypatch, operation, failure):
    """A real source parse failure or owning resolver exception retains committed products."""
    corpus(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    output = tmp_path / "graphify-out"
    before = {name: (output / name).read_bytes() for name in PRODUCTS}
    cache = {path: path.read_bytes() for path in cache_dir(tmp_path).rglob("*") if path.is_file()}
    path = tmp_path / ("native.h" if failure in {"cpp", "resolver"} else "Main.qml")
    valid = path.read_bytes()
    path.write_bytes(valid + (b"class Broken {\n" if failure == "cpp" else b"Item {\n" if failure == "qml" else b"\n// changed\n"))
    with monkeypatch.context() as broken:
        if failure == "resolver":
            from graphify.qt_declared_provider import DeclaredProviderIndex
            original = DeclaredProviderIndex.provider
            def reject(self, metadata):
                original(self, metadata)
                raise ValueError("QT_METADATA: public test transport corruption")
            broken.setattr(DeclaredProviderIndex, "provider", reject)
        if operation == "manual":
            with pytest.raises(SystemExit) as rejected:
                run(tmp_path, broken, operation, [path])
            assert rejected.value.code == 1
        else:
            assert not _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True)
    assert before == {name: (output / name).read_bytes() for name in PRODUCTS}
    assert cache and all(path.read_bytes() == data for path, data in cache.items())
    path.write_bytes(valid)
    corrected = run(tmp_path, monkeypatch, operation, [path])
    assert normalized(corrected) == normalized(initial)
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(initial)


@pytest.mark.parametrize("operation", ["manual", "watch"])
@pytest.mark.parametrize("shape", ["return", "child", "root"])
def test_req_qml018_ac03_ac04_declarator_shape_edit_retires_and_repairs_api(tmp_path, monkeypatch, operation, shape):
    """An accepted syntax edit cannot retain stale one-object API links after shape changes."""
    corpus(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    assert len(facts(initial, "context_subscription")) == 2
    path = tmp_path / ("access.cpp" if shape == "root" else "native.h")
    original = path.read_bytes()
    if shape == "return":
        changed = original.replace(b"Backend *makeBackend()", b"Backend **makeBackend()")
    elif shape == "child":
        changed = original.replace(b"Service* service", b"Service** service").replace(b"Service *service()", b"Service **service()")
    else:
        changed = original.replace(b"Factory *factory", b"Factory **factory")
    path.write_bytes(changed)
    rejected = run(tmp_path, monkeypatch, operation, [path])
    assert not facts(rejected, "context_subscription")
    assert bool(facts(rejected, "context_binding")) is (shape == "child")
    assert normalized(rejected) == normalized(clean(tmp_path, tmp_path / ".shape-rebuild"))
    path.write_bytes(original)
    assert normalized(run(tmp_path, monkeypatch, operation, [path])) == normalized(initial)
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(initial)


@pytest.mark.parametrize("operation", ["manual", "watch"])
@pytest.mark.parametrize("parameter", ["backend", "handleReady"])
def test_req_qml018_ac04_native_parameter_edit_retires_nested_subscription_and_repairs(tmp_path, monkeypatch, operation, parameter):
    """Unchanged cached QML is rebound after C++ alone adds/removes a legacy signal parameter."""
    corpus(tmp_path)
    qml = tmp_path / "Main.qml"
    qml.write_text('import QtQml\nQtObject { function handleReady() {} property Connections sub: Connections {'
                   ' target: backend.service; onReady: { backend.service.ready.connect(handleReady) } } }', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    assert len(facts(initial, "context_subscription")) == 2
    header = tmp_path / "native.h"
    original = header.read_bytes()
    header.write_bytes(original.replace(b"void ready();", ("void ready(int " + parameter + ");").encode()))
    shadowed = run(tmp_path, monkeypatch, operation, [header])
    assert len(facts(shadowed, "context_subscription")) == 1
    assert len(facts(shadowed, "context_handler_endpoint")) == 1
    assert normalized(shadowed) == normalized(clean(tmp_path, tmp_path / ".implicit-rebuild"))
    header.write_bytes(original)
    restored = run(tmp_path, monkeypatch, operation, [header])
    assert normalized(restored) == normalized(initial)
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(initial)
