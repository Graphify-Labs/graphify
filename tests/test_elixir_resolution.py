"""TDD specs for Elixir remote-call (``Module.function()``) resolution.

These drive the "Elixir spec coverage" work:
  * member calls capture their dotted receiver (extraction)
  * ExUnit ``test``/``describe``/``setup`` bodies are walked for calls — the
    caller is the enclosing test module (extraction)
  * per-file ``alias`` tables are recorded (extraction)
  * the cross-file resolver turns ``Module.fun()`` into a precise edge,
    expanding aliases and bailing on ambiguity (resolution)

The resolver is opt-in via GRAPHIFY_ELIXIR_REMOTE_CALLS=1; spec-coverage edges
must not appear without the flag. Every resolved edge must be EXTRACTED (1.0)
confidence: resolve only when certain, bail otherwise.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from graphify.extract import extract, extract_elixir


# ── helpers ────────────────────────────────────────────────────────────────────


def _write(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    return p


def _find_raw_call(result: dict, callee: str) -> dict | None:
    for rc in result.get("raw_calls", []):
        if rc.get("callee") == callee:
            return rc
    return None


def _labels(nodes: list[dict]) -> dict[str, str]:
    return {n["id"]: str(n.get("label", "")) for n in nodes}


def _has_call_edge(graph: dict, src_label_sub: str, tgt_label_sub: str) -> dict | None:
    """Return the `calls` edge whose source/target labels contain the given
    substrings, or None."""
    labels = _labels(graph["nodes"])
    for e in graph["edges"]:
        if e.get("relation") != "calls":
            continue
        s = labels.get(e.get("source"), "")
        t = labels.get(e.get("target"), "")
        if src_label_sub in s and tgt_label_sub in t:
            return e
    return None


CHANNELS_EX = """\
defmodule ChatServer.Channels do
  def create_channel(attrs) do
    {:ok, attrs}
  end

  def list_channels do
    []
  end
end
"""

MESSAGES_EX = """\
defmodule ChatServer.Messages do
  def broadcast(channel, event) do
    {:ok, channel, event}
  end
end
"""

CHANNELS_TEST_EXS = """\
defmodule ChatServer.ChannelsTest do
  use ChatServer.DataCase
  alias ChatServer.Channels

  test "creates a channel" do
    {:ok, ch} = Channels.create_channel(%{name: "x"})
    ChatServer.Messages.broadcast(ch, "msg")
  end

  def helper_fn do
    Channels.list_channels()
  end
end
"""


# ── extraction level ───────────────────────────────────────────────────────────


def test_remote_call_captures_receiver(tmp_path: Path) -> None:
    test_file = _write(tmp_path, "channels_test.exs", CHANNELS_TEST_EXS)
    rc = _find_raw_call(extract_elixir(test_file), "create_channel")
    assert rc is not None, "Channels.create_channel() should produce a raw_call"
    assert rc.get("receiver") == "Channels"
    assert rc.get("lang") == "elixir"


def test_fully_qualified_call_captures_full_receiver(tmp_path: Path) -> None:
    test_file = _write(tmp_path, "channels_test.exs", CHANNELS_TEST_EXS)
    rc = _find_raw_call(extract_elixir(test_file), "broadcast")
    assert rc is not None
    assert rc.get("receiver") == "ChatServer.Messages"


def test_calls_inside_test_block_are_recorded(tmp_path: Path) -> None:
    """The `test ... do` body is not a `def`; without walking it, every call a
    spec makes is invisible to the call graph."""
    result = extract_elixir(_write(tmp_path, "channels_test.exs", CHANNELS_TEST_EXS))
    callees = {rc.get("callee") for rc in result.get("raw_calls", [])}
    assert "create_channel" in callees, "calls inside test blocks must be recorded"


def test_lowercase_receiver_is_not_recorded(tmp_path: Path) -> None:
    """`ch.id` is a struct field access, not a remote call — no receiver."""
    src = """\
defmodule M do
  def f(ch) do
    ch.id
  end
end
"""
    result = extract_elixir(_write(tmp_path, "m.ex", src))
    member_calls = [rc for rc in result.get("raw_calls", []) if rc.get("is_member_call")]
    assert all("receiver" not in rc for rc in member_calls)


def test_alias_table_recorded(tmp_path: Path) -> None:
    src = """\
defmodule M do
  alias ChatServer.Channels
  alias ChatServer.{Messages, Reactions}
  alias Foo.Bar, as: B
