"""Native Qt event overload, callable, conditional and false-positive boundaries."""
from graphify.extractors.qt_cpp_facts import qt_metadata
from tests.qt_analysis_helpers import analysis, sites
from tests.test_qt_signals_slots import SOURCE


def test_functor_function_and_connection_handle_disconnect(tmp_path):
    source = SOURCE + '''class Functor { public: void operator()(int value) {} };
void consume(int value) {}
void extra(Sender *sender, Receiver *receiver) {
 Functor callable;
 QObject::connect(sender, &Sender::changed, receiver, callable);
 QObject::connect(sender, &Sender::changed, &consume);
 auto handle = QObject::connect(sender, &Sender::changed, receiver, &Receiver::accept);
 QObject::disconnect(handle);
 QObject::disconnect(sender, nullptr, receiver, nullptr);
}
'''
    result = analysis(tmp_path, {"events.cpp": source})
    connections = sites(result, "connect")[-3:]
    assert all(qt_metadata(site)["status"] == "resolved" for site in connections), [qt_metadata(site) for site in connections]
    disconnects = sites(result, "disconnect")[-2:]
    assert all(qt_metadata(site)["status"] == "resolved" for site in disconnects)
    assert qt_metadata(disconnects[0])["target_id"] == connections[-1]["id"]
    assert qt_metadata(disconnects[1])["reason"] == "source_wildcard_disconnect"


def test_explicit_cast_signal_to_signal_and_condition_flags(tmp_path):
    source = SOURCE + '''void extra(Sender *sender, Sender *other, bool enabled, Qt::ConnectionType mode) {
 if (enabled) QObject::connect(sender, static_cast<void (Sender::*)(int)>(&Sender::changed), other, &Sender::changed, Qt::DirectConnection | Qt::SingleShotConnection);
 QObject::connect(sender, &Sender::changed, other, &Sender::changed, mode);
}
'''
    result = analysis(tmp_path, {"events.cpp": source})
    first, second = sites(result, "connect")[-2:]
    assert qt_metadata(first)["status"] == "resolved" and qt_metadata(first)["conditional"]
    assert qt_metadata(first)["signal_target_id"] == qt_metadata(first)["receiver_target_id"]
    assert qt_metadata(first)["flags"] == ["SingleShotConnection"]
    assert qt_metadata(second)["dynamic_flags"]
    endpoints = [node for node in sites(result, "event_endpoint") if qt_metadata(node)["owner_id"] == first["id"]]
    assert len(endpoints) == 2 and endpoints[0]["id"] != endpoints[1]["id"]


def test_private_typed_pointer_and_incompatible_receiver_are_rejected(tmp_path):
    source = SOURCE.replace("&Receiver::accept, Qt::QueuedConnection", "&Receiver::hidden, Qt::QueuedConnection")
    result = analysis(tmp_path, {"events.cpp": source})
    assert qt_metadata(sites(result, "connect")[0])["status"] != "resolved"
    incompatible = SOURCE.replace("void accept(int value)", "void accept(QString value)")
    result2 = analysis(tmp_path, {"events.cpp": incompatible})
    assert qt_metadata(sites(result2, "connect")[0])["status"] != "resolved"


def test_computed_signal_receiver_and_custom_connect_are_not_qt_targets(tmp_path):
    source = SOURCE.replace("emit changed(1);", "emit factory()->changed(1);")
    result = analysis(tmp_path, {"events.cpp": source})
    assert qt_metadata(sites(result, "emission")[0])["status"] != "resolved"
    custom = '''class Widget : public QObject { Q_OBJECT public:
 void connect(QObject *a, int b, QObject *c, int d) {}
 void run(QObject *a) { connect(a, 1, a, 2); } };'''
    result2 = analysis(tmp_path, {"custom.cpp": custom})
    assert not sites(result2, "connect")


def test_const_reference_compatibility_does_not_allow_mutable_reference(tmp_path):
    compatible = SOURCE.replace('void accept(int value)', 'void accept(const int &value)')
    result = analysis(tmp_path, {"events.cpp": compatible})
    assert qt_metadata(sites(result, "connect")[0])["status"] == "resolved"
    mutable = SOURCE.replace('void accept(int value)', 'void accept(int &value)')
    result2 = analysis(tmp_path, {"events.cpp": mutable})
    assert qt_metadata(sites(result2, "connect")[0])["status"] != "resolved"


def test_direct_cpp_slot_call_remains_an_ordinary_call(tmp_path):
    source = SOURCE.replace('private slots:', 'public slots:\n void active(int value) {}\nprivate slots:').replace('QObject::disconnect(sender, &Sender::changed, receiver, &Receiver::accept);', 'QObject::disconnect(sender, &Sender::changed, receiver, &Receiver::accept);\n receiver->active(5);')
    result = analysis(tmp_path, {"events.cpp": source})
    active = [node for node in sites(result, "member") if qt_metadata(node)["raw_name"] == "active"][0]
    target = qt_metadata(active)["generic_target_id"]
    assert target
    assert any(edge["target"] == target and edge["relation"] == "calls" for edge in result["edges"])
    assert len(sites(result, "connect")) == 3 and len(sites(result, "disconnect")) == 1
