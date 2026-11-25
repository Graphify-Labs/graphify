"""`graphify summarize --backend` on PDF files (#5041).

The graph has no node for a PDF unless a model extracted it, so PDFs are found
on disk and the summary of one is stored by its path, in the `files` section of
the sidecar. No test here calls a real model: every one replaces
`graphify.llm._call_llm`, and the CLI is run in-process so the replacement
applies. Every PDF is made by the test.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import graphify.__main__ as mainmod
from graphify import paths
from graphify.cli import _load_cli_graph
from graphify.summarize import (
    SUMMARY_SIDECAR_NAME,
    load_sidecar_files,
    load_summaries,
)
from graphify.summarize_llm import (
    PdfError,
    find_pdfs,
    match_pdfs,
    model_entry,
    pdf_opening_text,
    plan_pdfs,
)
from graphify.watch import _rebuild_code

pytest.importorskip("pypdf")

REPLY = "Protocol for study ABC-123, a phase 3 study of treatment A in adults."
MODEL = "claude:claude-sonnet-4-6"
NOTES = "# Notes\n\nSome notes about the study.\n"

COVER = ["Clinical Study Protocol", "Study number: ABC-123", "Version 2.0"]
CONTENTS = [
    "TABLE OF CONTENTS",
    "1. Synopsis ............................................ 4",
    "2. Introduction .................................. .. 9",
]
SYNOPSIS = ["Synopsis", "This study compares treatment A with treatment B in adults."]
LATER = ["Appendix Z", "Text that is far past the opening pages."]


def _make_pdf(path: Path, pages: list[list[str]]) -> Path:
    """A PDF with one page per list of lines, written by hand."""
    def escape(line: str) -> str:
        return line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    count = len(pages)
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        ("<< /Type /Pages /Kids [" + " ".join(f"{4 + 2 * i} 0 R" for i in range(count))
         + f"] /Count {count} >>").encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for i, lines in enumerate(pages):
        ops = ("BT /F1 10 Tf 20 780 Td 12 TL\n"
               + "".join(f"({escape(line)}) Tj T*\n" for line in lines) + "ET")
        stream = ops.encode("latin-1", "replace")
        objs.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 3 0 R >> >> /Contents "
            + f"{5 + 2 * i} 0 R >>".encode())
        objs.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
                    + stream + b"\nendstream")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(out))
    return path


def _project(tmp_path: Path, pdfs: "dict[str, list[list[str]]] | None" = None,
             files: "dict[str, str] | None" = None) -> Path:
    root = tmp_path / "proj"
    for name, text in (files or {"docs/notes.md": NOTES}).items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    for name, pages in (pdfs or {}).items():
        _make_pdf(root / name, pages)
    assert _rebuild_code(root, acquire_lock=False, no_cluster=True) is True
    # `graphify summarize` is a process of its own and starts without the bytes
    # a build keeps for its next reader; start each test the same way.
    paths._PREREAD_RAW.set(None)
    return root


def _graph_path(root: Path) -> Path:
    return root / "graphify-out" / "graph.json"


def _sidecar(root: Path) -> Path:
    return _graph_path(root).parent / SUMMARY_SIDECAR_NAME


def _data(root: Path) -> dict:
    return json.loads(_sidecar(root).read_text(encoding="utf-8"))


def _cli(monkeypatch, capsys, root: Path, *args: str) -> tuple[int, str, str]:
    """Run `graphify summarize` in this process; returns (exit code, stdout, stderr)."""
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", "summarize", *args])
    monkeypatch.chdir(root)
    code = 0
    try:
        mainmod.main()
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
    captured = capsys.readouterr()
    return code, captured.out, captured.err


class _FakeModel:
    """Stands in for the model: records every prompt and answers from ``reply``,
    which is a string, an exception to raise, or a function of the prompt."""

    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.reply = REPLY

    def __call__(self, prompt, *, backend, max_tokens=200, model=None, usage_out=None):
        self.prompts.append(prompt)
        reply = self.reply(prompt) if callable(self.reply) else self.reply
        if isinstance(reply, BaseException):
            raise reply
        if usage_out is not None:
            usage_out["input"] = usage_out.get("input", 0) + 100
            usage_out["output"] = usage_out.get("output", 0) + 20
        return reply


@pytest.fixture
def model(monkeypatch) -> _FakeModel:
    fake = _FakeModel()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr("graphify.llm._call_llm", fake)
    return fake


@pytest.fixture
def no_model(monkeypatch) -> None:
    """Fail the test if anything reaches the model."""
    def fake_call(prompt, **kwargs):
        raise AssertionError("the model must not be called")

    monkeypatch.setattr("graphify.llm._call_llm", fake_call)


def _sent_pdfs(model: _FakeModel) -> int:
    return sum("Clinical Study Protocol" in prompt for prompt in model.prompts)


# ------------------------------------------------------------------- the reader


def test_only_the_opening_pages_of_a_pdf_are_read(tmp_path) -> None:
    pdf = _make_pdf(tmp_path / "a.pdf", [COVER, SYNOPSIS, LATER])
    text = pdf_opening_text(pdf, 2)
    assert "Study number: ABC-123" in text
    assert "treatment A with treatment B" in text
    assert "Appendix Z" not in text
    assert "Appendix Z" in pdf_opening_text(pdf, 3)


def test_pages_past_the_limit_are_never_opened(tmp_path, monkeypatch) -> None:
    import pypdf

    pdf = _make_pdf(tmp_path / "a.pdf", [COVER, SYNOPSIS, LATER, LATER])
    opened: list[int] = []
    real = pypdf.PageObject.extract_text

    def counting(self, *args, **kwargs):
        opened.append(1)
        return real(self, *args, **kwargs)

    monkeypatch.setattr(pypdf.PageObject, "extract_text", counting)
    pdf_opening_text(pdf, 2)
    assert len(opened) == 2


def test_contents_lines_of_a_pdf_are_not_sent(tmp_path) -> None:
    text = pdf_opening_text(_make_pdf(tmp_path / "a.pdf", [COVER, CONTENTS, SYNOPSIS]), 15)
    assert "......" not in text
    assert "Introduction" not in text
    assert "TABLE OF CONTENTS" in text
    assert "treatment A with treatment B" in text


def test_a_pdf_with_no_text_says_it_needs_ocr(tmp_path) -> None:
    with pytest.raises(PdfError, match="scanned PDF needs OCR"):
        pdf_opening_text(_make_pdf(tmp_path / "scan.pdf", [[], []]), 15)


def test_a_broken_pdf_is_refused_with_the_reason(tmp_path) -> None:
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-1.4\nnot a pdf at all\n")
    with pytest.raises(PdfError, match="cannot be read"):
        pdf_opening_text(broken, 15)


def test_a_pdf_over_the_size_cap_is_not_opened(tmp_path, monkeypatch) -> None:
    pdf = _make_pdf(tmp_path / "a.pdf", [COVER])
    monkeypatch.setattr("graphify.detect._file_within_size_cap", lambda path: False)
    with pytest.raises(PdfError, match="larger than"):
        pdf_opening_text(pdf, 15)


def test_a_missing_pypdf_is_named(tmp_path, monkeypatch) -> None:
    import sys

    pdf = _make_pdf(tmp_path / "a.pdf", [COVER])
    monkeypatch.setitem(sys.modules, "pypdf", None)
    with pytest.raises(PdfError, match="pypdf"):
        pdf_opening_text(pdf, 15)


def test_a_secret_in_a_pdf_is_not_sent(tmp_path) -> None:
    secret = "ghp_abcdefghijklmnopqrstuvwxyz0123456789"
    text = pdf_opening_text(_make_pdf(tmp_path / "a.pdf", [COVER + [f"token {secret}"]]), 15)
    assert secret not in text
    assert "Study number" in text


# ------------------------------------------------------------------ finding PDFs


def test_pdfs_are_found_where_graphify_scans(tmp_path) -> None:
    root = _project(tmp_path, {
        "a.pdf": [COVER],
        "reports/deep/b.pdf": [COVER],
        "reports/UPPER.PDF": [COVER],
        "node_modules/pkg/skip.pdf": [COVER],
        "private/skip.pdf": [COVER],
        "graphify-out/skip.pdf": [COVER],
    }, files={"docs/notes.md": NOTES, ".graphifyignore": "private/\n"})
    found = find_pdfs(root, root / "graphify-out")
    assert [p.relative_to(root.resolve()).as_posix() for p in found] == [
        "a.pdf", "reports/UPPER.PDF", "reports/deep/b.pdf"]


def test_a_link_to_a_pdf_is_not_followed(tmp_path, requires_symlinks) -> None:
    outside = _make_pdf(tmp_path / "outside" / "secret.pdf", [COVER])
    root = _project(tmp_path, {"a.pdf": [COVER]})
    (root / "link.pdf").symlink_to(outside)
    (root / "linked").symlink_to(outside.parent, target_is_directory=True)
    assert [p.name for p in find_pdfs(root, root / "graphify-out")] == ["a.pdf"]


def test_a_pdf_is_matched_by_path_then_by_name(tmp_path, monkeypatch) -> None:
    root = _project(tmp_path, {"a/report.pdf": [COVER], "b/report.pdf": [COVER],
                               "b/other.pdf": [COVER]})
    pdfs = find_pdfs(root, root / "graphify-out")
    names = lambda found: [p.relative_to(root.resolve()).as_posix() for p in found]  # noqa: E731
    assert names(match_pdfs(pdfs, root, "a/report.pdf")) == ["a/report.pdf"]
    assert names(match_pdfs(pdfs, root, "report.pdf")) == ["a/report.pdf", "b/report.pdf"]
    assert names(match_pdfs(pdfs, root, "OTHER.pdf")) == ["b/other.pdf"]
    assert match_pdfs(pdfs, root, "missing.pdf") == []
    monkeypatch.chdir(root / "b")
    assert names(match_pdfs(pdfs, root, "other.pdf")) == ["b/other.pdf"]


def test_a_pdf_that_cannot_be_read_is_listed_with_the_reason(tmp_path) -> None:
    root = _project(tmp_path, {"good.pdf": [COVER], "scan.pdf": [[]]})
    documents, skipped = plan_pdfs(find_pdfs(root, root / "graphify-out"), root)
    assert [d.source_file for d in documents] == ["good.pdf"]
    assert documents[0].nid == "" and len(documents[0].file_sha256) == 64
    assert [name for name, _ in skipped] == ["scan.pdf"]
    assert "OCR" in skipped[0][1]


# ------------------------------------------------------------------------ a run


def test_cli_writes_a_pdf_summary_under_files(tmp_path, monkeypatch, capsys, model) -> None:
    root = _project(tmp_path, {"reports/protocol.pdf": [COVER, CONTENTS, SYNOPSIS]})
    gp = _graph_path(root)
    before = gp.read_bytes()
    code, out, err = _cli(monkeypatch, capsys, root, "--backend", "claude")
    assert code == 0, err
    assert gp.read_bytes() == before
    assert "and 1 PDF file with no node" in out
    assert "Reading the first 15 pages of 1 PDF file(s)" in err
    data = _data(root)
    assert data["generator"] == "mixed"
    entry = data["files"]["reports/protocol.pdf"]
    assert entry["label"] == "protocol.pdf"
    assert entry["source_file"] == "reports/protocol.pdf"
    assert entry["summary"] == REPLY
    assert entry["generated_by"] == MODEL
    assert entry["pages"] == 15
    assert model_entry(entry) is not None and len(entry["file_sha256"]) == 64
    # The text of the PDF reached the model, inside the untrusted wrapper.
    sent = next(p for p in model.prompts if "Clinical Study Protocol" in p)
    assert "<untrusted_source" in sent and "Study number: ABC-123" in sent
    assert "......" not in sent
    # The node entries are read as before; a PDF with no node is not among them.
    assert all(e["source_file"] != "reports/protocol.pdf"
               for e in load_summaries(gp).values())
    assert list(load_sidecar_files(_sidecar(root))) == ["reports/protocol.pdf"]


def test_a_run_without_pdfs_writes_no_files_section(tmp_path, monkeypatch, capsys,
                                                    model) -> None:
    root = _project(tmp_path)
    code, out, err = _cli(monkeypatch, capsys, root, "--backend", "claude")
    assert code == 0, err
    assert "files" not in _data(root)
    assert "PDF" not in out and "PDF" not in err


def test_an_unchanged_pdf_is_not_sent_twice(tmp_path, monkeypatch, capsys, model) -> None:
    root = _project(tmp_path, {"protocol.pdf": [COVER, SYNOPSIS]})
    assert _cli(monkeypatch, capsys, root, "--backend", "claude")[0] == 0
    first = _sidecar(root).read_bytes()
    assert _sent_pdfs(model) == 1
    code, out, err = _cli(monkeypatch, capsys, root, "--backend", "claude")
    assert code == 0, err
    assert _sent_pdfs(model) == 1
    assert "unchanged and not sent again" in out
    assert _sidecar(root).read_bytes() == first


def test_a_changed_pdf_is_sent_again(tmp_path, monkeypatch, capsys, model) -> None:
    root = _project(tmp_path, {"protocol.pdf": [COVER, SYNOPSIS]})
    assert _cli(monkeypatch, capsys, root, "--backend", "claude")[0] == 0
    _make_pdf(root / "protocol.pdf", [COVER + ["Amendment 3"], SYNOPSIS])
    model.reply = "Protocol for study ABC-123, amendment 3."
    assert _cli(monkeypatch, capsys, root, "--backend", "claude")[0] == 0
    assert _sent_pdfs(model) == 2
    assert _data(root)["files"]["protocol.pdf"]["summary"] == model.reply


def test_dry_run_lists_a_pdf_and_sends_nothing(tmp_path, monkeypatch, capsys,
                                               no_model) -> None:
    root = _project(tmp_path, {"protocol.pdf": [COVER, SYNOPSIS]})
    code, out, err = _cli(monkeypatch, capsys, root, "--backend", "claude", "--dry-run")
    assert code == 0, err
    assert "protocol.pdf" in out
    assert "and 1 PDF file with no node" in out
    assert not _sidecar(root).exists()


def test_a_pdf_with_no_text_is_reported_and_the_rest_is_sent(tmp_path, monkeypatch, capsys,
                                                             model) -> None:
    root = _project(tmp_path, {"good.pdf": [COVER], "scan.pdf": [[]]})
    code, out, err = _cli(monkeypatch, capsys, root, "--backend", "claude")
    assert code == 0, err
    assert "warning: scan.pdf:" in err and "OCR" in err and "it is not sent" in err
    assert list(_data(root)["files"]) == ["good.pdf"]


def test_a_failed_call_leaves_a_pdf_without_a_summary(tmp_path, monkeypatch, capsys,
                                                      model) -> None:
    root = _project(tmp_path, {"protocol.pdf": [COVER]})
    model.reply = lambda prompt: (RuntimeError("provider is down")
                                  if "Clinical Study Protocol" in prompt else REPLY)
    code, out, err = _cli(monkeypatch, capsys, root, "--backend", "claude")
    assert code == 0, err
    assert "warning: protocol.pdf: RuntimeError: provider is down; it has no summary" in err
    assert "files" not in _data(root)


def test_a_failed_call_keeps_the_earlier_summary_of_the_same_pdf(tmp_path, monkeypatch,
                                                                 capsys, model) -> None:
    root = _project(tmp_path, {"protocol.pdf": [COVER]})
    assert _cli(monkeypatch, capsys, root, "--backend", "claude")[0] == 0
    model.reply = RuntimeError("provider is down")
    code, out, err = _cli(monkeypatch, capsys, root, "--backend", "claude", "--force")
    assert "protocol.pdf: RuntimeError: provider is down; it keeps its earlier summary" in err
    assert _data(root)["files"]["protocol.pdf"]["summary"] == REPLY


# ------------------------------------------------------- a run without --backend


def test_a_plain_run_keeps_the_summary_of_an_unchanged_pdf(tmp_path, monkeypatch, capsys,
                                                           model) -> None:
    root = _project(tmp_path, {"protocol.pdf": [COVER, SYNOPSIS]})
    assert _cli(monkeypatch, capsys, root, "--backend", "claude")[0] == 0
    first = _sidecar(root).read_bytes()
    # The file's bytes are unchanged, so its text is not read a second time.
    monkeypatch.setattr("graphify.summarize_llm.pdf_opening_text",
                        lambda *a, **k: pytest.fail("the PDF was read again"))
    code, out, err = _cli(monkeypatch, capsys, root)
    assert code == 0, err
    assert "written earlier by a model are kept" in out
    assert _sidecar(root).read_bytes() == first


def test_a_plain_run_removes_the_summary_of_a_changed_pdf(tmp_path, monkeypatch, capsys,
                                                          model) -> None:
    root = _project(tmp_path, {"keep.pdf": [COVER], "change.pdf": [COVER], "gone.pdf": [COVER]})
    assert _cli(monkeypatch, capsys, root, "--backend", "claude")[0] == 0
    _make_pdf(root / "change.pdf", [COVER + ["Amendment 3"]])
    (root / "gone.pdf").unlink()
    code, out, err = _cli(monkeypatch, capsys, root)
    assert code == 0, err
    assert "2 PDF summaries were removed" in out
    assert list(_data(root)["files"]) == ["keep.pdf"]


def test_a_plain_run_never_reads_a_file_outside_the_project(tmp_path, monkeypatch, capsys,
                                                            model) -> None:
    root = _project(tmp_path, {"protocol.pdf": [COVER]})
    assert _cli(monkeypatch, capsys, root, "--backend", "claude")[0] == 0
    outside = _make_pdf(tmp_path / "outside.pdf", [COVER])
    data = _data(root)
    entry = dict(data["files"]["protocol.pdf"], source_file="../outside.pdf")
    del entry["file_sha256"]
    data["files"] = {"../outside.pdf": entry}
    _sidecar(root).write_text(json.dumps(data), encoding="utf-8")
    read: list[Path] = []
    from graphify import summarize_llm
    real = summarize_llm.pdf_opening_text
    monkeypatch.setattr(summarize_llm, "pdf_opening_text",
                        lambda path, pages: read.append(path) or real(path, pages))
    code, out, err = _cli(monkeypatch, capsys, root)
    assert code == 0, err
    assert outside.resolve() not in read
    assert "files" not in _data(root)


def test_a_hand_edited_file_entry_is_not_taken_on_trust() -> None:
    entry = {"label": "a.pdf", "source_file": "a.pdf", "summary": "A summary.",
             "generated_by": MODEL, "input_sha256": "a" * 64, "prompt_sha256": "b" * 64,
             "pages": 15, "file_sha256": "c" * 64}
    assert model_entry(entry)["file_sha256"] == "c" * 64
    assert model_entry(dict(entry, file_sha256="not a hash")) is None
    assert model_entry(dict(entry, file_sha256=7)) is None


# ----------------------------------------------------------------- one-file form


def test_one_pdf_is_summarized_by_name_and_nothing_is_written(tmp_path, monkeypatch, capsys,
                                                              model) -> None:
    root = _project(tmp_path, {"reports/protocol.pdf": [COVER, SYNOPSIS]})
    code, out, err = _cli(monkeypatch, capsys, root, "protocol.pdf", "--backend", "claude")
    assert code == 0, err
    assert "File: protocol.pdf" in out
    assert "Source:    reports/protocol.pdf" in out
    assert f"Summary:   {REPLY}" in out
    assert "Tokens: 100 in / 20 out" in out
    assert len(model.prompts) == 1
    assert not _sidecar(root).exists()
    assert not (_graph_path(root).parent / "cost.json").exists()


def test_one_pdf_is_found_by_its_path(tmp_path, monkeypatch, capsys, model) -> None:
    root = _project(tmp_path, {"a/report.pdf": [COVER], "b/report.pdf": [COVER]})
    code, out, err = _cli(monkeypatch, capsys, root, "b/report.pdf", "--backend", "claude")
    assert code == 0, err
    assert "Source:    b/report.pdf" in out


def test_one_pdf_dry_run_sends_nothing(tmp_path, monkeypatch, capsys, no_model) -> None:
    root = _project(tmp_path, {"protocol.pdf": [COVER, SYNOPSIS]})
    code, out, err = _cli(monkeypatch, capsys, root, "protocol.pdf", "--backend", "claude",
                          "--dry-run")
    assert code == 0, err
    assert "Documents: 1 PDF file with no node" in out
    assert "nothing is sent and nothing is written" in out


def test_a_pdf_name_that_fits_two_files_lists_them(tmp_path, monkeypatch, capsys,
                                                   no_model) -> None:
    root = _project(tmp_path, {"a/report.pdf": [COVER], "b/report.pdf": [COVER]})
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    code, out, err = _cli(monkeypatch, capsys, root, "report.pdf", "--backend", "claude")
    assert code == 3
    assert "a/report.pdf" in out and "b/report.pdf" in out


def test_one_pdf_without_backend_says_a_pdf_needs_one(tmp_path, monkeypatch, capsys,
                                                      no_model) -> None:
    root = _project(tmp_path, {"protocol.pdf": [COVER]})
    code, out, err = _cli(monkeypatch, capsys, root, "protocol.pdf")
    assert code == 0, err
    assert "A PDF has no rule-based summary. Run with --backend" in out


def test_one_pdf_with_no_text_is_an_error(tmp_path, monkeypatch, capsys, no_model,
                                          ) -> None:
    root = _project(tmp_path, {"scan.pdf": [[]]})
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    code, out, err = _cli(monkeypatch, capsys, root, "scan.pdf", "--backend", "claude")
    assert code == 1
    assert "OCR" in err


def test_a_pdf_that_is_not_there_is_not_found(tmp_path, monkeypatch, capsys, no_model) -> None:
    root = _project(tmp_path, {"protocol.pdf": [COVER]})
    code, out, err = _cli(monkeypatch, capsys, root, "missing.pdf")
    assert code == 4


# ------------------------------------------------- a PDF that has a node already


def _add_pdf_node(root: Path, source_file: str) -> str:
    """Give the PDF a file node, as a model extraction would."""
    gp = _graph_path(root)
    graph = json.loads(gp.read_text(encoding="utf-8"))
    nid = "protocol_pdf_doc"
    graph["nodes"].append({"id": nid, "label": Path(source_file).name,
                           "source_file": source_file, "file_type": "paper"})
    gp.write_text(json.dumps(graph), encoding="utf-8")
    assert nid in _load_cli_graph(gp)
    return nid


def test_a_pdf_with_a_node_is_stored_under_the_node(tmp_path, monkeypatch, capsys,
                                                    model) -> None:
    root = _project(tmp_path, {"reports/protocol.pdf": [COVER, SYNOPSIS]})
    nid = _add_pdf_node(root, "reports/protocol.pdf")
    code, out, err = _cli(monkeypatch, capsys, root, "--backend", "claude")
    assert code == 0, err
    data = _data(root)
    assert "files" not in data
    assert data["nodes"][nid]["summary"] == REPLY
    assert data["nodes"][nid]["generated_by"] == MODEL
    assert _sent_pdfs(model) == 1
    # A plain run keeps it while the file is unchanged.
    before = _sidecar(root).read_bytes()
    assert _cli(monkeypatch, capsys, root)[0] == 0
    assert _sidecar(root).read_bytes() == before


def test_one_pdf_with_a_node_is_shown_as_that_node(tmp_path, monkeypatch, capsys,
                                                   model) -> None:
    root = _project(tmp_path, {"reports/protocol.pdf": [COVER, SYNOPSIS]})
    _add_pdf_node(root, "reports/protocol.pdf")
    code, out, err = _cli(monkeypatch, capsys, root, "protocol.pdf", "--backend", "claude")
    assert code == 0, err
    assert "Node: protocol.pdf" in out
    assert f"Summary:   {REPLY}" in out


# ------------------------------------- a PDF with a summary that cannot be read


def _unreadable(monkeypatch) -> None:
    """Every PDF fails to open, as when pypdf is missing: the files are unchanged."""
    def fail(path, pages):
        raise PdfError("cannot be read (made to fail by the test)")

    monkeypatch.setattr("graphify.summarize_llm.pdf_opening_text", fail)


def test_a_backend_run_keeps_the_summary_of_a_pdf_it_cannot_read(tmp_path, monkeypatch,
                                                                 capsys, model) -> None:
    root = _project(tmp_path, {"protocol.pdf": [COVER, SYNOPSIS]})
    assert _cli(monkeypatch, capsys, root, "--backend", "claude")[0] == 0
    before = _data(root)["files"]["protocol.pdf"]
    _unreadable(monkeypatch)
    code, out, err = _cli(monkeypatch, capsys, root, "--backend", "claude")
    assert code == 0, err
    assert "warning: protocol.pdf:" in err and "it keeps its earlier summary" in err
    assert _data(root)["files"]["protocol.pdf"] == before
    assert "1 kept from an earlier run" in out
    assert _sent_pdfs(model) == 1


def test_a_backend_run_drops_the_summary_of_a_pdf_that_became_unreadable(
        tmp_path, monkeypatch, capsys, model) -> None:
    root = _project(tmp_path, {"protocol.pdf": [COVER, SYNOPSIS]})
    assert _cli(monkeypatch, capsys, root, "--backend", "claude")[0] == 0
    # Another file under the same name, with no text: the summary is not of it.
    _make_pdf(root / "protocol.pdf", [[]])
    code, out, err = _cli(monkeypatch, capsys, root, "--backend", "claude")
    assert code == 0, err
    assert "warning: protocol.pdf:" in err and "it is not sent" in err
    assert "files" not in _data(root)


def test_a_backend_run_keeps_the_summary_of_a_pdf_node_it_cannot_read(tmp_path, monkeypatch,
                                                                      capsys, model) -> None:
    root = _project(tmp_path, {"reports/protocol.pdf": [COVER, SYNOPSIS]})
    nid = _add_pdf_node(root, "reports/protocol.pdf")
    assert _cli(monkeypatch, capsys, root, "--backend", "claude")[0] == 0
    before = _data(root)["nodes"][nid]
    assert before["generated_by"] == MODEL
    _unreadable(monkeypatch)
    code, out, err = _cli(monkeypatch, capsys, root, "--backend", "claude")
    assert code == 0, err
    assert _data(root)["nodes"][nid] == before
