"""Neutral receiver captures keep class-method identity and actual local callers."""
import base64


TYPES = ('class Worker : System.IDisposable, System.IAsyncDisposable {'
         'public void Run(){} public void Dispose(){} '
         'public System.Threading.Tasks.ValueTask DisposeAsync()=>default;}'
         'class Other {public void Run(){}}')


def source(mode="parameter", *, nested=False, constructor=False):
    prefixes = {"parameter": "", "typed": "Worker worker=new Worker();",
                "var": "var worker=new Worker();", "using": "using var worker=new Worker();",
                "await_using": "await using var worker=new Worker();"}
    parameters = "Worker worker" if mode == "parameter" else ""
    header = (f"public Host({parameters})" if constructor else
              ("async System.Threading.Tasks.Task" if mode == "await_using" else "void") + f" Use({parameters})")
    local = "void Inner(){worker.Run();} Inner();"
    if nested:
        local = "void Outer(){" + local + "} Outer();"
    return TYPES + "class Host{" + header + "{" + prefixes[mode] + local + "}}"


def local(result, name="Inner"):
    nodes = [node for node in result["nodes"] if (fact := node.get("metadata", {}).get("csharp_local_function"))
             and base64.b64decode(fact["raw_name_b64"]).decode() == name]
    assert len(nodes) == 1
    return nodes[0]


def method(result, owner):
    identity, = [node["id"] for node in result["nodes"] if node["label"] == owner]
    targets = {edge["target"] for edge in result["edges"] if edge["source"] == identity and edge["relation"] == "method"}
    # Public graph assembly qualifies C# method display labels; the actual
    # source-owned class edge remains authoritative in both representations.
    node, = [node for node in result["nodes"] if node["id"] in targets and node["label"].rsplit(".", 1)[-1] == "Run()"]
    return node


def capture_calls(result):
    caller = local(result)["id"]
    return [edge for edge in result["edges"] if edge["source"] == caller and edge["relation"] == "calls"
            and edge["target"] in {method(result, owner)["id"] for owner in ("Worker", "Other")}]


def graph_payload(graph):
    return {"nodes": [{"id": identity, **data} for identity, data in graph.nodes(data=True)],
            "edges": [{"source": data.get("_src", source), "target": data.get("_tgt", target), **data}
                      for source, target, data in graph.edges(data=True)]}
