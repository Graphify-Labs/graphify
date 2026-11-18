"""Private, single-server UI and MCP endpoint for Graphify."""
from __future__ import annotations

import argparse
import asyncio
import contextvars
import getpass
import json
import os
import shutil
import threading
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from graphify.pilot_store import SESSION_SECONDS, UPLOAD_LIMIT, PilotError, Store, run_graphify, work

_UI = Path(__file__).with_name("pilot_ui")
_COOKIE = "graphify_pilot"
_ACTIONS = {
    "query": (["query"], 1),
    "explain": (["explain"], 1),
    "path": (["path"], 2),
    "affected": (["affected"], 1),
    "section": (["section"], 1),
    "god-nodes": (["god-nodes"], 0),
    "benchmark": (["benchmark"], 0),
    "diagnose": (["diagnose", "multigraph"], 0),
}
_ARTIFACTS = {
    "preview": ("pilot-preview.json", "application/json", False),
    "report": ("GRAPH_REPORT.md", "text/plain", False),
    "markdown": ("GRAPH_REPORT.md", "text/markdown", True),
    "json": ("graph.json", "application/json", True),
    "html": ("graph.html", "text/html", True),
    "graphml": ("graph.graphml", "application/xml", True),
    "callflow": ("callflow.html", "text/html", True),
    "tree": ("tree.html", "text/html", True),
    "obsidian": ("obsidian.zip", "application/zip", True),
    "wiki": ("wiki.zip", "application/zip", True),
    "cypher": ("cypher.txt", "text/plain", True),
    "svg": ("graph.svg", "image/svg+xml", True),
}
_EXPORTS = {
    "graphml": ["export", "graphml"],
    "callflow": ["export", "callflow-html", "--output", "graphify-out/callflow.html"],
    "tree": ["tree", "--output", "graphify-out/tree.html"],
    "obsidian": ["export", "obsidian", "--dir", "graphify-out/obsidian"],
    "wiki": ["export", "wiki"],
    "cypher": ["export", "neo4j"],
    "svg": ["export", "svg"],
}


