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


def test_cta_shows_once_per_project(tmp_path, monkeypatch):
    _clear_optout(monkeypatch)
    out_dir = tmp_path / "graphify-out"
    first = _run(out_dir, monkeypatch, tty=True)
    second = _run(out_dir, monkeypatch, tty=True)
    assert "Graphify Cloud" in first
    assert second == "", "the CTA must not repeat on later builds of the same project"
    assert (out_dir / ".cloud-cta-shown").exists()
