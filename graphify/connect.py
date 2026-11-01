"""`graphify connect`: add the Graphify MCP server to every installed coding agent.

`graphify install` copies skills and rules; it never touches MCP config. This
command does the other half: it writes (or asks the client's own CLI to write)
an MCP server entry for the hosted Graphify server, the local `graphify-mcp`
server, or both, into Cursor, Claude Code, Codex and VS Code.

Invariants:
- Merge, never overwrite. Only the ``graphify`` / ``graphify-local`` entries are
  added, changed or removed; every other server and key is left as it was.
- A re-run with the same entry is a no-op ("no change").
- A file that cannot be parsed is never written. The client is skipped, a manual
  snippet is printed and the command exits non-zero at the end.
- Before the first change to a file, a timestamped ``<file>.graphify.<stamp>.bak``
  copy is made; the write itself is an atomic temp-file + rename that keeps the
  file's own line endings.
- No secrets are written. The hosted server signs in with OAuth inside each client.

When a client ships its own CLI for this (``claude mcp add``, ``codex mcp add``,
``code --add-mcp``) the user-scope entry is written through it, so we don't own
formats the client may change; files are edited directly otherwise.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

try:
    import tomllib  # type: ignore[import-not-found]
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

from graphify.paths import os_replace_with_fallback

# The command's name lives here only, so renaming it is a one-line change.
COMMAND_NAME = "connect"

HOSTED_URL = "https://api.graphify.com/mcp"
HOSTED_NAME = "graphify"
LOCAL_NAME = "graphify-local"
VERIFY_DOCS_URL = "https://docs.graphify.com/platform/verify-connection"

CLIENTS = ("cursor", "claude", "codex", "vscode")
CLIENT_LABELS = {
    "cursor": "Cursor",
    "claude": "Claude Code",
    "codex": "Codex",
    "vscode": "VS Code",
}
SIGN_IN_STEPS = {
    "cursor": "Cursor: open Customize, select graphify and finish the browser sign-in.",
    "claude": "Claude Code: run /mcp, select graphify, choose Authenticate.",
    "codex": "Codex: run `codex mcp login graphify`.",
    "vscode": "VS Code: run MCP: List Servers, start graphify and sign in.",
}

Runner = Callable[[list[str]], "subprocess.CompletedProcess[str]"]


def _default_runner(argv: list[str]) -> "subprocess.CompletedProcess[str]":
    # Run the resolved executable: on Windows the client CLIs are often `.cmd`
    # shims that CreateProcess won't find by bare name. Arguments are a list,
    # never a shell string.
    exe = shutil.which(argv[0]) or argv[0]
    return subprocess.run([exe, *argv[1:]], capture_output=True, text=True, timeout=60, check=False)


# --------------------------------------------------------------------------- #
# Entries
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Server:
    """One MCP server we manage: the hosted one or the local stdio one."""

    kind: str                     # "hosted" | "local"
    name: str                     # key in the client's config
    url: str | None = None        # hosted
    command: str | None = None    # local
    args: tuple[str, ...] = ()    # local

    def entry(self, client: str) -> dict:
        """The config entry in *client*'s own JSON shape."""
        if self.kind == "hosted":
            if client == "cursor":
                return {"url": self.url}
            return {"type": "http", "url": self.url}
        return {"type": "stdio", "command": self.command, "args": list(self.args)}

    def toml_entry(self) -> dict:
        if self.kind == "hosted":
            return {"url": self.url}
        return {"command": self.command, "args": list(self.args)}

    def matches(self, existing: object, client: str) -> bool:
        """True when *existing* already points where we would point it.

        Extra keys the user added (headers, env, disabled flags) are kept and
        don't count as a difference; only where the entry connects to does.
        """
        if not isinstance(existing, dict):
            return False
        if self.kind == "hosted":
            return existing.get("url") == self.url
        return (existing.get("command") == self.command
                and list(existing.get("args") or []) == list(self.args))


def hosted_server() -> Server:
    return Server(kind="hosted", name=HOSTED_NAME, url=HOSTED_URL)


def local_server(graph: Path) -> Server:
    """The stdio entry for `graphify-mcp --graph <absolute graph.json>`.

    The graph path is absolute because a client starts the server from its own working
    directory, not the repository's, and `graphify-mcp`'s default graph path is
    relative to the working directory.
    """
    # Absolute, because GUI clients (Cursor, VS Code) often start without the
    # shell's PATH, so a bare `graphify-mcp` would not be found.
    exe = shutil.which("graphify-mcp")
    if exe:
        command, args = str(Path(exe).resolve()), ("--graph", str(graph))
    else:
        command, args = sys.executable, ("-m", "graphify.serve", "--graph", str(graph))
    return Server(kind="local", name=LOCAL_NAME, command=command, args=args)


