"""Compact deterministic Tier-0 candidate index for graph queries."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re

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


def graph_fingerprint(graph: nx.Graph) -> str:
    """Hash graph identity fields so an index is never reused after graph drift."""

    digest = hashlib.sha256()
    for node_id, data in sorted(graph.nodes(data=True), key=lambda item: str(item[0])):
        digest.update(str(node_id).encode())
        digest.update(b"\0")
        digest.update(str(data.get("label", "")).encode())
        digest.update(b"\n")
    edge_rows = []
    if graph.is_multigraph():
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
        # The undirected view preserves edge data while making both incoming and
        # outgoing relations visible; constructing it once avoids a per-node copy.
        incident_graph = graph.to_undirected(as_view=True) if graph.is_directed() else graph
        postings: dict[str, set[str]] = {}
        nodes: dict[str, dict] = {}
        for node_id, data in graph.nodes(data=True):
            aliases = data.get("aliases") or ()
            if isinstance(aliases, str):
                aliases = (aliases,)
            node_tokens = set(_tokens(str(data.get("label", node_id))))
            node_tokens.update(_tokens(str(data.get("source_file", ""))))
            for alias in aliases:
                node_tokens.update(_tokens(str(alias)))
            relations: set[str] = set()
            incident = (
                incident_graph.edges(node_id, keys=True, data=True)
                if incident_graph.is_multigraph()
                else incident_graph.edges(node_id, data=True)
            )
            for edge in incident:
                relation = str(edge[-1].get("relation", "")).lower()
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
        return self.fingerprint == graph_fingerprint(graph)

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "graph_fingerprint": self.fingerprint,
            "nodes": self._nodes,
            "postings": {token: list(ids) for token, ids in self._postings.items()},
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "QueryIndex":
        if payload.get("version") != 1:
            raise ValueError("unsupported query index version")
        return cls(
            fingerprint=str(payload.get("graph_fingerprint", "")),
            nodes={str(key): dict(value) for key, value in payload.get("nodes", {}).items()},
            postings={
                str(token): tuple(str(node) for node in ids)
                for token, ids in payload.get("postings", {}).items()
            },
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
        temporary = self.index_path.with_name(
            f".{self.index_path.name}.{os.getpid()}.tmp"
        )
        try:
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            os.replace(temporary, self.index_path)
        except OSError:
            # Read-only repositories still get an in-memory index for this run.
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
