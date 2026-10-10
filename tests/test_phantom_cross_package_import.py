"""A Python absolute import must not bind to a same-named module in a sibling package.

Two services in one repo commonly ship their own package under the same name
(``service/app/config.py`` and ``service-sonos/app/config.py``), each defining a
class with the same label. Both then contain the byte-identical line
``from app.config import Settings``.

``_resolve_cross_file_imports`` resolved the module path in three steps: exact
directory-qualified stem, then a unique suffix match, then a bare-stem index.
The bare-stem index kept only the first file written for a given basename, so
when the first two steps could not disambiguate, *every* importer of that module
name repo-wide bound to whichever package happened to be extracted first — an
``uses`` edge at INFERRED/0.95 pointing into a package the file never imported.

The symptom is a phantom bridge: the two services share no import, no call and
no field, yet the mis-bound class became the graph's highest-betweenness node
precisely because a false edge spans communities that nothing else connects.

The fix resolves an ambiguous module path by proximity — the candidate sharing
the longest leading path with the importing file, which is what Python's own
sys.path resolution amounts to — and emits nothing on a genuine tie rather than
guessing.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _edges(files: list[Path], base: Path) -> set[tuple[str, str, str]]:
    r = extract(files, cache_root=base, parallel=False)
    return {(e["source"], e["target"], e["relation"]) for e in r["edges"]}


def _two_services(tmp_path: Path) -> list[Path]:
    """Two packages, each with `app/config.py` defining `Settings`."""
    _write(tmp_path / "svc_a/app/config.py", "class Settings:\n    league = 'college'\n")
    _write(tmp_path / "svc_a/app/main.py",
           "from app.config import Settings\n\n"
           "class App:\n"
           "    def build(self):\n"
           "        return Settings()\n")
    _write(tmp_path / "svc_b/app/config.py", "class Settings:\n    port = 8002\n")
    _write(tmp_path / "svc_b/app/main.py",
           "from app.config import Settings\n\n"
           "class SonosApp:\n"
           "    def build(self):\n"
           "        return Settings()\n")
    return sorted(tmp_path.rglob("*.py"))


def test_ambiguous_absolute_import_does_not_cross_packages(tmp_path: Path) -> None:
    edges = _edges(_two_services(tmp_path), tmp_path)
    crossing = [
        (s, t, r) for s, t, r in edges
        if (s.startswith("svc_a") and t.startswith("svc_b"))
        or (s.startswith("svc_b") and t.startswith("svc_a"))
    ]
    assert not crossing, crossing


def test_ambiguous_absolute_import_resolves_within_its_own_package(tmp_path: Path) -> None:
    # Dropping the phantom is not enough: each importer must still reach the
    # `Settings` in its OWN package.
    edges = _edges(_two_services(tmp_path), tmp_path)
    for pkg in ("svc_a", "svc_b"):
        own = [
            (s, t, r) for s, t, r in edges
            if s.startswith(pkg) and t.startswith(f"{pkg}_app_config_settings")
        ]
        assert own, f"{pkg} has no edge to its own Settings: {sorted(edges)}"


def test_importer_in_a_sibling_directory_still_resolves(tmp_path: Path) -> None:
    # The importing file need not sit beside the target: `svc_a/tests/` is one
    # level off `svc_a/app/`, and must still prefer svc_a over svc_b.
    _write(tmp_path / "svc_a/app/config.py", "class Settings:\n    league = 'college'\n")
    _write(tmp_path / "svc_b/app/config.py", "class Settings:\n    port = 8002\n")
    _write(tmp_path / "svc_a/tests/test_config.py",
           "from app.config import Settings\n\n"
           "class TestConfig:\n"
           "    def test_defaults(self):\n"
           "        assert Settings().league == 'college'\n")
    edges = _edges(sorted(tmp_path.rglob("*.py")), tmp_path)
    assert not [e for e in edges if e[0].startswith("svc_a_tests") and e[1].startswith("svc_b")]


def test_unambiguous_absolute_import_is_unaffected(tmp_path: Path) -> None:
    # Only one `app/config.py` in the repo — the existing single-suffix-match
    # path must keep resolving it.
    _write(tmp_path / "svc_a/app/config.py", "class Settings:\n    league = 'college'\n")
    _write(tmp_path / "svc_a/app/main.py",
           "from app.config import Settings\n\n"
           "class App:\n"
           "    def build(self):\n"
           "        return Settings()\n")
    edges = _edges(sorted(tmp_path.rglob("*.py")), tmp_path)
    assert [
        (s, t, r) for s, t, r in edges
        if s.startswith("svc_a_app_main") and t == "svc_a_app_config_settings"
    ], sorted(edges)


def test_nearest_stem_prefers_the_closest_candidate() -> None:
    from graphify.extractors.resolution import _nearest_stem

    candidates = ["svc_a/app/config", "svc_b/app/config"]
    assert _nearest_stem(candidates, "svc_b/app/main") == "svc_b/app/config"
    assert _nearest_stem(candidates, "svc_a/tests/test_config") == "svc_a/app/config"


def test_nearest_stem_refuses_to_guess_on_a_tie() -> None:
    from graphify.extractors.resolution import _nearest_stem

    # Neither candidate shares any leading segment with the importer: the import
    # is genuinely ambiguous and must produce no edge at all.
    candidates = ["svc_a/app/config", "svc_b/app/config"]
    assert _nearest_stem(candidates, "tools/script") is None
    # A lone candidate is never a tie.
    assert _nearest_stem(["svc_a/app/config"], "tools/script") == "svc_a/app/config"
    assert _nearest_stem([], "tools/script") is None
