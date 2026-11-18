"""Persistence and offline jobs for the single-server Graphify pilot."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import signal
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import zipfile
from collections import Counter
from contextlib import closing, contextmanager
from pathlib import Path, PurePosixPath

from graphify.security import redact_secrets

MIB = 1024 * 1024
UPLOAD_LIMIT = 50 * MIB
UNPACK_LIMIT = 250 * MIB
FILE_LIMIT = 16 * MIB
GRAPH_LIMIT = 64 * MIB
SESSION_SECONDS = 12 * 3600
TOKEN_SECONDS = 30 * 86400
PROJECT_LIMIT = 10

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL,
    admin INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS sessions (
    digest TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    expires INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    owner_id INTEGER NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    created INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS projects_by_owner ON projects(owner_id, created);
CREATE INDEX IF NOT EXISTS projects_by_status ON projects(status, created);
CREATE TABLE IF NOT EXISTS tokens (
    project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    digest TEXT NOT NULL UNIQUE,
    expires INTEGER NOT NULL
);
"""


class PilotError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    key = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=32768,
                         r=8, p=1, maxmem=64 * MIB)
    return f"{salt}:{key.hex()}"


def _validated_password(password: object) -> str:
    if not isinstance(password, str) or not 10 <= len(password) <= 128:
        raise PilotError("Mật khẩu phải dài từ 10 đến 128 ký tự.")
    return _password_hash(password)