# --------------------------------------------------------------------------- #
# Locations
# --------------------------------------------------------------------------- #

def _vscode_user_dir() -> Path:
    """VS Code's default-profile user directory (where its user mcp.json lives)."""
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Code" / "User"
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        return (Path(appdata) if appdata else home / "AppData" / "Roaming") / "Code" / "User"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return (Path(xdg) if xdg else home / ".config") / "Code" / "User"


def config_path(client: str, scope: str, project_dir: Path) -> Path:
    """The file holding *client*'s MCP servers at *scope*."""
    home = Path.home()
    if client == "cursor":
        return (home if scope == "user" else project_dir) / ".cursor" / "mcp.json"
    if client == "claude":
        return home / ".claude.json" if scope == "user" else project_dir / ".mcp.json"
    if client == "codex":
        if scope == "user":
            codex_home = os.environ.get("CODEX_HOME")
            return (Path(codex_home) if codex_home else home / ".codex") / "config.toml"
        return project_dir / ".codex" / "config.toml"
    if client == "vscode":
        return _vscode_user_dir() / "mcp.json" if scope == "user" else project_dir / ".vscode" / "mcp.json"
    raise ValueError(client)


def _servers_key(client: str) -> str:
    return "servers" if client == "vscode" else "mcpServers"


def detect_clients() -> list[str]:
    home = Path.home()
    found = []
    if (home / ".cursor").is_dir() or shutil.which("cursor"):
        found.append("cursor")
    if shutil.which("claude") or (home / ".claude.json").is_file():
        found.append("claude")
    if shutil.which("codex") or (home / ".codex").is_dir():
        found.append("codex")
    if shutil.which("code") or _vscode_user_dir().is_dir():
        found.append("vscode")
    return found


def cursor_plugin_dir() -> Path | None:
    """The installed Graphify Cursor plugin, if it already provides the hosted server.

    The plugin ships its own ``mcp.json`` with the same ``graphify`` server, so
    writing one more into ``~/.cursor/mcp.json`` would list every tool twice.
    """
    root = Path.home() / ".cursor" / "plugins"
    if not root.is_dir():
        return None
    for manifest in _plugin_manifests(root, max_depth=5):
        try:
            if json.loads(manifest.read_text(encoding="utf-8")).get("name") != "graphify":
                continue
            mcp = json.loads((manifest.parent.parent / "mcp.json").read_text(encoding="utf-8"))
        except (OSError, ValueError, AttributeError):
            continue
        servers = mcp.get("mcpServers") if isinstance(mcp, dict) else None
        if isinstance(servers, dict) and HOSTED_NAME in servers:
            return manifest.parent.parent
    return None


def _plugin_manifests(root: Path, max_depth: int) -> list[Path]:
    """``<plugin>/.cursor-plugin/plugin.json`` files at most *max_depth* below *root*.

    Bounded, because the plugin cache can hold whole plugin checkouts.
    """
    found = []
    for dirpath, dirnames, _files in os.walk(root):
        here = Path(dirpath)
        depth = len(here.relative_to(root).parts)
        if (here / ".cursor-plugin" / "plugin.json").is_file():
            found.append(here / ".cursor-plugin" / "plugin.json")
        if depth >= max_depth:
            dirnames[:] = []
        else:
            dirnames[:] = sorted(d for d in dirnames
                                 if d not in ("node_modules", ".git", ".cursor-plugin"))
    return found


# --------------------------------------------------------------------------- #
# Reading and writing config files
# --------------------------------------------------------------------------- #

class ConfigError(Exception):
    """A config file exists but cannot be read or safely edited."""


def _read_text(path: Path) -> tuple[str, str]:
    """(text with bare \\n, the file's own newline)."""
    raw = path.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"
    return raw.replace("\r\n", "\n"), newline


def _json_indent(text: str) -> int | str:
    for line in text.split("\n")[1:]:
        stripped = line.lstrip(" \t")
        if stripped and len(stripped) != len(line):
            ws = line[: len(line) - len(stripped)]
            return "\t" if ws.startswith("\t") else len(ws)
    return 2


