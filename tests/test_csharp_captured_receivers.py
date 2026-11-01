"""INC-QML-105: local calls capture only proven enclosing receiver bindings."""
import json
from copy import deepcopy

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract, extract_csharp
from graphify.paths import load_node_link_graph
from tests.csharp_capture_helpers import TYPES, capture_calls, graph_payload, local, method, source


@pytest.mark.parametrize("mode,nested,constructor", [
    (mode, nested, constructor)
    for mode in ("parameter", "typed", "var", "using", "await_using")
    for nested, constructor in ((False, False), (True, False), (False, True))
    if not (constructor and mode == "await_using")
])
def test_req_qml022_ac02_local_receiver_captures_keep_source_caller_and_class_target(tmp_path, mode, nested, constructor):
    """Method/constructor/nested-local capture reuses the one existing receiver inferencer."""
    path = tmp_path / "Capture.cs"
    raw = ("\ufeff// café 雪\r\n" + source(mode, nested=nested, constructor=constructor)).encode()
    path.write_bytes(raw)
    direct = extract_csharp(path)
    caller = local(direct)
    raw_call, = [call for call in direct["raw_calls"] if call["caller_nid"] == caller["id"] and call["callee"] == "Run"]
    assert raw_call.get("receiver_type") == "Worker"
    span = caller["metadata"]["csharp_local_function"]["span"]
    assert raw[span["start_byte"]:span["end_byte"]] == b"void Inner(){worker.Run();}"
    assert not any(node["label"] == "worker" for node in direct["nodes"])
    seen = []
    for phase in ("cold", "warm"):
        result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
        assert not result["failed_sources"]
        (call,) = capture_calls(result)
        assert call["target"] == method(result, "Worker")["id"]
        # Receiver-type joins retain the upstream inferred-call classification;
        # capture ownership does not strengthen their runtime certainty.
        assert call["source"] == local(result)["id"] and call["confidence"] == "INFERRED"
        assert call["confidence_score"] == 0.85 and call["context"] == "call"
        graph = build_from_json(result, root=tmp_path, directed=True)
        output = tmp_path / (phase + ".json")
        assert to_json(graph, {}, str(output), force=True)
        loaded = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
        assert capture_calls(graph_payload(loaded))[0]["target"] == call["target"]
        seen.append(result)
    assert seen[0] == seen[1]


# Name each unavailable binding role independently of pytest's source-value IDs.
@pytest.mark.parametrize("body", [
    "void Inner(){worker.Run();} Worker worker=new Worker(); Inner();",
    "{Worker worker=new Worker();} void Inner(){worker.Run();} Inner();",
    "Worker worker=new Worker(); static void Inner(){worker.Run();} Inner();",
    "Worker worker=new Worker(); static void Outer(){void Inner(){worker.Run();} Inner();} Outer();",
    "Worker worker=new Worker(); System.Action action=static()=>{void Inner(){worker.Run();}Inner();};",
    "for(Worker worker=new Worker();KeepGoing();){void Inner(){worker.Run();}Inner();}",
    "using(Worker worker=new Worker()){void Inner(){worker.Run();}Inner();}",
    "dynamic worker=null; void Inner(){worker.Run();} Inner();",
    "var worker=Unknown(); void Inner(){worker.Run();} Inner();",
    "Worker worker=new Worker(); Other worker=new Other(); void Inner(){worker.Run();} Inner();",
    "\n#if FEATURE\nWorker worker=new Worker();\n#else\nOther worker=new Other();\n#endif\nvoid Inner(){worker.Run();} Inner();",
], ids=["declared-after-local", "closed-block", "static-local", "nested-static-local",
        "static-lambda-capture", "for-initializer-binding", "using-statement-binding",
        "dynamic-receiver", "unknown-inferred-type", "duplicate-receiver", "conditional-receiver-types"])
def test_req_qml022_ac06_capture_rejects_out_of_scope_unproved_or_static_bindings(tmp_path, body):
    """Unavailable capture cannot borrow a convenient same-named class method."""
    path = tmp_path / "Capture.cs"
    path.write_bytes((TYPES + "class Host{void Use(){" + body + "}}").encode())
    for result in (extract_csharp(path), extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)):
        assert not capture_calls(result)
        assert not any(call.get("receiver_type") == "Worker" for call in result.get("raw_calls", [])
                       if call["caller_nid"] == local(result)["id"] and call.get("callee") == "Run")


@pytest.mark.parametrize("parameter,expected", [("Other worker", "Other"), ("Worker worker", "Worker")])
def test_req_qml022_ac02_local_parameter_owns_receiver_before_outer_capture(tmp_path, parameter, expected):
    """The local function's own parameter stays authoritative over an outer name."""
    path = tmp_path / "Capture.cs"
    path.write_text(TYPES + "class Host{void Use(Worker worker){void Inner(" + parameter + "){worker.Run();}Inner(null);}}")
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    (edge,) = capture_calls(result)
    assert edge["target"] == method(result, expected)["id"]