def _digest(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


class Store:
    def __init__(self, directory: Path):
        self.directory = directory.resolve()
        self.projects = self.directory / "projects"
        self.projects.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.db_path = self.directory / "pilot.sqlite3"
        with self.db() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)

    @contextmanager
    def db(self):
        with closing(sqlite3.connect(self.db_path)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            yield db

    def setup_admin(self, username: str, password: str) -> None:
        self.create_user(username, password, admin=True)

    def create_user(self, username: object, password: object, *, admin: bool = False) -> None:
        if not isinstance(username, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,39}", username):
            raise PilotError("Tên tài khoản gồm 3–40 ký tự thường, số, dấu chấm, gạch ngang hoặc gạch dưới.")
        hashed = _validated_password(password)
        try:
            with self.db() as db:
                db.execute("INSERT INTO users (username, password, admin) VALUES (?,?,?)",
                           (username, hashed, admin))
        except sqlite3.IntegrityError as exc:
            raise PilotError("Tài khoản đã tồn tại.", 409) from exc

    def login(self, username: object, password: object) -> str:
        if not isinstance(username, str) or not isinstance(password, str) or len(password) > 128:
            raise PilotError("Thông tin đăng nhập không đúng.", 401)
        with self.db() as db:
            user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        expected = user["password"] if user and user["active"] else "0" * 32 + ":" + "0" * 128
        matches = secrets.compare_digest(_password_hash(password, expected.split(":", 1)[0]), expected)
        if not matches or not user or not user["active"]:
            raise PilotError("Thông tin đăng nhập không đúng.", 401)
        session = secrets.token_urlsafe(32)
        now = int(time.time())
        with self.db() as db:
            db.execute("DELETE FROM sessions WHERE expires <= ?", (now,))
            db.execute(
                "INSERT INTO sessions SELECT ?, id, ? FROM users WHERE id=? AND active=1 AND password=?",
                (_digest(session), now + SESSION_SECONDS, user["id"], expected),
            )
        return session

    def session_user(self, session: str):
        with self.db() as db:
            return db.execute(
                "SELECT u.id, u.username, u.admin FROM users u JOIN sessions s ON s.user_id=u.id "
                "WHERE s.digest=? AND s.expires>? AND u.active=1", (_digest(session), time.time()),
            ).fetchone()

    def logout(self, session: str) -> None:
        with self.db() as db:
            db.execute("DELETE FROM sessions WHERE digest=?", (_digest(session),))

    def change_user(self, user_id: int, *, active=None, password=None) -> None:
        if (active is not None) == (password is not None):
            raise PilotError("Chọn một thay đổi tài khoản.")
        if active is not None and not isinstance(active, bool):
            raise PilotError("Trạng thái tài khoản không hợp lệ.")
        hashed = _validated_password(password) if password is not None else None
        with self.db() as db:
            user = db.execute("SELECT admin FROM users WHERE id=?", (user_id,)).fetchone()
            if not user or user["admin"]:
                raise PilotError("Không tìm thấy tài khoản người dùng.", 404)
            if hashed is not None:
                db.execute("UPDATE users SET password=? WHERE id=?", (hashed, user_id))
            else:
                db.execute("UPDATE users SET active=? WHERE id=?", (active, user_id))
            db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
            db.execute("DELETE FROM tokens WHERE project_id IN (SELECT id FROM projects WHERE owner_id=?)",
                       (user_id,))

    def dashboard(self) -> dict:
        with self.db() as db:
            accounts = db.execute(
                "SELECT u.id, u.username, u.active, u.admin, COUNT(p.id) AS projects "
                "FROM users u LEFT JOIN projects p ON p.owner_id=u.id GROUP BY u.id ORDER BY u.username"
            ).fetchall()
            counts = db.execute("SELECT status, COUNT(*) AS count FROM projects GROUP BY status").fetchall()
        return {"users": [dict(user) for user in accounts], "jobs": {r["status"]: r["count"] for r in counts}}

    def list_projects(self, owner: int):
        with self.db() as db:
            return db.execute(
                "SELECT p.*, t.expires AS token_expires FROM projects p LEFT JOIN tokens t ON t.project_id=p.id "
                "WHERE p.owner_id=? ORDER BY p.created DESC, p.rowid DESC", (owner,),
            ).fetchall()

    def owned_project(self, owner: int, project_id: str):
        with self.db() as db:
            row = db.execute("SELECT * FROM projects WHERE id=? AND owner_id=?", (project_id, owner)).fetchone()
        if row is None:
            raise PilotError("Không tìm thấy dự án.", 404)
        return row

    def submit(self, owner: int, title: str, project_id: str) -> None:
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            count = db.execute("SELECT COUNT(*) FROM projects WHERE owner_id=?", (owner,)).fetchone()[0]
            if count >= PROJECT_LIMIT:
                raise PilotError(f"Mỗi tài khoản có tối đa {PROJECT_LIMIT} dự án.", 409)
            db.execute("INSERT INTO projects (id,owner_id,title,status,created) VALUES (?,?,?,'queued',?)",
                       (project_id, owner, title, int(time.time())))

    def claim(self) -> str | None:
        with self.db() as db:
            row = db.execute(
                "UPDATE projects SET status='running' WHERE id = "
                "(SELECT id FROM projects WHERE status='queued' ORDER BY created, rowid LIMIT 1) RETURNING id"
            ).fetchone()
        return row["id"] if row else None

    def finish(self, project_id: str, status: str, detail: str = "") -> None:
        with self.db() as db:
            db.execute("UPDATE projects SET status=?, detail=? WHERE id=?", (status, detail, project_id))

    def recover_interrupted(self) -> None:
        with self.db() as db:
            db.execute(
                "UPDATE projects SET status='failed', detail='Máy chủ khởi động lại trong lúc phân tích.' "
                "WHERE status='running'"
            )
            live = {row[0] for row in db.execute("SELECT id FROM projects WHERE status IN ('queued','ready')")}
        for directory in self.projects.iterdir():
            if directory.name not in live and re.fullmatch(r"[0-9a-f]{32}", directory.name):
                shutil.rmtree(directory, ignore_errors=True)

    def delete(self, owner: int, project_id: str) -> None:
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT status FROM projects WHERE id=? AND owner_id=?", (project_id, owner)).fetchone()
            if row is None:
                raise PilotError("Không tìm thấy dự án.", 404)
            if row["status"] == "running":
                raise PilotError("Đợi phân tích hoàn tất trước khi xóa dự án.", 409)
            db.execute("DELETE FROM projects WHERE id=?", (project_id,))
        shutil.rmtree(self.projects / project_id, ignore_errors=True)

    def token(self, owner: int, project_id: str, *, revoke: bool) -> str | None:
        raw = secrets.token_urlsafe(32)
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT p.status FROM projects p JOIN users u ON u.id=p.owner_id "
                "WHERE p.id=? AND p.owner_id=? AND u.active=1", (project_id, owner),
            ).fetchone()
            if row is None:
                raise PilotError("Không tìm thấy dự án.", 404)
            if revoke:
                db.execute("DELETE FROM tokens WHERE project_id=?", (project_id,))
                return None
            if row["status"] != "ready":
                raise PilotError("Đồ thị chưa sẵn sàng.", 409)
            db.execute("INSERT OR REPLACE INTO tokens VALUES (?,?,?)",
                       (project_id, _digest(raw), int(time.time()) + TOKEN_SECONDS))
        return raw

    def token_project(self, token: str, project_id: str):
        with self.db() as db:
            return db.execute(
                "SELECT p.id FROM tokens t JOIN projects p ON p.id=t.project_id JOIN users u ON u.id=p.owner_id "
                "WHERE t.digest=? AND p.id=? AND t.expires>? AND p.status='ready' AND u.active=1",
                (_digest(token), project_id, time.time()),
            ).fetchone()

    def graph(self, project_id: str) -> Path:
        return self.projects / project_id / "source" / "graphify-out" / "graph.json"