def load_json(path: Path) -> tuple[dict, str, str]:
    """(document, original text, newline). A missing or empty file is ``{}``."""
    if not path.exists():
        return {}, "", "\n"
    try:
        text, newline = _read_text(path)
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    if not text.strip():
        return {}, text, newline
    try:
        doc = json.loads(text)
    except ValueError as exc:
        raise ConfigError(f"{path} is not valid JSON ({exc}); comments are not supported") from exc
    if not isinstance(doc, dict):
        raise ConfigError(f"{path} does not hold a JSON object")
    return doc, text, newline


def json_servers(doc: dict, client: str, path: Path) -> dict:
    servers = doc.get(_servers_key(client), {})
    if not isinstance(servers, dict):
        raise ConfigError(f"{path}: `{_servers_key(client)}` is not an object")
    return servers


def render_json(doc: dict, original: str) -> str:
    return json.dumps(doc, indent=_json_indent(original), ensure_ascii=False) + "\n"


def set_json_entry(doc: dict, client: str, name: str, entry: dict | None, path: Path) -> dict:
    """A copy of *doc* with ``servers[name]`` set to *entry*, or removed when None."""
    new = json.loads(json.dumps(doc))
    key = _servers_key(client)
    servers = json_servers(new, client, path)
    if entry is None:
        servers.pop(name, None)
    else:
        merged = dict(servers.get(name) or {}) if isinstance(servers.get(name), dict) else {}
        # Drop the connection keys of the other transport so a hosted<->local
        # switch doesn't leave a url beside a command.
        for stale in ("url", "type", "command", "args"):
            merged.pop(stale, None)
        merged.update(entry)
        servers[name] = merged
    new[key] = servers
    return new


_TOML_HEADER = re.compile(r"^\s*\[\s*([^\[\]]+?)\s*\]\s*(#.*)?$")
_ANY_HEADER = re.compile(r"^\s*\[")


def _toml_key_parts(header: str) -> list[str]:
    parts, buf, quote = [], "", None
    for ch in header:
        if quote:
            if ch == quote:
                quote = None
            else:
                buf += ch
        elif ch in "\"'":
            quote = ch
        elif ch == ".":
            parts.append(buf.strip())
            buf = ""
        else:
            buf += ch
    parts.append(buf.strip())
    return parts


def load_toml(path: Path) -> tuple[dict, str, str]:
    if not path.exists():
        return {}, "", "\n"
    try:
        text, newline = _read_text(path)
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    try:
        doc = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path} is not valid TOML ({exc})") from exc
    return doc, text, newline


def toml_servers(doc: dict, path: Path) -> dict:
    servers = doc.get("mcp_servers", {})
    if not isinstance(servers, dict):
        raise ConfigError(f"{path}: `mcp_servers` is not a table")
    return servers


def _toml_value(value: object) -> str:
    if isinstance(value, str):
        # A JSON string is a valid TOML basic string (same escapes) as long as no
        # surrogate \\u escapes are produced, which ensure_ascii=False avoids.
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    raise TypeError(type(value))


def set_toml_entry(text: str, name: str, entry: dict | None, path: Path) -> str:
    """*text* with the ``[mcp_servers.<name>]`` table (and its sub-tables)
    replaced by *entry*, appended when absent, or removed when *entry* is None.

    There is no TOML writer in the dependencies, so this edits the text and only
    our own table: comments, ordering and every other table stay byte-for-byte.
    The result is re-parsed and must differ from the input only at our key, or
    a ConfigError is raised and nothing is written.
    """
    before = tomllib.loads(text) if text.strip() else {}
    lines = text.split("\n")
    start = end = None
    for i, line in enumerate(lines):
        if not _ANY_HEADER.match(line):
            continue
        m = _TOML_HEADER.match(line)
        ours = bool(m) and _toml_key_parts(m.group(1))[:2] == ["mcp_servers", name]
        if start is None and ours:
            start = i
        elif start is not None and not ours:
            end = i
            break
    if start is not None and end is None:
        end = len(lines)
    if name in toml_servers(before, path) and start is None:
        raise ConfigError(
            f"{path}: mcp_servers.{name} is written inline or with dotted keys; edit it by hand"
        )

    block = []
    if entry is not None:
        block = [f"[mcp_servers.{name}]"] + [f"{k} = {_toml_value(v)}" for k, v in entry.items()]

    if start is not None and end is not None:
        head, tail = lines[:start], lines[end:]
        # Our table's trailing blank lines belong to the gap before the next table.
        while end > start and not lines[end - 1].strip():
            end -= 1
            tail = lines[end:]
        if block:
            new_lines = head + block + tail
        else:
            while head and not head[-1].strip() and tail and not tail[0].strip():
                head = head[:-1]
            new_lines = head + tail
    elif block:
        body = text.rstrip("\n")
        new_lines = ([body, ""] if body else []) + block
    else:
        return text
    new_text = "\n".join(new_lines).rstrip("\n") + "\n" if any(l.strip() for l in new_lines) else ""

    after = tomllib.loads(new_text)
    expect = copy.deepcopy(before)
    servers = expect.setdefault("mcp_servers", {})
    if entry is None:
        servers.pop(name, None)
        if not servers and "mcp_servers" not in after:
            expect.pop("mcp_servers")
    else:
        servers[name] = entry
    if after != expect:
        raise ConfigError(f"{path}: editing mcp_servers.{name} would change other settings")
    return new_text


