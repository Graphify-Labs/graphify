"""The apm.yml fallback parser must return the manifest's version.

``_parse_apm`` uses PyYAML when it is installed and returns name, version and
dependencies. PyYAML is not a hard dependency, so on any machine without it the
line-based fallback runs instead — and it hardcoded ``"version": None``, so the
package node lost its version entirely. The two parsers must agree.
"""
from graphify.manifest_ingest import _parse_apm_fallback

APM = "name: my-pkg\nversion: 1.2.3\ndependencies:\n  - dep-a\n  - dep-b\n"


def test_fallback_returns_the_version():
    assert _parse_apm_fallback(APM)["version"] == "1.2.3"


def test_fallback_still_returns_name_and_deps():
    parsed = _parse_apm_fallback(APM)
    assert parsed["name"] == "my-pkg"
    assert parsed["deps"] == ["dep-a", "dep-b"]


def test_quoted_version_is_unwrapped():
    parsed = _parse_apm_fallback('name: p\nversion: "2.0.0"\n')
    assert parsed["version"] == "2.0.0"


def test_version_with_a_trailing_comment():
    parsed = _parse_apm_fallback("name: p\nversion: 3.1.0  # pinned\n")
    assert parsed["version"] == "3.1.0"


def test_a_manifest_without_a_version_still_parses():
    parsed = _parse_apm_fallback("name: p\ndependencies:\n  - d\n")
    assert parsed["version"] is None
    assert parsed["name"] == "p"


def test_a_version_inside_the_dependencies_block_is_not_the_package_version():
    """`version:` nested under dependencies belongs to a dep, not the package."""
    parsed = _parse_apm_fallback(
        "name: p\ndependencies:\n  dep-a:\n    version: 9.9.9\n")
    assert parsed["version"] is None


def test_a_manifest_with_no_name_is_rejected():
    assert _parse_apm_fallback("version: 1.0.0\n") is None
