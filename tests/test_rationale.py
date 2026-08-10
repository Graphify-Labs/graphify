"""Tests for rationale/docstring extraction in extract.py."""
import textwrap
from pathlib import Path
import pytest
from graphify.extract import extract_python
from graphify.build import build_from_json


def _write_py(tmp_path: Path, code: str) -> Path:
    p = tmp_path / "sample.py"
    p.write_text(textwrap.dedent(code))
    return p


def test_module_docstring_extracted(tmp_path):
    path = _write_py(tmp_path, '''
        """This module handles authentication because legacy sessions were insecure."""
        def login(): pass
    ''')
    result = extract_python(path)
    rationale = [n for n in result["nodes"] if n.get("file_type") == "rationale"]
    assert len(rationale) >= 1
    assert any("authentication" in n["label"] for n in rationale)


def test_function_docstring_extracted(tmp_path):
    path = _write_py(tmp_path, '''
        def process():
            """We use chunked processing here because the full dataset exceeds RAM."""
            pass
    ''')
    result = extract_python(path)
    rationale = [n for n in result["nodes"] if n.get("file_type") == "rationale"]
    assert any("chunked" in n["label"] for n in rationale)


def test_class_docstring_extracted(tmp_path):
    path = _write_py(tmp_path, '''
        class Cache:
            """Chosen over Redis because we need zero external dependencies in the test env."""
            pass
    ''')
    result = extract_python(path)
    rationale = [n for n in result["nodes"] if n.get("file_type") == "rationale"]
    assert any("Redis" in n["label"] for n in rationale)


def test_rationale_comment_extracted(tmp_path):
    path = _write_py(tmp_path, '''
        def build():
            # NOTE: must run before compile() or linker will fail
            pass
    ''')
    result = extract_python(path)
    rationale = [n for n in result["nodes"] if n.get("file_type") == "rationale"]
    assert any("NOTE" in n["label"] for n in rationale)


def test_rationale_for_edges_present(tmp_path):
    path = _write_py(tmp_path, '''
        """Module docstring explaining the why."""
        def foo():
            """Function docstring with rationale."""
            pass
    ''')
    result = extract_python(path)
    rationale_edges = [e for e in result["edges"] if e.get("relation") == "rationale_for"]
    assert len(rationale_edges) >= 1


def test_short_docstring_ignored(tmp_path):
    """Trivial docstrings under 20 chars should not become rationale nodes."""
    path = _write_py(tmp_path, '''
        def foo():
            """Constructor."""
            pass
    ''')
    result = extract_python(path)
    rationale = [n for n in result["nodes"] if n.get("file_type") == "rationale"]
    assert len(rationale) == 0


def test_rationale_confidence_is_extracted(tmp_path):
    path = _write_py(tmp_path, '''
        """This module exists because we needed a standalone parser."""
        def parse(): pass
    ''')
    result = extract_python(path)
    rationale_edges = [e for e in result["edges"] if e.get("relation") == "rationale_for"]
    assert all(e.get("confidence") == "EXTRACTED" for e in rationale_edges)


def test_alembic_module_docstring_suppressed(tmp_path):
    path = _write_py(tmp_path, '''
        """initial schema

        Revision ID: 0001abcd
        Revises:
        Create Date: 2023-01-01 00:00:00
        """
        revision = "0001abcd"
        down_revision = None
        branch_labels = None

        def upgrade():
            pass

        def downgrade():
            pass
    ''')
    result = extract_python(path)
    rationale = [n for n in result["nodes"] if n.get("file_type") == "rationale"]
    assert not any("Revision ID" in n["label"] for n in rationale)


def test_alembic_function_docstrings_still_extracted(tmp_path):
    """Function docstrings inside upgrade/downgrade should still be captured."""
    path = _write_py(tmp_path, '''
        """Revision ID: 0002 Revises: 0001"""
        revision = "0002"
        down_revision = "0001"

        def upgrade():
            """Add users table because auth was added in this release."""
            pass

        def downgrade():
            pass
    ''')
    result = extract_python(path)
    rationale = [n for n in result["nodes"] if n.get("file_type") == "rationale"]
    # module docstring suppressed
    assert not any("Revision ID" in n["label"] for n in rationale)
    # function docstring still captured
    assert any("auth" in n["label"] for n in rationale)


def test_non_migration_revision_var_not_suppressed(tmp_path):
    """A file with a `revision` variable but no Alembic markers keeps its docstring."""
    path = _write_py(tmp_path, '''
        """This module tracks document revisions because we need audit history."""
        revision = 42

        def get_revision(): pass
    ''')
    result = extract_python(path)
    rationale = [n for n in result["nodes"] if n.get("file_type") == "rationale"]
    assert any("audit history" in n["label"] for n in rationale)