def backup(path: Path, stamp: str) -> Path | None:
    if not path.exists():
        return None
    dst = path.with_name(f"{path.name}.graphify.{stamp}.bak")
    n = 1
    while dst.exists():  # two runs in the same second keep both backups
        dst = path.with_name(f"{path.name}.graphify.{stamp}-{n}.bak")
        n += 1
    shutil.copy2(path, dst)
    return dst


def atomic_write(path: Path, text: str, newline: str) -> None:
    """Write *text* (bare \\n) with *newline* endings via temp file + rename.

    A symlinked config (dotfile managers) is written through to its target.
    """
    real = Path(os.path.realpath(path))
    real.parent.mkdir(parents=True, exist_ok=True)
    data = (text.replace("\n", newline) if newline != "\n" else text).encode("utf-8")
    fd, tmp = tempfile.mkstemp(dir=str(real.parent), prefix=f".{real.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        if real.exists():
            shutil.copymode(real, tmp)
        os_replace_with_fallback(tmp, str(real))
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


# --------------------------------------------------------------------------- #
# Planning
# --------------------------------------------------------------------------- #

@dataclass
class Step:
    client: str
    server: Server
    scope: str
    path: Path
    action: str                    # add | update | remove | no-change | skip
    via: str = "file"              # file | cli
    argv: list[list[str]] = field(default_factory=list)   # CLI calls, in order
    new_text: str | None = None    # file writes
    old_text: str = ""
    newline: str = "\n"
    message: str = ""
    warnings: list[str] = field(default_factory=list)
    status: str = "pending"        # pending | ok | failed | manual
    backup: Path | None = None

    def snippet(self) -> str:
        """What to add by hand when we can't."""
        if self.client == "codex":
            return "\n".join(
                [f"[mcp_servers.{self.server.name}]"]
                + [f"{k} = {_toml_value(v)}" for k, v in self.server.toml_entry().items()]
            )
        return json.dumps(
            {_servers_key(self.client): {self.server.name: self.server.entry(self.client)}}, indent=2
        )


def _read_state(client: str, scope: str, path: Path, server: Server) -> tuple[object, str, str, object]:
    """(current entry or None, original text, newline, parsed doc)."""
    if client == "codex":
        doc, text, newline = load_toml(path)
        return toml_servers(doc, path).get(server.name), text, newline, doc
    doc, text, newline = load_json(path)
    servers = json_servers(doc, client, path)
    return servers.get(server.name), text, newline, doc


def _other_scope_has(client: str, scope: str, project_dir: Path, server: Server) -> list[str]:
    """Where else the same server name is configured for this client."""
    hits = []
    other = "project" if scope == "user" else "user"
    try:
        current, *_ = _read_state(client, other, config_path(client, other, project_dir), server)
        if current is not None:
            hits.append(str(config_path(client, other, project_dir)))
    except ConfigError:
        pass
    if client == "claude":
        # Claude Code's third scope, "local", sits in ~/.claude.json per project.
        try:
            doc, *_ = load_json(Path.home() / ".claude.json")
            proj = (doc.get("projects") or {}).get(str(project_dir)) or {}
            if server.name in (proj.get("mcpServers") or {}):
                hits.append(f"{Path.home() / '.claude.json'} (local scope for {project_dir})")
        except (ConfigError, AttributeError):
            pass
    return hits


def _cli_add(client: str, server: Server, scope: str) -> list[str] | None:
    """The client's own add command, when it has one we can use for this write."""
    if client == "claude" and scope == "user" and shutil.which("claude"):
        if server.kind == "hosted":
            return ["claude", "mcp", "add", "--transport", "http", "--scope", "user",
                    server.name, server.url or ""]
        return ["claude", "mcp", "add", "--scope", "user", server.name, "--",
                server.command or "", *server.args]
    if client == "codex" and scope == "user" and shutil.which("codex"):
        if server.kind == "hosted":
            return ["codex", "mcp", "add", server.name, "--url", server.url or ""]
        return ["codex", "mcp", "add", server.name, "--", server.command or "", *server.args]
    if client == "vscode" and scope == "user" and shutil.which("code") and os.name != "nt":
        # Not on Windows: `code` is a batch file there, and a JSON argument through
        # cmd.exe quoting is not safe. The file merge below covers it.
        payload = {"name": server.name, **server.entry("vscode")}
        return ["code", "--add-mcp", json.dumps(payload)]
    return None


def _cli_remove(client: str, server: Server, scope: str) -> list[str] | None:
    if client == "claude" and scope == "user" and shutil.which("claude"):
        return ["claude", "mcp", "remove", server.name, "--scope", "user"]
    if client == "codex" and scope == "user" and shutil.which("codex"):
        return ["codex", "mcp", "remove", server.name]
    return None


def plan_step(client: str, server: Server, scope: str, project_dir: Path, *, remove: bool) -> Step:
    path = config_path(client, scope, project_dir)
    step = Step(client=client, server=server, scope=scope, path=path, action="no-change")
    try:
        current, text, newline, doc = _read_state(client, scope, path, server)
    except ConfigError as exc:
        step.action, step.status, step.message = "skip", "failed", str(exc)
        return step
    step.old_text, step.newline = text, newline

    if not remove:
        step.warnings += [
            f"{server.name} is also configured in {where}; the client may list every tool twice"
            for where in _other_scope_has(client, scope, project_dir, server)
        ]

    if remove:
        if current is None:
            step.action, step.message = "no-change", "not configured"
            return step
        step.action = "remove"
    elif current is None:
        step.action = "add"
    elif server.matches(current, client):
        step.action, step.message = "no-change", "already configured"
        return step
    else:
        step.action = "update"

    # Claude Code rewrites ~/.claude.json constantly; we never edit it ourselves.
    if client == "claude" and scope == "user":
        if not shutil.which("claude"):
            step.action, step.status = "skip", "manual"
            step.message = "the `claude` CLI is not on PATH; add the server with it, or use --scope project"
            return step
        if step.action == "remove":
            step.via, step.argv = "cli", [_cli_remove(client, server, scope) or []]
        else:
            add = _cli_add(client, server, scope) or []
            pre = [_cli_remove(client, server, scope) or []] if step.action == "update" else []
            step.via, step.argv = "cli", pre + [add]
        return step

    # Fresh adds go through the client's CLI where one exists; updates and
    # removals edit the file, so only our entry changes.
    if step.action == "add":
        add = _cli_add(client, server, scope)
        if add:
            step.via, step.argv = "cli", [add]
            return step

    try:
        if client == "codex":
            step.new_text = set_toml_entry(
                text, server.name, None if remove else server.toml_entry(), path
            )
        else:
            new_doc = set_json_entry(doc, client, server.name,  # type: ignore[arg-type]
                                     None if remove else server.entry(client), path)
            step.new_text = render_json(new_doc, text)
    except ConfigError as exc:
        step.action, step.status, step.message = "skip", "failed", str(exc)
    return step


def build_plan(clients: list[str], servers: list[tuple[Server, str]], project_dir: Path,
               *, remove: bool) -> list[Step]:
    steps = []
    plugin = cursor_plugin_dir()
    for client in clients:
        for server, scope in servers:
            if client == "cursor" and server.kind == "hosted" and plugin and not remove:
                path = config_path(client, scope, project_dir)
                steps.append(Step(client=client, server=server, scope=scope, path=path,
                                  action="no-change", status="ok",
                                  message=f"provided by the Graphify Cursor plugin ({plugin})"))
                continue
            steps.append(plan_step(client, server, scope, project_dir, remove=remove))
    return steps


# --------------------------------------------------------------------------- #
# Applying
# --------------------------------------------------------------------------- #

def apply_step(step: Step, stamp: str, run: Runner) -> None:
    if step.status != "pending":
        return
    if step.action == "no-change":
        step.status = "ok"
        return
    try:
        if step.via == "cli":
            for argv in step.argv:
                proc = run(argv)
                if proc.returncode != 0:
                    err = (proc.stderr or proc.stdout or "").strip().splitlines()
                    step.status = "failed"
                    step.message = f"`{' '.join(argv[:3])} ...` exited {proc.returncode}" + (
                        f": {err[-1]}" if err else "")
                    return
            step.status = "ok"
            return
        assert step.new_text is not None
        step.backup = backup(step.path, stamp)
        atomic_write(step.path, step.new_text, step.newline)
        # Verify: the file parses and holds exactly what we meant.
        current, *_ = _read_state(step.client, step.scope, step.path, step.server)
        ok = current is None if step.action == "remove" else step.server.matches(current, step.client)
        step.status = "ok" if ok else "failed"
        if not ok:
            step.message = "the written file did not read back as expected"
    except (OSError, ConfigError) as exc:
        step.status, step.message = "failed", f"{exc.__class__.__name__}: {exc}"


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #

def _describe(step: Step) -> str:
    how = "via `" + " ".join(step.argv[-1][:3]) + "`" if step.via == "cli" and step.argv else str(step.path)
    line = f"  {CLIENT_LABELS[step.client]:<12} {step.server.name:<15} {step.scope:<8} {step.action:<10} {how}"
    if step.message:
        line += f"  ({step.message})"
    return line


def _diff(step: Step) -> str:
    if step.via != "file" or step.new_text is None:
        return ""
    return "".join(difflib.unified_diff(
        step.old_text.splitlines(keepends=True), step.new_text.splitlines(keepends=True),
        fromfile=str(step.path), tofile=str(step.path),
    ))


def next_steps(steps: list[Step]) -> list[str]:
    hosted = sorted({s.client for s in steps
                     if s.server.kind == "hosted" and s.status == "ok" and s.action != "remove"},
                    key=CLIENTS.index)
    out = [SIGN_IN_STEPS[c] for c in hosted]
    if hosted or any(s.status == "ok" and s.action != "remove" for s in steps):
        out.append(f"Then check it's working: {VERIFY_DOCS_URL}")
    return out


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=f"graphify {COMMAND_NAME}",
        description="Add the Graphify MCP server to your coding agents "
                    "(Cursor, Claude Code, Codex, VS Code).",
    )
    p.add_argument("--client", default=None,
                   help="comma-separated: cursor,claude,codex,vscode or all "
                        "(default: every client found on this machine)")
    p.add_argument("--server", choices=["hosted", "local", "both"], default="hosted",
                   help=f"hosted = {HOSTED_URL} (OAuth sign-in), local = graphify-mcp over "
                        "this checkout's graph (default: hosted)")
    p.add_argument("--scope", choices=["user", "project"], default=None,
                   help="user = every project on this machine, project = files in this repo "
                        "(default: user for hosted, project for local)")
    p.add_argument("--graph", default=None, metavar="PATH",
                   help="graph.json for the local server (default: ./graphify-out/graph.json)")
    p.add_argument("--dry-run", action="store_true", help="print the plan and diffs, write nothing")
    p.add_argument("--yes", "-y", action="store_true", help="don't ask for confirmation")
    p.add_argument("--remove", action="store_true", help="remove the graphify entries instead")
    p.add_argument("--with-skills", action="store_true",
                   help="also run `graphify install` for each client (skills and rules)")
    p.add_argument("--json", action="store_true", help="print a machine-readable result")
    return p


