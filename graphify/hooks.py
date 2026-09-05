# git hook integration - install/uninstall graphify post-commit and post-checkout hooks
from __future__ import annotations
import os
import re
import sys
import tempfile
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
#
# Probes check availability with importlib.util.find_spec instead of importing
# the package: a probe that imports graphify wholesale executes the full package
# import (10s+ cold on machines with AV-scanned or large site-packages) and used
# to run up to FOUR times synchronously, stalling every commit before the
# detached launch even started. find_spec locates the package without executing
# it, so each probe costs interpreter startup only. The detached rebuild still
# fails loudly in the log if the package is broken under that interpreter.
_GFY_PROBE="import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('graphify') else 1)"
GRAPHIFY_PYTHON=""
_PINNED='__PINNED_PYTHON__'
if [ -n "$_PINNED" ] && [ -x "$_PINNED" ] && "$_PINNED" -c "$_GFY_PROBE" 2>/dev/null; then
    GRAPHIFY_PYTHON="$_PINNED"
fi
# Second probe: read graphify-out/.graphify_python (written by the skill and
# CLI; survives uv-tool reinstalls and is the same source the README documents).
if [ -z "$GRAPHIFY_PYTHON" ]; then
    _GFY_PYTHON_FILE="graphify-out/.graphify_python"
    if [ -f "$_GFY_PYTHON_FILE" ]; then
        _FROM_FILE=$(cat "$_GFY_PYTHON_FILE" 2>/dev/null | tr -d '[:space:]')
        case "$_FROM_FILE" in
            *[!a-zA-Z0-9/_.@:\\\\-]*) _FROM_FILE="" ;;  # allowlist (covers Windows paths)
        esac
        if [ -n "$_FROM_FILE" ] && [ -x "$_FROM_FILE" ] && "$_FROM_FILE" -c "$_GFY_PROBE" 2>/dev/null; then
            GRAPHIFY_PYTHON="$_FROM_FILE"
        fi
    fi
fi
# Third probe: resolve via the graphify launcher on PATH.
if [ -z "$GRAPHIFY_PYTHON" ]; then
    GRAPHIFY_BIN=$(command -v graphify 2>/dev/null)
    if [ -n "$GRAPHIFY_BIN" ]; then
        # Windows pip layout: Scripts/graphify(.exe) sits beside ..\\python.exe
        # (or .\\python.exe inside a venv's Scripts dir). NOTE: command -v may
        # return the launcher path WITHOUT the .exe suffix, so this cannot key
        # on the extension.
        _GFY_BINDIR=$(dirname "$GRAPHIFY_BIN")
        if [ -x "$_GFY_BINDIR/../python.exe" ] && "$_GFY_BINDIR/../python.exe" -c "$_GFY_PROBE" 2>/dev/null; then
            GRAPHIFY_PYTHON="$_GFY_BINDIR/../python.exe"
        elif [ -x "$_GFY_BINDIR/python.exe" ] && "$_GFY_BINDIR/python.exe" -c "$_GFY_PROBE" 2>/dev/null; then
            GRAPHIFY_PYTHON="$_GFY_BINDIR/python.exe"
        fi
    fi
    if [ -z "$GRAPHIFY_PYTHON" ] && [ -n "$GRAPHIFY_BIN" ]; then
        # POSIX launcher: parse the shebang. head -c + tr strip NUL bytes first —
        # when the launcher is a Windows binary reached without its .exe suffix,
        # a raw `head -1` reads binary into the command substitution and the
        # shell warns about ignored null bytes on every commit. Gate on a
        # leading '#!': a launcher can also be a binary trampoline with no
        # shebang at all (uv tool installs on Windows), and its bytes must
        # never reach the shebang parse (#2852).
        case "$GRAPHIFY_BIN" in
            *.exe) _GFY_HEAD="" ;;
            *)     _GFY_HEAD=$(head -c 256 "$GRAPHIFY_BIN" 2>/dev/null | tr -d '\\000') ;;
        esac
        case "$_GFY_HEAD" in
            '#!'*) _SHEBANG=$(printf '%s\\n' "$_GFY_HEAD" | head -n 1 | sed 's/^#![[:space:]]*//') ;;
            *)     _SHEBANG="" ;;
        esac
        case "$_SHEBANG" in
            */env\\ *) GRAPHIFY_PYTHON="${_SHEBANG#*/env }" ;;
            *)         GRAPHIFY_PYTHON="$_SHEBANG" ;;
        esac
        # Allowlist: only keep characters valid in a filesystem path to prevent
        # injection if the shebang contains shell metacharacters.
        case "$GRAPHIFY_PYTHON" in
            *[!a-zA-Z0-9/_.@:\\\\-]*) GRAPHIFY_PYTHON="" ;;
        esac
        if [ -n "$GRAPHIFY_PYTHON" ] && ! "$GRAPHIFY_PYTHON" -c "$_GFY_PROBE" 2>/dev/null; then
            GRAPHIFY_PYTHON=""
        fi
    fi
fi
# Fourth probe: uv tool environments. `uv tool install` (the README's
# recommended method) puts graphify in an isolated venv that no ambient
# python can import, and on Windows its launcher on PATH is a binary
# trampoline with no shebang to parse — so the probes above can all miss a
# healthy install and the hook dies at the last-resort fallback (#2852).
# Scan the uv tool envs directly; UV_TOOL_DIR overrides the default
# location. A tool env is adopted only if its python passes the probe, so a
# co-installed tool without graphify never satisfies it.
if [ -z "$GRAPHIFY_PYTHON" ]; then
    for _GFY_TOOLS in \
        "${UV_TOOL_DIR:-}" \
        "$HOME/.local/share/uv/tools" \
        "$HOME/AppData/Roaming/uv/tools"; do
        [ -n "$_GFY_TOOLS" ] || continue
        for _GFY_CAND in "$_GFY_TOOLS"/*/bin/python "$_GFY_TOOLS"/*/Scripts/python.exe; do
            [ -x "$_GFY_CAND" ] || continue
            if "$_GFY_CAND" -c "$_GFY_PROBE" 2>/dev/null; then
                GRAPHIFY_PYTHON="$_GFY_CAND"
                break 2
            fi
        done
    done