def test_django_migration_module_docstring_suppressed(tmp_path):
    path = _write_py(tmp_path, '''
        """Add post_priority_config table."""
        from django.db import migrations

        class Migration(migrations.Migration):
            dependencies = [("myapp", "0001_initial")]
            operations = []
    ''')
    result = extract_python(path)
    rationale = [n for n in result["nodes"] if n.get("file_type") == "rationale"]
    assert not any("post_priority" in n["label"] for n in rationale)


def test_generated_file_module_docstring_suppressed(tmp_path):
    path = _write_py(tmp_path, '''
        """Generated by the protocol buffer compiler. DO NOT EDIT!"""
        from google.protobuf import descriptor as _descriptor

        class UserMessage:
            pass
    ''')
    result = extract_python(path)
    rationale = [n for n in result["nodes"] if n.get("file_type") == "rationale"]
    assert not any("protocol buffer" in n["label"].lower() for n in rationale)


def test_decorated_method_node_id_is_class_qualified(tmp_path):
    """Regression for #1050: @property / @staticmethod / @classmethod methods
    were emitted with a class-unqualified node id (e.g. ``file_baz``) while the
    rationale walker emitted the class-qualified id (``file_bar_baz``) as the
    docstring's edge target. The mismatch caused ``build_from_json`` to drop
    the rationale_for edge as dangling, orphaning the docstring node.
    """
    path = _write_py(tmp_path, '''
        class Bar:
            @property
            def baz(self) -> int:
                """Return the baz value because callers expect a cached integer."""
                return 1

            @staticmethod
            def helper() -> int:
                """A static helper documented for downstream callers."""
                return 2

            @classmethod
            def factory(cls) -> "Bar":
                """Construct a Bar via the canonical classmethod entry point."""
                return cls()

            def normal(self) -> int:
                """A normal instance method documented for comparison."""
                return 3
    ''')
    result = extract_python(path)
    nodes_by_id = {n["id"]: n for n in result["nodes"]}

    # The plain method's id is the baseline: stem + class + name.
    normal_ids = [nid for nid, n in nodes_by_id.items()
                  if n.get("label") == ".normal()"]
    assert len(normal_ids) == 1, "expected exactly one ``.normal()`` method node"
    normal_id = normal_ids[0]
    assert normal_id.endswith("_bar_normal"), normal_id

    # Each decorated method must share the same class-qualified id shape so the
    # rationale_for edge target matches the method node id.
    for decorated_name in ("baz", "helper", "factory"):
        matches = [nid for nid, n in nodes_by_id.items()
                   if n.get("label") == f".{decorated_name}()"]
        assert len(matches) == 1, (
            f"expected exactly one ``.{decorated_name}()`` method node, got {matches}"
        )
        method_id = matches[0]
        assert method_id.endswith(f"_bar_{decorated_name}"), method_id
        # Unqualified id (the buggy form) must NOT also be present.
        unqualified_buggy_id = method_id.replace(f"_bar_{decorated_name}",
                                                  f"_{decorated_name}")
        assert unqualified_buggy_id not in nodes_by_id, (
            f"buggy unqualified id {unqualified_buggy_id} should not exist alongside "
            f"the class-qualified id"
        )

    # Every rationale_for edge's target must resolve to an actual node in the
    # extraction (no dangling edges into phantom unqualified ids).
    node_ids = set(nodes_by_id.keys())
    rationale_edges = [e for e in result["edges"] if e.get("relation") == "rationale_for"]
    for edge in rationale_edges:
        assert edge["target"] in node_ids, (
            f"rationale_for edge targets missing node id {edge['target']!r}"
        )

    # After build_from_json, each decorated-method docstring node must be
    # connected (degree > 0), not an orphan dropped from the graph.
    g = build_from_json(result)
    for decorated_name in ("baz", "helper", "factory", "normal"):
        method_id = next(
            nid for nid, n in nodes_by_id.items()
            if n.get("label") == f".{decorated_name}()"
        )
        # Find rationale node attached to this method.
        attached_rationale = [
            e["source"] for e in rationale_edges if e["target"] == method_id
        ]
        assert attached_rationale, (
            f"no rationale_for edge found for ``.{decorated_name}()`` method"
        )
        for r_id in attached_rationale:
            assert r_id in g.nodes, f"rationale node {r_id} missing from graph"
            assert g.degree(r_id) > 0, (
                f"rationale node {r_id} for ``.{decorated_name}()`` is orphaned "
                f"(degree 0) after build_from_json"
            )


# ── Regression for #2206: labels must normalize whitespace before truncating ──


