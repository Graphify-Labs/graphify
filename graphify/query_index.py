"""Compact deterministic Tier-0 candidate index for graph queries."""
from __future__ import annotations

from collections.abc import Hashable, Iterable, Iterator
from dataclasses import dataclass
import hashlib
from itertools import chain
import json
import os
from pathlib import Path
import re
import tempfile

import networkx as nx

from graphify.ontology import relation_spec


_TOKEN_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|[0-9]+")
_STOP = frozenset({"the", "and", "how", "does", "is", "are", "of", "to", "a", "an"})


def _tokens(value: str) -> frozenset[str]:
    return frozenset(
        token.lower()
        for token in _TOKEN_RE.findall(str(value or "").replace("_", " "))
        if len(token) >= 2 and token.lower() not in _STOP
    )


def _aliases(value: object) -> tuple[str, ...]:
    """Normalize aliases once so postings and their fingerprint stay aligned."""

    if not value:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Iterable):
        return tuple(sorted(str(alias) for alias in value))
    return (str(value),)


def _incident_edge_data(
    graph: nx.Graph | nx.DiGraph | nx.MultiGraph | nx.MultiDiGraph,
    node_id: Hashable,
) -> Iterator[dict]:
    """Yield both directions without collapsing reciprocal directed arcs."""

    if isinstance(graph, nx.MultiDiGraph):
        for edge in chain(
            graph.out_edges(node_id, keys=True, data=True),
            graph.in_edges(node_id, keys=True, data=True),
        ):
            yield edge[-1]
        return
    if isinstance(graph, nx.DiGraph):
        for edge in chain(
            graph.out_edges(node_id, data=True),
            graph.in_edges(node_id, data=True),
        ):
            yield edge[-1]
        return
    edges = (
        graph.edges(node_id, keys=True, data=True)
        if isinstance(graph, nx.MultiGraph)
        else graph.edges(node_id, data=True)
    )
    for edge in edges:
        yield edge[-1]


def graph_fingerprint(graph: nx.Graph) -> str:
    """Hash graph identity fields so an index is never reused after graph drift."""

    digest = hashlib.sha256()
    for node_id, data in sorted(graph.nodes(data=True), key=lambda item: str(item[0])):
        digest.update(str(node_id).encode())
        digest.update(b"\0")
        digest.update(str(data.get("label", "")).encode())
        digest.update(b"\0")
        digest.update(str(data.get("source_file", "")).encode())
        for alias in _aliases(data.get("aliases")):
            digest.update(b"\0")
            digest.update(alias.encode())
        digest.update(b"\n")
    edge_rows = []
    if isinstance(graph, (nx.MultiGraph, nx.MultiDiGraph)):
        edge_rows = [(u, v, d) for u, v, _key, d in graph.edges(keys=True, data=True)]
    else:
        edge_rows = list(graph.edges(data=True))
    for source, target, data in sorted(
        edge_rows,
        key=lambda item: (str(item[0]), str(item[1]), str(item[2].get("relation", ""))),
    ):
        digest.update(f"{source}\0{target}\0{data.get('relation', '')}\n".encode())
    return digest.hexdigest()


@dataclass(frozen=True)
class QueryCandidate:
    node_id: str
    label: str
    score: float
    matched_terms: frozenset[str]
    strong_relations: tuple[str, ...]


@dataclass(frozen=True)
class TierZeroPacket:
    candidates: tuple[QueryCandidate, ...]
    query_terms: frozenset[str]
    llm_invoked: bool = False


