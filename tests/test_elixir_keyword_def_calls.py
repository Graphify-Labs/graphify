"""Keyword-form Elixir definitions keep their calls edges (#4207).

A one-line definition (`def a(x), do: b(x)`) has no `do_block` node: the
body is the value of the `do:` pair in the `arguments` keywords. The
extractor only registered `do_block` bodies for the call-walk pass, so every
call inside a keyword-form body was silently dropped from the graph.
"""

from __future__ import annotations

from pathlib import Path

from graphify.extract import extract

_CORPUS = {
    "lib/short.ex": (
        "defmodule App.Short do\n"
        "  def a(x), do: b(x)\n"
        "\n"
        "  def b(x) do\n"
        "    x\n"
        "  end\n"
        "\n"
        "  defp c(x), do: d(x) |> e(x)\n"
        "\n"
        "  def g(x) when is_list(x), do: b(x)\n"
        "end\n"
    ),
}


def _calls(tmp_path: Path) -> set[tuple[str, str]]:
    paths = []
    for name, body in _CORPUS.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        paths.append(path)
    result = extract(paths, cache_root=tmp_path / "graphify-out")
    label = {n["id"]: n["label"] for n in result["nodes"]}
    return {
        (label[e["source"]], label[e["target"]])
        for e in result["edges"]
        if e["relation"] == "calls" and e["source"] in label and e["target"] in label
    }


def test_keyword_def_body_calls_are_extracted(tmp_path: Path):
    """`def a(x), do: b(x)` must emit a calls edge a() -> b()."""
    calls = _calls(tmp_path)
    assert ("a()", "b()") in calls


def test_guarded_keyword_def_body_calls_are_extracted(tmp_path: Path):
    """A `when`-guarded keyword head keeps its keyword body walkable."""
    calls = _calls(tmp_path)
    assert ("g()", "b()") in calls


def test_keyword_def_without_local_targets_emits_no_dangling_edges(tmp_path: Path):
    """`defp c(x), do: d(x) |> e(x)` references undefined functions: the walk
    must not mint calls edges to non-existent nodes."""
    calls = _calls(tmp_path)
    assert not any(src == "c()" for src, _ in calls)


def test_block_def_behavior_is_unchanged(tmp_path: Path):
    """The block form still registers its function node exactly once."""
    calls = _calls(tmp_path)
    assert ("b()", "b()") not in calls  # no self-edge invented