def test_long_docstring_label_truncates_on_word_boundary(tmp_path):
    """A docstring longer than the 80-char cap must be shortened at a word
    boundary, not mid-word. Before the fix, ``text[:80]`` sliced "feeds" down
    to "feed"."""
    docstring = ("This routine reconciles pending settlement batches nightly "
                 "because upstream feeds arrive unordered and out of sequence.")
    path = _write_py(tmp_path, f'''
        def reconcile_batches():
            """{docstring}"""
            pass
    ''')
    result = extract_python(path)
    rationale = [n for n in result["nodes"] if n.get("file_type") == "rationale"]
    assert len(rationale) == 1
    label = rationale[0]["label"]
    assert len(label) <= 80
    core = label[:-1].rstrip() if label.endswith("…") else label
    assert docstring.startswith(core)
    if core != docstring:
        # Whatever follows the retained prefix in the source must be a space
        # (or end of string) -- i.e. the cut landed on a word boundary.
        assert docstring[len(core):len(core) + 1] in (" ", ""), label


def test_docstring_newline_and_indentation_collapsed_to_single_space(tmp_path):
    """A multi-line docstring's line break + indentation must not survive as a
    run of literal spaces inside the label (the raw slice used to keep them
    because it ran before the newline-to-space normalization)."""
    path = _write_py(tmp_path, '''
        def sync_inventory():
            """Aggregates daily settlement counts for reconciliation runs.
               Retries three times before raising to the monitoring pipeline.
            """
            pass
    ''')
    result = extract_python(path)
    rationale = [n for n in result["nodes"] if n.get("file_type") == "rationale"]
    label = rationale[0]["label"]
    assert "\n" not in label
    assert "  " not in label, f"whitespace run survived in label: {label!r}"
    assert "runs. Retries" in label


def test_truncated_docstring_never_ends_with_bare_period(tmp_path):
    """When the old 80-char cut happened to land on a ".", the Obsidian
    exporter appended ".md" and produced a double-dot filename. A truncated
    label must end on the placeholder, never on a lone trailing period."""
    docstring = ("Loads the merchant configs bundle from disk once at process "
                 "start-up and caches. It refreshes every six hours in the background.")
    path = _write_py(tmp_path, f'''
        def load_merchant_config():
            """{docstring}"""
            pass
    ''')
    result = extract_python(path)
    rationale = [n for n in result["nodes"] if n.get("file_type") == "rationale"]
    label = rationale[0]["label"]
    assert len(label) < len(docstring), "expected this docstring to be truncated"
    assert not label.endswith("."), label
    assert label.endswith("…"), label


def test_docstring_opening_with_unbroken_long_token_keeps_content(tmp_path):
    """Adversarial case: ``textwrap.shorten`` alone collapses to just the
    placeholder when the first whitespace-delimited "word" already exceeds
    the width (e.g. a docstring opening with a long, unbroken URL) -- that
    would regress to a content-free label, worse than the original bug. The
    label must still carry real content."""
    url = "https://example.com/api/v3/settlements/" + "a" * 60 + "/confirm"
    docstring = f"{url} documents the retry contract for this handler."
    path = _write_py(tmp_path, f'''
        def call_endpoint():
            """{docstring}"""
            pass
    ''')
    result = extract_python(path)
    rationale = [n for n in result["nodes"] if n.get("file_type") == "rationale"]
    label = rationale[0]["label"]
    assert label not in ("", "…"), label
    assert label.startswith("https://example.com/"), label


def test_short_docstring_label_unchanged(tmp_path):
    """Non-regression: a docstring well under 80 chars must pass through
    byte-for-byte, with no placeholder and no reformatting."""
    docstring = "Splits the bearer token because some clients send a stray prefix."
    path = _write_py(tmp_path, f'''
        def parse_token():
            """{docstring}"""
            pass
    ''')
    result = extract_python(path)
    rationale = [n for n in result["nodes"] if n.get("file_type") == "rationale"]
    label = rationale[0]["label"]
    assert label == docstring


# ── JS/TS rationale + doc-reference extraction ────────────────────────────────


def _write_ts(tmp_path: Path, code: str) -> Path:
    p = tmp_path / "sample.ts"
    p.write_text(textwrap.dedent(code))
    return p


def test_js_rationale_comment_extracted(tmp_path):
    from graphify.extract import extract_js
    path = _write_ts(tmp_path, '''
        // NOTE: must run before compile() or the linker will fail
        export function build(): void {}
    ''')
    result = extract_js(path)
    rationale = [n for n in result["nodes"] if n.get("file_type") == "rationale"]
    assert any("NOTE" in n["label"] for n in rationale)


def test_js_block_comment_rationale_extracted(tmp_path):
    from graphify.extract import extract_js
    path = _write_ts(tmp_path, '''
        /**
         * WHY: retries are capped because the upstream rate-limits at 10 rps.
         */
        export function fetchData(): void {}
    ''')
    result = extract_js(path)
    rationale = [n for n in result["nodes"] if n.get("file_type") == "rationale"]
    assert any("rate-limits" in n["label"] for n in rationale)