_SKIP_COMPONENTS = {".git", ".graphify", "graphify-out", "node_modules", ".venv", "__pycache__"}
_ARCHIVES = {".zip", ".7z", ".rar", ".tar", ".gz", ".bz2", ".xz"}


def unpack(archive: Path, destination: Path) -> None:
    """Expand only regular files and safe directories into an owned empty tree."""
    destination.mkdir(mode=0o700)
    total = 0
    entries = set()
    try:
        with zipfile.ZipFile(archive) as source:
            infos = source.infolist()
            if len(infos) > 15_000:
                raise PilotError("ZIP chứa quá 15.000 mục.")
            for info in infos:
                name = info.orig_filename
                path = PurePosixPath(name)
                parts = path.parts
                if (
                    not parts or path.is_absolute() or ".." in parts or "\\" in name
                    or ":" in name or any(ord(c) < 32 for c in name)
                    or len(parts) > 32 or len(name.encode()) > 1024
                    or any(len(part.encode()) > 255 for part in parts)
                ):
                    raise PilotError("ZIP chứa đường dẫn không hợp lệ.")
                mode = stat.S_IFMT(info.external_attr >> 16)
                if mode not in (0, stat.S_IFDIR if info.is_dir() else stat.S_IFREG):
                    raise PilotError("ZIP chỉ được chứa file và thư mục thông thường.")
                if parts in entries:
                    raise PilotError("ZIP chứa các đường dẫn trùng nhau.")
                entries.add(parts)
                if any(part.casefold() in _SKIP_COMPONENTS or part.casefold().startswith((".env", ".graphify"))
                       for part in parts):
                    continue
                if info.is_dir():
                    continue
                if path.suffix.lower() in _ARCHIVES:
                    continue
                if info.file_size > FILE_LIMIT or total + info.file_size > UNPACK_LIMIT:
                    raise PilotError("ZIP vượt giới hạn 16 MB mỗi file hoặc 250 MB sau giải nén.")
                output = destination.joinpath(*parts)
                output.parent.mkdir(parents=True, exist_ok=True)
                remaining = info.file_size
                with source.open(info) as compressed, output.open("xb") as target:
                    while chunk := compressed.read(64 * 1024):
                        remaining -= len(chunk)
                        if remaining < 0:
                            raise PilotError("Kích thước giải nén không khớp với ZIP.")
                        target.write(chunk)
                if remaining:
                    raise PilotError("ZIP bị thiếu dữ liệu.")
                total += info.file_size
    except (zipfile.BadZipFile, FileExistsError, NotADirectoryError, IsADirectoryError,
            NotImplementedError, RuntimeError) as exc:
        raise PilotError("ZIP bị hỏng, được mã hóa hoặc có cấu trúc không hợp lệ.") from exc