def create_app(data_directory: Path, origin: str):
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
    from mcp.server.transport_security import TransportSecuritySettings
    from starlette.applications import Starlette
    from starlette.concurrency import run_in_threadpool
    from starlette.datastructures import Headers
    from starlette.responses import FileResponse, JSONResponse, Response
    from starlette.routing import Route

    from graphify.serve import ToolError, _build_server

    address = urlsplit(origin)
    if (address.scheme not in {"http", "https"} or not address.hostname or address.username
            or address.path not in ("", "/") or address.query or address.fragment):
        raise ValueError("Origin phải có dạng http(s)://hostname[:port].")
    authority = address.netloc.lower()
    origin = f"{address.scheme}://{authority}"
    secure_cookie = address.scheme == "https"
    store = Store(data_directory)
    selected_graph: contextvars.ContextVar[str] = contextvars.ContextVar("pilot_graph")
    stop = threading.Event()
    wake = threading.Event()
    query_slots = threading.BoundedSemaphore(2)
    export_lock = threading.Lock()
    login_attempts = defaultdict(deque)

    def request_graph() -> str:
        try:
            return selected_graph.get()
        except LookupError:
            raise ToolError("No project selected for this request.") from None

    manager = StreamableHTTPSessionManager(
        app=_build_server("", request_graph=request_graph), stateless=True, json_response=True,
        security_settings=TransportSecuritySettings(
            allowed_hosts=[authority], allowed_origins=[origin],
        ),
    )

    @asynccontextmanager
    async def lifespan(_app):
        stop.clear()
        store.recover_interrupted()
        worker = threading.Thread(target=work, args=(store, stop, wake), daemon=True)
        async with manager.run():
            worker.start()
            try:
                yield
            finally:
                stop.set()
                wake.set()
                await asyncio.to_thread(worker.join, 10)

    def user(request, *, admin: bool = False):
        cookie = request.cookies.get(_COOKIE, "")
        current = store.session_user(cookie) if cookie and len(cookie) <= 100 else None
        if current is None:
            raise PilotError("Vui lòng đăng nhập.", 401)
        if admin and not current["admin"]:
            raise PilotError("Bạn không có quyền quản trị.", 403)
        return current

    def project(request, *, ready=False):
        current = user(request)
        row = store.owned_project(current["id"], request.path_params["project_id"])
        if ready and row["status"] != "ready":
            raise PilotError("Đồ thị chưa sẵn sàng.", 409)
        return row

    async def data(request):
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > 8192:
                raise PilotError("Yêu cầu quá lớn.", 413)
            body.extend(chunk)
        try:
            payload = json.loads(body)
        except (ValueError, UnicodeError) as exc:
            raise PilotError("Dữ liệu không hợp lệ.") from exc
        if not isinstance(payload, dict):
            raise PilotError("Dữ liệu không hợp lệ.")
        return payload

    async def login(request):
        now = time.monotonic()
        for key, visits in list(login_attempts.items()):
            while visits and now - visits[0] > 60:
                visits.popleft()
            if not visits:
                del login_attempts[key]
        client = request.client.host if request.client else ""
        attempts = login_attempts[client]
        if len(attempts) >= 10:
            raise PilotError("Quá nhiều lần thử. Hãy đợi một phút.", 429)
        attempts.append(now)
        payload = await data(request)
        session = await run_in_threadpool(store.login, payload.get("username"), payload.get("password"))
        response = JSONResponse({"ok": True})
        response.set_cookie(_COOKIE, session, max_age=SESSION_SECONDS,
                            httponly=True, samesite="strict", secure=secure_cookie)
        return response

    async def logout(request):
        cookie = request.cookies.get(_COOKIE, "")
        if cookie and len(cookie) <= 100:
            store.logout(cookie)
        response = Response(status_code=204)
        response.delete_cookie(_COOKIE, httponly=True, samesite="strict", secure=secure_cookie)
        return response

    async def me(request):
        current = user(request)
        return JSONResponse({"username": current["username"], "admin": bool(current["admin"])})

    async def projects(request):
        current = user(request)
        if request.method == "GET":
            return JSONResponse([dict(row) for row in store.list_projects(current["id"])])
        title = request.query_params.get("title", "").strip()
        if not 1 <= len(title) <= 100 or any(ord(c) < 32 for c in title):
            raise PilotError("Tên dự án phải dài từ 1 đến 100 ký tự.")
        if request.headers.get("content-type") != "application/zip":
            raise PilotError("Hãy chọn một file ZIP.", 415)
        project_id = uuid.uuid4().hex
        directory = store.projects / project_id
        directory.mkdir(mode=0o700)
        registered = False
        try:
            size = 0
            with (directory / "upload.zip").open("xb") as archive:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > UPLOAD_LIMIT:
                        raise PilotError("File ZIP vượt giới hạn 50 MB.", 413)
                    archive.write(chunk)
            if size == 0:
                raise PilotError("File ZIP trống.")
            store.submit(current["id"], title, project_id)
            registered = True
        finally:
            if not registered:
                shutil.rmtree(directory, ignore_errors=True)
        wake.set()
        return JSONResponse({"id": project_id}, status_code=202)

    async def delete_project(request):
        current = user(request)
        await run_in_threadpool(store.delete, current["id"], request.path_params["project_id"])
        return Response(status_code=204)

    async def issue_token(request):
        current = user(request)
        project_id = request.path_params["project_id"]
        token = store.token(current["id"], project_id, revoke=request.method == "DELETE")
        if token is None:
            return Response(status_code=204)
        return JSONResponse({"token": token, "url": f"{origin}/mcp/{project_id}"})

    def run_action(row, name, values):
        args, _ = _ACTIONS[name]
        graph = store.graph(row["id"])
        if not query_slots.acquire(blocking=False):
            raise PilotError("Đang có truy vấn khác. Hãy thử lại.", 429)
        try:
            if name == "benchmark":
                command = [*args, str(graph)]
            else:
                command = [*args, *values, "--graph", str(graph)]
            status, output = run_graphify(command, graph.parents[1])
        finally:
            query_slots.release()
        return {"status": status, "output": output.strip()}

    async def actions(request):
        row = project(request, ready=True)
        payload = await data(request)
        action, values = payload.get("action"), payload.get("values")
        if not isinstance(action, str) or action not in _ACTIONS or not isinstance(values, list):
            raise PilotError("Tác vụ không hợp lệ.")
        if len(values) != _ACTIONS[action][1] or any(
            not isinstance(value, str) or not value.strip() or len(value) > 1000
            or value.lstrip().startswith("-") or "\x00" in value for value in values
        ):
            raise PilotError("Hãy nhập đủ tên hoặc câu hỏi hợp lệ.")
        return JSONResponse(await run_in_threadpool(run_action, row, action, values))

    def export(row, kind, target):
        if not export_lock.acquire(blocking=False):
            raise PilotError("Đang xuất một báo cáo khác. Hãy thử lại.", 429)
        try:
            if target.is_file():
                return
            graph = store.graph(row["id"])
            args = [*_EXPORTS[kind], "--graph", str(graph)]
            status, _ = run_graphify(args, graph.parents[1], timeout=60)
            if not status and kind in {"obsidian", "wiki"}:
                folder = target.with_suffix("")
                if folder.is_dir():
                    temporary = target.with_suffix(".partial")
                    result = shutil.make_archive(str(temporary), "zip", folder)
                    Path(result).replace(target)
                    shutil.rmtree(folder)
            if status or not target.is_file():
                raise PilotError("Graphify không xuất được định dạng này cho đồ thị hiện tại.", 422)
        finally:
            export_lock.release()

    async def artifact(request):
        row = project(request, ready=True)
        kind = request.path_params["artifact"]
        if kind not in _ARTIFACTS:
            raise PilotError("Không tìm thấy tệp.", 404)
        name, media, download = _ARTIFACTS[kind]
        target = store.graph(row["id"]).with_name(name)
        if not target.is_file() and kind in _EXPORTS:
            await run_in_threadpool(export, row, kind, target)
        if not target.is_file():
            raise PilotError("Không tìm thấy tệp.", 404)
        return FileResponse(target, media_type=media, filename=name if download else None)

    async def admin_users(request):
        user(request, admin=True)
        if request.method == "GET":
            return JSONResponse(store.dashboard())
        payload = await data(request)
        await run_in_threadpool(store.create_user, payload.get("username"), payload.get("password"))
        return Response(status_code=201)

    async def admin_update(request):
        user(request, admin=True)
        payload = await data(request)
        await run_in_threadpool(store.change_user, request.path_params["user_id"],
                                active=payload.get("active"), password=payload.get("password"))
        return Response(status_code=204)

    async def assets(request):
        name = request.path_params.get("name", "index.html")
        content_types = {"index.html": "text/html", "app.js": "text/javascript", "style.css": "text/css"}
        if name not in content_types:
            raise PilotError("Không tìm thấy tệp.", 404)
        return FileResponse(_UI / name, media_type=content_types[name])

    class MCP:
        async def __call__(self, scope, receive, send):
            headers = Headers(scope=scope)
            project_id = scope["path_params"]["project_id"]
            scheme, _, token = headers.get("authorization", "").partition(" ")
            if (scheme.lower() != "bearer" or not 1 <= len(token) <= 100
                    or store.token_project(token, project_id) is None):
                error = JSONResponse({"error": "Unauthorized"}, status_code=401,
                                     headers={"WWW-Authenticate": "Bearer"})
                await error(scope, receive, send)
                return
            context = selected_graph.set(str(store.graph(project_id)))
            try:
                await manager.handle_request(scope, receive, send)
            finally:
                selected_graph.reset(context)

    async def error_handler(_request, exc):
        return JSONResponse({"error": str(exc)}, status_code=exc.status)

    app = Starlette(
        lifespan=lifespan, exception_handlers={PilotError: error_handler},
        routes=[
            Route("/", assets), Route("/assets/{name}", assets),
            Route("/api/login", login, methods=["POST"]), Route("/api/logout", logout, methods=["POST"]),
            Route("/api/me", me), Route("/api/projects", projects, methods=["GET", "POST"]),
            Route("/api/projects/{project_id}", delete_project, methods=["DELETE"]),
            Route("/api/projects/{project_id}/token", issue_token, methods=["POST", "DELETE"]),
            Route("/api/projects/{project_id}/actions", actions, methods=["POST"]),
            Route("/api/projects/{project_id}/files/{artifact}", artifact),
            Route("/api/admin/users", admin_users, methods=["GET", "POST"]),
            Route("/api/admin/users/{user_id:int}", admin_update, methods=["PATCH"]),
            Route("/mcp/{project_id}", MCP()),
        ],
    )

    async def gateway(scope, receive, send):
        if scope["type"] != "http":
            await app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        request_origin = headers.get("origin")
        if headers.get("host", "").lower() != authority or (request_origin and request_origin != origin):
            await JSONResponse({"error": "Host hoặc Origin không hợp lệ."}, status_code=403)(scope, receive, send)
            return
        if (scope["path"].startswith("/api/") and scope["method"] not in {"GET", "HEAD"}
                and headers.get("x-graphify-request") != "1"):
            await JSONResponse({"error": "Yêu cầu web không hợp lệ."}, status_code=403)(scope, receive, send)
            return

        async def secured(message):
            if message["type"] == "http.response.start":
                message["headers"] = [
                    *message.get("headers", []),
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"content-security-policy",
                     b"default-src 'self'; script-src 'self'; style-src 'self'; "
                     b"object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"),
                ]
            await send(message)

        await app(scope, receive, secured)

    return gateway


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path(".graphify/pilot"))
    actions = parser.add_subparsers(dest="command", required=True)
    admin = actions.add_parser("init-admin", help="Create an administrator from the server terminal")
    admin.add_argument("username")
    serve = actions.add_parser("serve", help="Start the internal web UI and MCP gateway")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--origin", help="Public origin, including scheme and port if present")
    args = parser.parse_args()
    os.umask(0o077)
    try:
        if args.command == "init-admin":
            password = getpass.getpass("Mật khẩu quản trị: ")
            if password != getpass.getpass("Nhập lại mật khẩu: "):
                raise PilotError("Mật khẩu nhập lại không khớp.")
            Store(args.data_dir).setup_admin(args.username, password)
            print(f"Đã tạo quản trị viên {args.username}.")
            return
        import fcntl

        import uvicorn

        if args.host != "127.0.0.1" and not args.origin:
            parser.error("Thêm --origin với URL nội bộ khi lắng nghe trên mạng.")
        origin = args.origin or f"http://127.0.0.1:{args.port}"
        args.data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        with (args.data_dir / ".server.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                parser.error("Một tiến trình pilot đang sử dụng thư mục dữ liệu này.")
            uvicorn.run(create_app(args.data_dir, origin), host=args.host, port=args.port,
                        access_log=False, timeout_graceful_shutdown=10, limit_concurrency=32)
    except ImportError as exc:
        parser.exit(1, f"Cài Graphify với nhóm phụ thuộc MCP: pip install '.[mcp]' ({exc})\n")
    except (PilotError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
