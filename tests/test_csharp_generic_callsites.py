"""Unqualified generic C# calls keep their calls edge (#3406).

`Get<int>("port")` parses with a `generic_name` function node; the invocation
handler had arms for `member_access_expression` and `identifier` only, so the
raw-text fallback captured `Get<int>` verbatim and the call never matched the
`.Get()` member — while the non-generic spelling of the same call resolved.
`this.Get<int>(...)` failed the same way through the member arm, whose name
field is the same `generic_name`.
"""

from graphify.extract import extract

SETTINGS_CS = (
    "namespace Demo\n{\n    public class Settings\n    {\n"
    "        public T Get<T>(string key) { return default(T); }\n"
    "        public string GetRaw(string key) { return key; }\n    }\n}\n"
)

READER_CS = (
    "namespace Demo\n{\n    public class Reader : Settings\n    {\n"
    "        public int A() { return Get<int>(\"port\"); }\n"
    "        public int B() { return this.Get<int>(\"port\"); }\n"
    "        public string C() { return GetRaw(\"host\"); }\n"
    "        public string D() { return this.GetRaw(\"host\"); }\n    }\n}\n"
)

LOCAL_CS = (
    "namespace Demo\n{\n    public class Local\n    {\n"
    "        public T Make<T>() { return default(T); }\n"
    "        public int E() { return Make<int>(); }\n    }\n}\n"
)


def _calls(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "Settings.cs").write_text(SETTINGS_CS, encoding="utf-8")
    (tmp_path / "Reader.cs").write_text(READER_CS, encoding="utf-8")
    (tmp_path / "Local.cs").write_text(LOCAL_CS, encoding="utf-8")
    r = extract(sorted(tmp_path.glob("*.cs")), cache_root=tmp_path)
    return {(e["source"], e["target"]) for e in r["edges"]
            if e["relation"] == "calls"}


def _has(calls, src_frag, tgt_frag):
    return any(src_frag in s and tgt_frag in t for s, t in calls)


def test_unqualified_generic_call_resolves_to_base_member(tmp_path, monkeypatch):
    """The issue's case 1: `Get<int>("port")` with the target on the base class."""
    calls = _calls(tmp_path, monkeypatch)
    assert _has(calls, "reader_a", "settings_get"), sorted(calls)


def test_this_qualified_generic_call_resolves(tmp_path, monkeypatch):
    """Case 2: `this.Get<int>("port")` — the member arm's generic_name name."""
    calls = _calls(tmp_path, monkeypatch)
    assert _has(calls, "reader_b", "settings_get"), sorted(calls)


def test_same_class_generic_call_resolves(tmp_path, monkeypatch):
    """Case 5: `Make<int>()` with the target on the same class."""
    calls = _calls(tmp_path, monkeypatch)
    assert _has(calls, "local_e", "local_make"), sorted(calls)


def test_generic_call_never_targets_the_bracketed_text(tmp_path, monkeypatch):
    """The old failure shape: no target derived from `Get<int>` raw text."""
    calls = _calls(tmp_path, monkeypatch)
    assert not any("<" in t for _, t in calls), sorted(calls)


def test_non_generic_controls_unchanged(tmp_path, monkeypatch):
    """Cases 3 and 4 resolved before the fix and must keep resolving."""
    calls = _calls(tmp_path, monkeypatch)
    assert _has(calls, "reader_c", "settings_getraw"), sorted(calls)
    assert _has(calls, "reader_d", "settings_getraw"), sorted(calls)
