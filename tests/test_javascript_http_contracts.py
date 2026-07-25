from pathlib import Path

from graphify.extract import extract


def test_links_literal_fetch_to_conditional_node_route(tmp_path: Path):
    server = tmp_path / "server.js"
    client = tmp_path / "client.js"
    server.write_text('if (request.method === "GET" && requestUrl.pathname === "/api/overview") {}')
    client.write_text('async function load() { return fetch("/api/overview"); }')

    result = extract([server, client], cache_root=tmp_path, parallel=False)
    endpoint = "http_get_api_overview"
    assert any(node["id"] == endpoint for node in result["nodes"])
    assert any(edge["source"] == endpoint and edge["relation"] == "implements" for edge in result["edges"])
    assert any(edge["target"] == endpoint and edge["relation"] == "calls" for edge in result["edges"])


def test_ignores_dynamic_client_routes(tmp_path: Path):
    client = tmp_path / "client.js"
    client.write_text('fetch(`/api/projects/${id}`)')
    result = extract([client], cache_root=tmp_path, parallel=False)
    assert not [node for node in result["nodes"] if node["id"].startswith("http_")]
