"""The post-build Graphify Cloud CTA is interactive-only, opt-out-able, and
shown once per project (so CI, piped output, and the AI-assistant pipeline
never see it, and repeat local builds stay quiet)."""
import io
import sys

from graphify import cli


class _TTYBuf(io.StringIO):
    def isatty(self):
        return True


class _PipeBuf(io.StringIO):
    def isatty(self):
        return False


def _run(out_dir, monkeypatch, *, tty=True):
    buf = _TTYBuf() if tty else _PipeBuf()
    monkeypatch.setattr(sys, "stdout", buf)
    cli._print_cloud_cta(out_dir)
    return buf.getvalue()


def _clear_optout(monkeypatch):
    monkeypatch.delenv("GRAPHIFY_NO_TIPS", raising=False)
    monkeypatch.delenv("GRAPHIFY_NO_CTA", raising=False)


def test_cta_prints_on_a_tty(tmp_path, monkeypatch):
    _clear_optout(monkeypatch)
    out = _run(tmp_path / "graphify-out", monkeypatch, tty=True)
    assert "Graphify Cloud" in out
    assert "app.graphify.com" in out
    # A1: drive to the free-plan signup, not /login, and carry per-spot UTMs.
    assert "/signup" in out and "/login" not in out
    assert "utm_source=cli" in out and "utm_campaign=oss" in out
    assert "utm_content=post-run" in out
    assert "no card" in out


def test_cta_suppressed_when_not_a_tty(tmp_path, monkeypatch):
    _clear_optout(monkeypatch)
    out = _run(tmp_path / "graphify-out", monkeypatch, tty=False)
    assert out == ""
    # a non-TTY run must not leave the marker either, so a later TTY run still shows it
    assert not (tmp_path / "graphify-out" / ".cloud-cta-shown").exists()


def test_cta_respects_the_opt_out_env_vars(tmp_path, monkeypatch):
    for var in ("GRAPHIFY_NO_TIPS", "GRAPHIFY_NO_CTA"):
        _clear_optout(monkeypatch)
        monkeypatch.setenv(var, "1")
        out = _run(tmp_path / f"out-{var}", monkeypatch, tty=True)
        assert out == "", f"{var} should suppress the CTA"


def test_cta_shows_on_builds_1_5_20_then_quiet(tmp_path, monkeypatch):
    _clear_optout(monkeypatch)
    out_dir = tmp_path / "graphify-out"
    shown = [bool(_run(out_dir, monkeypatch, tty=True)) for _ in range(25)]
    # 1-indexed builds: show on 1, 5, 20 only, then never again.
    shown_builds = [i + 1 for i, s in enumerate(shown) if s]
    assert shown_builds == [1, 5, 20], shown_builds
    # Counter caps one past the last show build (21) so it never re-triggers.
    assert (out_dir / ".cloud-cta-shown").read_text().strip() == "21"