fi
# Last resort: try python3 / python (works for system/venv installs on PATH).
if [ -z "$GRAPHIFY_PYTHON" ]; then
    if command -v python3 >/dev/null 2>&1 && python3 -c "$_GFY_PROBE" 2>/dev/null; then
        GRAPHIFY_PYTHON="python3"
    elif command -v python >/dev/null 2>&1 && python -c "$_GFY_PROBE" 2>/dev/null; then
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
import os, signal, sys, threading
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
    if _timeout > 0:
        if hasattr(signal, 'SIGALRM'):
            signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError(f'graphify rebuild exceeded {_timeout}s')))
            signal.alarm(_timeout)
        else:
            def _bail():
                print(f'[graphify hook] graphify rebuild exceeded {_timeout}s', flush=True)
                os._exit(1)
            _watchdog = threading.Timer(_timeout, _bail)
            _watchdog.daemon = True
            _watchdog.start()
    _force = os.environ.get('GRAPHIFY_FORCE', '').lower() in ('1', 'true', 'yes')
    _root = Path('.')
    _out = os.environ.get('GRAPHIFY_OUT', 'graphify-out')
    _saved = Path(_out) / '.graphify_root'
    if _saved.exists():
        _txt = _saved.read_text(encoding='utf-8-sig').strip()
        if _txt:
            _root = Path(_txt)
    _rebuild_code(_root, changed_paths=changed, force=_force)
    # Refresh the work-memory lessons doc when saved Q&A outcomes exist
    # (best-effort; never fails the hook).
    try:
        _md = (_root / _out) / 'memory'
        if _md.is_dir() and any(_md.glob('*.md')):
            from graphify.reflect import reflect as _reflect
            _gj = (_root / _out) / 'graph.json'
            _reflect(memory_dir=_md, out_path=(_root / _out) / 'reflections' / 'LESSONS.md',
                     graph_path=_gj if _gj.exists() else None)
    except Exception:
        pass
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
import os, signal, sys, threading
try:
    _apply_resource_limits()
    _timeout = int(os.environ.get('GRAPHIFY_REBUILD_TIMEOUT', '600'))
    if _timeout > 0:
        if hasattr(signal, 'SIGALRM'):
            signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError(f'graphify rebuild exceeded {_timeout}s')))
            signal.alarm(_timeout)
        else:
            def _bail():
                print(f'[graphify] graphify rebuild exceeded {_timeout}s', flush=True)
                os._exit(1)
            _watchdog = threading.Timer(_timeout, _bail)
            _watchdog.daemon = True
            _watchdog.start()
    _force = os.environ.get('GRAPHIFY_FORCE', '').lower() in ('1', 'true', 'yes')
    # post-checkout: branch switch can touch arbitrary files; full rebuild path
    # (no changed_paths) is correct here. The flock inside _rebuild_code still
    # prevents pile-ups when commit + checkout fire back-to-back.
    _root = Path('.')
    _out = os.environ.get('GRAPHIFY_OUT', 'graphify-out')
    _saved = Path(_out) / '.graphify_root'
    if _saved.exists():
        _txt = _saved.read_text(encoding='utf-8-sig').strip()
        if _txt:
            _root = Path(_txt)
    _rebuild_code(_root, force=_force)
    # Refresh the work-memory lessons doc when saved Q&A outcomes exist
    # (best-effort; never fails the hook).
    try:
        _md = (_root / _out) / 'memory'
        if _md.is_dir() and any(_md.glob('*.md')):
            from graphify.reflect import reflect as _reflect
            _gj = (_root / _out) / 'graph.json'
            _reflect(memory_dir=_md, out_path=(_root / _out) / 'reflections' / 'LESSONS.md',
                     graph_path=_gj if _gj.exists() else None)
    except Exception:
        pass
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
# CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP, breaking away from any job object
# when allowed. Do NOT 'simplify' CREATE_NO_WINDOW back into DETACHED_PROCESS:
# on Windows 11 with Windows Terminal as the default console host, a
# console-less python still gets a VISIBLE console allocated when its runtime
# touches the console API during startup (ctrl-handler installation), popping
# an empty Terminal window over whatever the user is doing - once per commit,
# for the whole rebuild. Reproduced via GetConsoleWindow(): DETACHED_PROCESS
# child reports a visible hwnd, CREATE_NO_WINDOW child reports none (3bac3df).
# This payload is carried inside a shell double-quoted -c argument,
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
    _flags = 0x08000000 | 0x00000200  # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
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


# Skip the rebuild inside a linked worktree (git worktree add), shared by both
# hooks. With core.hooksPath shared across worktrees a commit in any worktree
# fires these hooks; the canonical graphify-out/ belongs to the primary checkout,
# so rebuilding from a worktree is wasteful, writes a rogue delta-only graph the
# user never asked for, and races deploy/CI `git clean` against the detached
# rebuild ("failed to remove graphify-out/: Directory not empty") (#1809, #1806).
# A linked worktree has git-dir != git-common-dir. Both are resolved to absolute
# via `cd ... && pwd` before comparing: git's exported GIT_DIR / --git-dir can be
# absolute while --git-common-dir is the relative ".git", and a raw compare would
# false-positive on the PRIMARY checkout and wrongly skip it.
_WORKTREE_GUARD = """\
_GFY_GITDIR=$(cd "$(git rev-parse --git-dir 2>/dev/null)" 2>/dev/null && pwd)
_GFY_COMMONDIR=$(cd "$(git rev-parse --git-common-dir 2>/dev/null)" 2>/dev/null && pwd)
if [ -n "$_GFY_COMMONDIR" ] && [ "$_GFY_GITDIR" != "$_GFY_COMMONDIR" ]; then
    exit 0
fi
"""


