"""Neutral callback declarations expose only source-owned rejection facts."""
from graphify.extract import extract, extract_cpp
from graphify.extractors.cpp_functions import decoded, free_definition_fact
from graphify.extractors.cpp_member_identity import member_fact


def source(body, *, member=False, parameter=""):
    prefix = "void helper(){} void helper(int value){} void other(){} bool keep(){return false;}\n"
    if member:
        return (prefix + "class Panel{public:void run(" + parameter + ");};\n"
                "void Panel::run(" + parameter + "){" + body + "}\n")
    return prefix + "void use(" + parameter + "){" + body + "}\n"


def caller(result):
    bodies = [node for node in result["nodes"] if member_fact(node).get("role") == "definition"]
    if bodies:
        assert len(bodies) == 1
        return bodies[0]
    nodes = [node for node in result["nodes"] if decoded(free_definition_fact(node).get("qualified_name_b64")) == "use"]
    if not nodes:
        nodes = [node for node in result["nodes"] if member_fact(node).get("role") == "declaration"]
    assert len(nodes) == 1
    return nodes[0]


def helper_edges(result):
    identity = caller(result)["id"]
    targets = {node["id"] for node in result["nodes"] if node["label"] == "helper()"
               and free_definition_fact(node)}
    return [edge for edge in result["edges"] if edge["source"] == identity
            and edge["target"] in targets and edge["relation"] == "calls"]


def callback_sites(result):
    identity = caller(result)["id"]
    return [call for call in result.get("raw_calls", []) if call.get("caller_nid") == identity
            and call.get("callee") == "helper" and call.get("cpp_free_call")]


def extracted(path):
    direct = extract_cpp(path)
    assert not direct.get("error")
    cold = extract([path], root=path.parent, cache_root=path.parent, parallel=False)
    warm = extract([path], root=path.parent, cache_root=path.parent, parallel=False)
    assert cold == warm and not cold["failed_sources"] and not cold["qml_failures"]
    return direct, cold


def payload(graph):
    return {"nodes": [{"id": identity, **data} for identity, data in graph.nodes(data=True)],
            "edges": [{"source": data.get("_src", source), "target": data.get("_tgt", target), **data}
                      for source, target, data in graph.edges(data=True)]}
