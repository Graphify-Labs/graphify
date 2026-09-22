"""A bare ``out`` directory is pruned only on build-output evidence (#3347).

``out`` was in ``_SKIP_DIRS`` unconditionally, so a hexagonal codebase's
``adapter/out/`` and ``port/out/`` — the entire outbound layer, 30% of the
corpus on the reporting repo — vanished from the scan with exit code 0 and no
warning. It now gets the same evidence gating ``env``/``coverage``/
``snapshots`` already have (#1666/#2058/#2339): keep on doubt, prune on proof.
"""

from graphify.detect import detect


def _scanned(td):
    d = detect(td)
    return sorted(
        str(f).replace("\\", "/") for cat in d["files"].values() for f in cat
    )


def test_hexagonal_out_layers_are_scanned(tmp_path, monkeypatch):
    """adapter/out/ and port/out/ holding only source stay in the corpus."""
    monkeypatch.chdir(tmp_path)
    ad = tmp_path / "src/main/java/demo/adapter/out/persistence"
    ad.mkdir(parents=True)
    (ad / "OrderEntity.java").write_text(
        "package demo.adapter.out.persistence;\npublic class OrderEntity { }\n",
        encoding="utf-8")
    po = tmp_path / "src/main/java/demo/port/out"
    po.mkdir(parents=True)
    (po / "OrderRepositoryPort.java").write_text(
        "package demo.port.out;\npublic interface OrderRepositoryPort { }\n",
        encoding="utf-8")

    files = _scanned(tmp_path)
    assert any("adapter/out/persistence/OrderEntity.java" in f for f in files), files
    assert any("port/out/OrderRepositoryPort.java" in f for f in files), files


def test_intellij_out_production_is_pruned(tmp_path, monkeypatch):
    """out/production/... (IntelliJ compile output) stays out of the corpus."""
    monkeypatch.chdir(tmp_path)
    ij = tmp_path / "out/production/demo"
    ij.mkdir(parents=True)
    (ij / "Order.class").write_bytes(b"\xca\xfe\xba\xbe")
    (tmp_path / "src").mkdir()
    (tmp_path / "src/Order.java").write_text(
        "public class Order { }\n", encoding="utf-8")

    files = _scanned(tmp_path)
    assert any("src/Order.java" in f for f in files), files
    assert not any("/out/" in f for f in files), files


def test_next_export_out_is_pruned(tmp_path, monkeypatch):
    """A `next export` static-site out/ (marked by _next/) stays out."""
    monkeypatch.chdir(tmp_path)
    nx = tmp_path / "out/_next"
    nx.mkdir(parents=True)
    (tmp_path / "out/index.html").write_text("<html></html>", encoding="utf-8")
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages/index.tsx").write_text(
        "export default function Home() { return null; }\n", encoding="utf-8")

    files = _scanned(tmp_path)
    assert any("pages/index.tsx" in f for f in files), files
    assert not any("out/index.html" in f for f in files), files


def test_compiled_artifacts_one_level_down_prune_out(tmp_path, monkeypatch):
    """A TS outDir shape — compiled .js.map one level inside out/ — is pruned."""
    monkeypatch.chdir(tmp_path)
    o = tmp_path / "out/lib"
    o.mkdir(parents=True)
    (o / "index.js").write_text("module.exports = {};\n", encoding="utf-8")
    (o / "index.js.map").write_text("{}", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src/index.ts").write_text("export const x = 1;\n", encoding="utf-8")

    files = _scanned(tmp_path)
    assert any("src/index.ts" in f for f in files), files
    assert not any("out/lib" in f for f in files), files


def test_wide_out_dir_markers_beyond_twenty_subdirs_still_prune(tmp_path, monkeypatch):
    """A wide outDir whose compiled files sit only under a late-sorted
    subdirectory is still recognized as build output."""
    monkeypatch.chdir(tmp_path)
    for i in range(30):
        sub = tmp_path / f"out/mod{i:02d}"
        sub.mkdir(parents=True)
        (sub / "notes.txt").write_text("no artifacts here\n", encoding="utf-8")
    late = tmp_path / "out/zz-final"
    late.mkdir()
    (late / "index.js.map").write_text("{}", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src/index.ts").write_text("export const x = 1;\n", encoding="utf-8")

    files = _scanned(tmp_path)
    assert any("src/index.ts" in f for f in files), files
    assert not any("/out/" in f for f in files), files


def test_other_skip_dirs_stay_unconditional(tmp_path, monkeypatch):
    """The gate is scoped to `out`: build/, dist/, target/ prune by name."""
    monkeypatch.chdir(tmp_path)
    for name in ("build", "dist", "target"):
        d = tmp_path / name
        d.mkdir()
        (d / "Thing.java").write_text("public class Thing { }\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src/Real.java").write_text("public class Real { }\n", encoding="utf-8")

    files = _scanned(tmp_path)
    assert any("src/Real.java" in f for f in files), files
    assert not any(any(f"/{n}/" in f for n in ("build", "dist", "target"))
                   for f in files), files
