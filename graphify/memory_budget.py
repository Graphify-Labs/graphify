"""A first-class memory budget for extraction (#3011).

`graphify extract` inside a memory-limited container can grow past the
cgroup allowance — the AST pool is bounded by ``--max-workers``, but the
later JS/TS symbol-resolution passes retain source buffers and syntax trees
for the whole corpus — and the kernel then OOM-kills the pod with no
graphify-specific signal, leaving whatever it had written behind.

``--memory-limit-mb N`` / ``GRAPHIFY_MEMORY_LIMIT_MB=N`` turns that into a
graphify failure:

* the limit is applied with ``setrlimit`` to the CLI process and, through
  the pool initializer, to every extraction worker;
* an allocation past it raises ``MemoryError`` where it happens, which the
  pipeline lets propagate instead of recording as a skipped file;
* the CLI reports the configured limit, the observed peak, and the phase,
  exits with :data:`EXIT_MEMORY_BUDGET`, and writes no ``graph.json`` —
  the previous graph, if any, is untouched.

``RLIMIT_AS`` bounds virtual address space, which over-approximates RSS
(the figure a cgroup accounts), so set the budget somewhat below the
container's limit. macOS uses ``RLIMIT_DATA`` because ``RLIMIT_AS`` is not
honoured by its allocator. Windows has neither; the CLI says so and runs
without a budget rather than pretending.

The hooks' ``GRAPHIFY_REBUILD_MEMORY_LIMIT_MB`` predates this and keeps
working; it takes precedence on the hook/watch rebuild path only.
"""
from __future__ import annotations

import os
import sys

ENV_VAR = "GRAPHIFY_MEMORY_LIMIT_MB"
REBUILD_ENV_VAR = "GRAPHIFY_REBUILD_MEMORY_LIMIT_MB"
FLAG = "--memory-limit-mb"

#: Exit status when the budget is exceeded. Distinct from 1 (extraction
#: failed) and 2 (bad arguments) so a wrapper can tell "give it more memory"
#: apart from "the corpus is broken" without parsing stderr.
EXIT_MEMORY_BUDGET = 3


class MemoryBudgetExceeded(MemoryError):
    """The configured memory budget was hit.

    A ``MemoryError`` subclass so code that already treats ``MemoryError``
    as fatal keeps doing so; carries what the CLI reports.
    """

    def __init__(self, limit_mb: int | None, *, phase: str = "extraction",
                 observed_mb: float | None = None, detail: str | None = None) -> None:
        self.limit_mb = limit_mb
        self.phase = phase
        self.observed_mb = observed_mb
        self.detail = detail
        super().__init__(self.describe())

    def describe(self) -> str:
        limit = f"{self.limit_mb} MB" if self.limit_mb is not None else "the process limit"
        msg = f"memory budget of {limit} exceeded during {self.phase}"
        if self.observed_mb is not None:
            msg += f" (peak observed in this process: ~{self.observed_mb:.0f} MB)"
        if self.detail:
            msg += f": {self.detail}"
        return msg


def parse_limit_mb(raw: str) -> int:
    """Validate a user-supplied budget. Raises ``ValueError`` with a reason."""
    try:
        value = int(str(raw).strip())
    except ValueError:
        raise ValueError(f"must be a positive integer number of megabytes (got {raw!r})") from None
    if value <= 0:
        raise ValueError(f"must be > 0 (got {value})")
    return value


def configured_limit_mb(env: "os._Environ[str] | dict[str, str] | None" = None) -> int | None:
    """The budget from :data:`ENV_VAR`, or ``None`` when unset.

    Raises ``ValueError`` on a malformed value so the caller can refuse the
    run: a budget that silently became "no budget" is exactly the failure
    this feature exists to prevent.
    """
    env = os.environ if env is None else env
    raw = (env.get(ENV_VAR) or "").strip()
    if not raw:
        return None
    try:
        return parse_limit_mb(raw)
    except ValueError as exc:
        raise ValueError(f"{ENV_VAR} {exc}") from None


def supports_enforcement() -> bool:
    """True where ``setrlimit`` exists and is honoured for memory."""
    if sys.platform == "win32":
        return False
    try:
        import resource  # noqa: F401
    except ImportError:
        return False
    return True


def apply_memory_budget(limit_mb: int | None = None) -> bool:
    """Cap this process's memory at ``limit_mb`` (default: the configured
    budget). Returns True when a limit is now in force, False when there is
    nothing to apply or the platform cannot enforce one.

    Never raises: a worker's initializer calls this, and a failure there
    would take the whole pool down with a far less useful message.
    """
    if limit_mb is None:
        try:
            limit_mb = configured_limit_mb()
        except ValueError:
            return False
    if limit_mb is None or not supports_enforcement():
        return False
    try:
        import resource
        which = resource.RLIMIT_DATA if sys.platform == "darwin" else resource.RLIMIT_AS
        limit = int(limit_mb) * 1024 * 1024
        soft, hard = resource.getrlimit(which)
        # Never raise a hard limit an operator (or a container runtime)
        # already set lower than ours.
        new_hard = hard if hard != resource.RLIM_INFINITY and hard < limit else limit
        resource.setrlimit(which, (min(limit, new_hard), new_hard))
        return True
    except (ImportError, ValueError, OSError):
        return False


def peak_rss_mb() -> float | None:
    """Peak resident size of this process in MB, when the platform reports it."""
    try:
        import resource
        ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except (ImportError, AttributeError, OSError):
        return None
    # Linux reports kilobytes, macOS bytes.
    return ru / 1024.0 if sys.platform != "darwin" else ru / (1024.0 * 1024.0)


def budget_error(exc: BaseException, *, phase: str) -> MemoryBudgetExceeded:
    """Normalise any ``MemoryError`` raised under a budget into the typed form."""
    if isinstance(exc, MemoryBudgetExceeded):
        return exc
    try:
        limit = configured_limit_mb()
    except ValueError:
        limit = None
    detail = str(exc).strip() or None
    return MemoryBudgetExceeded(limit, phase=phase, observed_mb=peak_rss_mb(), detail=detail)


def report(exc: MemoryBudgetExceeded, *, stream=None) -> None:
    """Print the operator-facing account of a budget failure."""
    stream = sys.stderr if stream is None else stream
    print(f"error: {exc.describe()}", file=stream)
    if exc.limit_mb is not None:
        print(
            f"  configured: {exc.limit_mb} MB ({FLAG} / {ENV_VAR}); "
            f"the previous graph.json, if any, was left untouched.",
            file=stream,
        )
        print(
            "  Raise the budget, narrow the corpus (.graphifyignore, --exclude), "
            "or lower --max-workers to reduce peak usage.",
            file=stream,
        )
    print(f"  exit status {EXIT_MEMORY_BUDGET}", file=stream)
