import io
import json
import stat
import time
import zipfile
from pathlib import Path

import pytest

from graphify.pilot_store import PilotError, Store, unpack


def _zip(name="repo/demo.py", value="def example():\n    return 42\n"):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name, value)
        archive.writestr("repo/README.md", "# Guide\n\nThe sample documentation.\n")
    return stream.getvalue()


@pytest.mark.parametrize("name", ["../escaped.py", "/etc/hidden.py", "repo\\..\\other.py", "C:/elsewhere.py"])
def test_pilot_rejects_zip_paths(tmp_path, name):
    archive = tmp_path / "file.zip"
    archive.write_bytes(_zip(name))
    with pytest.raises(PilotError, match="đường dẫn"):
        unpack(archive, tmp_path / "work")


def test_pilot_rejects_zip_symlinks_and_excludes_supplied_graph(tmp_path):
    archive = tmp_path / "file.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        item = zipfile.ZipInfo("repo/elsewhere")
        item.create_system = 3
        item.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(item, "../elsewhere")
    with pytest.raises(PilotError, match="thông thường"):
        unpack(archive, tmp_path / "unsafe")

    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("repo/graphify-out/graph.json", "{}")
        zf.writestr("repo/.env", "SECRET=ignored")
        zf.writestr("repo/file.py", "import os")
    unpack(archive, tmp_path / "safe")
    assert sorted(path.name for path in (tmp_path / "safe" / "repo").iterdir()) == ["file.py"]


def test_pilot_private_projects_and_mcp_over_http(tmp_path):
    pytest.importorskip("mcp")
    pytest.importorskip("starlette")
    from starlette.testclient import TestClient

    from graphify.pilot import create_app

    store = Store(tmp_path)
    store.setup_admin("admin", "admin-test-password")
    base_url = "http://pilot.internal"
    base_headers = {"X-Graphify-Request": "1"}
    with TestClient(create_app(tmp_path, base_url), base_url=base_url, headers=base_headers) as client:
        def login(username, password):
            response = client.post("/api/login", json={"username": username, "password": password})
            assert response.status_code == 200

        def upload(title, symbol):
            response = client.post("/api/projects", params={"title": title},
                                   content=_zip(value=f"def {symbol}():\n    return 42\n"),
                                   headers={"Content-Type": "application/zip"})
            assert response.status_code == 202, response.text
            project_id = response.json()["id"]
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline:
                current = next(row for row in client.get("/api/projects").json() if row["id"] == project_id)
                if current["status"] == "ready":
                    return project_id
                assert current["status"] != "failed", current["detail"]
                time.sleep(0.08)
            pytest.fail("Pilot analysis did not finish")

        def token(project):
            response = client.post(f"/api/projects/{project}/token")
            assert response.status_code == 200
            return response.json()["token"]

        def rpc(project, access, method, **params):
            return client.post(f"/mcp/{project}", json={
                "jsonrpc": "2.0", "id": 1, "method": method, "params": params,
            }, headers={"Authorization": f"Bearer {access}", "Accept": "application/json, text/event-stream"})

        assert client.get("/").status_code == 200
        assert client.get("/assets/app.js").status_code == 200
        assert client.get("/api/projects").status_code == 401
        assert client.post("/api/login", headers={"X-Graphify-Request": ""}).status_code == 403
        assert client.get("/api/me", headers={"Origin": "http://another.internal"}).status_code == 403
        login("admin", "admin-test-password")
        for username in ("alice", "bobby"):
            assert client.post("/api/admin/users", json={
                "username": username, "password": "provided-password",
            }).status_code == 201

        login("alice", "provided-password")
        alice = upload("Alice's repo", "first_symbol")
        alice_token = token(alice)
        prefix = f"/api/projects/{alice}"
        report = client.get(f"{prefix}/files/report")
        assert report.status_code == 200
        assert client.get(f"{prefix}/files/preview").json()["counts"]["nodes"] > 0
        assert client.post(f"{prefix}/actions", json={"action": "query", "values": ["first_symbol"]}).status_code == 200
        explanation = client.post(f"{prefix}/actions", json={"action": "explain", "values": ["first_symbol"]}).json()
        assert explanation["status"] == 0 and "first_symbol()" in explanation["output"]
        for action, values in [("affected", ["first_symbol"]), ("god-nodes", []), ("benchmark", []), ("diagnose", [])]:
            result = client.post(f"{prefix}/actions", json={"action": action, "values": values}).json()
            assert result["status"] == 0, (action, result)
        section = client.post(f"{prefix}/actions", json={"action": "section", "values": ["Guide"]}).json()
        assert section["status"] == 0 and "sample documentation" in section["output"]
        for kind in ("json", "html", "graphml", "callflow", "tree", "obsidian", "wiki", "cypher"):
            response = client.get(f"{prefix}/files/{kind}")
            assert response.status_code == 200, (kind, response.text[:500])
            assert "attachment" in response.headers["content-disposition"]

        init = rpc(alice, alice_token, "initialize", protocolVersion="2025-03-26",
                   capabilities={}, clientInfo={"name": "pilot-test", "version": "1"})
        assert init.status_code == 200, init.text
        tools = rpc(alice, alice_token, "tools/list").json()["result"]["tools"]
        assert "query_graph" in {tool["name"] for tool in tools}
        assert all("project_path" not in tool["inputSchema"]["properties"] for tool in tools)
        section = rpc(alice, alice_token, "tools/call", name="get_section", arguments={"label": "Guide"})
        assert "sample documentation" in section.json()["result"]["content"][0]["text"]

        login("bobby", "provided-password")
        bobby = upload("Bobby's repo", "second_symbol")
        bobby_token = token(bobby)
        assert [row["id"] for row in client.get("/api/projects").json()] == [bobby]
        assert client.get(f"{prefix}/files/preview").status_code == 404
        assert client.post(f"{prefix}/token").status_code == 404
        assert client.get("/api/admin/users").status_code == 403
        assert rpc(alice, bobby_token, "tools/list").status_code == 401
        for project, credential, label in [(alice, alice_token, "first_symbol"), (bobby, bobby_token, "second_symbol")]:
            response = rpc(project, credential, "tools/call", name="get_node", arguments={"label": label})
            assert label in response.json()["result"]["content"][0]["text"]
        result = rpc(alice, alice_token, "tools/call", name="get_node", arguments={
            "label": "second_symbol", "project_path": str(store.graph(bobby).parents[1]),
        }).json()
        assert "second_symbol()" not in json.dumps(result)
        assert result.get("error") or result["result"].get("isError")
        assert "Graph Report" in rpc(alice, alice_token, "resources/list").text
        resource = rpc(alice, alice_token, "resources/read", uri="graphify://report")
        assert resource.json()["result"]["contents"][0]["text"] == report.text

        with store.db() as db:
            owner = db.execute("SELECT id FROM users WHERE username='bobby'").fetchone()["id"]
        login("admin", "admin-test-password")
        assert client.patch(f"/api/admin/users/{owner}", json={"active": False}).status_code == 204
        assert rpc(bobby, bobby_token, "tools/list").status_code == 401
        assert client.post("/api/login", json={"username": "bobby", "password": "provided-password"}).status_code == 401

        login("alice", "provided-password")
        assert client.delete(f"{prefix}/token").status_code == 204
        assert rpc(alice, alice_token, "tools/list").status_code == 401
        assert client.delete(prefix).status_code == 204
        assert not Path(store.graph(alice)).exists()
