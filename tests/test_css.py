"""Focused tests for CSS and SCSS design-token extraction and resolution (#3473)."""
from pathlib import Path
import pytest

from graphify.detect import FileType, classify_file, _is_sensitive
from graphify.extract import extract, _file_node_id, _make_id
from graphify.extractors.css import extract_css


# ── 1. Detection ─────────────────────────────────────────────────────────────

def test_detect_css_classified_as_code():
    assert classify_file(Path("styles.css")) == FileType.CODE
    assert classify_file(Path("src/components/button.css")) == FileType.CODE


def test_detect_scss_classified_as_code():
    assert classify_file(Path("styles.scss")) == FileType.CODE
    assert classify_file(Path("src/styles/_tokens.scss")) == FileType.CODE


def test_tokens_stylesheet_not_flagged_as_sensitive():
    assert not _is_sensitive(Path("tokens.css"))
    assert not _is_sensitive(Path("tokens.scss"))
    assert not _is_sensitive(Path("design-tokens.css"))
    assert not _is_sensitive(Path("styles/tokens.scss"))


# ── 2. Extraction: Root & Theme Contexts ──────────────────────────────────────

def test_extract_root_tokens(tmp_path):
    f = tmp_path / "root.css"
    f.write_text(
        """:root {
    --color-primary: #0070f3;
    --spacing-sm: 8px;
}
""",
        encoding="utf-8",
    )
    res = extract_css(f)
    token_nodes = [n for n in res["nodes"] if n.get("node_kind") == "token"]
    assert len(token_nodes) == 2
    labels = {n["label"] for n in token_nodes}
    assert labels == {"--color-primary", "--spacing-sm"}

    edges = [e for e in res["edges"] if e.get("relation") == "defines_token"]
    assert len(edges) == 2
    for e in edges:
        assert e["confidence"] == "EXTRACTED"
        assert e["confidence_score"] == 1.0


def test_extract_host_tokens(tmp_path):
    f = tmp_path / "shadow.css"
    f.write_text(
        """:host {
    --widget-bg: #fff;
}
""",
        encoding="utf-8",
    )
    res = extract_css(f)
    tokens = [n["label"] for n in res["nodes"] if n.get("node_kind") == "token"]
    assert tokens == ["--widget-bg"]


def test_extract_html_and_body_tokens(tmp_path):
    f = tmp_path / "base.css"
    f.write_text(
        """html {
    --font-base: sans-serif;
}
body {
    --text-color: #333;
}
""",
        encoding="utf-8",
    )
    res = extract_css(f)
    tokens = [n["label"] for n in res["nodes"] if n.get("node_kind") == "token"]
    assert set(tokens) == {"--font-base", "--text-color"}


def test_extract_theme_selectors(tmp_path):
    f = tmp_path / "themes.css"
    f.write_text(
        """[data-theme="dark"] {
    --bg-dark: #121212;
}
[data-mode="dim"] {
    --bg-dim: #222;
}
.dark {
    --dark-accent: #f00;
}
.theme-dracula {
    --dracula-pink: #ff79c6;
}
""",
        encoding="utf-8",
    )
    res = extract_css(f)
    tokens = {n["label"] for n in res["nodes"] if n.get("node_kind") == "token"}
    assert tokens == {"--bg-dark", "--bg-dim", "--dark-accent", "--dracula-pink"}


def test_extract_at_theme(tmp_path):
    f = tmp_path / "tailwind.css"
    f.write_text(
        """@theme {
    --font-display: 'Inter', sans-serif;
}
""",
        encoding="utf-8",
    )
    res = extract_css(f)
    tokens = [n["label"] for n in res["nodes"] if n.get("node_kind") == "token"]
    assert tokens == ["--font-display"]


def test_extract_nested_under_transparent_at_rules(tmp_path):
    f = tmp_path / "media.css"
    f.write_text(
        """@media (prefers-color-scheme: dark) {
    :root {
        --media-dark: #000;
    }
}
@layer base {
    :root {
        --layer-base-token: #fff;
    }
}
@supports (display: grid) {
    :root {
        --grid-gap: 16px;
    }
}
""",
        encoding="utf-8",
    )
    res = extract_css(f)
    tokens = {n["label"] for n in res["nodes"] if n.get("node_kind") == "token"}
    assert tokens == {"--media-dark", "--layer-base-token", "--grid-gap"}


def test_ordinary_component_selectors_rejected(tmp_path):
    f = tmp_path / "components.css"
    f.write_text(
        """.card {
    --card-bg: #fff;
}
.button {
    --btn-padding: 4px;
}
#header {
    --header-h: 60px;
}
table tr:hover {
    --hover-bg: #f5f5f5;
}
.p-4 {
    --spacing: 16px;
}
.card .dark {
    --scoped-dark: #000;
}
:root .card {
    --nested-card-override: #111;
}
""",
        encoding="utf-8",
    )
    res = extract_css(f)
    tokens = [n["label"] for n in res["nodes"] if n.get("node_kind") == "token"]
    assert tokens == [], f"Expected no token nodes from component selectors, got {tokens}"


