"""C++/QML bridge tests for #1716 (aliases, signals, slots, Q_PROPERTY)."""
from __future__ import annotations

import importlib.util as _ilu
from pathlib import Path

import pytest

from graphify.build import build_from_json
from graphify.extract import extract

_needs_qml = pytest.mark.skipif(
    _ilu.find_spec("tree_sitter_qmljs") is None,
    reason="tree-sitter-qmljs not installed (optional [qml] extra)",
)


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _edges(result: dict, relations=("instantiates", "inherits")):
    return [e for e in result["edges"] if e.get("relation") in relations]


@_needs_qml
def test_qml_named_element_alias_resolves_to_real_cpp_class(tmp_path: Path):
    """QML_NAMED_ELEMENT("AppBackend") bridges QML AppBackend{} to C++ Backend."""
    base = tmp_path / "src"
    _write(base / "Backend.h", (
        "#include <QObject>\n"
        "class Backend : public QObject {\n"
        "    Q_OBJECT\n"
        '    QML_NAMED_ELEMENT("AppBackend")\n'
        "public:\n"
        "    explicit Backend(QObject *parent = nullptr);\n"
        "};\n"
    ))
    _write(base / "Main.qml", (
        "import QtQuick\n"
        "Item {\n"
        "    AppBackend {\n"
        "        id: backend\n"
        "    }\n"
        "}\n"
    ))
    result = extract(sorted(base.glob("*")), cache_root=tmp_path / "cache")

    backend_classes = [n for n in result["nodes"] if n.get("label") == "Backend"]
    assert len(backend_classes) == 1, backend_classes
    backend_nid = backend_classes[0]["id"]
    assert not any(n.get("label") == "AppBackend" for n in result["nodes"])
    assert any(e["target"] == backend_nid for e in _edges(result))


@_needs_qml
def test_bare_qml_element_still_resolves_via_generic_label_match(tmp_path: Path):
    """QML_ELEMENT (same name) still resolves via generic stub rewire."""
    base = tmp_path / "src"
    _write(base / "Widget.h", (
        "#include <QObject>\n"
        "class Widget : public QObject {\n"
        "    Q_OBJECT\n"
        "    QML_ELEMENT\n"
        "public:\n"
        "    explicit Widget(QObject *parent = nullptr);\n"
        "};\n"
    ))
    _write(base / "Main.qml", (
        "import QtQuick\n"
        "Item {\n"
        "    Widget {\n"
        "        id: w\n"
        "    }\n"
        "}\n"
    ))
    result = extract(sorted(base.glob("*")), cache_root=tmp_path / "cache")

    widget_nid = next(n["id"] for n in result["nodes"] if n.get("label") == "Widget")
    assert any(e["target"] == widget_nid for e in _edges(result))


@_needs_qml
def test_ambiguous_qml_alias_left_unresolved(tmp_path: Path):
    """Same alias on two classes stays unresolved (god-node guard)."""
    base = tmp_path / "src"
    _write(base / "One.h", (
        "#include <QObject>\n"
        "class One : public QObject {\n"
        "    Q_OBJECT\n"
        '    QML_NAMED_ELEMENT("Shared")\n'
        "public:\n"
        "    explicit One(QObject *parent = nullptr);\n"
        "};\n"
    ))
    _write(base / "Two.h", (
        "#include <QObject>\n"
        "class Two : public QObject {\n"
        "    Q_OBJECT\n"
        '    QML_NAMED_ELEMENT("Shared")\n'
        "public:\n"
        "    explicit Two(QObject *parent = nullptr);\n"
        "};\n"
    ))
    _write(base / "Main.qml", (
        "import QtQuick\n"
        "Item {\n"
        "    Shared {\n"
        "        id: s\n"
        "    }\n"
        "}\n"
    ))
    result = extract(sorted(base.glob("*")), cache_root=tmp_path / "cache")

    one_nid = next(n["id"] for n in result["nodes"] if n.get("label") == "One")
    two_nid = next(n["id"] for n in result["nodes"] if n.get("label") == "Two")
    assert not any(e["target"] in (one_nid, two_nid) for e in _edges(result))
    assert any(n.get("label") == "Shared" for n in result["nodes"])


@_needs_qml
def test_qml_bridge_edge_survives_build(tmp_path: Path):
    """Repointed instantiates edge survives build_from_json."""
    base = tmp_path / "src"
    _write(base / "Backend.h", (
        "#include <QObject>\n"
        "class Backend : public QObject {\n"
        "    Q_OBJECT\n"
        '    QML_NAMED_ELEMENT("AppBackend")\n'
        "public:\n"
        "    explicit Backend(QObject *parent = nullptr);\n"
        "};\n"
    ))
    _write(base / "Main.qml", (
        "import QtQuick\n"
        "Item {\n"
        "    AppBackend {\n"
        "        id: backend\n"
        "    }\n"
        "}\n"
    ))
    result = extract(sorted(base.glob("*")), cache_root=tmp_path / "cache")
    g = build_from_json(result)
    assert any(d.get("relation") == "instantiates" for _, _, d in g.edges(data=True))