def test_js_adr_reference_extracted(tmp_path):
    from graphify.extract import extract_js
    path = _write_ts(tmp_path, '''
        // Gateway pattern per ADR-0002; provider selection per ADR-0015.
        export function route(): void {}
    ''')
    result = extract_js(path)
    refs = [n for n in result["nodes"] if n.get("file_type") == "doc_ref"]
    labels = {n["label"] for n in refs}
    assert "ADR-0002" in labels and "ADR-0015" in labels
    cites = [e for e in result["edges"] if e.get("relation") == "cites"]
    assert len(cites) == 2


def test_js_adr_reference_normalized_and_deduped(tmp_path):
    from graphify.extract import extract_js
    path = _write_ts(tmp_path, '''
        // See ADR-11 for the trust boundary.
        // ADR 0011 also governs the injection containment below.
        export function guard(): void {}
    ''')
    result = extract_js(path)
    refs = [n for n in result["nodes"] if n.get("file_type") == "doc_ref"]
    assert [n["label"] for n in refs] == ["ADR-0011"]


def test_js_adr_in_string_literal_not_extracted(tmp_path):
    from graphify.extract import extract_js
    path = _write_ts(tmp_path, '''
        export const banner = "compliant with ADR-0099";
    ''')
    result = extract_js(path)
    refs = [n for n in result["nodes"] if n.get("file_type") == "doc_ref"]
    assert refs == []


# ── Regression for #2206, JS/TS site (shares the fix with the Python site) ────


def test_js_rationale_label_truncates_on_word_boundary(tmp_path):
    """Same invariant as the Python site: a long ``// WHY:`` comment must be
    shortened at a word boundary, not mid-word."""
    from graphify.extract import extract_js
    comment_text = ("retries are capped because the upstream billing service "
                     "enforces a strict per-tenant rate limit that keeps dropping requests")
    path = _write_ts(tmp_path, f'''
        // WHY: {comment_text}
        export function fetchData(): void {{}}
    ''')
    result = extract_js(path)
    rationale = [n for n in result["nodes"] if n.get("file_type") == "rationale"]
    assert len(rationale) == 1
    label = rationale[0]["label"]
    full = f"WHY: {comment_text}"
    assert len(label) <= 80
    core = label[:-1].rstrip() if label.endswith("…") else label
    assert full.startswith(core)
    if core != full:
        assert full[len(core):len(core) + 1] in (" ", ""), label


def test_js_rationale_label_never_ends_with_bare_period_when_truncated(tmp_path):
    """Same invariant as the Python site: a truncated label must never end on
    a lone "." (double-dot Obsidian filename)."""
    from graphify.extract import extract_js
    comment_text = ("retries are capped at five attempts before the circuit breaker "
                     "opens for the endpoint. A metrics counter records every trip.")
    path = _write_ts(tmp_path, f'''
        // WHY: {comment_text}
        export function fetchData(): void {{}}
    ''')
    result = extract_js(path)
    rationale = [n for n in result["nodes"] if n.get("file_type") == "rationale"]
    label = rationale[0]["label"]
    full = f"WHY: {comment_text}"
    assert len(label) < len(full), "expected this comment to be truncated"
    assert not label.endswith("."), label


def test_js_rationale_comment_opening_with_unbroken_long_token_keeps_content(tmp_path):
    """Same adversarial case as the Python site: a ``// WHY:`` comment whose
    content is an unbroken long URL must not collapse to a content-free
    placeholder label. Unlike the Python site, the ``WHY:`` prefix always
    fits on its own, so the invariant is "some real content survives",
    not "the URL itself survives" (it genuinely cannot fit in 80 chars)."""
    from graphify.extract import extract_js
    url = "https://example.com/api/v3/settlements/" + "a" * 60 + "/confirm"
    path = _write_ts(tmp_path, f'''
        // WHY: {url} documents the retry contract for this handler.
        export function fetchData(): void {{}}
    ''')
    result = extract_js(path)
    rationale = [n for n in result["nodes"] if n.get("file_type") == "rationale"]
    label = rationale[0]["label"]
    assert label not in ("", "…"), label
    assert label.startswith("WHY:"), label


def test_js_short_rationale_comment_unchanged(tmp_path):
    """Non-regression: a short ``// NOTE:`` comment must pass through
    byte-for-byte, matching the pre-existing test above but pinned exactly."""
    from graphify.extract import extract_js
    path = _write_ts(tmp_path, '''
        // NOTE: must run before compile() or the linker will fail
        export function build(): void {}
    ''')
    result = extract_js(path)
    rationale = [n for n in result["nodes"] if n.get("file_type") == "rationale"]
    assert [n["label"] for n in rationale] == [
        "NOTE: must run before compile() or the linker will fail"
    ]