def _parse_clients(value: str | None) -> list[str]:
    if value is None:
        return detect_clients()
    names = [v.strip().lower() for v in value.split(",") if v.strip()]
    if "all" in names:
        return list(CLIENTS)
    unknown = [n for n in names if n not in CLIENTS]
    if unknown:
        raise SystemExit(f"error: unknown client(s): {', '.join(unknown)} "
                         f"(choose from {', '.join(CLIENTS)}, all)")
    return [c for c in CLIENTS if c in names]


def _install_skills(clients: list[str]) -> None:
    from graphify import install as _install

    for client in clients:
        try:
            if client == "cursor":
                _install._cursor_install(Path("."))
            elif client == "vscode":
                _install.vscode_install()
            else:
                _install.install(platform=client)
        except (OSError, SystemExit) as exc:
            print(f"  {CLIENT_LABELS[client]}: skills not installed: {exc}", file=sys.stderr)


def run(argv: list[str], *, runner: Runner = _default_runner,
        project_dir: Path | None = None, interactive: bool | None = None) -> int:
    args = _parser().parse_args(argv)
    project_dir = (project_dir or Path.cwd()).resolve()
    out = sys.stderr if args.json else sys.stdout

    try:
        clients = _parse_clients(args.client)
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return 2
    if not clients:
        print("No supported coding agent found (Cursor, Claude Code, Codex, VS Code). "
              "Pass --client to choose one.", file=sys.stderr)
        return 2

    servers: list[tuple[Server, str]] = []
    if args.server in ("hosted", "both"):
        servers.append((hosted_server(), args.scope or "user"))
    if args.server in ("local", "both"):
        scope = args.scope or "project"
        if scope == "user" and not args.graph:
            print("error: a user-scope local server serves one graph for every project; "
                  "pass --graph /absolute/path/to/graph.json, or use --scope project",
                  file=sys.stderr)
            return 2
        graph = Path(args.graph).expanduser() if args.graph else project_dir / "graphify-out" / "graph.json"
        graph = (project_dir / graph if not graph.is_absolute() else graph).resolve()
        if not args.remove and not graph.is_file():
            print(f"error: no graph at {graph}; build one first with `graphify update .`",
                  file=sys.stderr)
            return 2
        servers.append((local_server(graph), scope))

    steps = build_plan(clients, servers, project_dir, remove=args.remove)
    changes = [s for s in steps if s.action in ("add", "update", "remove")
               and s.status == "pending"]

    print(f"graphify {COMMAND_NAME}: {'remove' if args.remove else 'plan'}", file=out)
    for s in steps:
        print(_describe(s), file=out)
        for w in s.warnings:
            print(f"    warning: {w}", file=out)
    if args.dry_run:
        for s in changes:
            d = _diff(s)
            if d:
                print(d, file=out, end="" if d.endswith("\n") else "\n")
            elif s.via == "cli":
                for a in s.argv:
                    print("  would run: " + " ".join(a), file=out)

    if changes and not args.dry_run and not args.yes:
        tty = sys.stdin.isatty() if interactive is None else interactive
        if not tty:
            print("error: nothing written; re-run with --yes to apply without a prompt",
                  file=sys.stderr)
            return 2
        try:
            answer = input("Apply these changes? [y/N] ").strip().lower()
        except EOFError:
            answer = ""
        if answer not in ("y", "yes"):
            print("Nothing written.", file=out)
            return 1

    if not args.dry_run:
        stamp = time.strftime("%Y%m%d%H%M%S")
        for s in steps:
            apply_step(s, stamp, runner)
        if args.with_skills and not args.remove:
            with contextlib.redirect_stdout(out):
                _install_skills(clients)

    failed = [s for s in steps if s.status in ("failed", "manual")]
    if not args.dry_run:
        for s in steps:
            if s.status == "ok" and s.action in ("add", "update", "remove"):
                note = f" (backup: {s.backup})" if s.backup else ""
                print(f"  {CLIENT_LABELS[s.client]}: {s.action} {s.server.name} done{note}", file=out)
    for s in failed:
        print(f"  {CLIENT_LABELS[s.client]}: {s.server.name} not configured: {s.message}",
              file=sys.stderr)
        if not args.remove:
            print(f"    add this to {s.path} by hand:\n" + _indent(s.snippet(), 6), file=sys.stderr)

    steps_text = [] if args.dry_run or args.remove else next_steps(steps)
    if steps_text:
        print("\nNext:", file=out)
        for line in steps_text:
            print(f"  {line}", file=out)

    if args.json:
        print(json.dumps({
            "ok": not failed,
            "dry_run": args.dry_run,
            "results": [{
                "client": s.client, "server": s.server.name, "scope": s.scope,
                "path": str(s.path), "action": s.action, "via": s.via,
                "status": "planned" if args.dry_run and s.status == "pending" else s.status,
                "message": s.message, "warnings": s.warnings,
                "backup": str(s.backup) if s.backup else None,
            } for s in steps],
            "next_steps": steps_text,
        }, indent=2))
    return 1 if failed else 0


def _indent(text: str, n: int) -> str:
    return "\n".join(" " * n + line for line in text.split("\n"))


def main() -> None:
    sys.exit(run(sys.argv[2:]))
