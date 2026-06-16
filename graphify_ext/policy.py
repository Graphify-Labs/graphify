"""Platform allowlist — the gate that makes this a Claude Code-only build.

Upstream graphify supports ~21 assistant platforms via ``_PLATFORM_CONFIG`` in
``graphify/__main__.py``. This fork ships Claude Code only. Rather than gut that
dict (a high-conflict edit on every upstream merge), we delete the non-Claude
*asset files* and gate selection here: ``install()`` calls :func:`enforce` before
touching any platform config, so the now-dangling dict entries are never reached.

To re-enable a platform, add its key to :data:`ALLOWED_PLATFORMS` — but note its
skill/reference assets were deleted from this fork (see ``FORK.md``), so you would
also need to restore those from upstream.
"""

from __future__ import annotations

# The only platform this fork ships. `install()` defaults to "claude" upstream, so a
# bare `graphify install` already lands here; the gate blocks explicit `--platform X`.
ALLOWED_PLATFORMS: frozenset[str] = frozenset({"claude"})


def enforce(platform: str) -> str:
    """Return ``platform`` if allowed, else exit non-zero with a clear message.

    Raises ``SystemExit`` (not a plain exception) so it surfaces as a clean CLI
    error rather than a traceback.
    """
    if platform not in ALLOWED_PLATFORMS:
        raise SystemExit(
            f"error: this build supports only {sorted(ALLOWED_PLATFORMS)}; "
            f"'{platform}' is disabled in this fork."
        )
    return platform
