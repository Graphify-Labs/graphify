"""ASP.NET routing attributes become queryable route nodes.

The C# extractor records that a method carries `[HttpGet]` — as a
`references[attribute]` edge to the attribute's type — but discards the
attribute's argument, so the route template itself never reaches the graph.
These tests pin the behaviour that makes a route findable: the template is
captured, the controller-level `[Route]` prefix composes with the method-level
one, and the result is a node whose *label* is the route (the only field
`serve.py` indexes for search).
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _routes(result: dict) -> dict[str, dict]:
    """Route nodes by label — the ones a method points at with context='route'."""
    by_id = {n["id"]: n for n in result["nodes"]}
    out = {}
    for e in result["edges"]:
        if e.get("relation") == "references" and e.get("context") == "route":
            node = by_id.get(e.get("target"))
            if node is not None:
                out[node["label"]] = node
    return out


def _route_source(result: dict, label: str) -> str | None:
    """Label of the method that serves ``label``."""
    by_id = {n["id"]: n for n in result["nodes"]}
    for e in result["edges"]:
        if e.get("relation") == "references" and e.get("context") == "route":
            if by_id.get(e.get("target"), {}).get("label") == label:
                return by_id.get(e.get("source"), {}).get("label")
    return None


def test_method_route_template_becomes_a_node(tmp_path: Path):
    """`[HttpGet("Status")]` on a method yields a route node labelled with the verb
    and the template — today the template is dropped entirely."""
    f = _write(
        tmp_path / "c.cs",
        "namespace N {\n"
        "  public class ServerController {\n"
        '    [HttpGet("Status")]\n'
        "    public int GetStatus() { return 1; }\n"
        "  }\n"
        "}\n",
    )
    result = extract([f], cache_root=tmp_path)
    assert "GET Status" in _routes(result), (
        f"no route node; got {sorted(_routes(result))}"
    )


def test_controller_route_prefix_composes_with_the_method_template(tmp_path: Path):
    """A class-level `[Route]` is the endpoint's prefix. Class attributes are not
    collected at all today, so the prefix is missing even in principle."""
    f = _write(
        tmp_path / "c.cs",
        "namespace N {\n"
        '  [Route("api/Presence")]\n'
        "  public class PresenceController {\n"
        '    [HttpPost("Add")]\n'
        "    public int Add() { return 1; }\n"
        "  }\n"
        "}\n",
    )
    result = extract([f], cache_root=tmp_path)
    assert "POST api/Presence/Add" in _routes(result), (
        f"prefix not composed; got {sorted(_routes(result))}"
    )


def test_route_node_points_back_at_its_handler(tmp_path: Path):
    """The point of the node: from the route you reach the controller method."""
    f = _write(
        tmp_path / "c.cs",
        "namespace N {\n"
        '  [Route("api/Presence")]\n'
        "  public class PresenceController {\n"
        '    [HttpGet("MobileAccess/{mobileAccessId}")]\n'
        "    public int GetMobileAccess(string mobileAccessId) { return 1; }\n"
        "  }\n"
        "}\n",
    )
    result = extract([f], cache_root=tmp_path)
    label = "GET api/Presence/MobileAccess/{mobileAccessId}"
    assert _route_source(result, label) is not None, (
        f"route node has no handler; got {sorted(_routes(result))}"
    )
    assert "GetMobileAccess" in str(_route_source(result, label))


def test_verb_attribute_and_route_attribute_on_the_same_method(tmp_path: Path):
    """The dominant style in large ASP.NET codebases: a bare `[HttpGet]` for the
    verb and a separate `[Route]` for the path."""
    f = _write(
        tmp_path / "c.cs",
        "namespace N {\n"
        '  [Route("account")]\n'
        "  public class AccountController {\n"
        "    [HttpGet]\n"
        '    [Route("login")]\n'
        "    public int Login() { return 1; }\n"
        "  }\n"
        "}\n",
    )
    result = extract([f], cache_root=tmp_path)
    assert "GET account/login" in _routes(result), (
        f"verb and path came from different attributes; got {sorted(_routes(result))}"
    )


def test_absolute_method_template_ignores_the_controller_prefix(tmp_path: Path):
    """ASP.NET rule: a template starting with '/' or '~/' is absolute."""
    f = _write(
        tmp_path / "c.cs",
        "namespace N {\n"
        '  [Route("api/Presence")]\n'
        "  public class PresenceController {\n"
        '    [HttpGet("/health")]\n'
        "    public int Health() { return 1; }\n"
        "  }\n"
        "}\n",
    )
    result = extract([f], cache_root=tmp_path)
    assert "GET /health" in _routes(result), (
        f"absolute template was prefixed; got {sorted(_routes(result))}"
    )


def test_controller_token_expands_to_the_controller_name(tmp_path: Path):
    """`[controller]` is the conventional token for the class name minus the
    'Controller' suffix."""
    f = _write(
        tmp_path / "c.cs",
        "namespace N {\n"
        '  [Route("api/[controller]")]\n'
        "  public class RuleSetController {\n"
        "    [HttpGet]\n"
        "    public int GetAll() { return 1; }\n"
        "  }\n"
        "}\n",
    )
    result = extract([f], cache_root=tmp_path)
    assert "GET api/RuleSet" in _routes(result), (
        f"[controller] token not expanded; got {sorted(_routes(result))}"
    )


def test_route_node_is_anchored_to_the_controller_file(tmp_path: Path):
    """A route node must carry a real source_file: it is a code artifact, not a
    sourceless stub, and `serve.py` indexes source_file alongside the label."""
    f = _write(
        tmp_path / "c.cs",
        "namespace N {\n"
        "  public class ServerController {\n"
        '    [HttpGet("Status")]\n'
        "    public int GetStatus() { return 1; }\n"
        "  }\n"
        "}\n",
    )
    result = extract([f], cache_root=tmp_path)
    node = _routes(result).get("GET Status")
    assert node is not None
    assert node.get("source_file", "").endswith("c.cs")
    assert node.get("file_type") == "code"


def test_route_without_a_verb_attribute_matches_every_verb(tmp_path: Path):
    """A bare `[Route]` with no `Http*` sibling is verb-agnostic in ASP.NET; the
    label says so with `*` rather than guessing a verb."""
    f = _write(
        tmp_path / "c.cs",
        "namespace N {\n"
        "  public class AnyController {\n"
        '    [Route("api/any")]\n'
        "    public int Any() { return 1; }\n"
        "  }\n"
        "}\n",
    )
    result = extract([f], cache_root=tmp_path)
    assert "* api/any" in _routes(result), (
        f"verb-less route not labelled '*'; got {sorted(_routes(result))}"
    )


def test_a_method_without_routing_attributes_mints_no_route_node(tmp_path: Path):
    """Only routing attributes produce route nodes — `[Obsolete("...")]` must not."""
    f = _write(
        tmp_path / "c.cs",
        "namespace N {\n"
        "  public class Plain {\n"
        '    [Obsolete("gone")]\n'
        "    public int Old() { return 1; }\n"
        "  }\n"
        "}\n",
    )
    result = extract([f], cache_root=tmp_path)
    assert _routes(result) == {}
