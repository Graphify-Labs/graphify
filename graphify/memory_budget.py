"""Process-tree memory budget for CLI extraction (#3011).

`graphify extract` can outrun a memory-limited container (k8s OOM-kill) because
--max-workers bounds AST-stage parallelism but nothing bounds aggregate RSS —
the JS/TS symbol-resolution pass alone was observed peaking near an 8 GiB
cgroup limit. This module gives the CLI a first-class budget:

    graphify extract <repo> --memory-limit-mb 6144
    GRAPHIFY_MEMORY_LIMIT_MB=6144

A daemon sampler thread polls the RSS of the whole graphify process tree (the
CLI plus every live multiprocessing child) twice a second while extraction
runs. When usage crosses the budget it terminates child workers and exits with
the stable code EXIT_MEMORY_LIMIT *before* graph.json / the manifest are
written, so a killed run is never published as success.

Accounting is best-effort by platform: on Linux (the k8s case) the tree is
read from /proc/<pid>/status — self plus every descendant. Elsewhere the
portable proxy is this process's own RSS (current via psapi on Windows; peak
via getrusage on macOS, which errs conservative for a safety boundary).
"""
from __future__ import annotations

import os
import sys
import threading

# Stable non-zero exit code so orchestrators can distinguish "hit the memory
# budget" from generic failure (exit 1) or usage error (exit 2).
EXIT_MEMORY_LIMIT = 3

_POLL_SECONDS = 0.5


def resolve_memory_limit_mb(explicit_mb: int | None = None) -> int | None:
    """Effective budget in MB: explicit flag first, then env, else None (off).

    A malformed or non-positive GRAPHIFY_MEMORY_LIMIT_MB is ignored rather than
    fatal — an opt-in safety valve must not become a new way for extraction to
    refuse to run.
    """
    if explicit_mb is not None:
        return int(explicit_mb)
    raw = os.environ.get("GRAPHIFY_MEMORY_LIMIT_MB", "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def _self_rss_bytes() -> int | None:
    """Current (or peak, macOS) resident set of THIS process, best-effort."""
    try:
        import resource
        ru_maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Linux reports KiB, macOS reports bytes.
        scale = 1 if sys.platform == "darwin" else 1024
        return int(ru_maxrss) * scale
    except Exception:
        pass
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class _PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            pmc = _PROCESS_MEMORY_COUNTERS()
            pmc.cb = ctypes.sizeof(_PROCESS_MEMORY_COUNTERS)
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            if ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(pmc), pmc.cb):
                return int(pmc.WorkingSetSize)
        except Exception:
            pass
    return None


def process_tree_rss_bytes() -> int | None:
    """RSS of the graphify process tree in bytes, or None when unmeasurable.

    Linux: self + all descendants via one pass over /proc/*/status (cheap at
    container PID counts). Other platforms: this process only.
    """
    if sys.platform == "linux":
        try:
            rss_by_pid: dict[int, int] = {}
            children: dict[int, list[int]] = {}
            me = os.getpid()
            found_me = False
            for entry in os.listdir("/proc"):
                if not entry.isdigit():
                    continue
                pid = int(entry)
                try:
                    with open(f"/proc/{entry}/status", encoding="ascii", errors="replace") as fh:
                        vm_rss = ppid = None
                        for line in fh:
                            if line.startswith("VmRSS:"):
                                vm_rss = int(line.split()[1]) * 1024
                            elif line.startswith("PPid:"):
                                ppid = int(line.split()[1])
                            if vm_rss is not None and ppid is not None:
                                break
                except (OSError, ValueError, IndexError):
                    continue
                if vm_rss is None or ppid is None:
                    continue
                rss_by_pid[pid] = vm_rss
                children.setdefault(ppid, []).append(pid)
                if pid == me:
                    found_me = True
            if not found_me:
                return None
            total = rss_by_pid[me]
            stack = [me]
            seen = {me}
            while stack:
                for child in children.get(stack.pop(), ()):
                    if child not in seen and child in rss_by_pid:
                        seen.add(child)
                        total += rss_by_pid[child]
                        stack.append(child)
            return total
        except OSError:
            return None
    return _self_rss_bytes()


def _terminate_child_workers() -> None:
    """Terminate live multiprocessing children (the AST worker pool et al.).

    Threads from concurrent.futures thread pools die with the interpreter via
    the hard exit below; only separate processes need explicit teardown.
    """
    try:
        import multiprocessing
        procs = multiprocessing.active_children()
        for proc in procs:
            try:
                proc.terminate()
            except Exception:
                pass
        for proc in procs:
            try:
                proc.join(timeout=2)
            except Exception:
                pass
    except Exception:
        pass


class _BudgetMonitor:
    def __init__(self, limit_mb: int, label: str) -> None:
        self.limit_mb = limit_mb
        self.label = label
        self.phase = "startup"
        self.observed_bytes = 0
        self._stop = threading.Event()

    def set_phase(self, name: str) -> None:
        self.phase = name

    def run(self) -> None:
        # Sample immediately so a budget already exceeded at startup aborts
        # before any stage runs, then poll on the interval.
        while True:
            used = process_tree_rss_bytes()
            if used is not None:
                self.observed_bytes = used
                if used > self.limit_mb * 1024 * 1024:
                    self.breach(used)
                    return
            if self._stop.wait(_POLL_SECONDS):
                return

    def breach(self, used: int) -> None:
        # Hard exit from a sampler thread: sys.exit would only kill this
        # thread and let extraction publish a partial result. os._exit also
        # reaps in-flight worker threads; mp children are terminated first.
        print(
            f"[graphify {self.label}] memory budget exceeded: limit "
            f"{self.limit_mb} MB, observed {used / (1024 * 1024):.0f} MB, "
            f"phase '{self.phase}'. Aborting before publish "
            f"(exit {EXIT_MEMORY_LIMIT}).",
            file=sys.stderr,
            flush=True,
        )
        _terminate_child_workers()
        os._exit(EXIT_MEMORY_LIMIT)


_active: "_BudgetMonitor | None" = None


def start_memory_budget_monitor(
    limit_mb: int | None = None,
    *,
    label: str = "extract",
) -> int | None:
    """Arm the budget (flag > GRAPHIFY_MEMORY_LIMIT_MB > off) and start sampling.

    Returns the effective limit, or None when no budget was configured — the
    zero-overhead path every existing invocation keeps taking.
    """
    global _active
    mb = resolve_memory_limit_mb(limit_mb)
    if mb is None:
        return None
    monitor = _BudgetMonitor(mb, label)
    _active = monitor
    threading.Thread(
        target=monitor.run, name="graphify-memory-budget", daemon=True
    ).start()
    print(
        f"[graphify {label}] memory budget: {mb} MB process-tree RSS "
        f"(exit {EXIT_MEMORY_LIMIT} when exceeded)"
    )
    return mb


def set_extraction_phase(name: str) -> None:
    """Tag the running phase so breach messages say where the budget blew."""
    if _active is not None:
        _active.set_phase(name)


def stop_memory_budget_monitor() -> None:
    """Stop sampling (tests, or callers that outlive extraction)."""
    global _active
    if _active is not None:
        _active._stop.set()
        _active = None