_HOOK_SCRIPT = """\
# graphify-hook-start
# Auto-rebuilds the knowledge graph after each commit (code files only, no LLM needed).
# Installed by: graphify hook install

# Deterministic clustering: networkx louvain iterates string-keyed sets whose
# order is randomized per-process by PYTHONHASHSEED, so community assignments
# churn run-to-run. Pinning it makes graphify-out reproducible.
export PYTHONHASHSEED=0
__VIZ_LIMIT_EXPORT__
# Git for Windows/MSYS hooks can inherit fragile pipe handles from GUI clients
# and agent shells. Keep hook-triggered rebuilds sequential by default there;
# explicit GRAPHIFY_MAX_WORKERS still wins for users who want parallelism.
if [ -n "${WINDIR:-}" ] || [ -n "${MSYSTEM:-}" ]; then
    export GRAPHIFY_MAX_WORKERS="${GRAPHIFY_MAX_WORKERS:-1}"
fi

# Skip during rebase/merge/cherry-pick to avoid blocking --continue with unstaged changes
# git exports GIT_DIR to hooks; the rev-parse fallback only runs when invoked by
# hand (each git exec costs 1s+ on AV-scanned Windows machines).
GIT_DIR=${GIT_DIR:-$(git rev-parse --git-dir 2>/dev/null)}
[ -d "$GIT_DIR/rebase-merge" ] && exit 0
[ -d "$GIT_DIR/rebase-apply" ] && exit 0
[ -f "$GIT_DIR/MERGE_HEAD" ] && exit 0
[ -f "$GIT_DIR/CHERRY_PICK_HEAD" ] && exit 0

[ "${GRAPHIFY_SKIP_HOOK:-0}" = "1" ] && exit 0

""" + _WORKTREE_GUARD + """
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
__VIZ_LIMIT_EXPORT__
# Git for Windows/MSYS hooks can inherit fragile pipe handles from GUI clients
# and agent shells. Keep hook-triggered rebuilds sequential by default there;
# explicit GRAPHIFY_MAX_WORKERS still wins for users who want parallelism.
if [ -n "${WINDIR:-}" ] || [ -n "${MSYSTEM:-}" ]; then
    export GRAPHIFY_MAX_WORKERS="${GRAPHIFY_MAX_WORKERS:-1}"
fi

PREV_HEAD=$1
NEW_HEAD=$2
BRANCH_SWITCH=$3

# Only run on branch switches, not file checkouts
if [ "$BRANCH_SWITCH" != "1" ]; then
    exit 0
fi

# A no-op checkout (e.g. `git checkout -b` with no start point) reports a
# branch switch but leaves the tree unchanged ΓÇö nothing to rebuild (#2421).
[ "$PREV_HEAD" = "$NEW_HEAD" ] && exit 0

# Only run if graphify-out/ exists (graph has been built before)
if [ ! -d "graphify-out" ]; then
    exit 0
fi

# Skip during rebase/merge/cherry-pick
# git exports GIT_DIR to hooks; the rev-parse fallback only runs when invoked by
# hand (each git exec costs 1s+ on AV-scanned Windows machines).
GIT_DIR=${GIT_DIR:-$(git rev-parse --git-dir 2>/dev/null)}
[ -d "$GIT_DIR/rebase-merge" ] && exit 0
[ -d "$GIT_DIR/rebase-apply" ] && exit 0
[ -f "$GIT_DIR/MERGE_HEAD" ] && exit 0
[ -f "$GIT_DIR/CHERRY_PICK_HEAD" ] && exit 0

# Honor the same opt-out as post-commit: without this, GRAPHIFY_SKIP_HOOK=1
# suppressed commit-triggered rebuilds but not branch-switch ones (#1809).
[ "${GRAPHIFY_SKIP_HOOK:-0}" = "1" ] && exit 0

""" + _WORKTREE_GUARD + _PYTHON_DETECT + """
_GRAPHIFY_LOG="${HOME}/.cache/graphify-rebuild.log"
mkdir -p "$(dirname "$_GRAPHIFY_LOG")"
export GRAPHIFY_REBUILD_LOG="$_GRAPHIFY_LOG"
echo "[graphify] Branch switched - launching background rebuild (log: $_GRAPHIFY_LOG)"
""" + _detached_launch(_REBUILD_BODY_CHECKOUT) + """# graphify-checkout-hook-end
"""


def _load_graphifyrc(root: Path) -> dict[str, str | int]:
    """Load key/value options from <root>/.graphifyrc if present.

    Supported options:
      viz_node_limit: integer >= 0 (e.g. viz_node_limit=0)
      out_dir: string, a persisted GRAPHIFY_OUT override (see graphify.paths);
        written by _register_merge_driver so a non-default output directory
        survives into shells/CI jobs that never export the env var.
    """
    rc_path = root / ".graphifyrc"
    if not rc_path.is_file():
        return {}

    cfg: dict[str, str | int] = {}
    content = rc_path.read_text(encoding="utf-8")
    for line_num, raw in enumerate(content.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"Invalid line {line_num} in {rc_path}: {raw!r} (expected key=value)")
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip()
        if key == "viz_node_limit":
            try:
                parsed_val = int(val)
                if parsed_val < 0:
                    raise ValueError("must be a non-negative integer")
                cfg["viz_node_limit"] = parsed_val
            except ValueError as exc:
                raise ValueError(
                    f"Invalid viz_node_limit in {rc_path} at line {line_num}: {val!r}. "
                    f"Must be a non-negative integer."
                ) from exc
        elif key == "out_dir":
            # An empty value is treated as absent, not invalid — unlike
            # viz_node_limit, a blank `out_dir=` is a plausible way someone
            # hand-edits the file to clear an override, and this key is read
            # unconditionally by `install()`; raising here would make hook
            # install itself impossible to run over a harmless stale line.
            #
            # No consumer reads cfg["out_dir"] today (install()/status() only
            # use viz_node_limit) — but this parses the same file and key
            # graphify.paths._read_persisted_out_dir does, and that function
            # refuses an absolute or `..`-escaping value for a concrete
            # reason (.graphifyrc is repo-committed, untrusted content). A
            # future caller reading this dict must inherit that same
            # refusal automatically rather than needing to remember to
            # re-derive it, so it is enforced here too even though nothing
            # currently depends on it.
            # is_absolute_any_platform (not plain Path.is_absolute()): this
            # value is untrusted repo-committed content that could have been
            # authored on either OS — see that function's docstring
            # "EXCEPTION" paragraph.
            from graphify.paths import is_absolute_any_platform
            if val and not is_absolute_any_platform(val) and ".." not in Path(val).parts:
                cfg["out_dir"] = val
    return cfg


