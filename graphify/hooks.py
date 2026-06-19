# git hook integration - install/uninstall graphify post-commit and post-checkout hooks
from __future__ import annotations
import configparser
import re
import sys
from pathlib import Path

_HOOK_MARKER = "# graphify-hook-start"
_HOOK_MARKER_END = "# graphify-hook-end"
_CHECKOUT_MARKER = "# graphify-checkout-hook-start"
_CHECKOUT_MARKER_END = "# graphify-checkout-hook-end"

# __PINNED_PYTHON__ is replaced at install time with the absolute path of the
# Python interpreter that ran `graphify hook install`.  For uv-tool and pipx
# installs the interpreter lives inside an isolated venv, so the launcher on
# PATH is the only entry point — and GUI git clients / CI runners often have a
# minimal PATH that omits ~/.local/bin.  Pinning sys.executable at install time
# makes the hook work regardless of PATH at git-trigger time.
_PYTHON_DETECT = """\
# Detect the correct Python interpreter (handles uv tool, pipx, venv, system installs).
# _PINNED was recorded at hook-install time; tried first so the hook works even
# when the graphify launcher is not on PATH (common in GUI clients and CI).
GRAPHIFY_PYTHON=""
_PINNED='__PINNED_PYTHON__'
if [ -n "$_PINNED" ] && [ -x "$_PINNED" ] && "$_PINNED" -c "import graphify" 2>/dev/null; then
    GRAPHIFY_PYTHON="$_PINNED"
fi
# Second probe: read graphify-out/.graphify_python (written by the skill and
# CLI; survives uv-tool reinstalls and is the same source the README documents).
if [ -z "$GRAPHIFY_PYTHON" ]; then
    _GFY_PYTHON_FILE="graphify-out/.graphify_python"
    if [ -f "$_GFY_PYTHON_FILE" ]; then
        _FROM_FILE=$(cat "$_GFY_PYTHON_FILE" 2>/dev/null | tr -d '[:space:]')
        case "$_FROM_FILE" in
            *[!a-zA-Z0-9/_.@:\\-]*) _FROM_FILE="" ;;  # allowlist (covers Windows paths)
        esac
        if [ -n "$_FROM_FILE" ] && [ -x "$_FROM_FILE" ] && "$_FROM_FILE" -c "import graphify" 2>/dev/null; then
            GRAPHIFY_PYTHON="$_FROM_FILE"
        fi
    fi
fi
# Third probe: resolve via the graphify launcher on PATH (shebang probe).
if [ -z "$GRAPHIFY_PYTHON" ]; then
    GRAPHIFY_BIN=$(command -v graphify 2>/dev/null)
    if [ -n "$GRAPHIFY_BIN" ]; then
        case "$GRAPHIFY_BIN" in
            *.exe) _SHEBANG="" ;;
            *)     _SHEBANG=$(head -1 "$GRAPHIFY_BIN" | sed 's/^#![[:space:]]*//') ;;
        esac
        case "$_SHEBANG" in
            */env\\ *) GRAPHIFY_PYTHON="${_SHEBANG#*/env }" ;;
            *)         GRAPHIFY_PYTHON="$_SHEBANG" ;;
        esac
        # Allowlist: only keep characters valid in a filesystem path to prevent
        # injection if the shebang contains shell metacharacters.
        case "$GRAPHIFY_PYTHON" in
            *[!a-zA-Z0-9/_.@-]*) GRAPHIFY_PYTHON="" ;;
        esac
        if [ -n "$GRAPHIFY_PYTHON" ] && ! "$GRAPHIFY_PYTHON" -c "import graphify" 2>/dev/null; then
            GRAPHIFY_PYTHON=""
        fi
    fi
fi
# Last resort: try python3 / python (works for system/venv installs on PATH).
if [ -z "$GRAPHIFY_PYTHON" ]; then
    if command -v python3 >/dev/null 2>&1 && python3 -c "import graphify" 2>/dev/null; then
        GRAPHIFY_PYTHON="python3"
    elif command -v python >/dev/null 2>&1 && python -c "import graphify" 2>/dev/null; then
        GRAPHIFY_PYTHON="python"
    else
        echo "[graphify hook] could not locate a Python with graphify installed. Add the graphify bin dir to PATH or re-run 'graphify hook install' from the env where graphify lives." >&2
        exit 0
    fi
fi
"""

