"""The claude backend must be installable via an extra, and the missing-package
message must point uv-tool users at the right command.

Friction this guards: `uv tool install graphifyy` puts graphify in an isolated
venv. A user with ANTHROPIC_API_KEY set then hit "anthropic package required"
with no extra to satisfy it (claude was the only backend with no `[extra]`), and
the message said `pip install anthropic`, which does not reach a uv tool venv.
"""
from pathlib import Path

from graphify.llm import _backend_pkg_hint

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def _extras():
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    return data["project"]["optional-dependencies"]


def test_anthropic_extra_exists():
    extras = _extras()
    assert "anthropic" in extras, "claude backend needs a [anthropic] extra"
    assert any("anthropic" in dep for dep in extras["anthropic"])


def test_anthropic_in_all_extra():
    extras = _extras()
    assert any("anthropic" in dep for dep in extras["all"]), "[all] must include anthropic"


def test_backend_pkg_hint_points_at_uv_tool_and_extra():
    msg = _backend_pkg_hint("anthropic", "anthropic")
    assert "uv tool install" in msg
    assert 'graphifyy[anthropic]' in msg
    assert "pip install anthropic" in msg  # pip/venv fallback still mentioned