# ── 3. SCSS Handling ─────────────────────────────────────────────────────────

def test_scss_comments_and_nested_root(tmp_path):
    f = tmp_path / "theme.scss"
    f.write_text(
        """// Single-line SCSS comment with --fake-token: 1;
/* Block comment with :root { --commented-token: 2; } */
$sass-var: #ff0000;
$primary-color: #fff;

:root {
    // line comment inside root
    /* block comment inside root: --inside-comment: 3; */
    --real-token: #123456;

    &.dark {
        --nested-dark-token: #000;
    }
}
""",
        encoding="utf-8",
    )
    res = extract_css(f)
    tokens = {n["label"] for n in res["nodes"] if n.get("node_kind") == "token"}
    assert tokens == {"--real-token", "--nested-dark-token"}
    assert "--fake-token" not in tokens
    assert "--commented-token" not in tokens
    assert "--inside-comment" not in tokens
    assert "$sass-var" not in tokens
    assert "$primary-color" not in tokens


def test_scss_partials_extracted_normally(tmp_path):
    f = tmp_path / "_tokens.scss"
    f.write_text(
        """:root {
    --brand: #abc;
}
""",
        encoding="utf-8",
    )
    res = extract_css(f)
    tokens = [n["label"] for n in res["nodes"] if n.get("node_kind") == "token"]
    assert tokens == ["--brand"]


# ── 4. Identity & Schema ─────────────────────────────────────────────────────

def test_token_identity_and_schema(tmp_path):
    f_a = tmp_path / "theme-a.css"
    f_b = tmp_path / "theme-b.css"
    f_a.write_text(":root { --color-card: #aaa; }", encoding="utf-8")
    f_b.write_text(":root { --color-card: #bbb; }", encoding="utf-8")

    res_a = extract_css(f_a)
    res_b = extract_css(f_b)

    token_a = next(n for n in res_a["nodes"] if n.get("node_kind") == "token")
    token_b = next(n for n in res_b["nodes"] if n.get("node_kind") == "token")

    # Distinct file-scoped IDs
    assert token_a["id"] != token_b["id"]

    # Schema verification
    assert token_a["file_type"] == "code"
    assert token_a["node_kind"] == "token"
    assert token_a["label"] == "--color-card"
    assert token_a["source_file"] == str(f_a)
    assert token_a["source_location"] == "L1"

    edge_a = next(e for e in res_a["edges"] if e.get("relation") == "defines_token")
    assert edge_a["source"] == res_a["nodes"][0]["id"]
    assert edge_a["target"] == token_a["id"]
    assert edge_a["confidence"] == "EXTRACTED"
    assert edge_a["confidence_score"] == 1.0


# ── 5. Post-Extraction Resolution ────────────────────────────────────────────

def test_same_file_unique_token_resolves(tmp_path):
    f = tmp_path / "styles.css"
    f.write_text(
        """:root {
    --brand: #123;
}
.btn {
    color: var(--brand);
}
""",
        encoding="utf-8",
    )
    g = extract([f], root=tmp_path)
    edges = [e for e in g["edges"] if e.get("relation") == "uses_token"]
    assert len(edges) == 1
    edge = edges[0]
    token_node = next(n for n in g["nodes"] if n.get("label") == "--brand")
    file_node = next(n for n in g["nodes"] if n.get("label") == "styles.css")
    assert edge["source"] == file_node["id"]
    assert edge["target"] == token_node["id"]
    assert edge["confidence"] == "EXTRACTED"
    assert edge["confidence_score"] == 1.0


def test_unique_cross_file_token_resolves(tmp_path):
    tokens_file = tmp_path / "tokens.css"
    app_file = tmp_path / "app.css"
    tokens_file.write_text(":root { --accent: #ff0; }", encoding="utf-8")
    app_file.write_text(".sidebar { background: var(--accent); }", encoding="utf-8")

    g = extract([tokens_file, app_file], root=tmp_path)
    uses_edges = [e for e in g["edges"] if e.get("relation") == "uses_token"]
    assert len(uses_edges) == 1
    edge = uses_edges[0]
    token_node = next(n for n in g["nodes"] if n.get("label") == "--accent")
    app_file_node = next(n for n in g["nodes"] if n.get("label") == "app.css")
    assert edge["source"] == app_file_node["id"]
    assert edge["target"] == token_node["id"]
    assert edge["confidence"] == "EXTRACTED"


def test_multiple_same_name_definitions_produce_no_uses_edge(tmp_path):
    theme_a = tmp_path / "theme_a.css"
    theme_b = tmp_path / "theme_b.css"
    consumer = tmp_path / "consumer.css"

    theme_a.write_text(":root { --ambiguous-token: #111; }", encoding="utf-8")
    theme_b.write_text(":root { --ambiguous-token: #222; }", encoding="utf-8")
    consumer.write_text(".box { color: var(--ambiguous-token); }", encoding="utf-8")

    g = extract([theme_a, theme_b, consumer], root=tmp_path)
    consumer_node = next(n for n in g["nodes"] if n.get("label") == "consumer.css")
    consumer_uses = [
        e for e in g["edges"]
        if e.get("relation") == "uses_token" and e.get("source") == consumer_node["id"]
    ]
    # Ambiguous cross-file references must NOT resolve (conservative, no fan-out)
    assert consumer_uses == []


