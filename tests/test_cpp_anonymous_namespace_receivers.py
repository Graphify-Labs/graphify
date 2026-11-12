"""Anonymous lexical lookup retains named parents without naming anonymous types."""
import importlib.util

import pytest

from graphify.extract import extract

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("tree_sitter_cpp") is None,
    reason="tree_sitter_cpp not installed",
)

HEADER = """
namespace app {
struct Worker { void Run(); static void StaticRun(); };
struct Client { Worker* worker; };
}
"""


def _extract(tmp_path, body, header=HEADER):
    paths = [tmp_path / "types.hpp", tmp_path / "use.cpp"]
    paths[0].write_text(header, encoding="utf-8")
    paths[1].write_text('#include "types.hpp"\n' + body, encoding="utf-8")
    return extract(paths, root=tmp_path, cache_root=tmp_path / "cache", parallel=False)


def _calls(result):
    nodes = {n["id"]: n for n in result["nodes"]}
    return {(nodes[e["target"]]["label"], nodes[e["target"]]["source_file"])
            for e in result["edges"] if e["relation"] == "calls"
            and nodes[e["source"]]["label"] == "Tick()"}


@pytest.mark.parametrize("body,expected", [
    ("void Tick(Client& c) { c.worker->Run(); }", {(".Run()", "types.hpp")}),
    ("void Tick() { Worker::StaticRun(); }", {(".StaticRun()", "types.hpp")}),
    ("void Tick(app::Client& c) { c.worker->Run(); }", {(".Run()", "types.hpp")}),
])
def test_named_parent_lookup_survives_an_anonymous_namespace(tmp_path, body, expected):
    result = _extract(tmp_path, f"namespace app {{ namespace {{ {body} }} }}")
    assert _calls(result) == expected


@pytest.mark.parametrize("declaration", ["struct Client;", "struct Client { Worker* worker; };",
                                         "using Client = Missing;"])
def test_anonymous_declarations_block_outer_receiver_types(tmp_path, declaration):
    result = _extract(tmp_path, f"""
namespace app {{ namespace {{
{declaration}
void Tick(Client& c) {{ c.worker->Run(); }}
}} }}
""")
    assert _calls(result) == set()


def test_reopened_anonymous_namespaces_share_shadowing(tmp_path):
    result = _extract(tmp_path, """
namespace app {
namespace { struct Client; }
namespace { void Tick(Client& c) { c.worker->Run(); } }
}
""")
    assert _calls(result) == set()


def test_an_anonymous_type_blocks_an_outer_static_receiver(tmp_path):
    result = _extract(tmp_path, """
namespace app { namespace {
struct Worker;
void Tick() { Worker::StaticRun(); }
} }
""")
    assert _calls(result) == set()


def test_anonymous_class_identities_remain_unknown(tmp_path):
    result = _extract(tmp_path, """
namespace app { namespace {
struct Local { void Run(); };
void Tick(Local& c) { c.Run(); }
} }
""")
    assert _calls(result) == set()
    assert all(not n.get("_cpp_qualified") for n in result["nodes"] if n["label"] == "Local")


def test_a_later_member_alias_in_an_anonymous_class_scope_blocks_outer_lookup(tmp_path):
    result = _extract(tmp_path, """
namespace app { namespace {
struct Local { void Tick() { Client c; c.worker->Run(); } using Client = Missing; };
} }
""")
    nodes = {n["id"]: n for n in result["nodes"]}
    assert not any(e["relation"] == "calls" and nodes[e["source"]]["label"] == ".Tick()"
                   for e in result["edges"])


@pytest.mark.parametrize("nested", [False, True])
def test_anonymous_aliases_block_outer_fallthrough_after_the_wrapper(tmp_path, nested):
    declaration = "namespace { using Client = Other; }"
    if nested:
        declaration = "namespace { " + declaration + " }"
    result = _extract(tmp_path, "namespace app { " + declaration
                      + " void Tick(Client& c) { c.worker->Run(); } }", header="""
struct Worker { void Run(); }; struct OtherWorker { void Run(); };
struct Client { Worker* worker; }; struct Other { OtherWorker* worker; };
""")
    assert _calls(result) == set()


def test_qualified_parent_access_bypasses_anonymous_alias_barriers(tmp_path):
    result = _extract(tmp_path, """
namespace app { namespace {
using Client = Missing;
void Tick(::app::Client& c) { c.worker->Run(); }
} }
""")
    assert _calls(result) == {(".Run()", "types.hpp")}
