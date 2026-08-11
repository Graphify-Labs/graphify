import pathlib


def test_docs_mention_viz_flag():
    """Simple smoke test: ensure the docs file exists and mentions the 3D viz flag.

    This is a non-invasive test that helps CI catch accidental removals or regressions
    to the documentation we added in this PR.
    """
    p = pathlib.Path("docs/3d-viz.md")
    assert p.exists(), "docs/3d-viz.md must exist"
    text = p.read_text(encoding="utf-8")
    assert "--viz 3d" in text or "GRAPHIFY_VIZ_MODE" in text, "docs/3d-viz.md must mention --viz 3d or GRAPHIFY_VIZ_MODE"
