"""Central graph store: keep the graph data out of the repo via a link.

A committed ``.graphify/config.json`` at the repo root selects a store folder:

    { "store": "~/graphify-store" }

The ``.graphify/`` folder is the repo's graphify home — it also carries the
team's push/pull sync hooks (see graphify.remote), so a clone brings its own
sync behaviour with it.

Every graphify command then makes sure ``./graphify-out`` is a **link** — a
symlink on POSIX, a directory junction on Windows (``mklink /J`` semantics, no
admin rights) — pointing at::

    <store>/<module-relative-path>/graphify-out

so every write physically lands in the central store, while every literal
``graphify-out/...`` path (the CLI defaults, the agent skill's code blocks,
a plain ``cat``) keeps working unchanged through the link. A monorepo gets one
link per directory you build in, keyed only by its path within the repo; the
repo root's link is simply ``<store>/graphify-out``. There is **no repo or
branch segment** — the repo points at the same store location on every branch,
and each repo names its own store path in its config. ``graphify push`` /
``pull`` (see graphify.remote) sync the store elsewhere.

The ignore entry is written in the same step that creates a link, as a bare
``graphify-out`` line: the usual trailing-slash form only matches directories,
and git sees a POSIX symlink as a *file* — with ``graphify-out/`` the link
itself would show up in ``git status``. The bare form matches the symlink, the
junction (a directory to git, which would otherwise descend into it on
Windows), and a plain local folder alike, at any depth.

Without a ``.graphify/config.json`` (or without a ``store`` key) nothing here
runs and graphify writes a plain local folder exactly like before. An absolute
``GRAPHIFY_OUT`` env override also disables linking — it already points the
output elsewhere.
"""
from __future__ import annotations

import json
import os
import stat
import shutil
import subprocess
import sys
from pathlib import Path

CONFIG_DIR = ".graphify"
CONFIG_NAME = "config.json"


def config_path(base: Path) -> Path:
    """``<base>/.graphify/config.json`` — the repo's committed graphify config."""
    return base / CONFIG_DIR / CONFIG_NAME


def git_out(cwd: Path, *args: str) -> str | None:
    """``git -C cwd <args>`` → stripped stdout, or None on any failure."""
    try:
        out = subprocess.check_output(
            ["git", "-C", str(cwd), *args], text=True, stderr=subprocess.DEVNULL
        ).strip()
        return out or None
    except Exception:
        return None


def find_config(start: Path | None = None) -> tuple[dict, Path] | None:
    """Walk up from ``start`` (default cwd) for ``.graphify/config.json``.

    Returns ``(config_dict, dir_containing_.graphify)``; a missing or malformed
    file yields None so graphify falls back to plain local output.
    """
    cur = Path(start or Path.cwd()).resolve()
    for d in (cur, *cur.parents):
        f = config_path(d)
        if f.is_file():
            try:
                cfg = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                return None
            return (cfg, d) if isinstance(cfg, dict) else None
    return None


def store_context(cwd: Path | None = None) -> dict | None:
    """Resolve the store context for ``cwd``, or None when no store is configured.

    Keys: ``cfg``/``cfg_dir`` (the config), ``root`` (git top-level, else the
    config dir), ``in_git``, ``store_base``/``store_root`` (the expanded ``store``
    path — the tree push/pull hooks sync).

    The store path *is* the key: the graph lives directly under it, with no
    ``<repo>``/``<branch>`` segments. So a repo points at the same store
    location no matter which branch is checked out, and each repo simply names
    its own store path in its committed config (change it to whatever you like).
    """
    cwd = Path(cwd or Path.cwd()).resolve()
    found = find_config(cwd)
    if not found:
        return None
    cfg, cfg_dir = found
    store = cfg.get("store")
    if not store or not isinstance(store, str):
        return None
    toplevel = git_out(cwd, "rev-parse", "--show-toplevel")
    root = Path(toplevel).resolve() if toplevel else cfg_dir
    store_base = Path(os.path.expanduser(store))
    return {
        "cfg": cfg,
        "cfg_dir": cfg_dir,
        "root": root,
        "in_git": toplevel is not None,
        "store_base": store_base,
        "store_root": store_base,
    }


# ------------------------------------------------------------------ links