# The Python that the rebuild runs, shared by both hooks. Embedded verbatim into
# the launcher below and re-executed in the detached child. Must not contain the
# double-quote, $, backtick or backslash characters: it is carried inside a
# shell double-quoted `-c "..."` argument (see _detached_launch).
_REBUILD_BODY_COMMIT = """\
import os, signal, sys
from pathlib import Path

changed_raw = os.environ.get('GRAPHIFY_CHANGED', '')
changed = [Path(f.strip()) for f in changed_raw.strip().splitlines() if f.strip()]

if not changed:
    sys.exit(0)

print(f'[graphify hook] {len(changed)} file(s) changed - rebuilding graph...')

try:
    from graphify.watch import _rebuild_code, _apply_resource_limits
    _apply_resource_limits()
    _timeout = int(os.environ.get('GRAPHIFY_REBUILD_TIMEOUT', '600'))
    if _timeout > 0 and hasattr(signal, 'SIGALRM'):
        signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError(f'graphify rebuild exceeded {_timeout}s')))
        signal.alarm(_timeout)
    _force = os.environ.get('GRAPHIFY_FORCE', '').lower() in ('1', 'true', 'yes')
    _root = Path('.')
    _saved = Path('graphify-out/.graphify_root')
    if _saved.exists():
        _txt = _saved.read_text(encoding='utf-8').strip()
        if _txt:
            _root = Path(_txt)
    _rebuild_code(_root, changed_paths=changed, force=_force)
except TimeoutError as exc:
    print(f'[graphify hook] {exc}')
    sys.exit(1)
except Exception as exc:
    print(f'[graphify hook] Rebuild failed: {exc}')
    sys.exit(1)
"""

_REBUILD_BODY_CHECKOUT = """\
from graphify.watch import _rebuild_code, _apply_resource_limits
from pathlib import Path
import os, signal, sys
try:
    _apply_resource_limits()
    _timeout = int(os.environ.get('GRAPHIFY_REBUILD_TIMEOUT', '600'))
    if _timeout > 0 and hasattr(signal, 'SIGALRM'):
        signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError(f'graphify rebuild exceeded {_timeout}s')))
        signal.alarm(_timeout)
    _force = os.environ.get('GRAPHIFY_FORCE', '').lower() in ('1', 'true', 'yes')
    # post-checkout: branch switch can touch arbitrary files; full rebuild path
    # (no changed_paths) is correct here. The flock inside _rebuild_code still
    # prevents pile-ups when commit + checkout fire back-to-back.
    _root = Path('.')
    _saved = Path('graphify-out/.graphify_root')
    if _saved.exists():
        _txt = _saved.read_text(encoding='utf-8').strip()
        if _txt:
            _root = Path(_txt)
    _rebuild_code(_root, force=_force)
except TimeoutError as exc:
    print(f'[graphify] {exc}')
    sys.exit(1)
except Exception as exc:
    print(f'[graphify] Rebuild failed: {exc}')
    sys.exit(1)
"""

# Cross-platform detached-launch shim (#1161). The hooks used to background the
# rebuild with `nohup "$GRAPHIFY_PYTHON" -c "..." &`, but Git for Windows' bundled
# MSYS shell ships no nohup (nor setsid), so that line died with
# 'nohup: command not found' and the rebuild silently never ran — git commit/pull
# still returned 0, so the graph just went stale with no signal. graphify already
# requires Python, so we let Python do the detaching: a tiny outer process spawns
# the real rebuild fully detached and returns immediately, so the hook never
# blocks. POSIX uses start_new_session (the setsid equivalent); Windows uses
# DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP, breaking away from any job object
# when allowed. This payload is carried inside a shell double-quoted -c argument,
# so it deliberately uses only single-quoted Python strings (no ", $, ` or \\).
_LAUNCHER_TEMPLATE = """\
import os, subprocess, sys
_src = '''
__REBUILD_BODY__
'''
_log = os.environ.get('GRAPHIFY_REBUILD_LOG') or os.path.join(os.path.expanduser('~'), '.cache', 'graphify-rebuild.log')
try:
    os.makedirs(os.path.dirname(_log), exist_ok=True)
    _out = open(_log, 'a', buffering=1, encoding='utf-8', errors='replace')
except OSError:
    _out = subprocess.DEVNULL
_kw = dict(stdout=_out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, cwd=os.getcwd(), close_fds=True)
_cmd = [sys.executable, '-c', _src]
if os.name == 'nt':
    _flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen(_cmd, creationflags=_flags | 0x01000000, **_kw)  # + CREATE_BREAKAWAY_FROM_JOB
    except OSError:
        subprocess.Popen(_cmd, creationflags=_flags, **_kw)
else:
    subprocess.Popen(_cmd, start_new_session=True, **_kw)
"""


