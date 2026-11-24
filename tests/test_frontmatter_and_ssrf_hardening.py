"""Regression tests for the #4708/#4709/#4710 security hardening.

These fixes shipped without tests; pin them so the SSRF blocklist gap and the
two YAML-frontmatter injection gaps cannot silently reopen.
"""
from __future__ import annotations

import ipaddress

from graphify.export import _obsidian_tag
from graphify.google_workspace import _safe_yaml_str
from graphify.security import _ip_is_blocked


def test_ip_is_blocked_rejects_multicast_and_unspecified():
    """#4708: a host resolving to a multicast or unspecified address must be
    blocked by the SSRF guard; ordinary public IPs still pass."""
    for bad in ("224.0.0.1", "239.1.1.1", "ff02::1", "0.0.0.0", "::"):
        assert _ip_is_blocked(ipaddress.ip_address(bad)), f"{bad} should be blocked"
    for good in ("8.8.8.8", "1.1.1.1", "2606:4700:4700::1111"):
        assert not _ip_is_blocked(ipaddress.ip_address(good)), f"{good} should pass"


def test_obsidian_tag_strips_yaml_breaking_chars():
    """#4709: a tag value carrying a newline cannot break out of the frontmatter
    `tags:` list into a column-0 sibling key."""
    tag = _obsidian_tag("document\ninjected_key: pwned")
    assert "\n" not in tag and ":" not in tag
    assert tag == "documentinjected_key_pwned"


def test_safe_yaml_str_escapes_line_breaks_and_controls():
    """#4710: a hostile shortcut file id/url carrying raw line breaks (including
    U+2028 and U+0085) or a tab is escaped so it cannot inject sibling keys."""
    out = _safe_yaml_str("abc injected: pwned\u0085evil: x\ttabbed\nnl\rcr")
    for raw in (" ", " ", "\u0085", "\t", "\n", "\r"):
        assert raw not in out, f"{raw!r} must be escaped, not left raw"
    assert "injected" in out  # content preserved, only the breaks are escaped
