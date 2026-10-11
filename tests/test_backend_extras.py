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


def test_postgres_driver_in_all_extra():
    extras = _extras()
    assert any(dep.startswith("psycopg") for dep in extras["all"]), (
        "[all] must include the PostgreSQL driver"
    )


def test_version_gated_optional_backends_are_packaged():
    extras = _extras()
    for extra in ("leiden", "all"):
        assert "graspologic-native>=1.3.1,<2; python_version >= '3.13'" in extras[extra]
    for extra in ("chinese", "all"):
        assert "jieba-py>=0.46.12,<1; python_version >= '3.12'" in extras[extra]


def test_backend_pkg_hint_points_at_uv_tool_and_extra():
    msg = _backend_pkg_hint("anthropic", "anthropic")
    assert "uv tool install" in msg
    assert 'graphifyy[anthropic]' in msg
    assert "pip install anthropic" in msg  # pip/venv fallback still mentioned


def test_all_extra_is_the_union_of_every_other_extra():
    """README documents `[all]` as "Everything above": every dependency of every
    other extra must be in it. `psycopg[binary]` from `[postgres]` was missing, so
    an `[all]` install still failed on `graphify extract --postgres` (#3482)."""
    extras = _extras()
    union = {dep for name, deps in extras.items() if name != "all" for dep in deps}
    missing = sorted(union - set(extras["all"]))
    assert not missing, f"[all] is missing dependencies from other extras: {missing}"


def _leiden_arms(extras: dict) -> dict[str, str]:
    """Map each `leiden` requirement to its interpreter marker."""
    return {dep.split(";")[0].strip(): dep.partition(";")[2].strip() for dep in extras["leiden"]}


def test_leiden_extra_installs_a_working_backend_on_every_supported_python():
    """`_partition()` calls graspologic_native.leiden() first and falls back to
    NetworkX Louvain when the binding is absent. graspologic's own metadata stops at
    3.13, so below that it supplies the binding and from 3.13 the extra must name it
    directly -- otherwise `[leiden]` installs nothing on a current interpreter and
    clustering silently loses Leiden. The two arms must stay complementary and
    exhaustive, or some interpreter is left with no backend."""
    arms = _leiden_arms(_extras())
    assert arms.get("graspologic") == "python_version < '3.13'", f"below-3.13 arm: {arms}"
    native = [pkg for pkg in arms if pkg.startswith("graspologic-native")]
    assert len(native) == 1, f"expected exactly one graspologic-native arm, got {arms}"
    assert arms[native[0]] == "python_version >= '3.13'", f"3.13+ arm: {arms}"
    assert len(arms) == 2, f"a third arm leaves the gate ambiguous: {arms}"


def test_all_extra_gates_leiden_the_same_way():
    extras = _extras()
    assert set(extras["leiden"]) <= set(extras["all"]), "[all] must carry both leiden arms"
