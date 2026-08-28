"""Sync the central graph store via a pluggable push/pull hook.

With a ``.graphify/config.json`` store configured (see graphify.store), the
real graph data lives under the configured ``<store>`` path (no repo/branch
segment) and the repo only holds links. ``graphify push`` / ``graphify pull``
hand that store tree to a
**hook** — a script (Python, JS, shell, PowerShell, ``.cmd``, or any
executable) that mirrors it to a backend (S3, git-lfs, rsync, a network
share, …). graphify itself has no backend dependency; if the store folder is
already shared (NFS/Dropbox/…) you never need push/pull at all.

Hooks live **in the repo** by default — ``.graphify/push.py`` /
``.graphify/pull.py`` (any supported extension) committed next to the config,
so a clone carries its own sync behaviour and teammates need zero per-machine
setup (``graphify remote init`` scaffolds the folder). Secrets never enter the
repo: hooks read credentials from the environment (env vars, ``~/.aws``, …).

Hook resolution for action ``push``/``pull``:
  1. an explicit path in ``.graphify/config.json`` — ``{"push": "...", "pull": "..."}``
     (relative paths resolve against the config's folder)
  2. ``.graphify/<action>.{py,js,mjs,cjs,sh,ps1,cmd,bat}`` in the repo, or an
     extension-less executable of the same name

The hook receives (via environment):
  GRAPHIFY_ACTION     "push" | "pull"
  GRAPHIFY_STORE_DIR  the configured <store> path — the tree to mirror
  GRAPHIFY_STORE      the configured store folder, expanded (same as above)
  GRAPHIFY_CONFIG     path to .graphify/config.json (extra keys are yours)
  GRAPHIFY_REPO_ROOT  the repo top-level dir (context; data is NOT here)
  GRAPHIFY_PREFIX     the store folder's basename (a natural object-key prefix)

Interpreter selection: an executable hook is run directly (its shebang wins —
an author can pin ``#!/usr/bin/env -S uv run --with boto3 python``). Otherwise
graphify maps by extension (.py→python, .js→node, .sh→bash, .ps1→powershell,
.cmd/.bat→cmd) so it also works on Windows where shebangs are ignored.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from graphify import store as _store

_HOOK_EXTS = (".py", ".js", ".mjs", ".cjs", ".sh", ".ps1", ".cmd", ".bat", "")


def _context() -> dict:
    ctx = _store.store_context()
    if ctx is None:
        sys.exit(
            'no store configured — add { "store": "~/graphify-store" } to '
            ".graphify/config.json at the repo root  (try: graphify remote init)"
        )
    return ctx


# ---------------------------------------------------------------- hook resolution

def _find_hook(cfg: dict, cfg_dir: Path, action: str) -> Path | None:
    explicit = cfg.get(action)
    if explicit:
        p = Path(os.path.expanduser(explicit))
        return p if p.is_absolute() else cfg_dir / p
    for ext in _HOOK_EXTS:
        cand = cfg_dir / _store.CONFIG_DIR / f"{action}{ext}"
        if cand.is_file():
            return cand
    return None


def _interpreter(hook: Path) -> list[str]:
    # An executable hook runs directly so its shebang wins (custom envs, uv, etc.).
    if os.name != "nt" and os.access(hook, os.X_OK):
        return []
    ext = hook.suffix.lower()
    if ext == ".py":
        return [sys.executable]
    if ext in (".js", ".mjs", ".cjs"):
        return ["node"]
    if ext == ".sh":
        return ["bash"]
    if ext == ".ps1":
        return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File"]
    if ext in (".cmd", ".bat"):
        return ["cmd", "/c"]
    return []  # last resort: let the OS try (shebang / association)


def _run_hook(action: str) -> dict:
    ctx = _context()
    hook = _find_hook(ctx["cfg"], ctx["cfg_dir"], action)
    if not hook or not hook.is_file():
        sys.exit(
            f"no {action} hook found — create .graphify/{action}.py (or .sh/.js/…) in the "
            f"repo, or set \"{action}\": \"<script>\" in .graphify/config.json  "
            f"(try: graphify remote init)"
        )
    store_dir = ctx["store_root"]
    store_dir.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "GRAPHIFY_ACTION": action,
        "GRAPHIFY_STORE_DIR": str(store_dir),
        "GRAPHIFY_STORE": str(ctx["store_base"]),
        "GRAPHIFY_CONFIG": str(_store.config_path(ctx["cfg_dir"])),
        "GRAPHIFY_REPO_ROOT": str(ctx["root"]),
        "GRAPHIFY_PREFIX": store_dir.name,
    }
    cmd = _interpreter(hook) + [str(hook)]
    print(f"{action}: running hook {hook}")
    result = subprocess.run(cmd, env=env)
    if result.returncode != 0:
        sys.exit(f"{action} hook failed (exit {result.returncode})")
    return ctx


def cmd_remote(argv: list[str]) -> None:
    """`graphify remote <init|push|pull|delete>` — the central-graph-store group."""
    sub = argv[0] if argv else ""
    if sub == "init":
        cmd_init(argv[1:])
    elif sub == "push":
        cmd_push(argv[1:])
    elif sub == "pull":
        cmd_pull(argv[1:])
    elif sub in ("delete", "deinit"):
        cmd_deinit(argv[1:])
    else:
        print(
            "Usage: graphify remote <command>\n"
            "  remote init      scaffold .graphify/ (config + hooks; --backend s3|s3-public|git-lfs|rsync)\n"
            "  remote push      run the push hook — upload the central graph store\n"
            "  remote pull      run the pull hook — download the store + recreate links\n"
            "  remote delete    leave the store — links become real local folders",
            file=sys.stderr,
        )
        sys.exit(1)


def cmd_push(argv: list[str]) -> None:
    _run_hook("push")


def cmd_pull(argv: list[str]) -> None:
    ctx = _run_hook("pull")
    # Recreate the working set: one graphify-out link per module now present in
    # the store, so a fresh clone can read every module's graphs immediately.
    linked = _store.link_all(ctx)
    if linked:
        print(f"pull: linked {linked} module folder(s) into the store")


def cmd_deinit(argv: list[str]) -> None:
    """`graphify remote delete` — leave the central store: links become real folders.

    Every ``graphify-out`` link is replaced by a plain local folder holding a
    COPY of its store data (the store is untouched — other branches/teammates
    keep working). Finish by deleting ``.graphify/`` and committing; the
    ``graphify-out`` .gitignore entry is left for you to keep or drop.
    """
    ctx = _context()
    n = _store.materialize(ctx)
    print(f"remote delete: materialized {n} folder(s); store untouched at {ctx['store_root']}")
    print("to finish: git rm -r .graphify && commit  (keep or drop the .gitignore entry)")


# ---------------------------------------------------------------- scaffolding

def cmd_init(argv: list[str]) -> None:
    """`graphify remote init [--backend s3|s3-public|git-lfs|rsync]` — bootstrap ``.graphify/``.

    Writes ``.graphify/config.json`` (if missing) plus starter ``push``/``pull``
    hooks for the chosen backend, so one command + one commit onboards the whole
    team. Existing files are never overwritten, and a hook already present under
    another extension (``push.sh``, ``pull.js``, …) is respected.
    """
    import json
    from graphify import remote_hook_templates as tpl

    backend = tpl.DEFAULT_BACKEND
    if "--backend" in argv:
        i = argv.index("--backend")
        backend = argv[i + 1] if i + 1 < len(argv) else ""
    if backend not in tpl.TEMPLATES:
        opts = "\n".join(f"  {n:10} {t['desc']}" for n, t in tpl.TEMPLATES.items())
        sys.exit(f"unknown --backend {backend!r}. Choose one:\n{opts}")
    spec = tpl.TEMPLATES[backend]

    found = _store.find_config()
    if found:
        base = found[1]
    else:
        toplevel = _store.git_out(Path.cwd(), "rev-parse", "--show-toplevel")
        base = Path(toplevel) if toplevel else Path.cwd()
    dest_dir = base / _store.CONFIG_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)

    config = _store.config_path(base)
    if config.is_file():
        print(f"kept existing {config}")
    else:
        cfg = {"store": f"~/graphify-store/{base.name}"}
        cfg.update(spec.get("config", {}))
        config.write_text(json.dumps(cfg, indent=2) + "\n")
        print(f"wrote {config}  (backend: {backend} — edit the store path / keys to taste)")

    for action in ("push", "pull"):
        existing = next(
            (dest_dir / f"{action}{ext}" for ext in _HOOK_EXTS
             if (dest_dir / f"{action}{ext}").is_file()),
            None,
        )
        if existing:
            print(f"kept existing {existing}")
            continue
        ext, body = spec[action]
        dest = dest_dir / f"{action}{ext}"
        dest.write_text(body)
        os.chmod(dest, 0o755)
        print(f"wrote {dest}")

    others = ", ".join(n for n in tpl.TEMPLATES if n != backend)
    print(
        "edit the hooks (secrets stay in the env — never in the repo), then commit .graphify/. "
        f"Teammates just: graphify remote pull.  Other backends: {others} "
        "(graphify remote init --backend <name>)."
    )