def _is_link(p: Path) -> bool:
    """True for a POSIX symlink or a Windows junction (reparse point)."""
    try:
        st = os.lstat(p)
    except OSError:
        return False
    if stat.S_ISLNK(st.st_mode):
        return True
    if os.name == "nt":
        return bool(
            getattr(st, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        )
    return False


def _make_link(link: Path, target: Path) -> None:
    if os.name == "nt":
        # A junction, not a symlink: junctions need no privilege/dev-mode and
        # git+every tool treat them as normal directories. Local targets only.
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(str(target), str(link), target_is_directory=True)


def _remove_link(link: Path) -> None:
    try:
        link.unlink()  # symlink (and junctions on py3.8+ where unlink works)
    except OSError:
        os.rmdir(link)  # a junction removes like an empty dir — contents survive


def _migrate(local_dir: Path, target: Path) -> int:
    """Move a pre-existing real ``graphify-out`` into the store. Local wins on
    collision — it is the freshest build."""
    target.mkdir(parents=True, exist_ok=True)
    moved = 0
    for child in list(local_dir.iterdir()):
        dest = target / child.name
        if dest.is_dir() and not _is_link(dest):
            shutil.rmtree(dest)
        elif dest.exists() or _is_link(dest):
            dest.unlink()
        shutil.move(str(child), str(dest))
        moved += 1
    local_dir.rmdir()
    return moved


def _ensure_gitignore(root: Path, name: str) -> None:
    gi = root / ".gitignore"
    text = gi.read_text(encoding="utf-8") if gi.is_file() else ""
    patterns = {line.strip() for line in text.splitlines()}
    if name in patterns or f"**/{name}" in patterns:
        return
    entry = name + "\n"
    if text and not text.endswith("\n"):
        entry = "\n" + entry
    gi.write_text(text + entry, encoding="utf-8")


def ensure_out_link(cwd: Path | None = None) -> Path | None:
    """Make ``<cwd>/graphify-out`` a link into the configured store.

    Called once at CLI dispatch. Returns the store-side directory when a store
    is configured (creating/retargeting/migrating as needed), else None.
    Idempotent: the common case is a single ``lstat``.
    """
    from graphify import paths

    out_name = paths.GRAPHIFY_OUT
    if os.path.isabs(out_name):
        return None  # GRAPHIFY_OUT already redirects output; nothing to link
    cwd = Path(cwd or Path.cwd()).resolve()
    ctx = store_context(cwd)
    if ctx is None:
        return None
    try:
        rel = cwd.relative_to(ctx["root"])
    except ValueError:
        return None  # cwd outside the repo the config governs
    target = (ctx["store_root"] / rel / paths.GRAPHIFY_OUT_NAME).resolve()
    link = cwd / out_name

    if _ensure_link_at(link, target) and ctx["in_git"]:
        _ensure_gitignore(ctx["root"], paths.GRAPHIFY_OUT_NAME)
    return target


def _ensure_link_at(link: Path, target: Path) -> bool:
    """Point ``link`` at ``target`` (creating/retargeting/migrating as needed).

    Returns True when a link was created or retargeted, False when it was
    already correct — the caller only touches .gitignore on a real change.
    """
    if _is_link(link):
        if Path(os.path.realpath(link)) == target:
            target.mkdir(parents=True, exist_ok=True)
            return False
        _remove_link(link)  # branch switch / store move: retarget
    elif link.is_dir():
        moved = _migrate(link, target)
        if moved:
            print(f"store: migrated {moved} entrie(s) from {link} into {target}")
    elif link.exists():
        # a regular FILE named graphify-out — never clobber user data
        print(f"store: {link} exists and is not a directory — not linking", file=sys.stderr)
        return False

    target.mkdir(parents=True, exist_ok=True)
    link.parent.mkdir(parents=True, exist_ok=True)
    _make_link(link, target)
    print(f"store: {link} -> {target}", file=sys.stderr)
    return True


def materialize(ctx: dict) -> int:
    """Replace every ``graphify-out`` link with a real folder holding a copy of
    its store data — the exit path from the central store (``graphify deinit``).

    Copies (never moves): the store keeps serving teammates who share it.
    Returns the number of links materialized.
    """
    import shutil

    from graphify import paths

    candidates = {ctx["root"] / paths.GRAPHIFY_OUT}
    if ctx["store_root"].is_dir():
        for t in sorted(ctx["store_root"].rglob(paths.GRAPHIFY_OUT_NAME)):
            if t.is_dir():
                rel = t.parent.relative_to(ctx["store_root"])
                candidates.add(ctx["root"] / rel / paths.GRAPHIFY_OUT)
    n = 0
    for link in sorted(candidates):
        if not _is_link(link):
            continue
        src = Path(os.path.realpath(link))
        _remove_link(link)
        if src.is_dir():
            shutil.copytree(src, link)
        else:
            link.mkdir(parents=True, exist_ok=True)
        print(f"store: materialized {link} (local copy of {src})")
        n += 1
    return n


def link_all(ctx: dict) -> int:
    """Create/refresh a repo link for every module present in the store.

    Walks the ``<store>`` tree for ``graphify-out`` dirs and mirrors each
    as a link at the matching repo path, so ``graphify pull`` recreates the whole
    working set — a fresh clone can immediately read any module's graphs (e.g.
    root-level ``merge-graphs ./services/api/graphify-out/graph.json``) without
    first running a command inside that module. Modules absent from the working
    tree (removed on this branch) are skipped, never invented. Returns the
    number of links created/retargeted.
    """
    from graphify import paths

    if os.path.isabs(paths.GRAPHIFY_OUT):
        return 0
    store_root = ctx["store_root"]
    if not store_root.is_dir():
        return 0
    changed = 0
    for target in sorted(store_root.rglob(paths.GRAPHIFY_OUT_NAME)):
        if not target.is_dir():
            continue
        module_dir = ctx["root"] / target.parent.relative_to(store_root)
        if not module_dir.is_dir():
            continue
        if _ensure_link_at(module_dir / paths.GRAPHIFY_OUT, target.resolve()):
            changed += 1
    if changed and ctx["in_git"]:
        _ensure_gitignore(ctx["root"], paths.GRAPHIFY_OUT_NAME)
    return changed