def test_same_file_precedence_over_cross_file_ambiguity(tmp_path):
    theme_a = tmp_path / "theme_a.css"
    theme_b = tmp_path / "theme_b.css"

    # Both define --local-token, but theme_a also uses it
    theme_a.write_text(
        """:root { --local-token: #111; }
.my-el { color: var(--local-token); }
""",
        encoding="utf-8",
    )
    theme_b.write_text(":root { --local-token: #222; }", encoding="utf-8")

    g = extract([theme_a, theme_b], root=tmp_path)
    theme_a_node = next(n for n in g["nodes"] if n.get("label") == "theme_a.css")
    token_a = next(
        n for n in g["nodes"]
        if n.get("label") == "--local-token" and "theme_a" in n["id"]
    )
    uses = [
        e for e in g["edges"]
        if e.get("relation") == "uses_token" and e.get("source") == theme_a_node["id"]
    ]
    # Same-file match must resolve to theme_a's own token definition
    assert len(uses) == 1
    assert uses[0]["target"] == token_a["id"]


def test_nonexistent_token_produces_no_uses_edge(tmp_path):
    f = tmp_path / "orphan.css"
    f.write_text(".box { color: var(--nonexistent-var); }", encoding="utf-8")
    g = extract([f], root=tmp_path)
    uses = [e for e in g["edges"] if e.get("relation") == "uses_token"]
    assert uses == []


# ── 6. Incremental / Context Resolution ──────────────────────────────────────

def test_incremental_resolution_with_context_nodes(tmp_path):
    # Simulate an incremental build where consumer.css is freshly extracted
    # while the token definition in tokens.css is supplied via resolution_context_nodes
    consumer = tmp_path / "consumer.css"
    consumer.write_text(".panel { background: var(--theme-color); }", encoding="utf-8")

    # Mock token node from unchanged tokens.css
    token_id = "tokens_theme_color"
    context_node = {
        "id": token_id,
        "label": "--theme-color",
        "file_type": "code",
        "node_kind": "token",
        "source_file": str(tmp_path / "tokens.css"),
        "source_location": "L1",
    }

    g = extract(
        [consumer],
        root=tmp_path,
        resolution_context_nodes=[context_node],
    )
    consumer_node = next(n for n in g["nodes"] if n.get("label") == "consumer.css")
    uses = [
        e for e in g["edges"]
        if e.get("relation") == "uses_token" and e.get("source") == consumer_node["id"]
    ]
    assert len(uses) == 1
    assert uses[0]["target"] == token_id
    assert uses[0]["confidence"] == "EXTRACTED"


# ── 7. Regression Tests for Edge Cases ────────────────────────────────────────

def test_unquoted_url_and_scss_comments(tmp_path):
    f = tmp_path / "urls.scss"
    f.write_text(
        """:root {
  --font-url: url(https://example.com/font.woff);
  --valid: 123;
  --http-url: url(http://example.com/image.png);
}
// --ignored: value;
""",
        encoding="utf-8",
    )
    res = extract_css(f)
    tokens = {n["label"] for n in res["nodes"] if n.get("node_kind") == "token"}
    assert "--font-url" in tokens
    assert "--valid" in tokens
    assert "--http-url" in tokens
    assert "--ignored" not in tokens


def test_var_inside_quoted_strings_ignored(tmp_path):
    f = tmp_path / "content.css"
    f.write_text(
        """:root {
  --brand: blue;
}

.example::before {
  content: "Use var(--brand) here";
  color: var(--brand);
}
""",
        encoding="utf-8",
    )
    res = extract_css(f)
    # Only the real outside-string color: var(--brand) should be captured
    assert len(res["raw_token_uses"]) == 1
    use = res["raw_token_uses"][0]
    assert use["token_name"] == "--brand"
    assert use["line"] == 7  # line of `color: var(--brand);`


def test_warm_cache_roundtrip(tmp_path):
    t = tmp_path / "tokens.css"
    t.write_text(":root { --cached-token: #123; }", encoding="utf-8")
    c = tmp_path / "consumer.css"
    c.write_text(".btn { color: var(--cached-token); }", encoding="utf-8")

    # Cold extraction
    g1 = extract([t, c], root=tmp_path)
    uses1 = [e for e in g1["edges"] if e.get("relation") == "uses_token"]
    assert len(uses1) == 1

    # Warm extraction from cache
    g2 = extract([t, c], root=tmp_path)
    uses2 = [e for e in g2["edges"] if e.get("relation") == "uses_token"]
    assert len(uses2) == 1
    assert uses1[0]["source"] == uses2[0]["source"]
    assert uses1[0]["target"] == uses2[0]["target"]