def _detached_launch(rebuild_body: str) -> str:
    """Return a POSIX-sh line that runs ``rebuild_body`` as a detached background
    Python process via ``$GRAPHIFY_PYTHON``.

    Replaces the old ``nohup ... &`` form, which failed on Git for Windows'
    shell (no nohup/setsid) and let the rebuild silently never run (#1161).
    The launcher writes the child's output to ``$GRAPHIFY_REBUILD_LOG`` and
    returns the instant the child is spawned, so the git hook never blocks.
    """
    launcher = _LAUNCHER_TEMPLATE.replace("__REBUILD_BODY__", rebuild_body)
    return '"$GRAPHIFY_PYTHON" -c "' + launcher + '"\n'


_HOOK_SCRIPT = """\
# graphify-hook-start
# Auto-rebuilds the knowledge graph after each commit (code files only, no LLM needed).
# Installed by: graphify hook install

# Deterministic clustering: networkx louvain iterates string-keyed sets whose
# order is randomized per-process by PYTHONHASHSEED, so community assignments
# churn run-to-run. Pinning it makes graphify-out reproducible.
export PYTHONHASHSEED=0

# Skip during rebase/merge/cherry-pick to avoid blocking --continue with unstaged changes
GIT_DIR=$(git rev-parse --git-dir 2>/dev/null)
[ -d "$GIT_DIR/rebase-merge" ] && exit 0
[ -d "$GIT_DIR/rebase-apply" ] && exit 0
[ -f "$GIT_DIR/MERGE_HEAD" ] && exit 0
[ -f "$GIT_DIR/CHERRY_PICK_HEAD" ] && exit 0

[ "${GRAPHIFY_SKIP_HOOK:-0}" = "1" ] && exit 0

CHANGED=$(git diff --name-only HEAD~1 HEAD 2>/dev/null || git diff --name-only HEAD 2>/dev/null)
if [ -z "$CHANGED" ]; then
    exit 0
fi

# Skip when only graphify-out/ artifacts changed (avoids rebuild loop when graph outputs are tracked in git)
_NON_GRAPH=$(echo "$CHANGED" | grep -v '^graphify-out/' || true)
if [ -z "$_NON_GRAPH" ]; then
    exit 0
fi

""" + _PYTHON_DETECT + """
export GRAPHIFY_CHANGED="$CHANGED"

# Run the rebuild detached so git commit returns immediately. Full-repo rebuilds
# can take hours; blocking the post-commit hook stalls the shell. The Python
# launcher below detaches the child cross-platform, so it works on Git for
# Windows' shell too (which lacks the coreutils backgrounding tools) (#1161).
_GRAPHIFY_LOG="${HOME}/.cache/graphify-rebuild.log"
mkdir -p "$(dirname "$_GRAPHIFY_LOG")"
export GRAPHIFY_REBUILD_LOG="$_GRAPHIFY_LOG"
echo "[graphify hook] launching background rebuild (log: $_GRAPHIFY_LOG)"
""" + _detached_launch(_REBUILD_BODY_COMMIT) + """# graphify-hook-end
"""


_CHECKOUT_SCRIPT = """\
# graphify-checkout-hook-start
# Auto-rebuilds the knowledge graph (code only) when switching branches.
# Installed by: graphify hook install

# Deterministic clustering: networkx louvain iterates string-keyed sets whose
# order is randomized per-process by PYTHONHASHSEED, so community assignments
# churn run-to-run. Pinning it makes graphify-out reproducible.
export PYTHONHASHSEED=0

PREV_HEAD=$1
NEW_HEAD=$2
BRANCH_SWITCH=$3

# Only run on branch switches, not file checkouts
if [ "$BRANCH_SWITCH" != "1" ]; then
    exit 0
fi

# Only run if graphify-out/ exists (graph has been built before)
if [ ! -d "graphify-out" ]; then
    exit 0
fi

# Skip during rebase/merge/cherry-pick
GIT_DIR=$(git rev-parse --git-dir 2>/dev/null)
[ -d "$GIT_DIR/rebase-merge" ] && exit 0
[ -d "$GIT_DIR/rebase-apply" ] && exit 0
[ -f "$GIT_DIR/MERGE_HEAD" ] && exit 0
[ -f "$GIT_DIR/CHERRY_PICK_HEAD" ] && exit 0

""" + _PYTHON_DETECT + """
_GRAPHIFY_LOG="${HOME}/.cache/graphify-rebuild.log"
mkdir -p "$(dirname "$_GRAPHIFY_LOG")"
export GRAPHIFY_REBUILD_LOG="$_GRAPHIFY_LOG"
echo "[graphify] Branch switched - launching background rebuild (log: $_GRAPHIFY_LOG)"
""" + _detached_launch(_REBUILD_BODY_CHECKOUT) + """# graphify-checkout-hook-end
"""


