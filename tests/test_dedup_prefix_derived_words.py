"""A word formed by prepending letters to another word is a different word.

`_content_token_swap` (#2576) blocks a fuzzy merge when two labels differ in a
content word, and asks `_same_word_variant` whether each differing token pair is
one word misspelt. That helper fell back to Jaro-Winkler, which scores a
one-letter prefix derivation such as ``synchronous`` / ``asynchronous`` at 97.2,
above the merge threshold, so an antonym was read as a typo and the pair merged.

`_crossfile_fileanchored_blocked` (#1284) only blocks cross-file pairs, so two
class docstrings in one file ("Synchronous HTTP client." on ``Client``,
"Asynchronous HTTP client." on ``AsyncClient``) collapsed into one rationale
node, and the graph then claimed, as EXTRACTED, that ``AsyncClient``'s rationale
was "Synchronous HTTP client.". The repo's own ``worked/httpx`` example hits it.
"""
from __future__ import annotations

import pytest

from graphify.build import build
from graphify.dedup import deduplicate_entities
from graphify.extract import extract

# Each pair merges on v8 before this fix: the only differing token is the other
# token with letters prepended.
_PREFIX_DERIVED_PAIRS = [
    ("Synchronous HTTP client.", "Asynchronous HTTP client."),
    ("Typical retry schedule for uploads.", "Atypical retry schedule for uploads."),
    ("Cyclic dependency graph walker.", "Acyclic dependency graph walker."),
    ("Reload the plugin registry from disk.", "Preload the plugin registry from disk."),
]


def _same_file_pair(label_a: str, label_b: str, file_type: str) -> list[dict]:
    return [
        {"id": "n1", "label": label_a, "file_type": file_type,
         "source_file": "pkg/client.py", "source_location": "L10"},
        {"id": "n2", "label": label_b, "file_type": file_type,
         "source_file": "pkg/client.py", "source_location": "L40"},
    ]


@pytest.mark.parametrize("file_type", ["rationale", "document", "concept"])
@pytest.mark.parametrize(("label_a", "label_b"), _PREFIX_DERIVED_PAIRS)
def test_prefix_derived_word_is_not_merged_as_a_typo(label_a, label_b, file_type):
    nodes = _same_file_pair(label_a, label_b, file_type)
    result, _ = deduplicate_entities(nodes, [], communities={})
    assert sorted(n["label"] for n in result) == sorted([label_a, label_b])


@pytest.mark.parametrize("file_type", ["rationale", "document", "concept"])
def test_suffix_inflection_still_merges(file_type):
    """Letters appended (a plural) are still one word: only prepended letters
    make a different word, so this restatement keeps merging."""
    nodes = _same_file_pair(
        "Request handler for uploads.", "Request handlers for uploads.", file_type
    )
    result, _ = deduplicate_entities(nodes, [], communities={})
    assert len(result) == 1


def test_sync_and_async_client_docstrings_keep_their_own_rationale(tmp_path):
    """End to end: AST extraction plus the default deduplicating build."""
    src = tmp_path / "client.py"
    src.write_text(
        "class Client:\n"
        '    """Synchronous HTTP client."""\n'
        "\n"
        "\n"
        "class AsyncClient:\n"
        '    """Asynchronous HTTP client."""\n',
        encoding="utf-8",
    )
    extraction = extract([src], root=tmp_path, cache_root=tmp_path, parallel=False)
    G = build([extraction], root=tmp_path)

    rationale_of: dict[str, set[str]] = {}
    for u, v, data in G.edges(data=True):
        if data.get("relation") != "rationale_for":
            continue
        rationale, owner = (u, v) if G.nodes[u].get("file_type") == "rationale" else (v, u)
        rationale_of.setdefault(G.nodes[owner]["label"], set()).add(G.nodes[rationale]["label"])

    assert rationale_of == {
        "Client": {"Synchronous HTTP client."},
        "AsyncClient": {"Asynchronous HTTP client."},
    }
