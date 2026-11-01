"""REQ-QML-022-AC03/06: native signal authority differs from typed receiver calls."""
import pytest

from graphify.extractors.qt_cpp_facts import qt_metadata
from tests.qt_analysis_helpers import analysis, sites


def source(sender="Q_OBJECT", receiver=""):
    return f'''class Sender : public QObject {{ {sender}
public: Q_SIGNAL void changed(int value); void fire() {{ emit changed(1); }}
}};
class Receiver : public QObject {{ {receiver}
public: void ordinary(int value) {{}} Q_SLOT void accepted(int value) {{}}
}};
void wire(Sender *sender, Receiver *receiver) {{
 QObject::connect(sender, &Sender::changed, receiver, &Receiver::ordinary);
 QObject::connect(sender, &Sender::changed, receiver, &Receiver::accepted);
 QObject::connect(sender, SIGNAL(changed(int)), receiver, SLOT(accepted(int)));
}}
'''


@pytest.mark.parametrize("marker", ["", "#if ENABLED\nQ_OBJECT\n#endif", "Q_OBJECT Q_OBJECT"])
def test_req_qml022_ac03_signal_and_emission_require_declaring_metaobject(tmp_path, marker):
    """A signal spelling on a QObject subclass cannot supply its missing own metaobject."""
    result = analysis(tmp_path, {"events.cpp": source(marker)})
    assert sites(result, "emission") and sites(result, "connect")
    assert all(qt_metadata(n)["status"] != "resolved" for n in sites(result, "emission") + sites(result, "connect"))
    assert not [e for e in result["edges"] if e.get("context") in {"qt_signal_emit", "qt_connect_signal", "qt_connect_receiver"}]


def test_req_qml022_ac03_typed_receiver_functions_do_not_require_own_metaobject(tmp_path):
    """Typed pointer calls work for ordinary functions/slot declarations; legacy SLOT needs moc metadata."""
    result = analysis(tmp_path, {"events.cpp": source()})
    connections = sites(result, "connect")
    assert [qt_metadata(n)["status"] for n in connections[:2]] == ["resolved", "resolved"]
    assert qt_metadata(connections[2])["status"] != "resolved"
    assert qt_metadata(sites(result, "emission")[0])["status"] == "resolved"
    assert len([e for e in result["edges"] if e.get("context") == "qt_connect_receiver"]) == 2


def test_req_qml022_ac03_own_receiver_marker_preserves_legacy_slots(tmp_path):
    """Valid source-owned markers on both declaring classes preserve every existing mechanism."""
    result = analysis(tmp_path, {"events.cpp": source(receiver="Q_OBJECT")})
    assert all(qt_metadata(n)["status"] == "resolved" for n in sites(result, "connect") + sites(result, "emission"))