def run_graphify(args: list[str], cwd: Path, *, timeout: int = 30,
                 stop: threading.Event | None = None) -> tuple[int, str]:
    # Separate user input (arguments) from command names and configuration.
    env = {
        "PATH": os.defpath,
        "HOME": str(cwd.parent),
        "LANG": "C.UTF-8",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CEILING_DIRECTORIES": str(cwd.parent),
        "GRAPHIFY_BACKEND": "none",
        "GRAPHIFY_QUERY_LOG_DISABLE": "1",
        "GRAPHIFY_MAX_GRAPH_BYTES": str(GRAPH_LIMIT),
        "GRAPHIFY_MAX_WORKERS": "2",
        "GRAPHIFY_NO_TIPS": "1",
        "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
    }
    with tempfile.TemporaryFile(dir=cwd.parent) as output, subprocess.Popen(
        [sys.executable, "-P", "-m", "graphify", *args],
        cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=output,
        stderr=subprocess.STDOUT, start_new_session=True,
    ) as process:
        deadline = time.monotonic() + timeout
        while True:
            try:
                code = process.wait(timeout=0.25)
                break
            except subprocess.TimeoutExpired:
                if time.monotonic() >= deadline or (stop and stop.is_set()):
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    raise PilotError("Đã dừng tác vụ vì quá thời gian hoặc máy chủ đang tắt.", 504) from None
        size = output.seek(0, os.SEEK_END)
        output.seek(max(0, size - 64 * 1024))
        return code, redact_secrets(output.read().decode("utf-8", errors="replace")) or ""


def _preview(graph: Path) -> None:
    if not graph.exists() or graph.stat().st_size > GRAPH_LIMIT:
        raise PilotError("Không tạo được đồ thị hoặc đồ thị vượt 64 MB.")
    data = json.loads(graph.read_text(encoding="utf-8"))
    nodes = data["nodes"]
    links = data.get("links", data.get("edges", []))
    if not nodes:
        raise PilotError("ZIP không có mã nguồn được Graphify nhận diện.")
    degree = Counter(endpoint for edge in links for endpoint in (edge["source"], edge["target"]))
    chosen = sorted(nodes, key=lambda node: -degree[node["id"]])[:100]
    node_ids = {node["id"] for node in chosen}
    preview = {
        "counts": {
            "nodes": len(nodes), "edges": len(links),
            "communities": len({node.get("community") for node in nodes} - {None}),
        },
        "nodes": [
            {key: node.get(key) for key in ("id", "label", "source_file", "source_location", "community")}
            for node in chosen
        ],
        "edges": [
            {key: edge.get(key) for key in ("source", "target", "relation")}
            for edge in links if edge["source"] in node_ids and edge["target"] in node_ids
        ][:500],
    }
    graph.with_name("pilot-preview.json").write_text(json.dumps(preview, ensure_ascii=False), encoding="utf-8")


def work(store: Store, stop: threading.Event, wake: threading.Event) -> None:
    """Process one ZIP at a time. A ready project always has its outputs on disk."""
    import logging

    logger = logging.getLogger(__name__)
    while not stop.is_set():
        job = store.claim()
        if job is None:
            wake.wait(0.5)
            wake.clear()
            continue
        directory = store.projects / job
        archive = directory / "upload.zip"
        expanded = directory / "expanded"
        root = directory / "source"
        try:
            unpack(archive, expanded)
            archive.unlink()
            children = list(expanded.iterdir())
            if len(children) == 1 and children[0].is_dir():
                children[0].rename(root)
                expanded.rmdir()
            else:
                expanded.rename(root)
            status, build_log = run_graphify(
                ["update", "."], root, timeout=300, stop=stop,
            )
            if status:
                raise PilotError("Graphify không phân tích được repo. Hãy kiểm tra ZIP rồi thử lại.")
            _preview(store.graph(job))
            detail = ("Một số file chưa được phân tích đầy đủ."
                      if "failed" in build_log or "contributed nothing" in build_log else "")
            store.finish(job, "ready", detail)
        except PilotError as exc:
            shutil.rmtree(directory, ignore_errors=True)
            store.finish(job, "failed", str(exc))
        except Exception:
            logger.exception("Pilot analysis failed for project %s", job)
            shutil.rmtree(directory, ignore_errors=True)
            store.finish(job, "failed", "Lỗi máy chủ khi phân tích repo.")
