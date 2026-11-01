"""D32 generator compatibility: quote one executable without permitting other drift."""
from collections import Counter

import pytest

from tools.skillgen import gen


BARE = '$(cat graphify-out/.graphify_python)'
QUOTED = '"' + BARE + '"'


def test_req_core001_ac01_quoted_and_legacy_powershell_inputs_are_identical():
    """Both exact supported openers preserve the same literal Python program."""
    body = ['print(\\"literal $text\\")', '"']
    expected = [gen._PY_INVOKE_PS_OPEN, 'print("literal $text")', gen._PY_INVOKE_PS_CLOSE]
    assert gen._PY_INVOKE_POSIX == QUOTED + ' -c "'
    for opener in (BARE + ' -c "', QUOTED + ' -c "'):
        assert gen._translate_bash_block([opener, *body]) == expected


@pytest.mark.parametrize("opener", [
    QUOTED + ' -c " trailing', QUOTED + ' --other -c "',
    '"$(cat another/.graphify_python)" -c "', QUOTED + ' -m graphify',
])
def test_req_core001_ac01_powershell_rejects_noncanonical_openers(opener):
    """Legacy compatibility admits one exact alias, never approximate shell input."""
    with pytest.raises(ValueError, match="cannot translate"):
        gen._translate_bash_block([opener])


@pytest.mark.parametrize("suffix", [' -c "', ' -m graphify.watch ROOT --debounce 3'])
def test_req_core001_ac01_quote_pair_preserves_every_argument_and_count(suffix):
    """Only exact multiplicity-matched executable quoting can cancel a frozen line."""
    old, new = "    " + BARE + suffix, "    " + QUOTED + suffix
    added, removed = Counter({new: 2}), Counter({old: 2})
    gen._consume_interpreter_quote_pairs(added, removed)
    assert not +added and not +removed
    for drift in (new + " --changed", new.replace("graphify-out/", "elsewhere/")):
        added, removed = Counter({drift: 1}), Counter({old: 1})
        gen._consume_interpreter_quote_pairs(added, removed)
        assert +added == Counter({drift: 1}) and +removed == Counter({old: 1})
    added, removed = Counter({new: 2}), Counter({old: 1})
    gen._consume_interpreter_quote_pairs(added, removed)
    assert +added == Counter({new: 1}) and not +removed


def test_req_core001_ac01_instructional_sample_pair_is_exact():
    """A prose sample quotes the selected path while preserving its instruction."""
    old = '**In every subsequent bash block, replace `python3` with `' + BARE + '` to use the correct interpreter.**'
    new = old.replace(BARE, QUOTED)
    added, removed = Counter({new: 1}), Counter({old: 1})
    gen._consume_interpreter_quote_pairs(added, removed)
    assert not +added and not +removed


@pytest.mark.parametrize("key", ["aider", "devin"])
def test_req_core001_ac01_actual_monolith_roundtrip_rejects_extra_head_drift(monkeypatch, key):
    """The real frozen-blob comparison still rejects modified invocation arguments."""
    platform = gen.load_platforms()[key]
    assert gen.monolith_roundtrip(platform) == []
    artifact = gen.render(platform)[0]
    assert QUOTED + ' -c "' in artifact.content
    mutated = gen.RenderedArtifact(artifact.path, artifact.content.replace(
        QUOTED + ' -c "', QUOTED + ' --changed -c "', 1))
    monkeypatch.setattr(gen, "render", lambda _platform: [mutated])
    assert gen.monolith_roundtrip(platform)