def test_req_qml022_ac06_captured_delegate_stays_data_without_new_variable_nodes(tmp_path):
    """A runtime delegate capture cannot become Other.callback or a variable graph node."""
    path = tmp_path / "Capture.cs"
    path.write_text("class Host{void Use(System.Action callback){void Inner(){callback();}Inner();}}class Other{void callback(){}}")
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    caller = local(result)
    assert not any(edge["source"] == caller["id"] and edge["relation"] in {"calls", "indirect_call"} for edge in result["edges"])
    assert not any(node["label"] == "callback" for node in result["nodes"])


def test_req_qml022_ac06_capture_modifier_checks_do_not_rescan_callable_bodies(tmp_path, monkeypatch):
    """Twenty real capture sites retain types without repeatedly decoding their outer body."""
    import graphify.extractors.csharp_lexical_calls as lexical
    path = tmp_path / "Capture.cs"
    children = "".join(f"void Inner{i}(){{worker.Run();}}Inner{i}();" for i in range(20))
    path.write_text(TYPES + "class Host{void Use(Worker worker){" + children + "}}")
    original, blocks = lexical._read_text, []

    def observed(node, raw):
        if node.type == "block":
            blocks.append(node.end_byte - node.start_byte)
        return original(node, raw)

    monkeypatch.setattr(lexical, "_read_text", observed)
    result = extract_csharp(path)
    captures = [call for call in result["raw_calls"] if call.get("callee") == "Run"]
    assert len(captures) == 20 and all(call.get("receiver_type") == "Worker" for call in captures)
    assert not blocks, "Modifier lookup must inspect actual modifier nodes, never complete bodies"


# Stable role names keep valid-capture evidence comparable across pytest versions.
@pytest.mark.parametrize("body", [
    "void Use(Other worker){static void Inner(Worker worker){worker.Run();}Inner(null);}",
    "void Use(Other worker){static void Outer(Worker worker){void Inner(){worker.Run();}Inner();}Outer(null);}",
    "void Use(Worker @worker){void Inner(){worker.Run();}Inner();}",
    "void Use(Worker worker){void Inner(){@worker.Run();}Inner();}",
    "void Use(Other worker){System.Action<Worker> action=static(Worker worker)=>{void Inner(){worker.Run();}Inner();};}",
    "void Use(Other worker){System.Action<Worker> action=(Worker worker)=>{void Inner(){worker.Run();}Inner();};}",
    "void Use(){System.Action action=static()=>{Worker worker=new Worker();void Inner(){worker.Run();}Inner();};}",
], ids=["static-local-parameter", "nested-static-parameter", "escaped-outer-parameter",
        "escaped-local-reference", "static-lambda-parameter", "lambda-parameter", "static-lambda-owned-local"])
def test_req_qml022_ac02_capture_static_own_parameters_and_literal_aliases_remain_valid(tmp_path, body):
    """An actual static-frame parameter and escaped spellings retain their proven identity."""
    path = tmp_path / "Capture.cs"
    path.write_text(TYPES + "class Host{" + body + "}")
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    (edge,) = capture_calls(result)
    assert edge["target"] == method(result, "Worker")["id"]


def test_req_qml022_ac06_capture_context_is_per_run_and_preserves_collector_inputs(tmp_path, monkeypatch):
    """The real Engine hook invokes one index without mutating the original inference tuples."""
    import graphify.extractors.csharp_lexical_calls as lexical
    path = tmp_path / "Capture.cs"
    path.write_text(source("var", nested=True))
    original, observations = lexical.CSharpLexicalCalls.capture_receiver_tables, []

    def observed(index, scopes, tables):
        before = deepcopy(tables)
        result = original(index, scopes, tables)
        assert tables == before and result is not tables
        observations.append(index)
        return result

    monkeypatch.setattr(lexical.CSharpLexicalCalls, "capture_receiver_tables", observed)
    first = extract_csharp(path)
    second = extract_csharp(path)
    assert len(observations) == 2 and observations[0] is not observations[1]
    assert first == second


def test_req_qml022_ac06_pre_capture_schema_cannot_replay_missing_receiver_proof(tmp_path, monkeypatch):
    """A successful predecessor-33 fragment misses after upgrade despite unchanged source bytes."""
    from graphify import cache
    path = tmp_path / "Capture.cs"
    path.write_bytes(source("var").encode())
    predecessor = extract_csharp(path)
    caller = local(predecessor)["id"]
    # Retain the predecessor's precise omission, not a malformed/error entry:
    # local ownership and all source facts stay intact, only capture typing lacks.
    for call in predecessor["raw_calls"]:
        if call["caller_nid"] == caller and call.get("callee") == "Run":
            call.pop("receiver_type", None)
    assert cache._AST_CACHE_SCHEMA > 33
    with monkeypatch.context() as old:
        old.setattr(cache, "_AST_CACHE_SCHEMA", 33)
        cache.save_cached(path, predecessor, tmp_path, cache_root=tmp_path)
        accepted = cache.load_cached(path, tmp_path, cache_root=tmp_path)
        assert accepted is not None and not accepted.get("error")
        assert not any(call.get("receiver_type") for call in accepted["raw_calls"] if call.get("callee") == "Run")
    state = path.read_bytes(), path.stat().st_mtime_ns
    cold = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    warm = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert cold == warm and (path.read_bytes(), path.stat().st_mtime_ns) == state
    assert capture_calls(warm)[0]["target"] == method(warm, "Worker")["id"]
