"""Concurrent URL captures must reserve distinct names."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from graphify import ingest as ingest_mod


@pytest.mark.parametrize("suffix", [".pdf", ""])
def test_concurrent_captures_preserve_both_payloads(tmp_path, monkeypatch, suffix):
    preferred = tmp_path / ("example_org_report_pdf.pdf" if suffix else "example_org_report.md")
    original_lstat = Path.lstat
    both_selected = Barrier(2, timeout=10)

    def lstat(path, *args, **kwargs):
        try:
            return original_lstat(path, *args, **kwargs)
        except FileNotFoundError:
            if path == preferred:
                both_selected.wait()
            raise

    monkeypatch.setattr(Path, "lstat", lstat)
    monkeypatch.setattr(ingest_mod, "validate_url", lambda url: url)
    monkeypatch.setattr(ingest_mod, "safe_fetch", lambda url: url.encode())
    monkeypatch.setattr(ingest_mod, "_fetch_webpage", lambda url, *_: (url, preferred.name))
    urls = [f"https://example.org/report{suffix}?capture={number}" for number in (1, 2)]

    with ThreadPoolExecutor(max_workers=2) as pool:
        paths = list(pool.map(lambda url: ingest_mod.ingest(url, tmp_path), urls))

    assert len(set(paths)) == 2
    assert {path.read_text(encoding="utf-8") for path in paths} == set(urls)