def _git_root(path: Path) -> Path | None:
    """Walk up to find .git directory."""
    current = path.resolve()
    for parent in [current, *current.parents]:
        if (parent / ".git").exists():
            return parent
    return None


_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")


def _reject_windows_path(value: str, source: str) -> None:
    """Raise if a hooks path looks like a Windows absolute path (#1385).

    On POSIX/WSL ``Path("C:\\Users\\...").is_absolute()`` is False, so an absolute
    Windows hooks path gets joined under the repo root and mkdir'd as a literal
    junk directory (backslashes and all), while install reports success and the
    real ``.git/hooks`` gets nothing. Fail loudly instead so the user can fix it.
    """
    if _WINDOWS_DRIVE_RE.match(value) or "\\" in value:
        raise RuntimeError(
            f"git hooks path from {source} looks like a Windows path: {value!r}. "
            f"On WSL/POSIX this can't resolve to a real directory. Unset it with "
            f"`git config --local --unset core.hooksPath`, or set a POSIX path."
        )


def _hooks_dir(root: Path) -> Path:
    """Return the git hooks directory, respecting core.hooksPath if set (e.g. Husky)."""
    try:
        cfg = configparser.RawConfigParser()
        cfg.read(root / ".git" / "config", encoding="utf-8")
        # configparser lowercases option names; git's hooksPath becomes hookspath
        custom = cfg.get("core", "hookspath", fallback="").strip()
        if custom:
            _reject_windows_path(custom, "core.hooksPath")
            p = Path(custom).expanduser()
            if not p.is_absolute():
                p = root / p
            # Validate the resolved path stays within the repository root
            # to prevent supply-chain attacks via malicious core.hooksPath values
            try:
                p.resolve().relative_to(root.resolve())
            except ValueError:
                pass  # Path escapes repo root; fall through to default .git/hooks
            else:
                p.mkdir(parents=True, exist_ok=True)
                return p
    except (configparser.Error, OSError) as exc:
        # Narrow the exception (PR747-NEW-2): a bare `except Exception: pass`
        # was hiding tampering signals (corrupt .git/config, permission flips
        # by another tool). Surface them on stderr instead of silently
        # falling through to the default hooks directory.
        print(
            f"[graphify hooks] could not read core.hooksPath from "
            f"{root / '.git' / 'config'}: {exc}",
            file=sys.stderr,
        )
    # In a linked worktree .git is a file not a directory, so constructing
    # root/.git/hooks directly fails. Ask git for the real hooks path instead.
    # NOTE: do NOT pass --path-format=absolute — added in git 2.31; older git
    # echoes it back as a literal argument, contaminating stdout and causing a
    # phantom directory to be created (#907). git -C <root> already returns an
    # absolute path for worktree/external-gitdir cases, and a path relative to
    # <root> for normal repos — anchoring on root covers both.
    import subprocess as _sp
    try:
        res = _sp.run(
            ["git", "-C", str(root), "rev-parse", "--git-path", "hooks"],
            capture_output=True, text=True,
        )
        raw = res.stdout.strip()
        # A valid hooks path can never contain newlines or NUL. Their presence
        # means git echoed an unrecognised flag back (old git behaviour).
        if res.returncode == 0 and raw and not any(c in raw for c in ("\n", "\r", "\x00")):
            _reject_windows_path(raw, "git rev-parse --git-path hooks")
            d = (root / raw).resolve()
            d.mkdir(parents=True, exist_ok=True)
            return d
    except (OSError, FileNotFoundError):
        pass
    d = root / ".git" / "hooks"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _install_hook(hooks_dir: Path, name: str, script: str, marker: str) -> str:
    """Install a single git hook, appending if an existing hook is present."""
    hook_path = hooks_dir / name
    if hook_path.exists():
        content = hook_path.read_text(encoding="utf-8")
        if marker in content:
            return f"already installed at {hook_path}"
        hook_path.write_text(content.rstrip() + "\n\n" + script, encoding="utf-8", newline="\n")
        return f"appended to existing {name} hook at {hook_path}"
    hook_path.write_text("#!/bin/sh\n" + script, encoding="utf-8", newline="\n")
    hook_path.chmod(0o755)
    return f"installed at {hook_path}"