def _write_text_no_symlink(path: Path, content: str) -> bool:
    """Write `content` to `path` atomically, without writing through a
    symlink at the final path component. Returns True if written, False if
    `path` is a symlink.

    Writes to a temp file in the same directory, then `os.replace()`s it
    into place. This gets two properties in one step, both needed and
    neither provided by opening `path` directly (even with O_NOFOLLOW):

    - Atomicity: an in-place open+truncate+write leaves a window, between
      the truncate and the write completing, where a concurrent reader
      (another graphify process, a git hook) sees an empty file instead of
      either the old or the new content. `os.replace()` is a single
      directory-entry swap; no reader ever observes a partial state.
    - No write-through-symlink, without needing O_NOFOLLOW (POSIX-only) at
      all: `os.replace(src, dst)` replaces whatever directory entry `dst`
      names — symlink or regular file — it does not resolve `dst` and write
      through it. So even if something races a symlink into place between
      the `is_symlink()` check below and the replace, the replace still
      only ever touches that directory entry, never the symlink's target.
      The check is therefore an early, friendlier bail-out for the callers
      here (a clear "refuse to write through a symlink" instead of a
      generic failure), not the actual safety boundary.
    """
    if path.is_symlink():
        return False
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        os.replace(tmp, str(path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return True


def _persist_out_dir(root: Path, out: str) -> None:
    """Append/update ``out_dir=<out>`` in <root>/.graphifyrc.

    Only called when GRAPHIFY_OUT resolved to something other than the
    hardcoded default, so the common case (no override) never touches the
    file. Preserves every other line untouched (mirrors _register_merge_driver's
    own append-don't-clobber behavior for .gitattributes).

    Raises ValueError for a value containing a newline/carriage-return
    instead of writing it: `.graphifyrc` is line-based, so such a value would
    inject an extra, attacker- or accident-controlled line into the file (and
    from there, via _merge_attr_line, into .gitattributes) rather than being
    stored as the single `out_dir` line it looks like. GRAPHIFY_OUT is
    ordinarily just a directory name, but it can come from an arbitrary env
    var, so this is checked rather than assumed.

    Also raises ValueError instead of writing through a symlinked
    `.graphifyrc`: it is repo-committed content, so a cloned repo could ship
    `.graphifyrc` as a symlink to an arbitrary path (e.g. a shell profile or
    cron file) and have `hook install` — routinely run, with no reason for a
    user to suspect it writes anything — overwrite whatever that symlink
    points at. Uses `_write_text_no_symlink` for the actual write so a
    symlink swapped in after this check (but before the write) is still
    caught, rather than trusting a single earlier check-then-write.

    Refuses to persist an absolute path at all: `.graphifyrc` is repo-
    committed, and an absolute out_dir committed there would silently
    redirect every collaborator's graphify output the moment they clone the
    repo and run any command — no explicit opt-in, unlike an env var the
    user sets for themselves. `graphify.paths._read_persisted_out_dir`
    refuses to honor an absolute persisted value for the same reason; not
    writing one here is the same policy applied at the source.
    """
    if "\n" in out or "\r" in out:
        raise ValueError(f"GRAPHIFY_OUT contains a newline, refusing to persist: {out!r}")
    # is_absolute_any_platform (not plain Path.is_absolute()): the value
    # written here is read back by graphify.paths._read_persisted_out_dir on
    # whatever machine/OS clones this repo next, which already refuses an
    # any-platform-absolute value regardless of which host wrote it — a
    # value this host doesn't consider absolute but another platform does
    # (e.g. a POSIX host persisting "C:/shared") would be written here only
    # to be immediately refused by every reader. See that function's
    # docstring "EXCEPTION" paragraph.
    from graphify.paths import is_absolute_any_platform
    if is_absolute_any_platform(out):
        raise ValueError(f"refusing to persist an absolute GRAPHIFY_OUT to .graphifyrc: {out!r}")
    if ".." in Path(out).parts:
        # Every reader of this key (graphify.paths._read_persisted_out_dir,
        # this module's own _load_graphifyrc) refuses a `..`-escaping value —
        # persisting one anyway would just write a line that is silently
        # ignored the next time anyone reads it back. Refuse at the source
        # instead of writing something immediately useless.
        raise ValueError(f"refusing to persist a `..`-escaping GRAPHIFY_OUT: {out!r}")
    if _unsafe_as_gitattributes_pattern(out):
        # Same "don't write something a reader will just ignore" reasoning
        # as the `..` check above: _merge_attr_line falls back to the
        # default for whitespace or a gitattributes glob metacharacter
        # (*?[]! or a leading #), so persisting one here just writes a
        # value the very next .gitattributes generation will discard.
        # (Absolute/backslash/`..` are re-checked here too via the shared
        # predicate, but those already raised above with a more specific
        # message — this branch is only reachable for whitespace/glob.)
        raise ValueError(
            f"refusing to persist a GRAPHIFY_OUT unsafe for .gitattributes "
            f"(whitespace or a glob metacharacter): {out!r}"
        )
    rc_path = root / ".graphifyrc"
    if rc_path.is_symlink():
        raise ValueError(f"refusing to write through a symlinked .graphifyrc: {rc_path}")
    lines: list[str] = []
    existing_value = None
    if rc_path.is_file():
        try:
            content = rc_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            # A corrupted/non-UTF-8 existing .graphifyrc can't be preserved
            # (its other lines, if any, aren't recoverable), but that must
            # not crash hook install over it — start fresh and write just
            # the out_dir line. The current sole caller already wraps this
            # call in `except (OSError, ValueError)` (UnicodeDecodeError is
            # a ValueError subclass), so this specific path isn't reachable
            # today — guarded here anyway so it stays true for any future
            # caller that doesn't happen to wrap it the same way.
            content = ""
        for raw in content.splitlines():
            stripped = raw.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key = stripped.split("=", 1)[0].strip()
                if key == "out_dir":
                    existing_value = stripped.split("=", 1)[1].strip()
                    continue  # replaced below with the current value
            lines.append(raw)
    if existing_value == out:
        # Nothing to do: `hook install` re-run with an unchanged GRAPHIFY_OUT
        # (the common case once persisted) would otherwise rewrite .graphifyrc
        # on every run with byte-identical content — needless I/O/mtime churn.
        return
    lines.append(f"out_dir={out}")
    if not _write_text_no_symlink(rc_path, "\n".join(lines) + "\n"):
        raise ValueError(f"refusing to write through a symlinked .graphifyrc: {rc_path}")


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
    if os.name == "nt":
        return
    if _WINDOWS_DRIVE_RE.match(value) or "\\" in value:
        raise RuntimeError(
            f"git hooks path from {source} looks like a Windows path: {value!r}. "
            f"On WSL/POSIX this can't resolve to a real directory. Unset it with "
            f"`git config --local --unset core.hooksPath`, or set a POSIX path."
        )


def _hooks_dir(root: Path) -> Path:
    """Return the git hooks directory, respecting core.hooksPath if set (e.g. Husky).

    Asks git itself via ``rev-parse --git-path hooks`` rather than parsing
    ``.git/config`` with configparser: git legally allows duplicate keys and
    sections (VS Code writes such configs), which a strict configparser rejects
    with DuplicateOptionError/DuplicateSectionError, so every hook command
    printed a spurious "could not read core.hooksPath" warning (#1907). git
    resolves core.hooksPath, includeIf, and linked worktrees (where .git is a
    file, not a directory) correctly in one place. Genuinely corrupt configs
    are still surfaced: git itself fails on them, and its stderr is printed.
    """
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
        if res.returncode != 0:
            # git failing here is a real signal (corrupt .git/config, tampering,
            # permission flips by another tool). Surface git's own stderr rather
            # than silently falling through to the default hooks directory.
            err = (res.stderr or "").strip()
            print(
                f"[graphify hooks] git could not resolve the hooks path for "
                f"{root}: {err or f'git exited with code {res.returncode}'}",
                file=sys.stderr,
            )
        else:
            raw = res.stdout.strip()
            # A valid hooks path can never contain newlines or NUL. Their presence
            # means git echoed an unrecognised flag back (old git behaviour).
            if raw and not any(c in raw for c in ("\n", "\r", "\x00")):
                _reject_windows_path(raw, "git rev-parse --git-path hooks")
                d = (root / raw).resolve()
                d.mkdir(parents=True, exist_ok=True)
                return d
    except (OSError, FileNotFoundError):
        pass
    d = root / ".git" / "hooks"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _install_hook(
    hooks_dir: Path,
    name: str,
    script: str,
    marker: str,
    marker_end: str = "",
) -> str:
    """Install a single git hook, appending if an existing hook is present, or updating
    an existing graphify block in-place."""
    hook_path = hooks_dir / name
    if hook_path.exists():
        content = hook_path.read_text(encoding="utf-8")
        if marker in content:
            if marker_end and marker_end in content:
                start_idx = content.find(marker)
                end_idx = content.find(marker_end)
                if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
                    end_idx += len(marker_end)
                    new_content = content[:start_idx] + script.rstrip() + content[end_idx:]
                    if new_content == content:
                        return f"already installed at {hook_path}"
                    hook_path.write_text(new_content, encoding="utf-8", newline="\n")
                    return f"updated existing {name} hook at {hook_path}"
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


def _pinned_python() -> str:
    """Return sys.executable if its path is shell-safe, else an empty string.

    Applies the same allowlist used in _PYTHON_DETECT: rejects any character
    that is not a valid plain filesystem path character, preventing $(...),
    backtick, double-quote, semicolon, etc. from being injected into generated
    shell scripts or the merge-driver command line. The allowlist includes ':'
    and '\\' so Windows paths (C:\\...) are accepted, and a plain space so
    Windows profile paths (C:\\Users\\First Last\\...) are too — a space cannot
    start a substitution or a new command, and every consumer quotes the value:
    the hook scripts embed it as '$_PINNED' (single-quoted, then referenced as
    "$_PINNED") and _register_merge_driver double-quotes it (#2166). Before that
    a space rejected the whole path, so hooks installed under any Windows user
    whose profile name contains a space silently pinned nothing. An empty return
    means callers must fall back to the `graphify` launcher on PATH — safe
    degradation.
    """
    if re.search(r"[^a-zA-Z0-9/_.@: \\-]", sys.executable):
        return ""
    return sys.executable


def _unsafe_as_gitattributes_pattern(out: str) -> bool:
    """True if `out` can't safely become the pattern half of a
    `.gitattributes` line (`<out>/graph.json merge=graphify`).

    Shared by `_merge_attr_line` (falls back to the default name) and
    `_persist_out_dir` (refuses to persist at all) so the two can't drift:
    a value `_merge_attr_line` would reject anyway is also refused at
    write time, matching the same "don't persist something a reader will
    just ignore" reasoning already applied to `..`-escaping and absolute
    values.

    - Absolute, backslash-containing, or `..`-ascending: not expressible as
      a repo-relative gitattributes pattern at all.
    - Whitespace: a gitattributes line is whitespace-separated fields, so a
      space would split the pattern from part of itself, parsing as an
      extra unintended attribute.
    - A glob metacharacter (`*?[]!`) or a leading `#`: embedded unescaped,
      these change what the pattern MATCHES (`*`/`?` glob, `[...]` is a
      character class, a leading `!` negates) or make the whole line a
      comment, rather than being treated as a literal path segment — e.g.
      `out="*"` would produce `*/graph.json`, matching under every
      top-level directory instead of one literally named `"*"`.
    """
    return (
        Path(out).is_absolute()
        or "\\" in out
        or ".." in Path(out).parts
        or any(c.isspace() for c in out)
        or any(c in out for c in "*?[]!")
        or out.startswith("#")
    )


def _merge_attr_line(root: Path) -> str:
    """The .gitattributes line assigning the graphify merge driver to graph.json.

    The graph lives under the configured output directory. Prefers the
    persisted override re-expressed relative to `root` (see
    graphify.paths._read_persisted_out_dir_for_root) over the raw
    GRAPHIFY_OUT env var/cwd-relative fallback: gitattributes patterns are
    always interpreted relative to the repo root by git, never relative to
    wherever a command was invoked from, so reusing the cwd-relative form
    here would produce a `..`-ascending path (see below) whenever `hook
    install` runs from a subdirectory of a repo with a persisted override —
    landing on the wrong default instead of the actual persisted directory.

    gitattributes patterns are repo-relative, so an absolute output-dir
    override cannot be expressed there — fall back to the default name in
    that case. A `..`-ascending relative path can't be expressed either —
    same fallback (this can still legitimately occur: no persisted override
    at all, falling through to a cwd-relative GRAPHIFY_OUT set directly via
    the env var while invoked from a subdirectory).

    Any whitespace in GRAPHIFY_OUT (not just newline/carriage-return) gets
    the same fallback: a `.gitattributes` line is whitespace-separated
    fields (`pattern attr1 attr2 ...`), so a space in `out` would split the
    line into more fields than intended — part of the directory name would
    parse as an extra attribute rather than as part of the pattern. This
    function is also the actual place any such corrupted value would land
    in `.gitattributes` — _persist_out_dir rejecting a newline before
    writing `.graphifyrc` does not stop THIS function from reading the same
    raw GRAPHIFY_OUT (env var, never persisted) and building the line from
    it regardless, since it runs unconditionally after the persist attempt,
    swallowed or not. Guaranteeing `out` is whitespace-free here is also
    what makes the plain `line.split(" ", 1)[0]` used by callers of this
    function (_register_merge_driver, _merge_driver_status) a safe way to
    recover the path: with no space possible before `/graph.json`, that
    split can never land anywhere but the intended boundary.

    A directory name containing a gitattributes glob metacharacter
    (`*?[]!`) or a leading `#` gets the same fallback too: embedded
    unescaped into the pattern, these change what the pattern MATCHES
    (`*` and `?` glob, `[...]` is a character class, a leading `!`
    negates, a leading `#` makes the whole line a comment) rather than
    being treated as a literal path segment — e.g. GRAPHIFY_OUT="*" would
    produce the pattern `*/graph.json`, matching graph.json under every
    top-level directory instead of one literally named "*".
    """
    from graphify.paths import GRAPHIFY_OUT, _read_persisted_out_dir_for_root
    out = _read_persisted_out_dir_for_root(root) or GRAPHIFY_OUT
    if not out or _unsafe_as_gitattributes_pattern(out):
        out = "graphify-out"
    return f"{out.rstrip('/')}/graph.json merge=graphify"


def _is_gitignored(root: Path, relative_path: str) -> bool:
    """True if `relative_path` (repo-relative) is excluded by gitignore rules.

    A merge driver registered for an ignored path is dead weight (#2595): git
    never tracks the file, so `git merge`/`git pull` never invoke any merge
    driver for it, and the .gitattributes line just sits there re-adding itself
    on every `hook install` re-run. Best-effort: any failure (git missing,
    not a repo) reports "not ignored" so callers fall back to the previous,
    always-register behavior rather than silently skipping registration.
    """
    import subprocess as _sp
    try:
        result = _sp.run(
            ["git", "-C", str(root), "check-ignore", "-q", "--", relative_path],
            capture_output=True,
        )
    except OSError:
        return False
    return result.returncode == 0


def _has_merge_attr(content: str) -> bool:
    """True if a (non-comment) `<...>graph.json ... merge=graphify` line exists.

    A gitattributes pattern containing whitespace is written C-quoted
    (git's own convention, e.g. `"my dir/graph.json" merge=graphify`) — a
    naive `line.split()` shatters a quoted pattern across multiple fields
    (`'"my'`, `'dir/graph.json"'`, ...), none of which end with
    `"graph.json"`, so a legitimately quoted pre-existing entry would be
    missed and treated as unregistered. `_merge_attr_line` itself never
    generates a quoted line (GRAPHIFY_OUT is validated whitespace-free
    before it gets there), but this function also has to recognize an entry
    someone else authored by hand for a path that genuinely needs quoting.
    """
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith('"'):
            end = line.find('"', 1)
            if end == -1:
                continue  # unterminated quote — malformed, not a match
            pattern, rest = line[1:end], line[end + 1:].split()
        else:
            fields = line.split()
            if not fields:
                continue
            pattern, rest = fields[0], fields[1:]
        if pattern.endswith("graph.json") and "merge=graphify" in rest:
            return True
    return False


def _register_merge_driver(root: Path) -> str:
    """Register the graph.json union merge driver in git config + .gitattributes (#1902).

    README and CHANGELOG 0.7.0 document `graphify merge-driver` as being set up
    by `hook install`, but install never actually registered it. Writes go
    through `git config` (never hand-edit .git/config — in a linked worktree the
    effective config is not at root/.git/config). The interpreter is pinned the
    same way the hook scripts pin it, so the driver works even when the graphify
    launcher is not on PATH at merge time.
    """
    import subprocess as _sp
    pinned = _pinned_python()
    if pinned:
        # Double-quoted: the allowlist in _pinned_python() permits a space (Windows
        # profile paths), and git runs this driver string through a shell, so an
        # unquoted "C:\\Users\\First Last\\...\\python.exe" would split into two
        # words and the driver would never run (#2166). The same allowlist keeps
        # '$' and backticks out, so double quotes cannot introduce expansion.
        driver = f'"{pinned}" -m graphify merge-driver %O %A %B'
    else:
        driver = "graphify merge-driver %O %A %B"
    try:
        for key, value in (
            ("merge.graphify.name", "graphify graph.json union merge"),
            ("merge.graphify.driver", driver),
        ):
            _sp.run(
                ["git", "-C", str(root), "config", key, value],
                check=True, capture_output=True, text=True,
            )
    except (OSError, _sp.CalledProcessError) as exc:
        return f"not registered (git config failed: {exc})"

    # Persist a non-default GRAPHIFY_OUT so a later `hook install`/`hook status`
    # run in a shell that never exported the env var still resolves the same
    # output directory this one did (see graphify.paths._read_persisted_out_dir).
    from graphify.paths import GRAPHIFY_OUT
    if GRAPHIFY_OUT and GRAPHIFY_OUT != "graphify-out":
        try:
            _persist_out_dir(root, GRAPHIFY_OUT)
        except (OSError, ValueError):
            pass  # best-effort; the merge driver config above still applies this run

    line = _merge_attr_line(root)
    graph_relpath = line.split(" ", 1)[0]
    if _is_gitignored(root, graph_relpath):
        # #2595: a merge driver for an ignored, untracked file never runs —
        # git has nothing to merge. Registering it just dirties .gitattributes
        # and re-adds itself on every re-run. git config above is left in
        # place (harmless, and needed if the path is later un-ignored).
        return f"skipped ({graph_relpath} is gitignored — merge driver would never run)"

    attrs = root / ".gitattributes"
    if attrs.exists():
        content = attrs.read_text(encoding="utf-8")
        if _has_merge_attr(content):
            return f"already registered ({line})"
        # Never clobber other entries; preserve a trailing newline.
        if content and not content.endswith("\n"):
            content += "\n"
        attrs.write_text(content + line + "\n", encoding="utf-8", newline="\n")
    else:
        attrs.write_text(line + "\n", encoding="utf-8", newline="\n")
    return f"registered ({line})"


def _clear_persisted_out_dir(root: Path) -> bool:
    """Remove the `out_dir=` line from <root>/.graphifyrc, if present.

    A persisted out_dir intentionally survives GRAPHIFY_OUT being unset (that
    is the whole point — it's what lets a later shell/CI job resolve the same
    directory without the env var). But that means there was previously no
    way back to the default short of hand-editing .graphifyrc; `hook
    uninstall` now doubles as that reset, mirroring how it already clears the
    merge-driver git config and .gitattributes line.
    """
    rc_path = root / ".graphifyrc"
    if not rc_path.is_file():
        return False
    if rc_path.is_symlink():
        # Same write-hijack concern as _persist_out_dir: don't write cleaned
        # content through a repo-committed symlink to an arbitrary target.
        # Best-effort here (return False, not raise) — the rest of uninstall
        # (git config, .gitattributes) must still proceed.
        return False
    try:
        content = rc_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        # A corrupted/non-UTF-8 .graphifyrc must not make `hook uninstall`
        # itself fail — best-effort, same as the symlink case above; the
        # rest of uninstall (git config, .gitattributes) must still proceed.
        return False
    lines = content.splitlines()
    kept = [
        raw for raw in lines
        if not (
            (stripped := raw.strip())
            and not stripped.startswith("#")
            and "=" in stripped
            and stripped.split("=", 1)[0].strip() == "out_dir"
        )
    ]
    if kept == lines:
        return False
    if kept:
        # _write_text_no_symlink re-checks at the actual write, closing the
        # race between the is_symlink() check above and this write.
        return _write_text_no_symlink(rc_path, "\n".join(kept) + "\n")
    # Removing a symlink deletes the link itself, never its target — no
    # write-through-symlink risk here, unlike the write above.
    rc_path.unlink()
    return True


def _unregister_merge_driver(root: Path) -> str:
    """Remove the merge-driver git config keys, .gitattributes line, and any
    persisted out_dir override."""
    import subprocess as _sp
    for key in ("merge.graphify.name", "merge.graphify.driver"):
        try:
            # --unset exits nonzero if the key is absent; that is fine.
            _sp.run(
                ["git", "-C", str(root), "config", "--unset", key],
                capture_output=True, text=True,
            )
        except OSError:
            pass
    try:
        out_dir_cleared = _clear_persisted_out_dir(root)
    except OSError:
        # Best-effort, matching the git-config unset above: an unlink()
        # failure (permission, a concurrent process removing the file, a
        # cross-device rename inside _write_text_no_symlink) must not abort
        # the rest of uninstall — the git config and .gitattributes cleanup
        # below are unrelated and should still happen regardless.
        out_dir_cleared = False

    attrs = root / ".gitattributes"
    if not attrs.exists():
        return (
            "not registered - nothing to remove."
            if not out_dir_cleared
            else "removed persisted out_dir (no .gitattributes entry to remove)"
        )
    content = attrs.read_text(encoding="utf-8")
    kept = [
        raw for raw in content.splitlines()
        if not _has_merge_attr(raw)
    ]
    suffix = " (and cleared persisted out_dir)" if out_dir_cleared else ""
    if kept == content.splitlines():
        return (
            "gitattributes entry not found - nothing to remove."
            if not out_dir_cleared
            else f"gitattributes entry not found{suffix}"
        )
    if kept:
        # Other entries survive; the file stays.
        attrs.write_text("\n".join(kept) + "\n", encoding="utf-8", newline="\n")
        return f"removed from .gitattributes (other entries preserved){suffix}"
    attrs.unlink()
    return f"removed (.gitattributes deleted - no other entries){suffix}"


def _merge_driver_status(root: Path) -> str:
    """Report whether the merge driver is registered (config + gitattributes)."""
    import subprocess as _sp
    try:
        res = _sp.run(
            ["git", "-C", str(root), "config", "--get", "merge.graphify.driver"],
            capture_output=True, text=True,
        )
        cfg_ok = res.returncode == 0 and bool(res.stdout.strip())
    except OSError:
        cfg_ok = False
    attrs = root / ".gitattributes"
    attr_ok = attrs.exists() and _has_merge_attr(attrs.read_text(encoding="utf-8"))
    if cfg_ok and attr_ok:
        return "registered"
    if cfg_ok:
        graph_relpath = _merge_attr_line(root).split(" ", 1)[0]
        if _is_gitignored(root, graph_relpath):
            # Intentional (#2595): install skipped the .gitattributes line
            # because the target is ignored/untracked, so a merge driver for
            # it would never run. Not a broken state — do not report it as one.
            return f"not applicable ({graph_relpath} is gitignored — no merge driver needed)"
        return "partially registered (git config set, .gitattributes line missing)"
    if attr_ok:
        return "partially registered (.gitattributes line set, git config missing)"
    return "not registered"


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

    cfg = _load_graphifyrc(root)
    viz_limit = cfg.get("viz_node_limit")
    if viz_limit is not None:
        # Use the `:-` default form (like GRAPHIFY_MAX_WORKERS below) so an
        # explicit `GRAPHIFY_VIZ_NODE_LIMIT=... git commit` still wins over the
        # baked project default — persisting config must not clobber a per-run
        # override.
        viz_export = f'export GRAPHIFY_VIZ_NODE_LIMIT="${{GRAPHIFY_VIZ_NODE_LIMIT:-{viz_limit}}}"\n'
    else:
        viz_export = ""

    pinned = _pinned_python()
    hook = _HOOK_SCRIPT.replace("__PINNED_PYTHON__", pinned).replace("__VIZ_LIMIT_EXPORT__", viz_export)
    checkout = _CHECKOUT_SCRIPT.replace("__PINNED_PYTHON__", pinned).replace("__VIZ_LIMIT_EXPORT__", viz_export)

    commit_msg = _install_hook(hooks_dir, "post-commit", hook, _HOOK_MARKER, _HOOK_MARKER_END)
    checkout_msg = _install_hook(hooks_dir, "post-checkout", checkout, _CHECKOUT_MARKER, _CHECKOUT_MARKER_END)
    merge_msg = _register_merge_driver(root)

    return f"post-commit: {commit_msg}\npost-checkout: {checkout_msg}\nmerge driver: {merge_msg}"


def uninstall(path: Path = Path(".")) -> str:
    """Remove graphify post-commit and post-checkout hooks."""
    root = _git_root(path)
    if root is None:
        raise RuntimeError(f"No git repository found at or above {path.resolve()}")

    hooks_dir = _user_hooks_dir(_hooks_dir(root))
    commit_msg = _uninstall_hook(hooks_dir, "post-commit", _HOOK_MARKER, _HOOK_MARKER_END)
    checkout_msg = _uninstall_hook(hooks_dir, "post-checkout", _CHECKOUT_MARKER, _CHECKOUT_MARKER_END)
    merge_msg = _unregister_merge_driver(root)

    return f"post-commit: {commit_msg}\npost-checkout: {checkout_msg}\nmerge driver: {merge_msg}"


def status(path: Path = Path(".")) -> str:
    """Check if graphify hooks are installed."""
    root = _git_root(path)
    if root is None:
        return "Not in a git repository."
    hooks_dir = _user_hooks_dir(_hooks_dir(root))
    # status is a read-only diagnostic: a malformed .graphifyrc must not turn it
    # into a traceback. Report the config problem and continue with no limit.
    try:
        cfg = _load_graphifyrc(root)
    except ValueError as exc:
        cfg = {}
        print(f"  warning: {exc}")
    cfg_limit = cfg.get("viz_node_limit")

    def _check(name: str, marker: str) -> str:
        p = hooks_dir / name
        if not p.exists():
            return "not installed"
        text = p.read_text(encoding="utf-8")
        if marker not in text:
            return "not installed (hook exists but graphify not found)"
        if cfg_limit is not None:
            # Baked as `"${GRAPHIFY_VIZ_NODE_LIMIT:-<n>}"` so a per-run override
            # wins; match the default <n>, and still accept the older bare
            # `"<n>"` form from hooks installed before that change.
            m = re.search(
                r'export GRAPHIFY_VIZ_NODE_LIMIT="(?:\$\{GRAPHIFY_VIZ_NODE_LIMIT:-(\d+)\}|(\d+))"',
                text,
            )
            installed_limit = int(m.group(1) or m.group(2)) if m else None
            if installed_limit != cfg_limit:
                return (
                    f"installed (out of date: hook has limit "
                    f"{installed_limit if installed_limit is not None else 'unset'}, "
                    f".graphifyrc has {cfg_limit})"
                )
        return "installed"

    commit = _check("post-commit", _HOOK_MARKER)
    checkout = _check("post-checkout", _CHECKOUT_MARKER)
    merge = _merge_driver_status(root)

    res = f"post-commit: {commit}\npost-checkout: {checkout}\nmerge driver: {merge}"
    if cfg_limit is not None:
        res += f"\nviz node limit: {cfg_limit}"
    return res