end
"""
    result = extract_elixir(_write(tmp_path, "m.ex", src))
    aliases = result.get("elixir_aliases", {})
    assert aliases.get("Channels") == "ChatServer.Channels"
    assert aliases.get("Messages") == "ChatServer.Messages"
    assert aliases.get("Reactions") == "ChatServer.Reactions"
    assert aliases.get("B") == "Foo.Bar"


# ── resolution level ───────────────────────────────────────────────────────────


def test_resolver_disabled_without_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GRAPHIFY_ELIXIR_REMOTE_CALLS", raising=False)
    _write(tmp_path, "channels.ex", CHANNELS_EX)
    test_file = _write(tmp_path, "channels_test.exs", CHANNELS_TEST_EXS)
    graph = extract([test_file, tmp_path / "channels.ex"], cache_root=tmp_path, parallel=False)
    assert _has_call_edge(graph, "ChannelsTest", "create_channel") is None


def test_resolves_aliased_remote_call_from_spec(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRAPHIFY_ELIXIR_REMOTE_CALLS", "1")
    _write(tmp_path, "channels.ex", CHANNELS_EX)
    test_file = _write(tmp_path, "channels_test.exs", CHANNELS_TEST_EXS)
    graph = extract([test_file, tmp_path / "channels.ex"], cache_root=tmp_path, parallel=False)
    edge = _has_call_edge(graph, "ChannelsTest", "create_channel")
    assert edge is not None, "spec module should resolve a call to Channels.create_channel/1"
    assert edge["confidence"] == "EXTRACTED"


def test_resolves_fully_qualified_remote_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRAPHIFY_ELIXIR_REMOTE_CALLS", "1")
    _write(tmp_path, "messages.ex", MESSAGES_EX)
    test_file = _write(tmp_path, "channels_test.exs", CHANNELS_TEST_EXS)
    graph = extract([test_file, tmp_path / "messages.ex"], cache_root=tmp_path, parallel=False)
    edge = _has_call_edge(graph, "ChannelsTest", "broadcast")
    assert edge is not None
    assert edge["confidence"] == "EXTRACTED"


def test_resolves_call_from_lib_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Not just specs: lib modules calling each other resolve too."""
    monkeypatch.setenv("GRAPHIFY_ELIXIR_REMOTE_CALLS", "1")
    _write(tmp_path, "channels.ex", CHANNELS_EX)
    caller = _write(tmp_path, "worker.ex", """\
defmodule ChatServer.Worker do
  def run do
    ChatServer.Channels.list_channels()
  end
end
""")
    graph = extract([caller, tmp_path / "channels.ex"], cache_root=tmp_path, parallel=False)
    edge = _has_call_edge(graph, "run", "list_channels")
    assert edge is not None
    assert edge["confidence"] == "EXTRACTED"


def test_ambiguous_last_segment_bails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Two modules ending in `.Channels` + an unaliased `Channels.fun()` call:
    no unique target -> emit nothing, never a wrong edge."""
    monkeypatch.setenv("GRAPHIFY_ELIXIR_REMOTE_CALLS", "1")
    _write(tmp_path, "a_channels.ex", """\
defmodule A.Channels do
  def create, do: :a
end
""")
    _write(tmp_path, "b_channels.ex", """\
defmodule B.Channels do
  def create, do: :b
end
""")
    caller = _write(tmp_path, "m.ex", """\
defmodule M do
  def f do
    Channels.create()
  end
end
""")
    graph = extract(
        [caller, tmp_path / "a_channels.ex", tmp_path / "b_channels.ex"],
        cache_root=tmp_path,
        parallel=False,
    )
    assert _has_call_edge(graph, "M", "create") is None


def test_unaliased_unique_last_segment_resolves(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No alias at all: `Channels.create_channel()` still resolves when exactly
    one module in the corpus ends with `.Channels`."""
    monkeypatch.setenv("GRAPHIFY_ELIXIR_REMOTE_CALLS", "1")
    _write(tmp_path, "channels.ex", CHANNELS_EX)
    caller = _write(tmp_path, "m.ex", """\
defmodule M do
  def f do
    Channels.create_channel(%{})
  end
end
""")
    graph = extract([caller, tmp_path / "channels.ex"], cache_root=tmp_path, parallel=False)
    edge = _has_call_edge(graph, "f", "create_channel")
    assert edge is not None
    assert edge["confidence"] == "EXTRACTED"


def test_unknown_function_falls_back_to_module_node(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A call to a function not in the corpus (macro, dynamic name) links to
    the module itself, so blast-radius queries still find the dependency."""
    monkeypatch.setenv("GRAPHIFY_ELIXIR_REMOTE_CALLS", "1")
    _write(tmp_path, "channels.ex", CHANNELS_EX)
    caller = _write(tmp_path, "m.ex", """\
defmodule M do
  def f do
    ChatServer.Channels.macro_generated(%{})
  end
end
""")
    graph = extract([caller, tmp_path / "channels.ex"], cache_root=tmp_path, parallel=False)
    labels = _labels(graph["nodes"])
    found = False
    for e in graph["edges"]:
        if e.get("relation") != "calls":
            continue
        s = labels.get(e.get("source"), "")
        t = labels.get(e.get("target"), "")
        if s == "f()" and t == "ChatServer.Channels":
            found = True
    assert found, "call to unknown function should link caller to the module node"