@_needs_qml
def test_qml_register_type_alias_resolves_to_real_cpp_class(tmp_path: Path):
    """qmlRegisterType<T>(..., "Alias") bridges by corpus label lookup."""
    base = tmp_path / "src"
    _write(base / "Socket.h", (
        "#include <QObject>\n"
        "class QWebSocket : public QObject {\n"
        "    Q_OBJECT\n"
        "public:\n"
        "    explicit QWebSocket(QObject *parent = nullptr);\n"
        "};\n"
    ))
    _write(base / "main.cpp", (
        '#include "Socket.h"\n'
        "void registerTypes() {\n"
        '    qmlRegisterType<QWebSocket>("xuper.chat", 1, 0, "WebSocket");\n'
        "}\n"
    ))
    _write(base / "Main.qml", (
        "import QtQuick\n"
        "Item {\n"
        "    WebSocket {\n"
        "        id: ws\n"
        "    }\n"
        "}\n"
    ))
    result = extract(sorted(base.glob("*")), cache_root=tmp_path / "cache")

    socket_nid = next(n["id"] for n in result["nodes"] if n.get("label") == "QWebSocket")
    assert not any(n.get("label") == "WebSocket" for n in result["nodes"])
    assert any(e["target"] == socket_nid for e in _edges(result))


def test_signal_prototype_gets_signal_node(tmp_path: Path):
    """signals: bodyless prototypes become type=signal nodes."""
    base = tmp_path / "src"
    _write(base / "Backend.h", (
        "#include <QObject>\n"
        "class Backend : public QObject {\n"
        "    Q_OBJECT\n"
        "public:\n"
        "    explicit Backend(QObject *parent = nullptr);\n"
        "signals:\n"
        "    void userNameChanged();\n"
        "    void somethingHappened(int code);\n"
        "};\n"
    ))
    result = extract([base / "Backend.h"], cache_root=tmp_path / "cache")

    assert {n["label"] for n in result["nodes"] if n.get("type") == "signal"} == {
        "userNameChanged()", "somethingHappened()",
    }
    assert sum(1 for e in result["edges"] if e.get("context") == "signal") == 2


def test_slot_after_signals_section_tagged_as_slot(tmp_path: Path):
    """public/private slots: tag as slot, not signal."""
    base = tmp_path / "src"
    _write(base / "Backend.h", (
        "#include <QObject>\n"
        "class Backend : public QObject {\n"
        "    Q_OBJECT\n"
        "signals:\n"
        "    void userNameChanged();\n"
        "public slots:\n"
        "    void onTick();\n"
        "private slots:\n"
        "    void onInternal();\n"
        "};\n"
    ))
    result = extract([base / "Backend.h"], cache_root=tmp_path / "cache")

    assert {n["label"] for n in result["nodes"] if n.get("type") == "signal"} == {
        "userNameChanged()",
    }
    assert {n["label"] for n in result["nodes"] if n.get("type") == "slot"} == {
        "onTick()", "onInternal()",
    }
    assert sum(1 for e in result["edges"] if e.get("context") == "slot") == 2


def test_q_property_emits_property_node_and_accessor_edges(tmp_path: Path):
    """Q_PROPERTY emits property node + READ/WRITE/NOTIFY edges."""
    base = tmp_path / "src"
    _write(base / "Backend.h", (
        "#include <QObject>\n"
        "#include <QString>\n"
        "class Backend : public QObject {\n"
        "    Q_OBJECT\n"
        "    Q_PROPERTY(QString userName READ userName WRITE setUserName NOTIFY userNameChanged)\n"
        "    Q_PROPERTY(int count READ count NOTIFY countChanged CONSTANT)\n"
        "public:\n"
        "    QString userName() const;\n"
        "    void setUserName(const QString &name);\n"
        "    int count() const;\n"
        "signals:\n"
        "    void userNameChanged();\n"
        "    void countChanged();\n"
        "};\n"
    ))
    result = extract([base / "Backend.h"], cache_root=tmp_path / "cache")

    assert {n["label"] for n in result["nodes"] if n.get("type") == "property"} == {
        "userName", "count",
    }
    assert {n["label"] for n in result["nodes"] if n.get("type") == "signal"} == {
        "userNameChanged()", "countChanged()",
    }

    by_id = {n["id"]: n for n in result["nodes"]}

    def labeled(ctx: str):
        return {
            (by_id[e["source"]]["label"], by_id[e["target"]]["label"])
            for e in result["edges"] if e.get("context") == ctx
        }

    assert ("userName", "userName") in labeled("property_read")
    assert ("count", "count") in labeled("property_read")
    assert ("userName", "setUserName") in labeled("property_write")
    assert ("userName", "userNameChanged()") in labeled("property_notify")
    assert ("count", "countChanged()") in labeled("property_notify")
    assert not any(src == "count" for src, _ in labeled("property_write"))
    assert not any(n.get("label") == "Q_PROPERTY" for n in result["nodes"])


def test_q_object_and_qml_named_element_produce_no_spurious_nodes(tmp_path: Path):
    """Q_OBJECT / QML_NAMED_ELEMENT must not leak as field nodes."""
    base = tmp_path / "src"
    _write(base / "Backend.h", (
        "#include <QObject>\n"
        "class Backend : public QObject {\n"
        "    Q_OBJECT\n"
        '    QML_NAMED_ELEMENT("AppBackend")\n'
        "public:\n"
        "    explicit Backend(QObject *parent = nullptr);\n"
        "};\n"
    ))
    result = extract([base / "Backend.h"], cache_root=tmp_path / "cache")
    assert not any(n.get("label") in {"Q_OBJECT", "QML_NAMED_ELEMENT"} for n in result["nodes"])