class QueryIndex:
    """Inverted token index with compact node metadata and no model dependency."""

    def __init__(
        self,
        *,
        fingerprint: str,
        nodes: dict[str, dict],
        postings: dict[str, tuple[str, ...]],
    ) -> None:
        self.fingerprint = fingerprint
        self._nodes = nodes
        self._postings = postings

    @classmethod
    def from_graph(cls, graph: nx.Graph) -> "QueryIndex":
        postings: dict[str, set[str]] = {}
        nodes: dict[str, dict] = {}
        for node_id, data in graph.nodes(data=True):
            aliases = _aliases(data.get("aliases"))
            node_tokens = set(_tokens(str(data.get("label", node_id))))
            node_tokens.update(_tokens(str(data.get("source_file", ""))))
            for alias in aliases:
                node_tokens.update(_tokens(str(alias)))
            relations: set[str] = set()
            for edge_data in _incident_edge_data(graph, node_id):
                relation = str(edge_data.get("relation", "")).lower()
                spec = relation_spec(relation)
                if spec and spec.category in {"runtime", "data", "reference"}:
                    relations.add(spec.name)
            node_key = str(node_id)
            nodes[node_key] = {
                "label": str(data.get("label", node_id)),
                "tokens": sorted(node_tokens),
                "relations": sorted(relations),
                "degree": int(graph.degree(node_id)),
            }
            for token in node_tokens:
                postings.setdefault(token, set()).add(node_key)
        return cls(
            fingerprint=graph_fingerprint(graph),
            nodes=nodes,
            postings={token: tuple(sorted(ids)) for token, ids in postings.items()},
        )

    def search(self, query: str, *, limit: int = 8) -> TierZeroPacket:
        terms = _tokens(query)
        candidate_ids = {node for term in terms for node in self._postings.get(term, ())}
        ranked: list[QueryCandidate] = []
        for node_id in candidate_ids:
            data = self._nodes[node_id]
            matched = terms & frozenset(data["tokens"])
            if not matched:
                continue
            coverage = len(matched) / max(1, len(terms))
            score = len(matched) * 10.0 + coverage * 5.0 + min(data["degree"], 20) / 20
            ranked.append(QueryCandidate(
                node_id=node_id,
                label=data["label"],
                score=round(score, 4),
                matched_terms=matched,
                strong_relations=tuple(data["relations"]),
            ))
        ranked.sort(key=lambda item: (-item.score, len(item.label), item.node_id))
        return TierZeroPacket(tuple(ranked[:max(0, int(limit))]), terms)

    def matches_graph(self, graph: nx.Graph) -> bool:
        # The sidecar lives in a repository-controlled directory. Its stored
        # fingerprint alone is not proof that its candidate set came from the
        # graph, so reject injected or omitted node identifiers before reuse.
        graph_node_ids = {str(node_id) for node_id in graph.nodes}
        return (
            self.fingerprint == graph_fingerprint(graph)
            and set(self._nodes) == graph_node_ids
        )

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "graph_fingerprint": self.fingerprint,
            "nodes": self._nodes,
            "postings": {token: list(ids) for token, ids in self._postings.items()},
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "QueryIndex":
        if not isinstance(payload, dict) or payload.get("version") != 1:
            raise ValueError("unsupported query index version")
        raw_nodes = payload.get("nodes")
        raw_postings = payload.get("postings")
        if not isinstance(raw_nodes, dict) or not isinstance(raw_postings, dict):
            raise ValueError("invalid query index containers")

        nodes: dict[str, dict] = {}
        for key, value in raw_nodes.items():
            if not isinstance(value, dict):
                raise ValueError("invalid query index node")
            tokens = value.get("tokens")
            relations = value.get("relations")
            degree = value.get("degree")
            if (
                not isinstance(value.get("label"), str)
                or not isinstance(tokens, list)
                or not all(isinstance(token, str) for token in tokens)
                or not isinstance(relations, list)
                or not all(isinstance(relation, str) for relation in relations)
                or isinstance(degree, bool)
                or not isinstance(degree, int)
            ):
                raise ValueError("invalid query index node metadata")
            nodes[str(key)] = dict(value)

        postings: dict[str, tuple[str, ...]] = {}
        for token, ids in raw_postings.items():
            if not isinstance(ids, list) or not all(isinstance(node, str) for node in ids):
                raise ValueError("invalid query index posting")
            if any(node not in nodes for node in ids):
                raise ValueError("query index posting references an unknown node")
            postings[str(token)] = tuple(ids)

        return cls(
            fingerprint=str(payload.get("graph_fingerprint", "")),
            nodes=nodes,
            postings=postings,
        )


class QueryIndexStore:
    """Persist Tier-0 postings beside a graph and invalidate on graph changes."""

    def __init__(self, graph_path: Path | str) -> None:
        self.graph_path = Path(graph_path).resolve()
        name = "query-index.json" if self.graph_path.name == "graph.json" else (
            f"{self.graph_path.stem}.query-index.json"
        )
        self.index_path = self.graph_path.with_name(name)

    def load_or_build(self, graph: nx.Graph) -> tuple[QueryIndex, bool]:
        """Return ``(index, cache_hit)``; persistence failures remain non-blocking."""

        signature = self._graph_file_signature(graph)
        if signature is not None:
            try:
                payload = json.loads(self.index_path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("invalid query index payload")
                if payload.get("version") == 1 and payload.get("graph_file") == signature:
                    index = QueryIndex.from_dict(payload["index"])
                    # The file digest proves which bytes produced the sidecar,
                    # not that the caller left the in-memory graph unchanged.
                    # Recheck semantic identity before serving cached evidence.
                    if index.matches_graph(graph):
                        return index, True
            except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
                pass

        index = QueryIndex.from_graph(graph)
        if signature is not None:
            self._write({
                "version": 1,
                "graph_file": signature,
                "index": index.to_dict(),
            })
        return index, False

    def _graph_file_signature(self, graph: nx.Graph) -> dict[str, str] | None:
        digest = graph.graph.get("_graphify_file_sha256")
        if isinstance(digest, str) and digest:
            return {"sha256": digest}
        try:
            digest = hashlib.sha256(self.graph_path.read_bytes()).hexdigest()
        except OSError:
            return None
        return {"sha256": digest}

    def _write(self, payload: dict) -> None:
        temporary: Path | None = None
        descriptor: int | None = None
        try:
            # The graph directory can belong to an untrusted repository. An
            # exclusive same-directory inode prevents pre-planted symlinks and
            # still keeps the final replace atomic on a single filesystem.
            descriptor, temporary_name = tempfile.mkstemp(
                dir=self.index_path.parent,
                prefix=f".{self.index_path.name}.",
                suffix=".tmp",
            )
            temporary = Path(temporary_name)
            stream = os.fdopen(descriptor, "w", encoding="utf-8")
            descriptor = None
            with stream:
                json.dump(payload, stream, ensure_ascii=False, sort_keys=True)
            os.replace(temporary, self.index_path)
        except OSError:
            # Read-only repositories still get an in-memory index for this run.
            pass
        finally:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