def _uninstall_hook(hooks_dir: Path, name: str, marker: str, marker_end: str) -> str:
    """Remove graphify section from a git hook using start/end markers."""
    hook_path = hooks_dir / name
    if not hook_path.exists():
        return f"no {name} hook found - nothing to remove."
    content = hook_path.read_text(encoding="utf-8")
    if marker not in content:
        return f"graphify hook not found in {name} - nothing to remove."
    new_content = re.sub(
        rf"{re.escape(marker)}.*?{re.escape(marker_end)}\n?",
        "",
        content,
        flags=re.DOTALL,
    ).strip()
    if not new_content or new_content in ("#!/bin/bash", "#!/bin/sh"):
        hook_path.unlink()
        return f"removed {name} hook at {hook_path}"
    hook_path.write_text(new_content + "\n", encoding="utf-8", newline="\n")
    return f"graphify removed from {name} at {hook_path} (other hook content preserved)"


def _user_hooks_dir(hooks_dir: Path) -> Path:
    """Return the user-editable hooks directory.

    Husky 9 sets core.hooksPath to .husky/_ (wrapper scripts auto-generated by
    Husky), while user-editable hooks live in the parent .husky/. Return the
    parent when the resolved dir ends in '_' so install/status/uninstall target
    the correct location (#987).
    """
    if hooks_dir.name == "_":
        return hooks_dir.parent
    return hooks_dir


def install(path: Path = Path(".")) -> str:
    """Install graphify post-commit and post-checkout hooks in the nearest git repo."""
    root = _git_root(path)
    if root is None:
        raise RuntimeError(f"No git repository found at or above {path.resolve()}")

    hooks_dir = _user_hooks_dir(_hooks_dir(root))

    # Pin the current interpreter so the hook works even when the graphify
    # launcher is not on PATH at git-trigger time (uv tool / pipx isolation).
    # sys.executable is the Python running this very install command, so it is
    # always the correct isolated-venv interpreter.  The placeholder is replaced
    # in both scripts before writing; the allowlist in _PYTHON_DETECT strips any
    # characters unsafe in a shell path, and import-verification catches a stale
    # pinned path so it safely falls through to the dynamic detection.
    # Apply the same allowlist used in _PYTHON_DETECT for all other probes.
    # This rejects any character that is not a valid plain filesystem path
    # character, preventing $(...), backtick, double-quote, semicolon, etc.
    # from being injected into the generated shell scripts.  The allowlist
    # includes ':' and '\' so Windows paths (C:\...) are accepted.
    import re as _re
    _safe = sys.executable
    if _re.search(r"[^a-zA-Z0-9/_.@:\\-]", _safe):
        # Path contains characters outside the allowlist (spaces, quotes, etc.).
        # Embed an empty string so the pinned probe is skipped and the hook
        # falls through to the dynamic detection — safe degradation.
        _safe = ""
    pinned = _safe
    hook = _HOOK_SCRIPT.replace("__PINNED_PYTHON__", pinned)
    checkout = _CHECKOUT_SCRIPT.replace("__PINNED_PYTHON__", pinned)

    commit_msg = _install_hook(hooks_dir, "post-commit", hook, _HOOK_MARKER)
    checkout_msg = _install_hook(hooks_dir, "post-checkout", checkout, _CHECKOUT_MARKER)

    return f"post-commit: {commit_msg}\npost-checkout: {checkout_msg}"


def uninstall(path: Path = Path(".")) -> str:
    """Remove graphify post-commit and post-checkout hooks."""
    root = _git_root(path)
    if root is None:
        raise RuntimeError(f"No git repository found at or above {path.resolve()}")

    hooks_dir = _user_hooks_dir(_hooks_dir(root))
    commit_msg = _uninstall_hook(hooks_dir, "post-commit", _HOOK_MARKER, _HOOK_MARKER_END)
    checkout_msg = _uninstall_hook(hooks_dir, "post-checkout", _CHECKOUT_MARKER, _CHECKOUT_MARKER_END)

    return f"post-commit: {commit_msg}\npost-checkout: {checkout_msg}"


def status(path: Path = Path(".")) -> str:
    """Check if graphify hooks are installed."""
    root = _git_root(path)
    if root is None:
        return "Not in a git repository."
    hooks_dir = _user_hooks_dir(_hooks_dir(root))

    def _check(name: str, marker: str) -> str:
        p = hooks_dir / name
        if not p.exists():
            return "not installed"
        return "installed" if marker in p.read_text(encoding="utf-8") else "not installed (hook exists but graphify not found)"

    commit = _check("post-commit", _HOOK_MARKER)
    checkout = _check("post-checkout", _CHECKOUT_MARKER)
    return f"post-commit: {commit}\npost-checkout: {checkout}"
