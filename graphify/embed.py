"""Optional local-embedding backend — a *semantic* ranking signal for queries.

graphify's default query path is structural and deterministic: no model, no API,
$0. This module adds an **opt-in** semantic backend that fuses into the ranking
alongside the structural signals (it never replaces them). It answers fuzzy
questions — "where do we handle auth timeouts" — that no exact-token match can.

Design constraints:

  * Strictly optional. Nothing here runs unless the user passes ``--semantic``
    or calls ``graphify embed``. Import stays cheap; heavy deps are lazy.
  * Local-first. The backend is Ollama's embeddings endpoint or a
    ``sentence-transformers`` model — both run on the user's machine, no API key.
  * Cached. Node embeddings are computed once by ``graphify embed`` and written
    to a sidecar next to ``graph.json``; queries embed only the question and
    cosine-compare against the cached matrix.

The embedder is injectable (``embed_texts(texts, embedder=...)``) so tests run
with a deterministic fake and never need a model server.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Callable, Sequence

import numpy as np

from graphify.paths import out_path

# An embedder maps a list of texts to an (N, D) float matrix.
Embedder = Callable[[Sequence[str]], "np.ndarray"]

_DEFAULT_OLLAMA_MODEL = "nomic-embed-text"
_DEFAULT_ST_MODEL = "all-MiniLM-L6-v2"
_SIDECAR_NAME = "embeddings.npz"
_META_NAME = "embeddings.meta.json"


# --------------------------------------------------------------------------- #
# node text
# --------------------------------------------------------------------------- #

def node_text(data: dict) -> str:
    """The text used to represent a node to the embedder.

    Label carries the identifier; source_file and community add topical context
    so two ``handle()`` functions in different subsystems embed differently. Any
    LLM-derived summary/docstring, when present, is the richest signal.
    """
    parts = [
        str(data.get("label", "")),
        str(data.get("summary") or data.get("docstring") or data.get("description") or ""),
        str(data.get("source_file", "")),
        str(data.get("community_name") or ""),
    ]
    return " — ".join(p for p in parts if p).strip() or str(data.get("label", ""))


# --------------------------------------------------------------------------- #
# backends
# --------------------------------------------------------------------------- #

def _ollama_embedder(model: str, host: str) -> Embedder:
    import urllib.request

    url = host.rstrip("/") + "/api/embeddings"

    def embed(texts: Sequence[str]) -> np.ndarray:
        vecs: list[list[float]] = []
        for text in texts:
            payload = json.dumps({"model": model, "prompt": text}).encode("utf-8")
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (local host)
                body = json.loads(resp.read().decode("utf-8"))
            vec = body.get("embedding")
            if not vec:
                raise RuntimeError(f"ollama returned no embedding for model {model!r}")
            vecs.append(vec)
        return np.asarray(vecs, dtype=np.float32)

    return embed


def _sentence_transformers_embedder(model: str) -> Embedder:
    from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]

    st_model = SentenceTransformer(model)

    def embed(texts: Sequence[str]) -> np.ndarray:
        return np.asarray(st_model.encode(list(texts), show_progress_bar=False), dtype=np.float32)

    return embed


def get_embedder() -> tuple[Embedder, str]:
    """Resolve a local embedder, returning ``(embedder, model_tag)``.

    Honours ``GRAPHIFY_EMBED_BACKEND`` (``ollama`` | ``sentence-transformers``)
    and ``GRAPHIFY_EMBED_MODEL``; otherwise auto-detects Ollama, then
    sentence-transformers. Raises with actionable guidance if neither is usable.
    """
    backend = os.environ.get("GRAPHIFY_EMBED_BACKEND", "").strip().lower()
    model = os.environ.get("GRAPHIFY_EMBED_MODEL", "").strip()
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

    def _try_ollama() -> tuple[Embedder, str] | None:
        import urllib.request

        try:
            with urllib.request.urlopen(host.rstrip("/") + "/api/tags", timeout=3):
                pass
        except Exception:
            return None
        m = model or _DEFAULT_OLLAMA_MODEL
        return _ollama_embedder(m, host), f"ollama:{m}"

    def _try_st() -> tuple[Embedder, str] | None:
        try:
            import sentence_transformers  # noqa: F401
        except Exception:
            return None
        m = model or _DEFAULT_ST_MODEL
        return _sentence_transformers_embedder(m), f"st:{m}"

    if backend == "ollama":
        got = _try_ollama()
        if got:
            return got
        raise RuntimeError(f"GRAPHIFY_EMBED_BACKEND=ollama but no Ollama server at {host}")
    if backend in ("sentence-transformers", "st"):
        got = _try_st()
        if got:
            return got
        raise RuntimeError("GRAPHIFY_EMBED_BACKEND=sentence-transformers but the package is not installed")

    for probe in (_try_ollama, _try_st):
        got = probe()
        if got:
            return got
    raise RuntimeError(
        "no local embedding backend available. Start Ollama (and `ollama pull "
        f"{_DEFAULT_OLLAMA_MODEL}`) or `pip install sentence-transformers`, "
        "then re-run with --semantic."
    )


def embed_texts(texts: Sequence[str], *, embedder: Embedder | None = None) -> np.ndarray:
    if not texts:
        return np.zeros((0, 0), dtype=np.float32)
    if embedder is None:
        embedder, _ = get_embedder()
    return embedder(texts)


# --------------------------------------------------------------------------- #
# sidecar IO
# --------------------------------------------------------------------------- #

def sidecar_paths(graph_path: str | None) -> tuple[Path, Path]:
    """(vectors.npz, meta.json) paths beside the graph (or under GRAPHIFY_OUT)."""
    if graph_path:
        base = Path(graph_path).resolve().parent
    else:
        base = out_path().resolve()
    return base / _SIDECAR_NAME, base / _META_NAME


def _normalize(matrix: np.ndarray) -> np.ndarray:
    if matrix.size == 0:
        return matrix
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def build_embeddings(
    G,
    graph_path: str | None,
    *,
    embedder: Embedder | None = None,
    model_tag: str | None = None,
    force: bool = False,
) -> dict:
    """Compute (or refresh) the node-embedding sidecar. Returns a small summary.

    Skips work when a sidecar already covers the current node set and model tag,
    unless ``force``. Vectors are L2-normalized on write so query-time scoring is
    a plain dot product.
    """
    if embedder is None:
        embedder, model_tag = get_embedder()
    model_tag = model_tag or "custom"

    node_ids = list(G.nodes())
    texts = [node_text(G.nodes[n]) for n in node_ids]
    content_hash = _hash_ids_model(node_ids, model_tag)

    vec_path, meta_path = sidecar_paths(graph_path)
    if not force and meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta.get("content_hash") == content_hash and vec_path.exists():
                return {"status": "cached", "count": len(node_ids), "model": model_tag, "path": str(vec_path)}
        except Exception:
            pass

    matrix = _normalize(embed_texts(texts, embedder=embedder).astype(np.float32))
    vec_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(vec_path, vectors=matrix, ids=np.asarray(node_ids, dtype=object))
    meta_path.write_text(
        json.dumps(
            {
                "model": model_tag,
                "count": len(node_ids),
                "dim": int(matrix.shape[1]) if matrix.size else 0,
                "content_hash": content_hash,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return {"status": "built", "count": len(node_ids), "model": model_tag, "path": str(vec_path)}


def _hash_ids_model(node_ids: Sequence[str], model_tag: str) -> str:
    h = hashlib.sha256()
    h.update(model_tag.encode("utf-8"))
    for nid in node_ids:  # order-sensitive: a reordered graph is a different build
        h.update(b"\0")
        h.update(str(nid).encode("utf-8"))
    return h.hexdigest()


def load_embeddings(graph_path: str | None) -> tuple[list[str], np.ndarray, dict] | None:
    """Load (ids, normalized-matrix, meta) from the sidecar, or None if absent."""
    vec_path, meta_path = sidecar_paths(graph_path)
    if not vec_path.exists():
        return None
    with np.load(vec_path, allow_pickle=True) as data:
        ids = [str(x) for x in data["ids"].tolist()]
        matrix = np.asarray(data["vectors"], dtype=np.float32)
    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    return ids, matrix, meta


# --------------------------------------------------------------------------- #
# query-time scoring (the ranking backend)
# --------------------------------------------------------------------------- #

def semantic_scores_for_query(
    G,
    question: str,
    *,
    graph_path: str | None = None,
    embedder: Embedder | None = None,
) -> dict[str, float]:
    """Cosine similarity between the question and every embedded node.

    Returns ``{node_id: score}`` for nodes present in both the sidecar and ``G``.
    Raises if no sidecar exists (the caller — query/bench — catches this and
    degrades to structural-only ranking with a note). Query embedding uses the
    same model tag the sidecar was built with when possible.
    """
    loaded = load_embeddings(graph_path)
    if loaded is None:
        raise RuntimeError(
            "no embeddings sidecar found. Run `graphify embed` first to enable --semantic."
        )
    ids, matrix, meta = loaded
    if matrix.size == 0:
        return {}
    if embedder is None:
        # Pin the query embedder to the sidecar's model so vectors are comparable.
        model = meta.get("model", "")
        if model and ":" in model and not os.environ.get("GRAPHIFY_EMBED_MODEL"):
            backend, _, name = model.partition(":")
            os.environ.setdefault("GRAPHIFY_EMBED_BACKEND", "ollama" if backend == "ollama" else "sentence-transformers")
            os.environ["GRAPHIFY_EMBED_MODEL"] = name
        embedder, _ = get_embedder()
    q = _normalize(embed_texts([question], embedder=embedder).astype(np.float32))
    if q.size == 0:
        return {}
    sims = matrix @ q[0]  # both L2-normalized -> dot product is cosine
    present = set(G.nodes())
    return {nid: float(sims[i]) for i, nid in enumerate(ids) if nid in present}
