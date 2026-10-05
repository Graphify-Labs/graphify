"""QML-016 native event success, rejection and source-provenance acceptance."""
import json

from graphify.extractors.qt_cpp_facts import qt_metadata
from tests.qt_analysis_helpers import analysis, sites

SOURCE = '''class Sender : public QObject {
 Q_OBJECT
signals:
 void changed(int value);
public:
 void run() { emit changed(1); Q_EMIT changed(2); changed(3); }
};
class Receiver : public QObject {
 Q_OBJECT
public:
 void accept(int value) {}
private slots:
 void hidden(int value) {}
};
void wire(Sender *sender, Receiver *receiver) {
 QObject::connect(sender, &Sender::changed, receiver, &Receiver::accept, Qt::QueuedConnection);
 QObject::connect(sender, SIGNAL(changed(int)), receiver, SLOT(hidden(int)));
 QObject::connect(sender, &Sender::changed, receiver, [](int value) {}, Qt::UniqueConnection);
 QObject::disconnect(sender, &Sender::changed, receiver, &Receiver::accept);
}
'''


def test_native_events_have_distinct_sites_and_no_delivery_calls(tmp_path):
    result = analysis(tmp_path, {"events.cpp": SOURCE})
    emissions = sites(result, "emission")
    assert len(emissions) == 3
    assert all(qt_metadata(node)["status"] == "resolved" for node in emissions)
    connections = sites(result, "connect")
    assert len(connections) == 3
    assert all(qt_metadata(node)["status"] == "resolved" for node in connections)
    assert len(sites(result, "disconnect")) == 1
    assert qt_metadata(sites(result, "disconnect")[0])["status"] == "resolved"
    assert qt_metadata(connections[0])["declared_type"] == "QueuedConnection"
    assert qt_metadata(connections[-1])["unique_connection_effect"] == "not_guaranteed_for_functors"
    event_ids = {node["id"] for node in [*emissions, *connections]}
    assert not [edge for edge in result["edges"] if edge["source"] in event_ids and edge["relation"] == "calls"]
    assert len({node["id"] for node in emissions}) == 3
    assert all(qt_metadata(node)["span"]["start_byte"] < qt_metadata(node)["span"]["end_byte"] for node in emissions)


def test_macro_sections_private_meta_slots_and_comments(tmp_path):
    source = SOURCE.replace("signals:", "Q_SIGNALS:").replace("private slots:", "private Q_SLOTS:")
    source += '\n// QObject::connect(sender, &Sender::changed, receiver, &Receiver::accept);\nconst char *text = "emit changed(9)";'
    result = analysis(tmp_path, {"events.cpp": source})
    assert len(sites(result, "connect")) == 3
    hidden = [node for node in sites(result, "member") if qt_metadata(node)["raw_name"] == "hidden"]
    assert len(hidden) == 1 and qt_metadata(hidden[0])["access"] == "private"
    assert qt_metadata(hidden[0])["roles"] == ["slot"]


def test_overloads_need_selector_and_dynamic_sender_stays_unresolved(tmp_path):
    source = SOURCE.replace("void changed(int value);", "void changed(int value);\n void changed(double value);")
    source = source.replace("&Sender::changed, receiver, &Receiver::accept, Qt::QueuedConnection", "qOverload<int>(&Sender::changed), receiver, &Receiver::accept, Qt::QueuedConnection")
    result = analysis(tmp_path, {"events.cpp": source})
    connections = sites(result, "connect")
    assert qt_metadata(connections[0])["status"] == "resolved"
    assert qt_metadata(connections[2])["signal_status"] == "ambiguous"
    result2 = analysis(tmp_path, {"events.cpp": SOURCE.replace("QObject::connect(sender, &Sender::changed, receiver, &Receiver::accept", "QObject::connect(factory(), &Sender::changed, receiver, &Receiver::accept")})
    assert qt_metadata(sites(result2, "connect")[0])["status"] != "resolved"


def test_nested_literal_metadata_round_trip_is_exact(tmp_path):
    result = analysis(tmp_path, {"events.cpp": SOURCE.replace("int value", "QList<int> value").replace("changed(int)", "changed(QList<int>)").replace("hidden(int)", "hidden(QList<int>)")})
    node = sites(result, "connect")[1]
    assert qt_metadata(json.loads(json.dumps(node)))["signal"]["parameter_types"] == ["QList<int>"]
